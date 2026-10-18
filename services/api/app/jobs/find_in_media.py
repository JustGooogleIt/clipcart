"""Natural-language find-in-video: open-vocab detect + rich describe → tray item."""

from __future__ import annotations

import logging
import re
import uuid

from app.contracts import FrameRef, Garment, GarmentObservation
from app.contracts.base import from_doc
from app.media.context import RequestContext
from app.sessions.service import new_id, now
from app.state import AppState

log = logging.getLogger("clipcart.find")

_LEAD = re.compile(
    r"^\s*(?:please\s+)?(?:can you\s+|could you\s+)?"
    r"(?:find|look for|search for|show|get|locate)\s+"
    r"(?:me\s+)?(?:the|a|an|that|this)?\s*",
    re.IGNORECASE,
)


def normalize_find_query(text: str) -> str:
    """Keep the shopper's descriptive phrase; only strip the 'find me the' lead-in."""
    raw = " ".join((text or "").split())
    if not raw:
        return ""
    stripped = _LEAD.sub("", raw).strip(" .,!?:;")
    # Never collapse further — "green plant" is too short to search well.
    return stripped or raw


def run_find_in_media(state: AppState, session_id: str, owner_id: str, text: str) -> dict:
    """Detect the requested object on current analysis frames and add it to the tray.

    Returns dict with keys: query, garment, observation, reply, and optional error code fields.
    """
    query = normalize_find_query(text)
    if len(query) < 2:
        return {"ok": False, "code": "empty_query", "reply": "Say what to find, e.g. find me the abstract painting on the wall."}

    sess = state.db.sessions.find_one({"_id": session_id, "ownerId": owner_id})
    if not sess or not sess.get("analysisId"):
        return {"ok": False, "code": "no_media", "reply": "Upload or scan a video first, then ask to find something in it."}

    analysis = state.db.analysis_jobs.find_one({"_id": sess["analysisId"], "ownerId": owner_id})
    if not analysis:
        return {"ok": False, "code": "no_analysis", "reply": "Scan is still running or missing. Wait for frames, then try again."}

    frame_docs = analysis.get("frames") or []
    if not frame_docs:
        return {"ok": False, "code": "no_frames", "reply": "No frames are ready yet. Wait for the scan to finish."}

    provider, mode = state.perception_provider()
    if provider is None:
        return {
            "ok": False,
            "code": "perception_unavailable",
            "reply": "Automatic find needs Perceptron. Draw a box around the object instead.",
        }

    frames = [from_doc(FrameRef, f) for f in frame_docs]
    ctx = RequestContext.with_timeout(owner_id, f"req_{uuid.uuid4().hex[:10]}", state.settings.analysis_deadline_s)
    try:
        result = provider.find_open_vocab(frames, query, ctx)
    except Exception as exc:  # noqa: BLE001
        log.exception("find_open_vocab failed")
        state.status["perceptron"].record(False, code="adapter_error", note=type(exc).__name__)
        return {"ok": False, "code": "find_failed", "reply": "Couldn't search the video for that. Try again or draw a box."}

    if result.mode == "live":
        for r in result.requests:
            state.status["perceptron"].record(
                r.outcome != "error", trace_id=r.provider_request_id, code=r.error_code, note=r.purpose
            )

    if not result.observations:
        return {
            "ok": False,
            "code": "not_found",
            "query": query,
            "reply": f"Couldn't find “{query}” in the scanned frames. Try a more specific description, or draw a box.",
        }

    obs = result.observations[0]
    details = obs.observed_attributes.get("details") or []
    search_desc = details[0] if details else (obs.raw_label or query)
    # Prefer the dense search_description; fall back to shopper query + what.
    if len(search_desc.split()) < 4:
        bits = [search_desc, query]
        search_desc = " — ".join(dict.fromkeys(b for b in bits if b))[:800]

    state.db.garment_observations.replace_one(
        {"_id": obs.id},
        {"_id": obs.id, "sessionId": session_id, "ownerId": owner_id, **obs.wire()},
        upsert=True,
    )
    label = (obs.raw_label or query)[:80]
    g = Garment(
        id=new_id("gar"),
        session_id=session_id,
        observation_ids=[obs.id],
        representative_crop_id=obs.crop_asset_id,
        label=label,
        grouping_basis="single",
        user_description=search_desc[:800],
    )
    doc = {
        "_id": g.id,
        "ownerId": owner_id,
        "analysisId": sess["analysisId"],
        "category": "other",
        "manual": False,
        "foundByQuery": query,
        **g.wire(),
    }
    state.db.garments.insert_one(doc)
    return {
        "ok": True,
        "query": query,
        "garment": {k: v for k, v in doc.items() if k != "_id"},
        "observation": obs.wire(),
        "searchDescription": search_desc,
        "reply": f"Found “{label}”. Searching with a full description — not a short label.",
        "detectionMode": mode,
    }
