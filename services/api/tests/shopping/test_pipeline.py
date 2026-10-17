import time

from app.contracts import Preferences, SearchBudget, SizePref
from app.providers.catalog import CatalogProviderError
from app.providers.status import ProviderStatus
from app.shopping.budget import BudgetLedger
from app.shopping.pipeline import run_search
from app.shopping.rules import GarmentProfile
from app.shopping.tools import clear_cache

from .fakes import FakeCatalog, item


def run(cat, prefs, profile=None, budget=None, current=lambda: True):
    clear_cache()
    events = []
    led = BudgetLedger(budget or SearchBudget(), time.monotonic() + 20)
    out = run_search(
        search_id="srch_t", garment_id="gar_t",
        profile=profile or GarmentProfile(category="jacket", colors=["black"], description="black bomber"),
        prefs=prefs, provider=cat, ledger=led,
        emit=lambda stage, summary, **k: events.append((stage, summary)),
        catalog_status=ProviderStatus("solescout", True), grok_status=ProviderStatus("grok", False),
        grok_client_factory=None, is_current=current,
    )
    return out, events, led


ITEMS = [
    item("a", "Black Nylon Bomber Jacket", 70),
    item("b", "Black Leather Bomber Jacket", 90),
    item("c", "Black Bomber Jacket Premium", 400, brand="Acme"),
    item("d", "Black Wool Sweater", 50),
    item("e", "Black Satin Bomber Jacket", 95),
    item("f", "Black Padded Bomber Jacket", 110),
]


def test_hard_constraints_filter_and_sections():
    cat = FakeCatalog(ITEMS, {s: {"sizes": ["S", "M"], "hidden": 2, "carrying": 3} for s in "abcdef"})
    out, events, led = run(cat, Preferences(max_item_price_minor=12000, size=SizePref(raw="M"), excluded_materials=["leather"]))
    primary = [r for r in out.recommendations if r.section == "primary"]
    assert len(primary) == 0  # material unknown everywhere -> needs checking, never fully compliant
    titles = {L.title for L in out.listings}
    assert "Black Leather Bomber Jacket" not in titles  # excluded by title evidence
    assert "Black Wool Sweater" not in titles  # off-category
    assert "Black Bomber Jacket Premium" not in titles  # over budget
    assert any("Excluded" in s and "budget" in s for _, s in events)
    assert led.budget.used_tool_calls <= 12 and led.budget.used_detail_calls <= 6


def test_primary_capped_at_three_and_links_are_not_checkouts():
    cat = FakeCatalog(ITEMS, {s: {"sizes": ["M"], "hidden": 1, "carrying": 2,
                                  "stores": [{"name": "Shop", "url": "https://shop.example/p", "price_usd": None}]} for s in "abcdef"})
    out, _, _ = run(cat, Preferences(max_item_price_minor=12000, size=SizePref(raw="M")))
    primary = [r for r in out.recommendations if r.section == "primary"]
    assert 1 <= len(primary) <= 3
    for r in primary:
        kinds = [lk.kind for lk in r.links]
        assert kinds[0] == "aggregator_product_page"
        assert all("checkout" not in lk.label.lower() for lk in r.links)
        store = [lk for lk in r.links if lk.kind == "retailer_product_page"]
        assert store and "no price" in store[0].price_note.lower()


def test_likely_original_over_budget_shown_separately():
    cat = FakeCatalog(ITEMS, {s: {"sizes": ["M"]} for s in "abcdef"})
    prof = GarmentProfile(category="jacket", colors=["black"], visible_text=["ACME"])
    out, events, _ = run(cat, Preferences(max_item_price_minor=12000), profile=prof)
    over = [r for r in out.recommendations if r.section == "original_over_budget"]
    assert len(over) == 1 and over[0].identity_tier == "likely"
    assert any("above your budget" in s for _, s in events)


def test_catalog_failure_is_reported_not_fabricated():
    cat = FakeCatalog(ITEMS, fail=CatalogProviderError("unavailable", "down", retryable=False))
    out, _, _ = run(cat, Preferences())
    assert out.status == "failed" and out.recommendations == [] and out.errors


def test_superseded_search_returns_no_results():
    cat = FakeCatalog(ITEMS, {s: {"sizes": ["M"]} for s in "abcdef"})
    out, _, _ = run(cat, Preferences(), current=lambda: False)
    assert out.status == "superseded" and out.recommendations == []


def test_tool_budget_holds_under_parallel_workers():
    cat = FakeCatalog(ITEMS * 1, {s: {"sizes": ["M"]} for s in "abcdef"}, delay=0.05)
    out, _, led = run(cat, Preferences(), budget=SearchBudget(max_tool_calls=3, max_detail_calls=1))
    assert led.budget.used_tool_calls <= 3 and led.budget.used_detail_calls <= 1
    assert sum(1 for k, _ in cat.calls) <= 3
