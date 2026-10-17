"""Prompt, JSON schema and strict validation for YouTube garment listing."""

from __future__ import annotations

import hashlib
import re
from typing import Any

from app.contracts import YouTubeGarment, YouTubeTimestamp

MAX_GARMENTS = 8

SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "garments": {
            "type": "array",
            "maxItems": MAX_GARMENTS,
            "items": {
                "type": "object",
                "properties": {
                    "category": {"type": "string", "enum": ["jacket", "top", "bag", "other"]},
                    "description": {"type": "string"},
                    "colors": {"type": "array", "items": {"type": "string"}, "maxItems": 4},
                    "pattern": {"type": "array", "items": {"type": "string"}, "maxItems": 3},
                    "visible_text": {"type": "array", "items": {"type": "string"}, "maxItems": 4},
                    "person_label": {"type": "string"},
                    "timestamps": {"type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": 5},
                },
                "required": ["category", "description", "timestamps"],
            },
        }
    },
    "required": ["garments"],
}


def build_prompt(start_s: int, end_s: int) -> str:
    return (
        "You are listing clothing a shopper could search for. Watch only the part of the video from "
        f"{fmt(start_s)} to {fmt(end_s)}.\n"
        "List each distinct jacket or coat, top (shirt, t-shirt, sweater, hoodie, blouse) and bag that is clearly "
        "visible on a person or on screen. Use category 'other' only for other clothing.\n"
        "Rules:\n"
        "- One entry per distinct garment. If the same garment appears again, add timestamps to that entry.\n"
        "- Similar garments on different people are different entries. Use person_label like person_1, person_2; "
        "never names or guesses about identity, age or other traits.\n"
        "- description: under 25 words, only what is visible (color, pattern, cut, length, collar, closure, pockets, "
        "logos as seen).\n"
        "- visible_text: only text or logo lettering you can actually read on the garment. Do not guess brands.\n"
        "- Never state material composition, size, price or where to buy.\n"
        "- timestamps: when the garment is clearly visible, as MM:SS (or H:MM:SS) measured from the start of the "
        f"full video, within {fmt(start_s)}-{fmt(end_s)}.\n"
        "- If no such garment is clearly visible, return an empty garments list. Do not invent garments."
    )


def fmt(seconds: int) -> str:
    h, rem = divmod(int(seconds), 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


_TS = re.compile(r"^\s*(?:(\d{1,2}):)?(\d{1,2}):(\d{2})(?:\.\d+)?\s*$")


def parse_ts(raw: Any) -> int | None:
    if isinstance(raw, (int, float)) and not isinstance(raw, bool) and raw >= 0:
        return int(raw)
    m = _TS.match(str(raw))
    if not m:
        return None
    h, mi, s = int(m.group(1) or 0), int(m.group(2)), int(m.group(3))
    if s >= 60 or (m.group(1) and mi >= 60):
        return None
    return h * 3600 + mi * 60 + s


def _clean_list(v: Any, n: int) -> list[str]:
    out: list[str] = []
    for x in v if isinstance(v, list) else []:
        if isinstance(x, str):
            w = " ".join(x.split())[:40]
            if w and w.lower() not in [o.lower() for o in out]:
                out.append(w)
    return out[:n]


def validate_garments(payload: Any, *, start_s: int, end_s: int, video_id: str) -> tuple[list[YouTubeGarment], int]:
    """Return (garments, dropped). Rejects anything malformed instead of repairing it into a claim."""
    if not isinstance(payload, dict) or not isinstance(payload.get("garments"), list):
        raise ValueError("response is missing the garments list")
    garments: list[YouTubeGarment] = []
    dropped = 0
    tol = 2
    for i, item in enumerate(payload["garments"][: MAX_GARMENTS * 2]):
        if not isinstance(item, dict):
            dropped += 1
            continue
        cat = item.get("category")
        desc = " ".join(str(item.get("description") or "").split())
        if cat not in ("jacket", "top", "bag", "other") or not desc:
            dropped += 1
            continue
        stamps: list[YouTubeTimestamp] = []
        for raw in item.get("timestamps") or []:
            sec = parse_ts(raw)
            if sec is None or not (start_s - tol <= sec <= end_s + tol):
                continue
            if sec not in [t.seconds for t in stamps]:
                stamps.append(YouTubeTimestamp(seconds=sec, label=fmt(sec)))
        if not stamps:
            dropped += 1  # no usable timestamp inside the analyzed window
            continue
        person = item.get("person_label")
        person = person if isinstance(person, str) and re.fullmatch(r"person_\d{1,2}", person.strip()) else None
        gid = "ytg_" + hashlib.sha256(f"{video_id}|{start_s}-{end_s}|{i}|{desc}".encode()).hexdigest()[:16]
        garments.append(
            YouTubeGarment(
                id=gid,
                category=cat,
                description=desc[:240],
                colors=_clean_list(item.get("colors"), 4),
                pattern=_clean_list(item.get("pattern"), 3),
                visible_text=_clean_list(item.get("visible_text"), 4),
                person_label=person.strip() if person else None,
                timestamps=sorted(stamps, key=lambda t: t.seconds)[:5],
            )
        )
        if len(garments) >= MAX_GARMENTS:
            break
    return garments, dropped
