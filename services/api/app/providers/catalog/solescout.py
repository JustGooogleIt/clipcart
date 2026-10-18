from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from .base import CatalogFilters, CatalogSearchResult
from .errors import CatalogProviderError
from .normalize import (
    build_evidence,
    dollars_to_minor,
    material_hint_from_title,
    stable_id,
    utc_now,
)
from .offers import resolve_solescout_offer
from .types import Listing


class SoleScoutCatalogProvider:
    """Live SoleScout public API adapter. No API key required for read endpoints."""

    name = "solescout"

    def __init__(
        self,
        base_url: str | None = None,
        timeout_s: float | None = None,
    ) -> None:
        self.base_url = (
            base_url or os.getenv("SOLESCOUT_BASE_URL") or "https://solescout.ai"
        ).rstrip("/")
        self.timeout_s = float(
            timeout_s
            if timeout_s is not None
            else os.getenv("SOLESCOUT_TIMEOUT_S", "20")
        )

    def search(
        self, query: str, filters: CatalogFilters, limit: int
    ) -> CatalogSearchResult:
        q = (query or "").strip()
        if not q:
            raise CatalogProviderError(
                "invalid_response", "query must be non-empty", retryable=False
            )
        limit = max(1, min(int(limit), 20))
        path = "/api/public/search?" + urllib.parse.urlencode(
            {"q": q, "limit": str(limit)}
        )
        payload, elapsed_ms = self._get_json(path)
        results = payload.get("results") or []
        checked_at = utc_now()
        listings: list[Listing] = []
        evidence = []
        for item in results:
            listing, ev = self._listing_from_search_hit(item, checked_at, filters)
            if listing is None:
                continue
            listings.append(listing)
            evidence.append(ev)
        return CatalogSearchResult(
            listings=listings,
            evidence=evidence,
            mode="live",
            provider=self.name,
            query=q,
            elapsed_ms=elapsed_ms,
            diagnostics={
                "total": payload.get("total"),
                "source": payload.get("source"),
                "docs": payload.get("docs"),
            },
        )

    def search_image(
        self, crop_asset_id: str, filters: CatalogFilters, limit: int
    ) -> CatalogSearchResult:
        raise CatalogProviderError(
            "unsupported_capability",
            "SoleScout public API does not support image search",
            retryable=False,
        )

    def get_details(
        self, provider_listing_id: str, variant_id: str | None = None
    ) -> CatalogSearchResult:
        slug = (provider_listing_id or "").strip()
        if not slug:
            raise CatalogProviderError(
                "invalid_response",
                "provider_listing_id (slug) required",
                retryable=False,
            )
        path = "/api/public/product?" + urllib.parse.urlencode({"slug": slug})
        payload, elapsed_ms = self._get_json(path)
        checked_at = utc_now()
        listing, ev = self._listing_from_product(payload, checked_at, variant_id)
        return CatalogSearchResult(
            listings=[listing] if listing else [],
            evidence=[ev] if listing else [],
            mode="live",
            provider=self.name,
            query=None,
            elapsed_ms=elapsed_ms,
            diagnostics={
                "disclaimer": payload.get("disclaimer"),
                "hidden_stores": payload.get("hidden_stores"),
                "stores_carrying": payload.get("stores_carrying"),
                "destinationKind": listing.get("destinationKind") if listing else None,
                # Raw detail fields for the integration verifier (size and store checks).
                "stores": payload.get("stores") or [],
                "sizes_in_stock": payload.get("sizes_in_stock") or [],
                "style_code": payload.get("style_code"),
                "retail_price_usd": payload.get("retail_price_usd"),
                "lowest_price_usd": payload.get("lowest_price_usd"),
                "comparison_url": str(payload.get("url") or ""),
            },
        )

    def _get_json(self, path: str) -> tuple[dict[str, Any], int]:
        url = f"{self.base_url}{path}"
        req = urllib.request.Request(
            url,
            headers={"Accept": "application/json", "User-Agent": "ClipCart/0.1"},
        )
        t0 = time.perf_counter()
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
                body = resp.read()
                status = resp.status
        except urllib.error.HTTPError as exc:
            if exc.code == 401 or exc.code == 403:
                raise CatalogProviderError(
                    "auth_error", f"HTTP {exc.code}", retryable=False
                ) from exc
            if exc.code == 429:
                raise CatalogProviderError(
                    "rate_limited", "HTTP 429", retryable=True
                ) from exc
            raise CatalogProviderError(
                "unavailable", f"HTTP {exc.code}", retryable=True
            ) from exc
        except TimeoutError as exc:
            raise CatalogProviderError(
                "timeout", "request timed out", retryable=True
            ) from exc
        except urllib.error.URLError as exc:
            raise CatalogProviderError(
                "unavailable", str(exc.reason), retryable=True
            ) from exc
        elapsed_ms = int((time.perf_counter() - t0) * 1000)
        if status != 200:
            raise CatalogProviderError(
                "unavailable", f"HTTP {status}", retryable=True
            )
        try:
            payload = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise CatalogProviderError(
                "invalid_response", "non-JSON body", retryable=False
            ) from exc
        if not isinstance(payload, dict):
            raise CatalogProviderError(
                "invalid_response", "expected object", retryable=False
            )
        return payload, elapsed_ms

    def _listing_from_search_hit(
        self, item: dict[str, Any], checked_at: str, filters: CatalogFilters
    ) -> tuple[Listing | None, Any]:
        """Search cards never include store records → always comparison destinations."""
        slug = item.get("slug")
        if not slug:
            return None, None
        title = str(item.get("title") or slug)
        url = str(item.get("url") or f"{self.base_url}/product/{slug}")
        image = item.get("image")
        price = dollars_to_minor(item.get("lowest_price_usd"), filters.currency)
        warnings = [
            "SoleScout comparison result — not a retailer checkout destination.",
            "Search hits expose aggregate lowest_price_usd only; call get_details for a direct retailer offer when available.",
            "Do not treat the SoleScout product page as merchant checkout.",
        ]
        material = material_hint_from_title(title)
        listing_id = stable_id(self.name, "search", slug, checked_at)
        offer_key = f"{self.name}:{slug}:comparison"
        ev = build_evidence(
            provider=self.name,
            source_url=url,
            retrieved_at=checked_at,
            claims=[
                {"field": "title", "value": title, "excerpt": title},
                {
                    "field": "price",
                    "value": item.get("lowest_price_usd"),
                    "excerpt": f"lowest_price_usd={item.get('lowest_price_usd')} (aggregate)",
                },
                {"field": "brand", "value": item.get("brand"), "excerpt": None},
                {
                    "field": "destinationKind",
                    "value": "comparison",
                    "excerpt": None,
                },
            ],
            raw_ref=f"solescout:search:{slug}",
            source_type="search_result",
        )
        listing: Listing = {
            "id": listing_id,
            "offerKey": offer_key,
            "provider": self.name,
            "providerListingId": str(slug),
            "productId": str(slug),
            "variantId": None,
            "retailer": "SoleScout (price comparison)",
            "canonicalUrl": url,
            "imageUrls": [str(image)] if image else [],
            "title": title,
            "brand": item.get("brand"),
            "price": price,
            "shippingMinor": None,
            "condition": "unknown",
            "size": None,
            "availability": "unknown",
            "materialText": material,
            "colorText": item.get("color"),
            "checkedAt": checked_at,
            "evidenceIds": [ev["id"]],
            "mode": "live",
            "destinationKind": "comparison",
            "warnings": warnings,
        }
        return listing, ev

    def _listing_from_product(
        self,
        item: dict[str, Any],
        checked_at: str,
        variant_id: str | None,
    ) -> tuple[Listing | None, Any]:
        slug = item.get("slug")
        if not slug:
            return None, None
        title = str(item.get("title") or slug)
        image = item.get("image")
        offer = resolve_solescout_offer(item, variant_id=variant_id)
        disclaimer = item.get("disclaimer")
        warnings = list(offer.warnings)
        if disclaimer:
            warnings.insert(0, str(disclaimer))

        price = dollars_to_minor(offer.price_usd, "USD")
        size = (
            {"raw": offer.size_raw, "system": None} if offer.size_raw else None
        )

        listing_id = stable_id(
            self.name,
            "detail",
            str(slug),
            offer.kind,
            checked_at,
            variant_id or "",
            offer.canonical_url,
        )
        offer_key = f"{self.name}:{slug}:{offer.kind}"
        if variant_id:
            offer_key += f":{variant_id}"
        if offer.kind == "retailer_offer" and offer.store_name:
            offer_key += f":{offer.store_name}"

        ev = build_evidence(
            provider=self.name,
            source_url=offer.canonical_url,
            retrieved_at=checked_at,
            claims=[
                {"field": "title", "value": title, "excerpt": title},
                {
                    "field": "price",
                    "value": offer.price_usd,
                    "excerpt": (
                        f"store.price_usd={offer.price_usd}"
                        if offer.kind == "retailer_offer"
                        else f"aggregate/comparison price_usd={offer.price_usd}"
                    ),
                },
                {
                    "field": "destinationKind",
                    "value": offer.kind,
                    "excerpt": None,
                },
                {
                    "field": "retailer",
                    "value": offer.retailer,
                    "excerpt": None,
                },
                {
                    "field": "sizes_in_stock",
                    "value": item.get("sizes_in_stock"),
                    "excerpt": None,
                },
            ],
            raw_ref=f"solescout:product:{slug}",
            source_type="merchant_api" if offer.kind == "retailer_offer" else "search_result",
        )
        listing: Listing = {
            "id": listing_id,
            "offerKey": offer_key,
            "provider": self.name,
            "providerListingId": str(slug),
            "productId": str(slug),
            "variantId": variant_id,
            "retailer": offer.retailer,
            "canonicalUrl": offer.canonical_url,
            "imageUrls": [str(image)] if image else [],
            "title": title,
            "brand": item.get("brand"),
            "price": price,
            "shippingMinor": None,
            "condition": "unknown",
            "size": size,
            "availability": offer.availability,  # type: ignore[typeddict-item]
            "materialText": material_hint_from_title(title),
            "colorText": item.get("color"),
            "checkedAt": checked_at,
            "evidenceIds": [ev["id"]],
            "mode": "live",
            "destinationKind": offer.kind,  # type: ignore[typeddict-item]
            "warnings": warnings,
        }
        return listing, ev
