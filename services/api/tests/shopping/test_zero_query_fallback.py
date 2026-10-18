"""A plain jacket (no color, text, cut, pattern, details or description) must still be searched, and a search that
never reached the catalog must not be reported as "No listings found" (2026-10-18 regression)."""

from api.conftest import H, app_factory, jpeg_bytes, new_client, wait  # noqa: F401  (fixture)
from shopping.fakes import FakeCatalog, item

import app.shopping.workers as W
from app.contracts import Preferences
from app.shopping.rules import GarmentProfile

PLAIN = GarmentProfile(category="jacket")


def test_plain_jacket_gets_a_controlled_category_query_for_both_workers():
    assert W.rule_queries("exact", PLAIN, Preferences()) == ["jacket"]
    assert W.rule_queries("alternatives", PLAIN, Preferences()) == ["jacket"]
    # The shopper's own colour choice may narrow the alternatives query; nothing about the garment is invented.
    assert W.rule_queries("alternatives", PLAIN, Preferences(colors=["Black"])) == ["black jacket"]
    assert W.rule_queries("exact", PLAIN, Preferences(colors=["Black"])) == ["jacket"]


def test_richer_profiles_are_unchanged():
    rich = GarmentProfile(category="jacket", colors=["black"], details=["nylon bomber"])
    qs = W.rule_queries("exact", rich, Preferences())
    assert qs and all(len(q.split()) >= 2 for q in qs)


def _plain_jacket_session(c):
    s = c.post("/api/sessions", headers=H).json()["session"]
    s = c.post(f"/api/media/uploads?sessionId={s['id']}&expectedRevision={s['revision']}", content=jpeg_bytes(), headers=H).json()["session"]
    a = wait(lambda: c.get(f"/api/analysis/{s['analysisId']}").json(), lambda a: a["status"] not in ("queued", "running"))
    g = c.post(f"/api/sessions/{s['id']}/garments", headers=H, json={
        "frameAssetId": a["frames"][0]["assetId"], "box01": [0.2, 0.2, 0.8, 0.9], "category": "jacket"}).json()["garment"]
    s = c.get(f"/api/sessions/{s['id']}").json()["session"]
    return c.patch(f"/api/sessions/{s['id']}", headers=H, json={"expectedRevision": s["revision"], "selectedGarmentId": g["id"],
                                                                 "preferences": {"maxItemPriceMinor": 50000}}).json()["session"]


def _search(c, s):
    r = c.post(f"/api/sessions/{s['id']}/searches", headers=H, json={"expectedRevision": s["revision"]}).json()
    return wait(lambda: c.get(f"/api/searches/{r['searchId']}").json(), lambda o: o["job"]["status"] not in ("queued", "running"))


def test_plain_jacket_search_reaches_the_catalog_and_keeps_category_verification(app_factory):
    cat = FakeCatalog([item("a", "Black Bomber Jacket", 90), item("b", "Graphic Cotton T-Shirt", 20), item("c", "Denim Trucker Jacket", 120)])
    c = new_client(app_factory(cat))
    out = _search(c, _plain_jacket_session(c))
    assert any(kind == "search" for kind, _ in cat.calls)  # retrieval happened
    titles = [r["listing"]["title"] for r in out["results"]]
    assert "Graphic Cotton T-Shirt" not in titles and titles  # category gate still applies
    assert out["job"]["status"] in ("completed", "partial")


def test_catalog_searched_with_no_listings_says_so(app_factory):
    cat = FakeCatalog([])
    c = new_client(app_factory(cat))
    out = _search(c, _plain_jacket_session(c))
    assert cat.calls and out["job"]["status"] == "no_match"
    assert out["job"]["summary"].startswith("Catalog searched (")


def test_no_query_is_reported_as_no_search_not_no_listings(app_factory, monkeypatch):
    monkeypatch.setattr(W, "rule_queries", lambda role, profile, prefs: [])
    cat = FakeCatalog([item("a", "Black Bomber Jacket", 90)])
    c = new_client(app_factory(cat))
    out = _search(c, _plain_jacket_session(c))
    assert cat.calls == []
    job = out["job"]
    assert job["status"] == "failed" and "No listings found" not in (job["summary"] or "")
    assert job["summary"].startswith("No catalog search was run")


def test_deadline_before_any_call_is_reported(app_factory, monkeypatch):
    from app.shopping.budget import BudgetLedger

    monkeypatch.setattr(BudgetLedger, "remaining_s", lambda self: 0.0)
    cat = FakeCatalog([item("a", "Black Bomber Jacket", 90)])
    c = new_client(app_factory(cat))
    out = _search(c, _plain_jacket_session(c))
    assert cat.calls == [] and out["job"]["status"] == "failed"
    assert out["job"]["summary"] == "Search ran out of time before any catalog call"


def test_alternatives_with_a_shopper_colour_no_longer_crashes():
    # rule_queries used to assign a local named "words", so the alternatives branch's words(...) call raised
    # UnboundLocalError whenever the shopper set a colour: that worker then silently searched nothing.
    rich = GarmentProfile(category="jacket", details=["nylon bomber"])
    assert W.rule_queries("alternatives", rich, Preferences(colors=["Black"]))
