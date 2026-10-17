"""Provisional listing/evidence shapes mirroring SRS §12.

Claude owns canonical Pydantic models. These TypedDicts are the teammate
normalization target so shopping code can swap to contracts without
rewriting SoleScout field mapping.
"""

from __future__ import annotations

from typing import Any, Literal, NotRequired, TypedDict

EvidenceTier = Literal["verified", "likely", "similar"]
ResultMode = Literal["live", "cached", "catalog", "fixture"]
Availability = Literal["in_stock", "out_of_stock", "unknown"]
Condition = Literal["new", "used", "unknown"]
# retailer_offer: canonicalUrl+price(+size) come from the same visible store record.
# comparison: SoleScout product page; not a retailer checkout destination.
DestinationKind = Literal["retailer_offer", "comparison"]


class Money(TypedDict):
    amountMinor: int
    currency: str


class SizeInfo(TypedDict):
    raw: str
    system: str | None


class EvidenceClaim(TypedDict):
    field: str
    value: Any
    excerpt: str | None


class Evidence(TypedDict):
    id: str
    sourceType: Literal[
        "merchant_api",
        "merchant_page",
        "creator_link",
        "search_result",
        "human_verified",
    ]
    sourceUrl: str | None
    provider: str | None
    retrievedAt: str
    claims: list[EvidenceClaim]
    rawResponseRef: str | None


class Listing(TypedDict):
    id: str
    offerKey: str
    provider: str
    providerListingId: str
    productId: str | None
    variantId: str | None
    retailer: str
    canonicalUrl: str
    imageUrls: list[str]
    title: str
    brand: str | None
    price: Money | None
    shippingMinor: int | None
    condition: Condition
    size: SizeInfo | None
    availability: Availability
    materialText: str | None
    colorText: str | None
    checkedAt: str
    evidenceIds: list[str]
    mode: ResultMode
    destinationKind: DestinationKind
    # Optional diagnostics for integrators; strip before browser if needed.
    warnings: NotRequired[list[str]]
