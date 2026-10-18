"""Research v2: normalized fields, offer comparison, SoleScout fallback, manual import, style hints."""

from datetime import datetime, timedelta, timezone

import pytest
from api.conftest import H, bootstrap, new_client, wait
from shopping.fakes import FakeCatalog, item

from app.contracts import Preferences, SizePref
from app.research.urlsafety import check_url
from app.research.verify import verify_submission

NOW = datetime.now(timezone.utc)


def nodns(u):
    return check_url(u, resolve=False)


def sub(**kw):
    base = {"retailer": "Shop", "productUrl": "https://shop-store.com/p1", "title": "Black Nylon Bomber Jacket",
            "matchType": "similar", "observedAt": NOW.isoformat()}
    return {**base, **kw}


def run(raw, prefs=None, **kw):
    kw.setdefault("mode", "live")
    return verify_submission(raw, job_id="rsj_t", prefs=prefs or Preferences(), job_created_at=NOW - timedelta(minutes=1),
                             url_checker=nodns, category="jacket", **kw)


def test_variants_keep_unavailable_sizes_and_size_check_uses_available_ones():
    raw = [sub(variants=[{"label": "S", "available": True}, {"label": "M", "available": False}, {"label": "L"}])]
    [p], _, _ = run(raw, Preferences(size=SizePref(raw="M")))
    assert [(v.label, v.availability) for v in p.variants] == [("S", "available"), ("M", "unavailable"), ("L", "unknown")]
    assert p.sizes_available == ["S"] and p.availability == "in_stock"
    size = next(c for c in p.constraint_checks if c.constraint == "size")
    assert size.state == "violated"  # M shown, but unavailable: never hidden, never counted as in stock


def test_brand_needs_page_evidence_and_images_are_https_checked():
    [p], _, _ = run([sub(brand="Alpha Industries", imageUrl="http://img-store.com/a.jpg")])
    assert p.brand is None and p.image_url is None
    assert any("Brand not shown" in w for w in p.warnings) and any("Image link" in w for w in p.warnings)
    [q], _, _ = run([sub(brand="Alpha Industries", imageUrl="https://img-store.com/a.jpg",
                         evidence=[{"field": "brand", "excerpt": "Brand: Alpha Industries"}])])
    assert q.brand == "Alpha Industries" and q.brand_basis == "page_text" and q.image_url == "https://img-store.com/a.jpg"


def test_condition_and_seller_kind_normalize():
    [p], _, _ = run([sub(condition="pre_owned", sellerKind="resale")])
    assert p.condition == "used" and p.seller_kind == "resale"
    [q], _, _ = run([sub(condition="pre_owned")], Preferences(condition="new"))
    assert next(c for c in q.constraint_checks if c.constraint == "condition").state == "violated"


def test_identifier_match_compares_only_confirmed_prices():
    raw = [
        sub(retailer="A", productUrl="https://a-store.com/x", observedPrice={"amountMinor": 9000, "currency": "USD"},
            priceExcerpt="$90.00", identifiers={"gtin": "0012345678905"}),
        sub(retailer="B", productUrl="https://b-store.com/x", observedPrice={"amountMinor": 8000, "currency": "USD"},
            priceExcerpt="$80.00", identifiers={"gtin": "12345678905"}),
        sub(retailer="C", productUrl="https://c-store.com/x", observedPrice={"amountMinor": 5000, "currency": "USD"},
            identifiers={"gtin": "12345678905"}),  # no page text for the price: uncertain, never the "lowest"
        sub(retailer="D", productUrl="https://d-store.com/y", title="Green Fleece Hoodie Jacket"),
    ]
    ps, _, _ = run(raw)
    by = {p.retailer: p for p in ps}
    g = by["A"].offer_group
    assert g.equivalence == "identifier_match" and g.offer_count == 3 and g.basis.startswith("Same GTIN")
    assert g.lowest_confirmed_price.amount_minor == 8000 and g.uncertain_price_count == 1
    assert by["B"].offer_group.is_lowest_confirmed and not by["A"].offer_group.is_lowest_confirmed
    assert by["C"].price is None and by["D"].offer_group.equivalence == "single"


def test_approximate_match_needs_same_evidenced_brand_and_is_labelled_unconfirmed():
    ev = [{"field": "brand", "excerpt": "Alpha Industries"}]
    raw = [
        sub(retailer="A", productUrl="https://a-store.com/1", title="Alpha Industries MA-1 Flight Jacket Black", brand="Alpha Industries", evidence=ev),
        sub(retailer="B", productUrl="https://b-store.com/1", title="MA-1 Flight Jacket - Black (Alpha Industries)", brand="Alpha Industries", evidence=ev),
        sub(retailer="C", productUrl="https://c-store.com/1", title="MA-1 Flight Jacket Black"),  # no brand: never grouped
    ]
    ps, _, _ = run(raw)
    by = {p.retailer: p for p in ps}
    assert by["A"].offer_group.equivalence == "approximate" and by["A"].offer_group.id == by["B"].offer_group.id
    assert "not confirmed" in by["A"].offer_group.basis and by["C"].offer_group.equivalence == "single"


def test_manual_mode_labels_and_old_observations_warn():
    old = (NOW - timedelta(days=3)).isoformat()
    [p], _, _ = run([sub(observedAt=old)], mode="manual", source="manual_import")
    assert p.mode == "manual" and p.source == "manual_import"
    assert p.warnings[0].startswith("Imported manually") and any("may have changed" in w for w in p.warnings)


# ---------------------------------------------------------------- sections for unpriced offers (contract: "Sections")
PRICED = {"observedPrice": {"amountMinor": 9000, "currency": "USD"}, "priceExcerpt": "$90.00", "identifiers": {"gtin": "0012345678905"}}
NO_EXCERPT = {"observedPrice": {"amountMinor": 5000, "currency": "USD"}, "identifiers": {"gtin": "0012345678905"}}


@pytest.mark.parametrize("budget", [None, 10000])
def test_unpriced_offers_are_never_recommended_or_lowest_with_or_without_a_budget(budget):
    raw = [
        sub(retailer="Priced", productUrl="https://a-store.com/x", **PRICED),
        sub(retailer="NoExcerpt", productUrl="https://b-store.com/x", **NO_EXCERPT),  # price given, page text missing
        sub(retailer="NoPrice", productUrl="https://c-store.com/x", identifiers={"gtin": "0012345678905"}),
        sub(retailer="SoleScout", productUrl="https://solescout.ai/product/abc",  # comparison page: never a seller price
            observedPrice={"amountMinor": 4000, "currency": "USD"}, priceExcerpt="from $40"),
    ]
    ps, _, _ = run(raw, Preferences(max_item_price_minor=budget))
    by = {p.retailer: p for p in ps}
    assert by["Priced"].section == "primary" and by["Priced"].offer_group.is_lowest_confirmed
    for name in ("NoExcerpt", "NoPrice", "SoleScout"):
        p = by[name]
        assert p.price is None and p.price_basis == "unknown" and p.section == "needs_checking", name
        assert not (p.offer_group and p.offer_group.is_lowest_confirmed), name
        unknown = {c.constraint for c in p.constraint_checks if c.state == "unknown"}
        assert unknown == ({"budget"} if budget else {"price"}), (name, unknown)
        assert not any(c.constraint == "budget" and c.state == "satisfied" for c in p.constraint_checks), name
    assert by["Priced"].offer_group.lowest_confirmed_price.amount_minor == 9000
    assert by["Priced"].offer_group.uncertain_price_count == 2  # NoExcerpt and NoPrice share the GTIN


def test_research_warnings_carry_stable_codes():
    old = (NOW - timedelta(days=3)).isoformat()
    raw = [
        sub(retailer="A", productUrl="https://a-store.com/x", observedAt=old, brand="Alpha", imageUrl="http://img-store.com/a.jpg",
            matchType="exact", **NO_EXCERPT),
        sub(retailer="SoleScout", productUrl="https://solescout.ai/product/abc"),
    ]
    ps, _, _ = run(raw, mode="fixture")
    by = {p.retailer: p for p in ps}
    assert by["A"].warning_codes == ["observation_stale", "price_without_page_text", "fixture_data", "brand_not_evidenced",
                                     "image_rejected", "exact_claim_unconfirmed"]
    assert by["A"].warnings[1:] and len(by["A"].warnings) == len(by["A"].warning_codes) + 1  # the first names the source
    assert by["SoleScout"].warning_codes == ["comparison_page", "fixture_data"]


def test_accessory_research_flags_seller_claims_by_code():
    raw = [sub(title="14K Gold Diamond Watch", productUrl="https://w-store.com/1"), sub(title="Steel field watch", productUrl="https://w-store.com/2")]
    ps, _, _ = verify_submission(raw, job_id="rsj_t", prefs=Preferences(), job_created_at=NOW - timedelta(minutes=1),
                                 url_checker=nodns, category="watch", mode="live")
    by = {p.title: p for p in ps}
    assert "seller_claims_unverified" in by["14K Gold Diamond Watch"].warning_codes
    assert "seller_claims_unverified" not in by["Steel field watch"].warning_codes


# ---------------------------------------------------------------- API
@pytest.fixture
def research(app_factory, monkeypatch):
    def make(provider="fixture", catalog=None, style=False):
        monkeypatch.setenv("FEATURE_AGENT_RESEARCH", "1")
        monkeypatch.setenv("RESEARCH_PROVIDER", provider)
        monkeypatch.setenv("RESEARCH_RESOLVE_DNS", "0")
        if style:
            monkeypatch.setenv("FEATURE_STYLE_MEMORY", "1")
        app = app_factory(catalog or FakeCatalog([item("a", "Black Nylon Bomber Jacket", 70)]))
        return new_client(app), app.state.clipcart
    return make


def start(c, s):
    return c.post(f"/api/sessions/{s['id']}/research-jobs", headers=H, json={"idempotencyKey": "r1"}).json()["job"]


GOOD = {"products": [sub(retailer="Shop", productUrl="https://shop-store.com/bomber", observedPrice={"amountMinor": 6500, "currency": "USD"},
                          priceExcerpt="$65.00 USD")], "notes": "found by hand"}


def test_manual_provider_waits_then_accepts_one_labelled_import(research):
    c, _ = research("manual")
    s, g, _ = bootstrap(c)
    job = start(c, s)
    assert job["status"] == "pending" and job["provider"] == "manual" and job["mode"] == "manual"
    bad = c.post(f"/api/research-jobs/{job['id']}/import", headers=H, json={"products": "nope"})
    assert bad.status_code == 422
    assert c.get(f"/api/research-jobs/{job['id']}").json()["job"]["status"] == "pending"  # a bad import never kills the job
    r = c.post(f"/api/research-jobs/{job['id']}/import", headers=H, json=GOOD)
    assert r.status_code == 200
    done = r.json()["job"]
    assert done["status"] == "completed" and done["resultSource"] == "manual_import" and done["summary"].startswith("Manually imported")
    p = done["products"][0]
    assert p["source"] == "manual_import" and p["mode"] == "manual" and p["price"]["amountMinor"] == 6500
    again = c.post(f"/api/research-jobs/{job['id']}/import", headers=H, json=GOOD)
    assert again.status_code == 409


def test_failed_bridge_job_can_be_completed_by_manual_import(research, monkeypatch):
    from app.research import providers

    monkeypatch.setattr(providers.FixtureResearchProvider, "dispatch",
                        lambda self, job, deliver: providers.DispatchResult(False, "webhook returned 401"))
    c, _ = research("fixture")
    s, g, _ = bootstrap(c)
    job = start(c, s)
    assert job["status"] == "failed" and job["error"]["code"] == "dispatch_failed"
    done = c.post(f"/api/research-jobs/{job['id']}/import", headers=H, json=GOOD).json()["job"]
    assert done["status"] == "completed" and done["error"] is None and done["resultSource"] == "manual_import"


def test_import_is_owner_scoped(research):
    c, st = research("manual")
    s, g, _ = bootstrap(c)
    job = start(c, s)
    other = new_client(c.app)
    other.post("/api/sessions", headers=H)
    assert other.post(f"/api/research-jobs/{job['id']}/import", headers=H, json=GOOD).status_code == 404


def test_solescout_fallback_turns_named_store_records_into_compared_offers(research):
    stores = [
        {"name": "Farfetch", "url": "https://www.farfetch.com/item-1.aspx", "price_usd": 120, "sizes_in_stock": ["M", "L"]},
        {"name": "SSENSE", "url": "https://www.ssense.com/en-us/item-1", "price_usd": 105, "sizes_in_stock": ["S"]},
        {"name": "Hidden", "url": None, "price_usd": 90},
    ]
    cat = FakeCatalog([item("a", "Black Nylon Bomber Jacket", 90, brand="Alpha Industries")],
                      {"a": {"sizes": ["S", "M", "L"], "carrying": 3, "hidden": 1, "stores": stores}})
    c, _ = research("solescout", cat)
    s, g, _ = bootstrap(c)
    job = start(c, s)
    assert job["provider"] == "solescout" and job["mode"] == "live"
    done = wait(lambda: c.get(f"/api/research-jobs/{job['id']}").json()["job"], lambda j: j["status"] != "pending")
    assert done["status"] == "completed", done
    shown = [p for p in done["products"] if p["section"] != "excluded"]
    assert {p["domain"] for p in shown} == {"farfetch.com", "ssense.com"}
    for p in shown:
        assert p["source"] == "catalog" and p["brand"] == "Alpha Industries" and p["brandBasis"] == "catalog_record"
        assert p["warnings"][0].startswith("From SoleScout's store record")
        assert p["offerGroup"]["equivalence"] == "identifier_match" and p["offerGroup"]["offerCount"] == 2
    cheapest = next(p for p in shown if p["offerGroup"]["isLowestConfirmed"])
    assert cheapest["domain"] == "ssense.com" and cheapest["offerGroup"]["lowestConfirmedPrice"]["amountMinor"] == 10500
    assert "SoleScout fallback" in done["agentNotes"]


def test_style_hints_are_attached_as_soft_context(research):
    c, _ = research("manual", style=True)
    s, g, _ = bootstrap(c)
    c.post("/api/style/memories", headers=H, json={"kind": "color_like", "value": "black", "source": "style_panel"})
    job = start(c, s)
    assert job["styleHints"]["colorsLike"] == ["black"]
    assert job["preferences"]["colors"] == []  # hints never become hard constraints


def test_solescout_fallback_fails_the_job_when_the_catalog_is_unreachable(research):
    from app.providers.catalog.errors import CatalogProviderError

    cat = FakeCatalog([item("a", "Black Nylon Bomber Jacket", 70)], fail=CatalogProviderError("unavailable", "down", retryable=False))
    c, _ = research("solescout", cat)
    s, g, _ = bootstrap(c)
    job = start(c, s)
    done = wait(lambda: c.get(f"/api/research-jobs/{job['id']}").json()["job"], lambda j: j["status"] != "pending")
    assert done["status"] == "failed" and done["error"]["code"] == "catalog_unavailable" and done["error"]["retryable"]


def test_solescout_fallback_offers_the_comparison_page_when_stores_are_hidden(research):
    cat = FakeCatalog([item("a", "Black Nylon Bomber Jacket", 90)], {"a": {"carrying": 2, "hidden": 2, "stores": []}})
    c, _ = research("solescout", cat)
    s, g, _ = bootstrap(c)
    job = start(c, s)
    done = wait(lambda: c.get(f"/api/research-jobs/{job['id']}").json()["job"], lambda j: j["status"] != "pending")
    [p] = [p for p in done["products"] if p["section"] != "excluded"]
    assert p["domain"] == "solescout.ai" and p["price"] is None and p["links"][0]["kind"] == "aggregator_product_page"
    assert "names none" in p["uncertainty"]
