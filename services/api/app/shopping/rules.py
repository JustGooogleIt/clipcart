"""Deterministic verification and ranking (SRS section 11). RANKING_VERSION is
recorded on every recommendation. Models never decide constraint states."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.contracts import ConstraintCheck, Listing, Money, Preferences

RANKING_VERSION = "rules-2026-10-18.3"

CATEGORY_WORDS: dict[str, tuple[str, ...]] = {
    "jacket": (
        "jacket", "coat", "blazer", "parka", "bomber", "windbreaker", "puffer", "anorak",
        "trucker", "gilet", "vest", "shacket", "overcoat", "trench", "peacoat", "raincoat", "biker",
        "moto", "varsity", "coach", "chore", "field",
    ),
    "top": (
        "shirt", "t-shirt", "tee", "top", "blouse", "sweater", "hoodie", "sweatshirt", "cardigan",
        "polo", "tank", "jersey", "knit", "crewneck", "pullover", "henley", "camisole", "turtleneck",
    ),
    "pants": (
        "pants", "jeans", "trousers", "chinos", "shorts", "leggings", "skirt", "denim", "cargos",
        "joggers", "sweatpants", "khakis",
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
# Hue names only. Fabric words like denim belong in style cues, not color matching.
_COLOR_WORDS = {
    "black", "white", "gray", "grey", "navy", "blue", "red", "green", "olive", "brown", "tan", "beige",
    "cream", "ivory", "pink", "purple", "yellow", "orange", "khaki", "camel", "burgundy", "maroon",
    "silver", "gold", "charcoal",
}
# Visible fabric / construction cues we use for search queries and ranking.
_FABRIC_CUES = {
    "denim", "jeans", "leather", "suede", "shearling", "fleece", "corduroy", "nylon", "satin",
    "velvet", "wool", "cashmere", "linen", "silk", "knit", "quilted", "down", "tweed", "canvas",
    "mesh", "sherpa",
}
_STYLE_CUES = {
    "trucker", "bomber", "biker", "moto", "parka", "puffer", "windbreaker", "trench", "peacoat",
    "anorak", "shacket", "overshirt", "chore", "field", "varsity", "coach", "raincoat", "blazer",
    "hoodie", "crewneck", "cardigan", "polo", "cargo", "skinny", "wide-leg", "oversized", "cropped",
}
# Soft conflicts: if the garment shows one fabric and the listing names another, down-rank.
_FABRIC_CONFLICTS: dict[str, frozenset[str]] = {
    "denim": frozenset({"leather", "suede", "shearling", "fleece", "nylon", "puffer", "down", "satin", "velvet"}),
    "leather": frozenset({"denim", "fleece", "knit", "puffer", "down"}),
    "fleece": frozenset({"denim", "leather", "satin"}),
    "puffer": frozenset({"denim", "leather", "trucker"}),
    "down": frozenset({"denim", "leather"}),
}
# Title tokens that count as matching a required fabric cue.
_FABRIC_SYNONYMS: dict[str, frozenset[str]] = {
    "denim": frozenset({"denim", "jean", "jeans"}),
    "leather": frozenset({"leather", "nappa", "lambskin", "calfskin"}),
    "suede": frozenset({"suede", "nubuck"}),
    "fleece": frozenset({"fleece", "sherpa"}),
    "corduroy": frozenset({"corduroy", "cord"}),
    "quilted": frozenset({"quilted", "quilt"}),
    "shearling": frozenset({"shearling", "sheepskin"}),
    "nylon": frozenset({"nylon", "ripstop"}),
}
_STOP = {
    "the", "a", "an", "and", "or", "with", "of", "in", "for", "on", "to", "this", "that",
    "jacket", "top", "pants", "bag", "as", "seen", "look", "looks", "like", "style", "type",
    "front", "back", "left", "right", "small", "large", "visible", "appearance",
}


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

    def bag_words(self) -> set[str]:
        return self.keywords() | {w for w in words(self.label) if len(w) > 2}

    def hue_colors(self) -> list[str]:
        """Hue names only — fabric words like denim are style, not color."""
        out: list[str] = []
        for part in self.colors:
            for w in words(part):
                if w in _COLOR_WORDS and w not in out:
                    out.append(w)
        return out

    def style_cues(self) -> list[str]:
        """Fabric + silhouette cues used to build catalog queries."""
        bag = self.bag_words()
        preferred = (
            "denim", "leather", "suede", "fleece", "corduroy", "quilted", "shearling",
            "trucker", "bomber", "biker", "moto", "puffer", "parka", "windbreaker",
            "trench", "varsity", "chore", "field", "hoodie", "polo", "jeans",
        )
        out: list[str] = []
        for w in preferred:
            if w in bag and w not in out:
                out.append(w)
        for w in sorted(bag & (_FABRIC_CUES | _STYLE_CUES)):
            if w not in out:
                out.append(w)
        return out[:6]

    def descriptors(self) -> list[str]:
        """Ordered distinctive tokens from every observed field (for queries + ranking)."""
        preferred = (
            "denim", "leather", "suede", "fleece", "corduroy", "quilted", "shearling", "nylon",
            "trucker", "bomber", "biker", "moto", "puffer", "parka", "windbreaker", "trench",
            "varsity", "chore", "hoodie", "polo", "jeans", "distressed", "faded", "washed",
            "indigo", "oversized", "cropped", "slim", "boxy", "hooded", "zip", "button",
            "rivet", "embroidery", "graphic", "plaid", "striped", "check",
        )
        bag = self.bag_words()
        out: list[str] = []
        for w in preferred:
            if w in bag and w not in out:
                out.append(w)
        for w in self.hue_colors():
            if w not in out:
                out.append(w)
        # Remaining detail/cut/pattern tokens, longest-first so "chest" beats noise.
        rest = sorted((bag - set(out)) - _STOP, key=lambda x: (-len(x), x))
        for w in rest:
            if len(w) >= 3 and w not in out:
                out.append(w)
            if len(out) >= 12:
                break
        return out


def title_matches_category(title: str, category: str) -> bool:
    fam = CATEGORY_WORDS.get(category)
    if not fam:
        return True
    toks = set(words(title))
    return any(w in toks for w in fam)


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


def _wanted_colors(profile: GarmentProfile, prefs: Preferences) -> set[str]:
    if prefs.colors:
        return set(words(" ".join(prefs.colors))) & _COLOR_WORDS
    return set(profile.hue_colors())


def _title_tokens(listing: Listing) -> set[str]:
    return set(words(f"{listing.title} {listing.color_text or ''} {listing.material_text or ''}"))


def required_fabrics(profile: GarmentProfile) -> list[str]:
    return [s for s in profile.style_cues() if s in _FABRIC_SYNONYMS]


def fabric_match(listing: Listing, profile: GarmentProfile) -> bool:
    """True when every required fabric cue is present (via synonyms) in the title."""
    title_toks = _title_tokens(listing)
    req = required_fabrics(profile)
    if not req:
        return True
    return all((_FABRIC_SYNONYMS[f] & title_toks) for f in req)


def type_match(listing: Listing, profile: GarmentProfile) -> bool:
    title_toks = _title_tokens(listing)
    types = [s for s in profile.style_cues() if s in _STYLE_CUES and s not in _FABRIC_SYNONYMS]
    if not types:
        return True
    return bool(set(types) & title_toks)


def clear_mismatch(listing: Listing, profile: GarmentProfile, prefs: Preferences) -> bool:
    """True only for hard visual conflicts — not 'low similarity'."""
    title_toks = _title_tokens(listing)
    wanted = _wanted_colors(profile, prefs)
    listed_colors = {w for w in title_toks if w in _COLOR_WORDS}
    gray_ok = {"grey", "gray"} if (wanted & {"grey", "gray"}) else set()
    if wanted and listed_colors and not (listed_colors & (wanted | gray_ok)):
        return True
    styles = set(profile.style_cues())
    for cue in styles:
        conflict = _FABRIC_CONFLICTS.get(cue, frozenset())
        syns = _FABRIC_SYNONYMS.get(cue, frozenset({cue}))
        if conflict & title_toks and not (syns & title_toks):
            return True
    return False


def relevance(listing: Listing, profile: GarmentProfile, prefs: Preferences) -> float:
    title_toks = _title_tokens(listing)
    desc = profile.descriptors()
    score = 0.0
    if desc:
        hit = len(set(desc) & title_toks)
        score += min(0.55, 0.11 * hit)
        score += 0.2 * (hit / len(desc))
    # Fabric + type are the biggest visual signals for "looks like the thing".
    req = required_fabrics(profile)
    if req:
        if fabric_match(listing, profile):
            score += 0.35
        else:
            score -= 0.35
    styles = set(profile.style_cues())
    type_hits = (styles & _STYLE_CUES & title_toks) - set(req)
    if type_hits:
        score += min(0.25, 0.12 * len(type_hits))
    elif any(s in _STYLE_CUES and s not in _FABRIC_SYNONYMS for s in styles):
        score -= 0.08  # known silhouette missing from title
    for cue in styles:
        conflict = _FABRIC_CONFLICTS.get(cue, frozenset())
        syns = _FABRIC_SYNONYMS.get(cue, frozenset({cue}))
        if conflict & title_toks and not (syns & title_toks):
            score -= 0.4
            break
    wanted = _wanted_colors(profile, prefs)
    if wanted & title_toks:
        score += 0.12
    if prefs.colors and wanted & title_toks:
        score += 0.08
    if clear_mismatch(listing, profile, prefs):
        score -= 0.55
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
