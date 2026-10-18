"""Research providers.

- ``fixture``: a labelled development submission (not research output).
- ``solescout``: catalog-backed fallback. One bounded catalog search plus a few detail checks; every
  named store record SoleScout returns (URL + price + sizes from the same record) becomes an offer.
  Real retailer URLs, but the data is SoleScout's store record, not the store page itself.
- ``manual``: dispatches nothing and waits for a clearly labelled manual import.

A bridge provider (Grok Bot webhook routine, xAI API agent) must implement ``dispatch`` and deliver
results through ``service.ingest_submission``. The Grok Bot bridge is not implemented: its callback
round trip has not been proven (docs/grok-bot-bridge.md).
"""

from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from app.config import REPO_ROOT

FIXTURE_PATH = REPO_ROOT / "fixtures" / "research" / "dev_research_result.json"
log = logging.getLogger("clipcart.research")


@dataclass(frozen=True)
class DispatchResult:
    accepted: bool
    detail: str
    retryable: bool = False


class ResearchProvider(Protocol):
    name: str
    mode: str  # live | fixture | manual
    source: str  # agent | catalog | manual_import — how ClipCart labels the products

    def dispatch(self, job: dict, deliver: Any) -> DispatchResult: ...


class FixtureResearchProvider:
    """Delivers a captured, labelled fixture submission after a short delay (simulates async research)."""

    name = "fixture"
    mode = "fixture"
    source = "agent"

    def __init__(self, path: Path = FIXTURE_PATH, delay_s: float = 1.5):
        data = json.loads(Path(path).read_text())
        if "NOT GROK BOT OUTPUT" not in str(data.get("fixture_label", "")).upper():
            raise ValueError("research fixture must carry an explicit fixture_label")
        self.products = data["products"]
        self.notes = data.get("notes")
        self.delay_s = delay_s

    def dispatch(self, job: dict, deliver: Any) -> DispatchResult:
        payload = {"jobId": job["id"], "products": self.products, "notes": self.notes}
        t = threading.Timer(self.delay_s, deliver, args=(job["id"], payload))
        t.daemon = True
        t.start()
        return DispatchResult(True, "fixture delivery scheduled")


class ManualResearchProvider:
    """No automatic research: the job waits for POST /api/research-jobs/{id}/import."""

    name = "manual"
    mode = "manual"
    source = "manual_import"

    def dispatch(self, job: dict, deliver: Any) -> DispatchResult:
        return DispatchResult(True, "waiting for a manual import")


class CatalogResearchProvider:
    """SoleScout fallback: named store records for the garment, normalized like any submission."""

    name = "solescout"
    source = "catalog"

    def __init__(self, state: Any, *, max_queries: int = 2, max_details: int = 3, search_limit: int = 10):
        if state is None or getattr(state, "catalog", None) is None:
            raise ValueError("research provider 'solescout' needs a configured catalog provider")
        self.state = state
        self.catalog = state.catalog
        self.mode = "fixture" if getattr(self.catalog, "name", "") == "fixture" else "live"
        self.max_queries, self.max_details, self.search_limit = max_queries, max_details, search_limit

    def dispatch(self, job: dict, deliver: Any) -> DispatchResult:
        t = threading.Thread(target=self._run, args=(job, deliver), daemon=True)
        t.start()
        return DispatchResult(True, "catalog research started")

    # ------------------------------------------------------------------ worker
    def _run(self, job: dict, deliver: Any) -> None:
        try:
            payload = self.collect(job)
        except Exception as exc:  # noqa: BLE001 - the job fails cleanly; nothing else depends on this thread
            log.exception("catalog research failed")
            payload = {"jobId": job["id"], "products": [], "providerError": "research_failed",
                       "notes": f"Catalog research failed: {type(exc).__name__}"}
        deliver(job["id"], payload)

    def collect(self, job: dict) -> dict:
        from app.contracts import Preferences, SearchBudget
        from app.providers.catalog import CatalogFilters
        from app.shopping.budget import BudgetLedger
        from app.shopping.rules import GarmentProfile, relevance, title_matches_category
        from app.shopping.tools import ToolBox
        from app.shopping.workers import rule_queries

        g = job["garment"]
        prefs = Preferences.model_validate(job["preferences"])
        profile = GarmentProfile(category=g["category"], colors=g.get("colors") or [], pattern=g.get("pattern") or [],
                                 cut=g.get("cut") or [], details=g.get("details") or [],
                                 visible_text=g.get("visibleText") or [], description=g.get("description"))
        filters = CatalogFilters(category=profile.category, country=prefs.country, currency=prefs.currency,
                                 max_price_minor=prefs.max_item_price_minor,
                                 size_raw=prefs.size.raw if prefs.size and not _is_accessory(profile.category) else None,
                                 colors=tuple(prefs.colors), excluded_materials=tuple(prefs.excluded_materials),
                                 condition=prefs.condition)
        ledger = BudgetLedger(SearchBudget(max_tool_calls=self.max_queries + self.max_details,
                                           max_detail_calls=self.max_details), time.monotonic() + 40)
        tools = ToolBox(self.catalog, ledger, filters, lambda *a, **k: None, self.state.status["catalog"])
        queries = list(dict.fromkeys(rule_queries("exact", profile, prefs) + rule_queries("alternative", profile, prefs)))
        for q in queries[: self.max_queries]:
            tools.search_catalog("research", q, self.search_limit)
        cands = [c for c in tools.candidates.values() if title_matches_category(c.listing.title, profile.category)]
        cands.sort(key=lambda c: -relevance(c.listing, profile, prefs))  # spend detail calls on the closest matches
        for c in cands[: self.max_details]:
            tools.get_listing_details("research", c.id)
        products: list[dict] = []
        for c in cands[: self.max_details]:
            products.extend(_store_offers_as_products(c.listing))
        if tools.errors and not tools.candidates:
            codes = sorted({e["code"] for e in tools.errors})
            return {"jobId": job["id"], "products": [], "providerError": "catalog_unavailable",
                    "notes": f"SoleScout was unreachable ({', '.join(codes)}); no research results."}
        notes = (f"SoleScout fallback: {len(queries[: self.max_queries])} search(es), {min(len(cands), self.max_details)} "
                 f"product detail check(s). Store records come from SoleScout; ClipCart did not open the store pages.")
        return {"jobId": job["id"], "products": products[:20], "notes": notes}


def _is_accessory(category: str) -> bool:
    from app.categories import is_accessory

    return is_accessory(category)


def _store_offers_as_products(L: Any) -> list[dict]:
    """Each named store record with its own URL becomes an offer. Price/sizes come from that same record."""
    out: list[dict] = []
    ref = f"{L.provider}:{L.product_id or L.provider_listing_id}"
    base = {
        "title": L.title, "matchType": "similar", "observedAt": L.checked_at.isoformat(), "imageUrl": (L.image_urls or [None])[0],
        "brand": L.brand, "condition": L.condition, "sourceUrl": L.canonical_url,
        "identifiers": {"catalogRef": ref, "styleCode": L.style_code},
    }
    for o in L.store_offers:
        if not o.url or o.retailer == "SoleScout comparison":
            continue
        price = o.price
        excerpt = f"SoleScout store record: {o.retailer} price_usd={price.amount_minor / 100:g}" if price else None
        evidence = [{"field": "title", "excerpt": f"SoleScout product: {L.title}"[:200]}]
        if excerpt:
            evidence.append({"field": "price", "excerpt": excerpt})
        if o.sizes_in_stock:
            evidence.append({"field": "size", "excerpt": f"{o.retailer} sizes_in_stock={', '.join(o.sizes_in_stock[:20])}"[:200]})
        if L.brand:
            evidence.append({"field": "brand", "excerpt": f"SoleScout brand: {L.brand}"})
        out.append({
            **base, "retailer": o.retailer[:80], "productUrl": o.url, "sellerKind": "retailer",
            "observedPrice": {"amountMinor": price.amount_minor, "currency": price.currency} if price else None,
            "priceExcerpt": excerpt, "availability": "in_stock" if o.sizes_in_stock else "unknown",
            "sizesAvailable": list(o.sizes_in_stock[:30]), "evidence": evidence,
            "uncertainty": "SoleScout store record; the store page was not opened.",
        })
    if not out and L.source_kind == "aggregator" and L.canonical_url:
        # No named store record (SoleScout's free tier often hides them): offer the comparison page, never a price.
        out.append({**base, "retailer": "SoleScout", "productUrl": L.canonical_url, "sellerKind": "unknown",
                    "availability": "unknown",
                    "evidence": [{"field": "title", "excerpt": f"SoleScout product: {L.title}"[:200]}],
                    "uncertainty": (f"SoleScout lists {L.stores_carrying or 'some'} store(s) for this product but names none; "
                                    "the comparison page shows the stores.")})
    if L.source_kind == "retailer" and L.canonical_url and not out:
        out.append({**base, "retailer": L.retailer[:80], "productUrl": L.canonical_url, "sellerKind": "retailer",
                    "observedPrice": L.price.model_dump(by_alias=True) if L.price else None,
                    "priceExcerpt": f"SoleScout store record price for {L.retailer}" if L.price else None,
                    "availability": L.availability, "sizesAvailable": [s.raw for s in (L.sizes_in_stock or [])][:30],
                    "evidence": [{"field": "title", "excerpt": f"SoleScout product: {L.title}"[:200]}],
                    "uncertainty": "SoleScout store record; the store page was not opened."})
    return out


def research_mode(name: str, state: Any = None) -> str | None:
    """The mode jobs from this provider get, without constructing it (health reports this).

    ``fixture`` → fixture; ``manual`` → manual; ``solescout`` → fixture with the fixture catalog, else live.
    ``None`` when the provider isn't implemented: no job can start, so there is no mode to report.
    """
    if name in ("fixture", "manual"):
        return name
    if name == "solescout":
        catalog = getattr(state, "catalog", None)
        if catalog is None:
            return None
        return "fixture" if getattr(catalog, "name", "") == "fixture" else "live"
    return None


def get_provider(name: str, state: Any = None) -> ResearchProvider:
    if name == "fixture":
        return FixtureResearchProvider()
    if name == "manual":
        return ManualResearchProvider()
    if name == "solescout":
        return CatalogResearchProvider(state)
    raise ValueError(f"research provider {name!r} is not implemented (bridge not proven; see docs/grok-bot-bridge.md)")
