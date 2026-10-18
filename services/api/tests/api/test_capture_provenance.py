"""Browser-capture provenance on POST /api/media/uploads (extension handoff, HANDOFF.md change B)."""

from urllib.parse import urlencode

import pytest

from .conftest import H, jpeg_bytes, new_client


def _upload(c, s, **params):
    q = urlencode({"sessionId": s["id"], "expectedRevision": s["revision"], **params})
    return c.post(f"/api/media/uploads?{q}", content=jpeg_bytes(), headers={**H, "Content-Type": "image/jpeg"})


def test_capture_with_provenance_is_stored_and_typed(app_factory):
    c = new_client(app_factory())
    s = c.post("/api/sessions", headers=H).json()["session"]
    r = _upload(c, s, sourceUrl="https://www.youtube.com/watch?v=abc&t=22", sourceTitle="  Fit check\n#12 \u0007 ")
    assert r.status_code == 200, r.text
    m = r.json()["media"]
    assert m["sourceType"] == "browser_capture"
    assert m["canonicalSourceUrl"] == "https://www.youtube.com/watch?v=abc&t=22"
    assert m["sourceTitle"] == "Fit check #12"  # whitespace collapsed, control characters dropped
    latest = c.get("/api/sessions/latest").json()
    assert latest["media"]["sourceTitle"] == "Fit check #12" and latest["media"]["sourceType"] == "browser_capture"


def test_plain_upload_is_unchanged(app_factory):
    c = new_client(app_factory())
    s = c.post("/api/sessions", headers=H).json()["session"]
    m = _upload(c, s).json()["media"]
    assert m["sourceType"] == "upload_image" and m["canonicalSourceUrl"] is None and m["sourceTitle"] is None


def test_long_title_is_capped(app_factory):
    c = new_client(app_factory())
    s = c.post("/api/sessions", headers=H).json()["session"]
    m = _upload(c, s, sourceUrl="http://example.com/v", sourceTitle="x" * 1000).json()["media"]
    assert len(m["sourceTitle"]) == 300


@pytest.mark.parametrize("params", [
    {"sourceUrl": "javascript:alert(1)"},
    {"sourceUrl": "file:///etc/passwd"},
    {"sourceUrl": "https://user:pw@example.com/v"},
    {"sourceUrl": "https://example.com:99999/v"},
    {"sourceUrl": "https://"},
    {"sourceUrl": "https://example.com/" + "a" * 2100},
    {"sourceTitle": "title without a url"},
])
def test_invalid_provenance_is_rejected_before_ingest(app_factory, params):
    app = app_factory()
    c = new_client(app)
    s = c.post("/api/sessions", headers=H).json()["session"]
    r = _upload(c, s, **params)
    assert r.status_code == 422 and r.json()["code"] == "invalid_request"
    assert c.get(f"/api/sessions/{s['id']}").json()["session"].get("mediaId") is None
