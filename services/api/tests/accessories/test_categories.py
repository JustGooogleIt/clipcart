"""Accessory category rules: labels, titles, appearance-only normalization, ring sizes."""

import re

import pytest

from app.categories import (
    accessory_from_label,
    appearance_safe,
    norm_ring_size,
    public_categories,
    seller_claims,
    title_is_category,
    tone_colors,
)


def toks(t):
    return set(re.findall(r"[a-z0-9]+(?:-[a-z0-9]+)?", t.lower()))


@pytest.mark.parametrize("label,cat", [
    ("earring", "earrings"), ("gold hoop earrings", "earrings"), ("stud earrings", "earrings"),
    ("wristwatch", "watch"), ("smartwatch", "watch"), ("necklace or pendant", "necklace"), ("choker", "necklace"),
    ("bangle", "bracelet"), ("finger ring", "ring"), ("signet", "ring"),
    ("key ring", None), ("jacket or coat", None), ("bag", None),
])
def test_detector_labels_map_to_categories(label, cat):
    assert accessory_from_label(label) == cat


@pytest.mark.parametrize("title,cat,ok", [
    ("Seiko 5 Automatic Watch 42mm", "watch", True),
    ("Apple Watch Band 41mm Sport Loop", "watch", False),
    ("Stainless steel watch strap 20mm", "watch", False),
    ("Gold hoop earrings", "ring", False),
    ("Gold hoop earrings", "earrings", True),
    ("Key ring with leather fob", "ring", False),
    ("LED ring light 10in", "ring", False),
    ("Sterling silver signet ring", "ring", True),
    ("Rubber band", "ring", False),
    ("Diamond eternity band", "ring", True),
    ("Tennis bracelet", "bracelet", True),
    ("Watch bracelet links", "bracelet", False),
    ("Layered pendant necklace", "necklace", True),
    ("Earring backs 100 pack", "earrings", False),
    ("Black denim trucker jacket", "jacket", None),  # not an accessory: legacy rules decide
])
def test_listing_titles_match_accessory_categories(title, cat, ok):
    assert title_is_category(title, cat, toks(title)) is ok


def test_appearance_only_normalization_never_keeps_metal_stone_brand_or_authenticity_claims():
    vals, changed = appearance_safe([
        "14k yellow gold links", "Rolex-style crown logo", "diamond pavé bezel", "pearl strand",
        "silver tone", "authentic designer chain", "emerald pendant", "rose gold case", "solid sterling cuff",
    ])
    assert changed
    text = " ".join(vals).lower()
    for banned in ("14k", "gold links", "rolex", "diamond", "pearl", "authentic", "designer", "emerald", "sterling", "solid"):
        assert banned not in text.replace("gold-tone", "").replace("rose-gold-tone", ""), banned
    assert "gold-tone links" in vals and "clear stone pavé bezel" in vals and "round beads strand" in vals
    assert "crown logo" in vals and "green stone pendant" in vals and "rose-gold-tone case" in vals
    assert appearance_safe(["black dial", "round case"]) == (["black dial", "round case"], False)


def test_tone_colors_and_seller_claims():
    assert tone_colors(["gold-tone", "rose-gold-tone", "silver-tone", "black"]) == ["gold", "silver"]
    assert seller_claims("14K Gold Diamond Tennis Bracelet") and seller_claims(None, "925 sterling silver")
    assert seller_claims("Authentic Rolex Submariner") and not seller_claims("Gold-tone hoop earrings")


@pytest.mark.parametrize("raw,out", [("7", "7"), ("6.5", "6.5"), ("US 8", "8"), ("size 10", "10"), ("9.25", "9.25"),
                                     ("2", None), ("16", None), ("M", None), ("", None)])
def test_ring_sizes(raw, out):
    assert norm_ring_size(raw) == out


def test_public_categories_keep_legacy_values_and_size_rules():
    cats = {c["id"]: c for c in public_categories()}
    assert {"jacket", "top", "pants", "bag", "other"} <= set(cats)
    assert cats["jacket"]["sizeRule"] == "clothing" and cats["bag"]["sizeRule"] == "clothing"  # bag unchanged
    assert cats["watch"]["sizeRule"] == "none" and cats["ring"]["sizeRule"] == "ring"
    assert {cats[c]["family"] for c in ("necklace", "bracelet", "ring", "earrings")} == {"jewelry"}
