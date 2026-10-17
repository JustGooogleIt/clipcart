from shopping.fakes import FakeCatalog, item

from .conftest import H, bootstrap, new_client, wait

ITEMS = [item("a", "Black Nylon Bomber Jacket", 70), item("b", "Black Satin Bomber Jacket", 95)]


def cat(**kw):
    return FakeCatalog(ITEMS, {s: {"sizes": ["M"], "hidden": 1, "carrying": 2} for s in "ab"}, **kw)


def test_health_reports_honest_modes(app_factory):
    c = new_client(app_factory())
    h = c.get("/api/health").json()
    assert h["database"]["mode"] == "local_memory" and "not MongoDB Atlas" in h["database"]["note"]
    assert h["providers"]["perceptron"]["mode"] == "unavailable"
    assert h["providers"]["grok"]["mode"] == "unavailable"
    assert h["features"] == {"photon": False, "voice": False, "solana": False, "youtubeGemini": False}


def test_full_journey_with_detection_unavailable(app_factory):
    c = new_client(app_factory(cat()))
    s, g, a = bootstrap(c)
    assert a["status"] == "detection_unavailable" and a["detectionMode"] == "unavailable"
    assert a["frames"][0]["timestampMs"] is None
    crop = c.get(f"/api/media/{g['representativeCropId']}")
    assert crop.status_code == 200 and crop.headers["content-type"] == "image/jpeg"
    r = c.post(f"/api/sessions/{s['id']}/searches", headers=H, json={"expectedRevision": s["revision"], "idempotencyKey": "s1"}).json()
    out = wait(lambda: c.get(f"/api/searches/{r['searchId']}").json(), lambda o: o["job"]["status"] not in ("queued", "running"))
    assert out["job"]["status"] == "completed" and out["job"]["workerMode"] == "rule_based"
    first = out["results"][0]
    assert first["listing"]["retailer"] == "SoleScout" and first["listing"]["priceBasis"] == "aggregate_lowest"
    assert first["evidence"] and first["listing"]["checkedAt"]
    tok = first["recommendation"]["links"][0]["token"]
    go = c.get(f"/go/{tok}", follow_redirects=False)
    assert go.status_code == 302 and go.headers["location"].startswith("https://solescout.ai/product/")
    sess = c.get(f"/api/sessions/{s['id']}").json()["session"]
    assert sess["lastPresentedResultIds"]  # committed and restorable on reload


def test_ownership_isolation(app_factory):
    app = app_factory(cat())
    a, b = new_client(app), new_client(app)
    s, g, an = bootstrap(a)
    b.post("/api/sessions", headers=H)
    assert b.get(f"/api/sessions/{s['id']}").status_code == 404
    assert b.get(f"/api/media/{g['representativeCropId']}").status_code == 404
    assert b.get(f"/api/analysis/{s['analysisId']}").status_code == 404
    assert b.patch(f"/api/sessions/{s['id']}", headers=H, json={"expectedRevision": s["revision"]}).status_code == 404
    r = a.post(f"/api/sessions/{s['id']}/searches", headers=H, json={"expectedRevision": s["revision"]}).json()
    out = wait(lambda: a.get(f"/api/searches/{r['searchId']}").json(), lambda o: o["job"]["status"] not in ("queued", "running"))
    tok = out["results"][0]["recommendation"]["links"][0]["token"]
    assert b.get(f"/api/searches/{r['searchId']}").status_code == 404
    assert b.get(f"/go/{tok}", follow_redirects=False).status_code == 404


def test_revision_idempotency_and_mutation_guard(app_factory):
    c = new_client(app_factory(cat()))
    s, g, _ = bootstrap(c)
    assert c.post("/api/sessions").status_code == 403  # no app header: cross-site mutation blocked
    body = {"expectedRevision": s["revision"], "idempotencyKey": "p1", "preferences": {"maxItemPriceMinor": 9000}}
    r1 = c.patch(f"/api/sessions/{s['id']}", headers=H, json=body)
    r2 = c.patch(f"/api/sessions/{s['id']}", headers=H, json=body)  # retry after reconnect: same result, no double apply
    assert r1.status_code == r2.status_code == 200 and r1.json()["session"]["revision"] == r2.json()["session"]["revision"]
    conflict = c.patch(f"/api/sessions/{s['id']}", headers=H, json={**body, "preferences": {"maxItemPriceMinor": 1}})
    assert conflict.status_code == 409 and conflict.json()["code"] == "idempotency_conflict"
    stale = c.patch(f"/api/sessions/{s['id']}", headers=H, json={"expectedRevision": s["revision"], "preferences": {"colors": ["red"]}})
    assert stale.status_code == 409 and stale.json()["code"] == "stale_revision" and stale.json()["requestId"]


def test_changed_preferences_supersede_running_search(app_factory):
    c = new_client(app_factory(cat(delay=0.6)))
    s, g, _ = bootstrap(c)
    r = c.post(f"/api/sessions/{s['id']}/searches", headers=H, json={"expectedRevision": s["revision"]}).json()
    first = r["searchId"]
    m = c.post(f"/api/sessions/{s['id']}/messages", headers=H,
               json={"text": "under $80 in black", "expectedRevision": r["session"]["revision"]}).json()
    assert m["applied"] and m["searchId"] != first
    wait(lambda: c.get(f"/api/searches/{m['searchId']}").json(), lambda o: o["job"]["status"] not in ("queued", "running"))
    old = wait(lambda: c.get(f"/api/searches/{first}").json(), lambda o: o["job"]["status"] not in ("queued", "running"))
    assert old["job"]["status"] == "superseded" and old["results"] == []
    sess = c.get(f"/api/sessions/{s['id']}").json()["session"]
    assert sess["activeSearchId"] == m["searchId"]
    assert sess["preferences"]["maxItemPriceMinor"] == 8000 and sess["preferences"]["colors"] == ["black"]


def test_go_rejects_unknown_and_arbitrary_targets(app_factory):
    c = new_client(app_factory(cat()))
    c.post("/api/sessions", headers=H)
    assert c.get("/go/https%3A%2F%2Fevil.example", follow_redirects=False).status_code == 404
    assert c.get("/go/lk_nope", follow_redirects=False).status_code == 404


def test_upload_rejects_fake_media(app_factory):
    c = new_client(app_factory(cat()))
    s = c.post("/api/sessions", headers=H).json()["session"]
    r = c.post(f"/api/media/uploads?sessionId={s['id']}&expectedRevision={s['revision']}", content=b"not a video", headers=H)
    assert r.status_code == 415 and r.json()["code"] == "unsupported_media"


def test_resume_reuses_latest_session(app_factory):
    c = new_client(app_factory(cat()))
    a = c.post("/api/sessions/resume", headers=H).json()["session"]
    b = c.post("/api/sessions/resume", headers=H).json()["session"]
    assert a["id"] == b["id"]
