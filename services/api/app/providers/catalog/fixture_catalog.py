from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .base import CatalogFilters, CatalogSearchResult
from .errors import CatalogProviderError
from .normalize import utc_now
from .types import Evidence, Listing

_REPO_ROOT = Path(__file__).resolve().parents[5]
_DEFAULT_CATALOG = _REPO_ROOT / "fixtures" / "catalog" / "demo_catalog.json"
_DEFAULT_EXAMPLES = _REPO_ROOT / "fixtures" / "catalog" / "search_examples.json"
# Hand-written listings for UI review paths the sourced demo catalog can't cover (watches, jewelry, style words).
# Labelled synthetic in the file and on every listing; only loaded with the default catalog.
_UI_REVIEW_CATALOG = _REPO_ROOT / "fixtures" / "catalog" / "ui_review_catalog.json"


class FixtureCatalogProvider:
    """Labeled sourced demo catalog. Never claim these as live provider results."""

    name = "fixture"

    def __init__(self, catalog_path: Path | None = None) -> None:
        self.catalog_path = catalog_path or _DEFAULT_CATALOG
        self._data = self._load()
        if catalog_path is None and _UI_REVIEW_CATALOG.is_file():
            extra = json.loads(_UI_REVIEW_CATALOG.read_text(encoding="utf-8"))
            if "NOT REAL PRODUCTS" not in str(extra.get("fixture_label", "")).upper():
                raise CatalogProviderError("unavailable", "synthetic fixture catalog must carry its fixture_label", retryable=False)
            self._data = {**self._data, "listings": [*self._data.get("listings", []), *extra.get("listings", [])],
                          "evidence": [*self._data.get("evidence", []), *extra.get("evidence", [])]}

    def _load(self) -> dict[str, Any]:
        if not self.catalog_path.is_file():
            raise CatalogProviderError(
                "unavailable",
                f"fixture catalog missing: {self.catalog_path}",
                retryable=False,
            )
        return json.loads(self.catalog_path.read_text(encoding="utf-8"))

    def search(
        self, query: str, filters: CatalogFilters, limit: int
    ) -> CatalogSearchResult:
        q = (query or "").strip().lower()
        limit = max(1, min(int(limit), 20))
        examples_path = _DEFAULT_EXAMPLES
        matched_ids: list[str] | None = None
        if examples_path.is_file():
            examples = json.loads(examples_path.read_text(encoding="utf-8"))
            for ex in examples.get("examples", []):
                needles = [str(x).lower() for x in ex.get("matchQueries", [])]
                if q in needles or any(n in q for n in needles if n):
                    matched_ids = list(ex.get("listingIds") or [])
                    break
        listings_out: list[Listing] = []
        evidence_out: list[Evidence] = []
        checked_at = utc_now()
        for item in self._data.get("listings", []):
            if matched_ids is not None and item.get("id") not in matched_ids:
                continue
            if matched_ids is None:
                blob = " ".join(
                    str(item.get(k) or "")
                    for k in ("title", "brand", "category", "materialText", "colorText")
                ).lower()
                if q and q not in blob and not all(tok in blob for tok in q.split()):
                    continue
            listing = dict(item)
            listing["checkedAt"] = checked_at
            listing["mode"] = listing.get("mode") or "fixture"
            listing.setdefault("destinationKind", "comparison")
            listings_out.append(listing)  # type: ignore[arg-type]
            for ev in self._data.get("evidence", []):
                if ev.get("id") in (listing.get("evidenceIds") or []):
                    evidence_out.append(ev)
            if len(listings_out) >= limit:
                break
        return CatalogSearchResult(
            listings=listings_out,
            evidence=evidence_out,
            mode="fixture",
            provider=self.name,
            query=query,
            elapsed_ms=0,
            diagnostics={"labeled": True, "catalogVersion": self._data.get("version")},
        )

    def search_image(
        self, crop_asset_id: str, filters: CatalogFilters, limit: int
    ) -> CatalogSearchResult:
        raise CatalogProviderError(
            "unsupported_capability",
            "fixture catalog has no image index",
            retryable=False,
        )

    def get_details(
        self, provider_listing_id: str, variant_id: str | None = None
    ) -> CatalogSearchResult:
        checked_at = utc_now()
        for item in self._data.get("listings", []):
            if item.get("providerListingId") != provider_listing_id and item.get(
                "id"
            ) != provider_listing_id:
                continue
            listing = dict(item)
            listing["checkedAt"] = checked_at
            listing.setdefault("destinationKind", "comparison")
            if variant_id:
                listing["variantId"] = variant_id
                size = listing.get("size") or {}
                if size.get("raw") and size["raw"].lower() != variant_id.lower():
                    listing["availability"] = "out_of_stock"
            evidence = [
                ev
                for ev in self._data.get("evidence", [])
                if ev.get("id") in (listing.get("evidenceIds") or [])
            ]
            return CatalogSearchResult(
                listings=[listing],  # type: ignore[list-item]
                evidence=evidence,  # type: ignore[arg-type]
                mode=str(listing.get("mode") or "fixture"),
                provider=self.name,
                elapsed_ms=0,
                diagnostics={"labeled": True},
            )
        return CatalogSearchResult(
            listings=[],
            evidence=[],
            mode="fixture",
            provider=self.name,
            elapsed_ms=0,
            diagnostics={"labeled": True, "notFound": provider_listing_id},
        )
