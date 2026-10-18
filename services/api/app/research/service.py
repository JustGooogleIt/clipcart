"""Research job lifecycle: create (idempotent) -> dispatch -> ingest once -> completed/failed/expired."""

from __future__ import annotations

import logging
from datetime import timedelta

from pydantic import ValidationError

from app.contracts import Preferences, ResearchJob, ResearchSubmission
from app.contracts.base import from_doc
from app.contracts.research import ResearchGarmentContext, StyleHints
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


def style_hints(state, owner: str) -> StyleHints | None:
    """Compact, soft hints from the style profile (only when style memory is on). Never hard constraints."""
    if not state.settings.feature_style_memory:
        return None
    from app.style.service import build_profile

    p = build_profile(state.db, owner)

    def vals(entries):
        return [str(e.value) for e in entries][:5]

    hints = StyleHints(colors_like=vals(p.colors_like), colors_avoid=vals(p.colors_avoid), brands_like=vals(p.brands_like),
                       brands_avoid=vals(p.brands_avoid), materials_avoid=vals(p.materials_avoid),
                       tones_like=vals(p.tones_like))
    return hints if any(hints.model_dump().values()) else None


def create_job(state, session_doc: dict, garment_doc: dict, prefs: Preferences) -> ResearchJob:
    s = state.settings
    provider = get_provider(s.research_provider, state)
    t = now()
    job = ResearchJob(
        id=new_id("rsj"), session_id=session_doc["_id"], provider=provider.name, mode=provider.mode, status="pending",
        garment=garment_context(state, garment_doc), preferences=prefs, created_at=t,
        expires_at=t + timedelta(seconds=s.research_job_ttl_s), style_hints=style_hints(state, session_doc["ownerId"]),
    )
    state.db.research_jobs.insert_one({"_id": job.id, "ownerId": session_doc["ownerId"], **job.wire()})
    src = provider.source  # the server decides the label; a submission can never claim to be catalog data
    result = provider.dispatch(job.wire(), lambda jid, payload: ingest_submission(state, jid, payload, source=src))
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


def ingest_submission(state, job_id: str, payload: dict, *, source: str = "agent",
                      allow: tuple[str, ...] = ("pending",)) -> tuple[bool, str]:
    """Accept results once, only while the job is in an allowed state (pending and unexpired by default)."""
    db = state.db
    doc = db.research_jobs.find_one({"_id": job_id})
    if not doc:
        return False, "unknown job"
    doc = expire_if_due(state, doc)
    if doc["status"] not in allow:
        return False, f"job is {doc['status']}"
    if source == "catalog" and payload.get("providerError"):  # server-built payload: the catalog itself failed
        _fail(state, job_id, str(payload["providerError"]), str(payload.get("notes") or "catalog research failed"), True)
        return False, "provider error"
    try:
        sub = ResearchSubmission.model_validate({"jobId": payload.get("jobId"), "products": [],
                                                 "notes": payload.get("notes")})
    except ValidationError:
        if source != "manual_import":  # a bad manual import is refused, never fatal to the job
            _fail(state, job_id, "invalid_submission", "submission envelope failed validation")
        return False, "invalid submission"
    if sub.job_id != job_id or not isinstance(payload.get("products"), list):
        if source != "manual_import":
            _fail(state, job_id, "invalid_submission", "job id mismatch or products missing")
        return False, "invalid submission"
    # Claim the job atomically so a duplicate delivery cannot ingest twice.
    claimed = db.research_jobs.find_one_and_update({"_id": job_id, "status": doc["status"]}, {"$set": {"status": "ingesting"}})
    if not claimed:
        return False, "already ingested"
    job = from_doc(ResearchJob, {**claimed, "status": "pending"})
    mode = "manual" if source == "manual_import" else job.mode
    products, rejected, targets = verify_submission(
        payload["products"], job_id=job_id, prefs=job.preferences, mode=mode, job_created_at=job.created_at,
        url_checker=state.research_url_checker, category=job.garment.category, source=source,
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
    update = {"status": "completed", "finishedAt": now().isoformat(), "products": [p.wire() for p in products],
              "rejected": [r.wire() for r in rejected], "agentNotes": sub.notes, "summary": summary}
    if source == "manual_import":
        update["resultSource"] = "manual_import"
        update["error"] = None  # a failed or expired bridge job can be completed by a labelled manual import
        update["summary"] = "Manually imported results. " + summary
    db.research_jobs.update_one({"_id": job_id}, {"$set": update})
    return True, "accepted"


def import_manual(state, job_id: str, owner: str, payload: dict) -> tuple[bool, str]:
    """Owner-imported results, labelled as such. Allowed while pending, or after a failed or expired bridge job."""
    doc = state.db.research_jobs.find_one({"_id": job_id, "ownerId": owner})
    if not doc:
        return False, "unknown job"
    payload = {**payload, "jobId": job_id}
    return ingest_submission(state, job_id, payload, source="manual_import", allow=("pending", "failed", "expired"))


def public_view(state, doc: dict) -> dict:
    doc = expire_if_due(state, doc)
    d = {k: v for k, v in doc.items() if k not in ("_id", "ownerId")}
    if d.get("status") == "ingesting":
        d["status"] = "pending"
    return ResearchJob.model_validate(d).wire()

