import os
import sys
import time
import uuid
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
    real = _real_mongo_uri()
    dbs: list[str] = []
    if real:
        # Opt-in: run against a real MongoDB server. Each app gets its own throwaway database.
        monkeypatch.setenv("MONGODB_URI", real)
    from app.main import create_app
    from app.shopping.tools import clear_cache

    def make(catalog=None):
        clear_cache()
        if real:
            name = f"cctest_{uuid.uuid4().hex[:12]}"
            dbs.append(name)
            monkeypatch.setenv("MONGODB_DB", name)
        app = create_app()
        if catalog is not None:
            app.state.clipcart.catalog = catalog
        return app

    yield make
    if real and dbs:
        import pymongo

        client = pymongo.MongoClient(real, serverSelectionTimeoutMS=5000)
        for name in dbs:
            client.drop_database(name)
        client.close()


def _real_mongo_uri() -> str | None:
    """CLIPCART_TEST_MONGODB_URI opts the API tests into a real MongoDB (default: mongomock).

    Tests create and drop their own cctest_* databases, so point this at a local or dedicated test
    server, never at the app's Atlas cluster.
    """
    uri = os.getenv("CLIPCART_TEST_MONGODB_URI")
    if uri and "mongodb.net" in uri and not os.getenv("CLIPCART_TEST_ALLOW_ATLAS"):
        raise pytest.UsageError("CLIPCART_TEST_MONGODB_URI points at Atlas; set CLIPCART_TEST_ALLOW_ATLAS=1 for a dedicated test cluster")
    return uri or None


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
