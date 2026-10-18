"""Grok Bot research provider (dormant until the bridge probe passes: docs/grok-bot-bridge.md).

dispatch → POST the job context to the owner's routine webhook (Bearer key). The Bot researches and, when done,
POSTs ``ResearchSubmission`` JSON to ``callbackUrl`` with ``callbackAuthorization`` (a one-time per-job token;
only its SHA-256 is stored). The webhook response never carries results.

The crop is shared as a short-lived HMAC-signed URL (``/api/research-crops/{token}``), never a raw asset id.
Results go through the same validation as every submission (``service.ingest_submission`` → ``verify``).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from datetime import datetime
from typing import Any

import httpx

from .providers import DispatchResult

INSTRUCTIONS = (
    "Research where to buy the garment in body.garment (open body.garment.cropUrl to see it; the link expires) for "
    "the shopper constraints in body.preferences. body.styleHints are soft preferences, never requirements. Search "
    "several independent retailers and resale marketplaces, not just one aggregator. Only report product pages you "
    "actually opened. For each, copy what the page shows: retailer, productUrl, title, matchType (exact only if the "
    "page is clearly the same product, otherwise similar), observedPrice with priceExcerpt (the price text as shown), "
    "availability, variants with available true/false, condition, brand only with an evidence entry quoting the page, "
    "imageUrl, identifiers (GTIN/MPN/SKU) if shown, sellerKind, observedAt (UTC ISO time you saw it). At most 12 "
    "products. Never guess prices, sizes or authenticity. When finished, send exactly one HTTP POST to "
    "body.callbackUrl with header Authorization set to body.callbackAuthorization and a JSON body "
    "{\"jobId\": body.jobId, \"products\": [...], \"notes\": \"...\"} that matches body.resultSchema. Do nothing else."
)
MAX_CALLBACK_BYTES = 256 * 1024


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


# ---------------------------------------------------------------- signed crop URLs
def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def sign_crop(secret: str, asset_id: str, owner: str, expires_at: float) -> str:
    body = _b64(json.dumps({"a": asset_id, "o": owner, "e": int(expires_at)}, separators=(",", ":")).encode())
    sig = _b64(hmac.new(secret.encode(), body.encode(), hashlib.sha256).digest())
    return f"{body}.{sig}"


def verify_crop(secret: str, token: str, now: float | None = None) -> tuple[str, str] | str:
    """Return (asset_id, owner) or an error code: 'invalid' | 'expired'."""
    try:
        body, sig = token.split(".", 1)
        want = _b64(hmac.new(secret.encode(), body.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(sig, want):
            return "invalid"
        d = json.loads(_unb64(body))
    except (ValueError, json.JSONDecodeError):
        return "invalid"
    if (now or time.time()) > d["e"]:
        return "expired"
    return d["a"], d["o"]


# ---------------------------------------------------------------- provider
class GrokBotResearchProvider:
    name = "grok_bot"
    mode = "live"
    source = "agent"  # results are an agent's claims, validated and labelled like any agent submission

    def __init__(self, state: Any, http: Any = None):
        s = state.settings
        missing = [k for k, v in (("GROK_BOT_WEBHOOK_URL", s.grok_bot_webhook_url), ("GROK_BOT_WEBHOOK_KEY", s.grok_bot_webhook_key),
                                  ("CLIPCART_PUBLIC_BASE_URL", s.public_base_url)) if not v]
        if missing:
            raise ValueError(f"research provider 'grok_bot' needs {', '.join(missing)}")
        if not (s.grok_bot_webhook_url.startswith("https://") and s.public_base_url.startswith("https://")):
            raise ValueError("research provider 'grok_bot' needs https webhook and public base URLs")
        self.state, self.http = state, http or httpx

    def dispatch(self, job: dict, deliver: Any) -> DispatchResult:
        s, db = self.state.settings, self.state.db
        doc = db.research_jobs.find_one({"_id": job["id"]}) or {}
        token = secrets.token_urlsafe(32)
        db.research_jobs.update_one({"_id": job["id"]}, {"$set": {"callbackTokenHash": token_hash(token)}})
        garment = {k: v for k, v in job["garment"].items() if k != "cropAssetId"}
        if job["garment"].get("cropAssetId") and doc.get("ownerId"):
            exp = datetime.fromisoformat(job["expiresAt"]).timestamp()
            garment["cropUrl"] = f"{s.public_base_url}/api/research-crops/{sign_crop(s.research_url_secret, job['garment']['cropAssetId'], doc['ownerId'], exp)}"
        from app.contracts import ResearchSubmission

        payload = {
            "jobId": job["id"], "expiresAt": job["expiresAt"], "garment": garment, "preferences": job["preferences"],
            "styleHints": job.get("styleHints"), "instructions": INSTRUCTIONS,
            "callbackUrl": f"{s.public_base_url}/api/research-jobs/{job['id']}/results",
            "callbackAuthorization": f"Bearer {token}",
            "resultSchema": ResearchSubmission.model_json_schema(by_alias=True),
        }
        headers = {"Authorization": f"Bearer {s.grok_bot_webhook_key}", "Content-Type": "application/json"}
        for attempt in (1, 2):  # one retry on a network error only; never on an HTTP answer
            try:
                r = self.http.post(s.grok_bot_webhook_url, json=payload, headers=headers, timeout=8.0, follow_redirects=False)
                break
            except httpx.TransportError as exc:
                if attempt == 2:
                    return DispatchResult(False, f"webhook unreachable ({type(exc).__name__})", retryable=True)
        if r.status_code != 200:
            return DispatchResult(False, f"webhook returned {r.status_code}", retryable=r.status_code >= 500)
        return DispatchResult(True, "routine run started; waiting for the Bot's callback")
