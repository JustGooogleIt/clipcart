import sys
import time
from pathlib import Path

import pytest

_API = Path(__file__).resolve().parents[2]
for p in (_API, _API / "tests" / "media", _API / "tests"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from fastapi.testclient import TestClient  # noqa: E402

H = {"X-ClipCart-Request": "1"}


@pytest.fixture
def app_factory(tmp_path, monkeypatch):
    for k in (
        "MONGODB_URI",
        "PERCEPTRON_API_KEY",
        "XAI_API_KEY",
        "PERCEPTION_PROVIDER",
        "FEATURE_YOUTUBE_DOWNLOAD",
        "YOUTUBE_ALLOWED_VIDEO_IDS",
        "FEATURE_AGENT_RESEARCH",
    ):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("CLIPCART_SKIP_DOTENV", "1")  # never read real keys in tests
    monkeypatch.setenv("CLIPCART_MEDIA_ROOT", str(tmp_path / "media"))
    monkeypatch.setenv("CLIPCART_WEB_DIST", str(tmp_path / "nodist"))
    from app.main import create_app
    from app.shopping.tools import clear_cache

    def make(catalog=None):
        clear_cache()
        app = create_app()
        if catalog is not None:
            app.state.clipcart.catalog = catalog
        return app

    return make


def wait(fn, cond, timeout=15):
    t0 = time.time()
    while time.time() - t0 < timeout:
        v = fn()
        if cond(v):
            return v
        time.sleep(0.1)
    raise AssertionError("timeout")


def jpeg_bytes():
    from media_factory import encode_with_orientation, marker_image

    return encode_with_orientation(marker_image((400, 300), (100, 60, 300, 260), color=(10, 10, 10)), 1)


def new_client(app):
    return TestClient(app)


def bootstrap(client):
    """Session -> upload -> manual garment -> selected. Returns (session, garment)."""
    s = client.post("/api/sessions", headers=H).json()["session"]
    v = client.post(f"/api/media/uploads?sessionId={s['id']}&expectedRevision={s['revision']}", content=jpeg_bytes(), headers=H).json()
    s = v["session"]
    a = wait(lambda: client.get(f"/api/analysis/{s['analysisId']}").json(), lambda a: a["status"] not in ("queued", "running"))
    g = client.post(f"/api/sessions/{s['id']}/garments", headers=H,
                    json={"frameAssetId": a["frames"][0]["assetId"], "box01": [0.2, 0.2, 0.8, 0.9], "category": "jacket",
                          "description": "black bomber"}).json()["garment"]
    s = client.patch(f"/api/sessions/{s['id']}", headers=H,
                     json={"expectedRevision": s["revision"], "selectedGarmentId": g["id"]}).json()["session"]
    return s, g, a
