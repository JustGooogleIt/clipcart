"""YouTube analysis jobs: validate -> oEmbed probe -> Gemini -> validated garments.

Status meanings are documented on ``YouTubeAnalysis``. No video bytes are
fetched by ClipCart; Gemini reads the public URL itself.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any

from app.contracts import YouTubeAnalysis, YouTubeInterval
from app.providers.gemini.client import GeminiClient, GeminiError, parse_json_text
from app.providers.gemini.garments import SCHEMA, build_prompt, validate_garments
from app.sessions.service import new_id, now

from .oembed import probe
from .url import YouTubeRef

log = logging.getLogger("clipcart.youtube")
CACHE_TTL_S = 3600.0
_cache: dict[tuple, tuple[float, dict]] = {}
_cache_lock = threading.Lock()

MESSAGES = {
    "not_found": "YouTube says this video doesn't exist or was removed.",
    "private_or_restricted": "Gemini can't read this video. It only reads public videos; private, unlisted, "
    "age-restricted or region-locked videos fail.",
    "private_or_restricted_listed": "YouTube lists this video, but Gemini can't read it. Gemini only reads public "
    "videos; unlisted, age-restricted or region-locked videos fail.",
    "no_garments": "Gemini didn't find a clearly visible jacket, top or bag in this part of the video.",
}


def clear_cache() -> None:
    with _cache_lock:
        _cache.clear()


def create_analysis(state, session_id: str, owner_id: str, ref: YouTubeRef, interval: YouTubeInterval) -> YouTubeAnalysis:
    a = YouTubeAnalysis(
        id=new_id("yta"),
        session_id=session_id,
        status="queued",
        video_id=ref.video_id,
        canonical_url=ref.canonical_url,
        interval=interval,
        model=state.settings.gemini_model,
        created_at=now(),
    )
    state.db.youtube_analyses.insert_one({"_id": a.id, "ownerId": owner_id, **a.wire()})
    state.executor.submit(run_analysis, state, a.id)
    return a


def _finish(state, aid: str, **fields: Any) -> None:
    fields["finishedAt"] = now().isoformat()
    state.db.youtube_analyses.update_one({"_id": aid}, {"$set": fields})


def run_analysis(state, aid: str, *, client_factory=None, probe_fn=None) -> None:
    probe_fn = probe_fn or probe
    db = state.db
    doc = db.youtube_analyses.find_one_and_update({"_id": aid, "status": "queued"}, {"$set": {"status": "running"}})
    if not doc:
        return
    s = state.settings
    start_s, end_s = doc["interval"]["startS"], doc["interval"]["endS"]
    key = (doc["videoId"], start_s, end_s, s.gemini_model)
    with _cache_lock:
        hit = _cache.get(key)
    if hit and time.monotonic() - hit[0] < CACHE_TTL_S:
        _finish(state, aid, **hit[1], cached=True)
        return

    meta = probe_fn(doc["canonicalUrl"])
    base: dict[str, Any] = {"title": meta.title, "channel": meta.channel}
    if meta.state == "not_found":
        _finish(state, aid, **base, status="not_found", errorCode="not_found", message=MESSAGES["not_found"])
        return
    try:
        client = (client_factory or _default_client_factory(s))()
        reply = client.analyze_youtube(
            doc["canonicalUrl"], build_prompt(start_s, end_s), SCHEMA, start_s=start_s, end_s=end_s,
            fps=s.gemini_fps, max_output_tokens=s.gemini_max_output_tokens, timeout_s=s.gemini_timeout_s,
        )
    except GeminiError as exc:
        state.status["gemini"].record(False, trace_id=exc.request_id, code=exc.code, note=exc.message)
        if exc.code == "video_inaccessible":
            msg = MESSAGES["private_or_restricted_listed" if meta.state == "ok" else "private_or_restricted"]
            _finish(state, aid, **base, status="private_or_restricted", errorCode=exc.code, message=msg)
        else:
            _finish(state, aid, **base, status="provider_error", errorCode=exc.code,
                    message=f"Gemini couldn't analyze the video ({exc.code}). Try again, or upload a clip instead.")
        return
    state.status["gemini"].record(True, trace_id=reply.interaction_id, note=f"youtube {doc['videoId']}")
    try:
        garments, dropped = validate_garments(parse_json_text(reply.text), start_s=start_s, end_s=end_s,
                                              video_id=doc["videoId"])
    except (ValueError, TypeError) as exc:
        _finish(state, aid, **base, status="provider_error", errorCode="invalid_response",
                providerRequestId=reply.interaction_id, message=f"Gemini's answer couldn't be used ({str(exc)[:80]}).")
        return
    result = {
        **base,
        "status": "completed" if garments else "no_garments",
        "garments": [g.wire() for g in garments],
        "droppedItems": dropped,
        "providerRequestId": reply.interaction_id,
        "errorCode": None,
        "message": None if garments else MESSAGES["no_garments"],
    }
    with _cache_lock:
        _cache[key] = (time.monotonic(), result)
    _finish(state, aid, **result)


def _default_client_factory(s):
    return lambda: GeminiClient(model=s.gemini_model, base_url=s.gemini_base_url)


def public_view(doc: dict | None) -> dict | None:
    if not doc:
        return None
    return YouTubeAnalysis.model_validate({k: v for k, v in doc.items() if k not in ("_id", "ownerId")}).wire()
