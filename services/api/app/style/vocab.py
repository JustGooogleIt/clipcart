"""Validate and normalize memory values. Anything outside the vocabulary is rejected, never guessed."""

from __future__ import annotations

import re
from typing import Any, get_args

from app.contracts import Tone

from app.shopping.refine import _MATERIALS
from app.shopping.rules import _COLOR_WORDS, norm_size

ONE_ACTIVE = {"size", "fit", "budget_max", "ring_size"}
PAIRS = {
    "color_like": "color_avoid", "color_avoid": "color_like",
    "material_like": "material_avoid", "material_avoid": "material_like",
    "brand_like": "brand_avoid", "brand_avoid": "brand_like",
    "tone_like": "tone_avoid", "tone_avoid": "tone_like",
    "style_like": "style_avoid", "style_avoid": "style_like",
}
TONES: tuple[str, ...] = get_args(Tone)  # the contract's Tone enum is the vocabulary
_TONE_ALIASES = {"gold": "gold-tone", "gold tone": "gold-tone", "golden": "gold-tone", "silver": "silver-tone",
                 "silver tone": "silver-tone", "rose gold": "rose-gold-tone", "rose gold tone": "rose-gold-tone",
                 "rose-gold": "rose-gold-tone", "two tone": "two-tone", "mixed metal": "two-tone"}
COLORS = set(_COLOR_WORDS) | {"gray"}
MATERIALS = set(_MATERIALS) | {"faux leather", "corduroy", "satin", "velvet", "tweed"}
_FIT = {"women": "womens", "womens": "womens", "women's": "womens", "woman's": "womens", "ladies": "womens",
        "men": "mens", "mens": "mens", "men's": "mens", "unisex": "unisex"}
_BRAND = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 &'.\-]{0,38}[A-Za-z0-9.]$")


class InvalidMemory(ValueError):
    pass


def normalize(kind: str, value: Any) -> Any:
    """Return a canonical value for ``kind`` or raise InvalidMemory."""
    if kind in ("color_like", "color_avoid"):
        v = str(value or "").strip().lower()
        v = "gray" if v == "grey" else v
        if v not in COLORS:
            raise InvalidMemory(f"unknown color {value!r}")
        return v
    if kind in ("material_like", "material_avoid"):
        v = " ".join(str(value or "").lower().split())
        if v not in MATERIALS:
            raise InvalidMemory(f"unknown material {value!r}")
        return v
    if kind in ("brand_like", "brand_avoid"):
        v = " ".join(str(value or "").split())
        if not _BRAND.match(v) or v.lower() in COLORS or v.lower() in MATERIALS:
            raise InvalidMemory(f"not a brand name: {value!r}")
        return v
    if kind == "fit":
        v = _FIT.get(str(value or "").strip().lower().replace("’", "'"))
        if not v:
            raise InvalidMemory(f"unknown fit {value!r}")
        return v
    if kind == "size":
        raw = value.get("raw") if isinstance(value, dict) else value
        raw = str(raw or "").strip()
        if not raw or len(raw) > 12:
            raise InvalidMemory("size must be 1-12 characters")
        label, system = norm_size(raw)
        return {"raw": label, "system": system if system in ("alpha", "numeric") else None}
    if kind in ("style_like", "style_avoid"):
        from .tags import STYLE_TAGS, normalize_tag

        v = normalize_tag(value)
        if not v:
            raise InvalidMemory(f"unknown style {value!r}; use one of {', '.join(STYLE_TAGS)}")
        return v
    if kind in ("tone_like", "tone_avoid"):
        v = " ".join(str(value or "").lower().replace("-", " ").split())
        v = _TONE_ALIASES.get(v, v.replace(" ", "-"))
        if v not in TONES:
            raise InvalidMemory(f"unknown tone {value!r}; use gold-tone, silver-tone, rose-gold-tone, black or two-tone")
        return v
    if kind == "ring_size":
        from app.categories import norm_ring_size

        raw = value.get("raw") if isinstance(value, dict) else value
        n = norm_ring_size(str(raw or ""))
        if n is None:
            raise InvalidMemory("ring size must be a US size from 3 to 15, e.g. 7 or 6.5")
        return {"raw": n, "system": "us"}
    if kind == "budget_max":
        if isinstance(value, dict):
            minor, cur = value.get("amountMinor"), str(value.get("currency") or "USD").upper()
        else:
            m = re.fullmatch(r"\$?\s*(\d{1,6}(?:\.\d{1,2})?)", str(value or "").strip())
            if not m:
                raise InvalidMemory(f"not an amount: {value!r}")
            minor, cur = int(round(float(m.group(1)) * 100)), "USD"
        if not isinstance(minor, int) or isinstance(minor, bool) or not (0 < minor <= 10_000_000) or cur != "USD":
            raise InvalidMemory("budget must be a positive USD amount")
        return {"amountMinor": minor, "currency": "USD"}
    raise InvalidMemory(f"unknown kind {kind!r}")


def colors_in(text: str | None) -> list[str]:
    toks = re.findall(r"[a-z]+", (text or "").lower())
    out = []
    for t in toks:
        t = "gray" if t == "grey" else t
        if t in COLORS and t != "denim" and t not in out:
            out.append(t)
    return out


def same_value(a: Any, b: Any) -> bool:
    if isinstance(a, str) and isinstance(b, str):
        return a.lower() == b.lower()
    return a == b
