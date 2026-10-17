"""Validate and canonicalize YouTube video URLs.

Accepted: youtube.com/watch?v=ID, m./music. variants, youtu.be/ID,
youtube.com/shorts/ID, youtube.com/embed/ID, youtube-nocookie.com/embed/ID.
Rejected as unsupported: playlists without a video, channels, /live/ and
/clip/ URLs, and anything that is not https on a YouTube host.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import parse_qs, urlparse

_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")
_WATCH_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com"}
_EMBED_HOSTS = _WATCH_HOSTS | {"www.youtube-nocookie.com", "youtube-nocookie.com"}


class YouTubeUrlError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code  # invalid_url | unsupported_url
        self.message = message


@dataclass(frozen=True)
class YouTubeRef:
    video_id: str
    canonical_url: str


def parse_youtube_url(raw: str) -> YouTubeRef:
    text = (raw or "").strip()
    if not text or len(text) > 500 or any(c.isspace() for c in text):
        raise YouTubeUrlError("invalid_url", "Paste a single YouTube video link.")
    if "://" not in text:
        text = "https://" + text
    p = urlparse(text)
    host = (p.hostname or "").lower()
    if p.scheme not in ("https", "http") or not host:
        raise YouTubeUrlError("invalid_url", "That isn't a web link.")
    if p.username or p.password or (p.port not in (None, 443, 80)):
        raise YouTubeUrlError("invalid_url", "That link has credentials or a port; paste the plain YouTube link.")
    parts = [s for s in p.path.split("/") if s]
    vid = None
    if host in ("youtu.be", "www.youtu.be"):
        vid = parts[0] if parts else None
    elif host in _EMBED_HOSTS:
        if parts[:1] == ["watch"]:
            vid = (parse_qs(p.query).get("v") or [None])[0]
        elif parts[:1] in (["shorts"], ["embed"], ["v"]) and len(parts) >= 2:
            vid = parts[1]
        elif parts[:1] in (["live"], ["clip"]):
            raise YouTubeUrlError("unsupported_url", "Live streams and clips aren't supported. Use the video's watch link.")
        elif parts[:1] == ["playlist"] or "list" in parse_qs(p.query):
            raise YouTubeUrlError("unsupported_url", "Playlists aren't supported. Open one video and paste its link.")
        elif parts and (parts[0].startswith("@") or parts[0] in ("channel", "c", "user", "results", "feed")):
            raise YouTubeUrlError("unsupported_url", "That's a channel or page, not a video. Paste a video link.")
    else:
        raise YouTubeUrlError("unsupported_url", "Only YouTube video links are supported here.")
    if not vid or not _ID.match(vid):
        raise YouTubeUrlError("invalid_url", "That YouTube link has no valid video ID.")
    return YouTubeRef(video_id=vid, canonical_url=f"https://www.youtube.com/watch?v={vid}")
