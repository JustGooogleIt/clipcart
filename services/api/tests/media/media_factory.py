"""Synthetic test media. Everything is generated at test time; no binaries are committed."""

from __future__ import annotations

import io
import shutil
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image

HAVE_FFMPEG = shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None

RED = (255, 0, 0)
BLUE = (0, 0, 255)
WHITE = (255, 255, 255)

# Transform that turns the *display* image into the *coded* image for each
# EXIF orientation, i.e. the inverse of what exif_transpose applies.
_DISPLAY_TO_CODED_OP = {
    1: None,
    2: Image.Transpose.FLIP_LEFT_RIGHT,
    3: Image.Transpose.ROTATE_180,
    4: Image.Transpose.FLIP_TOP_BOTTOM,
    5: Image.Transpose.TRANSPOSE,
    6: Image.Transpose.ROTATE_90,  # exif_transpose applies ROTATE_270
    7: Image.Transpose.TRANSVERSE,
    8: Image.Transpose.ROTATE_270,  # exif_transpose applies ROTATE_90
}


def marker_image(size, rect, color=RED, bg=WHITE) -> Image.Image:
    img = Image.new("RGB", size, bg)
    img.paste(Image.new("RGB", (rect[2] - rect[0], rect[3] - rect[1]), color), rect[:2])
    return img


def encode_with_orientation(display: Image.Image, orientation: int, fmt: str = "JPEG") -> bytes:
    op = _DISPLAY_TO_CODED_OP[orientation]
    coded = display.transpose(op) if op is not None else display.copy()
    exif = Image.Exif()
    exif[274] = orientation
    buf = io.BytesIO()
    if fmt == "JPEG":
        coded.save(buf, format="JPEG", quality=95, exif=exif.tobytes())
    else:
        coded.save(buf, format="PNG", exif=exif.tobytes())
    return buf.getvalue()


def find_color_box(img: Image.Image, color=RED, tol=60):
    a = np.asarray(img.convert("RGB")).astype(int)
    mask = (np.abs(a - np.array(color)).sum(axis=2) < tol)
    ys, xs = np.nonzero(mask)
    if len(xs) == 0:
        return None
    return xs.min(), ys.min(), xs.max() + 1, ys.max() + 1


def mean_color(img: Image.Image):
    return tuple(np.asarray(img.convert("RGB")).reshape(-1, 3).mean(axis=0))


def _run(cmd):
    subprocess.run(cmd, check=True, capture_output=True)


def color_segments_video(path: Path, segments, size=(320, 240), fps=30) -> Path:
    """Constant-frame-rate clip made of solid colour segments [(color, seconds), ...]."""
    inputs = []
    for color, secs in segments:
        inputs += ["-f", "lavfi", "-i", f"color=c={color}:s={size[0]}x{size[1]}:r={fps}:d={secs}"]
    n = len(segments)
    filt = "".join(f"[{i}:v]" for i in range(n)) + f"concat=n={n}:v=1[v]"
    _run(["ffmpeg", "-y", "-v", "error", *inputs, "-filter_complex", filt, "-map", "[v]",
          "-c:v", "libx264", "-pix_fmt", "yuv420p", str(path)])
    return path


def vfr_video(path: Path) -> Path:
    """30 red frames over 0-1s (30 fps) then 30 blue frames over 1-4s (10 fps)."""
    _run([
        "ffmpeg", "-y", "-v", "error",
        "-f", "lavfi", "-i", "color=c=red:s=320x240:r=30:d=1",
        "-f", "lavfi", "-i", "color=c=blue:s=320x240:r=30:d=1",
        "-filter_complex", "[0:v][1:v]concat=n=2:v=1,setpts='if(lt(N,30),N/30,1+(N-30)/10)/TB'[v]",
        "-map", "[v]", "-fps_mode", "passthrough", "-video_track_timescale", "90000",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", str(path),
    ])
    return path


def rotated_marker_video(path: Path, ccw_degrees: int, seconds: float = 1.0) -> Path:
    """Blue 320x240 coded frames with a red block in the coded top-left corner,
    tagged with a display rotation (counter-clockwise degrees, ffmpeg convention)."""
    raw = path.with_suffix(".raw.mp4")
    _run([
        "ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", f"color=c=blue:s=320x240:r=30:d={seconds}",
        "-vf", "drawbox=x=0:y=0:w=80:h=60:color=red:t=fill",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", str(raw),
    ])
    _run(["ffmpeg", "-y", "-v", "error", "-display_rotation", str(ccw_degrees), "-i", str(raw),
          "-c", "copy", str(path)])
    raw.unlink()
    return path


def moving_box_video(path: Path, seconds: float = 3.0) -> Path:
    """Grey 320x240 background with a black 80x120 'jacket' block at x=40+10t, y=60
    and a static grey-blue 'bag' block. Matches perception/fixtures/perceptron_dev_fixture.json."""
    _run([
        "ffmpeg", "-y", "-v", "error",
        "-f", "lavfi", "-i", f"color=c=gray:s=320x240:r=30:d={seconds}",
        "-f", "lavfi", "-i", f"color=c=black:s=80x120:r=30:d={seconds}",
        "-f", "lavfi", "-i", f"color=c=0x6070a0:s=48x72:r=30:d={seconds}",
        "-filter_complex",
        "[0:v][1:v]overlay=x='40+10*t':y=60:eval=frame[a];[a][2:v]overlay=x=224:y=72[v]",
        "-map", "[v]", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(path),
    ])
    return path
