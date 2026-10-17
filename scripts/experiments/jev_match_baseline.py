"""Offline baseline for the Jev matching experiment (no network, no model calls).

Runs the four manual Grok Bot jacket examples through ClipCart's *unchanged*
deterministic rules and prints them next to the expected decisions, which
were written before any Jev output existed. Candidate facts are limited to
what the shopper reported; unknown fields stay null.

    services/api/.venv/bin/python scripts/experiments/jev_match_baseline.py
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "services" / "api"))

from app.contracts import Listing, Preferences, SizePref  # noqa: E402
from app.shopping.rules import (  # noqa: E402
    GarmentProfile,
    check_constraints,
    identity_tier,
    relevance,
    section_for,
    title_matches_category,
)

# Live Perceptron mk1.5 observation of the black bomber photo (request be94e617..., 2026-10-17).
OBSERVED = GarmentProfile(
    category="jacket",
    colors=["black", "gold"],
    pattern=["solid"],
    cut=["bomber jacket silhouette", "mid-length", "ribbed collar", "full front zipper closure"],
    details=["two side zip pockets with gold zippers", "central front zipper with gold pull tab",
             "small embroidered logo on left chest (three-leaf clover shape)", "ribbed cuffs and hem"],
    visible_text=[],  # Perceptron read no text or logo lettering
)
# Shopper context: size M requested; fit category (men's/women's) not stated.
PREFS = Preferences(size=SizePref(raw="M", system="alpha"))

# Only the facts the shopper reported for each manual Grok Bot result.
CANDIDATES = [
    {"key": "sacred_bones", "title": "Sacred Bones gold-logo bomber", "brand": "Sacred Bones", "retailer": None,
     "facts": ["gold logo", "bomber"], "gender": None, "size_evidence": None},
    {"key": "albion_fit", "title": "Albion Fit black bomber (women's)", "brand": "Albion Fit", "retailer": None,
     "facts": ["black", "bomber", "women's item"], "gender": "women", "size_evidence": None},
    {"key": "alpha_ma1", "title": "Alpha Industries MA-1", "brand": "Alpha Industries", "retailer": None,
     "facts": ["MA-1"], "gender": None, "size_evidence": None},
    {"key": "karl_lagerfeld", "title": "Karl Lagerfeld jacket", "brand": "Karl Lagerfeld", "retailer": "Farfetch",
     "facts": ["Farfetch listing", "size not verified"], "gender": None, "size_evidence": "unverified"},
]

# Written before any Jev output: what a careful reviewer should decide from this evidence alone.
EXPECTED = {
    "sacred_bones": {"identity": "similar", "recommend": "needs_checking",
                     "must_flag": ["no exact-match evidence (logo/brand differ from observed trefoil-shaped logo)",
                                   "side zip pockets not evidenced", "color not stated"]},
    "albion_fit": {"identity": "similar", "recommend": "needs_checking",
                   "must_flag": ["women's item while shopper fit category is unknown", "side zip pockets not evidenced"]},
    "alpha_ma1": {"identity": "similar", "recommend": "needs_checking",
                  "must_flag": ["no exact-match evidence", "side zip pockets not evidenced", "color not stated"]},
    "karl_lagerfeld": {"identity": "similar", "recommend": "needs_checking",
                       "must_flag": ["size M not verified", "no exact-match evidence", "color not stated"]},
}


def to_listing(c: dict) -> Listing:
    return Listing(
        id=c["key"], offer_key=c["key"], provider="manual_grok_bot", provider_listing_id=c["key"], product_id=None,
        variant_id=None, retailer=c["retailer"] or "unknown", source_kind="retailer", canonical_url="https://example.invalid/",
        image_urls=[], title=c["title"], brand=c["brand"], price=None, price_basis="unknown", seller_visibility="unknown",
        shipping_minor=None, condition="unknown", size=None, sizes_in_stock=None, availability="unknown",
        material_text=None, color_text=None, checked_at=datetime.now(timezone.utc), detail_checked=False,
        evidence_ids=[], mode="fixture",
    )


def main() -> None:
    rows = []
    for c in CANDIDATES:
        L = to_listing(c)
        checks = check_constraints(L, PREFS)
        tier, reason = identity_tier(L, OBSERVED)
        gate = title_matches_category(L.title, OBSERVED.category)
        sec = section_for(checks) if gate else "set_aside_off_category"
        text = (L.title + " " + " ".join(c["facts"])).lower()
        flags = {
            "women_item_vs_unknown_fit": False,  # no gender/fit rule exists in the verifier
            "side_zips_checked": False,  # details only feed a keyword-overlap relevance score
            "size_unknown": any(k.constraint == "size" and k.state == "unknown" for k in checks),
            "exact_blocked": tier != "verified",
        }
        rows.append({
            "candidate": c["key"], "title": c["title"], "categoryGate": gate, "identity": tier, "identityReason": reason,
            "relevance": relevance(L, OBSERVED, PREFS), "section": sec,
            "checks": {k.constraint: k.state for k in checks}, "flags": flags,
            "expected": EXPECTED[c["key"]], "mentionsWomen": "women" in text,
        })
    rows.sort(key=lambda r: -r["relevance"])
    print(json.dumps(rows, indent=2))


if __name__ == "__main__":
    main()
