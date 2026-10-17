"""Convert catalog adapter output into canonical Listing/Evidence records.

Honesty rules enforced here, for every provider:

* SoleScout prices are the lowest price SoleScout saw across retailers whose
  names are often hidden. They become ``priceBasis = aggregate_lowest`` and
  the listing's retailer is "SoleScout", never a named store.
* A visible store keeps its own price, which is usually null, so the
  aggregate price is never attached to it.
* SoleScout and fixture product pages are ``aggregator_product_page`` links.
  They are not retailer checkouts.
* Fixture data keeps its capture timestamp instead of a fresh one.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

from app.contracts import Evidence, EvidenceClaim, Listing, Money, SizePref, SizeStock, StoreOffer

AGGREGATOR_PROVIDERS = {"solescout"}


def _parse_dt(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return datetime.now(timezone.utc)


def safe_url(url: Any) -> str | None:
    """Only absolute https URLs without credentials are stored as outbound targets."""
    if not isinstance(url, str):
        return None
    p = urlparse(url.strip())
    if p.scheme != "https" or not p.hostname or p.username or p.password:
        return None
    return url.strip()


def _money_usd(dollars: Any) -> Money | None:
    if dollars is None:
        return None
    try:
        return Money(amount_minor=int(round(float(dollars) * 100)), currency="USD")
    except (TypeError, ValueError):
        return None


def to_evidence(ev: dict) -> Evidence:
    return Evidence(
        id=str(ev["id"]),
        source_type=ev.get("sourceType") or "search_result",
        source_url=ev.get("sourceUrl"),
        provider=ev.get("provider"),
        retrieved_at=_parse_dt(ev.get("retrievedAt")),
        claims=[
            EvidenceClaim(field=str(c.get("field")), value=c.get("value"), excerpt=c.get("excerpt"))
            for c in (ev.get("claims") or [])
        ],
        raw_response_ref=ev.get("rawResponseRef"),
    )


def snapshot_id(offer_key: str, checked_at: datetime, detail: bool) -> str:
    raw = f"{offer_key}|{checked_at.isoformat()}|{'detail' if detail else 'search'}"
    return "lst_" + hashlib.sha256(raw.encode()).hexdigest()[:24]


def to_listing(
    item: dict,
    *,
    result_mode: str,
    evidence: list[Evidence],
    diagnostics: dict | None = None,
    detail: bool = False,
) -> Listing | None:
    url = safe_url(item.get("canonicalUrl"))
    if not url:
        return None
    provider = str(item.get("provider") or "unknown")
    mode = item.get("mode") or result_mode
    if mode not in ("live", "cached", "catalog", "fixture"):
        mode = "fixture"
    is_fixture = mode in ("fixture", "catalog")
    ev_ids = [str(e) for e in (item.get("evidenceIds") or [])]
    my_ev = [e for e in evidence if e.id in ev_ids]
    if is_fixture and my_ev:
        checked_at = min(e.retrieved_at for e in my_ev)  # capture time, not "now"
    else:
        checked_at = _parse_dt(item.get("checkedAt"))

    price_raw = item.get("price") or None
    price = None
    if isinstance(price_raw, dict) and price_raw.get("amountMinor") is not None:
        price = Money(amount_minor=int(price_raw["amountMinor"]), currency=str(price_raw.get("currency") or "USD"))

    warnings = [str(w) for w in (item.get("warnings") or [])]
    diag = diagnostics or {}
    store_offers: list[StoreOffer] = []
    hidden_count = None
    stores_carrying = None
    sizes_in_stock = None
    style_code = diag.get("style_code")

    if provider in AGGREGATOR_PROVIDERS:
        source_kind = "aggregator"
        retailer = "SoleScout"
        price_basis = "aggregate_lowest" if price else "unknown"
        seller_visibility = "unknown"
        if detail:
            hidden = diag.get("hidden_stores") or {}
            hidden_count = int(hidden.get("count") or 0)
            stores_carrying = diag.get("stores_carrying")
            for s in diag.get("stores") or []:
                store_offers.append(
                    StoreOffer(
                        retailer=str(s.get("name") or "Unnamed retailer")[:60],
                        url=safe_url(s.get("url")),
                        price=_money_usd(s.get("price_usd")),
                        sizes_in_stock=[
                            str(x.get("size") if isinstance(x, dict) else x)
                            for x in (s.get("sizes_in_stock") or [])
                            if (x.get("size") if isinstance(x, dict) else x)
                        ][:30],
                    )
                )
            named_at_lowest = price is not None and any(
                o.price is not None and o.price.amount_minor == price.amount_minor for o in store_offers
            )
            if hidden_count:
                seller_visibility = "hidden"
            elif named_at_lowest:
                seller_visibility = "named"
            sizes_in_stock = [
                SizeStock(raw=str(x.get("size")), lowest_price=_money_usd(x.get("lowest_price_usd")))
                if isinstance(x, dict)
                else SizeStock(raw=str(x), lowest_price=None)
                for x in (diag.get("sizes_in_stock") or [])
                if (x.get("size") if isinstance(x, dict) else x)
            ]
        if is_fixture:
            warnings.append("Captured fixture snapshot; not a fresh check.")
    elif provider.startswith("ebay"):
        source_kind = "marketplace"
        retailer = str(item.get("retailer") or "eBay seller")
        price_basis = "seller_offer" if price else "unknown"
        seller_visibility = "named"
    else:
        source_kind = "demo_catalog" if is_fixture else "retailer"
        retailer = str(item.get("retailer") or "Unknown retailer")
        price_basis = "seller_offer" if price else "unknown"
        seller_visibility = "named"

    if is_fixture and sizes_in_stock is None and item.get("availability") == "in_stock" and item.get("size"):
        # Fixture rows capture one size that SoleScout listed as in stock.
        raw = str(item["size"].get("raw"))
        sizes_in_stock = [SizeStock(raw=raw, lowest_price=price)]

    size = None
    if isinstance(item.get("size"), dict) and item["size"].get("raw"):
        size = SizePref(raw=str(item["size"]["raw"])[:20], system=item["size"].get("system"))

    return Listing(
        id=snapshot_id(str(item.get("offerKey") or url), checked_at, detail),
        offer_key=str(item.get("offerKey") or f"{provider}:{item.get('providerListingId')}"),
        provider=provider,
        provider_listing_id=str(item.get("providerListingId") or ""),
        product_id=item.get("productId"),
        variant_id=item.get("variantId"),
        retailer=retailer,
        source_kind=source_kind,
        canonical_url=url,
        image_urls=[u for u in (safe_url(x) for x in (item.get("imageUrls") or [])) if u][:4],
        title=str(item.get("title") or "Untitled")[:200],
        brand=item.get("brand"),
        price=price,
        price_basis=price_basis,
        seller_visibility=seller_visibility,
        stores_carrying=stores_carrying,
        hidden_store_count=hidden_count,
        store_offers=store_offers,
        shipping_minor=item.get("shippingMinor"),
        condition=item.get("condition") if item.get("condition") in ("new", "used") else "unknown",
        size=size,
        sizes_in_stock=sizes_in_stock,
        availability=item.get("availability") if item.get("availability") in ("in_stock", "out_of_stock") else "unknown",
        material_text=item.get("materialText"),
        color_text=item.get("colorText"),
        style_code=str(style_code) if style_code else None,
        checked_at=checked_at,
        detail_checked=detail,
        evidence_ids=ev_ids,
        mode=mode,
        warnings=list(dict.fromkeys(warnings)),
    )
