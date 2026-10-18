"""Shopping research job routes (FEATURE_AGENT_RESEARCH). Contract: docs/contracts/agent-research.md.

There is no external result-callback route yet: no research bridge is proven.
Results reach jobs only through a server-side provider (today, the labelled fixture).
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import Field

from app.contracts import Preferences
from app.research.service import create_job, public_view
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
