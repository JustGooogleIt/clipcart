"""Scan a cached video locally, then return the best stills for Perceptron.

We do NOT send every video frame to Perceptron (cost/latency). Instead:
1. Walk the whole clip with dense local sampling (+ scene cuts).
2. Score sharpness.
3. Pick a temporally diverse top-K set for the model.
"""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image

_SHOWINFO_RE = re.compile(r"pts_time:([0-9.]+)")


@dataclass(frozen=True)
class FrameSample:
    index: int
    time_sec: float
    path: Path
    width: int
    height: int
    sharpness: float
    reason: str  # uniform | scene | selected
    score: float = 0.0


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


def sharpness_score(path: Path) -> float:
    img = Image.open(path).convert("L")
    img.thumbnail((512, 512))
    a = np.asarray(img, dtype=np.float32)
    if a.shape[0] < 3 or a.shape[1] < 3:
        return 0.0
    lap = (
        -4 * a[1:-1, 1:-1]
        + a[:-2, 1:-1]
        + a[2:, 1:-1]
        + a[1:-1, :-2]
        + a[1:-1, 2:]
    )
    return float(lap.var())


def fashion_usefulness_score(path: Path) -> float:
    """Heuristic: sharp + mid exposure + some center detail (person/lookbook stills)."""
    with Image.open(path) as im:
        rgb = im.convert("RGB")
        rgb.thumbnail((384, 384))
        grey = rgb.convert("L")
        a = np.asarray(grey, dtype=np.float32)
        arr = np.asarray(rgb, dtype=np.float32)
    if a.shape[0] < 8 or a.shape[1] < 8:
        return 0.0
    lap = (
        -4 * a[1:-1, 1:-1]
        + a[:-2, 1:-1]
        + a[2:, 1:-1]
        + a[1:-1, :-2]
        + a[1:-1, 2:]
    )
    sharp = float(lap.var())
    mean = float(a.mean())
    # Penalize near-black / near-white title cards
    exposure = 1.0 - min(1.0, abs(mean - 118.0) / 118.0)
    h, w = a.shape
    cy0, cy1 = h // 4, (3 * h) // 4
    cx0, cx1 = w // 4, (3 * w) // 4
    center = a[cy0:cy1, cx0:cx1]
    center_energy = float(center.std())
    # Mild colorfulness: lookbooks have clothing color; logos/text cards less so
    colorfulness = float(arr.std(axis=2).mean())
    return sharp * (0.55 + 0.45 * exposure) * (0.7 + 0.3 * min(1.0, center_energy / 40.0)) * (
        0.75 + 0.25 * min(1.0, colorfulness / 25.0)
    )


def _scene_cut_times(video_path: Path, threshold: float = 0.28) -> list[float]:
    """Return pts times where ffmpeg scene detector fires."""
    cmd = [
        "ffmpeg",
        "-v",
        "info",
        "-i",
        str(video_path),
        "-vf",
        f"select='gt(scene,{threshold})',showinfo",
        "-f",
        "null",
        "-",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    # showinfo lands on stderr
    times: list[float] = []
    for line in (proc.stderr or "").splitlines():
        m = _SHOWINFO_RE.search(line)
        if m:
            try:
                times.append(float(m.group(1)))
            except ValueError:
                pass
    # unique + sorted
    out: list[float] = []
    for t in sorted(times):
        if not out or abs(t - out[-1]) > 0.35:
            out.append(round(t, 3))
    return out


def _uniform_times(duration_s: float, interval_s: float) -> list[float]:
    if duration_s <= 0.2:
        return [0.0]
    start = min(0.35, duration_s * 0.03)
    end = max(start + 0.05, duration_s - 0.35)
    times: list[float] = []
    t = start
    while t <= end + 1e-6:
        times.append(round(t, 3))
        t += interval_s
    if not times:
        times = [round(duration_s / 2, 3)]
    return times


def _extract_one(video_path: Path, t: float, out: Path) -> tuple[int, int]:
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
    with Image.open(out) as im:
        return im.size


def _pick_diverse(candidates: list[FrameSample], k: int, duration_s: float) -> list[FrameSample]:
    if not candidates:
        return []
    k = max(1, min(k, len(candidates)))
    min_gap = max(0.6, duration_s / (k * 3.0))
    ranked = sorted(candidates, key=lambda c: c.score if c.score else c.sharpness, reverse=True)
    picked: list[FrameSample] = []
    for c in ranked:
        if all(abs(c.time_sec - p.time_sec) >= min_gap for p in picked):
            picked.append(c)
        if len(picked) >= k:
            break
    # If diversity filter was too strict, fill remaining by score.
    if len(picked) < k:
        for c in ranked:
            if c in picked:
                continue
            picked.append(c)
            if len(picked) >= k:
                break
    picked.sort(key=lambda c: c.time_sec)
    # reindex
    return [
        FrameSample(
            index=i,
            time_sec=p.time_sec,
            path=p.path,
            width=p.width,
            height=p.height,
            sharpness=p.sharpness,
            reason="selected",
            score=p.score,
        )
        for i, p in enumerate(picked)
    ]


def scan_video_for_detect(
    video_path: Path,
    out_dir: Path,
    *,
    max_detect_frames: int = 10,
    max_candidate_frames: int = 64,
    sample_interval_s: float = 1.25,
) -> tuple[list[FrameSample], dict]:
    """Scan the whole clip locally; return diverse sharp frames for the model."""
    out_dir.mkdir(parents=True, exist_ok=True)
    duration_s = probe_duration_s(video_path)

    # Adapt interval so we stay under max_candidate_frames across full duration.
    interval = sample_interval_s
    est = max(1, int(duration_s / interval))
    if est > max_candidate_frames:
        interval = max(0.5, duration_s / max_candidate_frames)

    uniform = _uniform_times(duration_s, interval)
    try:
        scenes = _scene_cut_times(video_path, threshold=0.22)
    except Exception:  # noqa: BLE001
        scenes = []

    # Merge candidate times
    times: list[tuple[float, str]] = [(t, "uniform") for t in uniform]
    for t in scenes:
        if 0.2 <= t <= duration_s - 0.2:
            times.append((t, "scene"))
    # unique by ~0.2s bucket
    times.sort(key=lambda x: x[0])
    merged: list[tuple[float, str]] = []
    for t, reason in times:
        if not merged or abs(t - merged[-1][0]) > 0.2:
            merged.append((t, reason))
        elif reason == "scene":
            # prefer marking as scene if near-duplicate
            merged[-1] = (merged[-1][0], "scene")
    merged = merged[:max_candidate_frames]

    candidates: list[FrameSample] = []
    for i, (t, reason) in enumerate(merged):
        out = out_dir / f"cand_{i:03d}_{t:.2f}s.jpg"
        try:
            w, h = _extract_one(video_path, t, out)
        except RuntimeError:
            continue
        sharp = sharpness_score(out)
        score = fashion_usefulness_score(out)
        candidates.append(
            FrameSample(
                index=i,
                time_sec=t,
                path=out,
                width=w,
                height=h,
                sharpness=round(sharp, 2),
                reason=reason,
                score=round(score, 2),
            )
        )

    selected = _pick_diverse(candidates, max_detect_frames, duration_s)
    # Copy/symlink selected into selected_*.jpg for stable artifact URLs
    final: list[FrameSample] = []
    for i, s in enumerate(selected):
        dest = out_dir / f"selected_{i:02d}_{s.time_sec:.2f}s.jpg"
        if s.path.resolve() != dest.resolve():
            dest.write_bytes(s.path.read_bytes())
        final.append(
            FrameSample(
                index=i,
                time_sec=s.time_sec,
                path=dest,
                width=s.width,
                height=s.height,
                sharpness=s.sharpness,
                reason=s.reason,
                score=s.score,
            )
        )

    stats = {
        "durationS": round(duration_s, 3),
        "candidateCount": len(candidates),
        "sceneCutCount": len(scenes),
        "sampleIntervalS": round(interval, 3),
        "selectedCount": len(final),
        "maxDetectFrames": max_detect_frames,
        "note": (
            "Full clip was scanned locally; only the best temporally-diverse "
            "fashion-likely frames are sent to Perceptron."
        ),
    }
    return final, stats
