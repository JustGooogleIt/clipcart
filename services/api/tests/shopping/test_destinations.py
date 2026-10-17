"""PR #3 destination rules through the integration layer (real adapter, mocked HTTP)."""

import json
from pathlib import Path
from unittest import mock

from app.contracts import Preferences, SizePref
from app.providers.catalog.solescout import SoleScoutCatalogProvider
from app.shopping.canonical import to_evidence, to_listing
from app.shopping.pipeline import _links_for
from app.shopping.rules import check_constraints, price_phrase

ROOT = Path(__file__).resolve().parents[4]


def product(stores, sizes, lowest=55, hidden=2):
    return {
        "slug": "tee", "title": "Slim Fit Cotton T-shirt White", "brand": "Polo Ralph Lauren", "style_code": "NSC",
        "image": "https://solescout.ai/api/goat-image?slug=tee", "url": "https://solescout.ai/product/tee",
        "lowest_price_usd": lowest, "stores_carrying": 3, "stores": stores,
        "hidden_stores": {"count": hidden, "lowest_price_usd": lowest}, "sizes_in_stock": sizes,
        "disclaimer": "SoleScout does not sell products.",
    }


def detail(payload, variant=None):
    p = SoleScoutCatalogProvider(base_url="https://solescout.ai")
    with mock.patch.object(p, "_get_json", return_value=(payload, 5)):
        r = p.get_details("tee", variant)
    ev = [to_evidence(e) for e in r.evidence]
    return to_listing(r.listings[0], result_mode=r.mode, evidence=ev, diagnostics=r.diagnostics, detail=True)


FARFETCH = {"name": "Grp-Ff", "url": "https://www.farfetch.com/us/item-1.aspx", "price_usd": 74, "sizes_in_stock": ["S", "M"]}


def test_priced_store_with_size_becomes_store_offer_at_its_own_price():
    L = detail(product([FARFETCH], [{"size": "M", "lowest_price_usd": 55}]), "M")
    assert L.source_kind == "retailer" and L.retailer == "Grp-Ff" and L.price.amount_minor == 7400
    assert L.price_basis == "seller_offer" and L.canonical_url.startswith("https://www.farfetch.com/")
    assert [s.raw for s in L.sizes_in_stock] == ["S", "M"]  # the store's sizes, not the aggregate table
    phrase = price_phrase(L)
    assert "$74 at Grp-Ff" in phrase and "$55" not in phrase and "may be cheaper" in phrase
    links, _ = _links_for("rec", L, Preferences())
    assert links[0].kind == "retailer_product_page" and links[0].retailer == "Grp-Ff" and "$74" in links[0].price_note
    assert links[1].kind == "aggregator_product_page" and "$55" not in links[1].price_note


def test_unpriced_visible_store_stays_comparison_and_never_gets_aggregate_price():
    raw = json.loads((ROOT / "fixtures/catalog/raw/solescout_hoodie.json").read_text())
    p = SoleScoutCatalogProvider(base_url="https://solescout.ai")
    with mock.patch.object(p, "_get_json", return_value=(raw, 5)):
        r = p.get_details(raw["slug"], None)
    L = to_listing(r.listings[0], result_mode=r.mode, evidence=[to_evidence(e) for e in r.evidence],
                   diagnostics=r.diagnostics, detail=True)
    assert L.source_kind == "aggregator" and L.retailer == "SoleScout" and L.price_basis == "aggregate_lowest"
    links, _ = _links_for("rec", L, Preferences())
    assert links[0].kind == "aggregator_product_page"
    store = [lk for lk in links if lk.retailer == "Offseason"][0]
    assert store.kind == "retailer_product_page" and "$100" not in store.price_note and "no price" in store.price_note.lower()


def test_size_only_at_hidden_seller_is_comparison_with_unknown_size_stock_at_store():
    store_no_m = {**FARFETCH, "sizes_in_stock": ["S"]}
    L = detail(product([store_no_m], [{"size": "M", "lowest_price_usd": 60}]), "M")
    assert L.source_kind == "aggregator" and L.price_basis == "aggregate_lowest"
    checks = {c.constraint: c for c in check_constraints(L, Preferences(size=SizePref(raw="M"), max_item_price_minor=10000))}
    assert checks["budget"].state == "satisfied" and "lowest listed" in checks["budget"].detail.lower()
    assert "Grp-Ff" not in price_phrase(L)
