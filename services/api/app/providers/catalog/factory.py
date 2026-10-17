from __future__ import annotations

import os

from .base import CatalogProvider
from .ebay import EbayBrowseCatalogProvider
from .fixture_catalog import FixtureCatalogProvider
from .solescout import SoleScoutCatalogProvider


def get_catalog_provider(name: str | None = None) -> CatalogProvider:
    provider = (name or os.getenv("CATALOG_PROVIDER") or "solescout").strip().lower()
    if provider in {"fixture", "catalog", "demo"}:
        return FixtureCatalogProvider()
    if provider == "solescout":
        return SoleScoutCatalogProvider()
    if provider in {"ebay", "ebay_browse"}:
        return EbayBrowseCatalogProvider()
    raise ValueError(
        f"Unknown CATALOG_PROVIDER={provider!r}; use solescout, fixture, or ebay"
    )
