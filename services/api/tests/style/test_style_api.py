"""Style memory API: isolation, correction, deletion, click vs purchase, personalization."""

import pytest
from api.conftest import H, bootstrap, new_client, wait
from shopping.fakes import FakeCatalog, item

from app.style.service import record_verified_order

ITEMS = [
    item("a", "Black Nylon Bomber Jacket", 70, brand="Acme"),
    item("b", "Black Satin Bomber Jacket", 95, brand="Acme"),
    item("c", "Black Quilted Bomber Jacket", 90, brand="Nova"),
    item("e", "Orange Puffer Bomber Jacket", 80, brand="Zest"),
    item("d", "Black Padded Bomber Jacket", 400, brand="Luxe"),
]


@pytest.fixture
def style_app(app_factory, monkeypatch):
    def make(flag=True):
        if flag:
            monkeypatch.setenv("FEATURE_STYLE_MEMORY", "1")
        monkeypatch.setenv("OLLAMA_BASE_URL", "http://127.0.0.1:9")  # nothing listens: model unavailable
        monkeypatch.setenv("STYLE_MODEL_TIMEOUT_S", "1")
        app = app_factory(FakeCatalog(ITEMS, {s: {"sizes": ["M"], "hidden": 1, "carrying": 2} for s in "abcde"}))
        return new_client(app), app.state.clipcart
    return make


def search(c, s):
    s = c.get(f"/api/sessions/{s['id']}").json()["session"]
    r = c.post(f"/api/sessions/{s['id']}/searches", headers=H, json={"expectedRevision": s["revision"]}).json()
    out = wait(lambda: c.get(f"/api/searches/{r['searchId']}").json(), lambda o: o["job"]["status"] not in ("queued", "running"))
    return out, {x["listing"]["title"]: x["recommendation"] for x in out["results"]}


def ev(c, etype, rec_id):
    return c.post("/api/style/events", headers=H, json={"type": etype, "recommendationId": rec_id})


def mem(c, kind, value, source="preferences_form"):
    return c.post("/api/style/memories", headers=H, json={"kind": kind, "value": value, "source": source})


def active(c):
    return {(m["kind"], str(m["value"])): m for m in c.get("/api/style/memories").json()["memories"]}


def test_flag_off(style_app):
    c, _ = style_app(flag=False)
    c.post("/api/sessions", headers=H)
    assert c.get("/api/style/profile").json()["code"] == "feature_disabled"


def test_inferred_needs_repeated_evidence_and_stated_correction_overrides(style_app):
    c, _ = style_app()
    s, g, _ = bootstrap(c)
    _, recs = search(c, s)
    r = ev(c, "saved_item", recs["Black Nylon Bomber Jacket"]["id"]).json()
    assert r["event"]["item"]["brand"] == "Acme" and r["inferredChanges"]["added"] == []  # one save is not enough
    r = ev(c, "saved_item", recs["Black Satin Bomber Jacket"]["id"]).json()
    a = active(c)
    assert a[("color_like", "black")]["origin"] == "inferred" and a[("color_like", "black")]["evidenceCount"] == 2
    assert a[("brand_like", "Acme")]["source"] == "saved_items"
    # Explicit correction overrides the inference.
    inferred_id = a[("color_like", "black")]["id"]
    m = mem(c, "color_avoid", "black").json()
    assert m["memory"]["origin"] == "stated" and m["overridden"] == [inferred_id]
    a = active(c)
    assert ("color_like", "black") not in a and a[("color_avoid", "black")]["origin"] == "stated"
    over = c.get("/api/style/memories?status=overridden").json()["memories"]
    assert over[0]["kind"] == "color_like" and over[0]["overriddenBy"] == m["memory"]["id"]
    # Removing the stated correction lets the inference return.
    c.delete(f"/api/style/memories/{m['memory']['id']}", headers=H)
    assert active(c)[("color_like", "black")]["origin"] == "inferred"


def test_removed_memory_is_not_reinferred(style_app):
    c, _ = style_app()
    s, g, _ = bootstrap(c)
    _, recs = search(c, s)
    for t in ("Black Nylon Bomber Jacket", "Black Satin Bomber Jacket"):
        ev(c, "saved_item", recs[t]["id"])
    mid = active(c)[("color_like", "black")]["id"]
    assert c.delete(f"/api/style/memories/{mid}", headers=H).json()["memory"]["status"] == "removed"
    ev(c, "saved_item", recs["Black Padded Bomber Jacket"]["id"]) if "Black Padded Bomber Jacket" in recs else None
    assert ("color_like", "black") not in active(c)
    assert mem(c, "color_like", "black").status_code == 201  # re-stating is allowed


def test_latest_stated_wins_and_invalid_values(style_app):
    c, _ = style_app()
    c.post("/api/sessions", headers=H)
    m1 = mem(c, "size", "M").json()["memory"]
    m2 = mem(c, "size", {"raw": "L"}).json()
    assert m2["overridden"] == [m1["id"]] and c.get("/api/style/profile").json()["profile"]["size"]["value"]["raw"] == "L"
    for kind, val in [("color_like", "blurple"), ("budget_max", "-5"), ("fit", "athletic"), ("brand_like", "x")]:
        r = mem(c, kind, val)
        assert r.status_code == 422 and r.json()["code"] == "invalid_memory"


def test_click_is_never_a_purchase(style_app):
    c, st = style_app()
    s, g, _ = bootstrap(c)
    out, recs = search(c, s)
    tok = out["results"][0]["recommendation"]["links"][0]["token"]
    assert c.get(f"/go/{tok}", follow_redirects=False).status_code == 302
    events = c.get("/api/style/events").json()["events"]
    assert [e["type"] for e in events] == ["retailer_click"] and events[0]["origin"] == "inferred"
    prof = c.get("/api/style/profile").json()["profile"]
    assert prof["recentlyOwned"] == [] and c.get("/api/style/memories").json()["memories"] == []
    rid = out["results"][0]["recommendation"]["id"]
    for t in ("retailer_click", "verified_order", "purchase"):
        r = ev(c, t, rid)
        assert r.status_code == 422 and r.json()["code"] == "event_type_not_allowed"


def test_confirmed_purchase_and_verified_order(style_app):
    c, st = style_app()
    s, g, _ = bootstrap(c)
    _, recs = search(c, s)
    r = ev(c, "user_confirmed_purchase", recs["Black Quilted Bomber Jacket"]["id"]).json()
    assert r["event"]["origin"] == "stated"
    prof = c.get("/api/style/profile").json()["profile"]
    assert prof["recentlyOwned"][0]["source"] == "user_confirmed_purchase"
    assert prof["brandsLike"][0]["value"] == "Nova" and prof["brandsLike"][0]["origin"] == "inferred"
    assert prof["brandsLike"][0]["evidenceCount"] == 1  # one confirmed purchase is enough for a brand
    owner = st.db.sessions.find_one({"_id": s["id"]})["ownerId"]
    from app.contracts.style_memory import StyleItem

    item = StyleItem(title="ClipCart Demo Jacket", brand="ClipCart Demo")
    with pytest.raises(ValueError):
        record_verified_order(st.db, owner, {"id": "dmo_1", "ownerId": owner, "status": "awaiting_payment"}, item)
    with pytest.raises(ValueError):
        record_verified_order(st.db, owner, {"id": "dmo_1", "ownerId": "own_other", "status": "paid", "paymentSignature": "x"}, item)
    record_verified_order(st.db, owner, {"id": "dmo_1", "ownerId": owner, "status": "paid", "paymentSignature": "sig"}, item)
    owned = c.get("/api/style/profile").json()["profile"]["recentlyOwned"]
    assert owned[0]["source"] == "verified_order"


def test_delete_event_rederives(style_app):
    c, _ = style_app()
    s, g, _ = bootstrap(c)
    _, recs = search(c, s)
    e1 = ev(c, "saved_item", recs["Black Nylon Bomber Jacket"]["id"]).json()["event"]["id"]
    ev(c, "saved_item", recs["Black Satin Bomber Jacket"]["id"])
    assert ("color_like", "black") in active(c)
    r = c.delete(f"/api/style/events/{e1}", headers=H).json()
    assert r["inferredChanges"]["removed"] and ("color_like", "black") not in active(c)


def test_owner_isolation(style_app):
    c, st = style_app()
    s, g, _ = bootstrap(c)
    _, recs = search(c, s)
    e = ev(c, "saved_item", recs["Black Nylon Bomber Jacket"]["id"]).json()["event"]
    m = mem(c, "size", "M").json()["memory"]
    other = new_client(c.app)
    other.post("/api/sessions", headers=H)
    assert other.get("/api/style/memories?status=all").json()["memories"] == []
    assert other.get("/api/style/events").json()["events"] == []
    assert other.get("/api/style/profile").json()["profile"]["size"] is None
    assert other.delete(f"/api/style/memories/{m['id']}", headers=H).status_code == 404
    assert other.delete(f"/api/style/events/{e['id']}", headers=H).status_code == 404
    assert ev(other, "saved_item", recs["Black Satin Bomber Jacket"]["id"]).status_code == 404
    assert c.get("/api/style/profile").json()["profile"]["size"]["value"]["raw"] == "M"


def test_notes_fall_back_when_model_unavailable_and_save_nothing(style_app):
    c, _ = style_app()
    c.post("/api/sessions", headers=H)
    r = c.post("/api/style/notes", headers=H, json={"text": "I'm a medium and I hate orange"}).json()
    assert r["mode"] == "rule_based" and "unavailable" in r["note"]
    assert {p["kind"] for p in r["proposals"]} == {"size", "color_avoid"}
    assert c.get("/api/style/memories?status=all").json()["memories"] == []  # proposals are never saved
    h = c.get("/api/health").json()["providers"]["styleModel"]
    assert h["mode"] == "unverified" and h["failures"] >= 1


def test_personalization_is_soft_and_respects_hard_constraints(style_app):
    c, _ = style_app()
    s, g, _ = bootstrap(c)
    s = c.patch(f"/api/sessions/{s['id']}", headers=H, json={"expectedRevision": c.get(f"/api/sessions/{s['id']}").json()["session"]["revision"],
                                                              "preferences": {"maxItemPriceMinor": 15000}}).json()["session"]
    out, recs = search(c, s)
    assert "Black Padded Bomber Jacket" not in recs  # over budget
    ev(c, "rejected_item", recs["Black Nylon Bomber Jacket"]["id"])
    mem(c, "brand_like", "Luxe")  # stated like for an over-budget brand
    mem(c, "brand_like", "Nova")
    out2, recs2 = search(c, s)
    titles = [x["listing"]["title"] for x in out2["results"]]
    assert "Black Nylon Bomber Jacket" not in titles  # rejected item hidden
    assert "Black Padded Bomber Jacket" not in titles  # hard budget rule still wins over a stated like
    assert "Orange Puffer Bomber Jacket" not in titles  # the color mismatch gate still applies
    assert any("rejected" in e["summary"] for e in out2["events"])
    first = out2["results"][0]
    assert first["listing"]["brand"] == "Nova" and "You said you like Nova" in first["recommendation"]["personalization"]
    for r in out2["results"]:  # personalization never changes constraint checks or sections
        before = recs.get(r["listing"]["title"])
        if before:
            assert r["recommendation"]["constraintChecks"] == before["constraintChecks"]
            assert r["recommendation"]["section"] == before["section"]


def test_profile_wire_shape_matches_public_contract(style_app):
    from app.contracts import StyleProfileView

    c, _ = style_app()
    c.post("/api/sessions", headers=H)
    mem(c, "size", "M")
    prof = c.get("/api/style/profile").json()["profile"]
    StyleProfileView.model_validate(prof)  # extra="forbid": any internal field would fail here
    assert "rejectedProductKeys" not in prof and prof["rejectedOfferCount"] == 0
