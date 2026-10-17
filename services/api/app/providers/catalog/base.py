from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from .types import Evidence, Listing


@dataclass(frozen=True)
class CatalogFilters:
    category: str | None = None  # jacket | top | bag | other
    country: str = "US"
    currency: str = "USD"
    max_price_minor: int | None = None
    size_raw: str | None = None
    colors: tuple[str, ...] = ()
    excluded_materials: tuple[str, ...] = ()
    condition: str = "any"


@dataclass
class CatalogSearchResult:
    listings: list[Listing]
    evidence: list[Evidence]
    mode: str
    provider: str
    query: str | None = None
    elapsed_ms: int | None = None
    diagnostics: dict[str, Any] = field(default_factory=dict)


class CatalogProvider(Protocol):
    name: str

    def search(
        self, query: str, filters: CatalogFilters, limit: int
    ) -> CatalogSearchResult: ...

    def search_image(
        self, crop_asset_id: str, filters: CatalogFilters, limit: int
    ) -> CatalogSearchResult: ...

    def get_details(
        self, provider_listing_id: str, variant_id: str | None = None
    ) -> CatalogSearchResult: ...
