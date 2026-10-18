"""Wardrobe evidence, style tags, confidence, and validated, debounced model interpretations."""

from datetime import datetime, timedelta, timezone

import pytest
from api.conftest import H, bootstrap, new_client, wait
from shopping.fakes import FakeCatalog, item

from app.style.interpret import apply_proposals, run_due, schedule
from app.style.service import build_profile
from app.style.tags import extract

ITEMS = [
    item("v1", "Vintage 90s Denim Trucker Jacket", 80, brand="Levis"),
    item("v2", "Vintage Washed Denim Jacket", 70, brand="Wrangler"),
    item("w1", "Carhartt Duck Canvas Chore Coat Jacket", 90, brand="Carhartt"),
    item("n1", "Non-vintage Reproduction Denim Jacket", 60, brand="Acme"),
]


@pytest.mark.parametrize("text,tags", [
    ("Vintage 90s Levi's trucker jacket", {"vintage"}), ("Not vintage, new with tags", set()),
    ("Non-vintage reproduction denim", set()), ("Carhartt duck canvas chore coat", {"workwear"}),
    ("Supreme box logo hoodie", set()), ("Minimalist leather tote", {"minimalist"}), ("Y2K rhinestone top", {"y2k"}),
])
def test_style_tags_come_only_from_stated_listing_words(text, tags):
    assert {t for t, _ in extract(text)} == tags


class FakeModel:
    model = "fake-gemma"

    def __init__(self, reply=None):
        self.calls = []
        self.reply = reply or (lambda req: {"proposals": []})

    def chat_json(self, system, user, schema, *, max_tokens=300):
        import json

        req = json.loads(user)
        self.calls.append(req)
        return self.reply(req), {"wallMs": 5, "promptTokens": 100, "completionTokens": 20}


@pytest.fixture
def wapp(app_factory, monkeypatch):
    def make(ranking=False, debounce="20", max_wait="120", items=None):
        monkeypatch.setenv("FEATURE_STYLE_MEMORY", "1")
        monkeypatch.setenv("STYLE_INTERPRET_DEBOUNCE_S", debounce)
        monkeypatch.setenv("STYLE_INTERPRET_MAX_WAIT_S", max_wait)
        if ranking:
            monkeypatch.setenv("STYLE_MODEL_RANKING", "1")
        its = items or ITEMS
        app = app_factory(FakeCatalog(its, {s["slug"]: {"sizes": ["M"], "carrying": 1} for s in its}))
        return new_client(app), app.state.clipcart
    return make


def _search(c, s):
    s = c.get(f"/api/sessions/{s['id']}").json()["session"]
    r = c.post(f"/api/sessions/{s['id']}/searches", headers=H, json={"expectedRevision": s["revision"]}).json()
    out = wait(lambda: c.get(f"/api/searches/{r['searchId']}").json(), lambda o: o["job"]["status"] not in ("queued", "running"))
    return {x["listing"]["title"]: x["recommendation"] for x in out["results"]}


def _ev(c, etype, rec):
    r = c.post("/api/style/events", headers=H, json={"type": etype, "recommendationId": rec["id"]})
    assert r.status_code == 201, r.text
    return r.json()["event"]


def _mems(c, status="active"):
    return c.get(f"/api/style/memories?status={status}").json()["memories"]


def test_saves_carry_listing_style_facts_and_two_saves_infer_a_style(wapp):
    c, _ = wapp()
    s, _, _ = bootstrap(c)
    recs = _search(c, s)
    e1 = _ev(c, "saved_item", recs["Vintage 90s Denim Trucker Jacket"])
    assert [f["tag"] for f in e1["item"]["styleFacts"]] == ["vintage"] and "Vintage 90s" in e1["item"]["styleFacts"][0]["excerpt"]
    assert not [m for m in _mems(c) if m["kind"] == "style_like"]  # one save is not enough
    _ev(c, "saved_item", recs["Vintage Washed Denim Jacket"])
    [m] = [m for m in _mems(c) if m["kind"] == "style_like"]
    assert m["value"] == "vintage" and m["origin"] == "inferred" and m["source"] == "saved_items"
    assert m["confidence"] == 0.6 and len(m["evidence"]) == 2 and m["lastEvidenceAt"]
    assert all(e["type"] == "saved_item" and "intage" in e["excerpt"] for e in m["evidence"])


WORK = [ITEMS[2], ITEMS[0]]  # the chore coat must be among the (size-limited) results


def test_a_purchase_counts_double_and_clicks_never_count(wapp):
    c, _ = wapp(items=WORK)
    s, _, _ = bootstrap(c)
    recs = _search(c, s)
    tok = recs["Carhartt Duck Canvas Chore Coat Jacket"]["links"][0]["token"]
    c.get(f"/go/{tok}", follow_redirects=False)
    c.get(f"/go/{tok}", follow_redirects=False)
    assert not [m for m in _mems(c) if m["kind"] == "style_like"]  # interest only
    _ev(c, "user_confirmed_purchase", recs["Carhartt Duck Canvas Chore Coat Jacket"])
    [m] = [m for m in _mems(c) if m["kind"] == "style_like"]
    assert m["value"] == "workwear" and m["confidence"] == 0.6


def test_negated_listing_words_never_infer_a_style(wapp):
    c, _ = wapp()
    s, _, _ = bootstrap(c)
    recs = _search(c, s)
    e = _ev(c, "user_confirmed_purchase", recs["Non-vintage Reproduction Denim Jacket"])
    assert e["item"]["styleFacts"] == [] and not [m for m in _mems(c) if m["kind"].startswith("style_")]


def test_stated_styles_are_editable_validated_and_rank_results(wapp):
    c, _ = wapp()
    s, _, _ = bootstrap(c)
    assert c.post("/api/style/memories", headers=H, json={"kind": "style_like", "value": "sparkly"}).status_code == 422
    r = c.post("/api/style/memories", headers=H, json={"kind": "style_like", "value": "Vintage", "source": "style_panel"})
    assert r.status_code == 201 and r.json()["memory"]["value"] == "vintage" and r.json()["memory"]["confidence"] == 1.0
    recs = _search(c, s)
    assert "You said you like vintage style" in recs["Vintage 90s Denim Trucker Jacket"]["personalization"]
    assert not recs["Non-vintage Reproduction Denim Jacket"]["personalization"]


# ---------------------------------------------------------------- model interpretations
def _setup_saves(wapp, reply, **kw):
    kw.setdefault("items", ITEMS)
    c, st = wapp(**kw)
    fake = FakeModel(reply)
    st.style_model = lambda: fake
    s, _, _ = bootstrap(c)
    recs = _search(c, s)
    return c, st, fake, s, recs


def _owner(st):
    return st.db.style_events.find_one({})["ownerId"]


def test_debounce_and_dedupe(wapp):
    c, st, fake, s, recs = _setup_saves(wapp, None)
    t0 = datetime.now(timezone.utc)
    ids = [_ev(c, "saved_item", recs[t])["id"] for t in ("Vintage 90s Denim Trucker Jacket", "Vintage Washed Denim Jacket")]
    owner = _owner(st)
    assert run_due(st, owner, now=t0 + timedelta(seconds=5))["status"] == "debouncing"
    out = run_due(st, owner, now=t0 + timedelta(seconds=60))
    assert out["status"] == "done" and len(fake.calls) == 1
    assert sorted(e["eventId"] for e in fake.calls[0]["events"]) == sorted(ids)
    for i in ids:  # the same evidence again: never sent twice
        schedule(st, owner, i, now=t0 + timedelta(seconds=61))
    assert run_due(st, owner, now=t0 + timedelta(seconds=200))["status"] == "duplicate" and len(fake.calls) == 1


def test_max_wait_caps_the_sliding_debounce(wapp):
    c, st, fake, s, recs = _setup_saves(wapp, None, debounce="20", max_wait="30")
    t0 = datetime.now(timezone.utc)
    e = _ev(c, "saved_item", recs["Vintage 90s Denim Trucker Jacket"])
    owner = _owner(st)
    for k in range(1, 6):  # keeps arriving every 10 s
        schedule(st, owner, e["id"], now=t0 + timedelta(seconds=10 * k))
    q = st.db.style_interpret_queue.find_one({"_id": owner})
    assert datetime.fromisoformat(q["notBefore"]) <= datetime.fromisoformat(q["firstAt"]) + timedelta(seconds=30)


def _props(req, *props):
    return {"proposals": list(props)}


def test_validation_regressions_action_negation_kind_quote_and_overrides(wapp):
    c, st, fake, s, recs = _setup_saves(wapp, None, items=[ITEMS[0], ITEMS[2], ITEMS[3]])
    saved = _ev(c, "saved_item", recs["Vintage 90s Denim Trucker Jacket"])
    rejected = _ev(c, "rejected_item", recs["Carhartt Duck Canvas Chore Coat Jacket"])
    nonv = _ev(c, "saved_item", recs["Non-vintage Reproduction Denim Jacket"])
    c.post("/api/style/memories", headers=H, json={"kind": "style_avoid", "value": "vintage", "source": "style_panel"})
    r = c.post("/api/style/memories", headers=H, json={"kind": "color_like", "value": "blue", "source": "style_panel"})
    c.delete(f"/api/style/memories/{r.json()['memory']['id']}", headers=H)  # removed: must never come back
    owner = _owner(st)
    events = {e["id"]: e for e in st.db.style_events.find({"ownerId": owner})}
    raw = _props(None,
        {"kind": "style_like", "value": "workwear", "evidenceEventIds": [rejected["id"]], "quote": "Duck Canvas Chore Coat", "confidence": 0.9},
        {"kind": "style_like", "value": "vintage", "evidenceEventIds": [nonv["id"]], "quote": "Non-vintage Reproduction", "confidence": 0.9},
        {"kind": "size", "value": "M", "evidenceEventIds": [saved["id"]], "quote": "Vintage 90s", "confidence": 0.9},
        {"kind": "brand_like", "value": "Levis", "evidenceEventIds": [saved["id"]], "quote": "Levis 501 heritage", "confidence": 0.9},
        {"kind": "style_avoid", "value": "vintage", "evidenceEventIds": [saved["id"]], "quote": "Vintage 90s", "confidence": 0.9},
        {"kind": "style_like", "value": "vintage", "evidenceEventIds": [saved["id"]], "quote": "Vintage 90s Denim", "confidence": 0.9},
        {"kind": "color_like", "value": "blue", "evidenceEventIds": ["sev_unknown"], "quote": "Denim", "confidence": 0.9},
        {"kind": "brand_like", "value": "Levis", "evidenceEventIds": [saved["id"]], "quote": "Brand: Levis", "confidence": 0.95},
    )
    applied, rejected_ = apply_proposals(st.db, owner, raw, events, now=datetime.now(timezone.utc))
    reasons = [x["reason"] for x in rejected_]
    assert any(r.startswith("action mismatch") for r in reasons)            # like from a rejection, avoid from a save
    assert sum(r.startswith("action mismatch") for r in reasons) == 2
    assert any("negates" in r or "does not state" in r for r in reasons)    # "Non-vintage" never means vintage
    assert any(r.startswith("kind not allowed") for r in reasons)           # size is never model territory
    assert any(r.startswith("quote is not copied") for r in reasons)        # invented quote
    assert "you already set this yourself" in reasons                        # stated avoid wins
    assert any(r.startswith("cites events") for r in reasons)
    assert applied == [{"kind": "brand_like", "value": "Levis", "confidence": 0.7, "evidenceEventIds": [saved["id"]]}]
    m = st.db.style_memories.find_one({"kind": "brand_like", "value": "Levis", "source": "model_interpretation"})
    assert m["origin"] == "inferred" and m["confidence"] == 0.7 and m["evidence"][0]["excerpt"] == "Brand: Levis"


def test_removed_values_are_never_reapplied(wapp):
    c, st, fake, s, recs = _setup_saves(wapp, None)
    saved = _ev(c, "saved_item", recs["Vintage 90s Denim Trucker Jacket"])
    r = c.post("/api/style/memories", headers=H, json={"kind": "brand_like", "value": "Levis", "source": "style_panel"})
    c.delete(f"/api/style/memories/{r.json()['memory']['id']}", headers=H)
    owner = _owner(st)
    events = {e["id"]: e for e in st.db.style_events.find({"ownerId": owner})}
    _, rej = apply_proposals(st.db, owner, _props(None, {"kind": "brand_like", "value": "Levis", "evidenceEventIds": [saved["id"]],
                                                          "quote": "Brand: Levis", "confidence": 0.5}), events, now=datetime.now(timezone.utc))
    assert rej[0]["reason"] == "you removed this"


def test_model_memories_do_not_rank_by_default_and_never_touch_hard_constraints(wapp):
    def reply(req):
        e = next(x for x in req["events"] if x["brand"] == "Levis")
        return {"proposals": [{"kind": "brand_like", "value": "Levis", "evidenceEventIds": [e["eventId"]], "quote": "Brand: Levis", "confidence": 0.6}]}

    for ranking in (False, True):
        c, st, fake, s, recs = _setup_saves(wapp, reply, ranking=ranking)
        prefs_before = c.get(f"/api/sessions/{s['id']}").json()["session"]["preferences"]
        _ev(c, "saved_item", recs["Vintage 90s Denim Trucker Jacket"])
        assert c.post("/api/style/interpretations/run", headers=H).json()["status"] == "done"
        owner = _owner(st)
        assert [e.value for e in build_profile(st.db, owner).brands_like] == ["Levis"]  # shown in the panel
        assert c.get(f"/api/sessions/{s['id']}").json()["session"]["preferences"] == prefs_before
        why = _search(c, s)["Vintage 90s Denim Trucker Jacket"]["personalization"]
        assert bool(any("Levis" in w for w in why)) is ranking


def test_deleting_the_evidence_prunes_model_memories(wapp):
    def reply(req):
        e = req["events"][0]
        return {"proposals": [{"kind": "brand_like", "value": "Levis", "evidenceEventIds": [e["eventId"]], "quote": "Brand: Levis", "confidence": 0.6}]}

    c, st, fake, s, recs = _setup_saves(wapp, reply)
    e = _ev(c, "saved_item", recs["Vintage 90s Denim Trucker Jacket"])
    c.post("/api/style/interpretations/run", headers=H)
    assert st.db.style_memories.find_one({"source": "model_interpretation"})
    assert c.delete(f"/api/style/events/{e['id']}", headers=H).status_code == 200
    assert not st.db.style_memories.find_one({"source": "model_interpretation"})


def test_model_unavailable_requeues_and_status_reports_waiting(wapp):
    from app.style.model import ModelUnavailable

    def boom(req):
        raise ModelUnavailable("offline")

    c, st, fake, s, recs = _setup_saves(wapp, boom)
    _ev(c, "saved_item", recs["Vintage 90s Denim Trucker Jacket"])
    assert c.post("/api/style/interpretations/run", headers=H).json()["status"] == "model_unavailable"
    owner = _owner(st)
    assert st.db.style_interpret_queue.find_one({"_id": owner})["pendingEventIds"]  # evidence kept for later
    assert not st.db.style_interpret_runs.find_one({"ownerId": owner})
    st.style_model = lambda: None
    info = c.get("/api/style/interpretations").json()
    assert info["status"] == "waiting_for_model" and info["rankingInfluence"] is False


def test_interpretations_response_is_the_generated_shape(wapp):
    from app.contracts import InterpretationRunResult, StyleInterpretations

    def reply(req):
        e = next(x for x in req["events"] if x["brand"] == "Levis")
        return {"proposals": [
            {"kind": "brand_like", "value": "Levis", "evidenceEventIds": [e["eventId"]], "quote": "Brand: Levis", "confidence": 0.6},
            {"kind": "size", "value": 42, "evidenceEventIds": [e["eventId"]], "quote": "x"},  # non-string value from a model
        ]}

    c, st, fake, s, recs = _setup_saves(wapp, reply)
    _ev(c, "saved_item", recs["Vintage 90s Denim Trucker Jacket"])
    ran = c.post("/api/style/interpretations/run", headers=H).json()
    InterpretationRunResult.model_validate(ran)
    assert ran["status"] == "done" and ran["applied"][0]["value"] == "Levis" and ran["rejected"][0]["value"] == "42"
    info = c.get("/api/style/interpretations").json()
    StyleInterpretations.model_validate(info)  # strict: unknown keys or shapes raise
    run = info["runs"][0]
    assert info["rankingInfluence"] is False and info["styleModel"]["mode"] in ("unavailable", "unverified", "live")
    assert run["status"] == "done" and run["usage"] == {"wallMs": 5, "promptTokens": 100, "completionTokens": 20}
    assert run["applied"] == [{"kind": "brand_like", "value": "Levis", "confidence": 0.6, "evidenceEventIds": run["evidenceEventIds"]}]
    # Runs stored before the typed contract could hold a raw model value; they still read back as strings.
    st.db.style_interpret_runs.update_one({"id": run["id"]}, {"$set": {"rejected": [{"kind": 7, "value": {"a": 1}, "reason": "old"}]}})
    old = c.get("/api/style/interpretations").json()["runs"][0]["rejected"][0]
    assert old == {"kind": "7", "value": "{'a': 1}", "reason": "old"}
