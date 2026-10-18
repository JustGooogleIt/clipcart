"""Style memory routes (FEATURE_STYLE_MEMORY). Contract: docs/contracts/style-memory.md."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Request, Response
from pydantic import Field

from app.sessions.service import ApiProblem, idempotent
from app.style import service as svc
from app.style.model import propose

from .api import In
from .deps import current_owner, limiter, require_mutation_header, state_of

router = APIRouter()


class MemoryIn(In):
    kind: Literal["size", "fit", "budget_max", "color_like", "color_avoid", "material_like", "material_avoid",
                  "brand_like", "brand_avoid"]
    value: Any
    source: Literal["preferences_form", "style_note", "chat_refinement"] = "preferences_form"
    idempotency_key: str | None = Field(default=None, max_length=100)


class EventIn(In):
    type: str = Field(max_length=40)
    recommendation_id: str = Field(min_length=3, max_length=80)
    idempotency_key: str | None = Field(default=None, max_length=100)


class NoteIn(In):
    text: str = Field(min_length=2, max_length=500)


def _flag(request: Request):
    st = state_of(request)
    if not st.settings.feature_style_memory:
        raise ApiProblem(404, "feature_disabled", "Style memory is turned off")
    return st


def _model_info(st) -> dict:
    from .api import _style_model_info

    return {"mode": st.status["style_model"].mode, **_style_model_info(st.settings)}


@router.get("/api/style/profile")
def get_profile(request: Request) -> dict:
    st = _flag(request)
    owner = current_owner(request)
    return {"profile": svc.public_profile(svc.build_profile(st.db, owner)), "styleModel": _model_info(st)}


@router.get("/api/style/memories")
def get_memories(request: Request, status: str = "active") -> dict:
    st = _flag(request)
    owner = current_owner(request)
    if status not in ("active", "overridden", "removed", "all"):
        raise ApiProblem(422, "invalid_request", "status must be active, overridden, removed or all")
    return {"memories": svc.list_memories(st.db, owner, status)}


@router.post("/api/style/memories", status_code=201)
def post_memory(body: MemoryIn, request: Request, response: Response) -> dict:
    st = _flag(request)
    require_mutation_header(request)
    owner = current_owner(request)
    limiter.check(owner, "style", 120)
    replay, commit = idempotent(st.db, owner, "style:memory", body.idempotency_key, body.model_dump(mode="json"))
    if replay is not None:
        return replay
    mem, overridden = svc.add_stated_memory(st.db, owner, body.kind, body.value, body.source)
    svc.rebuild_inferred(st.db, owner)  # an inferred twin may now be overridden
    resp = {"memory": mem.wire(), "overridden": overridden}
    commit(resp)
    return resp


@router.delete("/api/style/memories/{memory_id}")
def delete_memory(memory_id: str, request: Request) -> dict:
    st = _flag(request)
    require_mutation_header(request)
    owner = current_owner(request)
    return {"memory": svc.remove_memory(st.db, owner, memory_id).wire()}


@router.get("/api/style/events")
def get_events(request: Request, limit: int = 50) -> dict:
    st = _flag(request)
    owner = current_owner(request)
    return {"events": svc.list_events(st.db, owner, limit)}


@router.post("/api/style/events", status_code=201)
def post_event(body: EventIn, request: Request) -> dict:
    st = _flag(request)
    require_mutation_header(request)
    owner = current_owner(request)
    limiter.check(owner, "style", 120)
    replay, commit = idempotent(st.db, owner, "style:event", body.idempotency_key, body.model_dump(mode="json"))
    if replay is not None:
        return replay
    ev, changes = svc.record_api_event(st.db, owner, body.type, body.recommendation_id)
    resp = {"event": ev.wire(), "inferredChanges": changes}
    commit(resp)
    return resp


@router.delete("/api/style/events/{event_id}")
def delete_event(event_id: str, request: Request) -> dict:
    st = _flag(request)
    require_mutation_header(request)
    owner = current_owner(request)
    return {"deleted": event_id, "inferredChanges": svc.delete_event(st.db, owner, event_id)}


@router.post("/api/style/notes")
def post_note(body: NoteIn, request: Request) -> dict:
    """Propose memory updates from text. Saves nothing."""
    st = _flag(request)
    require_mutation_header(request)
    owner = current_owner(request)
    limiter.check(owner, "style_note", 30)
    res = propose(body.text, st.style_model(), st.status["style_model"])
    info = _model_info(st)
    return {"mode": res.mode, "model": res.model, "hosting": info["hosting"] if res.mode == "model" else None,
            "provider": info["label"] if res.mode == "model" else "Rule-based parser",
            "proposals": [p.wire() for p in res.proposals], "rejectedProposals": res.rejected, "note": res.note,
            "usage": {k: v for k, v in res.timings.items() if k in ("promptTokens", "completionTokens", "wallMs")} or None}
