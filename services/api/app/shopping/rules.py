"""Deterministic verification and ranking (SRS section 11). RANKING_VERSION is
recorded on every recommendation. Models never decide constraint states."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.contracts import ConstraintCheck, Listing, Money, Preferences

RANKING_VERSION = "rules-2026-10-17.1"

CATEGORY_WORDS: dict[str, tuple[str, ...]] = {
    "jacket": (
        "jacket", "coat", "blazer", "parka", "bomber", "windbreaker", "puffer", "anorak",
        "trucker", "gilet", "vest", "shacket", "overcoat", "trench", "peacoat", "raincoat", "biker",
    ),
    "top": (
        "shirt", "t-shirt", "tee", "top", "blouse", "sweater", "hoodie", "sweatshirt", "cardigan",
        "polo", "tank", "jersey", "knit", "crewneck", "pullover", "henley", "camisole", "turtleneck",
    ),
    "bag": (
        "bag", "handbag", "tote", "backpack", "purse", "clutch", "satchel", "crossbody", "duffle",
        "hobo", "bucket", "messenger", "pouch",
    ),
}
ALPHA_SIZES = ["XXS", "XS", "S", "M", "L", "XL", "XXL", "XXXL"]
_ALPHA_ALIASES = {
    "2XS": "XXS", "2XL": "XXL", "3XL": "XXXL", "SMALL": "S", "MEDIUM": "M", "LARGE": "L",
    "X-SMALL": "XS", "EXTRA SMALL": "XS", "X-LARGE": "XL", "EXTRA LARGE": "XL", "XX-LARGE": "XXL",
}
_COLOR_WORDS = {
    "black", "white", "gray", "grey", "navy", "blue", "red", "green", "olive", "brown", "tan", "beige",
    "cream", "ivory", "pink", "purple", "yellow", "orange", "khaki", "camel", "burgundy", "maroon",
    "silver", "gold", "denim", "charcoal",
}
_STOP = {"the", "a", "an", "and", "or", "with", "of", "in", "for", "on", "to", "this", "that", "jacket", "top", "bag"}


def words(text: str | None) -> list[str]:
    return re.findall(r"[a-z0-9]+(?:-[a-z0-9]+)?", (text or "").lower())


def money_str(m: Money | None) -> str:
    if m is None:
        return "unknown price"
    amt = m.amount_minor / 100
    sym = "$" if m.currency == "USD" else f"{m.currency} "
    return f"{sym}{amt:,.0f}" if m.amount_minor % 100 == 0 else f"{sym}{amt:,.2f}"


@dataclass
class GarmentProfile:
    category: str
    colors: list[str] = field(default_factory=list)
    pattern: list[str] = field(default_factory=list)
    cut: list[str] = field(default_factory=list)
    details: list[str] = field(default_factory=list)
    visible_text: list[str] = field(default_factory=list)
    description: str | None = None
    label: str = ""

    def keywords(self) -> set[str]:
        bag: set[str] = set()
        for part in [*self.colors, *self.pattern, *self.cut, *self.details, self.description or ""]:
            bag.update(w for w in words(part) if w not in _STOP and len(w) > 2)
        return bag


# Multi-token names a word list can't catch, e.g. "Alpha Industries MA-1" is a bomber/flight jacket.
CATEGORY_PATTERNS: dict[str, tuple[re.Pattern, ...]] = {
    "jacket": (re.compile(r"\bma[-\s]?1\b", re.I), re.compile(r"\bflight\s+jacket\b", re.I)),
}

# Explicit women's labelling only. Never inferred from size, color or cut.
_WOMENS = re.compile(r"\b(?:women(?:'?s)?|woman'?s|wmns|ladies)\b", re.I)


def title_matches_category(title: str, category: str) -> bool:
    fam = CATEGORY_WORDS.get(category)
    if not fam:
        return True
    toks = set(words(title))
    if any(w in toks for w in fam):
        return True
    return any(p.search(title or "") for p in CATEGORY_PATTERNS.get(category, ()))


def explicitly_womens(text: str | None) -> bool:
    return bool(_WOMENS.search((text or "").replace("\u2019", "'")))


def norm_size(raw: str) -> tuple[str, str]:
    """Return (normalized label, system) where system is alpha|numeric|other."""
    s = " ".join(raw.strip().upper().split())
    s = _ALPHA_ALIASES.get(s, s)
    if s in ALPHA_SIZES:
        return s, "alpha"
    if re.fullmatch(r"\d{1,3}(\.\d)?", s):
        return s, "numeric"
    return s, "other"


def _price_for_size(listing: Listing, prefs: Preferences) -> tuple[Money | None, str]:
    if prefs.size and listing.sizes_in_stock:
        want, _ = norm_size(prefs.size.raw)
        for s in listing.sizes_in_stock:
            if norm_size(s.raw)[0] == want and s.lowest_price is not None:
                return s.lowest_price, f"size {s.raw}"
    return listing.price, ""


def price_phrase(listing: Listing, prefs: Preferences | None = None) -> str:
    price, size_note = _price_for_size(listing, prefs) if prefs else (listing.price, "")
    p = money_str(price)
    if listing.price_basis == "aggregate_lowest":
        n = listing.stores_carrying
        where = ("at 1 retailer" if n == 1 else f"across {n} retailers") if n else "across retailers"
        seller = "; cheapest seller not named" if listing.seller_visibility == "hidden" else ""
        sz = f" in {size_note}" if size_note else ""
        return f"Lowest listed {p}{sz} {where} via SoleScout{seller}"
    if listing.price_basis == "seller_offer":
        extra = ""
        if listing.provider == "solescout" and listing.hidden_store_count:
            extra = f"; {listing.hidden_store_count} unnamed seller(s) may be cheaper"
        return f"{p} at {listing.retailer} (found via SoleScout){extra}" if listing.provider == "solescout" else f"{p} at {listing.retailer}"
    return "Price not available"


def check_constraints(listing: Listing, prefs: Preferences) -> list[ConstraintCheck]:
    checks: list[ConstraintCheck] = []
    ev = listing.evidence_ids

    if prefs.max_item_price_minor is not None:
        price, size_note = _price_for_size(listing, prefs)
        budget = Money(amount_minor=prefs.max_item_price_minor, currency=prefs.currency)
        if price is None:
            checks.append(ConstraintCheck(constraint="budget", state="unknown", detail="No sourced price", evidence_ids=ev))
        elif price.currency != prefs.currency:
            checks.append(
                ConstraintCheck(
                    constraint="budget",
                    state="unknown",
                    detail=f"Price is in {price.currency}; no sourced conversion to {prefs.currency}",
                    evidence_ids=ev,
                )
            )
        else:
            basis = "lowest listed price" if listing.price_basis == "aggregate_lowest" else "listed price"
            sz = f" for {size_note}" if size_note else ""
            ok = price.amount_minor <= budget.amount_minor
            checks.append(
                ConstraintCheck(
                    constraint="budget",
                    state="satisfied" if ok else "violated",
                    detail=f"{basis.capitalize()}{sz} {money_str(price)} {'within' if ok else 'above'} "
                    f"{money_str(budget)} budget (excludes shipping and tax)",
                    evidence_ids=ev,
                )
            )

    if prefs.size:
        want, want_sys = norm_size(prefs.size.raw)
        if listing.sizes_in_stock is None:
            checks.append(ConstraintCheck(constraint="size", state="unknown", detail="Size stock not checked", evidence_ids=ev))
        elif not listing.sizes_in_stock:
            checks.append(
                ConstraintCheck(
                    constraint="size", state="unknown", detail="Source lists no in-stock sizes; stock unknown", evidence_ids=ev
                )
            )
        else:
            listed = [(s.raw, *norm_size(s.raw)) for s in listing.sizes_in_stock]
            if any(n == want for _, n, _ in listed):
                checks.append(
                    ConstraintCheck(constraint="size", state="satisfied", detail=f"{want} listed in stock", evidence_ids=ev)
                )
            elif want_sys != "other" and all(sys_ == want_sys for _, _, sys_ in listed):
                shown = ", ".join(r for r, _, _ in listed[:8])
                checks.append(
                    ConstraintCheck(
                        constraint="size", state="violated", detail=f"{want} not listed in stock (listed: {shown})", evidence_ids=ev
                    )
                )
            else:
                shown = ", ".join(r for r, _, _ in listed[:6])
                checks.append(
                    ConstraintCheck(
                        constraint="size",
                        state="unknown",
                        detail=f"Listed sizes use another system ({shown}); not converted",
                        evidence_ids=ev,
                    )
                )

    # ClipCart has no fit-category preference yet, so the shopper's fit is always unspecified.
    # An explicitly women's listing therefore needs checking. Size (e.g. "M") never implies fit.
    if explicitly_womens(listing.title):
        checks.append(
            ConstraintCheck(
                constraint="fit",
                state="unknown",
                detail="Listed as a women's item; your fit category isn't set",
                evidence_ids=ev,
            )
        )

    text = f"{listing.title} {listing.material_text or ''}".lower()
    for m in prefs.excluded_materials:
        pat = re.escape(m)
        faux = re.search(rf"\b(faux|vegan|imitation|synthetic)[\s-]+{pat}\b", text)
        plain = re.search(rf"\b{pat}\b", re.sub(rf"\b(faux|vegan|imitation|synthetic)[\s-]+{pat}\b", " ", text))
        if plain:
            checks.append(
                ConstraintCheck(
                    constraint=f"no {m}", state="violated", detail=f"Listing title mentions {m}", evidence_ids=ev
                )
            )
        elif faux:
            checks.append(
                ConstraintCheck(
                    constraint=f"no {m}",
                    state="unknown",
                    detail=f"Title says {faux.group(0)}; composition not confirmed by source",
                    evidence_ids=ev,
                )
            )
        else:
            checks.append(
                ConstraintCheck(
                    constraint=f"no {m}", state="unknown", detail="Source gives no material composition", evidence_ids=ev
                )
            )

    if prefs.condition != "any":
        if listing.condition == "unknown":
            checks.append(ConstraintCheck(constraint="condition", state="unknown", detail="Condition not provided by source"))
        else:
            ok = listing.condition == prefs.condition
            checks.append(
                ConstraintCheck(
                    constraint="condition",
                    state="satisfied" if ok else "violated",
                    detail=f"Listed as {listing.condition}",
                    evidence_ids=ev,
                )
            )
    return checks


def _alnum(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


def identity_tier(listing: Listing, profile: GarmentProfile) -> tuple[str, str]:
    """Return (tier, reason). Visual resemblance alone is never 'verified'."""
    seen = [_alnum(t) for t in profile.visible_text if t.strip()]
    if listing.style_code and len(_alnum(listing.style_code)) >= 5:
        code = _alnum(listing.style_code)
        if any(code in t for t in seen):
            return "verified", f"Style code {listing.style_code} read on the garment"
    if listing.brand and len(_alnum(listing.brand)) >= 3 and title_matches_category(listing.title, profile.category):
        b = _alnum(listing.brand)
        if any(b in t for t in seen):
            return "likely", f"Brand text '{listing.brand}' visible on the garment; product not confirmed"
        if profile.description and b in _alnum(profile.description):
            return "likely", f"You named the brand {listing.brand}; product not confirmed"
    return "similar", "Visual and attribute resemblance only"


def relevance(listing: Listing, profile: GarmentProfile, prefs: Preferences) -> float:
    title_toks = set(words(f"{listing.title} {listing.color_text or ''}"))
    kw = profile.keywords()
    score = 0.0
    if kw:
        score += 0.6 * len(kw & title_toks) / len(kw)
    garment_colors = {c for c in words(" ".join(profile.colors)) if c in _COLOR_WORDS}
    if garment_colors & title_toks:
        score += 0.2
    wanted = set(words(" ".join(prefs.colors))) if prefs.colors else garment_colors
    if prefs.colors and wanted & title_toks:
        score += 0.2
    listed_colors = {w for w in title_toks if w in _COLOR_WORDS} - {"denim"}
    if wanted and listed_colors and not (listed_colors & (wanted | {"grey" if "gray" in wanted else "gray"})):
        score -= 0.25  # the listing names a different color
    return round(max(min(score, 1.0), -1.0), 3)


TIER_ORDER = {"verified": 0, "likely": 1, "similar": 2}


def section_for(checks: list[ConstraintCheck]) -> str:
    states = {c.state for c in checks}
    if "violated" in states:
        return "excluded"
    if "unknown" in states:
        return "needs_checking"
    return "primary"


def explanation(listing: Listing, profile: GarmentProfile, tier: str, tier_reason: str, prefs: Preferences) -> str:
    parts = []
    if tier == "similar":
        shared = sorted(profile.keywords() & set(words(listing.title)))[:3]
        if shared:
            parts.append(f"Similar {profile.category}: title shares {', '.join(shared)}")
        else:
            parts.append(f"Similar {profile.category} found by the alternatives search")
    else:
        parts.append(tier_reason)
    parts.append(price_phrase(listing, prefs))
    return ". ".join(parts) + "."
