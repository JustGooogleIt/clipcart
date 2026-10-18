"""Accessories through the API: categories, manual crop, ring size, search, warnings, memory."""

from shopping.fakes import FakeCatalog, item

from .conftest import H, jpeg_bytes, new_client, wait

WATCHES = [
    item("w1", "Seiko silver-tone automatic watch", 180, brand="Seiko"),
    item("w2", "Apple Watch Band 41mm Sport Loop", 20),
    item("w3", "14K Gold Diamond Watch Authentic", 900),
    item("w4", "Black denim trucker jacket", 60),
]


def _session_with_item(c, category, description):
    s = c.post("/api/sessions", headers=H).json()["session"]
    v = c.post(f"/api/media/uploads?sessionId={s['id']}&expectedRevision={s['revision']}", content=jpeg_bytes(), headers=H).json()
    s = v["session"]
    a = wait(lambda: c.get(f"/api/analysis/{s['analysisId']}").json(), lambda a: a["status"] not in ("queued", "running"))
    r = c.post(f"/api/sessions/{s['id']}/garments", headers=H, json={
        "frameAssetId": a["frames"][0]["assetId"], "box01": [0.40, 0.40, 0.46, 0.47], "category": category,
        "description": description})
    assert r.status_code in (200, 201), r.text
    g = r.json()["garment"]
    s = c.get(f"/api/sessions/{s['id']}").json()["session"]
    s = c.patch(f"/api/sessions/{s['id']}", headers=H, json={"expectedRevision": s["revision"], "selectedGarmentId": g["id"]}).json()["session"]
    return s, g


def _search(c, s):
    r = c.post(f"/api/sessions/{s['id']}/searches", headers=H, json={"expectedRevision": s["revision"]}).json()
    return wait(lambda: c.get(f"/api/searches/{r['searchId']}").json(), lambda o: o["job"]["status"] not in ("queued", "running"))


def test_categories_endpoint_and_feature_flag(app_factory):
    c = new_client(app_factory())
    cats = {x["id"]: x for x in c.get("/api/categories").json()["categories"]}
    assert cats["ring"]["sizeRule"] == "ring" and cats["watch"]["family"] == "watch" and "jacket" in cats
    assert c.get("/api/health").json()["features"]["accessoryDetection"] is False


def test_manual_crop_watch_search_has_no_clothing_size_and_flags_seller_claims(app_factory):
    c = new_client(app_factory(FakeCatalog(WATCHES, {s: {"sizes": ["M"], "carrying": 1} for s in ("w1", "w2", "w3", "w4")})))
    s, g = _session_with_item(c, "watch", "silver-tone round watch on a metal bracelet")
    assert g["category"] == "watch"
    s = c.patch(f"/api/sessions/{s['id']}", headers=H, json={"expectedRevision": s["revision"],
                                                              "preferences": {"size": {"raw": "M"}}}).json()["session"]
    out = _search(c, s)
    titles = [r["listing"]["title"] for r in out["results"]]
    assert "Apple Watch Band 41mm Sport Loop" not in titles and "Black denim trucker jacket" not in titles
    assert titles and all(r["recommendation"]["identityTier"] == "similar" for r in out["results"])
    for r in out["results"]:
        assert all(ch["constraint"] != "size" for ch in r["recommendation"]["constraintChecks"])
    claims = next(r for r in out["results"] if r["listing"]["title"].startswith("14K"))
    assert any("seller's description" in w for w in claims["recommendation"]["warnings"])
    seiko = next(r for r in out["results"] if r["listing"]["title"].startswith("Seiko"))
    assert not any("seller's description" in w for w in seiko["recommendation"]["warnings"])


def test_ring_size_preference_validates_and_applies(app_factory):
    rings = [item("r1", "Gold-tone signet ring", 40), item("r2", "Key ring with leather fob", 10)]
    c = new_client(app_factory(FakeCatalog(rings, {"r1": {"sizes": ["6", "7", "8"], "carrying": 1}})))
    s, _ = _session_with_item(c, "ring", "gold-tone signet ring")
    bad = c.patch(f"/api/sessions/{s['id']}", headers=H, json={"expectedRevision": s["revision"], "preferences": {"ringSize": {"raw": "M"}}})
    assert bad.status_code == 422
    s = c.patch(f"/api/sessions/{s['id']}", headers=H, json={"expectedRevision": s["revision"],
                                                              "preferences": {"ringSize": {"raw": "US 7"}}}).json()["session"]
    assert s["preferences"]["ringSize"] == {"raw": "7", "system": "us"}
    out = _search(c, s)
    assert [r["listing"]["title"] for r in out["results"]] == ["Gold-tone signet ring"]
    checks = {ch["constraint"]: ch["state"] for ch in out["results"][0]["recommendation"]["constraintChecks"]}
    assert checks.get("ring size") == "satisfied"


def test_legacy_garment_categories_still_accepted(app_factory):
    c = new_client(app_factory(FakeCatalog(WATCHES)))
    s, g = _session_with_item(c, "jacket", "black denim trucker jacket")
    assert g["category"] == "jacket"


def test_analysis_requests_accessories_only_with_the_flag(app_factory, monkeypatch):
    seen = []
    from app.providers.perceptron import adapter

    orig = adapter.PerceptronPerceptionProvider.analyze

    def spy(self, frames, categories, ctx):
        seen.append(list(categories))
        return orig(self, frames, categories, ctx)

    monkeypatch.setattr(adapter.PerceptronPerceptionProvider, "analyze", spy)
    monkeypatch.setenv("PERCEPTION_PROVIDER", "fixture")
    for flag, expect in (("0", False), ("1", True)):
        monkeypatch.setenv("FEATURE_ACCESSORY_DETECTION", flag)
        c = new_client(app_factory())
        s = c.post("/api/sessions", headers=H).json()["session"]
        v = c.post(f"/api/media/uploads?sessionId={s['id']}&expectedRevision={s['revision']}", content=jpeg_bytes(), headers=H).json()
        wait(lambda: c.get(f"/api/analysis/{v['session']['analysisId']}").json(), lambda a: a["status"] not in ("queued", "running"))
        assert ("ring" in seen[-1]) is expect
