"""Accessory search rules: size rules, identity cap, queries."""

from datetime import datetime, timezone

from app.contracts import Listing, Preferences, SizePref, SizeStock
from app.shopping.rules import GarmentProfile, check_constraints, identity_tier
from app.shopping.workers import rule_queries


def listing(title, *, sizes=None, brand=None, style_code=None, material=None):
    return Listing(
        id="l", offer_key="k", provider="solescout", provider_listing_id="p", product_id=None, variant_id=None,
        retailer="R", source_kind="retailer", canonical_url="https://r.example/p", image_urls=[], title=title, brand=brand,
        price=None, price_basis="unknown", seller_visibility="named", shipping_minor=None, condition="unknown", size=None,
        sizes_in_stock=None if sizes is None else [SizeStock(raw=s, lowest_price=None) for s in sizes], availability="unknown",
        material_text=material, color_text=None, style_code=style_code, checked_at=datetime.now(timezone.utc),
        detail_checked=True, evidence_ids=[], mode="live",
    )


PREFS = Preferences(size=SizePref(raw="M"), ring_size=SizePref(raw="7"))


def kinds(checks):
    return {c.constraint: c.state for c in checks}


def test_clothing_size_never_applies_to_watches_or_jewelry():
    for cat in ("watch", "necklace", "bracelet", "earrings"):
        assert "size" not in kinds(check_constraints(listing("Gold-tone thing", sizes=["S", "L"]), PREFS, cat))
    assert kinds(check_constraints(listing("Black jacket", sizes=["S", "L"]), PREFS, "jacket"))["size"] == "violated"
    assert kinds(check_constraints(listing("Black jacket", sizes=["S", "L"]), PREFS))["size"] == "violated"  # legacy call


def test_ring_size_applies_to_rings_only():
    assert kinds(check_constraints(listing("Signet ring", sizes=["6", "7", "8"]), PREFS, "ring"))["ring size"] == "satisfied"
    assert kinds(check_constraints(listing("Signet ring", sizes=["5", "6"]), PREFS, "ring"))["ring size"] == "violated"
    assert kinds(check_constraints(listing("Signet ring", sizes=["S/M"]), PREFS, "ring"))["ring size"] == "unknown"
    assert kinds(check_constraints(listing("Signet ring"), PREFS, "ring"))["ring size"] == "unknown"
    assert "ring size" not in kinds(check_constraints(listing("Hoop earrings", sizes=["7"]), PREFS, "earrings"))


def test_womens_label_does_not_push_jewelry_into_needs_checking():
    assert "fit" not in kinds(check_constraints(listing("Women's gold-tone necklace"), PREFS, "necklace"))
    assert kinds(check_constraints(listing("Women's denim jacket"), PREFS, "jacket"))["fit"] == "unknown"


def test_accessory_identity_is_capped_at_similar_even_with_matching_lettering():
    prof = GarmentProfile(category="watch", visible_text=["ROLEX", "126610LN"], colors=["silver-tone"])
    tier, reason = identity_tier(listing("Rolex Submariner Date watch", brand="Rolex", style_code="126610LN"), prof)
    assert tier == "similar" and "authenticity" in reason
    jacket = GarmentProfile(category="jacket", visible_text=["LEVIS"])
    assert identity_tier(listing("Levis trucker jacket", brand="Levis"), jacket)[0] == "likely"  # unchanged for garments


def test_accessory_queries_use_tone_and_form_never_lettering():
    prof = GarmentProfile(category="earrings", colors=["gold-tone"], cut=["hoop"], visible_text=["CARTIER"],
                          details=["clear stone accents"])
    qs = rule_queries("exact", prof, Preferences())
    assert qs[0] == "gold tone hoop earrings"
    assert not any("cartier" in q for q in qs)
    alt = rule_queries("alternative", prof, Preferences(colors=["silver"]))
    assert "silver tone earrings" in alt


def test_tone_counts_as_gold_for_color_matching():
    assert GarmentProfile(category="ring", colors=["gold-tone"]).hue_colors() == ["gold"]
