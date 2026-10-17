"""Bounded media probing with Pillow (images) and ffprobe (video)."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass

from PIL import Image, UnidentifiedImageError

from .errors import MediaDecodeError, MediaLimitError, MediaTimeoutError, UnsupportedMediaError
from .geometry import oriented_size, rotation_to_orientation
from .limits import MediaLimits

JPEG_MAGIC = b"\xff\xd8\xff"
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
_BMFF_BOXES = {b"ftyp", b"moov", b"mdat", b"wide", b"free", b"skip"}

# Demuxer and protocol restrictions keep ffmpeg from following playlists,
# concat lists or network references embedded in a hostile file.
FFMPEG_INPUT_GUARD = ["-protocol_whitelist", "file", "-f", "mov"]


def sniff_kind(head: bytes) -> str | None:
    if head.startswith(JPEG_MAGIC):
        return "image/jpeg"
    if head.startswith(PNG_MAGIC):
        return "image/png"
    if len(head) >= 8 and head[4:8] in _BMFF_BOXES:
        return "video"
    return None


@dataclass(frozen=True)
class ImageProbe:
    mime: str
    coded_width: int
    coded_height: int
    exif_orientation: int
    width: int  # displayed
    height: int


@dataclass(frozen=True)
class VideoProbe:
    mime: str
    coded_width: int
    coded_height: int
    rotation_cw: int
    orientation: int
    width: int  # displayed
    height: int
    duration_ms: int
    start_time_s: float
    codec: str


def probe_image(path: str, limits: MediaLimits) -> ImageProbe:
    try:
        with Image.open(path) as img:
            fmt = img.format
            w, h = img.size
            if fmt not in ("JPEG", "PNG"):
                raise UnsupportedMediaError(f"unsupported image format {fmt}")
            if w <= 0 or h <= 0:
                raise MediaDecodeError("image has no pixels")
            if max(w, h) > limits.max_image_side or w * h > limits.max_image_pixels:
                raise MediaLimitError(f"image {w}x{h} exceeds dimension limits")
            orientation = int(img.getexif().get(274, 1) or 1)
            if orientation not in range(1, 9):
                orientation = 1
            img.load()  # full decode catches truncated files
    except (UnidentifiedImageError, Image.DecompressionBombError) as exc:
        raise UnsupportedMediaError(f"not a decodable image: {exc}") from None
    except OSError as exc:
        raise MediaDecodeError(f"image decode failed: {exc}") from None
    dw, dh = oriented_size(w, h, orientation)
    return ImageProbe(
        mime="image/jpeg" if fmt == "JPEG" else "image/png",
        coded_width=w,
        coded_height=h,
        exif_orientation=orientation,
        width=dw,
        height=dh,
    )


def _rotation_from_stream(stream: dict) -> int:
    """Return clockwise display rotation in degrees."""
    for sd in stream.get("side_data_list", []) or []:
        if "rotation" in sd:
            # ffprobe reports the display-matrix rotation counter-clockwise.
            return int(round(-float(sd["rotation"]))) % 360
    rotate_tag = (stream.get("tags") or {}).get("rotate")
    if rotate_tag is not None:
        return int(rotate_tag) % 360  # legacy tag is clockwise
    return 0


def probe_video(path: str, limits: MediaLimits) -> VideoProbe:
    cmd = [
        "ffprobe",
        "-v",
        "error",
        *FFMPEG_INPUT_GUARD,
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        path,
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, timeout=limits.probe_timeout_s, check=False)
    except subprocess.TimeoutExpired:
        raise MediaTimeoutError("video probe timed out") from None
    if proc.returncode != 0:
        raise UnsupportedMediaError("file is not a decodable MP4/MOV video")
    try:
        info = json.loads(proc.stdout or b"{}")
    except json.JSONDecodeError:
        raise MediaDecodeError("ffprobe returned invalid output") from None
    streams = [s for s in info.get("streams", []) if s.get("codec_type") == "video"]
    # Ignore attached cover art; it is not the video track.
    streams = [s for s in streams if not (s.get("disposition") or {}).get("attached_pic")]
    if not streams:
        raise UnsupportedMediaError("file has no video stream")
    v = streams[0]
    w, h = int(v.get("width") or 0), int(v.get("height") or 0)
    if w <= 0 or h <= 0:
        raise MediaDecodeError("video stream has no dimensions")
    if max(w, h) > limits.max_video_side:
        raise MediaLimitError(f"video {w}x{h} exceeds dimension limits")
    fmt = info.get("format", {})
    dur_s = None
    for candidate in (v.get("duration"), fmt.get("duration")):
        try:
            if candidate is not None:
                dur_s = float(candidate)
                break
        except ValueError:
            continue
    if dur_s is None or dur_s <= 0:
        raise MediaDecodeError("video duration unknown")
    duration_ms = int(round(dur_s * 1000))
    if duration_ms > limits.max_video_duration_ms:
        raise MediaLimitError(f"video is {duration_ms / 1000:.1f}s; limit is {limits.max_video_duration_ms / 1000:.0f}s")
    rotation = _rotation_from_stream(v)
    try:
        orientation = rotation_to_orientation(rotation)
    except ValueError:
        raise UnsupportedMediaError(f"unsupported display rotation {rotation}") from None
    dw, dh = oriented_size(w, h, orientation)
    try:
        start = float(v.get("start_time") or fmt.get("start_time") or 0.0)
    except ValueError:
        start = 0.0
    brand = ((fmt.get("tags") or {}).get("major_brand") or "").strip()
    mime = "video/quicktime" if brand == "qt" else "video/mp4"
    return VideoProbe(
        mime=mime,
        coded_width=w,
        coded_height=h,
        rotation_cw=rotation,
        orientation=orientation,
        width=dw,
        height=dh,
        duration_ms=duration_ms,
        start_time_s=start,
        codec=str(v.get("codec_name")),
    )
