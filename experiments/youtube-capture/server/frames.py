"""Extract a small number of JPEG frames from a cached video via ffmpeg."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class FrameSample:
    index: int
    time_sec: float
    path: Path
    width: int
    height: int


def probe_duration_s(video_path: Path) -> float:
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "json",
        str(video_path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr[-300:] or "ffprobe failed")
    data = json.loads(proc.stdout or "{}")
    dur = float((data.get("format") or {}).get("duration") or 0)
    if dur <= 0:
        raise RuntimeError("could not determine video duration")
    return dur


def sample_times(duration_s: float, count: int) -> list[float]:
    count = max(1, min(int(count), 6))
    if duration_s <= 0.5:
        return [0.0]
    # Stay off the very start/end (black/logo frames).
    start = min(0.4, duration_s * 0.08)
    end = max(start + 0.1, duration_s * 0.92)
    if count == 1:
        return [round((start + end) / 2, 3)]
    span = end - start
    return [round(start + span * i / (count - 1), 3) for i in range(count)]


def extract_frames(
    video_path: Path,
    out_dir: Path,
    *,
    count: int = 3,
    prefix: str = "frame",
) -> list[FrameSample]:
    out_dir.mkdir(parents=True, exist_ok=True)
    duration_s = probe_duration_s(video_path)
    times = sample_times(duration_s, count)
    samples: list[FrameSample] = []
    for i, t in enumerate(times):
        out = out_dir / f"{prefix}_{i:02d}_{t:.2f}s.jpg"
        cmd = [
            "ffmpeg",
            "-y",
            "-v",
            "error",
            "-ss",
            str(t),
            "-i",
            str(video_path),
            "-frames:v",
            "1",
            "-q:v",
            "3",
            str(out),
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if proc.returncode != 0 or not out.is_file():
            raise RuntimeError(proc.stderr[-300:] or f"ffmpeg failed at t={t}")
        # Probe size via ffprobe on the jpeg
        p = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=width,height",
                "-of",
                "json",
                str(out),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        width = height = 0
        if p.returncode == 0:
            streams = (json.loads(p.stdout or "{}").get("streams") or [{}])[0]
            width = int(streams.get("width") or 0)
            height = int(streams.get("height") or 0)
        samples.append(
            FrameSample(index=i, time_sec=t, path=out, width=width, height=height)
        )
    return samples
