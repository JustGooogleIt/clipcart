"""Research job lifecycle: create (idempotent) -> dispatch -> ingest once -> completed/failed/expired."""

from __future__ import annotations

import logging
from datetime import timedelta

from pydantic import ValidationError

from app.contracts import Preferences, ResearchJob, ResearchSubmission
from app.contracts.base import from_doc
from app.contracts.research import ResearchGarmentContext
from app.sessions.service import new_id, now

from .providers import get_provider
from .verify import verify_submission

log = logging.getLogger("clipcart.research")


def garment_context(state, garment_doc: dict) -> ResearchGarmentContext:
    from app.jobs.search import build_profile

    prof = build_profile(state, garment_doc)
    ts = None
    if garment_doc.get("observationIds"):
        o = state.db.garment_observations.find_one({"id": garment_doc["observationIds"][0]}, {"timestampMs": 1})
        ts = (o or {}).get("timestampMs")
    return ResearchGarmentContext(
        garment_id=garment_doc["id"],
        garment_source="gemini_youtube" if garment_doc.get("source") == "gemini_youtube" else "media",
        category=prof.category, description=prof.description, colors=prof.colors, pattern=prof.pattern,
        cut=prof.cut, details=prof.details, visible_text=prof.visible_text, timestamp_ms=ts,
        crop_asset_id=garment_doc.get("representativeCropId"),
    )


def create_job(state, session_doc: dict, garment_doc: dict, prefs: Preferences) -> ResearchJob:
    s = state.settings
    provider = get_provider(s.research_provider)
    t = now()
    job = ResearchJob(
        id=new_id("rsj"), session_id=session_doc["_id"], provider=provider.name, mode=provider.mode, status="pending",
        garment=garment_context(state, garment_doc), preferences=prefs, created_at=t,
        expires_at=t + timedelta(seconds=s.research_job_ttl_s),
    )
    state.db.research_jobs.insert_one({"_id": job.id, "ownerId": session_doc["ownerId"], **job.wire()})
    result = provider.dispatch(job.wire(), lambda jid, payload: ingest_submission(state, jid, payload))
    if not result.accepted:
        _fail(state, job.id, "dispatch_failed", result.detail, result.retryable)
    return job


def _fail(state, job_id: str, code: str, message: str, retryable: bool = False) -> None:
    state.db.research_jobs.update_one(
        {"_id": job_id, "status": "pending"},
        {"$set": {"status": "failed", "finishedAt": now().isoformat(),
                  "error": {"code": code, "message": message[:200], "retryable": retryable}}},
    )


def expire_if_due(state, doc: dict) -> dict:
    if doc.get("status") == "pending" and doc.get("expiresAt", "") < now().isoformat():
        state.db.research_jobs.update_one({"_id": doc["_id"], "status": "pending"},
                                          {"$set": {"status": "expired", "finishedAt": now().isoformat(),
                                                    "summary": "No research results arrived before the job expired."}})
        doc = state.db.research_jobs.find_one({"_id": doc["_id"]})
    return doc


def ingest_submission(state, job_id: str, payload: dict) -> tuple[bool, str]:
    """Accept results once, only while the job is pending and unexpired. Returns (accepted, reason)."""
    db = state.db
    doc = db.research_jobs.find_one({"_id": job_id})
    if not doc:
        return False, "unknown job"
    doc = expire_if_due(state, doc)
    if doc["status"] != "pending":
        return False, f"job is {doc['status']}"
    try:
        sub = ResearchSubmission.model_validate({"jobId": payload.get("jobId"), "products": [],
                                                 "notes": payload.get("notes")})
    except ValidationError:
        _fail(state, job_id, "invalid_submission", "submission envelope failed validation")
        return False, "invalid submission"
    if sub.job_id != job_id or not isinstance(payload.get("products"), list):
        _fail(state, job_id, "invalid_submission", "job id mismatch or products missing")
        return False, "invalid submission"
    # Claim the job atomically so a duplicate delivery cannot ingest twice.
    claimed = db.research_jobs.find_one_and_update({"_id": job_id, "status": "pending"}, {"$set": {"status": "ingesting"}})
    if not claimed:
        return False, "already ingested"
    job = from_doc(ResearchJob, {**claimed, "status": "pending"})
    products, rejected, targets = verify_submission(
        payload["products"], job_id=job_id, prefs=job.preferences, mode=job.mode, job_created_at=job.created_at,
        url_checker=state.research_url_checker, category=job.garment.category,
    )
    expires = (now() + timedelta(days=7)).isoformat()
    for token, url, kind, pid in targets:
        db.outbound_links.replace_one({"_id": token}, {
            "_id": token, "ownerId": claimed["ownerId"], "sessionId": job.session_id, "recommendationId": pid,
            "listingId": pid, "url": url, "kind": kind, "createdAt": now().isoformat(), "expiresAt": expires,
        }, upsert=True)
    shown = [p for p in products if p.section != "excluded"]
    n_p = sum(1 for p in shown if p.section == "primary")
    summary = (f"{n_p} recommended, {len(shown) - n_p} need checking" if shown else "No usable products in the research results")
    if rejected:
        summary += f"; {len(rejected)} item(s) rejected"
    db.research_jobs.update_one({"_id": job_id}, {"$set": {
        "status": "completed", "finishedAt": now().isoformat(), "products": [p.wire() for p in products],
        "rejected": [r.wire() for r in rejected], "agentNotes": sub.notes, "summary": summary,
    }})
    return True, "accepted"


def public_view(state, doc: dict) -> dict:
    doc = expire_if_due(state, doc)
    d = {k: v for k, v in doc.items() if k not in ("_id", "ownerId")}
    if d.get("status") == "ingesting":
        d["status"] = "pending"
    return ResearchJob.model_validate(d).wire()

