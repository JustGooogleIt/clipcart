"""YouTube analyze product path: download → ingest → analysis → garments."""

from __future__ import annotations

from pathlib import Path

import pytest
from media_factory import HAVE_FFMPEG, moving_box_video
from shopping.fakes import FakeCatalog, item

from .conftest import H, new_client, wait


def test_parse_video_id_accepts_watch_and_shorts():
    from app.media.youtube_cache import YoutubeCacheError, parse_video_id

    assert parse_video_id("https://www.youtube.com/watch?v=7-etsr5-Z8A") == "7-etsr5-Z8A"
    assert parse_video_id("https://youtu.be/7-etsr5-Z8A") == "7-etsr5-Z8A"
    assert parse_video_id("https://www.youtube.com/shorts/OEUkhEPVadA") == "OEUkhEPVadA"
    with pytest.raises(YoutubeCacheError) as ei:
        parse_video_id("https://example.com/watch?v=abc")
    assert ei.value.code == "invalid_url"


@pytest.mark.skipif(not HAVE_FFMPEG, reason="ffmpeg needed")
def test_youtube_analyze_uses_ranked_path_and_groups(app_factory, tmp_path, monkeypatch):
    monkeypatch.setenv("PERCEPTION_PROVIDER", "fixture")
    clip = moving_box_video(tmp_path / "yt.mp4", seconds=3.0)

    class FakeCached:
        video_id = "7-etsr5-Z8A"
        path = clip
        youtube_url = "https://www.youtube.com/watch?v=7-etsr5-Z8A"
        title = "Winter coats lookbook"
        duration_s = 3.0
        cached = False
        downloaded_at = 0.0

    # Route binds the symbol at import time.
    monkeypatch.setattr("app.routes.api.download_youtube", lambda _cache, _url: FakeCached())

    c = new_client(app_factory(FakeCatalog([item("a", "Black Bomber Jacket", 70)])))
    s = c.post("/api/sessions", headers=H).json()["session"]
    resp = c.post(
        f"/api/sessions/{s['id']}/youtube-analyze",
        headers=H,
        json={"youtubeUrl": "https://www.youtube.com/watch?v=7-etsr5-Z8A", "expectedRevision": s["revision"]},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["youtube"]["videoId"] == "7-etsr5-Z8A"
    assert body["youtube"]["cacheHit"] is False
    assert any("Temporary YouTube download" in w for w in body["warnings"])
    s = body["session"]
    assert body["media"]["sourceType"] == "youtube_download"
    assert body["media"]["canonicalSourceUrl"] == "https://www.youtube.com/watch?v=7-etsr5-Z8A"

    a = wait(
        lambda: c.get(f"/api/analysis/{s['analysisId']}").json(),
        lambda a: a["status"] not in ("queued", "running"),
        timeout=30,
    )
    assert a["status"] in ("completed", "partial")
    v = c.get(f"/api/sessions/{s['id']}").json()
    assert v["garments"], "expected fixture garments from ranked YouTube frames"
    assert all(o.get("timestampMs") is not None for o in v["observations"])


def test_youtube_analyze_rejects_bad_url(app_factory):
    c = new_client(app_factory(FakeCatalog([])))
    s = c.post("/api/sessions", headers=H).json()["session"]
    resp = c.post(
        f"/api/sessions/{s['id']}/youtube-analyze",
        headers=H,
        json={"youtubeUrl": "https://example.com/not-youtube", "expectedRevision": s["revision"]},
    )
    assert resp.status_code == 400
    assert resp.json()["code"] == "invalid_url"
