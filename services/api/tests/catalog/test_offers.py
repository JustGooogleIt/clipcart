from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

API_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(API_ROOT))

from app.providers.catalog.base import CatalogFilters  # noqa: E402
from app.providers.catalog.offers import (  # noqa: E402
    resolve_solescout_offer,
    usable_direct_stores,
)
from app.providers.catalog.solescout import SoleScoutCatalogProvider  # noqa: E402

FIXTURES = Path(__file__).resolve().parents[4] / "fixtures" / "catalog" / "raw"


class OfferHonestyTests(unittest.TestCase):
    def test_hidden_lowest_not_paired_with_visible_store(self) -> None:
        product = json.loads(
            (FIXTURES / "product_3-pack-classic-slim-crew-tee-nscnp3whd.json").read_text()
        )
        # Aggregate lowest $55 is hidden; Farfetch visible at $74.
        self.assertEqual(product["lowest_price_usd"], 55)
        offer = resolve_solescout_offer(product, variant_id="M")
        self.assertEqual(offer.kind, "retailer_offer")
        self.assertEqual(offer.price_usd, 74)
        self.assertTrue(offer.canonical_url.startswith("https://www.farfetch.com/"))
        self.assertNotEqual(offer.price_usd, product["lowest_price_usd"])
        self.assertNotIn("solescout.ai/product", offer.canonical_url)

    def test_visible_store_without_price_is_comparison(self) -> None:
        product = json.loads((FIXTURES / "solescout_hoodie.json").read_text())
        # Offseason URL present, price null; hidden holds the $100 lowest.
        offer = resolve_solescout_offer(product)
        self.assertEqual(offer.kind, "comparison")
        self.assertIn("solescout.ai/product", offer.canonical_url)
        self.assertEqual(offer.retailer, "SoleScout (price comparison)")
        self.assertEqual(offer.price_usd, 100)
        self.assertTrue(
            any("without price" in w for w in offer.warnings)
            or any("not a retailer checkout" in w for w in offer.warnings)
        )
        self.assertFalse(
            any(
                (s.get("url") or "").startswith("https://off--season.com")
                and offer.canonical_url == s.get("url")
                for s in product["stores"]
            )
            and offer.kind == "retailer_offer"
        )

    def test_size_specific_uses_same_store_price_not_aggregate(self) -> None:
        product = json.loads(
            (FIXTURES / "product_3-pack-classic-slim-crew-tee-nscnp3whd.json").read_text()
        )
        # Aggregate size M is $55; Farfetch store price for M is $74.
        m_agg = next(
            r["lowest_price_usd"]
            for r in product["sizes_in_stock"]
            if r["size"] == "M"
        )
        self.assertEqual(m_agg, 55)
        offer = resolve_solescout_offer(product, variant_id="M")
        self.assertEqual(offer.kind, "retailer_offer")
        self.assertEqual(offer.size_raw, "M")
        self.assertEqual(offer.price_usd, 74)

    def test_size_missing_on_visible_stores_falls_back_to_comparison(self) -> None:
        product = json.loads(
            (FIXTURES / "product_3-pack-classic-slim-crew-tee-nscnp3whd.json").read_text()
        )
        offer = resolve_solescout_offer(product, variant_id="XXL")
        self.assertEqual(offer.kind, "comparison")
        self.assertIn("solescout.ai/product", offer.canonical_url)
        self.assertEqual(offer.availability, "out_of_stock")

    def test_usable_direct_stores_requires_url_and_price(self) -> None:
        stores = [
            {"name": "A", "url": "https://a.example/x", "price_usd": None, "sizes_in_stock": ["M"]},
            {"name": "B", "url": "https://b.example/x", "price_usd": 40, "sizes_in_stock": ["M"]},
            {"name": "C", "price_usd": 10, "sizes_in_stock": ["M"]},
        ]
        usable = usable_direct_stores(stores, variant_id="M")
        self.assertEqual(len(usable), 1)
        self.assertEqual(usable[0]["name"], "B")

    def test_adapter_get_details_maps_destination_kind(self) -> None:
        product = json.loads(
            (FIXTURES / "product_3-pack-classic-slim-crew-tee-nscnp3whd.json").read_text()
        )
        provider = SoleScoutCatalogProvider()
        listing, _ev = provider._listing_from_product(product, "2026-10-17T21:00:00Z", "M")
        assert listing is not None
        self.assertEqual(listing["destinationKind"], "retailer_offer")
        self.assertEqual(listing["price"]["amountMinor"], 7400)
        self.assertTrue(listing["canonicalUrl"].startswith("https://www.farfetch.com/"))
        self.assertEqual(listing["retailer"], "Grp-Ff")

    def test_adapter_search_hit_is_comparison_only(self) -> None:
        provider = SoleScoutCatalogProvider()
        hit = {
            "slug": "example-jacket",
            "title": "Example Jacket",
            "brand": "Example",
            "lowest_price_usd": 120,
            "url": "https://solescout.ai/product/example-jacket",
            "image": "https://example.com/j.jpg",
        }
        listing, _ev = provider._listing_from_search_hit(
            hit, "2026-10-17T21:00:00Z", CatalogFilters(currency="USD")
        )
        assert listing is not None
        self.assertEqual(listing["destinationKind"], "comparison")
        self.assertEqual(listing["retailer"], "SoleScout (price comparison)")
        self.assertIn("solescout.ai/product", listing["canonicalUrl"])


if __name__ == "__main__":
    unittest.main()
