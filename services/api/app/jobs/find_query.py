"""Query normalization and helpers for find-in-video (kept free of AppState)."""

from __future__ import annotations

import re

_LEAD = re.compile(
    r"^\s*(?:please\s+)?(?:can you\s+|could you\s+)?"
    r"(?:find|look for|search for|show|get|locate)\s+"
    r"(?:me\s+)?(?:the|a|an|that|this)?\s*",
    re.IGNORECASE,
)
_VAGUE = frozenset(
    {
        "thing", "things", "object", "objects", "item", "items", "stuff", "something",
        "one", "piece", "it", "that", "this", "whatever", "anything",
    }
)
_STOP = frozenset({"the", "a", "an", "and", "or", "with", "of", "in", "on", "by", "to", "for"})
# Concrete anchors that make a short query searchable enough to attempt.
_ANCHORS = frozenset(
    {
        "jacket", "coat", "blazer", "hoodie", "sweater", "shirt", "tee", "top", "pants", "jeans",
        "trousers", "shorts", "skirt", "dress", "bag", "purse", "tote", "backpack", "hat", "cap",
        "shoe", "sneaker", "boot", "watch", "glasses", "sunglasses", "scarf", "belt",
        "plant", "monstera", "flower", "vase", "painting", "poster", "print", "frame", "lamp",
        "chair", "sofa", "table", "bottle", "cup", "phone", "laptop", "camera", "guitar",
        "denim", "leather", "trucker", "bomber", "biker",
    }
)
_APPAREL = {
    "jacket": (
        "jacket", "coat", "blazer", "parka", "bomber", "trucker", "windbreaker", "puffer",
        "anorak", "shacket", "trench", "peacoat", "biker", "moto", "vest", "gilet",
    ),
    "top": (
        "shirt", "tee", "t-shirt", "top", "blouse", "sweater", "hoodie", "sweatshirt",
        "cardigan", "polo", "tank", "jersey", "crewneck", "pullover", "henley",
    ),
    "pants": ("pants", "jeans", "trousers", "chinos", "shorts", "leggings", "skirt", "cargos", "joggers"),
    "bag": ("bag", "handbag", "tote", "backpack", "purse", "clutch", "satchel", "crossbody", "duffle"),
}


def normalize_find_query(text: str) -> str:
    """Keep the shopper's descriptive phrase; only strip the 'find me the' lead-in."""
    raw = " ".join((text or "").split())
    if not raw:
        return ""
    stripped = _LEAD.sub("", raw).strip(" .,!?:;")
    return stripped or raw


# One-word asks that are still worth attempting (common shoppable nouns).
_SINGLE_OK = frozenset({"jacket", "jeans", "hoodie", "sneakers", "backpack", "handbag"})


def query_too_vague(query: str) -> str | None:
    """Return a shopper-facing reason if the query is too thin to search well."""
    words = [w.lower() for w in re.findall(r"[a-z0-9]+(?:-[a-z0-9]+)?", query or "")]
    content = [w for w in words if w not in _STOP]
    if not content:
        return "Say what to find — e.g. the tall monstera in the speckled ceramic pot."
    if len(content) == 1:
        if content[0] in _VAGUE:
            return "“Thing” is too vague. Name the object and 2–3 visible details (color, material, shape)."
        if content[0] not in _SINGLE_OK:
            return (
                f"“{query}” is too short for a good search. Add visible details "
                "(color, material, pattern, pot/frame/hardware) — we keep the full description."
            )
    if len(content) <= 2 and not any(w in _ANCHORS for w in content):
        return (
            f"“{query}” is thin for search. Add distinctive details "
            "(color, material, pattern, container/frame) so we can match listings."
        )
    return None


def detect_classes_for_query(query: str) -> list[str]:
    """Open-vocab class list: full phrase first, then shorter fallbacks for recall."""
    q = " ".join((query or "").split())
    if not q:
        return []
    words = q.split()
    out = [q]
    if len(words) > 6:
        out.append(" ".join(words[-5:]))
        out.append(" ".join(words[:5]))
    if len(words) > 3:
        out.append(" ".join(words[-3:]))
    # Apparel shorthand helps Perceptron when the shopper wrote a long sentence.
    lower = q.lower()
    for cat, nouns in _APPAREL.items():
        hit = next((n for n in nouns if re.search(rf"\b{re.escape(n)}\b", lower)), None)
        if hit:
            # Keep a mid-length product phrase if fabric/type words are present.
            bits = [w for w in words if w.lower() in {hit, "denim", "leather", "suede", "fleece", "quilted", "vintage", "washed", "distressed", "indigo", "black", "blue", "white", "green", "brown"} or w.lower() in nouns]
            if bits:
                out.append(" ".join(dict.fromkeys(bits))[:80])
            out.append(hit)
            break
    return list(dict.fromkeys(c for c in out if len(c.strip()) >= 2))[:4]


def infer_category(query: str, what: str | None = None) -> str:
    """Map find results onto apparel categories when the ask/description is clearly clothing."""
    blob = f"{what or ''} {query or ''}".lower()
    for cat, nouns in _APPAREL.items():
        if any(re.search(rf"\b{re.escape(n)}\b", blob) for n in nouns):
            return cat
    return "other"


def compose_search_description(
    query: str,
    what: str | None,
    search_desc: str | None,
    detail_bits: list[str] | None = None,
) -> str:
    """Build a dense catalog line — never drop the shopper's specifics."""
    parts: list[str] = []
    for p in (search_desc, what, query):
        p = " ".join((p or "").split())
        if not p:
            continue
        if not parts:
            parts.append(p)
            continue
        # Append if it adds words we don't already have.
        have = set(parts[0].lower().split())
        extra = [w for w in p.lower().split() if w not in have and w not in _STOP]
        if len(extra) >= 2 or (p.lower() not in parts[0].lower() and len(p.split()) >= 4):
            parts.append(p)
    if detail_bits:
        for d in detail_bits[:4]:
            d = " ".join((d or "").split())
            if d and d.lower() not in " ".join(parts).lower():
                parts.append(d)
    blob = " — ".join(parts) if parts else query
    # Guarantee shopper query tokens survive into the catalog string.
    q = " ".join((query or "").split())
    if q and q.lower() not in blob.lower():
        blob = f"{blob}. Asked for: {q}"
    # Reject useless short blobs by appending query.
    if len(blob.split()) < 5 and q and q.lower() != blob.lower():
        blob = f"{blob} {q}".strip()
    return blob[:800]
