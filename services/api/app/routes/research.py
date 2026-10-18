"""Shopping research job routes (FEATURE_AGENT_RESEARCH). Contract: docs/contracts/agent-research.md.

There is no external result-callback route: no research bridge is proven (docs/grok-bot-bridge.md).
Results reach jobs through a server-side provider (fixture, SoleScout fallback) or the owner's
clearly labelled manual import.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import Field

from app.contracts import Preferences
from app.research.service import create_job, import_manual, public_view
from app.sessions.service import ApiProblem, get_owned, idempotent

from .api import In
from .deps import current_owner, limiter, require_mutation_header, state_of

router = APIRouter()


class ResearchJobIn(In):
    idempotency_key: str | None = Field(default=None, max_length=100)


def _flag(request: Request):
    st = state_of(request)
    if not st.settings.feature_agent_research:
        raise ApiProblem(404, "feature_disabled", "Agent research is turned off")
    return st


@router.post("/api/sessions/{session_id}/research-jobs")
def start_research(session_id: str, body: ResearchJobIn, request: Request) -> dict:
    st = _flag(request)
    require_mutation_header(request)
    owner = current_owner(request)
    sess = get_owned(st.db, session_id, owner)
    replay, commit = idempotent(st.db, owner, f"research:{session_id}", body.idempotency_key,
                                {"garment": sess.get("selectedGarmentId"), "prefs": sess.get("preferences")})
    if replay is not None:
        return replay
    gid = sess.get("selectedGarmentId")
    if not gid:
        raise ApiProblem(422, "no_selection", "Select a garment first")
    garment = st.db.garments.find_one({"_id": gid, "ownerId": owner})
    if not garment:
        raise ApiProblem(404, "not_found", "Selected garment not found")
    limiter.check(owner, "research", 10)
    try:
        job = create_job(st, sess, garment, Preferences.model_validate(sess["preferences"]))
    except ValueError as exc:
        raise ApiProblem(503, "provider_not_available", str(exc)) from None
    st.bump("research_jobs")
    resp = {"job": public_view(st, st.db.research_jobs.find_one({"_id": job.id}))}
    commit(resp)
    return resp


@router.get("/api/research-jobs/{job_id}")
def get_research(job_id: str, request: Request) -> dict:
    st = _flag(request)
    owner = current_owner(request)
    doc = st.db.research_jobs.find_one({"_id": job_id, "ownerId": owner})
    if not doc:
        raise ApiProblem(404, "not_found", "Research job not found")
    return {"job": public_view(st, doc)}


class ManualImportIn(In):
    products: list[dict] = Field(max_length=20)
    notes: str | None = Field(default=None, max_length=500)


@router.post("/api/research-jobs/{job_id}/import")
def import_research(job_id: str, body: ManualImportIn, request: Request) -> dict:
    """Owner's manual import of research results (e.g. after a bridge failed). Products are labelled manual_import."""
    st = _flag(request)
    require_mutation_header(request)
    owner = current_owner(request)
    limiter.check(owner, "research_import", 10)
    if not st.db.research_jobs.find_one({"_id": job_id, "ownerId": owner}):
        raise ApiProblem(404, "not_found", "Research job not found")
    ok, reason = import_manual(st, job_id, owner, {"products": body.products, "notes": body.notes})
    if not ok:
        code = "already_completed" if reason in ("job is completed", "already ingested") else "invalid_import"
        raise ApiProblem(409 if code == "already_completed" else 422, code, f"Import not accepted: {reason}")
    return {"job": public_view(st, st.db.research_jobs.find_one({"_id": job_id}))}
