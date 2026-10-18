"""Ranked frame selection for YouTube / fashion clips."""

from __future__ import annotations

import pytest
from media_factory import HAVE_FFMPEG, moving_box_video

from app.media.service import MediaService, _fashion_usefulness_score, _uniform_sample_times
from app.media.storage import LocalAssetStore
from PIL import Image


def test_uniform_sample_times_spans_clip():
    times = _uniform_sample_times(10.0, 2.0)
    assert times[0] < 1.0
    assert times[-1] > 8.0
    assert len(times) >= 4


def test_fashion_score_prefers_mid_exposure_detail():
    dark = Image.new("RGB", (200, 200), (2, 2, 2))
    mid = Image.new("RGB", (200, 200), (120, 80, 40))
    # Add structure to mid
    for x in range(40, 160):
        for y in range(40, 160):
            mid.putpixel((x, y), (200 if (x + y) % 3 else 40, 90, 60))
    assert _fashion_usefulness_score(mid) > _fashion_usefulness_score(dark)


@pytest.mark.skipif(not HAVE_FFMPEG, reason="ffmpeg needed")
def test_extract_ranked_frames_returns_bounded_set(tmp_path):
    clip = moving_box_video(tmp_path / "clip.mp4", seconds=4.0)
    svc = MediaService(LocalAssetStore(tmp_path / "media"))
    with clip.open("rb") as fh:
        asset = svc.ingest(fh, "own_test", source_type="youtube_download", source_url="https://youtu.be/abcdefghijk")
    frames = svc.extract_ranked_frames(asset.id, "own_test", max_frames=4, max_candidates=16, sample_interval_s=0.5)
    assert 1 <= len(frames) <= 4
    stamps = [f.timestamp_ms for f in frames]
    assert all(t is not None for t in stamps)
    assert stamps == sorted(stamps)
