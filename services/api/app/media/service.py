"""MediaService: bounded ingest, timed frame extraction, crops, shot cuts.

Implements the SRS frozen-interface shapes:

    MediaService.ingest(upload, owner_id) -> MediaAsset
    MediaService.extract_frames(media_id, interval_ms, max_frames) -> FrameRef[]
    MediaService.crop(frame_asset_id, box01) -> CropRef

``owner_id`` is required on every read so a caller cannot reach another
owner's bytes by guessing an ID.
"""

from __future__ import annotations

import hashlib
import io
import math
import os
import re
import subprocess
import tempfile
from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import BinaryIO

import numpy as np
from PIL import Image, ImageOps

from .errors import (
    MediaDecodeError,
    MediaError,
    MediaTimeoutError,
    MediaTooLargeError,
    UnsupportedMediaError,
)
from .geometry import box01_to_pixels, fit_within, validate_box01
from .limits import MediaLimits
from .probe import FFMPEG_INPUT_GUARD, probe_image, probe_video, sniff_kind
from .storage import LocalAssetStore
from .types import CropRef, FrameRef, FrameTransform, MediaAsset, SourceType

_CHUNK = 1024 * 1024
_SHOWINFO_RE = re.compile(r"\bn:\s*(\d+)\s+pts:\s*(-?\d+)\s+pts_time:\s*(-?[0-9.]+(?:e-?\d+)?)")
JPEG_QUALITY = 90


def sharpness_score(img: Image.Image) -> float:
    """Variance of a 4-neighbour Laplacian on a grey copy capped at 512px (blur heuristic)."""
    grey = img.convert("L")
    grey.thumbnail((512, 512))  # native resolution for typical crops
    a = np.asarray(grey, dtype=np.float32)
    if a.shape[0] < 3 or a.shape[1] < 3:
        return 0.0
    lap = -4 * a[1:-1, 1:-1] + a[:-2, 1:-1] + a[2:, 1:-1] + a[1:-1, :-2] + a[1:-1, 2:]
    return float(round(lap.var(), 3))


def _fashion_usefulness_score(img: Image.Image) -> float:
    """Sharp + mid exposure + center detail + mild colorfulness (lookbook stills)."""
    rgb = img.convert("RGB")
    rgb.thumbnail((384, 384))
    grey = rgb.convert("L")
    a = np.asarray(grey, dtype=np.float32)
    arr = np.asarray(rgb, dtype=np.float32)
    if a.shape[0] < 8 or a.shape[1] < 8:
        return 0.0
    lap = -4 * a[1:-1, 1:-1] + a[:-2, 1:-1] + a[2:, 1:-1] + a[1:-1, :-2] + a[1:-1, 2:]
    sharp = float(lap.var())
    mean = float(a.mean())
    exposure = 1.0 - min(1.0, abs(mean - 118.0) / 118.0)
    h, w = a.shape
    center = a[h // 4 : (3 * h) // 4, w // 4 : (3 * w) // 4]
    center_energy = float(center.std())
    colorfulness = float(arr.std(axis=2).mean())
    return sharp * (0.55 + 0.45 * exposure) * (0.7 + 0.3 * min(1.0, center_energy / 40.0)) * (
        0.75 + 0.25 * min(1.0, colorfulness / 25.0)
    )


def _uniform_sample_times(duration_s: float, interval_s: float) -> list[float]:
    if duration_s <= 0.2:
        return [0.0]
    start = min(0.35, duration_s * 0.03)
    end = max(start + 0.05, duration_s - 0.35)
    times: list[float] = []
    t = start
    while t <= end + 1e-6:
        times.append(round(t, 3))
        t += interval_s
    return times or [round(duration_s / 2, 3)]


def _encode_jpeg(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="JPEG", quality=JPEG_QUALITY)
    return buf.getvalue()


class MediaService:
    def __init__(self, store: LocalAssetStore, limits: MediaLimits | None = None):
        self.store = store
        self.limits = limits or MediaLimits()

    # ------------------------------------------------------------------ ingest
    def ingest(
        self,
        upload: BinaryIO,
        owner_id: str,
        *,
        source_url: str | None = None,
        source_type: SourceType | None = None,
    ) -> MediaAsset:
        """Stream ``upload`` to disk with a hard byte cap, then validate by decoding.

        The cap is chosen from the sniffed magic bytes so an oversized image is
        rejected at 10 MB instead of 150 MB. The declared filename or content
        type is never trusted.
        """
        fd, tmp = self.store.temp_file()
        try:
            sha = hashlib.sha256()
            total = 0
            kind: str | None = None
            cap = self.limits.max_video_bytes
            with os.fdopen(fd, "wb") as out:
                while True:
                    chunk = upload.read(_CHUNK)
                    if not chunk:
                        break
                    if kind is None:
                        kind = sniff_kind(chunk[:16])
                        if kind is None:
                            raise UnsupportedMediaError("only JPEG, PNG, MP4 and MOV uploads are accepted")
                        cap = self.limits.max_image_bytes if kind.startswith("image/") else self.limits.max_video_bytes
                    total += len(chunk)
                    if total > cap:
                        raise MediaTooLargeError(f"upload exceeds {cap // (1024 * 1024)} MB limit")
                    sha.update(chunk)
                    out.write(chunk)
            if kind is None:
                raise UnsupportedMediaError("empty upload")
            media_id = self.store.new_id("media")
            now = datetime.now(timezone.utc)
            if kind.startswith("image/"):
                p = probe_image(tmp, self.limits)
                asset = MediaAsset(
                    id=media_id,
                    owner_id=owner_id,
                    sha256=sha.hexdigest(),
                    mime=p.mime,
                    kind="image",
                    width=p.width,
                    height=p.height,
                    duration_ms=None,
                    source_type=source_type or "upload_image",
                    canonical_source_url=source_url,
                    storage_key=f"{media_id}.bin",
                    byte_size=total,
                    rotation_degrees=0,
                    exif_orientation=p.exif_orientation,
                    created_at=now,
                )
                extra = {"coded_width": p.coded_width, "coded_height": p.coded_height}
            else:
                p = probe_video(tmp, self.limits)
                asset = MediaAsset(
                    id=media_id,
                    owner_id=owner_id,
                    sha256=sha.hexdigest(),
                    mime=p.mime,
                    kind="video",
                    width=p.width,
                    height=p.height,
                    duration_ms=p.duration_ms,
                    source_type=source_type or "upload_video",
                    canonical_source_url=source_url,
                    storage_key=f"{media_id}.bin",
                    byte_size=total,
                    rotation_degrees=p.rotation_cw,
                    exif_orientation=p.orientation,
                    created_at=now,
                )
                extra = {
                    "coded_width": p.coded_width,
                    "coded_height": p.coded_height,
                    "start_time_s": p.start_time_s,
                    "codec": p.codec,
                }
            self.store.put_file(
                media_id,
                tmp,
                {"owner_id": owner_id, "kind": "media", "asset": asset.model_dump(mode="json"), **extra},
            )
            return asset
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)

    def get_media(self, media_id: str, owner_id: str) -> MediaAsset:
        meta = self.store.meta(media_id, owner_id)
        if meta.get("kind") != "media":
            raise MediaError("asset is not a media upload")
        return MediaAsset.model_validate(meta["asset"])

    def get_frame(self, frame_asset_id: str, owner_id: str) -> FrameRef:
        meta = self.store.meta(frame_asset_id, owner_id)
        if meta.get("kind") != "frame":
            raise MediaError("asset is not a frame")
        return FrameRef.model_validate(meta["frame"])

    # ------------------------------------------------------------------ frames
    def extract_frames(
        self,
        media_id: str,
        owner_id: str,
        *,
        interval_ms: int | None = None,
        max_frames: int | None = None,
        start_ms: int | None = None,
        end_ms: int | None = None,
    ) -> list[FrameRef]:
        """Sample frames with decoder timestamps.

        Default: up to ``max_frames`` evenly spaced over the clip (interval =
        duration / max_frames). ``start_ms``/``end_ms`` restrict sampling to a
        window, used for the "frames around a chosen target" pass, which is
        capped at ``limits.max_target_frames``.
        """
        asset = self.get_media(media_id, owner_id)
        meta = self.store.meta(media_id, owner_id)
        src = self.store.path(media_id, owner_id)
        targeted = start_ms is not None or end_ms is not None
        cap = self.limits.max_target_frames if targeted else self.limits.max_initial_frames
        n = min(max_frames or (12 if not targeted else cap), cap)
        if n <= 0:
            raise MediaError("max_frames must be positive")
        if asset.kind == "image":
            return [self._image_frame(asset, meta, src, owner_id)]
        return self._video_frames(asset, meta, src, owner_id, n, interval_ms, start_ms, end_ms)

    def extract_ranked_frames(
        self,
        media_id: str,
        owner_id: str,
        *,
        max_frames: int | None = None,
        max_candidates: int = 48,
        sample_interval_s: float = 1.25,
    ) -> list[FrameRef]:
        """Scan the clip locally; keep sharp, fashion-likely, time-diverse stills.

        Used for YouTube downloads so Perceptron sees the best frames without
        paying for every decoded FPS sample.
        """
        asset = self.get_media(media_id, owner_id)
        meta = self.store.meta(media_id, owner_id)
        src = self.store.path(media_id, owner_id)
        if asset.kind == "image":
            return [self._image_frame(asset, meta, src, owner_id)]

        n = min(max_frames or 12, self.limits.max_initial_frames)
        if n <= 0:
            raise MediaError("max_frames must be positive")
        duration_ms = asset.duration_ms or 0
        if duration_ms <= 0:
            raise MediaError("video has no duration")
        duration_s = duration_ms / 1000.0

        interval = sample_interval_s
        est = max(1, int(duration_s / interval))
        if est > max_candidates:
            interval = max(0.5, duration_s / max_candidates)

        times_s = _uniform_sample_times(duration_s, interval)
        try:
            scene_ms = self.detect_shot_boundaries(media_id, owner_id, threshold=0.22)
        except Exception:  # noqa: BLE001
            scene_ms = []
        for ms in scene_ms:
            t = ms / 1000.0
            if 0.2 <= t <= duration_s - 0.2:
                times_s.append(t)

        times_s = sorted(set(round(t, 3) for t in times_s))
        merged: list[float] = []
        for t in times_s:
            if not merged or abs(t - merged[-1]) > 0.2:
                merged.append(t)
        merged = merged[:max_candidates]

        # Extract candidate stills at each time, score, then pick diverse top-K.
        tw, th, scale = fit_within(asset.width, asset.height, self.limits.frame_max_side)
        transform = FrameTransform(
            source_width=meta["coded_width"],
            source_height=meta["coded_height"],
            exif_orientation=asset.exif_orientation,
            rotation_degrees=asset.rotation_degrees,
            oriented_width=asset.width,
            oriented_height=asset.height,
            output_width=tw,
            output_height=th,
            scale=scale,
        )
        start_s = float(meta.get("start_time_s") or 0.0)
        scored: list[tuple[float, float, Image.Image]] = []  # score, t, img
        with tempfile.TemporaryDirectory(dir=self.store.root) as outdir:
            for i, t in enumerate(merged):
                out = Path(outdir) / f"c_{i:03d}.jpg"
                try:
                    img = self._extract_still_at(src, start_s + t, out, tw, th)
                except MediaError:
                    continue
                score = _fashion_usefulness_score(img)
                scored.append((score, t, img))

        if not scored:
            raise MediaDecodeError("no frames decoded for ranked sampling")

        min_gap = max(0.6, duration_s / (n * 3.0))
        ranked = sorted(scored, key=lambda x: x[0], reverse=True)
        picked: list[tuple[float, float, Image.Image]] = []
        for item in ranked:
            if all(abs(item[1] - p[1]) >= min_gap for p in picked):
                picked.append(item)
            if len(picked) >= n:
                break
        if len(picked) < n:
            for item in ranked:
                if item in picked:
                    continue
                picked.append(item)
                if len(picked) >= n:
                    break
        picked.sort(key=lambda x: x[1])

        frames: list[FrameRef] = []
        for i, (_score, t, img) in enumerate(picked):
            ts_ms = max(0, int(round(t * 1000)))
            frames.append(self._store_frame(asset, owner_id, img, i, ts_ms, start_s + t, transform))
        return frames

    def _extract_still_at(self, src: Path, abs_t: float, out: Path, tw: int, th: int) -> Image.Image:
        cmd = [
            "ffmpeg",
            "-nostdin",
            "-hide_banner",
            "-loglevel",
            "error",
            "-threads",
            "2",
            *FFMPEG_INPUT_GUARD,
            "-ss",
            f"{abs_t:.3f}",
            "-i",
            str(src),
            "-frames:v",
            "1",
            "-vf",
            f"scale={tw}:{th}:flags=area",
            "-q:v",
            "2",
            str(out),
        ]
        try:
            proc = subprocess.run(cmd, capture_output=True, timeout=self.limits.extract_timeout_s, check=False)
        except subprocess.TimeoutExpired:
            raise MediaTimeoutError("frame extraction timed out") from None
        if proc.returncode != 0 or not out.is_file():
            raise MediaDecodeError("could not extract still")
        with Image.open(out) as im:
            img = im.convert("RGB")
        if img.size != (tw, th):
            img = img.resize((tw, th), Image.Resampling.LANCZOS)
        return img

    def _image_frame(self, asset: MediaAsset, meta: dict, src: Path, owner_id: str) -> FrameRef:
        with Image.open(src) as raw:
            img = ImageOps.exif_transpose(raw)  # applies EXIF orientation exactly once
            img = img.convert("RGB")
        ow, oh = img.size
        tw, th, _ = fit_within(ow, oh, self.limits.frame_max_side)
        if (tw, th) != (ow, oh):
            img = img.resize((tw, th), Image.Resampling.LANCZOS)
        transform = FrameTransform(
            source_width=meta["coded_width"],
            source_height=meta["coded_height"],
            exif_orientation=asset.exif_orientation,
            rotation_degrees=0,
            oriented_width=ow,
            oriented_height=oh,
            output_width=tw,
            output_height=th,
            scale=tw / ow,
        )
        return self._store_frame(asset, owner_id, img, 0, None, None, transform)

    def _video_frames(
        self,
        asset: MediaAsset,
        meta: dict,
        src: Path,
        owner_id: str,
        n: int,
        interval_ms: int | None,
        start_ms: int | None,
        end_ms: int | None,
    ) -> list[FrameRef]:
        start_s = float(meta.get("start_time_s") or 0.0)
        duration_ms = asset.duration_ms or 0
        win_start = max(0, start_ms or 0)
        win_end = min(duration_ms, end_ms if end_ms is not None else duration_ms)
        if win_end <= win_start:
            raise MediaError("empty sampling window")
        span_ms = win_end - win_start
        step_ms = interval_ms if interval_ms and interval_ms > 0 else max(1, math.floor(span_ms / n))
        # Times in the select expression are absolute stream times.
        a = start_s + win_start / 1000
        b = start_s + win_end / 1000
        step = step_ms / 1000
        # Pick the first decoded frame at or after each grid time a + k*step
        # (k = frames selected so far). Anchoring to the grid avoids drift;
        # the half-step spacing guard stops bursts after a long frame gap.
        select = (
            f"select='gte(t,{a:.6f})*lte(t,{b:.6f})"
            f"*gte(t,{a:.6f}+selected_n*{step:.6f}-0.0001)"
            f"*(isnan(prev_selected_t)+gte(t-prev_selected_t,{step / 2:.6f}))'"
        )
        tw, th, scale = fit_within(asset.width, asset.height, self.limits.frame_max_side)
        # ffmpeg applies display rotation automatically before the user filter chain.
        vf = f"{select},scale={tw}:{th}:flags=area,showinfo"
        with tempfile.TemporaryDirectory(dir=self.store.root) as outdir:
            cmd = [
                "ffmpeg",
                "-nostdin",
                "-hide_banner",
                "-loglevel",
                "info",
                "-threads",
                "2",
                *FFMPEG_INPUT_GUARD,
                "-i",
                str(src),
                "-map",
                "0:v:0",
                "-an",
                "-sn",
                "-dn",
                "-vf",
                vf,
                "-fps_mode",
                "passthrough",
                "-frames:v",
                str(n),
                "-q:v",
                "2",
                os.path.join(outdir, "f_%04d.png"),
            ]
            try:
                proc = subprocess.run(cmd, capture_output=True, timeout=self.limits.extract_timeout_s, check=False)
            except subprocess.TimeoutExpired:
                raise MediaTimeoutError("frame extraction timed out") from None
            stderr = proc.stderr.decode("utf-8", "replace")
            if proc.returncode != 0:
                raise MediaDecodeError("frame extraction failed")
            stamps = [float(m.group(3)) for m in _SHOWINFO_RE.finditer(stderr)]
            files = sorted(Path(outdir).glob("f_*.png"))
            if not files:
                raise MediaDecodeError("no frames decoded in the requested window")
            if len(stamps) != len(files):
                raise MediaDecodeError(f"timestamp/frame mismatch: {len(stamps)} timestamps for {len(files)} frames")
            transform = FrameTransform(
                source_width=meta["coded_width"],
                source_height=meta["coded_height"],
                exif_orientation=asset.exif_orientation,
                rotation_degrees=asset.rotation_degrees,
                oriented_width=asset.width,
                oriented_height=asset.height,
                output_width=tw,
                output_height=th,
                scale=scale,
            )
            frames = []
            for i, (path, pts) in enumerate(zip(files, stamps)):
                with Image.open(path) as im:
                    img = im.convert("RGB")
                if img.size != (tw, th):
                    raise MediaDecodeError(f"decoded frame {img.size} does not match expected {(tw, th)}")
                ts_ms = max(0, int(round((pts - start_s) * 1000)))
                frames.append(self._store_frame(asset, owner_id, img, i, ts_ms, pts, transform))
            return frames

    def _store_frame(
        self,
        asset: MediaAsset,
        owner_id: str,
        img: Image.Image,
        index: int,
        ts_ms: int | None,
        pts: float | None,
        transform: FrameTransform,
    ) -> FrameRef:
        fid = self.store.new_id("frame")
        frame = FrameRef(
            asset_id=fid,
            media_id=asset.id,
            index=index,
            timestamp_ms=ts_ms,
            pts_seconds=pts,
            width=img.width,
            height=img.height,
            transform=transform,
            sharpness=sharpness_score(img),
        )
        self.store.put_bytes(
            fid,
            _encode_jpeg(img),
            {"owner_id": owner_id, "kind": "frame", "mime": "image/jpeg", "frame": frame.model_dump(mode="json")},
        )
        return frame

    # ------------------------------------------------------------------ shots
    def detect_shot_boundaries(self, media_id: str, owner_id: str, *, threshold: float = 0.35) -> list[int]:
        """Timestamps (ms) where a scene cut starts. Empty for still images."""
        asset = self.get_media(media_id, owner_id)
        if asset.kind == "image":
            return []
        meta = self.store.meta(media_id, owner_id)
        src = self.store.path(media_id, owner_id)
        start_s = float(meta.get("start_time_s") or 0.0)
        cmd = [
            "ffmpeg",
            "-nostdin",
            "-hide_banner",
            "-loglevel",
            "info",
            "-threads",
            "2",
            *FFMPEG_INPUT_GUARD,
            "-i",
            str(src),
            "-map",
            "0:v:0",
            "-an",
            "-vf",
            f"scale=160:-2,select='gt(scene,{threshold})',showinfo",
            "-f",
            "null",
            "-",
        ]
        try:
            proc = subprocess.run(cmd, capture_output=True, timeout=self.limits.extract_timeout_s, check=False)
        except subprocess.TimeoutExpired:
            raise MediaTimeoutError("shot detection timed out") from None
        if proc.returncode != 0:
            raise MediaDecodeError("shot detection failed")
        stderr = proc.stderr.decode("utf-8", "replace")
        return [max(0, int(round((float(m.group(3)) - start_s) * 1000))) for m in _SHOWINFO_RE.finditer(stderr)]

    # ------------------------------------------------------------------ crops
    def crop(self, frame_asset_id: str, box01: Sequence[float], owner_id: str) -> CropRef:
        """Crop ``box01`` (displayed-frame coordinates) from a stored frame."""
        box = validate_box01(box01)
        frame = self.get_frame(frame_asset_id, owner_id)
        path = self.store.path(frame_asset_id, owner_id)
        with Image.open(path) as im:
            img = im.convert("RGB")
        if img.size != (frame.width, frame.height):
            raise MediaDecodeError("stored frame does not match its recorded dimensions")
        rect = box01_to_pixels(box, frame.width, frame.height, min_side=self.limits.min_crop_side_px)
        cropped = img.crop(rect)
        cid = self.store.new_id("crop")
        ref = CropRef(
            crop_asset_id=cid,
            frame_asset_id=frame_asset_id,
            box01=box,
            pixel_box=rect,
            frame_width=frame.width,
            frame_height=frame.height,
            width=cropped.width,
            height=cropped.height,
            sharpness=sharpness_score(cropped),
        )
        self.store.put_bytes(
            cid,
            _encode_jpeg(cropped),
            {"owner_id": owner_id, "kind": "crop", "mime": "image/jpeg", "crop": ref.model_dump(mode="json")},
        )
        return ref

    def get_crop(self, crop_asset_id: str, owner_id: str) -> CropRef:
        meta = self.store.meta(crop_asset_id, owner_id)
        if meta.get("kind") != "crop":
            raise MediaError("asset is not a crop")
        return CropRef.model_validate(meta["crop"])


def select_supporting_crops(crops: Sequence[CropRef], limit: int = 3) -> list[CropRef]:
    """Pick up to ``limit`` clear crops: sharpness weighted by pixel size."""
    return sorted(crops, key=lambda c: c.sharpness * math.sqrt(c.width * c.height), reverse=True)[:limit]
