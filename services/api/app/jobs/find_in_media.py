"""Natural-language find-in-video: open-vocab detect + rich describe → tray item."""

from __future__ import annotations

import logging
import uuid

from app.contracts import FrameRef, Garment, GarmentObservation
from app.contracts.base import from_doc
from app.jobs.find_query import (
    compose_search_description,
    infer_category,
    normalize_find_query,
    query_too_vague,
)
from app.media.context import RequestContext
from app.media.geometry import iou
from app.sessions.service import new_id
from app.state import AppState

log = logging.getLogger("clipcart.find")

# Re-export for callers/tests that imported from this module.
__all__ = ["normalize_find_query", "run_find_in_media"]


def _existing_same_find(
    state: AppState, session_id: str, owner_id: str, obs: GarmentObservation
) -> dict | None:
    """Reuse a tray item that already covers roughly the same box (avoid duplicates)."""
    for g in state.db.garments.find({"sessionId": session_id, "ownerId": owner_id}):
        oids = g.get("observationIds") or []
        if not oids:
            continue
        od = state.db.garment_observations.find_one({"id": oids[0], "ownerId": owner_id})
        if not od:
            continue
        try:
            if od.get("frameAssetId") == obs.frame_asset_id and iou(tuple(od["box01"]), obs.box01) >= 0.55:
                return g
        except Exception:  # noqa: BLE001
            continue
    return None


def run_find_in_media(state: AppState, session_id: str, owner_id: str, text: str) -> dict:
    """Detect the requested object on current analysis frames and add it to the tray."""
    query = normalize_find_query(text)
    if len(query) < 2:
        return {
            "ok": False,
            "code": "empty_query",
            "reply": "Say what to find, e.g. find me the abstract painting on the wall.",
        }
    vague = query_too_vague(query)
    if vague:
        return {"ok": False, "code": "query_too_vague", "query": query, "reply": vague}

    sess = state.db.sessions.find_one({"_id": session_id, "ownerId": owner_id})
    if not sess or not sess.get("analysisId"):
        return {
            "ok": False,
            "code": "no_media",
            "reply": "Upload or scan a video first, then ask to find something in it.",
        }

    analysis = state.db.analysis_jobs.find_one({"_id": sess["analysisId"], "ownerId": owner_id})
    if not analysis:
        return {
            "ok": False,
            "code": "no_analysis",
            "reply": "Scan is still running or missing. Wait for frames, then try again.",
        }
    if analysis.get("status") in ("queued", "running"):
        return {
            "ok": False,
            "code": "analysis_running",
            "reply": "Still scanning frames. Wait a moment, then try Find again.",
        }

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
    # Prefer sharper frames first for find (already ranked for Shorts, but sort helps photos).
    frames = sorted(frames, key=lambda f: getattr(f, "sharpness", 0.0) or 0.0, reverse=True)
    ctx = RequestContext.with_timeout(owner_id, f"req_{uuid.uuid4().hex[:10]}", state.settings.analysis_deadline_s)
    try:
        result = provider.find_open_vocab(frames, query, ctx)
    except Exception as exc:  # noqa: BLE001
        log.exception("find_open_vocab failed")
        state.status["perceptron"].record(False, code="adapter_error", note=type(exc).__name__)
        return {
            "ok": False,
            "code": "find_failed",
            "reply": "Couldn't search the video for that. Try again or draw a box.",
        }

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
            "reply": (
                f"Couldn't find “{query}” in the scanned frames. "
                "Try naming a clearer visual detail, or draw a box on the frame."
            ),
        }

    obs = result.observations[0]
    details = list(obs.observed_attributes.get("details") or [])
    what = obs.raw_label or query
    prior_desc = details[0] if details else None
    search_desc = compose_search_description(query, what, prior_desc, details[1:])
    category = infer_category(query, what)

    existing = _existing_same_find(state, session_id, owner_id, obs)
    if existing:
        state.db.garment_observations.replace_one(
            {"_id": obs.id},
            {"_id": obs.id, "sessionId": session_id, "ownerId": owner_id, **obs.wire()},
            upsert=True,
        )
        state.db.garments.update_one(
            {"_id": existing["_id"]},
            {
                "$set": {
                    "userDescription": search_desc[:800],
                    "label": (what or existing.get("label") or query)[:80],
                    "category": category,
                    "representativeCropId": obs.crop_asset_id,
                    "observationIds": [obs.id],
                    "foundByQuery": query,
                }
            },
        )
        doc = state.db.garments.find_one({"_id": existing["_id"]})
        return {
            "ok": True,
            "query": query,
            "garment": {k: v for k, v in doc.items() if k != "_id"},
            "observation": obs.wire(),
            "searchDescription": search_desc,
            "reused": True,
            "reply": f"Updated “{(what or query)[:60]}” with a fuller description for search.",
            "detectionMode": mode,
        }

    state.db.garment_observations.replace_one(
        {"_id": obs.id},
        {"_id": obs.id, "sessionId": session_id, "ownerId": owner_id, **obs.wire()},
        upsert=True,
    )
    label = (what or query)[:80]
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
        "category": category,
        "manual": False,
        "foundByQuery": query,
        **g.wire(),
    }
    # wire() may set category from Garment model default — force inferred category.
    doc["category"] = category
    state.db.garments.insert_one(doc)
    return {
        "ok": True,
        "query": query,
        "garment": {k: v for k, v in doc.items() if k != "_id"},
        "observation": obs.wire(),
        "searchDescription": search_desc,
        "reused": False,
        "reply": f"Found “{label}”. Searching with a full description — not a short label.",
        "detectionMode": mode,
    }
