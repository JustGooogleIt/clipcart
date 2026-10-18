"""Search job lifecycle: persist before dispatch, claim atomically, run within
budget, and publish results only while the job is still the session's active search."""

from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
from datetime import datetime, timedelta, timezone

from pymongo.errors import DuplicateKeyError

from app.contracts import AgentEvent, Garment, GarmentObservation, Preferences, SearchBudget, SearchJob
from app.contracts.base import from_doc
from app.providers.grok.client import GrokClient
from app.sessions.service import new_id, now
from app.shopping.budget import BudgetLedger
from app.shopping.pipeline import run_search
from app.shopping.rules import GarmentProfile
from app.state import AppState

log = logging.getLogger("clipcart.search")
LEASE_S = 90


def build_profile(state: AppState, garment_doc: dict) -> GarmentProfile:
    g = from_doc(Garment, garment_doc)
    obs = [from_doc(GarmentObservation, d) for d in state.db.garment_observations.find({"id": {"$in": g.observation_ids}})]
    cat = garment_doc.get("category") or (obs[0].category if obs else "other")
    agg: dict[str, list[str]] = {"color": [], "pattern": [], "cut": [], "details": []}
    text: list[str] = []
    for o in obs:
        for k in agg:
            for v in o.observed_attributes.get(k, []):
                if v.lower() not in [x.lower() for x in agg[k]]:
                    agg[k].append(v)
        for t in o.visible_text:
            if t not in text:
                text.append(t)
    from app.shopping.rules import _COLOR_WORDS, words

    for w in words(g.user_description):
        if w in _COLOR_WORDS and w not in [c.lower() for c in agg["color"]]:
            agg["color"].insert(0, w)  # the shopper's own words win over model attributes
    # Open-vocab finds need the full descriptive line, not a truncated attribute bag.
    detail_limit = 10 if cat == "other" else 4
    return GarmentProfile(
        category=cat,
        colors=agg["color"][:4],
        pattern=agg["pattern"][:3],
        cut=agg["cut"][:5],
        details=agg["details"][:detail_limit],
        visible_text=text[:4],
        description=g.user_description,
        label=g.label,
    )


def create_search(state: AppState, session_doc: dict, garment_doc: dict, prefs: Preferences) -> SearchJob:
    s = state.settings
    payload = {"garment": garment_doc["id"], "prefs": prefs.wire(), "rev": session_doc["revision"]}
    job = SearchJob(
        id=new_id("srch"),
        session_id=session_doc["id"],
        owner_id=session_doc["ownerId"],
        session_revision=session_doc["revision"],
        input_hash=hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:32],
        status="queued",
        preference_snapshot=prefs,
        garment_id=garment_doc["id"],
        budget=SearchBudget(max_tool_calls=s.max_tool_calls, max_detail_calls=s.max_detail_calls),
        deadline_at=now() + timedelta(seconds=s.search_deadline_s),
        worker_mode="grok" if s.xai_key_present else "rule_based",
        catalog_mode=state.status["catalog"].mode,
        created_at=now(),
    )
    state.db.search_jobs.insert_one({"_id": job.id, "attempt": 0, "leaseOwner": None, "leaseExpiresAt": None, **job.wire()})
    return job


def dispatch(state: AppState, job_id: str) -> None:
    state.executor.submit(run_search_job, state, job_id)


class _Emitter:
    def __init__(self, state: AppState, job_id: str):
        self.state = state
        self.job_id = job_id
        self.seq = 0
        self.lock = threading.Lock()

    def __call__(self, stage: str, summary: str, *, worker: str = "system", tool_name: str | None = None,
                 elapsed_ms: int | None = None, evidence_ids: list[str] | None = None, result_ids: list[str] | None = None):
        with self.lock:
            self.seq += 1
            ev = AgentEvent(
                id=f"{self.job_id}:{self.seq}",
                job_id=self.job_id,
                sequence=self.seq,
                stage=stage,
                summary=summary[:200],
                tool_name=tool_name,
                worker=worker if worker in ("exact", "alternatives", "verifier", "system") else "system",
                elapsed_ms=elapsed_ms,
                evidence_ids=(evidence_ids or [])[:5],
                result_ids=(result_ids or [])[:5],
                at=now(),
            )
            try:
                self.state.db.agent_events.insert_one({"_id": ev.id, **ev.wire()})
            except DuplicateKeyError:
                pass


def _is_current(state: AppState, job_id: str, session_id: str) -> bool:
    job = state.db.search_jobs.find_one({"_id": job_id}, {"status": 1})
    if not job or job.get("status") not in ("running", "queued"):
        return False
    return state.db.sessions.find_one({"_id": session_id, "activeSearchId": job_id}, {"_id": 1}) is not None


def run_search_job(state: AppState, job_id: str) -> None:
    db = state.db
    lease_until = (datetime.now(timezone.utc) + timedelta(seconds=LEASE_S)).isoformat()
    job_doc = db.search_jobs.find_one_and_update(
        {"_id": job_id, "status": "queued", "attempt": {"$lt": 2}},
        {"$set": {"status": "running", "leaseOwner": "local-worker", "leaseExpiresAt": lease_until}, "$inc": {"attempt": 1}},
    )
    if not job_doc:
        return
    emit = _Emitter(state, job_id)
    job = from_doc(SearchJob, job_doc)
    try:
        _run(state, job, emit)
    except Exception as exc:  # noqa: BLE001
        log.exception("search job crashed")
        emit("failed", f"Search failed unexpectedly ({type(exc).__name__})")
        db.search_jobs.update_one(
            {"_id": job_id, "status": "running"},
            {"$set": {"status": "failed", "finishedAt": now().isoformat(),
                      "error": {"code": "internal_error", "message": type(exc).__name__, "retryable": True}}},
        )


def _run(state: AppState, job: SearchJob, emit: _Emitter) -> None:
    db = state.db
    if state.catalog is None:
        emit("failed", f"Catalog provider unavailable: {state.catalog_error}")
        db.search_jobs.update_one({"_id": job.id}, {"$set": {"status": "failed", "finishedAt": now().isoformat(),
            "error": {"code": "unavailable", "message": "Catalog provider unavailable", "retryable": True}}})
        return
    garment_doc = db.garments.find_one({"_id": job.garment_id, "ownerId": job.owner_id})
    if not garment_doc:
        raise RuntimeError("garment missing")
    profile = build_profile(state, garment_doc)
    deadline_mono = time.monotonic() + max(1.0, (job.deadline_at - now()).total_seconds())
    budget = job.budget.model_copy()
    ledger = BudgetLedger(budget, deadline_mono)
    s = state.settings
    factory = (lambda: GrokClient(model=s.xai_model, base_url=s.xai_base_url)) if s.xai_key_present else None

    outcome = run_search(
        search_id=job.id,
        garment_id=job.garment_id,
        profile=profile,
        prefs=job.preference_snapshot,
        provider=state.catalog,
        ledger=ledger,
        emit=emit,
        catalog_status=state.status["catalog"],
        grok_status=state.status["grok"],
        grok_client_factory=factory,
        is_current=lambda: _is_current(state, job.id, job.session_id),
    )
    budget_doc = budget.wire()
    if outcome.status == "superseded" or not _is_current(state, job.id, job.session_id):
        emit("superseded", "A newer search replaced this one; its results were not published")
        db.search_jobs.update_one({"_id": job.id}, {"$set": {"status": "superseded", "budget": budget_doc,
                                                             "finishedAt": now().isoformat(), "workerModes": outcome.worker_modes}})
        return

    for e in outcome.evidence:
        db.evidence.replace_one({"_id": e.id}, {"_id": e.id, **e.wire()}, upsert=True)
    for L in outcome.listings:
        db.listings.replace_one({"_id": L.id}, {"_id": L.id, **L.wire()}, upsert=True)
        db.offers.update_one(
            {"provider": L.provider, "providerListingId": L.provider_listing_id, "variantKey": L.variant_id or ""},
            {"$set": {"offerKey": L.offer_key, "latestListingId": L.id, "latestCheckedAt": L.checked_at.isoformat()}},
            upsert=True,
        )
    for r in outcome.recommendations:
        db.recommendations.replace_one({"_id": r.id}, {"_id": r.id, "ownerId": job.owner_id, "sessionId": job.session_id, **r.wire()}, upsert=True)
    expires = (now() + timedelta(days=7)).isoformat()
    for t in outcome.links:
        db.outbound_links.replace_one(
            {"_id": t.token},
            {"_id": t.token, "ownerId": job.owner_id, "sessionId": job.session_id, "recommendationId": t.recommendation_id,
             "listingId": t.listing_id, "url": t.url, "kind": t.kind, "createdAt": now().isoformat(), "expiresAt": expires},
            upsert=True,
        )
    primary_ids = [r.id for r in outcome.recommendations if r.section == "primary"]
    committed = db.sessions.update_one(
        {"_id": job.session_id, "activeSearchId": job.id},
        {"$set": {"lastPresentedResultIds": primary_ids, "updatedAt": now().isoformat()}},
    )
    if committed.matched_count == 0:
        emit("superseded", "A newer search replaced this one; its results were not published")
        db.search_jobs.update_one({"_id": job.id}, {"$set": {"status": "superseded", "budget": budget_doc,
                                                             "finishedAt": now().isoformat()}})
        return
    err = None
    if outcome.errors:
        e0 = outcome.errors[0]
        err = {"code": e0["code"], "message": e0.get("message", "")[:200], "retryable": True}
    final_stage = {"completed": "completed", "partial": "partial", "no_match": "no_match"}.get(outcome.status, "failed")
    emit(final_stage, outcome.summary, result_ids=primary_ids)
    db.search_jobs.update_one(
        {"_id": job.id, "status": "running"},
        {"$set": {"status": outcome.status, "resultIds": [r.id for r in outcome.recommendations], "budget": budget_doc,
                  "finishedAt": now().isoformat(), "summary": outcome.summary, "error": err,
                  "workerModes": outcome.worker_modes}},
    )


def recover_on_startup(state: AppState) -> dict:
    """Interrupted running jobs fail explicitly; queued jobs resume (SRS section 21)."""
    db = state.db
    failed = db.search_jobs.update_many(
        {"status": "running"},
        {"$set": {"status": "failed", "finishedAt": now().isoformat(),
                  "error": {"code": "interrupted", "message": "Server restarted during the search", "retryable": True}}},
    ).modified_count
    queued = [d["_id"] for d in db.search_jobs.find({"status": "queued"}, {"_id": 1})]
    for jid in queued:
        dispatch(state, jid)
    db.analysis_jobs.update_many({"status": {"$in": ["running", "queued"]}},
                                 {"$set": {"status": "failed", "message": "Server restarted during analysis; upload again"}})
    return {"failed": failed, "resumed": len(queued)}
