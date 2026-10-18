import pytest
from media_factory import HAVE_FFMPEG, moving_box_video
from shopping.fakes import FakeCatalog, item

from .conftest import H, new_client, wait


@pytest.mark.skipif(not HAVE_FFMPEG, reason="ffmpeg needed")
def test_fixture_detection_groups_garments_and_is_labeled(app_factory, tmp_path, monkeypatch):
    monkeypatch.setenv("PERCEPTION_PROVIDER", "fixture")
    c = new_client(app_factory(FakeCatalog([item("a", "Black Bomber Jacket", 70)])))
    h = c.get("/api/health").json()
    assert h["providers"]["perceptron"]["mode"] == "fixture"
    s = c.post("/api/sessions", headers=H).json()["session"]
    clip = moving_box_video(tmp_path / "clip.mp4", seconds=3.0).read_bytes()
    s = c.post(f"/api/media/uploads?sessionId={s['id']}&expectedRevision={s['revision']}", content=clip, headers=H).json()["session"]
    a = wait(lambda: c.get(f"/api/analysis/{s['analysisId']}").json(), lambda a: a["status"] not in ("queued", "running"))
    assert a["detectionMode"] == "fixture" and a["status"] in ("completed", "partial")
    v = c.get(f"/api/sessions/{s['id']}").json()
    labels = sorted(g["label"] for g in v["garments"])
    assert labels and all(g["groupingBasis"] in ("single", "within_shot") for g in v["garments"])
    assert all(o["modelId"] == "fixture" and not o["editedByUser"] for o in v["observations"])
    assert {o["timestampMs"] for o in v["observations"]} - {None}  # timed video observations
