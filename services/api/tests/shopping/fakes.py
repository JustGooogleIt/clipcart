"""Offline catalog fake shaped like the SoleScout adapter output."""

from __future__ import annotations

import threading
import time
from datetime import datetime, timezone

from app.providers.catalog import CatalogSearchResult


def _now():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def item(slug, title, price, *, brand=None, color=None, provider="solescout"):
    return {
        "slug": slug, "title": title, "price": price, "brand": brand, "color": color, "provider": provider,
    }


class FakeCatalog:
    name = "solescout"

    def __init__(self, items, details=None, delay=0.0, fail=None):
        self.items = items
        self.details = details or {}
        self.delay = delay
        self.fail = fail
        self.calls = []
        self.lock = threading.Lock()

    def _listing(self, it, detail=False):
        t = _now()
        ev_id = f"ev_{it['slug']}_{'d' if detail else 's'}"
        listing = {
            "id": f"lst_{it['slug']}", "offerKey": f"solescout:{it['slug']}", "provider": it["provider"],
            "providerListingId": it["slug"], "productId": it["slug"], "variantId": None,
            "retailer": "SoleScout (aggregator)", "canonicalUrl": f"https://solescout.ai/product/{it['slug']}",
            "imageUrls": [f"https://solescout.ai/api/goat-image?slug={it['slug']}"], "title": it["title"],
            "brand": it["brand"], "price": None if it["price"] is None else {"amountMinor": it["price"] * 100, "currency": "USD"},
            "shippingMinor": None, "condition": "unknown", "size": None, "availability": "unknown",
            "materialText": None, "colorText": it["color"], "checkedAt": t, "evidenceIds": [ev_id], "mode": "live",
            "warnings": [],
        }
        ev = {"id": ev_id, "sourceType": "search_result", "sourceUrl": listing["canonicalUrl"], "provider": "solescout",
              "retrievedAt": t, "claims": [{"field": "price", "value": it["price"], "excerpt": None}], "rawResponseRef": None}
        return listing, ev

    def search(self, query, filters, limit):
        with self.lock:
            self.calls.append(("search", query))
        if self.delay:
            time.sleep(self.delay)
        if self.fail:
            raise self.fail
        out = [self._listing(i) for i in self.items][:limit]
        return CatalogSearchResult([x for x, _ in out], [e for _, e in out], "live", "solescout", query, 5, {})

    def search_image(self, *a, **k):
        raise NotImplementedError

    def get_details(self, slug, variant_id=None):
        with self.lock:
            self.calls.append(("detail", slug))
        it = next(i for i in self.items if i["slug"] == slug)
        listing, ev = self._listing(it, detail=True)
        d = self.details.get(slug, {})
        sizes = d.get("sizes", [])
        listing["availability"] = "in_stock" if sizes else "unknown"
        diag = {
            "stores": d.get("stores", []),
            "hidden_stores": {"count": d.get("hidden", 0)},
            "stores_carrying": d.get("carrying"),
            "sizes_in_stock": [{"size": s, "lowest_price_usd": it["price"]} for s in sizes],
            "style_code": d.get("style_code"),
        }
        ev["sourceType"] = "merchant_api"
        return CatalogSearchResult([listing], [ev], "live", "solescout", None, 5, diag)
