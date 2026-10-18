"""Grok Bot provider (dormant): dispatch, one-time callback token, validation, signed crop URLs. Simulated Bot only."""

import time
from datetime import datetime, timezone

import httpx
import pytest
from api.conftest import H, bootstrap, new_client
from shopping.fakes import FakeCatalog, item

from app.research import grokbot


class FakeWebhook:
    def __init__(self, status=200, fail=False):
        self.status, self.fail, self.calls = status, fail, []

    def post(self, url, json=None, headers=None, timeout=None, follow_redirects=None):
        self.calls.append({"url": url, "json": json, "headers": headers})
        if self.fail:
            raise httpx.ConnectError("down")
        return httpx.Response(self.status, request=httpx.Request("POST", url))


@pytest.fixture
def bot(app_factory, monkeypatch):
    def make(status=200, fail=False, configured=True):
        monkeypatch.setenv("FEATURE_AGENT_RESEARCH", "1")
        monkeypatch.setenv("RESEARCH_PROVIDER", "grok_bot")
        monkeypatch.setenv("RESEARCH_RESOLVE_DNS", "0")
        if configured:
            monkeypatch.setenv("GROK_BOT_WEBHOOK_URL", "https://bot.example-hooks.com/routine/abc")
            monkeypatch.setenv("GROK_BOT_WEBHOOK_KEY", "test-webhook-key")
            monkeypatch.setenv("CLIPCART_PUBLIC_BASE_URL", "https://tunnel-host.trycloudflare.com")
        hook = FakeWebhook(status, fail)
        monkeypatch.setattr(grokbot, "httpx", type("H", (), {"post": hook.post, "TransportError": httpx.TransportError}))
        app = app_factory(FakeCatalog([item("a", "Black Nylon Bomber Jacket", 70)]))
        return new_client(app), app.state.clipcart, hook
    return make


def _start(c):
    s, g, _ = bootstrap(c)
    return c.post(f"/api/sessions/{s['id']}/research-jobs", headers=H, json={}).json()


def _product(**kw):
    return {"retailer": "Shop", "productUrl": "https://shop-store.com/bomber", "title": "Black Nylon Bomber Jacket",
            "matchType": "similar", "observedPrice": {"amountMinor": 6500, "currency": "USD"}, "priceExcerpt": "$65.00",
            "observedAt": datetime.now(timezone.utc).isoformat(), **kw}


def test_dispatch_sends_context_and_a_one_time_token_but_never_secrets_or_asset_ids(bot):
    c, st, hook = bot()
    job = _start(c)["job"]
    assert job["provider"] == "grok_bot" and job["status"] == "pending" and "callbackTokenHash" not in job
    [call] = hook.calls
    assert call["headers"]["Authorization"] == "Bearer test-webhook-key"
    body = call["json"]
    assert body["callbackUrl"] == f"https://tunnel-host.trycloudflare.com/api/research-jobs/{job['id']}/results"
    assert body["callbackAuthorization"].startswith("Bearer ") and "cropAssetId" not in body["garment"]
    assert body["garment"]["cropUrl"].startswith("https://tunnel-host.trycloudflare.com/api/research-crops/")
    assert "products" in body["resultSchema"]["properties"] and "callbackUrl" in body["instructions"]
    stored = st.db.research_jobs.find_one({"_id": job["id"]})["callbackTokenHash"]
    assert stored == grokbot.token_hash(body["callbackAuthorization"][7:])  # only the hash is stored


def test_callback_round_trip_is_validated_labelled_and_single_use(bot):
    c, st, hook = bot()
    job = _start(c)["job"]
    auth = hook.calls[0]["json"]["callbackAuthorization"]
    url = f"/api/research-jobs/{job['id']}/results"
    assert c.post(url, json={"products": [_product()]}, headers={"Authorization": "Bearer wrong"}).status_code == 401
    r = c.post(url, json={"products": [_product(), _product(productUrl="http://insecure-store.com/x")], "notes": "2 found"},
               headers={"Authorization": auth})
    assert r.status_code == 202
    done = c.get(f"/api/research-jobs/{job['id']}").json()["job"]
    assert done["status"] == "completed" and done["mode"] == "live" and done["resultSource"] == "provider"
    [p] = [p for p in done["products"] if p["section"] != "excluded"]
    assert p["source"] == "agent" and p["price"]["amountMinor"] == 6500 and p["warnings"][0].startswith("Found by a research agent")
    assert any("not https" in x["reason"] for x in done["rejected"])
    assert c.post(url, json={"products": [_product()]}, headers={"Authorization": auth}).status_code == 401  # token consumed


def test_callback_after_expiry_and_oversized_bodies_are_refused(bot, monkeypatch):
    c, st, hook = bot()
    job = _start(c)["job"]
    auth = hook.calls[0]["json"]["callbackAuthorization"]
    url = f"/api/research-jobs/{job['id']}/results"
    big = {"products": [], "notes": "x" * (grokbot.MAX_CALLBACK_BYTES + 10)}
    assert c.post(url, json=big, headers={"Authorization": auth}).status_code == 413
    st.db.research_jobs.update_one({"_id": job["id"]}, {"$set": {"expiresAt": "2000-01-01T00:00:00+00:00"}})
    r = c.post(url, json={"products": [_product()]}, headers={"Authorization": auth})
    assert r.status_code == 409 and c.get(f"/api/research-jobs/{job['id']}").json()["job"]["status"] == "expired"


@pytest.mark.parametrize("status,fail,code", [(401, False, "webhook returned 401"), (200, True, "webhook unreachable")])
def test_dispatch_failures_fail_the_job_and_allow_manual_import(bot, status, fail, code):
    c, st, hook = bot(status=status, fail=fail)
    job = _start(c)["job"]
    assert job["status"] == "failed" and job["error"]["code"] == "dispatch_failed" and code in job["error"]["message"]
    assert len(hook.calls) == (2 if fail else 1)  # one retry on a network error only
    r = c.post(f"/api/research-jobs/{job['id']}/import", headers=H, json={"products": [_product()]})
    assert r.status_code == 200 and r.json()["job"]["resultSource"] == "manual_import"


def test_unconfigured_provider_is_refused(bot):
    c, st, hook = bot(configured=False)
    s, g, _ = bootstrap(c)
    r = c.post(f"/api/sessions/{s['id']}/research-jobs", headers=H, json={})
    assert r.status_code == 503 and "GROK_BOT_WEBHOOK_URL" in r.json()["message"] and not hook.calls


def test_signed_crop_urls_work_expire_and_reject_tampering(bot):
    c, st, hook = bot()
    _start(c)
    path = hook.calls[0]["json"]["garment"]["cropUrl"].split("trycloudflare.com")[1]
    other = new_client(c.app)  # no cookie needed: the signature is the authorization
    r = other.get(path)
    assert r.status_code == 200 and r.headers["content-type"] == "image/jpeg" and r.headers["cache-control"] == "no-store"
    tok = path.rsplit("/", 1)[1]
    assert other.get(path[:-len(tok)] + tok[:-2] + ("A" if tok[-2] != "A" else "B") + tok[-1]).status_code == 403
    secret = st.settings.research_url_secret
    asset, owner = grokbot.verify_crop(secret, tok)
    expired = grokbot.sign_crop(secret, asset, owner, time.time() - 1)
    assert other.get(f"/api/research-crops/{expired}").status_code == 410


def test_health_says_unverified_until_a_bot_job_completes_then_operational(bot):
    c, st, hook = bot()
    assert c.get("/api/health").json()["research"] == {"provider": "grok_bot", "mode": "live", "status": "unverified"}
    job = _start(c)["job"]
    token = hook.calls[0]["json"]["callbackAuthorization"]
    # A labelled manual import never counts as the provider working.
    st.db.research_jobs.insert_one({"_id": "rsj_manual", "provider": "grok_bot", "status": "completed", "resultSource": "manual_import"})
    assert c.get("/api/health").json()["research"]["status"] == "unverified"
    r = c.post(f"/api/research-jobs/{job['id']}/results", headers={"Authorization": token},
               json={"jobId": job["id"], "products": [_product()]})
    assert r.status_code == 202, r.text
    assert c.get("/api/health").json()["research"]["status"] == "operational"


def test_health_reports_grok_bot_unavailable_without_its_configuration(bot):
    c, st, hook = bot(configured=False)
    assert c.get("/api/health").json()["research"] == {"provider": "grok_bot", "mode": None, "status": "unavailable"}


import pytest as _pytest  # noqa: E402


@_pytest.mark.parametrize("notes", [
    "Closest match: " + "olive sport coat, notch lapel, flap pockets; " * 30,  # ~1300 chars: a real Bot wrote >500
    ["Opened 9 pages.", "Amazon blocked (403).", None, "Poshmark 404."],
    {"summary": "two retail, one resale", "blocked": ["ebay.com"]},
    12345,
])
def test_callback_with_overlong_or_non_string_notes_still_validates_products(bot, notes):
    """Regression (2026-10-18): a real Bot callback failed the whole job with "submission envelope failed validation"
    because only the free-text notes broke the envelope. Notes are normalised; products are still fully validated."""
    c, st, hook = bot()
    job = _start(c)["job"]
    token = hook.calls[0]["json"]["callbackAuthorization"]
    r = c.post(f"/api/research-jobs/{job['id']}/results", headers={"Authorization": token},
               json={"jobId": job["id"], "products": [_product(), _product(productUrl="ftp://bad-store.com/x")], "notes": notes})
    assert r.status_code == 202, r.text
    done = c.get(f"/api/research-jobs/{job['id']}").json()["job"]
    assert done["status"] == "completed" and done["resultSource"] == "provider"
    assert isinstance(done["agentNotes"], str) and 0 < len(done["agentNotes"]) <= 500
    assert len(done["products"]) == 1 and done["products"][0]["source"] == "agent"  # product validation unchanged
    assert any("product_url" in x["reason"] for x in done["rejected"])


def test_envelope_failure_names_the_field_and_auth_is_unchanged(bot):
    c, st, hook = bot()
    job = _start(c)["job"]
    token = hook.calls[0]["json"]["callbackAuthorization"]
    assert c.post(f"/api/research-jobs/{job['id']}/results", headers={"Authorization": "Bearer wrong"},
                  json={"jobId": job["id"], "products": []}).status_code == 401
    r = c.post(f"/api/research-jobs/{job['id']}/results", headers={"Authorization": token},
               json={"jobId": 42, "products": [_product()]})
    assert r.status_code == 422
    err = c.get(f"/api/research-jobs/{job['id']}").json()["job"]["error"]
    assert err["code"] == "invalid_submission" and "jobId" in err["message"] and "42" not in err["message"]
