"""eBay Browse adapter skeleton.

Not live yet: requires EBAY_CLIENT_ID + EBAY_CLIENT_SECRET and a successful
client-credentials token with buy.browse scope. Until then, calls fail with
auth_error / unavailable so the app can fall back to SoleScout or fixtures.
"""

from __future__ import annotations

import base64
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from .base import CatalogFilters, CatalogSearchResult
from .errors import CatalogProviderError
from .normalize import build_evidence, dollars_to_minor, stable_id, utc_now
from .types import Listing


class EbayBrowseCatalogProvider:
    name = "ebay_browse"

    def __init__(self) -> None:
        self.client_id = (os.getenv("EBAY_CLIENT_ID") or "").strip()
        self.client_secret = (os.getenv("EBAY_CLIENT_SECRET") or "").strip()
        self.marketplace = os.getenv("EBAY_MARKETPLACE_ID") or "EBAY_US"
        self.token_url = os.getenv(
            "EBAY_TOKEN_URL", "https://api.ebay.com/identity/v1/oauth2/token"
        )
        self.api_base = os.getenv(
            "EBAY_API_BASE", "https://api.ebay.com/buy/browse/v1"
        ).rstrip("/")
        self._token: str | None = None
        self._token_expires_at = 0.0

    def search(
        self, query: str, filters: CatalogFilters, limit: int
    ) -> CatalogSearchResult:
        token = self._access_token()
        limit = max(1, min(int(limit), 50))
        params = {"q": query.strip(), "limit": str(limit)}
        if filters.category:
            # Category IDs are marketplace-specific; leave unset until mapped.
            pass
        path = "/item_summary/search?" + urllib.parse.urlencode(params)
        payload, elapsed_ms = self._authorized_get(path, token)
        checked_at = utc_now()
        listings: list[Listing] = []
        evidence = []
        for item in payload.get("itemSummaries") or []:
            listing, ev = self._from_summary(item, checked_at, filters.currency)
            if listing:
                listings.append(listing)
                evidence.append(ev)
        return CatalogSearchResult(
            listings=listings,
            evidence=evidence,
            mode="live",
            provider=self.name,
            query=query,
            elapsed_ms=elapsed_ms,
            diagnostics={"total": payload.get("total")},
        )

    def search_image(
        self, crop_asset_id: str, filters: CatalogFilters, limit: int
    ) -> CatalogSearchResult:
        # Browse supports image search via a different endpoint/body; wire after
        # credentials and crop-byte upload path exist.
        raise CatalogProviderError(
            "unsupported_capability",
            "eBay image search not wired yet on this branch",
            retryable=False,
        )

    def get_details(
        self, provider_listing_id: str, variant_id: str | None = None
    ) -> CatalogSearchResult:
        token = self._access_token()
        item_id = urllib.parse.quote(provider_listing_id, safe="")
        path = f"/item/{item_id}"
        payload, elapsed_ms = self._authorized_get(path, token)
        checked_at = utc_now()
        listing, ev = self._from_item(payload, checked_at, variant_id)
        return CatalogSearchResult(
            listings=[listing] if listing else [],
            evidence=[ev] if listing else [],
            mode="live",
            provider=self.name,
            elapsed_ms=elapsed_ms,
            diagnostics={},
        )

    def _access_token(self) -> str:
        if not self.client_id or not self.client_secret:
            raise CatalogProviderError(
                "auth_error",
                "EBAY_CLIENT_ID / EBAY_CLIENT_SECRET not configured",
                retryable=False,
            )
        now = time.time()
        if self._token and now < self._token_expires_at - 60:
            return self._token
        basic = base64.b64encode(
            f"{self.client_id}:{self.client_secret}".encode("utf-8")
        ).decode("ascii")
        body = urllib.parse.urlencode(
            {
                "grant_type": "client_credentials",
                "scope": "https://api.ebay.com/oauth/api_scope/buy.browse",
            }
        ).encode("utf-8")
        req = urllib.request.Request(
            self.token_url,
            data=body,
            method="POST",
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Authorization": f"Basic {basic}",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raise CatalogProviderError(
                "auth_error", f"token HTTP {exc.code}", retryable=False
            ) from exc
        except Exception as exc:  # noqa: BLE001
            raise CatalogProviderError(
                "unavailable", f"token request failed: {exc}", retryable=True
            ) from exc
        token = data.get("access_token")
        if not token:
            raise CatalogProviderError(
                "auth_error", "token response missing access_token", retryable=False
            )
        self._token = token
        self._token_expires_at = now + float(data.get("expires_in") or 7200)
        return token

    def _authorized_get(self, path: str, token: str) -> tuple[dict[str, Any], int]:
        url = f"{self.api_base}{path}"
        req = urllib.request.Request(
            url,
            headers={
                "Authorization": f"Bearer {token}",
                "X-EBAY-C-MARKETPLACE-ID": self.marketplace,
                "Accept": "application/json",
            },
        )
        t0 = time.perf_counter()
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code in (401, 403):
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
            raise CatalogProviderError("timeout", "timed out", retryable=True) from exc
        elapsed_ms = int((time.perf_counter() - t0) * 1000)
        if not isinstance(payload, dict):
            raise CatalogProviderError(
                "invalid_response", "expected object", retryable=False
            )
        return payload, elapsed_ms

    def _from_summary(
        self, item: dict[str, Any], checked_at: str, currency: str
    ) -> tuple[Listing | None, Any]:
        item_id = item.get("itemId")
        if not item_id:
            return None, None
        price_obj = item.get("price") or {}
        amount = price_obj.get("value")
        cur = price_obj.get("currency") or currency
        try:
            dollars = float(amount) if amount is not None else None
        except (TypeError, ValueError):
            dollars = None
        price = dollars_to_minor(dollars, cur) if dollars is not None else None
        url = item.get("itemWebUrl") or item.get("itemHref")
        images = []
        if item.get("image", {}).get("imageUrl"):
            images.append(item["image"]["imageUrl"])
        for img in item.get("thumbnailImages") or []:
            if img.get("imageUrl"):
                images.append(img["imageUrl"])
        title = str(item.get("title") or item_id)
        listing_id = stable_id(self.name, "summary", str(item_id), checked_at)
        ev = build_evidence(
            provider=self.name,
            source_url=url,
            retrieved_at=checked_at,
            claims=[
                {"field": "title", "value": title, "excerpt": title},
                {"field": "price", "value": price_obj, "excerpt": None},
            ],
            raw_ref=f"ebay:summary:{item_id}",
            source_type="merchant_api",
        )
        listing: Listing = {
            "id": listing_id,
            "offerKey": f"{self.name}:{item_id}",
            "provider": self.name,
            "providerListingId": str(item_id),
            "productId": item.get("epid"),
            "variantId": None,
            "retailer": "eBay",
            "canonicalUrl": str(url or ""),
            "imageUrls": images,
            "title": title,
            "brand": (item.get("brand") or None),
            "price": price,
            "shippingMinor": None,
            "condition": "unknown",
            "size": None,
            "availability": "unknown",
            "materialText": None,
            "colorText": None,
            "checkedAt": checked_at,
            "evidenceIds": [ev["id"]],
            "mode": "live",
            "warnings": ["eBay adapter provisional until credentials verified."],
        }
        return listing, ev

    def _from_item(
        self, item: dict[str, Any], checked_at: str, variant_id: str | None
    ) -> tuple[Listing | None, Any]:
        # Item detail payload differs slightly; reuse summary mapping fields.
        listing, ev = self._from_summary(item, checked_at, "USD")
        if listing and variant_id:
            listing["variantId"] = variant_id
        return listing, ev
