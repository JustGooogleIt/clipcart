"""Catalog providers (teammate-owned until Claude wires shopping tools).

Logical interface (SRS §12):
  CatalogProvider.search(query, filters, limit) -> listings + evidence
  CatalogProvider.search_image(crop_asset_id, filters, limit) -> listings | unsupported
  CatalogProvider.get_details(provider_listing_id, variant_id) -> listing + evidence
"""

from .base import CatalogFilters, CatalogProvider, CatalogSearchResult
from .ebay import EbayBrowseCatalogProvider
from .errors import CatalogProviderError
from .factory import get_catalog_provider
from .fixture_catalog import FixtureCatalogProvider
from .solescout import SoleScoutCatalogProvider

__all__ = [
    "CatalogFilters",
    "CatalogProvider",
    "CatalogProviderError",
    "CatalogSearchResult",
    "EbayBrowseCatalogProvider",
    "FixtureCatalogProvider",
    "SoleScoutCatalogProvider",
    "get_catalog_provider",
]
