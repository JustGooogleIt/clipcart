"""Soft personalization for search. Never touches hard constraints, eligibility or sections."""

from __future__ import annotations

from app.contracts import Listing, StyleProfile

from .vocab import colors_in

W_STATED_LIKE, W_INFERRED_LIKE = 2.0, 1.0
W_STATED_AVOID, W_INFERRED_AVOID = -3.0, -1.5


def style_score(listing: Listing, profile: StyleProfile | None) -> tuple[float, list[str]]:
    """Ranking nudge plus human-readable, fact-based reasons."""
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
    return score, reasons[:3]


def product_key(listing: Listing) -> str:
    return f"{listing.provider}:{listing.provider_listing_id}"


def is_rejected(listing: Listing, profile: StyleProfile | None) -> bool:
    return bool(profile and product_key(listing) in set(profile.rejected_product_keys))
