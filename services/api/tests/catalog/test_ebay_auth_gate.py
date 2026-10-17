from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

API_ROOT = Path(__file__).resolve().parents[2]  # services/api
sys.path.insert(0, str(API_ROOT))

from app.providers.catalog.base import CatalogFilters  # noqa: E402
from app.providers.catalog.ebay import EbayBrowseCatalogProvider  # noqa: E402
from app.providers.catalog.errors import CatalogProviderError  # noqa: E402


class EbayAuthGateTests(unittest.TestCase):
    def test_ebay_fails_closed_without_credentials(self) -> None:
        old_id = os.environ.pop("EBAY_CLIENT_ID", None)
        old_secret = os.environ.pop("EBAY_CLIENT_SECRET", None)
        try:
            provider = EbayBrowseCatalogProvider()
            with self.assertRaises(CatalogProviderError) as ctx:
                provider.search("denim jacket", CatalogFilters(), 3)
            self.assertEqual(ctx.exception.code, "auth_error")
        finally:
            if old_id is not None:
                os.environ["EBAY_CLIENT_ID"] = old_id
            if old_secret is not None:
                os.environ["EBAY_CLIENT_SECRET"] = old_secret


if __name__ == "__main__":
    unittest.main()
