"""YouTube analyze product path: download → ingest → analysis → garments."""

from __future__ import annotations

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
    monkeypatch.setenv("FEATURE_YOUTUBE_DOWNLOAD", "1")
    monkeypatch.setenv("YOUTUBE_ALLOWED_VIDEO_IDS", "7-etsr5-Z8A")
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


def test_youtube_analyze_rejects_bad_url(app_factory, monkeypatch):
    monkeypatch.setenv("FEATURE_YOUTUBE_DOWNLOAD", "1")
    c = new_client(app_factory(FakeCatalog([])))
    s = c.post("/api/sessions", headers=H).json()["session"]
    resp = c.post(
        f"/api/sessions/{s['id']}/youtube-analyze",
        headers=H,
        json={"youtubeUrl": "https://example.com/not-youtube", "expectedRevision": s["revision"]},
    )
    assert resp.status_code == 400
    assert resp.json()["code"] == "invalid_url"


def _start(c, url):
    s = c.post("/api/sessions", headers=H).json()["session"]
    return c.post(f"/api/sessions/{s['id']}/youtube-analyze", headers=H,
                  json={"youtubeUrl": url, "expectedRevision": s["revision"]})


def test_flag_off_refuses_before_download(app_factory, monkeypatch):
    calls = []
    monkeypatch.setattr("app.routes.api.download_youtube", lambda *a: calls.append(a))
    r = _start(new_client(app_factory(FakeCatalog([]))), "https://www.youtube.com/watch?v=7-etsr5-Z8A")
    assert r.status_code == 404 and r.json()["code"] == "feature_disabled" and calls == []


def test_unpermitted_video_refused_before_download(app_factory, monkeypatch):
    monkeypatch.setenv("FEATURE_YOUTUBE_DOWNLOAD", "1")
    monkeypatch.setenv("YOUTUBE_ALLOWED_VIDEO_IDS", "aqz-KE-bpKQ")
    calls = []
    monkeypatch.setattr("app.routes.api.download_youtube", lambda *a: calls.append(a))
    r = _start(new_client(app_factory(FakeCatalog([]))), "https://www.youtube.com/watch?v=7-etsr5-Z8A")
    assert r.status_code == 403 and r.json()["code"] == "video_not_permitted" and calls == []


def test_ytdlp_command_never_uses_cookies_or_client_overrides(monkeypatch):
    from app.media.youtube_cache import _yt_dlp_cmd

    monkeypatch.setenv("YOUTUBE_COOKIES_FROM_BROWSER", "chrome")
    monkeypatch.setenv("YOUTUBE_COOKIES_FILE", "/tmp/cookies.txt")
    monkeypatch.setenv("YOUTUBE_PLAYER_CLIENT", "android")
    cmd = " ".join(_yt_dlp_cmd("https://www.youtube.com/watch?v=aqz-KE-bpKQ", "/tmp/x.%(ext)s"))
    assert "cookies" not in cmd and "player_client" not in cmd and "--ignore-config" in cmd


def test_blocked_download_is_single_attempt_and_honest(tmp_path, monkeypatch):
    import subprocess

    from app.media import youtube_cache as yc

    runs = []

    def fake_run(cmd, **kw):
        runs.append(cmd)
        return subprocess.CompletedProcess(cmd, 1, "", "ERROR: Sign in to confirm you're not a bot")

    monkeypatch.setattr(yc.subprocess, "run", fake_run)
    with pytest.raises(yc.YoutubeCacheError) as e:
        yc.download_youtube(tmp_path, "https://www.youtube.com/watch?v=aqz-KE-bpKQ")
    assert e.value.code == "youtube_blocked" and "Upload" in e.value.message and len(runs) == 1
