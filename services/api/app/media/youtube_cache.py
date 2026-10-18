"""Temporary YouTube download cache (yt-dlp). Bounded duration/height/TTL.

Ported from experiments/youtube-capture for the product ingest path.
Cache lives under the media store root; never commit bytes.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import parse_qs, urlparse

MAX_DURATION_S = int(os.getenv("YOUTUBE_CACHE_MAX_DURATION_S", "90"))
MAX_HEIGHT = int(os.getenv("YOUTUBE_CACHE_MAX_HEIGHT", "720"))
TTL_S = int(os.getenv("YOUTUBE_CACHE_TTL_S", "3600"))
DOWNLOAD_TIMEOUT_S = int(os.getenv("YOUTUBE_CACHE_DOWNLOAD_TIMEOUT_S", "180"))

_VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{6,20}$")


class YoutubeCacheError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class CachedVideo:
    video_id: str
    path: Path
    youtube_url: str
    title: str | None
    duration_s: float | None
    cached: bool
    downloaded_at: float


def parse_video_id(raw: str) -> str:
    raw = (raw or "").strip()
    if not raw:
        raise YoutubeCacheError("invalid_url", "empty URL")
    try:
        u = urlparse(raw)
    except Exception as exc:  # noqa: BLE001
        raise YoutubeCacheError("invalid_url", "could not parse URL") from exc
    host = (u.hostname or "").lower()
    if host not in {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be", "www.youtu.be"}:
        raise YoutubeCacheError("invalid_url", "only youtube.com / youtu.be URLs are allowed")
    vid: str | None = None
    if "youtu.be" in host:
        vid = u.path.strip("/").split("/")[0] or None
    else:
        qs = parse_qs(u.query)
        if "v" in qs and qs["v"]:
            vid = qs["v"][0]
        else:
            parts = [p for p in u.path.split("/") if p]
            for key in ("embed", "shorts", "live", "v"):
                if key in parts:
                    i = parts.index(key)
                    if i + 1 < len(parts):
                        vid = parts[i + 1]
                        break
    if not vid or not _VIDEO_ID_RE.match(vid):
        raise YoutubeCacheError("invalid_url", "could not extract a YouTube video id")
    return vid


def _meta_path(cache_dir: Path, video_id: str) -> Path:
    return cache_dir / f"{video_id}.meta.json"


def _find_media(cache_dir: Path, video_id: str) -> Path | None:
    for ext in (".mp4", ".mkv", ".webm"):
        p = cache_dir / f"{video_id}{ext}"
        if p.is_file() and p.stat().st_size > 0:
            return p
    return None


def _section_arg(max_duration_s: int) -> str:
    m, s = divmod(max(1, max_duration_s), 60)
    return f"*0:00-{m}:{s:02d}"


def purge_expired(cache_dir: Path, *, now: float | None = None) -> int:
    cache_dir.mkdir(parents=True, exist_ok=True)
    now = now if now is not None else time.time()
    removed = 0
    for meta in cache_dir.glob("*.meta.json"):
        try:
            data = json.loads(meta.read_text(encoding="utf-8"))
            downloaded_at = float(data.get("downloaded_at") or 0)
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            downloaded_at = 0
        if downloaded_at and now - downloaded_at < TTL_S:
            continue
        video_id = meta.name.removesuffix(".meta.json")
        for p in cache_dir.glob(f"{video_id}.*"):
            try:
                p.unlink()
                removed += 1
            except OSError:
                pass
    return removed


def get_cached(cache_dir: Path, video_id: str) -> CachedVideo | None:
    purge_expired(cache_dir)
    meta_file = _meta_path(cache_dir, video_id)
    media = _find_media(cache_dir, video_id)
    if not meta_file.is_file() or media is None:
        return None
    try:
        data = json.loads(meta_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    downloaded_at = float(data.get("downloaded_at") or 0)
    if time.time() - downloaded_at > TTL_S:
        return None
    return CachedVideo(
        video_id=video_id,
        path=media,
        youtube_url=str(data.get("youtube_url") or ""),
        title=data.get("title"),
        duration_s=data.get("duration_s"),
        cached=True,
        downloaded_at=downloaded_at,
    )


def _yt_dlp_cmd(youtube_url: str, out_tmpl: str) -> list[str]:
    """One plain yt-dlp invocation. No browser cookies, cookie files or player-client
    overrides: blocked videos fail honestly instead of being worked around."""
    fmt = (
        f"bv*[height<={MAX_HEIGHT}][ext=mp4]+ba[ext=m4a]/"
        f"b[height<={MAX_HEIGHT}][ext=mp4]/"
        f"b[height<={MAX_HEIGHT}]/best"
    )
    return [
        sys.executable,
        "-m",
        "yt_dlp",
        "--no-playlist",
        "--no-warnings",
        "--ignore-config",  # never pick up a user-level yt-dlp config (cookies, proxies)
        "-f",
        fmt,
        "--merge-output-format",
        "mp4",
        "--download-sections",
        _section_arg(MAX_DURATION_S),
        "--force-keyframes-at-cuts",
        "-o",
        out_tmpl,
        "--print",
        "after_move:%(title)s\t%(duration)s",
        youtube_url,
    ]


_BLOCKED_HINTS = (
    "not a bot",
    "sign in",
    "page needs to be reloaded",
    "confirm you're not a bot",
    "http error 403",
    "http error 429",
    "private video",
    "members-only",
    "age-restricted",
)


def _is_blocked(err: str) -> bool:
    low = err.lower()
    return any(n in low for n in _BLOCKED_HINTS)


def download_youtube(cache_dir: Path, youtube_url: str) -> CachedVideo:
    """Download (or reuse cache) a short bounded clip for analysis ingest. Single attempt."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    video_id = parse_video_id(youtube_url)
    hit = get_cached(cache_dir, video_id)
    if hit:
        return hit

    purge_expired(cache_dir)
    out_tmpl = str(cache_dir / f"{video_id}.%(ext)s")
    cmd = _yt_dlp_cmd(youtube_url, out_tmpl)
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=DOWNLOAD_TIMEOUT_S, check=False)
    except FileNotFoundError as exc:
        raise YoutubeCacheError("yt_dlp_missing", "yt-dlp is not installed in the API environment") from exc
    except subprocess.TimeoutExpired as exc:
        raise YoutubeCacheError("timeout", f"download exceeded {DOWNLOAD_TIMEOUT_S}s") from exc

    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "yt-dlp failed")[-400:]
        if _is_blocked(err):
            raise YoutubeCacheError(
                "youtube_blocked",
                "YouTube didn't allow this download. Upload the clip from your device instead.",
            )
        raise YoutubeCacheError("download_failed", "The YouTube download failed. Upload the clip from your device instead.")

    media = _find_media(cache_dir, video_id)
    if media is None:
        raise YoutubeCacheError("download_failed", "yt-dlp finished but no media file was found")

    title = None
    duration_s = None
    for line in (proc.stdout or "").strip().splitlines():
        if "\t" in line:
            title, _, dur = line.partition("\t")
            title = title.strip() or None
            try:
                duration_s = float(dur)
            except ValueError:
                duration_s = None

    downloaded_at = time.time()
    meta = {
        "video_id": video_id,
        "youtube_url": youtube_url,
        "title": title,
        "duration_s": duration_s,
        "downloaded_at": downloaded_at,
        "path": media.name,
        "max_duration_s": MAX_DURATION_S,
        "ttl_s": TTL_S,
        "source": "yt-dlp_temporary_cache",
    }
    _meta_path(cache_dir, video_id).write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return CachedVideo(
        video_id=video_id,
        path=media,
        youtube_url=youtube_url,
        title=title,
        duration_s=duration_s,
        cached=False,
        downloaded_at=downloaded_at,
    )
