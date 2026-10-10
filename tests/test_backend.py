"""Independent, offline tests. All media fixtures are temporary artificial bytes.

Run with: python -m unittest discover -s tests -v
No user directory or native picker is opened by this suite.
"""

import concurrent.futures
import hashlib
import http.client
import json
import os
from pathlib import Path
import subprocess
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.parse import quote, urlencode

import app


class FilesystemCase(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="frame-test-")
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name).resolve()
        self.root = self.base / "library"
        self.root.mkdir()
        self.outside = self.base / "outside"
        self.outside.mkdir()
        (self.outside / "secret.jpg").write_bytes(b"OUTSIDE SECRET")

    def file(self, path, content=b"fixture"):
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        return target

    def assert_api_error(self, code, status, callable_, *args):
        with self.assertRaises(app.ApiError) as result:
            callable_(*args)
        self.assertEqual((result.exception.code, result.exception.status), (code, status))


class PathAndScanTests(FilesystemCase):
    def test_relative_paths_accept_nested_unicode_and_spaces(self):
        self.assertEqual(app.relative_path("旅行记/海边 ＆ sunset #1.JPG").as_posix(), "旅行记/海边 ＆ sunset #1.JPG")
        self.assertEqual(app.relative_path("").as_posix(), ".")

    def test_relative_paths_reject_traversal_native_drives_and_nul(self):
        for value in ("..", "a/../secret.jpg", "./x", "/etc/passwd", "C:/x", "C:\\x", "a\\b", "//host/x", "x\x00.jpg"):
            with self.subTest(value=value):
                self.assert_api_error("forbidden_path", 403, app.relative_path, value)

    def test_invalid_path_types_and_length(self):
        for value in (None, 42, "x" * 4097):
            with self.subTest(value_type=type(value).__name__):
                self.assert_api_error("invalid_path", 400, app.relative_path, value)

    def test_resolve_existing_nested_and_missing(self):
        target = self.file("图集/photo.PNG")
        self.assertEqual(app.inside_root(self.root, "图集/photo.PNG"), target.resolve())
        self.assert_api_error("not_found", 404, app.inside_root, self.root, "missing.jpg")

    def test_validate_root_accepts_absolute_readable_directory(self):
        self.assertEqual(app.validate_root("  " + str(self.root) + "  "), self.root)

    def test_validate_root_rejects_invalid_types_relative_unc_and_file(self):
        for value in (None, 12, "", "   ", "relative", "\\\\server\\share", "//server/share", "x\x00"):
            with self.subTest(value=value):
                self.assert_api_error("invalid_root", 400, app.validate_root, value)
        self.assert_api_error("invalid_root", 400, app.validate_root, str(self.file("not-a-directory.txt")))
        self.assert_api_error("not_found", 404, app.validate_root, str(self.base / "absent"))

    def test_validate_root_permission_error_mapping(self):
        with patch("app.os.scandir", side_effect=PermissionError("fixture")):
            self.assert_api_error("permission_denied", 403, app.validate_root, str(self.root))

    def test_scan_recognizes_all_declared_extensions_case_insensitively(self):
        for index, extension in enumerate(sorted(app.MEDIA_EXTENSIONS)):
            self.file(f"{index:02}{extension.upper()}")
        self.file("unsupported.svg")
        self.file("plain.txt")
        result = app.scan_library(self.root, self.root, "session")
        self.assertEqual(len(result["media"]), len(app.MEDIA_EXTENSIONS))
        for item in result["media"]:
            expected = "image" if Path(item["name"]).suffix.lower() in app.IMAGE_EXTENSIONS else "video"
            self.assertEqual(item["type"], expected)
            self.assertEqual(item["size"], 7)
        self.assertEqual(result["warnings"], [])

    def test_recursive_album_counts_prefers_image_cover_and_keeps_empty_album(self):
        self.file("旅行记/a.mp4")
        self.file("旅行记/嵌套/b.JPG")
        self.file("旅行记/嵌套/c.png")
        (self.root / "空图集").mkdir()
        self.file("root.jpeg")
        result = app.scan_library(self.root, self.root, "s")
        albums = {item["name"]: item for item in result["albums"]}
        self.assertEqual((albums["旅行记"]["imageCount"], albums["旅行记"]["videoCount"]), (2, 1))
        self.assertEqual(albums["旅行记"]["cover"]["type"], "image")
        self.assertEqual(albums["空图集"]["count"], 0)
        self.assertIsNone(albums["空图集"]["cover"])
        self.assertEqual([item["name"] for item in result["media"]], ["root.jpeg"])
        nested = app.scan_library(self.root, self.root / "旅行记", "s")
        self.assertEqual(nested["path"], "旅行记")
        self.assertEqual(len(nested["albums"]), 1)
        self.assertEqual([item["name"] for item in nested["media"]], ["a.mp4"])

    def test_empty_directory_is_successful_empty_library(self):
        result = app.scan_library(self.root, self.root, "s")
        self.assertEqual((result["albums"], result["media"], result["path"]), ([], [], ""))

    def test_scan_budget_never_hides_current_level_regression(self):
        for index in range(8):
            self.file(f"a-large/{index}.jpg")
        self.file("z-other/b.jpg")
        self.file("z-root.png")
        result = app.scan_library(self.root, self.root, "s", limit=2)
        self.assertEqual([album["name"] for album in result["albums"]], ["a-large", "z-other"])
        self.assertEqual([item["name"] for item in result["media"]], ["z-root.png"])
        self.assertTrue(result["warnings"])
        self.assertTrue(all(album["partial"] for album in result["albums"]))
        self.assertEqual(result["albums"][0]["count"], 2)

    def test_scandir_consumption_is_bounded_before_recursive_sort(self):
        for index in range(15):
            self.file(f"large/{index:02}.jpg")
        self.file("z.jpg")
        original = os.scandir
        consumed = {}
        class CountedIterator:
            def __init__(self, directory):
                self.directory = str(directory)
                self.delegate = original(directory)
            def __enter__(self):
                return self
            def __exit__(self, *args):
                self.delegate.close()
            def __iter__(self):
                return self
            def __next__(self):
                item = next(self.delegate)
                consumed[self.directory] = consumed.get(self.directory, 0) + 1
                return item
        with patch("app.os.scandir", side_effect=CountedIterator):
            result = app.scan_library(self.root, self.root, "s", limit=3)
        self.assertEqual(consumed[str(self.root / "large")], 4)
        self.assertEqual(result["albums"][0]["count"], 3)
        self.assertEqual([item["name"] for item in result["media"]], ["z.jpg"])

    def test_current_level_independent_cap_reads_only_cap_plus_one(self):
        for index in range(15):
            self.file(f"{index:02}.jpg")
        original = os.scandir
        consumed = []
        class CountedIterator:
            def __enter__(inner):
                inner.delegate = original(self.root)
                return inner
            def __exit__(inner, *args):
                inner.delegate.close()
            def __iter__(inner):
                return inner
            def __next__(inner):
                item = next(inner.delegate)
                consumed.append(item.name)
                return item
        with patch("app.os.scandir", return_value=CountedIterator()):
            result = app.scan_library(self.root, self.root, "s", limit=0, level_limit=2)
        self.assertEqual(len(consumed), 3)
        self.assertEqual(len(result["media"]), 2)
        self.assertTrue(result["partial"])
        self.assertTrue(any("本层列表已截断" in warning for warning in result["warnings"]))

    def test_scan_preserves_special_unicode_html_like_filename(self):
        # Angle brackets are valid POSIX filenames but illegal native Windows names.
        name = "中文 & # ' \".jpg" if os.name != "nt" else "中文 & # ' ［img onerror=alert(1)］.jpg"
        self.file(name)
        result = app.scan_library(self.root, self.root, "s")
        self.assertEqual(result["media"][0]["name"], name)
        self.assertEqual(result["media"][0]["path"], name)

    def test_symlink_outside_and_cycle_are_skipped(self):
        try:
            (self.root / "escape").symlink_to(self.outside, target_is_directory=True)
            (self.root / "cycle").symlink_to(self.root, target_is_directory=True)
        except OSError as error:
            self.skipTest(f"OS does not permit creating symlinks: {error}")
        self.assertEqual(app.scan_library(self.root, self.root, "s")["albums"], [])
        self.assert_api_error("forbidden_path", 403, app.inside_root, self.root, "escape/secret.jpg")

    def test_scan_skips_symlink_flagged_entry_with_deterministic_stub(self):
        target = self.file("simulated-link.jpg")
        class Entry:
            name = target.name
            path = str(target)
            def is_symlink(self):
                return True
            def stat(self, **kwargs):
                raise AssertionError("A symlink must be skipped before stat or resolve")
        class Directory:
            def __enter__(self):
                return iter([Entry()])
            def __exit__(self, *args):
                pass
        with patch("app.os.scandir", return_value=Directory()):
            result = app.scan_library(self.root, self.root, "s")
        self.assertEqual(result["media"], [])

    @unittest.skipUnless(os.name == "nt", "Windows junction regression")
    def test_windows_junction_outside_and_cycle_skipped_on_python310(self):
        links = [(self.root / "escape", self.outside), (self.root / "cycle", self.root)]
        try:
            for link, target in links:
                result = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)], capture_output=True)
                if result.returncode:
                    self.fail("Could not create junction fixture: " + result.stdout.decode(errors="replace"))
            scan = app.scan_library(self.root, self.root, "s")
            self.assertEqual(scan["albums"], [])
            self.assert_api_error("forbidden_path", 403, app.inside_root, self.root, "escape/secret.jpg")
        finally:
            # Remove only junction entries themselves; never recursively follow them.
            for link, _ in links:
                if link.exists():
                    os.rmdir(link)


class StateAndRangeTests(FilesystemCase):
    def test_no_root_and_stale_session(self):
        state = app.LibraryState()
        self.assertIsNone(state.summary()["root"])
        self.assert_api_error("no_root", 409, state.snapshot, state.session)
        self.assert_api_error("stale_session", 409, state.snapshot, "old")

    def test_replace_rotates_session_retains_token(self):
        state = app.LibraryState(self.root)
        old_session, token = state.session, state.token
        result = state.replace(self.outside, old_session)
        self.assertNotEqual(result["session"], old_session)
        self.assertEqual(state.token, token)
        self.assertEqual(state.snapshot(result["session"])[0], self.outside)
        self.assert_api_error("stale_session", 409, state.replace, self.root, old_session)

    def test_range_full_single_open_suffix_and_clamp(self):
        cases = [(None, (0, 9, False)), ("bytes=0-0", (0, 0, True)), ("bytes=2-4", (2, 4, True)),
                 ("bytes=6-", (6, 9, True)), ("bytes=-3", (7, 9, True)), ("bytes=-99", (0, 9, True)),
                 ("bytes=2-999", (2, 9, True)), ("BYTES=0-2", (0, 2, True))]
        for header, expected in cases:
            with self.subTest(header=header):
                self.assertEqual(app.parse_range(header, 10), expected)

    def test_range_invalid_and_unsatisfiable(self):
        for header in ("bytes=10-", "bytes=6-2", "bytes=-0", "bytes=-", "bytes=x-4", "bytes=0-x", "malformed", "bytes=0-1-2"):
            with self.subTest(header=header):
                self.assert_api_error("invalid_range", 416, app.parse_range, header, 10)

    def test_multirange_and_unknown_unit_are_ignored_regression(self):
        for header in ("bytes=0-1,3-4", "items=0-1", "unknown=99-100"):
            with self.subTest(header=header):
                self.assertEqual(app.parse_range(header, 10), (0, 9, False))

    def test_empty_media_full_response_and_range(self):
        self.assertEqual(app.parse_range(None, 0), (0, -1, False))
        self.assert_api_error("invalid_range", 416, app.parse_range, "bytes=0-", 0)

    def test_server_rejects_nonloopback_bind_before_socket_creation(self):
        for host in ("0.0.0.0", "192.0.2.1", "localhost", "::1"):
            with self.subTest(host=host), self.assertRaises(ValueError):
                app.create_server(host=host, port=0)


class PickerUnitTests(unittest.TestCase):
    def test_picker_selected_and_cancelled_with_subprocess_stub(self):
        for stdout, expected in ((json.dumps("C:\\人工素材", ensure_ascii=True), "C:\\人工素材"), ('""', None)):
            with self.subTest(expected=expected), patch("app.subprocess.run", return_value=subprocess.CompletedProcess([], 0, stdout, "")) as run:
                self.assertEqual(app.choose_folder("fixture", timeout=1), expected)
                self.assertEqual(run.call_args.kwargs["timeout"], 1)

    def test_picker_timeout_and_unavailable(self):
        errors = [(subprocess.TimeoutExpired("fixture", 1), "picker_timeout", 408), (OSError("fixture"), "picker_unavailable", 503)]
        for error, code, status in errors:
            with self.subTest(code=code), patch("app.subprocess.run", side_effect=error), self.assertRaises(app.ApiError) as result:
                app.choose_folder()
            self.assertEqual((result.exception.code, result.exception.status), (code, status))

    def test_picker_rejects_failed_or_invalid_subprocess_output(self):
        for code, stdout in ((1, ""), (0, "garbage"), (0, "null"), (0, "{}")):
            with self.subTest(returncode=code, stdout=stdout), patch("app.subprocess.run", return_value=subprocess.CompletedProcess([], code, stdout, "")), self.assertRaises(app.ApiError) as result:
                app.choose_folder()
            self.assertEqual(result.exception.code, "picker_unavailable")


class HttpTests(FilesystemCase):
    def setUp(self):
        super().setUp()
        self.payload = b"0123456789abcdefghij"
        self.file("旅行记/海边 ＆ #1.JPG", self.payload)
        self.file("movie.mp4", self.payload)
        self.file("empty.mp4", b"")
        self.file("private.txt", b"PRIVATE")
        self.server = app.create_server(port=0, root=self.root)
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": .01}, daemon=True)
        self.thread.start()
        self.addCleanup(self.stop_server)
        self.host = f"127.0.0.1:{self.server.server_port}"
        self.session = self.server.state.session
        self.token = self.server.state.token

    def stop_server(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def request(self, method, route, payload=None, headers=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
        try:
            connection.request(method, route, body=payload, headers=headers or {})
            response = connection.getresponse()
            return response.status, dict(response.getheaders()), response.read()
        finally:
            connection.close()

    def post(self, route="/api/root", body=None, headers=None):
        defaults = {"Content-Type": "application/json", "X-App-Token": self.token}
        defaults.update(headers or {})
        return self.request("POST", route, json.dumps(body if body is not None else {"session": self.session, "path": str(self.root)}), defaults)

    def media(self, name="movie.mp4", session=None):
        return "/media/" + (session or self.session) + "/" + quote(name, safe="/")

    def library(self, path="", session=None):
        return "/api/library?" + urlencode({"session": session or self.session, "path": path})

    def assert_json_error(self, response, status, code):
        self.assertEqual(response[0], status)
        self.assertEqual(json.loads(response[2])["code"], code)

    def test_bootstrap_and_static_security_headers(self):
        status, headers, body = self.request("GET", "/api/bootstrap")
        self.assertEqual(status, 200)
        bootstrap = json.loads(body)
        self.assertEqual((bootstrap["session"], bootstrap["token"], bootstrap["root"]), (self.session, self.token, str(self.root)))
        self.assertEqual(headers["X-Content-Type-Options"], "nosniff")
        self.assertIn("frame-ancestors 'none'", headers["Content-Security-Policy"])
        self.assertEqual(headers["Cache-Control"], "no-store")
        for path in ("/", "/index.html", "/style.css", "/app.js", "/favicon.svg"):
            with self.subTest(path=path):
                self.assertEqual(self.request("GET", path)[0], 200)

    def test_static_allowlist_does_not_expose_source_or_traversal(self):
        for path in ("/app.py", "/README.md", "/../app.py", "/%2e%2e/app.py", "/static/index.html"):
            with self.subTest(path=path):
                self.assert_json_error(self.request("GET", path), 404, "not_found")

    def test_head_static_and_api_have_no_body(self):
        for route in ("/", "/api/bootstrap", self.library()):
            with self.subTest(route=route):
                status, headers, body = self.request("HEAD", route)
                self.assertEqual((status, body), (200, b""))
                self.assertGreater(int(headers["Content-Length"]), 0)

    def test_invalid_hosts_are_rejected(self):
        hosts = ["example.com", "127.0.0.1:1", f"user@{self.host}", f"{self.host}/x", f"{self.host}?x=1", "localhost:bad"]
        for host in hosts:
            with self.subTest(host=host):
                self.assert_json_error(self.request("GET", "/api/bootstrap", headers={"Host": host}), 403, "invalid_host")

    def test_localhost_host_with_correct_port_is_allowed(self):
        self.assertEqual(self.request("GET", "/api/bootstrap", headers={"Host": f"localhost:{self.server.server_port}"})[0], 200)

    def test_origin_cross_site_rejected_and_same_origin_allowed(self):
        for origin in ("https://evil.example", "null", "http://127.0.0.1:1"):
            with self.subTest(origin=origin):
                self.assert_json_error(self.request("GET", "/api/bootstrap", headers={"Origin": origin}), 403, "invalid_origin")
        self.assert_json_error(self.request("GET", "/api/bootstrap", headers={"Sec-Fetch-Site": "cross-site"}), 403, "invalid_origin")
        self.assertEqual(self.request("GET", "/api/bootstrap", headers={"Origin": f"http://{self.host}", "Sec-Fetch-Site": "same-origin"})[0], 200)

    def test_missing_wrong_and_unicode_token_fail_without_500_regression(self):
        for token in ("", "wrong", "é"):
            with self.subTest(token=token):
                self.assert_json_error(self.post(headers={"X-App-Token": token}), 403, "invalid_token")

    def test_json_body_invalid_shapes_and_bytes(self):
        headers = {"Content-Type": "application/json", "X-App-Token": self.token}
        for body in (b"not json", b"[]", b"null", b"42", b'"text"', b"\xff"):
            with self.subTest(body=body):
                self.assert_json_error(self.request("POST", "/api/root", body, headers), 400, "invalid_body")

    def test_body_content_type_transfer_encoding_and_size(self):
        self.assert_json_error(self.post(headers={"Content-Type": "text/plain"}), 415, "invalid_body")
        self.assert_json_error(self.post(headers={"Transfer-Encoding": "chunked"}), 400, "invalid_body")
        self.assert_json_error(self.post(headers={"Content-Length": str(app.MAX_BODY_BYTES + 1)}), 413, "invalid_body")
        self.assert_json_error(self.post(headers={"Content-Length": "invalid"}), 400, "invalid_body")
        self.assert_json_error(self.post(headers={"Content-Length": "-1"}), 411, "invalid_body")

    def test_post_stale_session_does_not_mutate_root(self):
        self.assert_json_error(self.post(body={"session": "stale", "path": str(self.outside)}), 409, "stale_session")
        self.assertEqual(self.server.state.root, self.root)

    def test_root_switch_old_library_and_media_are_stale(self):
        response = self.post(body={"session": self.session, "path": str(self.outside)})
        self.assertEqual(response[0], 200)
        new_session = json.loads(response[2])["session"]
        self.assertNotEqual(new_session, self.session)
        self.assert_json_error(self.request("GET", self.library()), 409, "stale_session")
        self.assert_json_error(self.request("GET", self.media()), 409, "stale_session")
        self.assertEqual(self.request("GET", self.library(session=new_session))[0], 200)

    def test_root_invalid_or_absent_rejected_and_old_root_retained(self):
        for path, status, code in (("relative", 400, "invalid_root"), (str(self.base / "missing"), 404, "not_found"), (str(self.root / "private.txt"), 400, "invalid_root")):
            with self.subTest(path=path):
                self.assert_json_error(self.post(body={"session": self.session, "path": path}), status, code)
                self.assertEqual(self.server.state.root, self.root)

    def test_library_nested_and_missing_and_file_path(self):
        response = self.request("GET", self.library("旅行记"))
        self.assertEqual(response[0], 200)
        self.assertEqual(json.loads(response[2])["media"][0]["name"], "海边 ＆ #1.JPG")
        self.assert_json_error(self.request("GET", self.library("missing")), 404, "not_found")
        self.assert_json_error(self.request("GET", self.library("movie.mp4")), 400, "invalid_path")

    def test_library_scan_switch_midscan_rejects_stale_result(self):
        original = app.scan_library
        def switching_scan(*args, **kwargs):
            result = original(*args, **kwargs)
            self.server.state.replace(self.outside, self.session)
            return result
        with patch("app.scan_library", side_effect=switching_scan):
            self.assert_json_error(self.request("GET", self.library()), 409, "stale_session")

    def test_media_full_get_unicode_url_and_mime(self):
        status, headers, body = self.request("GET", self.media("旅行记/海边 ＆ #1.JPG"))
        self.assertEqual((status, body), (200, self.payload))
        self.assertEqual(headers["Content-Type"], "image/jpeg")
        self.assertEqual(headers["Accept-Ranges"], "bytes")
        self.assertEqual(int(headers["Content-Length"]), len(self.payload))

    def test_media_ranges_single_open_suffix_clamp(self):
        cases = [("bytes=2-5", b"2345", "bytes 2-5/20"), ("bytes=17-", b"hij", "bytes 17-19/20"),
                 ("bytes=-4", b"ghij", "bytes 16-19/20"), ("bytes=17-999", b"hij", "bytes 17-19/20")]
        for header, expected, content_range in cases:
            with self.subTest(header=header):
                status, headers, body = self.request("GET", self.media(), headers={"Range": header})
                self.assertEqual((status, body), (206, expected))
                self.assertEqual(headers["Content-Range"], content_range)
                self.assertEqual(int(headers["Content-Length"]), len(expected))

    def test_media_unsatisfiable_range_includes_total(self):
        response = self.request("GET", self.media(), headers={"Range": "bytes=20-"})
        self.assert_json_error(response, 416, "invalid_range")
        self.assertEqual(response[1]["Content-Range"], "bytes */20")

    def test_head_ignores_satisfiable_and_invalid_range_regression(self):
        for header in ("bytes=2-5", "bytes=999-", "nonsense"):
            with self.subTest(header=header):
                status, headers, body = self.request("HEAD", self.media(), headers={"Range": header})
                self.assertEqual((status, body), (200, b""))
                self.assertEqual(headers["Content-Length"], "20")
                self.assertNotIn("Content-Range", headers)

    def test_media_multirange_and_unknown_unit_return_full_200_regression(self):
        for header in ("bytes=0-1,3-4", "items=0-1"):
            with self.subTest(header=header):
                status, headers, body = self.request("GET", self.media(), headers={"Range": header})
                self.assertEqual((status, body), (200, self.payload))
                self.assertNotIn("Content-Range", headers)

    def test_empty_media_get_head_and_range(self):
        for method in ("GET", "HEAD"):
            with self.subTest(method=method):
                status, headers, body = self.request(method, self.media("empty.mp4"))
                self.assertEqual((status, body, headers["Content-Length"]), (200, b"", "0"))
        response = self.request("GET", self.media("empty.mp4"), headers={"Range": "bytes=0-"})
        self.assert_json_error(response, 416, "invalid_range")
        self.assertEqual(response[1]["Content-Range"], "bytes */0")

    def test_media_missing_nonmedia_and_directory_not_exposed(self):
        for name in ("absent.jpg", "private.txt", "旅行记"):
            with self.subTest(name=name):
                self.assert_json_error(self.request("GET", self.media(name)), 404, "not_found")

    def test_media_and_library_reject_encoded_traversal_drives_and_backslash(self):
        for path in ("../outside/secret.jpg", "C:/secret.jpg", "..\\outside\\secret.jpg", "/outside/secret.jpg"):
            with self.subTest(path=path):
                self.assert_json_error(self.request("GET", self.media(path)), 403, "forbidden_path")
                self.assert_json_error(self.request("GET", self.library(path)), 403, "forbidden_path")

    def test_reads_do_not_modify_source_bytes_or_mtime(self):
        before = {path: (hashlib.sha256(path.read_bytes()).hexdigest(), path.stat().st_mtime_ns) for path in self.root.rglob("*") if path.is_file()}
        self.request("GET", self.library())
        self.request("GET", self.media())
        self.request("GET", self.media(), headers={"Range": "bytes=0-2"})
        after = {path: (hashlib.sha256(path.read_bytes()).hexdigest(), path.stat().st_mtime_ns) for path in before}
        self.assertEqual(before, after)

    def test_unknown_mutation_and_unsupported_methods(self):
        self.assert_json_error(self.post(route="/api/unknown"), 404, "not_found")
        for method in ("PUT", "DELETE", "PATCH", "OPTIONS"):
            with self.subTest(method=method):
                self.assert_json_error(self.request(method, "/api/root"), 405, "method_not_allowed")

    def test_picker_selected_and_cancelled_release_busy(self):
        with patch("app.choose_folder", return_value=None):
            response = self.post("/api/picker", {"session": self.session})
        self.assertEqual(response[0], 200)
        self.assertTrue(json.loads(response[2])["cancelled"])
        self.assertEqual(self.server.state.session, self.session)
        self.assertFalse(self.server.state.picker_busy)
        with patch("app.choose_folder", return_value=str(self.outside)):
            response = self.post("/api/picker", {"session": self.session})
        self.assertEqual(response[0], 200)
        self.assertFalse(json.loads(response[2])["cancelled"])
        self.assertEqual(self.server.state.root, self.outside)
        self.assertFalse(self.server.state.picker_busy)

    def test_picker_failure_releases_busy(self):
        with patch("app.choose_folder", side_effect=app.ApiError(503, "fixture", "picker_unavailable")):
            self.assert_json_error(self.post("/api/picker", {"session": self.session}), 503, "picker_unavailable")
        self.assertFalse(self.server.state.picker_busy)
        self.assertEqual(self.server.state.root, self.root)

    def test_picker_busy_concurrent_request_and_stale_completion_release(self):
        started, release = threading.Event(), threading.Event()
        def delayed_picker(_initial):
            started.set()
            if not release.wait(4):
                raise RuntimeError("fixture release timed out")
            return str(self.outside)
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool, patch("app.choose_folder", side_effect=delayed_picker):
            pending = pool.submit(self.post, "/api/picker", {"session": self.session})
            try:
                self.assertTrue(started.wait(2))
                self.assert_json_error(self.post("/api/picker", {"session": self.session}), 409, "picker_busy")
                self.assertEqual(self.post(body={"session": self.session, "path": str(self.root)})[0], 200)
            finally:
                release.set()
            self.assert_json_error(pending.result(timeout=5), 409, "stale_session")
        self.assertFalse(self.server.state.picker_busy)
        self.assertEqual(self.server.state.root, self.root)


if __name__ == "__main__":
    unittest.main(verbosity=2)
