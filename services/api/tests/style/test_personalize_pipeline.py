import time
from datetime import datetime, timezone

from shopping.fakes import FakeCatalog, item

from app.contracts import Preferences, SearchBudget, StyleProfile
from app.contracts.style_memory import ProfileEntry
from app.providers.status import ProviderStatus
from app.shopping.budget import BudgetLedger
from app.shopping.pipeline import run_search
from app.shopping.rules import GarmentProfile
from app.shopping.tools import clear_cache

ITEMS = [item("a", "Black Nylon Bomber Jacket", 70, brand="Acme"), item("b", "Black Satin Bomber Jacket", 95, brand="Bolt"),
         item("c", "Black Quilted Bomber Jacket", 90, brand="Nova")]


def run(style=None):
    clear_cache()
    cat = FakeCatalog(ITEMS, {s: {"sizes": ["M"]} for s in "abc"})
    out = run_search(
        search_id="s", garment_id="g", profile=GarmentProfile(category="jacket", colors=["black"], description="black bomber"),
        prefs=Preferences(max_item_price_minor=15000), provider=cat, ledger=BudgetLedger(SearchBudget(), time.monotonic() + 20),
        emit=lambda *a, **k: None, catalog_status=ProviderStatus("solescout", True), grok_status=ProviderStatus("grok", False),
        grok_client_factory=None, is_current=lambda: True, style=style,
    )
    by_id = {L.id: L for L in out.listings}
    return [(by_id[r.listing_id].brand, r.section, [c.state for c in r.constraint_checks], r.personalization) for r in out.recommendations]


def entry(v, origin="stated"):
    return ProfileEntry(value=v, origin=origin, memory_id="m")


def test_stated_like_moves_last_to_first_and_avoid_moves_first_to_last():
    base = run()
    brands = [b for b, *_ in base]
    assert len(brands) == 3
    liked = run(StyleProfile(brands_like=[entry(brands[-1])], updated_at=datetime.now(timezone.utc)))
    assert liked[0][0] == brands[-1] and f"You said you like {brands[-1]}" in liked[0][3]
    avoided = run(StyleProfile(brands_avoid=[entry(brands[0])]))
    assert avoided[-1][0] == brands[0] and any("Ranked lower" in r for r in avoided[-1][3])
    # Sections and constraint states are identical; only order and reasons change.
    key = lambda rows: sorted((b, s, tuple(c)) for b, s, c, _ in rows)  # noqa: E731
    assert key(base) == key(liked) == key(avoided)


def test_inferred_like_weighs_less_than_stated_avoid():
    base = run()
    b0 = base[0][0]
    rows = run(StyleProfile(brands_like=[entry(b0, "inferred")], brands_avoid=[entry(b0, "stated")]))
    assert rows[-1][0] == b0  # stated avoid (-3) outweighs inferred like (+1)


def test_rejected_product_hidden():
    rows = run(StyleProfile(rejected_product_keys=["solescout:a"]))
    assert "Acme" not in [b for b, *_ in rows]


def test_no_style_means_no_personalization():
    assert all(p == [] for *_, p in run())
