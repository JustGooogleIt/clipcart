"""Shopping categories: garments, bags, watches and jewelry (contract: docs/contracts/accessories.md).

One source of truth for category families, size rules and the appearance-only rule for accessories:
ClipCart never infers authenticity, a luxury brand, precious metal or gemstone composition from
how an item looks.
"""

from __future__ import annotations

import re

APPAREL = ("jacket", "top", "pants")
JEWELRY = ("necklace", "bracelet", "ring", "earrings")
ACCESSORIES = ("watch", *JEWELRY)
ALL = (*APPAREL, "bag", *ACCESSORIES)

INFO: dict[str, dict] = {
    "jacket": {"label": "Jacket", "family": "apparel", "sizeRule": "clothing"},
    "top": {"label": "Top", "family": "apparel", "sizeRule": "clothing"},
    "pants": {"label": "Pants", "family": "apparel", "sizeRule": "clothing"},
    "bag": {"label": "Bag", "family": "bag", "sizeRule": "clothing"},  # unchanged legacy behavior; see contract
    "watch": {"label": "Watch", "family": "watch", "sizeRule": "none"},
    "necklace": {"label": "Necklace", "family": "jewelry", "sizeRule": "none"},
    "bracelet": {"label": "Bracelet", "family": "jewelry", "sizeRule": "none"},
    "ring": {"label": "Ring", "family": "jewelry", "sizeRule": "ring"},
    "earrings": {"label": "Earrings", "family": "jewelry", "sizeRule": "none"},
    "other": {"label": "Other", "family": "other", "sizeRule": "none"},
}
_ATTR_KEYS = {"apparel": ["color", "pattern", "cut", "details"], "bag": ["color", "pattern", "cut", "details"],
              "watch": ["color", "cut", "details"], "jewelry": ["color", "cut", "details"], "other": ["color", "details"]}

# What the detector is asked to find. Wording kept short; Perceptron takes free-text classes.
DETECT_PROMPTS = {
    "watch": "wristwatch",
    "necklace": "necklace or pendant",
    "bracelet": "bracelet or bangle",
    "ring": "finger ring",
    "earrings": "earring",
}


def is_accessory(category: str | None) -> bool:
    return category in ACCESSORIES


def family(category: str | None) -> str:
    return INFO.get(category or "other", INFO["other"])["family"]


def size_rule(category: str | None) -> str:
    return INFO.get(category or "other", INFO["other"])["sizeRule"]


def public_categories() -> list[dict]:
    return [{"id": c, **INFO[c], "attributeKeys": _ATTR_KEYS[INFO[c]["family"]]} for c in (*ALL, "other")]


# ---------------------------------------------------------------- label → category (detector output)
_LABEL_RULES: tuple[tuple[str, re.Pattern], ...] = (
    # Order matters: earrings before rings, watches before bracelets ("watch bracelet").
    ("earrings", re.compile(r"\bear[-\s]?rings?\b|\bstud earrings?\b|\bhoops?\b|\bhuggies?\b|\bear\s?cuffs?\b", re.I)),
    ("watch", re.compile(r"\b(?:wrist)?watch(?:es)?\b|\bsmartwatch\b|\btimepiece\b|\bchronograph\b", re.I)),
    ("necklace", re.compile(r"\bnecklaces?\b|\bpendants?\b|\bchokers?\b|\blockets?\b", re.I)),
    ("bracelet", re.compile(r"\bbracelets?\b|\bbangles?\b|\bwristbands?\b|\bcuff bracelet\b", re.I)),
    ("ring", re.compile(r"(?<!ear)(?<!ear )(?<!key )(?<!key)\brings?\b|\bsignet\b|\bwedding band\b", re.I)),
)


def accessory_from_label(label: str | None) -> str | None:
    text = label or ""
    for cat, rx in _LABEL_RULES:
        if rx.search(text):
            return cat
    return None


# ---------------------------------------------------------------- listing titles (verification)
TITLE_WORDS: dict[str, tuple[str, ...]] = {
    "watch": ("watch", "watches", "wristwatch", "timepiece", "chronograph", "smartwatch"),
    "necklace": ("necklace", "necklaces", "pendant", "choker", "locket", "lariat"),
    "bracelet": ("bracelet", "bracelets", "bangle", "bangles", "cuff"),
    "ring": ("ring", "rings", "signet", "band"),
    "earrings": ("earring", "earrings", "studs", "hoops", "huggies", "huggie"),
}
# Things that share a word with an accessory but aren't one.
NOT_THIS: dict[str, re.Pattern] = {
    "watch": re.compile(r"\b(?:watch\s*(?:band|strap|bracelet|case|winder|box|stand|charger|screen protector)s?|"
                        r"apple watch band|replacement strap)\b", re.I),
    "ring": re.compile(r"\b(?:key\s?rings?|keyrings?|ring\s?lights?|o-?rings?|ring\s?binders?|ring\s?doorbell|"
                       r"napkin rings?|earrings?|ring\s?sling|teething ring)\b", re.I),
    "bracelet": re.compile(r"\bwatch\s*bracelets?\b|\bapple watch\b", re.I),
    "necklace": re.compile(r"\bnecklace\s*(?:stand|display|holder)s?\b", re.I),
    "earrings": re.compile(r"\bearring\s*(?:backs?|holders?|stands?|organizers?)\b", re.I),
}


def title_is_category(title: str, category: str, tokens: set[str]) -> bool | None:
    """True/False for accessory categories; None when the category isn't an accessory."""
    if category not in ACCESSORIES:
        return None
    if NOT_THIS.get(category) and NOT_THIS[category].search(title or ""):
        return False
    words = TITLE_WORDS[category]
    if category == "ring":  # "band" alone is too broad: require ring/signet, or "band" with a ring cue
        return bool(tokens & {"ring", "rings", "signet"}) or ("band" in tokens and bool(tokens & {"wedding", "eternity", "stacking"}))
    return bool(tokens & set(words))


# ---------------------------------------------------------------- appearance-only normalization (perception)
_TONE = (
    (re.compile(r"\brose[-\s]?gold(?:[-\s]?tone)?\b", re.I), "rose-gold-tone"),
    (re.compile(r"\bwhite[-\s]?gold\b|\bplatinum\b", re.I), "silver-tone"),
    (re.compile(r"\byellow[-\s]?gold\b|\bgold(?:en)?(?:[-\s]?tone)?\b", re.I), "gold-tone"),
    (re.compile(r"\bsilver(?:[-\s]?tone)?\b|\bsterling\b|\bsteel(?:[-\s]?tone)?\b", re.I), "silver-tone"),
)
_STONES = (
    (re.compile(r"\bdiamonds?\b|\bcrystals?\b|\bcubic zirconia\b|\bcz\b|\bmoissanite\b", re.I), "clear stone"),
    (re.compile(r"\bemeralds?\b", re.I), "green stone"),
    (re.compile(r"\brub(?:y|ies)\b", re.I), "red stone"),
    (re.compile(r"\bsapphires?\b", re.I), "blue stone"),
    (re.compile(r"\bpearls?\b", re.I), "round beads"),
    (re.compile(r"\b(?:gem\s?stones?|gems?|jewels?)\b", re.I), "stone"),
)
_CLAIMS = re.compile(
    r"\b(?:\d{1,2}\s?k(?:t|arat)?|\d{1,2}\s?ct|karat|carat|925|solid|plated|vermeil|filled|genuine|authentic|real|"
    r"luxury|designer|replica|fake|precious|fine jewelry|swiss made)\b",
    re.I,
)
LUXURY_BRANDS = re.compile(
    r"\b(?:rolex|cartier|tiffany|omega|patek(?:\s+philippe)?|audemars(?:\s+piguet)?|van\s+cleef|bulgari|bvlgari|"
    r"chanel|herm[eè]s|gucci|louis\s+vuitton|dior|chopard|tag\s+heuer|breitling|david\s+yurman|hublot|iwc|"
    r"jaeger[-\s]le[-\s]?coultre|piaget|vacheron|richard\s+mille|panerai|messika|boucheron)\b(?:[-\s]?style)?",
    re.I,
)


def appearance_safe(values: list[str]) -> tuple[list[str], bool]:
    """Rewrite model-written accessory attributes so they only describe appearance. Returns (values, changed)."""
    out: list[str] = []
    changed = False
    for v in values:
        s = v
        for rx, rep in (*_TONE, *_STONES):
            s = rx.sub(rep, s)
        s = _CLAIMS.sub("", s)
        s = LUXURY_BRANDS.sub("", s)
        s = re.sub(r"\btone[-\s]tone\b", "tone", s)
        s = " ".join(s.replace(" ,", ",").split()).strip(" ,-")
        if s != v:
            changed = True
        if s and s.lower() not in {x.lower() for x in out}:
            out.append(s)
    return out, changed


def tone_colors(values: list[str]) -> list[str]:
    """Base hue words for tone values, so 'gold-tone' still matches a shopper's 'gold'."""
    out: list[str] = []
    for v in values:
        t = v.lower()
        base = "gold" if "gold" in t else "silver" if "silver" in t else None
        if base and base not in out:
            out.append(base)
    return out


# ---------------------------------------------------------------- seller claims on listings (results)
SELLER_CLAIMS = re.compile(
    r"\b(?:\d{1,2}\s?k(?:t|arat)?\b|\d{1,2}\s?ct\b|karat|carat|925|sterling|solid gold|gold[-\s]?plated|vermeil|platinum|"
    r"diamonds?|emeralds?|rub(?:y|ies)|sapphires?|pearls?|moissanite|genuine|authentic|certified|swiss made)",
    re.I,
)
SELLER_CLAIMS_WARNING = "Metal, stones and authenticity are the seller's description; ClipCart doesn't verify them."


def seller_claims(*texts: str | None) -> bool:
    return any(t and SELLER_CLAIMS.search(t) for t in texts)


# ---------------------------------------------------------------- ring sizes
_RING_SIZE = re.compile(r"^(?:us\s*)?(?:size\s*)?(\d{1,2})(?:\.(5|25|75))?$", re.I)


def norm_ring_size(raw: str | None) -> str | None:
    """US ring sizes 3–15 with halves/quarters. Returns e.g. '7', '6.5', or None if not a ring size."""
    m = _RING_SIZE.match(" ".join((raw or "").split()))
    if not m:
        return None
    whole = int(m.group(1))
    if not 3 <= whole <= 15:
        return None
    return f"{whole}.{m.group(2)}" if m.group(2) else str(whole)
