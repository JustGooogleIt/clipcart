import time
from datetime import datetime, timezone

import pytest

from app.contracts import Preferences, SearchBudget, SizePref
from app.shopping.budget import BudgetExceeded, BudgetLedger
from app.shopping.canonical import safe_url, to_evidence, to_listing
from app.shopping.refine import apply_patch, parse_refinement
from app.shopping.rules import GarmentProfile, check_constraints, identity_tier, price_phrase, relevance, section_for
from app.shopping.workers import rule_queries

from .fakes import FakeCatalog, item


def detail_listing(slug="x", title="Black Bomber Jacket", price=90, **d):
    fc = FakeCatalog([item(slug, title, price, brand=d.pop("brand", None))], {slug: d})
    r = fc.get_details(slug)
    ev = [to_evidence(e) for e in r.evidence]
    return to_listing(r.listings[0], result_mode=r.mode, evidence=ev, diagnostics=r.diagnostics, detail=True)


def test_aggregate_price_never_attributed_to_named_store():
    L = detail_listing(stores=[{"name": "GOAT", "url": "https://www.goat.com/x", "price_usd": None, "sizes_in_stock": ["M"]}],
                       hidden=2, carrying=3, sizes=["M"])
    assert L.retailer == "SoleScout" and L.source_kind == "aggregator"
    assert L.price_basis == "aggregate_lowest" and L.seller_visibility == "hidden"
    assert L.store_offers[0].retailer == "GOAT" and L.store_offers[0].price is None
    phrase = price_phrase(L)
    assert "via SoleScout" in phrase and "GOAT" not in phrase and "not named" in phrase


def test_named_seller_only_when_store_price_equals_lowest_and_nothing_hidden():
    L = detail_listing(stores=[{"name": "Shop", "url": "https://shop.example/x", "price_usd": 90}], hidden=0, carrying=1)
    assert L.seller_visibility == "named"


def test_fixture_keeps_capture_time_not_now():
    item_ = {"offerKey": "solescout:a", "provider": "solescout", "providerListingId": "a", "canonicalUrl": "https://solescout.ai/product/a",
             "title": "Tee", "price": {"amountMinor": 100, "currency": "USD"}, "checkedAt": datetime.now(timezone.utc).isoformat(),
             "evidenceIds": ["ev1"], "mode": "fixture"}
    ev = to_evidence({"id": "ev1", "sourceType": "merchant_api", "retrievedAt": "2026-10-17T20:40:36Z", "claims": []})
    L = to_listing(item_, result_mode="fixture", evidence=[ev])
    assert L.checked_at.isoformat().startswith("2026-10-17T20:40:36") and L.mode == "fixture"
    assert any("fixture" in w.lower() for w in L.warnings)


@pytest.mark.parametrize("u", ["http://x.com/a", "javascript:alert(1)", "https://user:pw@x.com", "//x.com", None, 5])
def test_unsafe_urls_rejected(u):
    assert safe_url(u) is None


def prefs(**kw):
    return Preferences(**kw)


def states(L, p):
    return {c.constraint: c.state for c in check_constraints(L, p)}


def test_budget_states():
    L = detail_listing(price=90, sizes=["M"])
    assert states(L, prefs(max_item_price_minor=10000))["budget"] == "satisfied"
    assert states(L, prefs(max_item_price_minor=8000))["budget"] == "violated"
    assert states(L, prefs(max_item_price_minor=8000, currency="EUR"))["budget"] == "unknown"


def test_size_states_never_convert_systems():
    L = detail_listing(sizes=["S", "M"])
    assert states(L, prefs(size=SizePref(raw="m")))["size"] == "satisfied"
    assert states(L, prefs(size=SizePref(raw="XL")))["size"] == "violated"
    N = detail_listing(sizes=["30", "32"])
    assert states(N, prefs(size=SizePref(raw="M")))["size"] == "unknown"  # no M<->32 mapping
    E = detail_listing(sizes=[])
    assert states(E, prefs(size=SizePref(raw="M")))["size"] == "unknown"  # empty list is not out of stock


def test_material_exclusion_needs_evidence():
    assert states(detail_listing(title="Leather Biker Jacket"), prefs(excluded_materials=["leather"]))["no leather"] == "violated"
    assert states(detail_listing(title="Faux Leather Bomber"), prefs(excluded_materials=["leather"]))["no leather"] == "unknown"
    assert states(detail_listing(title="Nylon Bomber"), prefs(excluded_materials=["leather"]))["no leather"] == "unknown"


def test_unknowns_go_to_needs_checking_not_primary():
    L = detail_listing(sizes=["M"])
    assert section_for(check_constraints(L, prefs(max_item_price_minor=10000, size=SizePref(raw="M")))) == "primary"
    assert section_for(check_constraints(L, prefs(excluded_materials=["wool"]))) == "needs_checking"
    assert section_for(check_constraints(L, prefs(max_item_price_minor=100))) == "excluded"


def test_visual_resemblance_never_verified():
    L = detail_listing(title="Acme Bomber Jacket", brand="Acme", style_code="AC-12345")
    assert identity_tier(L, GarmentProfile(category="jacket", colors=["black"]))[0] == "similar"
    assert identity_tier(L, GarmentProfile(category="jacket", visible_text=["ACME"]))[0] == "likely"
    assert identity_tier(L, GarmentProfile(category="jacket", visible_text=["ac12345"]))[0] == "verified"


def test_rule_queries_prefer_denim_over_bare_blue_jacket():
    prof = GarmentProfile(
        category="jacket",
        colors=["blue"],
        cut=["trucker", "button front"],
        details=["denim weave", "chest pockets", "metal rivets", "faded wash"],
        description="blue denim trucker jacket",
    )
    qs = rule_queries("exact", prof, prefs())
    joined = " | ".join(qs)
    assert qs[0] in {"denim trucker jacket", "jean jacket", "denim trucker"}, qs
    assert any("denim" in q and "trucker" in q for q in qs), qs
    assert any("jean" in q for q in qs), qs  # SoleScout synonym
    assert not any(q.strip() == "blue jacket" for q in qs), qs
    assert "denim" in joined


def test_relevance_ranks_denim_above_random_blue_jacket():
    from app.shopping.rules import fabric_match

    prof = GarmentProfile(
        category="jacket",
        colors=["blue"],
        cut=["trucker"],
        details=["denim"],
        description="denim trucker",
    )
    denim = detail_listing(slug="d", title="Blue Denim Trucker Jacket")
    jean = detail_listing(slug="j", title="Vintage Blue Jean Jacket")
    track = detail_listing(slug="t", title="Blue Track Jacket")
    leather = detail_listing(slug="l", title="Blue Leather Biker Jacket")
    assert fabric_match(denim, prof) and fabric_match(jean, prof)
    assert not fabric_match(track, prof)
    assert relevance(denim, prof, prefs()) > relevance(track, prof, prefs())
    assert relevance(jean, prof, prefs()) > relevance(track, prof, prefs())
    assert relevance(denim, prof, prefs()) > relevance(leather, prof, prefs())


def test_descriptors_pull_from_all_attribute_fields():
    prof = GarmentProfile(
        category="jacket",
        colors=["indigo", "blue"],
        pattern=["faded"],
        cut=["trucker", "oversized"],
        details=["denim weave", "chest pockets", "copper rivets"],
    )
    d = prof.descriptors()
    assert "denim" in d and "trucker" in d and "blue" in d
    assert any(x in d for x in ("faded", "oversized", "pockets", "rivets", "indigo"))


def test_refinement_preserves_unspecified_fields():
    p = Preferences()
    i = parse_refinement("Find that jacket under $120, in medium, with no leather.", p)
    p = apply_patch(p, i.patch)
    assert (p.max_item_price_minor, p.size.raw, p.excluded_materials) == (12000, "M", ["leather"])
    p2 = apply_patch(p, parse_refinement("actually, under $80", p).patch)
    assert p2.max_item_price_minor == 8000 and p2.size.raw == "M" and p2.excluded_materials == ["leather"]
    p3 = apply_patch(p2, parse_refinement("in black instead", p2).patch)
    assert p3.colors == ["black"] and p3.max_item_price_minor == 8000
    assert parse_refinement("hello", p3).changes == []


def test_budget_ledger_caps_and_deadline():
    led = BudgetLedger(SearchBudget(max_tool_calls=3, max_detail_calls=1), time.monotonic() + 30)
    led.take_tool()
    led.take_tool(detail=True)
    with pytest.raises(BudgetExceeded):
        led.take_tool(detail=True)
    led.take_tool(cached=True)  # cache hit: no paid budget
    led.take_tool()
    with pytest.raises(BudgetExceeded):
        led.take_tool()
    expired = BudgetLedger(SearchBudget(), time.monotonic() - 1)
    with pytest.raises(BudgetExceeded):
        expired.take_tool()
