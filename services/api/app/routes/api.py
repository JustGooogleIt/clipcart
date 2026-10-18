"""Public JSON API (SRS section 15). Every session route checks ownership."""

from __future__ import annotations

import logging
import tempfile
from typing import Any

from fastapi import APIRouter, Request, Response
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, RedirectResponse
from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from app.contracts import Garment, GarmentObservation, PreferencePatch, Preferences
from app.contracts.base import from_doc
from app.jobs.analysis import create_analysis
from app.jobs.find_in_media import run_find_in_media
from app.jobs.find_query import normalize_find_query
from app.jobs.search import create_search, dispatch
from app.media.errors import AssetNotFoundError, MediaError
from app.media.youtube_cache import YoutubeCacheError, download_youtube, parse_video_id
from app.providers.perceptron.adapter import correct_observation, manual_observation
from app.sessions.service import (
    ApiProblem,
    cas_update,
    create_session,
    get_owned,
    idempotent,
    new_id,
    now,
    supersede_active_search,
    to_session,
)
from app.shopping.refine import apply_patch, parse_refinement
from app.storage.db import ping

from .deps import current_owner, ensure_owner, limiter, require_mutation_header, state_of

log = logging.getLogger("clipcart.api")
router = APIRouter()
STRIP = {"_id", "ownerId", "owner_id"}


def clean(doc: dict | None) -> dict | None:
    if doc is None:
        return None
    return {k: v for k, v in doc.items() if k not in STRIP}


class In(BaseModel):
    model_config = ConfigDict(extra="forbid", alias_generator=to_camel, populate_by_name=True, allow_inf_nan=False)


class SessionPatchIn(In):
    expected_revision: int
    idempotency_key: str | None = Field(default=None, max_length=100)
    selected_garment_id: str | None = None
    preferences: PreferencePatch | None = None


class ManualGarmentIn(In):
    frame_asset_id: str
    box01: tuple[float, float, float, float]
    category: str = Field(pattern="^(jacket|top|pants|bag)$")
    description: str | None = Field(default=None, max_length=200)


class GarmentPatchIn(In):
    box01: tuple[float, float, float, float] | None = None
    category: str | None = Field(default=None, pattern="^(jacket|top|pants|bag|other)$")
    description: str | None = Field(default=None, max_length=800)


class StartSearchIn(In):
    expected_revision: int
    idempotency_key: str | None = Field(default=None, max_length=100)


class MessageIn(In):
    text: str = Field(min_length=1, max_length=500)
    expected_revision: int
    idempotency_key: str | None = Field(default=None, max_length=100)


class FindInMediaIn(In):
    text: str = Field(min_length=2, max_length=400)
    expected_revision: int = Field(ge=1)
    idempotency_key: str | None = Field(default=None, max_length=100)
    start_search: bool = True


class YoutubeAnalyzeIn(In):
    youtube_url: str = Field(min_length=8, max_length=500)
    expected_revision: int = Field(ge=1)


# ------------------------------------------------------------------ system
def _style_model_info(s) -> dict:
    """Never claims local processing for a hosted model."""
    if not s.feature_style_memory:
        return {"provider": None, "model": s.style_model, "hosting": None, "label": None}
    if s.style_model_provider == "openai_compatible":
        return {"provider": "openai_compatible", "model": s.style_remote_model, "hosting": "remote",
                "label": s.style_remote_label}
    if s.style_model_provider == "ollama":
        return {"provider": "ollama", "model": s.style_model, "hosting": "local", "label": f"{s.style_model} via local Ollama"}
    return {"provider": "none", "model": None, "hosting": None, "label": "Rule-based parser only"}


@router.get("/api/health")
def health(request: Request) -> dict:
    st = state_of(request)
    s = st.settings
    return {
        "api": "ok",
        "database": {"mode": s.db_mode, "ok": ping(st.db),
                     "note": None if s.mongodb_uri else "In-process local store; not MongoDB Atlas"},
        "worker": {"mode": "in_process_threads", "maxConcurrency": 3},
        "providers": {
            "perceptron": {**st.status["perceptron"].snapshot(), "model": s.perceptron_model,
                           "setting": s.perception_provider},
            "grok": {**st.status["grok"].snapshot(), "model": s.xai_model},
            "catalog": {**st.status["catalog"].snapshot(), "provider": s.catalog_provider, "error": st.catalog_error},
            "styleModel": {**st.status["style_model"].snapshot(), **_style_model_info(s)},
        },
        "features": {
            "photon": s.feature_photon,
            "voice": s.feature_voice,
            "solana": s.feature_solana,
            "agentResearch": s.feature_agent_research,
            "youtubeDownload": s.feature_youtube_download,
            "styleMemory": s.feature_style_memory,
        },
        "youtube": {
            "enabled": s.feature_youtube_download,
            "allowedVideoCount": len(s.youtube_allowed_video_ids),
            "maxDurationS": 90,
        },
        "research": {"provider": s.research_provider if s.feature_agent_research else None,
                     "mode": ("fixture" if s.research_provider == "fixture" else "live") if s.feature_agent_research else None},
    }


@router.get("/api/diagnostics")
def diagnostics(request: Request) -> dict:
    st = state_of(request)
    db = st.db
    jobs = list(db.search_jobs.find({}, {"_id": 0, "id": 1, "status": 1, "workerMode": 1, "workerModes": 1, "budget": 1,
                                          "catalogMode": 1, "createdAt": 1, "finishedAt": 1, "summary": 1, "error": 1})
                .sort("createdAt", -1).limit(10))
    counts = {c: db[c].count_documents({}) for c in ("sessions", "search_jobs", "recommendations", "referrals", "analysis_jobs")}
    return {"health": health(request), "requestCounts": dict(st.counters), "recentSearches": jobs, "collections": counts}


# ------------------------------------------------------------------ sessions
def session_view(st, doc: dict) -> dict:
    db = st.db
    sess = to_session(doc)
    out: dict[str, Any] = {"session": sess.wire(), "media": None, "analysis": None, "garments": [], "observations": []}
    out["session"].pop("ownerId", None)
    if sess.media_id:
        try:
            m = st.media.get_media(sess.media_id, doc["ownerId"]).wire()
            for k in ("ownerId", "storageKey"):
                m.pop(k, None)
            out["media"] = m
        except MediaError:
            pass
    if sess.analysis_id:
        out["analysis"] = clean(db.analysis_jobs.find_one({"_id": sess.analysis_id, "ownerId": doc["ownerId"]}))
    garments = [clean(g) for g in db.garments.find({"sessionId": sess.id, "ownerId": doc["ownerId"]})]
    # Only garments for the current media analysis or manual ones on its frames.
    if sess.analysis_id:
        garments = [g for g in garments if g.get("analysisId") == sess.analysis_id]
    out["garments"] = garments
    obs_ids = [o for g in garments for o in g.get("observationIds", [])]
    out["observations"] = [clean(o) for o in db.garment_observations.find({"id": {"$in": obs_ids}})]
    for o in out["observations"]:
        o.pop("sessionId", None)
    if sess.active_search_id:
        out["activeSearch"] = clean(db.search_jobs.find_one({"_id": sess.active_search_id},
                                                             {"leaseOwner": 0, "leaseExpiresAt": 0}))
    return out


@router.post("/api/sessions")
def create(request: Request, response: Response) -> dict:
    require_mutation_header(request)
    owner = ensure_owner(request, response)
    limiter.check(owner, "session", 30)
    st = state_of(request)
    st.bump("sessions_created")
    s = create_session(st.db, owner)
    return session_view(st, st.db.sessions.find_one({"_id": s.id}))


@router.post("/api/sessions/resume")
def resume(request: Request, response: Response) -> dict:
    """Boot: the owner's most recent committed session, or a new one."""
    require_mutation_header(request)
    owner = ensure_owner(request, response)
    st = state_of(request)
    doc = st.db.sessions.find_one({"ownerId": owner}, sort=[("createdAt", -1)])
    if doc:
        return session_view(st, doc)
    limiter.check(owner, "session", 30)
    st.bump("sessions_created")
    s = create_session(st.db, owner)
    return session_view(st, st.db.sessions.find_one({"_id": s.id}))


@router.get("/api/sessions/latest")
def latest(request: Request) -> dict:
    owner = current_owner(request)
    st = state_of(request)
    doc = st.db.sessions.find_one({"ownerId": owner}, sort=[("createdAt", -1)])
    if not doc:
        raise ApiProblem(404, "not_found", "No session yet")
    return session_view(st, doc)


@router.get("/api/sessions/{session_id}")
def get_session(session_id: str, request: Request) -> dict:
    owner = current_owner(request)
    st = state_of(request)
    return session_view(st, get_owned(st.db, session_id, owner))


@router.patch("/api/sessions/{session_id}")
def patch_session(session_id: str, body: SessionPatchIn, request: Request) -> dict:
    require_mutation_header(request)
    owner = current_owner(request)
    st = state_of(request)
    payload = body.model_dump(mode="json")
    replay, commit = idempotent(st.db, owner, f"patch:{session_id}", body.idempotency_key, payload)
    if replay is not None:
        return replay
    before = get_owned(st.db, session_id, owner)
    if before["revision"] != body.expected_revision:
        raise ApiProblem(409, "stale_revision", "Session changed since you loaded it; refresh and retry", retryable=True)
    fields: dict[str, Any] = {}
    if "selected_garment_id" in body.model_fields_set:
        gid = body.selected_garment_id
        if gid is not None and not st.db.garments.find_one({"_id": gid, "ownerId": owner, "sessionId": session_id}):
            raise ApiProblem(404, "not_found", "Garment not found")
        fields["selectedGarmentId"] = gid
    if body.preferences is not None:
        current = Preferences.model_validate(before["preferences"])
        fields["preferences"] = apply_patch(current, body.preferences).wire()
    changed = any(before.get(k) != v for k, v in fields.items())
    if changed:
        fields["activeSearchId"] = None
    doc = cas_update(st.db, session_id, owner, body.expected_revision, fields)
    if changed:
        supersede_active_search(st.db, before)
    resp = session_view(st, doc)
    commit(resp)
    return resp


# ------------------------------------------------------------------ media
@router.post("/api/media/uploads")
async def upload(request: Request, sessionId: str, expectedRevision: int) -> dict:  # noqa: N803
    require_mutation_header(request)
    owner = current_owner(request)
    st = state_of(request)
    limiter.check(owner, "upload", 20)
    get_owned(st.db, sessionId, owner)
    cap = st.media.limits.max_video_bytes
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > cap:
        raise ApiProblem(413, "media_too_large", "File exceeds the 150 MB limit")
    spool = tempfile.SpooledTemporaryFile(max_size=8 * 1024 * 1024, dir=st.media.store.root)
    total = 0
    try:
        async for chunk in request.stream():
            total += len(chunk)
            if total > cap:
                raise ApiProblem(413, "media_too_large", "File exceeds the 150 MB limit")
            spool.write(chunk)
        spool.seek(0)
        try:
            asset = await run_in_threadpool(st.media.ingest, spool, owner)
        except MediaError as exc:
            raise ApiProblem(exc.http_status, exc.code, exc.message, exc.retryable) from None
    finally:
        spool.close()
    st.bump("uploads")
    before = get_owned(st.db, sessionId, owner)
    job = create_analysis(st, sessionId, owner, asset.id)
    doc = cas_update(
        st.db, sessionId, owner, expectedRevision,
        {"mediaId": asset.id, "analysisId": job.id, "selectedGarmentId": None, "activeSearchId": None,
         "lastPresentedResultIds": []},
    )
    supersede_active_search(st.db, before)
    return session_view(st, doc)


@router.post("/api/sessions/{session_id}/youtube-analyze")
async def youtube_analyze(session_id: str, body: YoutubeAnalyzeIn, request: Request) -> dict:
    """Temporary YouTube download → ingest as media → queue analysis.

    Off by default. When enabled, only ``YOUTUBE_ALLOWED_VIDEO_IDS`` are accepted
    (team-owned / permitted clips). Everyone else should upload a file.
    """
    require_mutation_header(request)
    owner = current_owner(request)
    st = state_of(request)
    if not st.settings.feature_youtube_download:
        raise ApiProblem(404, "feature_disabled", "YouTube clip analysis is turned off. Upload the clip instead.")
    get_owned(st.db, session_id, owner)
    try:
        vid = parse_video_id(body.youtube_url.strip())
    except YoutubeCacheError as exc:
        raise ApiProblem(400, exc.code, exc.message) from None
    if vid not in st.settings.youtube_allowed_video_ids:
        raise ApiProblem(
            403,
            "video_not_permitted",
            "This video isn't on the permitted list. Upload the clip from your device instead.",
        )
    limiter.check(owner, "youtube", 10)

    cache_dir = st.media.store.root / "youtube-cache"
    try:
        cached = await run_in_threadpool(download_youtube, cache_dir, body.youtube_url.strip())
    except YoutubeCacheError as exc:
        status = {
            "invalid_url": 400,
            "youtube_blocked": 422,
            "yt_dlp_missing": 503,
            "timeout": 504,
        }.get(exc.code, 502)
        raise ApiProblem(status, exc.code, exc.message, retryable=exc.code == "timeout") from None

    def _ingest_cached() -> Any:
        with cached.path.open("rb") as fh:
            return st.media.ingest(
                fh,
                owner,
                source_url=body.youtube_url.strip(),
                source_type="youtube_download",
            )

    try:
        asset = await run_in_threadpool(_ingest_cached)
    except MediaError as exc:
        raise ApiProblem(exc.http_status, exc.code, exc.message, exc.retryable) from None

    st.bump("youtube_analyzes")
    before = get_owned(st.db, session_id, owner)
    job = create_analysis(st, session_id, owner, asset.id)
    doc = cas_update(
        st.db,
        session_id,
        owner,
        body.expected_revision,
        {
            "mediaId": asset.id,
            "analysisId": job.id,
            "selectedGarmentId": None,
            "activeSearchId": None,
            "lastPresentedResultIds": [],
        },
    )
    supersede_active_search(st.db, before)
    view = session_view(st, doc)
    view["youtube"] = {
        "videoId": cached.video_id,
        "title": cached.title,
        "cacheHit": cached.cached,
        "source": "youtube_download_cache_autoscans",
    }
    view["warnings"] = [
        "Temporary YouTube download was used for analysis (TTL cache). This is not a tab-share or link-only flow.",
        "The whole clip is scanned locally; Perceptron runs only on the best ranked stills.",
    ]
    return view


@router.get("/api/media/{asset_id}")
def media_bytes(asset_id: str, request: Request):
    owner = current_owner(request)
    st = state_of(request)
    try:
        meta = st.media.store.meta(asset_id, owner)
        path = st.media.store.path(asset_id, owner)
    except AssetNotFoundError:
        raise ApiProblem(404, "not_found", "Media not found") from None
    mime = meta.get("mime") or (meta.get("asset") or {}).get("mime") or "application/octet-stream"
    return FileResponse(path, media_type=mime, headers={"Cache-Control": "private, max-age=3600"})


@router.get("/api/analysis/{analysis_id}")
def get_analysis(analysis_id: str, request: Request) -> dict:
    owner = current_owner(request)
    st = state_of(request)
    doc = st.db.analysis_jobs.find_one({"_id": analysis_id, "ownerId": owner})
    if not doc:
        raise ApiProblem(404, "not_found", "Analysis not found")
    return clean(doc)


# ------------------------------------------------------------------ garments
def _store_garment(st, owner: str, session_id: str, analysis_id: str | None, obs: GarmentObservation,
                   description: str | None) -> dict:
    st.db.garment_observations.replace_one({"_id": obs.id}, {"_id": obs.id, "sessionId": session_id, "ownerId": owner,
                                                               **obs.wire()}, upsert=True)
    g = Garment(
        id=new_id("gar"),
        session_id=session_id,
        observation_ids=[obs.id],
        representative_crop_id=obs.crop_asset_id,
        label=f"{obs.category} (your selection)",
        grouping_basis="single",
        user_description=(description or None),
    )
    doc = {"_id": g.id, "ownerId": owner, "analysisId": analysis_id, "category": obs.category, "manual": True, **g.wire()}
    st.db.garments.insert_one(doc)
    return clean(doc)


@router.post("/api/sessions/{session_id}/garments")
def add_manual_garment(session_id: str, body: ManualGarmentIn, request: Request) -> dict:
    require_mutation_header(request)
    owner = current_owner(request)
    st = state_of(request)
    sess = get_owned(st.db, session_id, owner)
    try:
        frame = st.media.get_frame(body.frame_asset_id, owner)
        if frame.media_id != sess.get("mediaId"):
            raise ApiProblem(422, "wrong_frame", "Frame does not belong to this session's media")
        obs = manual_observation(st.media, frame, body.box01, body.category, owner)
    except MediaError as exc:
        raise ApiProblem(exc.http_status, exc.code, exc.message) from None
    return {"garment": _store_garment(st, owner, session_id, sess.get("analysisId"), obs, body.description),
            "observation": clean(obs.wire())}


@router.patch("/api/garments/{garment_id}")
def patch_garment(garment_id: str, body: GarmentPatchIn, request: Request) -> dict:
    require_mutation_header(request)
    owner = current_owner(request)
    st = state_of(request)
    g = st.db.garments.find_one({"_id": garment_id, "ownerId": owner})
    if not g:
        raise ApiProblem(404, "not_found", "Garment not found")
    updates: dict[str, Any] = {}
    if body.box01 is not None or body.category is not None:
        od = st.db.garment_observations.find_one({"id": g["observationIds"][0], "ownerId": owner})
        if not od:
            raise ApiProblem(404, "not_found", "Observation not found")
        obs = from_doc(GarmentObservation, od)
        try:
            fixed = correct_observation(st.media, obs, owner, box01=body.box01, category=body.category)
        except MediaError as exc:
            raise ApiProblem(exc.http_status, exc.code, exc.message) from None
        st.db.garment_observations.replace_one({"_id": od["_id"]}, {"_id": od["_id"], "sessionId": od["sessionId"],
                                                                      "ownerId": owner, **fixed.wire()})
        updates.update({"representativeCropId": fixed.crop_asset_id, "category": fixed.category,
                        "label": f"{fixed.category} (edited)"})
    if "description" in body.model_fields_set:
        updates["userDescription"] = body.description or None
    if updates:
        st.db.garments.update_one({"_id": garment_id}, {"$set": updates})
        # Editing the selected garment invalidates any running search for it.
        sess = st.db.sessions.find_one({"_id": g["sessionId"], "ownerId": owner})
        if sess and sess.get("selectedGarmentId") == garment_id and sess.get("activeSearchId"):
            supersede_active_search(st.db, sess)
            st.db.sessions.update_one({"_id": sess["_id"]}, {"$set": {"activeSearchId": None}, "$inc": {"revision": 1}})
    return {"garment": clean(st.db.garments.find_one({"_id": garment_id}))}


# ------------------------------------------------------------------ searches
def _start_search(st, owner: str, session_id: str, expected_revision: int) -> dict:
    before = get_owned(st.db, session_id, owner)
    if before["revision"] != expected_revision:
        raise ApiProblem(409, "stale_revision", "Session changed since you loaded it; refresh and retry", retryable=True)
    gid = before.get("selectedGarmentId")
    if not gid:
        raise ApiProblem(422, "no_selection", "Select a garment first")
    garment = st.db.garments.find_one({"_id": gid, "ownerId": owner})
    if not garment:
        raise ApiProblem(404, "not_found", "Selected garment not found")
    limiter.check(owner, "search", 40)
    prefs = Preferences.model_validate(before["preferences"])
    job = create_search(st, {**before, "id": before["_id"]}, garment, prefs)
    try:
        doc = cas_update(st.db, session_id, owner, expected_revision, {"activeSearchId": job.id, "lastPresentedResultIds": []})
    except ApiProblem:
        st.db.search_jobs.update_one({"_id": job.id}, {"$set": {"status": "cancelled", "finishedAt": now().isoformat()}})
        raise
    supersede_active_search(st.db, before)
    st.bump("searches")
    dispatch(st, job.id)  # paid work starts only after job and session point at each other
    return {"searchId": job.id, **session_view(st, doc)}


@router.post("/api/sessions/{session_id}/searches")
def start_search(session_id: str, body: StartSearchIn, request: Request) -> dict:
    require_mutation_header(request)
    owner = current_owner(request)
    st = state_of(request)
    replay, commit = idempotent(st.db, owner, f"search:{session_id}", body.idempotency_key, body.model_dump(mode="json"))
    if replay is not None:
        return replay
    resp = _start_search(st, owner, session_id, body.expected_revision)
    commit(resp)
    return resp


@router.get("/api/searches/{search_id}")
def get_search(search_id: str, request: Request, afterSeq: int = 0) -> dict:  # noqa: N803
    owner = current_owner(request)
    st = state_of(request)
    job = st.db.search_jobs.find_one({"_id": search_id, "ownerId": owner}, {"leaseOwner": 0, "leaseExpiresAt": 0})
    if not job:
        raise ApiProblem(404, "not_found", "Search not found")
    events = [clean(e) for e in st.db.agent_events.find({"jobId": search_id, "sequence": {"$gt": afterSeq}}).sort("sequence", 1)]
    out: dict[str, Any] = {"job": clean(job), "events": events, "results": []}
    if job["status"] in ("completed", "partial", "no_match"):
        recs = [clean(r) for r in st.db.recommendations.find({"searchId": search_id, "ownerId": owner})]
        lids = [r["listingId"] for r in recs]
        listings = {d["id"]: clean(d) for d in st.db.listings.find({"id": {"$in": lids}})}
        ev_ids = {e for d in listings.values() for e in d.get("evidenceIds", [])}
        evidence = {d["id"]: clean(d) for d in st.db.evidence.find({"id": {"$in": list(ev_ids)}})}
        order = {"primary": 0, "needs_checking": 1, "original_over_budget": 2}
        recs.sort(key=lambda r: (order.get(r["section"], 9), r["rank"]))
        for r in recs:
            r.pop("sessionId", None)
            L = listings.get(r["listingId"])
            out["results"].append({"recommendation": r, "listing": L,
                                   "evidence": [evidence[e] for e in (L or {}).get("evidenceIds", []) if e in evidence]})
    return out


@router.post("/api/searches/{search_id}/cancel")
def cancel_search(search_id: str, request: Request) -> dict:
    require_mutation_header(request)
    owner = current_owner(request)
    st = state_of(request)
    job = st.db.search_jobs.find_one({"_id": search_id, "ownerId": owner})
    if not job:
        raise ApiProblem(404, "not_found", "Search not found")
    st.db.search_jobs.update_one({"_id": search_id, "status": {"$in": ["queued", "running"]}},
                                 {"$set": {"status": "cancelled", "finishedAt": now().isoformat()}})
    st.db.sessions.update_one({"_id": job["sessionId"], "activeSearchId": search_id}, {"$set": {"activeSearchId": None}})
    return {"status": st.db.search_jobs.find_one({"_id": search_id})["status"]}


def _apply_find_in_media(st, owner: str, session_id: str, before: dict, text: str, *, start_search: bool) -> dict:
    found = run_find_in_media(st, session_id, owner, text)
    if not found.get("ok"):
        code = found.get("code") or "find_failed"
        status = 404 if code in ("not_found", "no_media", "no_frames", "no_analysis") else 422
        if code == "perception_unavailable":
            status = 503
        if code == "analysis_running":
            status = 409
        raise ApiProblem(
            status,
            code,
            found.get("reply") or "Find failed",
            retryable=code in ("find_failed", "analysis_running"),
        )
    gid = found["garment"]["id"]
    supersede_active_search(st.db, before)
    doc = cas_update(
        st.db,
        session_id,
        owner,
        before["revision"],
        {"selectedGarmentId": gid, "activeSearchId": None},
    )
    resp: dict[str, Any] = {
        "applied": True,
        "find": {
            "query": found.get("query"),
            "searchDescription": found.get("searchDescription"),
            "garmentId": gid,
        },
        "reply": found.get("reply") or "Found it.",
        **session_view(st, doc),
    }
    if start_search:
        resp.update(_start_search(st, owner, session_id, doc["revision"]))
    return resp


# ------------------------------------------------------------------ find-in-video (open vocabulary)
@router.post("/api/sessions/{session_id}/find-in-media")
def find_in_media(session_id: str, body: FindInMediaIn, request: Request) -> dict:
    """Natural-language find: locate anything in the scanned frames, describe richly, search."""
    require_mutation_header(request)
    owner = current_owner(request)
    st = state_of(request)
    limiter.check(owner, "find_in_media", 20)
    replay, commit = idempotent(st.db, owner, f"find:{session_id}", body.idempotency_key, body.model_dump(mode="json"))
    if replay is not None:
        return replay
    before = get_owned(st.db, session_id, owner)
    if before["revision"] != body.expected_revision:
        raise ApiProblem(409, "stale_revision", "Session changed since you loaded it; refresh and retry", retryable=True)
    resp = _apply_find_in_media(st, owner, session_id, before, body.text, start_search=body.start_search)
    st.bump("find_in_media")
    commit(resp)
    return resp


# ------------------------------------------------------------------ refinement
@router.post("/api/sessions/{session_id}/messages")
def message(session_id: str, body: MessageIn, request: Request) -> dict:
    require_mutation_header(request)
    owner = current_owner(request)
    st = state_of(request)
    limiter.check(owner, "message", 60)
    replay, commit = idempotent(st.db, owner, f"msg:{session_id}", body.idempotency_key, body.model_dump(mode="json"))
    if replay is not None:
        return replay
    before = get_owned(st.db, session_id, owner)
    if before["revision"] != body.expected_revision:
        raise ApiProblem(409, "stale_revision", "Session changed since you loaded it; refresh and retry", retryable=True)
    # "find me the …" is find-in-video, not a preference refinement.
    lead = body.text.strip().lower()
    if lead.startswith(("find ", "find me", "look for", "search for", "show me the", "locate ")):
        if normalize_find_query(body.text):
            resp = _apply_find_in_media(st, owner, session_id, before, body.text, start_search=True)
            st.bump("find_in_media")
            commit(resp)
            return resp
    current = Preferences.model_validate(before["preferences"])
    interp = parse_refinement(body.text, current)
    if not interp.changes:
        resp = {"applied": False, "changes": [], "reply": interp.selection_hint
                or "I can find objects (“find me the plant by the window”) or change budget, size, color, materials, condition.",
                **session_view(st, before)}
        commit(resp)
        return resp
    new_prefs = apply_patch(current, interp.patch)
    doc = cas_update(st.db, session_id, owner, body.expected_revision,
                     {"preferences": new_prefs.wire(), "activeSearchId": None})
    supersede_active_search(st.db, before)
    resp: dict[str, Any] = {"applied": True, "changes": interp.changes, "reply": "Updated: " + "; ".join(interp.changes)}
    if doc.get("selectedGarmentId"):
        resp.update(_start_search(st, owner, session_id, doc["revision"]))
    else:
        resp.update(session_view(st, doc))
    commit(resp)
    return resp


# ------------------------------------------------------------------ outbound
@router.get("/go/{token}")
def go(token: str, request: Request):
    st = state_of(request)
    link = st.db.outbound_links.find_one({"_id": token}) if token.startswith("lk_") else None
    owner_tok = request.cookies.get("cc_owner")
    from .deps import owner_from_token

    if not link or not owner_tok or owner_from_token(owner_tok) != link["ownerId"]:
        raise ApiProblem(404, "not_found", "Link not found or expired")
    if link["expiresAt"] < now().isoformat():
        raise ApiProblem(410, "expired", "This link expired; run the search again")
    try:
        ref_id = new_id("ref")
        st.db.referrals.insert_one({
            "_id": ref_id, "id": ref_id, "sessionId": link["sessionId"], "recommendationId": link["recommendationId"],
            "listingId": link["listingId"], "linkToken": token, "outboundUrl": link["url"], "linkKind": link["kind"],
            "occurredAt": now().isoformat(), "affiliateConfigured": False, "conversionStatus": "unknown",
        })
        st.bump("outbound_clicks")
    except Exception:  # noqa: BLE001 - analytics must never block the shopper
        log.exception("referral logging failed")
    if st.settings.feature_style_memory:
        try:  # a click is interest only: never a purchase, never a memory
            from app.style.service import record_retailer_click

            record_retailer_click(st.db, link["ownerId"], link["listingId"], link.get("recommendationId"), link["kind"])
        except Exception:  # noqa: BLE001 - must never block the redirect
            log.exception("style click logging failed")
    return RedirectResponse(link["url"], status_code=302, headers={"Referrer-Policy": "no-referrer"})
