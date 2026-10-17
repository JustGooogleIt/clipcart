"""Bounded retrieval tools shared by the exact-match and alternatives workers.

Tools return typed summaries with opaque candidate IDs. They never accept URLs
from a model. Every call passes through the shared BudgetLedger first.
"""

from __future__ import annotations

import hashlib
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from app.contracts import Evidence, Listing
from app.providers.catalog import CatalogFilters, CatalogProviderError
from app.providers.status import ProviderStatus

from .budget import BudgetExceeded, BudgetLedger
from .canonical import to_evidence, to_listing
from .rules import money_str, price_phrase

DISCOVERY_TTL_S = 600.0
_cache: dict[tuple, tuple[float, Any]] = {}
_cache_lock = threading.Lock()


def _cache_get(key: tuple):
    with _cache_lock:
        hit = _cache.get(key)
        if hit and time.monotonic() - hit[0] < DISCOVERY_TTL_S:
            return hit[1]
        return None


def _cache_put(key: tuple, value: Any) -> None:
    with _cache_lock:
        _cache[key] = (time.monotonic(), value)
        if len(_cache) > 500:
            for k in sorted(_cache, key=lambda k: _cache[k][0])[:100]:
                _cache.pop(k, None)


def clear_cache() -> None:
    with _cache_lock:
        _cache.clear()


@dataclass
class Candidate:
    id: str
    listing: Listing
    evidence: list[Evidence]
    found_by: set[str] = field(default_factory=set)
    queries: list[str] = field(default_factory=list)
    submitted_by: set[str] = field(default_factory=set)


class ToolBox:
    def __init__(
        self,
        provider: Any,
        ledger: BudgetLedger,
        filters: CatalogFilters,
        emit: Callable[..., None],
        status: ProviderStatus,
    ):
        self.provider = provider
        self.ledger = ledger
        self.filters = filters
        self.emit = emit
        self.status = status
        self.candidates: dict[str, Candidate] = {}
        self.errors: list[dict] = []
        self._lock = threading.Lock()

    # ----------------------------------------------------------- internals
    def _call(self, fn: Callable[[], Any], *, label: str) -> Any:
        """One retry with jitter for transient failures, inside the deadline."""
        for attempt in (1, 2):
            try:
                result = fn()
                self.status.record(True, note=label)
                return result
            except CatalogProviderError as exc:
                self.status.record(False, code=exc.code, note=f"{label}: {exc.message}")
                if attempt == 2 or not exc.retryable or exc.code == "auth_error" or self.ledger.remaining_s() < 4:
                    raise
                time.sleep(0.4 + 0.3 * (hash(label) % 3) / 3)
        raise AssertionError("unreachable")

    def _cand_id(self, offer_key: str) -> str:
        return "cand_" + hashlib.sha256(offer_key.encode()).hexdigest()[:10]

    def _summary(self, c: Candidate) -> dict:
        L = c.listing
        out = {
            "candidate_id": c.id,
            "title": L.title,
            "brand": L.brand,
            "color": L.color_text,
            "price": price_phrase(L),
            "detail_checked": L.detail_checked,
        }
        if L.detail_checked:
            out["sizes_in_stock"] = [s.raw for s in (L.sizes_in_stock or [])][:12]
            out["material_text"] = L.material_text
            out["named_stores"] = [s.retailer for s in L.store_offers][:3]
            out["hidden_store_count"] = L.hidden_store_count
        return out

    # ----------------------------------------------------------- tools
    def search_catalog(self, worker: str, query: str, limit: int = 6) -> dict:
        query = " ".join(str(query).split())[:120]
        if not query:
            return {"error": "empty_query"}
        limit = max(1, min(int(limit or 6), 8))
        key = (getattr(self.provider, "name", "catalog"), query.lower(), limit)
        cached = _cache_get(key)
        try:
            self.ledger.take_tool(cached=cached is not None)
        except BudgetExceeded as exc:
            return {"error": f"budget_exhausted:{exc.kind}"}
        t0 = time.monotonic()
        stage = "searching_original" if worker == "exact" else "searching_alternatives"
        if cached is None:
            try:
                result = self._call(lambda: self.provider.search(query, self.filters, limit), label=f"search '{query}'")
            except CatalogProviderError as exc:
                self.errors.append({"code": exc.code, "message": exc.message, "worker": worker})
                self.emit(stage, f"Catalog search failed ({exc.code}) for '{query}'", worker=worker, tool_name="search_catalog")
                return {"error": exc.code}
            _cache_put(key, result)
            mode_override = None
        else:
            result = cached
            mode_override = "cached"
        evidence = [to_evidence(e) for e in (result.evidence or []) if e]
        found = []
        for item in result.listings:
            L = to_listing(item, result_mode=result.mode, evidence=evidence)
            if L is None:
                continue
            if mode_override and L.mode == "live":
                L = L.model_copy(update={"mode": "cached"})
            cid = self._cand_id(L.offer_key)
            with self._lock:
                c = self.candidates.get(cid)
                if c is None:
                    c = Candidate(cid, L, [e for e in evidence if e.id in L.evidence_ids])
                    self.candidates[cid] = c
                c.found_by.add(worker)
                c.queries.append(query)
            found.append(self._summary(c))
        ms = int((time.monotonic() - t0) * 1000)
        src = "cache" if mode_override else result.provider
        self.emit(
            stage,
            f"Searched {src} for '{query}': {len(found)} listing{'s' if len(found) != 1 else ''}",
            worker=worker,
            tool_name="search_catalog",
            elapsed_ms=ms,
        )
        return {"results": found, "mode": mode_override or result.mode}

    def get_listing_details(self, worker: str, candidate_id: str) -> dict:
        with self._lock:
            c = self.candidates.get(str(candidate_id))
        if c is None:
            return {"error": "unknown_candidate_id"}
        if c.listing.detail_checked:
            return self._summary(c)
        try:
            self.ledger.take_tool(detail=True)
        except BudgetExceeded as exc:
            return {"error": f"budget_exhausted:{exc.kind}"}
        t0 = time.monotonic()
        try:
            result = self._call(
                lambda: self.provider.get_details(c.listing.provider_listing_id, None),
                label=f"detail {c.listing.provider_listing_id}",
            )
        except CatalogProviderError as exc:
            self.errors.append({"code": exc.code, "message": exc.message, "worker": worker})
            self.emit("verifying_listings", f"Detail check failed ({exc.code}) for {c.listing.title[:60]}", worker=worker,
                      tool_name="get_listing_details")
            return {"error": exc.code}
        if not result.listings:
            return {"error": "not_found"}
        evidence = [to_evidence(e) for e in (result.evidence or []) if e]
        L = to_listing(result.listings[0], result_mode=result.mode, evidence=evidence, diagnostics=result.diagnostics,
                       detail=True)
        if L is None:
            return {"error": "invalid_listing"}
        with self._lock:
            c.listing = L
            c.evidence = c.evidence + [e for e in evidence if e.id in L.evidence_ids]
        n = len(L.sizes_in_stock or [])
        stock = f"{n} size{'s' if n != 1 else ''} listed in stock" if n else "no size stock listed"
        self.emit(
            "verifying_listings",
            f"Checked details for {L.title[:60]}: {money_str(L.price)} lowest, {stock}",
            worker=worker,
            tool_name="get_listing_details",
            elapsed_ms=int((time.monotonic() - t0) * 1000),
            evidence_ids=L.evidence_ids,
        )
        return self._summary(c)

    def submit_candidates(self, worker: str, candidate_ids: list[str]) -> dict:
        accepted = []
        with self._lock:
            for cid in candidate_ids or []:
                c = self.candidates.get(str(cid))
                if c:
                    c.submitted_by.add(worker)
                    accepted.append(c.id)
        return {"accepted": accepted, "rejected": [x for x in (candidate_ids or []) if x not in accepted]}
