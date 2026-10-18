"""Rule-based parser from shopper text to a validated PreferencePatch (FR14).

Only fields the text mentions are set; everything else is preserved by the
session patch. Unrecognized text produces no change rather than a guess.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.contracts import PreferencePatch, Preferences, SizePref

from .rules import ALPHA_SIZES, _COLOR_WORDS, norm_size

_MATERIALS = {
    "leather", "suede", "wool", "polyester", "nylon", "cotton", "silk", "fur", "down", "acrylic",
    "cashmere", "linen", "denim", "rayon", "viscose", "spandex", "pvc", "vinyl", "fleece",
}
_NUM = r"\$?\s*(\d{1,5}(?:\.\d{1,2})?)\s*(?:usd|dollars|bucks)?"


@dataclass
class Interpretation:
    patch: PreferencePatch
    changes: list[str] = field(default_factory=list)
    selection_hint: str | None = None


def _money_minor(s: str) -> int:
    return int(round(float(s) * 100))


def parse_refinement(text: str, current: Preferences) -> Interpretation:
    t = " " + " ".join(text.lower().replace("’", "'").split()) + " "
    upd: dict = {}
    changes: list[str] = []

    # Budget
    if re.search(r"\b(no budget|any price|price doesn't matter|remove (the )?budget)\b", t):
        upd["max_item_price_minor"] = None
        changes.append("budget removed")
    else:
        m = re.search(
            rf"\b(?:under|below|less than|max(?:imum)?|at most|up to|no more than|budget(?: of| is)?|cheaper than|within)\s*{_NUM}",
            t,
        ) or re.search(rf"{_NUM}\s*(?:or less|max|tops|or under)\b", t)
        if m:
            upd["max_item_price_minor"] = _money_minor(m.group(1))
            changes.append(f"budget under ${m.group(1)}")

    # Size
    size_m = re.search(
        r"\b(?:size|in (?:a |an )?|fits? (?:a )?)\s*(xxs|xs|s|m|l|xl|xxl|xxxl|2xl|3xl|small|medium|large|extra small|extra large|x-small|x-large|\d{1,2}(?:\.5)?)\b",
        t,
    )
    if size_m:
        raw, system = norm_size(size_m.group(1))
        upd["size"] = SizePref(raw=raw, system="alpha" if system == "alpha" else ("numeric" if system == "numeric" else None))
        changes.append(f"size {raw}")
    elif re.search(r"\b(any size|no size)\b", t):
        upd["size"] = None
        changes.append("size cleared")

    # Materials: exclusions and re-allowing
    excluded = list(current.excluded_materials)
    touched = False
    for mat in _MATERIALS:
        if re.search(rf"\b(?:no|without|not|avoid|exclude|non|nothing in)[\s-]+(?:real |genuine )?{mat}\b", t) or re.search(
            rf"\b{mat}[\s-]free\b", t
        ):
            if mat not in excluded:
                excluded.append(mat)
                changes.append(f"exclude {mat}")
            touched = True
        elif re.search(rf"\b{mat} (?:is )?(?:fine|ok|okay|allowed)\b", t) and mat in excluded:
            excluded.remove(mat)
            changes.append(f"allow {mat}")
            touched = True
    if touched:
        upd["excluded_materials"] = excluded

    # Colors (a material word like 'denim' is a color only when not excluded)
    if re.search(r"\b(any colou?r)\b", t):
        upd["colors"] = []
        changes.append("any color")
    else:
        found = [c for c in _COLOR_WORDS if re.search(rf"\b(?:in|color|colour|a|an|different color:?)\s+{c}\b", t)
                 or re.search(rf"\b{c} (?:one|version|instead|color|colour)\b", t)]
        found = [("gray" if c == "grey" else c) for c in found]
        found = [c for c in dict.fromkeys(found) if c not in upd.get("excluded_materials", [])]
        if found:
            upd["colors"] = found
            changes.append("color " + ", ".join(found))

    # Condition
    if re.search(r"\b(new only|brand new|only new|new condition)\b", t):
        upd["condition"] = "new"
        changes.append("new only")
    elif re.search(r"\b(used only|pre-?owned only|second-?hand only)\b", t):
        upd["condition"] = "used"
        changes.append("used only")
    elif re.search(r"\b(used is fine|pre-?owned is fine|any condition|new or used)\b", t):
        upd["condition"] = "any"
        changes.append("any condition")

    hint = None
    if re.search(r"\b(different|another|other) (one|garment|item|jacket|top|pants|bag)\b", t):
        hint = "Pick a different garment in the tray to change the selection."
    return Interpretation(patch=PreferencePatch(**upd), changes=changes, selection_hint=hint)


def apply_patch(current: Preferences, patch: PreferencePatch) -> Preferences:
    data = current.model_dump()
    for k in patch.model_fields_set:
        data[k] = getattr(patch, k)
    return Preferences.model_validate(data)


__all__ = ["Interpretation", "parse_refinement", "apply_patch", "ALPHA_SIZES"]
