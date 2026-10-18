"""UI review paths through the real fixture providers, with no injected session data.

Perception: tests/perception/fixtures/perceptron_dev_fixture.json (a labelled wristwatch box, returned only when
accessory detection is requested). Catalog: the default fixture catalog, which merges the labelled synthetic
fixtures/catalog/ui_review_catalog.json (watches, rings, jackets whose titles state a style).
"""

import pytest
from media_factory import HAVE_FFMPEG, moving_box_video

from .conftest import H, new_client, wait
from .test_accessories_api import _search, _session_with_item

CODE_TEXT = {
    "seller_claims_unverified": "Metal, stones and authenticity are the seller's description; ClipCart doesn't verify them.",
    "availability_unknown": "Availability unknown",
    "fixture_data": "Fixture data: not a live result",
}


@pytest.fixture
def fx(app_factory, monkeypatch, tmp_path):
    def make(accessories=True, style=True):
        monkeypatch.setenv("PERCEPTION_PROVIDER", "fixture")
        monkeypatch.setenv("CATALOG_PROVIDER", "fixture")
        if accessories:
            monkeypatch.setenv("FEATURE_ACCESSORY_DETECTION", "1")
        if style:
            monkeypatch.setenv("FEATURE_STYLE_MEMORY", "1")
        return new_client(app_factory())
    return make


def _analyzed(c, tmp_path):
    s = c.post("/api/sessions", headers=H).json()["session"]
    clip = moving_box_video(tmp_path / "clip.mp4", seconds=3.0).read_bytes()
    s = c.post(f"/api/media/uploads?sessionId={s['id']}&expectedRevision={s['revision']}", content=clip, headers=H).json()["session"]
    wait(lambda: c.get(f"/api/analysis/{s['analysisId']}").json(), lambda a: a["status"] not in ("queued", "running"))
    return c.get(f"/api/sessions/{s['id']}").json()


def _select(c, view, category):
    s = view["session"]
    g = next(g for g in view["garments"] if g["category"] == category)
    s = c.patch(f"/api/sessions/{s['id']}", headers=H, json={"expectedRevision": s["revision"], "selectedGarmentId": g["id"]}).json()["session"]
    return s, g


def _assert_coded_tail(rec):
    codes = rec["warningCodes"]
    assert rec["warnings"][len(rec["warnings"]) - len(codes):] == [CODE_TEXT[c] for c in codes]


@pytest.mark.skipif(not HAVE_FFMPEG, reason="ffmpeg needed")
def test_fixture_watch_detection_has_attributes_text_and_coded_seller_claims(fx, tmp_path):
    c = fx()
    view = _analyzed(c, tmp_path)
    s, g = _select(c, view, "watch")
    obs = next(o for o in view["observations"] if o["category"] == "watch")
    assert obs["modelId"] == "fixture" and obs["visibleText"] == ["FIELD 38"]
    assert obs["observedAttributes"]["color"] == ["silver-tone"] and "metal bracelet" in obs["observedAttributes"]["details"]
    out = _search(c, s)
    by = {r["listing"]["title"]: r["recommendation"] for r in out["results"]}
    assert "Silver-tone Metal Watch Band 20mm Round Links" not in by  # straps aren't watches
    claims = by["14K White Gold Diamond Accent Watch, Silver Tone - Authentic, Swiss Made"]
    plain = by["Silver-tone Round Field Watch with Metal Bracelet"]
    assert "seller_claims_unverified" in claims["warningCodes"] and "seller_claims_unverified" not in plain["warningCodes"]
    assert all(r["identityTier"] == "similar" for r in by.values())
    for rec in by.values():
        _assert_coded_tail(rec)
        assert all(ch["constraint"] != "size" for ch in rec["constraintChecks"])


@pytest.mark.skipif(not HAVE_FFMPEG, reason="ffmpeg needed")
def test_accessories_stay_hidden_when_detection_is_off(fx, tmp_path):
    c = fx(accessories=False)
    view = _analyzed(c, tmp_path)
    assert view["garments"] and not [g for g in view["garments"] if g["category"] == "watch"]


def test_fixture_rings_check_us_ring_size(fx):
    c = fx()
    s, _ = _session_with_item(c, "ring", "silver-tone signet ring")
    s = c.patch(f"/api/sessions/{s['id']}", headers=H, json={"expectedRevision": s["revision"],
                                                              "preferences": {"ringSize": {"raw": "7"}}}).json()["session"]
    out = _search(c, s)
    checks = {r["listing"]["title"]: {ch["constraint"]: ch["state"] for ch in r["recommendation"]["constraintChecks"]}
              for r in out["results"]}
    assert checks["Sterling Silver 925 Signet Ring"]["ring size"] == "satisfied"
    sterling = next(r["recommendation"] for r in out["results"] if r["listing"]["title"].startswith("Sterling"))
    assert "seller_claims_unverified" in sterling["warningCodes"]
    _assert_coded_tail(sterling)


@pytest.mark.skipif(not HAVE_FFMPEG, reason="ffmpeg needed")
def test_fixture_jacket_saves_infer_a_style_with_evidence(fx, tmp_path):
    c = fx(accessories=False)
    view = _analyzed(c, tmp_path)
    s, _ = _select(c, view, "jacket")
    out = _search(c, s)
    by = {r["listing"]["title"]: r["recommendation"] for r in out["results"]}
    for t in ("Vintage 90s Black Denim Trucker Jacket", "Black Bomber Jacket, Vintage Wash Nylon"):
        r = c.post("/api/style/events", headers=H, json={"type": "saved_item", "recommendationId": by[t]["id"]})
        assert r.status_code == 201, r.text
        assert [f["tag"] for f in r.json()["event"]["item"]["styleFacts"]] == ["vintage"]
    [m] = [m for m in c.get("/api/style/memories").json()["memories"] if m["kind"] == "style_like"]
    assert m["value"] == "vintage" and m["origin"] == "inferred" and len(m["evidence"]) == 2
    assert all("intage" in e["excerpt"] for e in m["evidence"])


@pytest.mark.skipif(not HAVE_FFMPEG, reason="ffmpeg needed")
def test_accessory_research_offers_through_manual_import_are_coded(fx, tmp_path, monkeypatch):
    # SoleScout research only turns SoleScout store records into offers, so the synthetic watches never appear there
    # (they would be mislabelled). Accessory research offers come in through the labelled manual import instead.
    monkeypatch.setenv("FEATURE_AGENT_RESEARCH", "1")
    monkeypatch.setenv("RESEARCH_PROVIDER", "manual")
    monkeypatch.setenv("RESEARCH_RESOLVE_DNS", "0")
    c = fx()
    assert c.get("/api/health").json()["research"] == {"provider": "manual", "mode": "manual"}
    view = _analyzed(c, tmp_path)
    s, _ = _select(c, view, "watch")
    job = c.post(f"/api/sessions/{s['id']}/research-jobs", headers=H, json={"idempotencyKey": "w1"}).json()["job"]
    now = job["createdAt"]
    products = [
        {"retailer": "Synthetic test store", "productUrl": "https://www.example.com/clipcart-fixture/w-claims", "observedAt": now,
         "title": "14K White Gold Diamond Accent Watch, Silver Tone - Authentic", "matchType": "similar",
         "observedPrice": {"amountMinor": 89000, "currency": "USD"}, "priceExcerpt": "$890.00"},
        {"retailer": "Synthetic test store", "productUrl": "https://www.example.com/clipcart-fixture/w-plain", "observedAt": now,
         "title": "Silver-tone Round Field Watch", "matchType": "similar"},
    ]
    r = c.post(f"/api/research-jobs/{job['id']}/import", headers=H, json={"products": products, "notes": "UI review fixture"})
    assert r.status_code in (200, 202), r.text
    done = r.json()["job"]
    by = {p["title"]: p for p in done["products"]}
    claims, plain = by[products[0]["title"]], by[products[1]["title"]]
    assert claims["source"] == "manual_import" and "seller_claims_unverified" in claims["warningCodes"]
    assert "seller_claims_unverified" not in plain["warningCodes"]
    assert plain["price"] is None and plain["section"] == "needs_checking"  # unpriced: never Recommended
    for p in done["products"]:
        assert len(p["warnings"]) == len(p["warningCodes"]) + 1  # the first names the source; the rest are coded, in order
