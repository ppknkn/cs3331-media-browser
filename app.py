"""Frame / 拾光: a read-only, loopback-only local media browser (Python 3.10+)."""

from __future__ import annotations

import argparse
import json
import mimetypes
import os
from pathlib import Path, PurePosixPath
import secrets
import stat
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from itertools import islice
from urllib.parse import parse_qs, unquote, urlsplit
import webbrowser


APP_DIR = Path(__file__).resolve().parent
STATIC_DIR = APP_DIR / "static"
IMAGE_EXTENSIONS = frozenset({".jpg", ".jpeg", ".png", ".gif", ".webp", ".avif", ".bmp"})
VIDEO_EXTENSIONS = frozenset({".mp4", ".webm", ".mov", ".m4v", ".ogg", ".ogv"})
MEDIA_EXTENSIONS = IMAGE_EXTENSIONS | VIDEO_EXTENSIONS
MIME_TYPES = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
              ".gif": "image/gif", ".webp": "image/webp", ".avif": "image/avif",
              ".bmp": "image/bmp", ".mp4": "video/mp4", ".m4v": "video/mp4",
              ".webm": "video/webm", ".mov": "video/quicktime", ".ogg": "video/ogg",
              ".ogv": "video/ogg"}
MAX_BODY_BYTES = 8192
MAX_SCAN_ENTRIES = 100000
PICKER_TIMEOUT = 90
CHUNK_BYTES = 64 * 1024


class ApiError(Exception):
    def __init__(self, status: int, message: str, code: str = "request_error"):
        super().__init__(message)
        self.status, self.message, self.code = status, message, code


def relative_path(value: str) -> PurePosixPath:
    """Validate API paths before native Windows/POSIX path conversion."""
    if not isinstance(value, str) or len(value) > 4096:
        raise ApiError(400, "路径格式不正确。", "invalid_path")
    if "\\" in value or ":" in value or "\x00" in value or value.startswith("/"):
        raise ApiError(403, "只能访问已打开文件夹内的相对路径。", "forbidden_path")
    parts = value.split("/")
    if any(part in {".", ".."} for part in parts):
        raise ApiError(403, "路径不能包含上级目录。", "forbidden_path")
    return PurePosixPath(value)


def inside_root(root: Path, value: str) -> Path:
    rel = relative_path(value)
    try:
        resolved = root.joinpath(*rel.parts).resolve(strict=True)
        resolved.relative_to(root)
    except (ValueError, RuntimeError):
        raise ApiError(403, "该路径超出已打开的文件夹。", "forbidden_path") from None
    except (OSError, FileNotFoundError):
        raise ApiError(404, "文件或文件夹已不存在，请刷新。", "not_found") from None
    return resolved


def validate_root(value: str) -> Path:
    if not isinstance(value, str) or not value.strip() or len(value) > 4096 or "\x00" in value:
        raise ApiError(400, "请输入有效的本地文件夹路径。", "invalid_root")
    candidate = Path(value.strip()).expanduser()
    if not candidate.is_absolute() or str(candidate).startswith(("\\\\", "//")):
        raise ApiError(400, "请使用本地文件夹的绝对路径。", "invalid_root")
    try:
        resolved = candidate.resolve(strict=True)
        if not resolved.is_dir():
            raise ApiError(400, "所选路径不是文件夹。", "invalid_root")
        with os.scandir(resolved):
            pass
        return resolved
    except ApiError:
        raise
    except PermissionError:
        raise ApiError(403, "无法读取此文件夹，请检查访问权限。", "permission_denied") from None
    except OSError:
        raise ApiError(404, "找不到此文件夹，请检查路径。", "not_found") from None


class LibraryState:
    def __init__(self, root: Path | None = None):
        self.lock = threading.RLock()
        self.root = validate_root(str(root)) if root is not None else None
        self.session = secrets.token_urlsafe(18)
        self.token = secrets.token_urlsafe(32)
        self.picker_busy = False

    def summary(self) -> dict:
        with self.lock:
            return {"session": self.session, "root": str(self.root) if self.root else None,
                    "name": self.root.name or str(self.root) if self.root else None,
                    "pickerBusy": self.picker_busy}

    def snapshot(self, expected: str | None) -> tuple[Path, str]:
        with self.lock:
            if expected != self.session:
                raise ApiError(409, "已切换文件夹，请重新加载。", "stale_session")
            if self.root is None:
                raise ApiError(409, "请先打开一个本地文件夹。", "no_root")
            return self.root, self.session

    def ensure_current(self, session: str) -> None:
        with self.lock:
            if session != self.session:
                raise ApiError(409, "已切换文件夹，请重新加载。", "stale_session")

    def replace(self, root: Path, expected: str | None) -> dict:
        with self.lock:
            self.ensure_current(expected)
            self.root = root
            self.session = secrets.token_urlsafe(18)
            return self.summary()


def scan_library(root: Path, folder: Path, session: str, limit: int = MAX_SCAN_ENTRIES,
                 level_limit: int = MAX_SCAN_ENTRIES) -> dict:
    """Read one level; album totals/cover images include safe nested descendants."""
    budget = [limit]
    level_partial = False
    warnings: set[str] = set()

    def entries(directory: Path, charge_budget: bool = True):
        nonlocal level_partial
        try:
            cap = max(0, budget[0] if charge_budget else level_limit)
            with os.scandir(directory) as iterator:
                # Bound the directory iterator before sorting: sorting a whole
                # directory would defeat the scanner's memory/work budget.
                sampled = list(islice(iterator, cap + 1))
            truncated = len(sampled) > cap
            ordered = sorted(sampled[:cap], key=lambda entry: (entry.name.casefold(), entry.name))
            if truncated:
                if charge_budget:
                    warnings.add(f"图集递归统计达到 {limit} 项上限；部分计数不完整，当前层级入口由独立预算保留。")
                else:
                    level_partial = True
                    warnings.add(f"当前文件夹超过 {level_limit} 项，本层列表已截断；请打开更小的子文件夹浏览。")
            for entry in ordered:
                if charge_budget:
                    budget[0] -= 1
                try:
                    # Ignore symlinks/junctions pointing beyond the library and avoid cycles.
                    path = Path(entry.path)
                    if entry.is_symlink():
                        continue
                    # pathlib.is_junction was only added in Python 3.12. On
                    # Windows 3.10 junctions are directory reparse points.
                    attributes = getattr(entry.stat(follow_symlinks=False), "st_file_attributes", 0)
                    reparse_point = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
                    if attributes & reparse_point and entry.is_dir(follow_symlinks=False):
                        continue
                    resolved = path.resolve(strict=True)
                    resolved.relative_to(root)
                    yield entry, resolved
                except (OSError, ValueError, RuntimeError):
                    continue
            if truncated and charge_budget:
                budget[0] = -1
        except OSError:
            warnings.add("部分文件夹无法读取，已跳过。")

    def media_item(path: Path) -> dict | None:
        extension = path.suffix.lower()
        if extension not in MEDIA_EXTENSIONS:
            return None
        try:
            info = path.stat()
        except OSError:
            warnings.add("部分文件已移动或无法读取，已跳过。")
            return None
        return {"name": path.name, "path": path.relative_to(root).as_posix(),
                "type": "image" if extension in IMAGE_EXTENSIONS else "video",
                "size": info.st_size, "modified": info.st_mtime,
                "extension": extension[1:].upper()}

    def album_info(directory: Path) -> dict:
        photos = videos = 0
        cover = None
        seen: set[Path] = set()
        stack = [directory]
        while stack and budget[0] >= 0:
            current = stack.pop()
            if current in seen:
                continue
            seen.add(current)
            for entry, path in entries(current):
                try:
                    if entry.is_dir(follow_symlinks=False):
                        stack.append(path)
                    elif entry.is_file(follow_symlinks=False):
                        item = media_item(path)
                        if item:
                            if item["type"] == "image":
                                photos += 1
                                if cover is None or cover["type"] == "video":
                                    cover = item
                            else:
                                videos += 1
                                if cover is None:
                                    cover = item
                except OSError:
                    continue
        try:
            modified = directory.stat().st_mtime
        except OSError:
            modified = 0
        return {"name": directory.name, "path": directory.relative_to(root).as_posix(),
                "imageCount": photos, "videoCount": videos, "count": photos + videos,
                "cover": cover, "modified": modified, "partial": budget[0] < 0}

    albums, media = [], []
    # Discovery of the current level must not depend on how many descendants
    # an earlier album contains. Current-level discovery has its own cap.
    for entry, path in entries(folder, charge_budget=False):
        try:
            if entry.is_dir(follow_symlinks=False):
                albums.append(album_info(path))
            elif entry.is_file(follow_symlinks=False):
                item = media_item(path)
                if item:
                    media.append(item)
        except OSError:
            continue
    return {"session": session, "path": folder.relative_to(root).as_posix() if folder != root else "",
            "albums": albums, "media": media, "warnings": sorted(warnings), "partial": level_partial,
            "scannedAt": time.time()}


def choose_folder(initial: str | None = None, timeout: float = PICKER_TIMEOUT) -> str | None:
    """Tk runs in its own process; the HTTP worker never owns Tk's event loop."""
    script = (
        "import json,sys,tkinter as tk; from tkinter import filedialog; "
        "window=tk.Tk(); window.withdraw(); window.attributes('-topmost',True); "
        "selected=filedialog.askdirectory(parent=window,title='选择要浏览的本地媒体文件夹',"
        "initialdir=sys.argv[1] or None,mustexist=True); "
        "window.destroy(); print(json.dumps(selected,ensure_ascii=True))"
    )
    try:
        result = subprocess.run([sys.executable, "-c", script, initial or ""],
                                capture_output=True, text=True, timeout=timeout,
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except subprocess.TimeoutExpired:
        raise ApiError(408, "选择窗口已超时关闭，请重试或输入路径。", "picker_timeout") from None
    except OSError:
        raise ApiError(503, "无法启动文件夹选择器，请输入路径。", "picker_unavailable") from None
    if result.returncode:
        raise ApiError(503, "当前环境无法显示选择窗口，请输入路径。", "picker_unavailable")
    try:
        selected = json.loads(result.stdout.strip())
    except (ValueError, TypeError):
        raise ApiError(503, "文件夹选择器未返回有效结果，请输入路径。", "picker_unavailable") from None
    if not isinstance(selected, str):
        raise ApiError(503, "文件夹选择器未返回有效结果，请输入路径。", "picker_unavailable")
    return selected or None


def parse_range(header: str | None, size: int) -> tuple[int, int, bool]:
    if header is None:
        return 0, size - 1, False
    try:
        unit, bounds = header.split("=", 1)
        # Unsupported units and multi-range requests are ignored; a full 200
        # response is valid and avoids mislabelling satisfiable ranges as 416.
        if unit.lower() != "bytes" or "," in bounds:
            return 0, size - 1, False
        if size <= 0:
            raise ValueError
        start_text, end_text = bounds.split("-", 1)
        if start_text:
            if not start_text.isdecimal() or (end_text and not end_text.isdecimal()):
                raise ValueError
            start = int(start_text)
            end = min(int(end_text), size - 1) if end_text else size - 1
            if start >= size or end < start:
                raise ValueError
        else:
            if not end_text.isdecimal() or int(end_text) <= 0:
                raise ValueError
            start, end = max(0, size - int(end_text)), size - 1
        return start, end, True
    except (ValueError, OverflowError):
        raise ApiError(416, "请求的视频分段范围无效。", "invalid_range") from None


class MediaServer(ThreadingHTTPServer):
    daemon_threads = True
    block_on_close = False

    def __init__(self, address, state: LibraryState, verbose: bool = False):
        self.state = state
        self.verbose = verbose
        super().__init__(address, MediaHandler)


class MediaHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "Frame/1.0"
    sys_version = ""

    @property
    def state(self) -> LibraryState:
        return self.server.state

    def log_message(self, format, *args):
        if self.server.verbose:
            print(f"[{self.log_date_time_string()}] {self.command} {urlsplit(self.path).path.split('/')[1:2]} {args[1] if len(args) > 1 else ''}")

    def _boundary(self) -> None:
        host = self.headers.get("Host", "")
        try:
            parsed = urlsplit("//" + host)
            if parsed.hostname not in {"127.0.0.1", "localhost", "::1"} or parsed.port != self.server.server_port:
                raise ValueError
            if parsed.username or parsed.password or parsed.path or parsed.query or parsed.fragment:
                raise ValueError
        except ValueError:
            raise ApiError(403, "仅允许本机访问此服务。", "invalid_host") from None
        origin = self.headers.get("Origin")
        if origin is not None and origin != f"http://{host}":
            raise ApiError(403, "此请求来源不受允许。", "invalid_origin")
        if self.headers.get("Sec-Fetch-Site") == "cross-site":
            raise ApiError(403, "此请求来源不受允许。", "invalid_origin")

    def _headers(self, status: int, content_type: str, length: int, extra: dict | None = None):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(length))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; media-src 'self' blob:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
        if extra:
            for name, value in extra.items():
                self.send_header(name, str(value))
        self.end_headers()

    def _json(self, status: int, value: dict, extra: dict | None = None):
        payload = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self._headers(status, "application/json; charset=utf-8", len(payload), extra)
        if self.command != "HEAD":
            self.wfile.write(payload)

    def _body(self) -> dict:
        if self.headers.get("Transfer-Encoding"):
            raise ApiError(400, "不支持此请求传输方式。", "invalid_body")
        if self.headers.get_content_type() != "application/json":
            raise ApiError(415, "请求内容必须为 JSON。", "invalid_body")
        try:
            length = int(self.headers.get("Content-Length", "-1"))
        except ValueError:
            raise ApiError(400, "请求长度无效。", "invalid_body") from None
        if length < 0:
            raise ApiError(411, "缺少请求长度。", "invalid_body")
        if length > MAX_BODY_BYTES:
            raise ApiError(413, "请求内容过大。", "invalid_body")
        try:
            value = json.loads(self.rfile.read(length))
        except (ValueError, UnicodeError):
            raise ApiError(400, "无法解析 JSON 请求。", "invalid_body") from None
        if not isinstance(value, dict):
            raise ApiError(400, "JSON 请求必须是对象。", "invalid_body")
        return value

    def _mutation(self) -> dict:
        token = self.headers.get("X-App-Token", "")
        if not token.isascii() or not secrets.compare_digest(token, self.state.token):
            raise ApiError(403, "操作凭据无效，请刷新页面。", "invalid_token")
        body = self._body()
        self.state.ensure_current(body.get("session"))
        return body

    def _dispatch(self):
        self._boundary()
        parsed = urlsplit(self.path)
        route = unquote(parsed.path)
        query = parse_qs(parsed.query, keep_blank_values=True)
        if self.command in {"GET", "HEAD"}:
            if route == "/api/bootstrap":
                self._json(200, {**self.state.summary(), "token": self.state.token,
                                 "formats": {"images": sorted(IMAGE_EXTENSIONS), "videos": sorted(VIDEO_EXTENSIONS)}})
            elif route == "/api/library":
                root, session = self.state.snapshot(query.get("session", [None])[0])
                folder = inside_root(root, query.get("path", [""])[0])
                if not folder.is_dir():
                    raise ApiError(400, "所选路径不是图集文件夹。", "invalid_path")
                result = scan_library(root, folder, session)
                self.state.ensure_current(session)
                self._json(200, result)
            elif route.startswith("/media/"):
                pieces = route.split("/", 3)
                if len(pieces) != 4:
                    raise ApiError(404, "未找到此媒体。", "not_found")
                self._media(pieces[2], pieces[3])
            else:
                self._static(route)
        elif self.command == "POST" and route in {"/api/root", "/api/picker"}:
            body = self._mutation()
            if route == "/api/root":
                root = validate_root(body.get("path"))
                self._json(200, self.state.replace(root, body.get("session")))
            else:
                with self.state.lock:
                    if self.state.picker_busy:
                        raise ApiError(409, "文件夹选择窗口已打开。", "picker_busy")
                    self.state.picker_busy = True
                    initial = str(self.state.root) if self.state.root else None
                try:
                    selected = choose_folder(initial)
                    self.state.ensure_current(body.get("session"))
                    result = self.state.replace(validate_root(selected), body.get("session")) if selected else self.state.summary()
                    self._json(200, {**result, "cancelled": selected is None})
                finally:
                    with self.state.lock:
                        self.state.picker_busy = False
        elif self.command == "POST":
            raise ApiError(404, "未找到此接口。", "not_found")
        else:
            raise ApiError(405, "不支持此请求方法。", "method_not_allowed")

    def _static(self, route: str):
        files = {"/": "index.html", "/index.html": "index.html", "/app.js": "app.js",
                 "/style.css": "style.css", "/favicon.svg": "favicon.svg"}
        filename = files.get(route)
        if filename is None:
            raise ApiError(404, "未找到此页面。", "not_found")
        path = STATIC_DIR / filename
        payload = path.read_bytes()
        mime = mimetypes.guess_type(filename)[0] or "application/octet-stream"
        self._headers(200, mime + ("; charset=utf-8" if mime.startswith("text/") or filename.endswith(".js") else ""), len(payload))
        if self.command != "HEAD":
            self.wfile.write(payload)

    def _media(self, session: str, value: str):
        root, _ = self.state.snapshot(session)
        path = inside_root(root, value)
        if not path.is_file() or path.suffix.lower() not in MEDIA_EXTENSIONS:
            raise ApiError(404, "未找到可浏览的媒体文件。", "not_found")
        try:
            with path.open("rb") as stream:
                size = os.fstat(stream.fileno()).st_size
                self.state.ensure_current(session)
                try:
                    # RFC 9110 section 14.2: Range only modifies GET semantics.
                    range_header = self.headers.get("Range") if self.command == "GET" else None
                    start, end, partial = parse_range(range_header, size)
                except ApiError as error:
                    self._json(error.status, {"error": error.message, "code": error.code},
                               {"Content-Range": f"bytes */{size}", "Accept-Ranges": "bytes"})
                    return
                length = max(0, end - start + 1)
                extra = {"Accept-Ranges": "bytes"}
                if partial:
                    extra["Content-Range"] = f"bytes {start}-{end}/{size}"
                self._headers(206 if partial else 200, MIME_TYPES[path.suffix.lower()], length, extra)
                if self.command == "HEAD":
                    return
                stream.seek(start)
                remaining = length
                while remaining:
                    chunk = stream.read(min(CHUNK_BYTES, remaining))
                    if not chunk:
                        self.close_connection = True
                        return
                    self.wfile.write(chunk)
                    remaining -= len(chunk)
        except PermissionError:
            raise ApiError(403, "无法读取此媒体，请检查文件权限。", "permission_denied") from None
        except FileNotFoundError:
            raise ApiError(404, "媒体已移动或删除，请刷新。", "not_found") from None

    def _handle(self):
        self.connection.settimeout(15)
        try:
            self._dispatch()
        except ApiError as error:
            if self.command not in {"GET", "HEAD"}:
                self.close_connection = True
            self._json(error.status, {"error": error.message, "code": error.code})
        except (BrokenPipeError, ConnectionResetError, TimeoutError):
            self.close_connection = True
        except OSError:
            self.close_connection = True
            self._json(500, {"error": "读取文件时发生错误，请刷新后重试。", "code": "io_error"})
        except Exception:
            self.close_connection = True
            self._json(500, {"error": "服务发生错误，请重试。", "code": "internal_error"})

    do_GET = _handle
    do_HEAD = _handle
    do_POST = _handle
    do_PUT = _handle
    do_DELETE = _handle
    do_PATCH = _handle
    do_OPTIONS = _handle


def create_server(host: str = "127.0.0.1", port: int = 8877,
                  root: str | Path | None = None, verbose: bool = False) -> MediaServer:
    if host != "127.0.0.1":
        raise ValueError("Frame only binds to 127.0.0.1")
    return MediaServer((host, port), LibraryState(Path(root) if root is not None else None), verbose)


def main():
    parser = argparse.ArgumentParser(description="拾光 · 本地媒体浏览器")
    parser.add_argument("--port", type=int, default=8877)
    parser.add_argument("--root", help="启动时打开的本地文件夹绝对路径")
    parser.add_argument("--demo", action="store_true", help="打开项目内离线演示素材")
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()
    if not 0 <= args.port <= 65535:
        parser.error("端口应为 0 到 65535；0 由系统分配可用端口。")
    root = str(APP_DIR / "demo-media") if args.demo else args.root
    try:
        server = create_server(port=args.port, root=root, verbose=args.verbose)
    except (ApiError, OSError) as error:
        parser.exit(1, f"启动失败：{error}\n")
    url = f"http://127.0.0.1:{server.server_port}"
    print(f"拾光已启动：{url}\n仅在本机读取媒体；按 Ctrl+C 退出。", flush=True)
    if not args.no_browser:
        threading.Timer(0.4, webbrowser.open, args=(url,)).start()
    try:
        server.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
