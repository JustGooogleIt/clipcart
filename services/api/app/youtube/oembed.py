"""Accessibility probe using YouTube's public oEmbed metadata endpoint.

Metadata only (title, channel). This is never a source of video bytes and
does not use the YouTube Data API.
"""

from __future__ import annotations

from dataclasses import dataclass

import httpx

OEMBED_URL = "https://www.youtube.com/oembed"


@dataclass(frozen=True)
class OEmbedResult:
    state: str  # ok | not_found | restricted | unknown
    title: str | None = None
    channel: str | None = None
    http_status: int | None = None


def probe(canonical_url: str, *, timeout_s: float = 8.0, client: httpx.Client | None = None) -> OEmbedResult:
    try:
        c = client or httpx
        r = c.get(OEMBED_URL, params={"url": canonical_url, "format": "json"}, timeout=timeout_s)
    except httpx.HTTPError:
        return OEmbedResult("unknown")
    if r.status_code == 200:
        try:
            d = r.json()
        except ValueError:
            return OEmbedResult("unknown", http_status=200)
        return OEmbedResult("ok", str(d.get("title") or "")[:200] or None, str(d.get("author_name") or "")[:120] or None, 200)
    if r.status_code in (400, 404):
        return OEmbedResult("not_found", http_status=r.status_code)
    if r.status_code in (401, 403):
        # Private, or public with embedding disabled; Gemini decides which.
        return OEmbedResult("restricted", http_status=r.status_code)
    return OEmbedResult("unknown", http_status=r.status_code)
