"""Media limits from SRS section 9. Overridable via environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    return int(raw) if raw else default


@dataclass(frozen=True)
class MediaLimits:
    max_video_bytes: int = 150 * 1024 * 1024
    max_image_bytes: int = 10 * 1024 * 1024
    max_video_duration_ms: int = 90_000
    max_video_side: int = 4096
    max_image_side: int = 8192
    max_image_pixels: int = 40_000_000
    max_initial_frames: int = 24
    max_target_frames: int = 12
    frame_max_side: int = 1280  # stored frames are downscaled to this long side
    min_crop_side_px: int = 16
    probe_timeout_s: float = 15.0
    extract_timeout_s: float = 60.0

    @classmethod
    def from_env(cls) -> MediaLimits:
        d = cls()
        return cls(
            max_video_bytes=_env_int("CLIPCART_MAX_VIDEO_BYTES", d.max_video_bytes),
            max_image_bytes=_env_int("CLIPCART_MAX_IMAGE_BYTES", d.max_image_bytes),
            max_video_duration_ms=_env_int("CLIPCART_MAX_VIDEO_MS", d.max_video_duration_ms),
            max_initial_frames=_env_int("CLIPCART_MAX_INITIAL_FRAMES", d.max_initial_frames),
            frame_max_side=_env_int("CLIPCART_FRAME_MAX_SIDE", d.frame_max_side),
        )
