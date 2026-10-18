"""Model interpretations of new style evidence (Gemma via Ollama or a hosted OpenAI-compatible endpoint).

The model proposes structured, soft profile updates from listing facts and the shopper's actions. Nothing is
trained: accepted proposals are stored as inferred memories with ``source: "model_interpretation"``.

Guarantees (contract: docs/contracts/style-memory.md, "Model interpretations"):
- debounced per owner (sliding window with a maximum wait) and deduplicated (same evidence + model never twice);
- only soft kinds (style/brand/color/tone); never size, ring size, fit or budget, never session preferences;
- every proposal is validated in code: vocabulary, cited events in the request, action consistency (likes only
  from saves/purchases, avoids only from rejections), verbatim quote from those listings, not negated in the
  quote, not removed by the shopper, no stated memory saying otherwise, not a duplicate of a deterministic one;
- they influence ranking only with STYLE_MODEL_RANKING=1 (search snapshots exclude them otherwise).
"""

from __future__ import annotations

import hashlib
import json
import logging
import threading
from datetime import datetime, timedelta, timezone
from typing import Any

from .model import ModelUnavailable
from .tags import STYLE_TAGS, extract
from .vocab import COLORS, PAIRS, TONES, InvalidMemory, colors_in, normalize, same_value

log = logging.getLogger("clipcart.style.interpret")

SOFT_KINDS = ("style_like", "style_avoid", "brand_like", "brand_avoid", "color_like", "color_avoid", "tone_like", "tone_avoid")
LIKE_EVENTS = {"saved_item", "user_confirmed_purchase", "verified_order"}
AVOID_EVENTS = {"rejected_item"}
INTERPRET_EVENTS = LIKE_EVENTS | AVOID_EVENTS
MODEL_CONFIDENCE_CAP = 0.7
_ACTION = {"saved_item": "saved", "rejected_item": "rejected", "user_confirmed_purchase": "bought",
           "verified_order": "verified_order"}

SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"proposals": {"type": "array", "maxItems": 8, "items": {
        "type": "object",
        "properties": {
            "kind": {"type": "string", "enum": list(SOFT_KINDS)},
            "value": {"type": "string"},
            "evidenceEventIds": {"type": "array", "items": {"type": "string"}, "maxItems": 5},
            "quote": {"type": "string"},
            "confidence": {"type": "number"},
        },
        "required": ["kind", "value", "evidenceEventIds", "quote", "confidence"],
    }}},
    "required": ["proposals"],
}
SYSTEM = (
    "You interpret a shopper's actions on product listings as soft style preferences. Actions: saved = interest "
    "only (not ownership); bought = the shopper says they own it; verified_order = bought through ClipCart; "
    "rejected = not for them. Propose only these kinds: " + ", ".join(SOFT_KINDS) + ". Likes only from saved, "
    "bought or verified_order events; avoids only from rejected events. value: for style_* one of "
    + ", ".join(STYLE_TAGS) + "; color_* one color word; tone_* one of " + ", ".join(TONES) + "; brand_* the brand "
    "exactly as written. quote: copy the exact words from that listing's text that support the value. "
    "evidenceEventIds: the eventId of each listing you used. Never propose size, fit, budget, or anything the "
    "listing words do not support. An empty list is fine."
)

_timers: dict[str, threading.Timer] = {}
_lock = threading.Lock()


def _utc(now: datetime | None) -> datetime:
    return now or datetime.now(timezone.utc)


def _iso(d: datetime) -> str:
    return d.isoformat()


# ---------------------------------------------------------------- debounce
def schedule(state, owner: str, event_id: str, *, now: datetime | None = None) -> dict:
    """Queue new evidence. The run waits for a quiet period (sliding), but never longer than the max wait."""
    db, s = state.db, state.settings
    t = _utc(now)
    doc = db.style_interpret_queue.find_one({"_id": owner})
    first = datetime.fromisoformat(doc["firstAt"]) if doc else t
    pending = list(dict.fromkeys([*(doc or {}).get("pendingEventIds", []), event_id]))
    not_before = min(t + timedelta(seconds=s.style_interpret_debounce_s), first + timedelta(seconds=s.style_interpret_max_wait_s))
    db.style_interpret_queue.replace_one({"_id": owner}, {"_id": owner, "ownerId": owner, "pendingEventIds": pending,
                                                          "firstAt": _iso(first), "notBefore": _iso(not_before)}, upsert=True)
    if state.style_model() is not None:
        _arm(state, owner, max(0.0, (not_before - t).total_seconds()) + 0.2)
    return {"pendingEvents": len(pending), "notBefore": _iso(not_before)}


def _arm(state, owner: str, delay_s: float) -> None:
    def fire():
        try:
            run_due(state, owner)
        except Exception:  # noqa: BLE001 - background: never crash the server
            log.exception("style interpretation failed")

    with _lock:
        old = _timers.pop(owner, None)
        if old:
            old.cancel()
        t = threading.Timer(delay_s, fire)
        t.daemon = True
        _timers[owner] = t
        t.start()


# ---------------------------------------------------------------- run
def run_due(state, owner: str, *, now: datetime | None = None, force: bool = False) -> dict:
    db = state.db
    t = _utc(now)
    doc = db.style_interpret_queue.find_one({"_id": owner})
    if not doc:
        return {"status": "idle"}
    if not force and datetime.fromisoformat(doc["notBefore"]) > t:
        return {"status": "debouncing", "pendingEvents": len(doc["pendingEventIds"])}
    model = state.style_model()
    if model is None:
        return {"status": "waiting_for_model", "pendingEvents": len(doc["pendingEventIds"])}
    claimed = db.style_interpret_queue.find_one_and_delete({"_id": owner, "notBefore": doc["notBefore"]})
    if not claimed:
        return {"status": "already_running"}
    ids = sorted(set(claimed["pendingEventIds"]))
    events = {e["id"]: e for e in db.style_events.find({"ownerId": owner, "id": {"$in": ids}})
              if e["type"] in INTERPRET_EVENTS}
    ids = sorted(events)
    if not ids:
        return {"status": "idle"}
    key = "sir_" + hashlib.sha256(f"{owner}|{model.model}|{'|'.join(ids)}".encode()).hexdigest()[:24]
    if db.style_interpret_runs.find_one({"_id": key}):
        return {"status": "duplicate", "runId": key}
    request = {"events": [_event_view(events[i]) for i in ids]}
    run = {"_id": key, "id": key, "ownerId": owner, "at": _iso(t), "model": model.model, "evidenceEventIds": ids,
           "applied": [], "rejected": [], "status": "running"}
    db.style_interpret_runs.insert_one(run)
    try:
        raw, timings = model.chat_json(SYSTEM, json.dumps(request), SCHEMA, max_tokens=400)
    except ModelUnavailable as exc:
        log.warning("style model unavailable for interpretation: %s", str(exc)[:200])
        db.style_interpret_runs.delete_one({"_id": key})  # not a completed run: allow a retry with the same evidence
        for i in ids:  # put the evidence back
            schedule(state, owner, i, now=t)
        return {"status": "model_unavailable"}
    applied, rejected = apply_proposals(db, owner, raw, events, now=t)
    db.style_interpret_runs.update_one({"_id": key}, {"$set": {"status": "done", "applied": applied, "rejected": rejected,
                                                               "usage": {k: timings.get(k) for k in ("promptTokens", "completionTokens", "wallMs")}}})
    return {"status": "done", "runId": key, "applied": applied, "rejected": rejected}


def _event_view(e: dict) -> dict:
    it = e.get("item") or {}
    return {"eventId": e["id"], "action": _ACTION[e["type"]], "title": it.get("title"), "brand": it.get("brand"),
            "condition": it.get("condition"), "category": it.get("category"),
            "styleFacts": [f.get("excerpt") for f in it.get("styleFacts") or []]}


def _event_text(e: dict) -> str:
    it = e.get("item") or {}
    parts = [it.get("title"), f"Brand: {it['brand']}" if it.get("brand") else None, it.get("condition"),
             *[f.get("excerpt") for f in it.get("styleFacts") or []]]
    return " ".join(" ".join(str(p).split()) for p in parts if p)


def _supports(kind: str, value: str, quote: str) -> bool:
    """The value must be stated, not negated, in the quote itself."""
    if kind.startswith("style_"):
        return value in {t for t, _ in extract(quote)}
    if kind.startswith("color_"):
        return value in colors_in(quote) and not _negated(value, quote)
    if kind.startswith("tone_"):
        base = value.replace("-tone", "").replace("-", " ")
        return base in quote.lower().replace("-", " ") and not _negated(base, quote)
    return value.lower() in quote.lower() and not _negated(value, quote)


def _negated(word: str, text: str) -> bool:
    import re

    return bool(re.search(rf"\b(?:not|non|no|without|never)[-\s]+(?:\w+[-\s]+)?{re.escape(word.lower())}\b", text.lower()))


def apply_proposals(db, owner: str, raw: Any, events: dict[str, dict], *, now: datetime) -> tuple[list[dict], list[dict]]:
    applied: list[dict] = []
    rejected: list[dict] = []
    props = raw.get("proposals") if isinstance(raw, dict) else None
    if not isinstance(props, list):
        return [], [{"kind": None, "value": None, "reason": "model output is not {proposals: [...]}"}]
    memories = list(db.style_memories.find({"ownerId": owner}))
    removed = {(d["kind"], str(d["value"]).lower()) for d in memories if d["status"] == "removed"}
    stated = [d for d in memories if d["origin"] == "stated" and d["status"] == "active"]
    deterministic = {(d["kind"], str(d["value"]).lower()) for d in memories
                     if d["origin"] == "inferred" and d.get("source") != "model_interpretation" and d["status"] == "active"}
    for p in props[:8]:
        kind = p.get("kind") if isinstance(p, dict) else None

        def reject(reason: str, value: Any = None):
            raw = value if value is not None else (p.get("value") if isinstance(p, dict) else None)
            rejected.append({"kind": str(kind)[:40] if kind is not None else None,
                             "value": str(raw)[:80] if raw is not None else None, "reason": reason})

        if kind not in SOFT_KINDS:
            reject("kind not allowed (soft style kinds only)")
            continue
        try:
            value = normalize(kind, p.get("value"))
        except InvalidMemory as exc:
            reject(f"not in vocabulary: {exc}")
            continue
        cited = [i for i in (p.get("evidenceEventIds") or []) if isinstance(i, str)]
        if not cited or any(i not in events for i in cited):
            reject("cites events that were not in the request", value)
            continue
        allowed = LIKE_EVENTS if kind.endswith("_like") else AVOID_EVENTS
        if any(events[i]["type"] not in allowed for i in cited):
            reject("action mismatch (likes need saves or purchases; avoids need rejections)", value)
            continue
        quote = " ".join(str(p.get("quote") or "").split())
        texts = " || ".join(_event_text(events[i]) for i in cited).lower()
        if not quote or quote.lower() not in texts:
            reject("quote is not copied from the cited listings", value)
            continue
        if not _supports(kind, str(value), quote):
            reject("quote does not state the value (or negates it)", value)
            continue
        vkey = str(value).lower()
        if (kind, vkey) in removed:
            reject("you removed this", value)
            continue
        if any((d["kind"] == kind or PAIRS.get(kind) == d["kind"]) and same_value(d["value"], value) for d in stated):
            reject("you already set this yourself", value)
            continue
        if (kind, vkey) in deterministic:
            reject("already inferred from listing facts", value)
            continue
        conf = p.get("confidence")
        conf = round(min(MODEL_CONFIDENCE_CAP, max(0.1, float(conf))), 2) if isinstance(conf, (int, float)) else 0.4
        _upsert_model_memory(db, owner, kind, value, cited, events, quote, conf, now)
        applied.append({"kind": kind, "value": value, "confidence": conf, "evidenceEventIds": cited})
    return applied, rejected


def _upsert_model_memory(db, owner, kind, value, cited, events, quote, conf, now: datetime) -> None:
    mid = "mem_m" + hashlib.sha256(f"{owner}|{kind}|{str(value).lower()}".encode()).hexdigest()[:20]
    ev = [{"eventId": i, "type": events[i]["type"], "at": events[i]["occurredAt"], "excerpt": quote[:120]} for i in cited][:5]
    last = max(events[i]["occurredAt"] for i in cited)
    old = db.style_memories.find_one({"_id": mid})
    if old:
        ids = sorted(set(old.get("sourceEventIds", [])) | set(cited))
        merged = (old.get("evidence") or []) + [e for e in ev if e["eventId"] not in {x["eventId"] for x in old.get("evidence") or []}]
        db.style_memories.update_one({"_id": mid}, {"$set": {
            "sourceEventIds": ids[:20], "evidenceCount": len(ids), "confidence": max(conf, old.get("confidence") or 0),
            "lastEvidenceAt": max(last, old.get("lastEvidenceAt") or last), "evidence": merged[-5:],
            "updatedAt": _iso(now)}})
        return
    db.style_memories.insert_one({
        "_id": mid, "id": mid, "ownerId": owner, "kind": kind, "value": value, "origin": "inferred",
        "source": "model_interpretation", "status": "active", "sourceEventIds": cited, "evidenceCount": len(cited),
        "overriddenBy": None, "createdAt": _iso(now), "updatedAt": _iso(now), "confidence": conf,
        "lastEvidenceAt": last, "evidence": ev,
    })


def prune(db, owner: str) -> list[str]:
    """Drop model memories whose evidence was all deleted (deleting history deletes what it implied)."""
    live = {e["id"] for e in db.style_events.find({"ownerId": owner}, {"id": 1})}
    gone = []
    for d in db.style_memories.find({"ownerId": owner, "source": "model_interpretation", "status": {"$ne": "removed"}}):
        keep = [i for i in d.get("sourceEventIds", []) if i in live]
        if not keep:
            db.style_memories.delete_one({"_id": d["_id"]})
            gone.append(d["_id"])
        elif len(keep) != len(d.get("sourceEventIds", [])):
            db.style_memories.update_one({"_id": d["_id"]}, {"$set": {"sourceEventIds": keep, "evidenceCount": len(keep),
                                                                       "evidence": [e for e in d.get("evidence") or [] if e["eventId"] in keep]}})
    return gone


def status(db, owner: str, limit: int = 10) -> dict:
    q = db.style_interpret_queue.find_one({"_id": owner})
    keep = ("id", "at", "model", "evidenceEventIds", "status", "applied", "rejected", "usage")
    runs = [{k: r[k] for k in keep if k in r}
            for r in db.style_interpret_runs.find({"ownerId": owner}).sort("at", -1).limit(limit)]
    for r in runs:  # runs stored before the typed contract may hold non-string model values
        r["rejected"] = [{**x, "kind": None if x.get("kind") is None else str(x["kind"])[:40],
                          "value": None if x.get("value") is None else str(x["value"])[:80]} for x in r.get("rejected", [])]
    return {"pendingEvents": len(q["pendingEventIds"]) if q else 0, "notBefore": q["notBefore"] if q else None, "runs": runs}


__all__ = ["schedule", "run_due", "apply_proposals", "prune", "status", "SOFT_KINDS", "COLORS"]
