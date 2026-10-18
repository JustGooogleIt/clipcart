"""Soft personalization for search. Never touches hard constraints, eligibility or sections."""

from __future__ import annotations

from app.categories import is_accessory
from app.contracts import Listing, StyleProfile

from .tags import extract
from .vocab import colors_in

W_STATED_LIKE, W_INFERRED_LIKE = 2.0, 1.0
W_STATED_AVOID, W_INFERRED_AVOID = -3.0, -1.5


def _listing_tones(listing: Listing) -> set[str]:
    t = f"{listing.title} {listing.color_text or ''}".lower()
    out = set()
    if "rose gold" in t or "rose-gold" in t:
        out.add("rose-gold-tone")
    elif "gold" in t:
        out.add("gold-tone")
    if "silver" in t or "stainless" in t or "sterling" in t:
        out.add("silver-tone")
    if "two-tone" in t or "two tone" in t:
        out.add("two-tone")
    return out


def style_score(listing: Listing, profile: StyleProfile | None, category: str | None = None) -> tuple[float, list[str]]:
    """Ranking nudge plus human-readable, fact-based reasons. Tone preferences apply to watches and jewelry only."""
    if profile is None:
        return 0.0, []
    score = 0.0
    reasons: list[str] = []
    brand = (listing.brand or "").lower()
    colors = set(colors_in(f"{listing.title} {listing.color_text or ''}"))
    for e in profile.brands_like:
        if brand and str(e.value).lower() == brand:
            score += W_STATED_LIKE if e.origin == "stated" else W_INFERRED_LIKE
            reasons.append(f"You said you like {e.value}" if e.origin == "stated"
                           else f"Matches a brand from items you saved or bought ({e.value})")
    for e in profile.brands_avoid:
        if brand and str(e.value).lower() == brand:
            score += W_STATED_AVOID if e.origin == "stated" else W_INFERRED_AVOID
            reasons.append(f"Ranked lower: you said you avoid {e.value}" if e.origin == "stated"
                           else f"Ranked lower: similar to items you rejected ({e.value})")
    for e in profile.colors_like:
        if e.value in colors:
            score += W_STATED_LIKE if e.origin == "stated" else W_INFERRED_LIKE
            reasons.append(f"You said you like {e.value}" if e.origin == "stated"
                           else f"In a color you often save ({e.value})")
    for e in profile.colors_avoid:
        if e.value in colors:
            score += W_STATED_AVOID if e.origin == "stated" else W_INFERRED_AVOID
            reasons.append(f"Ranked lower: you said you avoid {e.value}" if e.origin == "stated"
                           else f"Ranked lower: a color you often reject ({e.value})")
    tags = {t for t, _ in extract(f"{listing.title} {listing.material_text or ''}")}
    for e in profile.styles_like:
        if e.value in tags:
            score += W_STATED_LIKE if e.origin == "stated" else W_INFERRED_LIKE
            reasons.append(f"You said you like {e.value} style" if e.origin == "stated"
                           else f"Matches a style from items you saved or bought ({e.value})")
    for e in profile.styles_avoid:
        if e.value in tags:
            score += W_STATED_AVOID if e.origin == "stated" else W_INFERRED_AVOID
            reasons.append(f"Ranked lower: you said you avoid {e.value} style" if e.origin == "stated"
                           else f"Ranked lower: a style you often hide ({e.value})")
    if category and is_accessory(category):
        tones = _listing_tones(listing)
        for e in profile.tones_like:
            if e.value in tones:
                score += W_STATED_LIKE if e.origin == "stated" else W_INFERRED_LIKE
                reasons.append(f"You said you like {e.value}" if e.origin == "stated" else f"In a tone you often save ({e.value})")
        for e in profile.tones_avoid:
            if e.value in tones:
                score += W_STATED_AVOID if e.origin == "stated" else W_INFERRED_AVOID
                reasons.append(f"Ranked lower: you said you avoid {e.value}" if e.origin == "stated"
                               else f"Ranked lower: a tone you often reject ({e.value})")
    return score, reasons[:3]


def product_key(listing: Listing) -> str:
    return f"{listing.provider}:{listing.provider_listing_id}"


def is_rejected(listing: Listing, profile: StyleProfile | None) -> bool:
    return bool(profile and product_key(listing) in set(profile.rejected_product_keys))
