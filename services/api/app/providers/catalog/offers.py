"""Honest purchase-destination selection for SoleScout product payloads.

Rules:
- A *retailer_offer* requires the same visible store record to supply URL,
  price, and (when a size/variant is requested) that size in ``sizes_in_stock``.
- Never pair ``lowest_price_usd`` / hidden-store prices with a different
  store's URL.
- Never label a SoleScout product page as retailer checkout.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ResolvedOffer:
    kind: str  # retailer_offer | comparison
    retailer: str
    canonical_url: str
    price_usd: float | None
    size_raw: str | None
    availability: str  # in_stock | out_of_stock | unknown
    warnings: tuple[str, ...]
    store_name: str | None = None


def _store_has_size(store: dict[str, Any], variant_id: str) -> bool:
    sizes = store.get("sizes_in_stock") or []
    want = variant_id.strip().lower()
    return any(str(s).strip().lower() == want for s in sizes)


def usable_direct_stores(
    stores: list[Any] | None, *, variant_id: str | None = None
) -> list[dict[str, Any]]:
    """Stores that can back a retailer_offer (URL + priced, optional size)."""
    out: list[dict[str, Any]] = []
    for store in stores or []:
        if not isinstance(store, dict):
            continue
        url = store.get("url")
        price = store.get("price_usd")
        if not url or price is None:
            continue
        try:
            float(price)
        except (TypeError, ValueError):
            continue
        if variant_id and not _store_has_size(store, variant_id):
            continue
        out.append(store)
    return out


def aggregate_size_price(
    sizes_in_stock: list[Any] | None, variant_id: str | None
) -> float | None:
    """Size-row lowest from SoleScout aggregate table (may be a hidden retailer)."""
    if not variant_id or not sizes_in_stock:
        return None
    want = variant_id.strip().lower()
    for row in sizes_in_stock:
        if not isinstance(row, dict):
            continue
        if str(row.get("size", "")).strip().lower() != want:
            continue
        price = row.get("lowest_price_usd")
        if price is None:
            return None
        try:
            return float(price)
        except (TypeError, ValueError):
            return None
    return None


def resolve_solescout_offer(
    product: dict[str, Any],
    *,
    variant_id: str | None = None,
) -> ResolvedOffer:
    slug = product.get("slug") or ""
    comparison_url = str(
        product.get("url") or f"https://solescout.ai/product/{slug}"
    )
    stores = product.get("stores") if isinstance(product.get("stores"), list) else []
    hidden = product.get("hidden_stores") if isinstance(product.get("hidden_stores"), dict) else {}
    sizes = (
        product.get("sizes_in_stock")
        if isinstance(product.get("sizes_in_stock"), list)
        else []
    )

    direct = usable_direct_stores(stores, variant_id=variant_id)
    if direct:
        store = min(direct, key=lambda s: float(s["price_usd"]))
        warnings = [
            "Direct retailer offer: URL, price, and size (if requested) come from the same store record.",
        ]
        if hidden.get("count"):
            warnings.append(
                f"SoleScout reports {hidden['count']} cheaper hidden retailer(s); "
                "their price is not paired with this store URL."
            )
        size_raw = variant_id.strip() if variant_id else None
        if size_raw is None and len(store.get("sizes_in_stock") or []) == 1:
            size_raw = str(store["sizes_in_stock"][0])
        return ResolvedOffer(
            kind="retailer_offer",
            retailer=str(store.get("name") or "unknown retailer"),
            canonical_url=str(store["url"]),
            price_usd=float(store["price_usd"]),
            size_raw=size_raw,
            availability="in_stock",
            warnings=tuple(warnings),
            store_name=str(store.get("name") or ""),
        )

    # Comparison path — SoleScout page is not retailer checkout.
    warnings = [
        "SoleScout comparison result — not a retailer checkout destination.",
        "Do not treat the SoleScout product page as merchant checkout.",
    ]
    visible_unpriced = [
        s
        for s in stores
        if isinstance(s, dict) and s.get("url") and s.get("price_usd") is None
    ]
    if visible_unpriced:
        names = ", ".join(str(s.get("name") or "store") for s in visible_unpriced[:3])
        warnings.append(
            f"Visible store link(s) without price ({names}) were not used as checkout."
        )
    if hidden.get("count"):
        warnings.append(
            f"{hidden['count']} cheapest retailer name(s) hidden on free tier; "
            "aggregate lowest price is not tied to a purchasable URL we can open."
        )

    price_usd: float | None
    size_raw = variant_id.strip() if variant_id else None
    size_price = aggregate_size_price(sizes, variant_id)
    if size_price is not None:
        price_usd = size_price
        warnings.append(
            f"Displayed price is SoleScout aggregate lowest for size {variant_id!r} "
            "(may be a hidden retailer)."
        )
        # Size appears in aggregate table but no priced visible store carries it.
        availability = "unknown"
    else:
        lowest = product.get("lowest_price_usd")
        try:
            price_usd = float(lowest) if lowest is not None else None
        except (TypeError, ValueError):
            price_usd = None
        if price_usd is not None:
            warnings.append(
                "Displayed price is SoleScout aggregate lowest_price_usd, not a store checkout price."
            )
        if variant_id:
            # Requested size not on any priced visible store and not in aggregate rows.
            in_aggregate = any(
                isinstance(r, dict)
                and str(r.get("size", "")).strip().lower() == variant_id.strip().lower()
                for r in sizes
            )
            availability = "out_of_stock" if not in_aggregate and sizes else "unknown"
        else:
            availability = "unknown"

    return ResolvedOffer(
        kind="comparison",
        retailer="SoleScout (price comparison)",
        canonical_url=comparison_url,
        price_usd=price_usd,
        size_raw=size_raw,
        availability=availability,
        warnings=tuple(warnings),
        store_name=None,
    )
