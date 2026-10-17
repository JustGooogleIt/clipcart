from __future__ import annotations

import sys
import unittest
from pathlib import Path

API_ROOT = Path(__file__).resolve().parents[2]  # services/api
sys.path.insert(0, str(API_ROOT))

from app.providers.catalog.base import CatalogFilters  # noqa: E402
from app.providers.catalog.errors import CatalogProviderError  # noqa: E402
from app.providers.catalog.fixture_catalog import FixtureCatalogProvider  # noqa: E402


class FixtureProviderTests(unittest.TestCase):
    def test_fixture_leather_exclusion_case(self) -> None:
        provider = FixtureCatalogProvider()
        result = provider.search("leather jacket", CatalogFilters(), limit=5)
        self.assertEqual(result.mode, "fixture")
        self.assertEqual(len(result.listings), 1)
        listing = result.listings[0]
        self.assertEqual(listing["mode"], "fixture")
        self.assertIn("leather", (listing["materialText"] or "").lower())
        self.assertTrue(listing["evidenceIds"])

    def test_fixture_no_match_does_not_invent(self) -> None:
        provider = FixtureCatalogProvider()
        result = provider.search(
            "zzzzz-no-such-garment-clipcart", CatalogFilters(), limit=5
        )
        self.assertEqual(result.listings, [])
        self.assertEqual(result.evidence, [])

    def test_fixture_over_budget_bomber(self) -> None:
        provider = FixtureCatalogProvider()
        result = provider.search("black nylon bomber jacket", CatalogFilters(), limit=5)
        self.assertGreaterEqual(len(result.listings), 1)
        self.assertEqual(result.listings[0]["price"]["amountMinor"], 181000)

    def test_fixture_unavailable_size_via_details(self) -> None:
        provider = FixtureCatalogProvider()
        result = provider.get_details(
            "032c-oversized-graphic-printed-hoodie-fw22c2040", "M"
        )
        self.assertEqual(len(result.listings), 1)
        self.assertEqual(result.listings[0]["availability"], "out_of_stock")

    def test_fixture_image_search_unsupported(self) -> None:
        provider = FixtureCatalogProvider()
        with self.assertRaises(CatalogProviderError) as ctx:
            provider.search_image("crop_x", CatalogFilters(), 3)
        self.assertEqual(ctx.exception.code, "unsupported_capability")


if __name__ == "__main__":
    unittest.main()
