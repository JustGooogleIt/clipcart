"""Deterministic style tags from listing text. The listing's own words are the evidence.

Keyword rules only: a tag needs a phrase that names it (or a garment type that is the style itself, like
"chore coat" for workwear). Negated phrases ("not vintage", "non-vintage") never produce a tag. Brands never
imply a style here: that would be ClipCart's opinion, not a listing fact.
"""

from __future__ import annotations

import re

STYLE_TAGS = (
    "vintage", "minimalist", "streetwear", "workwear", "preppy", "athleisure", "y2k", "outdoor", "techwear",
    "western", "bohemian", "classic", "grunge", "punk",
)

_RULES: dict[str, str] = {
    "vintage": r"vintage|retro|(?:19)?[5-9]0s|deadstock",
    "minimalist": r"minimalist|minimal(?:ist)? design|clean[-\s]lined?",
    "streetwear": r"streetwear|street[-\s]?style|skate(?:wear|board)?",
    "workwear": r"workwear|chore (?:coat|jacket)|carpenter|duck canvas|utility (?:jacket|pants|vest)",
    "preppy": r"preppy|oxford shirt|cable[-\s]knit|rugby shirt",
    "athleisure": r"athleisure|track (?:jacket|pants|suit)|joggers?|tech fleece",
    "y2k": r"y2k",
    "outdoor": r"gorpcore|outdoor|hiking|trail|technical shell",
    "techwear": r"techwear",
    "western": r"western|cowboy|rodeo",
    "bohemian": r"boho|bohemian",
    "classic": r"classic|timeless|heritage",
    "grunge": r"grunge",
    "punk": r"punk|studded",
}
_NEG = r"(?:not|non|no|isn'?t|without|never)[-\s]+(?:\w+[-\s]+)?"
_COMPILED = {tag: (re.compile(rf"\b(?:{rx})\b", re.I), re.compile(rf"\b{_NEG}(?:{rx})\b", re.I)) for tag, rx in _RULES.items()}
# "vintage wash" on new jeans is still a vintage *look*; "vintage-inspired" too. Both count as the style.


def extract(text: str | None) -> list[tuple[str, str]]:
    """Return [(tag, excerpt)] for tags stated (and not negated) in ``text``."""
    t = " ".join((text or "").split())
    out: list[tuple[str, str]] = []
    for tag, (pos, neg) in _COMPILED.items():
        hits = [m for m in pos.finditer(t)]
        negated = {m.end() for m in neg.finditer(t)}
        for m in hits:
            if m.end() in negated:
                continue
            a, b = max(0, m.start() - 25), min(len(t), m.end() + 25)
            out.append((tag, t[a:b].strip()))
            break
    return out


def listing_facts(title: str | None, material: str | None = None, condition: str | None = None) -> list[dict]:
    """StyleTagFact dicts for a listing: {tag, field, excerpt}."""
    facts: list[dict] = []
    seen: set[str] = set()
    for field, text in (("title", title), ("material", material)):
        for tag, excerpt in extract(text):
            if tag not in seen:
                seen.add(tag)
                facts.append({"tag": tag, "field": field, "excerpt": excerpt[:120]})
    return facts


def normalize_tag(value: str | None) -> str | None:
    v = " ".join(str(value or "").lower().replace("-", " ").split())
    v = {"minimal": "minimalist", "street": "streetwear", "boho": "bohemian", "gorpcore": "outdoor", "retro": "vintage",
         "athletic": "athleisure", "work wear": "workwear", "street wear": "streetwear"}.get(v, v)
    return v if v in STYLE_TAGS else None
