from datetime import timedelta

import pytest
from api.conftest import H, bootstrap, new_client, wait
from shopping.fakes import FakeCatalog, item

from app.research.service import ingest_submission
from app.research.urlsafety import check_url
from app.sessions.service import now


@pytest.fixture
def research_app(app_factory, monkeypatch):
    def make(flag=True):
        if flag:
            monkeypatch.setenv("FEATURE_AGENT_RESEARCH", "1")
        monkeypatch.setenv("RESEARCH_RESOLVE_DNS", "0")  # tests never touch DNS
        app = app_factory(FakeCatalog([item("a", "Black Nylon Bomber Jacket", 70)]))
        return new_client(app), app.state.clipcart
    return make


def start(c, s):
    return c.post(f"/api/sessions/{s['id']}/research-jobs", headers=H, json={"idempotencyKey": "r1"})


def test_flag_off(research_app):
    c, _ = research_app(flag=False)
    s = c.post("/api/sessions", headers=H).json()["session"]
    r = start(c, s)
    assert r.status_code == 404 and r.json()["code"] == "feature_disabled"


def test_requires_selected_garment(research_app):
    c, _ = research_app()
    s = c.post("/api/sessions", headers=H).json()["session"]
    assert start(c, s).json()["code"] == "no_selection"


def test_fixture_job_lifecycle_and_labels(research_app):
    c, st = research_app()
    s, g, _ = bootstrap(c)
    r = start(c, s)
    job = r.json()["job"]
    assert job["status"] == "pending" and job["mode"] == "fixture" and job["provider"] == "fixture"
    assert job["garment"]["category"] == "jacket" and job["garment"]["description"] == "black bomber"
    assert start(c, s).json()["job"]["id"] == job["id"]  # idempotent create
    done = wait(lambda: c.get(f"/api/research-jobs/{job['id']}").json()["job"], lambda j: j["status"] != "pending")
    assert done["status"] == "completed"
    shown = [p for p in done["products"] if p["section"] != "excluded"]
    # The garment is a jacket: the captured T-shirt is set aside by the category gate.
    assert {p["domain"] for p in shown} == {"solescout.ai"}
    assert all(p["mode"] == "fixture" and p["identityTier"] in ("likely", "similar") for p in done["products"])
    ss = shown[0]
    assert ss["price"] is None and ss["links"][0]["kind"] == "aggregator_product_page"
    reasons = [r["reason"] for r in done["rejected"]]
    assert len(reasons) == 4 and any(r.startswith("not a jacket") for r in reasons)
    go = c.get(f"/go/{ss['links'][0]['token']}", follow_redirects=False)
    assert go.status_code == 302 and go.headers["location"].startswith("https://solescout.ai/product/")
    # A second delivery for the same job is refused.
    assert ingest_submission(st, job["id"], {"jobId": job["id"], "products": []}) == (False, "job is completed")


def test_fixture_top_garment_keeps_store_offer_with_agent_observed_price(research_app):
    c, st = research_app()
    s, g, _ = bootstrap(c)
    c.patch(f"/api/garments/{g['id']}", headers=H, json={"category": "top"})
    sess = c.get(f"/api/sessions/{s['id']}").json()["session"]
    job = start(c, sess).json()["job"]
    done = wait(lambda: c.get(f"/api/research-jobs/{job['id']}").json()["job"], lambda j: j["status"] != "pending")
    ff = next(p for p in done["products"] if p["domain"] == "farfetch.com")
    assert ff["price"]["amountMinor"] == 7400 and ff["priceBasis"] == "agent_observed"
    assert ff["observedAt"].startswith("2026-10-17T21:17:33")  # capture time, not "now"
    go = c.get(f"/go/{ff['links'][0]['token']}", follow_redirects=False)
    assert go.status_code == 302 and go.headers["location"].startswith("https://www.farfetch.com/")


def test_expiry_and_late_delivery(research_app, monkeypatch):
    c, st = research_app()
    import app.research.providers as prov

    monkeypatch.setattr(prov.FixtureResearchProvider, "dispatch", lambda self, job, deliver: prov.DispatchResult(True, "held"))
    s, g, _ = bootstrap(c)
    job = start(c, s).json()["job"]
    st.db.research_jobs.update_one({"_id": job["id"]}, {"$set": {"expiresAt": (now() - timedelta(seconds=1)).isoformat()}})
    j = c.get(f"/api/research-jobs/{job['id']}").json()["job"]
    assert j["status"] == "expired" and j["products"] == []
    assert ingest_submission(st, job["id"], {"jobId": job["id"], "products": []}) == (False, "job is expired")


def test_dispatch_failure_marks_failed(research_app, monkeypatch):
    c, st = research_app()
    import app.research.providers as prov

    monkeypatch.setattr(prov.FixtureResearchProvider, "dispatch",
                        lambda self, job, deliver: prov.DispatchResult(False, "webhook returned 401"))
    s, g, _ = bootstrap(c)
    j = start(c, s).json()["job"]
    assert j["status"] == "failed" and j["error"]["code"] == "dispatch_failed"


def test_mismatched_job_id_rejected(research_app, monkeypatch):
    c, st = research_app()
    import app.research.providers as prov

    monkeypatch.setattr(prov.FixtureResearchProvider, "dispatch", lambda self, job, deliver: prov.DispatchResult(True, "held"))
    s, g, _ = bootstrap(c)
    job = start(c, s).json()["job"]
    assert ingest_submission(st, job["id"], {"jobId": "rsj_other", "products": []})[0] is False
    assert c.get(f"/api/research-jobs/{job['id']}").json()["job"]["status"] == "failed"


def test_ownership(research_app):
    c, st = research_app()
    s, g, _ = bootstrap(c)
    job = start(c, s).json()["job"]
    other = new_client(c.app)
    other.post("/api/sessions", headers=H)
    assert other.get(f"/api/research-jobs/{job['id']}").status_code == 404


def test_health_reports_research_mode(research_app):
    c, _ = research_app()
    h = c.get("/api/health").json()
    assert h["features"]["agentResearch"] is True and h["research"] == {"provider": "fixture", "mode": "fixture", "status": "unverified"}
    assert check_url  # imported for parity with live config
