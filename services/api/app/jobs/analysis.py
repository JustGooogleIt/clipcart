"""Media-analysis job: frames -> (Perceptron detections | detection unavailable) -> garments."""

from __future__ import annotations

import logging
import uuid

from app.contracts import AnalysisJob
from app.media.context import RequestContext
from app.media.grouping import GarmentGrouper
from app.sessions.service import new_id, now
from app.state import AppState

log = logging.getLogger("clipcart.analysis")
CATEGORIES = ["jacket", "top", "bag"]


def create_analysis(state: AppState, session_id: str, owner_id: str, media_id: str) -> AnalysisJob:
    _, detection_mode = state.perception_provider()
    job = AnalysisJob(
        id=new_id("anl"),
        session_id=session_id,
        owner_id=owner_id,
        media_id=media_id,
        status="queued",
        detection_mode=detection_mode,
        created_at=now(),
    )
    state.db.analysis_jobs.insert_one({"_id": job.id, **job.wire()})
    state.executor.submit(run_analysis, state, job.id)
    return job


def _finish(state: AppState, job_id: str, **fields) -> None:
    fields["finishedAt"] = now().isoformat()
    state.db.analysis_jobs.update_one({"_id": job_id}, {"$set": fields})


def run_analysis(state: AppState, job_id: str) -> None:
    db = state.db
    job = db.analysis_jobs.find_one_and_update({"_id": job_id, "status": "queued"}, {"$set": {"status": "running"}})
    if not job:
        return
    owner, media_id, session_id = job["ownerId"], job["mediaId"], job["sessionId"]
    provider, mode = state.perception_provider()
    # With paid live detection, sample only as many frames as we analyze, so every
    # shown frame has detections and spend stays bounded per upload.
    n_frames = state.settings.perception_max_frames if (provider is not None and mode != "fixture") else 12
    try:
        frames = state.media.extract_frames(media_id, owner, max_frames=n_frames)
        cuts = state.media.detect_shot_boundaries(media_id, owner)
    except Exception as exc:  # noqa: BLE001
        log.warning("frame extraction failed: %s", exc)
        _finish(state, job_id, status="failed", message=f"Could not read frames from this file ({getattr(exc, 'code', type(exc).__name__)})")
        return
    db.analysis_jobs.update_one(
        {"_id": job_id},
        {"$set": {"frameIds": [f.asset_id for f in frames], "shotBoundariesMs": cuts,
                  "frames": [f.wire() for f in frames]}},
    )
    if provider is None:
        _finish(
            state,
            job_id,
            status="detection_unavailable",
            detectionMode="unavailable",
            message="Automatic garment detection (Perceptron) is not configured. Draw a box around the garment you want.",
        )
        return
    ctx = RequestContext.with_timeout(owner, f"req_{uuid.uuid4().hex[:10]}", state.settings.analysis_deadline_s)
    try:
        result = provider.analyze(frames, CATEGORIES, ctx)
    except Exception as exc:  # noqa: BLE001 - adapter guard requested in PR #2 review
        log.exception("perception analyze crashed")
        state.status["perceptron"].record(False, code="adapter_error", note=type(exc).__name__)
        _finish(state, job_id, status="failed", message="Garment detection failed. Draw a box around the garment instead.")
        return
    if result.mode == "live":
        st = state.status["perceptron"]
        for r in result.requests:
            st.record(r.outcome != "error", trace_id=r.provider_request_id, code=r.error_code, note=r.purpose)
    obs = result.observations
    for o in obs:
        db.garment_observations.replace_one({"_id": o.id}, {"_id": o.id, "sessionId": session_id, "ownerId": owner, **o.wire()}, upsert=True)

    def quality(crop_id: str) -> float:
        try:
            c = state.media.get_crop(crop_id, owner)
            return c.sharpness * (c.width * c.height) ** 0.5
        except Exception:  # noqa: BLE001
            return 0.0

    garments = GarmentGrouper().group(obs, cuts, session_id=session_id, crop_quality=quality)
    for g in garments:
        db.garments.replace_one(
            {"_id": g.id},
            {"_id": g.id, "ownerId": owner, "analysisId": job_id, "category": _category(obs, g), **g.wire()},
            upsert=True,
        )
    status = {"ok": "completed", "partial": "partial", "failed": "failed"}[result.status]
    msg = None
    if status == "failed":
        codes = sorted({i.code for i in result.issues})
        msg = f"Garment detection failed ({', '.join(codes)}). Draw a box around the garment instead."
    elif not garments:
        msg = "No jackets, tops or bags were detected. Draw a box around the garment if one is visible."
    detection_mode = "fixture" if result.mode == "fixture" else state.status["perceptron"].mode
    _finish(
        state,
        job_id,
        status=status,
        detectionMode=detection_mode,
        garmentIds=[g.id for g in garments],
        issues=[i.wire() for i in result.issues][:20],
        message=msg,
        droppedDetections=result.dropped_detections,
    )


def _category(obs, g) -> str:
    for o in obs:
        if o.id in g.observation_ids:
            return o.category
    return "other"
