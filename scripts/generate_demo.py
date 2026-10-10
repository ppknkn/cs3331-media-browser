"""Draw reproducible offline demo media; application runtime needs no FFmpeg.

Uses only Python's standard library. If FFmpeg is available, export JPEG photos
and an H.264 MP4. Otherwise export BMP photos, which Frame also recognizes.
"""

from __future__ import annotations

import argparse
import math
from pathlib import Path
import random
import shutil
import struct
import subprocess
import sys


WIDTH, HEIGHT = 960, 640
PROJECT_DIR = Path(__file__).resolve().parents[1]


class Canvas:
    def __init__(self, top: tuple[int, int, int], bottom: tuple[int, int, int]):
        self.pixels = bytearray()
        for y in range(HEIGHT):
            ratio = y / (HEIGHT - 1)
            color = bytes(round(a + (b - a) * ratio) for a, b in zip(top, bottom))
            self.pixels.extend(color * WIDTH)

    def span(self, y: int, left: int, right: int, color: tuple[int, int, int]):
        if not 0 <= y < HEIGHT:
            return
        left, right = max(0, left), min(WIDTH, right)
        if left < right:
            self.pixels[(y * WIDTH + left) * 3:(y * WIDTH + right) * 3] = bytes(color) * (right - left)

    def rectangle(self, x: int, y: int, w: int, h: int, color: tuple[int, int, int]):
        for row in range(max(y, 0), min(y + h, HEIGHT)):
            self.span(row, x, x + w, color)

    def ellipse(self, x: int, y: int, rx: int, ry: int, color: tuple[int, int, int]):
        for row in range(max(0, y - ry), min(HEIGHT, y + ry + 1)):
            half = round(rx * math.sqrt(max(0, 1 - ((row - y) / ry) ** 2)))
            self.span(row, x - half, x + half + 1, color)

    def polygon(self, points: list[tuple[int, int]], color: tuple[int, int, int]):
        for row in range(max(0, min(y for _, y in points)), min(HEIGHT, max(y for _, y in points) + 1)):
            intersections = []
            for (x1, y1), (x2, y2) in zip(points, points[1:] + points[:1]):
                if (y1 <= row < y2) or (y2 <= row < y1):
                    intersections.append(x1 + (row - y1) * (x2 - x1) / (y2 - y1))
            intersections.sort()
            for left, right in zip(intersections[::2], intersections[1::2]):
                self.span(row, math.ceil(left), math.ceil(right), color)


def draw_scene(theme: str, seed: int) -> bytes:
    rng = random.Random(seed)
    if theme == "city":
        canvas = Canvas((14, 25, 54), (90, 100, 146))
        canvas.ellipse(760, 130, 47, 47, (236, 215, 174))
        for _ in range(85):
            canvas.rectangle(rng.randrange(10, WIDTH - 10), rng.randrange(12, 300), 2, 2, (182, 193, 218))
        for layer, base, color in [(0, 515, (51, 65, 93)), (1, 600, (24, 39, 66))]:
            x = -10
            while x < WIDTH:
                width, height = rng.randrange(45, 105), rng.randrange(100, 280)
                canvas.rectangle(x, base - height, width, height, color)
                if layer == 1:
                    for row in range(base - height + 14, base - 12, 23):
                        for column in range(x + 10, x + width - 7, 18):
                            if rng.random() > 0.36:
                                canvas.rectangle(column, row, 5, 9, (225, 178, 112))
                x += width + rng.randrange(8, 22)
        canvas.rectangle(0, 600, WIDTH, 40, (18, 33, 57))
        for x in range(20, WIDTH, 160):
            canvas.rectangle(x, 565, 3, 65, (198, 184, 144))
            canvas.ellipse(x + 1, 563, 6, 3, (255, 223, 163))
    elif theme == "coast":
        canvas = Canvas((74, 114, 155), (245, 185, 140))
        sun_x = 680 + (seed % 4) * 22
        canvas.ellipse(sun_x, 280, 62, 62, (255, 219, 153))
        canvas.polygon([(0, 340), (110, 285), (245, 315), (330, 280), (480, 360), (960, 355), (960, 640), (0, 640)], (65, 116, 133))
        for y in range(385, 620, 11):
            half = round((y - 350) * 0.20)
            canvas.span(y, sun_x - half + rng.randrange(-20, 20), sun_x + half, (204, 181, 146))
        canvas.polygon([(0, 470), (130, 493), (245, 512), (390, 515), (580, 595), (960, 640), (0, 640)], (217, 172, 127))
        canvas.polygon([(0, 514), (180, 543), (340, 552), (440, 587), (475, 640), (0, 640)], (92, 115, 104))
        for x, y in [(80, 474), (132, 483), (195, 497)]:
            canvas.polygon([(x, y), (x + 8, y - 83), (x + 14, y)], (48, 84, 78))
            canvas.polygon([(x + 9, y - 90), (x - 45, y - 78), (x + 4, y - 71)], (40, 82, 77))
            canvas.polygon([(x + 9, y - 90), (x + 58, y - 72), (x + 15, y - 71)], (40, 82, 77))
        canvas.polygon([(440, 386), (505, 387), (490, 397), (454, 398)], (45, 66, 78))
        canvas.polygon([(475, 383), (475, 322), (502, 383)], (243, 233, 204))
    else:
        canvas = Canvas((121, 168, 181), (239, 228, 196))
        canvas.ellipse(725, 148, 52, 52, (250, 234, 185))
        canvas.polygon([(0, 394), (115, 240), (226, 360), (411, 155), (610, 360), (794, 226), (960, 399), (960, 640), (0, 640)], (139, 160, 157))
        canvas.polygon([(307, 267), (411, 155), (515, 262), (445, 231), (411, 216), (381, 247)], (219, 224, 209))
        canvas.polygon([(0, 433), (140, 329), (273, 432), (410, 338), (543, 446), (710, 343), (960, 455), (960, 640), (0, 640)], (81, 131, 126))
        canvas.polygon([(0, 500), (110, 460), (240, 509), (510, 463), (691, 500), (960, 438), (960, 640), (0, 640)], (47, 105, 94))
        canvas.polygon([(618, 492), (585, 545), (708, 607), (662, 640), (452, 640), (599, 596), (534, 555), (600, 493)], (206, 191, 143))
        for _ in range(38):
            x, y = rng.randrange(-20, WIDTH + 20), rng.randrange(485, 635)
            if 470 < x < 730:
                continue
            h = rng.randrange(26, 93)
            canvas.rectangle(x - 2, y - h, 4, h, (34, 77, 72))
            canvas.polygon([(x, y - h), (x - h // 3, y - 9), (x + h // 3, y - 9)], (26, 77, 69))
    return bytes(canvas.pixels)


def write_bmp(path: Path, rgb: bytes):
    stride = (WIDTH * 3 + 3) & ~3
    size = 54 + stride * HEIGHT
    with path.open("wb") as stream:
        stream.write(struct.pack("<2sIHHI", b"BM", size, 0, 0, 54))
        stream.write(struct.pack("<IiiHHIIiiII", 40, WIDTH, HEIGHT, 1, 24, 0, stride * HEIGHT, 2835, 2835, 0, 0))
        for y in range(HEIGHT - 1, -1, -1):
            row = rgb[y * WIDTH * 3:(y + 1) * WIDTH * 3]
            bgr = bytearray(len(row))
            bgr[0::3], bgr[1::3], bgr[2::3] = row[2::3], row[1::3], row[0::3]
            stream.write(bgr)
            stream.write(b"\0" * (stride - WIDTH * 3))


def write_jpeg(ffmpeg: str, path: Path, rgb: bytes):
    result = subprocess.run(
        [ffmpeg, "-hide_banner", "-loglevel", "error", "-f", "rawvideo", "-pixel_format", "rgb24",
         "-video_size", f"{WIDTH}x{HEIGHT}", "-i", "pipe:0", "-frames:v", "1", "-q:v", "2",
         "-f", "image2pipe", "-vcodec", "mjpeg", "pipe:1"],
        input=rgb, capture_output=True, timeout=60, check=True,
    )
    path.write_bytes(result.stdout)


def write_video(ffmpeg: str, source: Path, destination: Path):
    subprocess.run(
        [ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-loop", "1", "-i", str(source),
         "-vf", f"zoompan=z='min(zoom+0.0005,1.05)':d=96:s={WIDTH}x{HEIGHT}:fps=24,scale=in_range=full:out_range=tv,format=yuv420p",
         "-t", "4", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-color_range", "tv",
         "-movflags", "+faststart", str(destination)],
        capture_output=True, timeout=60, check=True,
    )


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="生成拾光的离线程序绘制演示素材。")
    parser.add_argument("--output", type=Path, default=PROJECT_DIR / "demo-media")
    parser.add_argument("--ffmpeg", help="可选 FFmpeg 路径；默认从 PATH 查找")
    parser.add_argument("--no-video", action="store_true", help="只生成图片")
    args = parser.parse_args()
    ffmpeg = shutil.which(args.ffmpeg or "ffmpeg")
    if args.ffmpeg and not ffmpeg:
        parser.error("未找到指定的 FFmpeg 可执行文件。")
    output = args.output.expanduser().resolve()
    extension = ".jpg" if ffmpeg else ".bmp"
    scenes = [
        ("01-海边暮色", "coast", 7),
        ("02-山间晨光", "mountain", 9),
        ("旅行记/01-海湾", "coast", 11),
        ("旅行记/02-日落", "coast", 14),
        ("旅行记/山间小径/01-山麓", "mountain", 21),
        ("旅行记/山间小径/02-峰顶", "mountain", 27),
        ("城市漫游/01-夜色", "city", 32),
        ("城市漫游/02-蓝调", "city", 42),
    ]
    try:
        for stem, theme, seed in scenes:
            path = output / (stem + extension)
            path.parent.mkdir(parents=True, exist_ok=True)
            rgb = draw_scene(theme, seed)
            if ffmpeg:
                write_jpeg(ffmpeg, path, rgb)
            else:
                write_bmp(path, rgb)
            print(f"图片：{path.relative_to(output)}")
        if ffmpeg and not args.no_video:
            video = output / "旅行记" / "03-海边短片.mp4"
            write_video(ffmpeg, output / (scenes[2][0] + extension), video)
            print(f"视频：{video.relative_to(output)}")
    except (OSError, subprocess.SubprocessError) as error:
        print(f"生成失败：{error}", file=sys.stderr)
        if isinstance(error, subprocess.CalledProcessError):
            print(error.stderr.decode("utf-8", errors="replace"), file=sys.stderr)
        return 1
    if not ffmpeg:
        print("未找到 FFmpeg：已生成 BMP 图片，跳过视频。应用运行无需 FFmpeg。")
    print(f"素材目录：{output}\n在项目目录运行 app.py --demo 即可浏览默认演示素材。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
