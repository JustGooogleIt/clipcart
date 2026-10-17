"""Public YouTube URL analysis routes (FEATURE_YOUTUBE_GEMINI). See docs/contracts/youtube-gemini.md."""

from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import Field

from app.contracts import YouTubeInterval
from app.sessions.service import ApiProblem, cas_update, get_owned, idempotent, new_id, supersede_active_search
from app.youtube.service import create_analysis, public_view
from app.youtube.url import YouTubeUrlError, parse_youtube_url

from .api import In, session_view
from .deps import current_owner, limiter, require_mutation_header, state_of

router = APIRouter()


class YouTubeAnalysisIn(In):
    url: str = Field(min_length=1, max_length=500)
    start_s: int | None = Field(default=None, ge=0)
    end_s: int | None = Field(default=None, gt=0)
    idempotency_key: str | None = Field(default=None, max_length=100)


class YouTubeSelectIn(In):
    expected_revision: int
    idempotency_key: str | None = Field(default=None, max_length=100)


def _require_flag(request: Request):
    st = state_of(request)
    if not st.settings.feature_youtube_gemini:
        raise ApiProblem(404, "feature_disabled", "YouTube link analysis is turned off")
    return st


@router.post("/api/sessions/{session_id}/youtube-analyses")
def start_youtube_analysis(session_id: str, body: YouTubeAnalysisIn, request: Request) -> dict:
    st = _require_flag(request)
    require_mutation_header(request)
    owner = current_owner(request)
    get_owned(st.db, session_id, owner)
    replay, commit = idempotent(st.db, owner, f"yt:{session_id}", body.idempotency_key, body.model_dump(mode="json"))
    if replay is not None:
        return replay
    try:
        ref = parse_youtube_url(body.url)
    except YouTubeUrlError as exc:
        raise ApiProblem(422 if exc.code == "unsupported_url" else 400, exc.code, exc.message) from None
    start = body.start_s or 0
    end = body.end_s if body.end_s is not None else start + st.settings.youtube_default_window_s
    try:
        interval = YouTubeInterval(start_s=start, end_s=end)
    except ValueError:
        raise ApiProblem(422, "invalid_interval", "Choose an interval of up to 10 minutes with end after start") from None
    if not st.settings.gemini_key_present:
        raise ApiProblem(503, "provider_not_configured", "YouTube analysis needs GEMINI_API_KEY on the server")
    limiter.check(owner, "youtube", 10)
    st.bump("youtube_analyses")
    a = create_analysis(st, session_id, owner, ref, interval)
    resp = {"analysis": a.wire()}
    commit(resp)
    return resp


@router.get("/api/youtube-analyses/{analysis_id}")
def get_youtube_analysis(analysis_id: str, request: Request) -> dict:
    st = _require_flag(request)
    owner = current_owner(request)
    doc = st.db.youtube_analyses.find_one({"_id": analysis_id, "ownerId": owner})
    if not doc:
        raise ApiProblem(404, "not_found", "Analysis not found")
    return {"analysis": public_view(doc)}


@router.post("/api/youtube-analyses/{analysis_id}/garments/{garment_id}/select")
def select_youtube_garment(analysis_id: str, garment_id: str, body: YouTubeSelectIn, request: Request) -> dict:
    """Turn one Gemini-described garment into the session's selected garment for catalog search."""
    st = _require_flag(request)
    require_mutation_header(request)
    owner = current_owner(request)
    doc = st.db.youtube_analyses.find_one({"_id": analysis_id, "ownerId": owner})
    if not doc:
        raise ApiProblem(404, "not_found", "Analysis not found")
    sid = doc["sessionId"]
    replay, commit = idempotent(st.db, owner, f"ytsel:{sid}", body.idempotency_key, {"a": analysis_id, "g": garment_id,
                                                                                         "r": body.expected_revision})
    if replay is not None:
        return replay
    yg = next((g for g in doc.get("garments") or [] if g.get("id") == garment_id), None)
    if not yg:
        raise ApiProblem(404, "not_found", "Garment not found in this analysis")
    before = get_owned(st.db, sid, owner)
    if before["revision"] != body.expected_revision:
        raise ApiProblem(409, "stale_revision", "Session changed since you loaded it; refresh and retry", retryable=True)
    gid = new_id("gar")
    label = f"{(yg.get('colors') or [''])[0]} {yg['category']}".strip()
    st.db.garments.insert_one({
        "_id": gid, "id": gid, "ownerId": owner, "sessionId": sid, "source": "gemini_youtube",
        "analysisId": analysis_id, "category": yg["category"], "label": label or yg["category"],
        "observationIds": [], "representativeCropId": None, "groupingBasis": "single",
        "userDescription": None,
        "youtube": {"analysisId": analysis_id, "garmentId": garment_id, "videoId": doc["videoId"],
                    "canonicalUrl": doc["canonicalUrl"], **{k: yg.get(k) for k in
                    ("description", "colors", "pattern", "visibleText", "personLabel", "timestamps")}},
    })
    sess = cas_update(st.db, sid, owner, body.expected_revision, {"selectedGarmentId": gid, "activeSearchId": None})
    supersede_active_search(st.db, before)
    resp = {"garmentId": gid, **session_view(st, sess)}
    commit(resp)
    return resp
