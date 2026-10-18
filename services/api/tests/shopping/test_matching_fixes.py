"""Deterministic matching fixes from the Jev comparison (no model involved)."""

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from app.contracts import Listing, Preferences, SizePref
from app.shopping.rules import (
    GarmentProfile,
    check_constraints,
    explicitly_womens,
    identity_tier,
    section_for,
    title_matches_category,
)

EVIDENCE = Path(__file__).resolve().parents[4] / "fixtures" / "research" / "manual" / "grokbot_four_jackets_2026-10-17.json"


def listing(title: str, brand: str | None = None) -> Listing:
    return Listing(
        id="x", offer_key="x", provider="manual", provider_listing_id="x", product_id=None, variant_id=None,
        retailer="unknown", source_kind="retailer", canonical_url="https://shop.example.com/x", image_urls=[],
        title=title, brand=brand, price=None, price_basis="unknown", seller_visibility="unknown", shipping_minor=None,
        condition="unknown", size=None, sizes_in_stock=None, availability="unknown", material_text=None,
        color_text=None, checked_at=datetime.now(timezone.utc), detail_checked=False, evidence_ids=[], mode="fixture",
    )


@pytest.mark.parametrize("title", ["Alpha Industries MA-1", "Alpha Industries MA1 Slim Fit", "MA 1 in Black",
                                   "Nylon Flight Jacket", "Alpha Industries MA-1 Flight Jacket"])
def test_ma1_and_flight_jacket_pass_jacket_gate(title):
    assert title_matches_category(title, "jacket")


@pytest.mark.parametrize("title", ["Mama 1 Tote", "MA-10 Sneaker", "Flight Bag", "Maxi Dress"])
def test_gate_does_not_overmatch(title):
    assert not title_matches_category(title, "jacket")


@pytest.mark.parametrize("title,expected", [
    ("Albion Fit black bomber (women's)", True), ("Womens Bomber", True), ("Women Bomber Jacket", True),
    ("Ladies' quilted jacket", True), ("WMNS Satin Bomber", True), ("Albion Fit black bomber (women’s)", True),
    ("Womenswear-inspired bomber", False), ("Black Nylon Bomber", False), ("Men's Bomber", False),
])
def test_explicit_womens_detection(title, expected):
    assert explicitly_womens(title) is expected


def test_womens_item_needs_checking_when_fit_unspecified():
    checks = check_constraints(listing("Albion Fit black bomber (women's)"), Preferences())
    fit = [c for c in checks if c.constraint == "fit"]
    assert fit and fit[0].state == "unknown" and section_for(checks) == "needs_checking"


def test_size_m_alone_never_implies_fit():
    checks = check_constraints(listing("Black Nylon Bomber Jacket"), Preferences(size=SizePref(raw="M")))
    assert not [c for c in checks if c.constraint == "fit"]


def test_manual_grokbot_evidence_matches_expected_decisions():
    ev = json.loads(EVIDENCE.read_text())
    assert "MANUAL RESEARCH EVIDENCE" in ev["label"]
    assert all(r["price"] is None and r["productUrl"] is None for r in ev["results"])  # nothing invented
    prof = GarmentProfile(category="jacket", colors=["black", "gold"], visible_text=[])
    prefs = Preferences(size=SizePref(raw="M", system="alpha"))
    out = {}
    for r in ev["results"]:
        L = listing(r["title"], r["brand"])
        checks = check_constraints(L, prefs)
        out[r["key"]] = (title_matches_category(L.title, "jacket"), identity_tier(L, prof)[0], section_for(checks),
                         {c.constraint: c.state for c in checks})
    assert all(gate and tier == "similar" and sec == "needs_checking" for gate, tier, sec, _ in out.values())
    assert out["albion_fit"][3]["fit"] == "unknown"
    assert "fit" not in out["sacred_bones"][3] and "fit" not in out["karl_lagerfeld"][3]
    assert out["alpha_ma1"][0] is True  # previously set aside as "not a jacket"
