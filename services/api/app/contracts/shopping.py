"""Canonical shopping records (SRS section 12) plus integration additions.

Additions beyond the SRS logical schema exist to keep claims honest with
aggregator data:

* ``Listing.priceBasis`` says whether ``price`` is one seller's offer or the
  lowest price an aggregator saw across retailers it may not name.
* ``Listing.sellerVisibility`` says whether the cheapest seller is named.
* ``OutboundLink.kind`` separates an aggregator product page from a
  retailer product page. Neither is a checkout.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import Field, field_validator

from .base import Mutable, Record

EvidenceTier = Literal["verified", "likely", "similar"]
CheckState = Literal["satisfied", "violated", "unknown"]
ResultMode = Literal["live", "cached", "catalog", "fixture"]
Condition = Literal["new", "used", "any"]
SearchStatus = Literal["queued", "running", "completed", "partial", "no_match", "failed", "cancelled", "superseded"]
AnalysisStatus = Literal["queued", "running", "completed", "partial", "detection_unavailable", "failed"]
Section = Literal["primary", "needs_checking", "original_over_budget"]
PriceBasis = Literal["seller_offer", "aggregate_lowest", "unknown"]
SellerVisibility = Literal["named", "hidden", "unknown"]
LinkKind = Literal["aggregator_product_page", "retailer_product_page"]


class Money(Record):
    amount_minor: int = Field(ge=0)
    currency: str = Field(min_length=3, max_length=3)


class SizePref(Record):
    raw: str = Field(min_length=1, max_length=20)
    system: str | None = Field(default=None, max_length=20)


class Preferences(Record):
    country: str = "US"
    currency: str = "USD"
    max_item_price_minor: int | None = Field(default=None, ge=0, le=10_000_000)
    size: SizePref | None = None
    colors: list[str] = Field(default_factory=list, max_length=6)
    excluded_materials: list[str] = Field(default_factory=list, max_length=8)
    condition: Condition = "any"

    @field_validator("colors", "excluded_materials")
    @classmethod
    def _norm_words(cls, v: list[str]) -> list[str]:
        out: list[str] = []
        for s in v:
            w = " ".join(str(s).lower().split())[:30]
            if w and w not in out:
                out.append(w)
        return out


class PreferencePatch(Record):
    """Partial update. Only fields present in the request are applied (FR14)."""

    country: str | None = None
    currency: str | None = None
    max_item_price_minor: int | None = Field(default=None, ge=0, le=10_000_000)
    size: SizePref | None = None
    colors: list[str] | None = Field(default=None, max_length=6)
    excluded_materials: list[str] | None = Field(default=None, max_length=8)
    condition: Condition | None = None


class ShoppingSession(Record):
    id: str
    owner_id: str
    revision: int
    media_id: str | None
    analysis_id: str | None = None
    selected_garment_id: str | None
    preferences: Preferences
    active_search_id: str | None
    last_presented_result_ids: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class EvidenceClaim(Record):
    field: str
    value: Any = None
    excerpt: str | None = None


class Evidence(Record):
    id: str
    source_type: Literal["merchant_api", "merchant_page", "creator_link", "search_result", "human_verified"]
    source_url: str | None
    provider: str | None
    retrieved_at: datetime
    claims: list[EvidenceClaim]
    raw_response_ref: str | None


class SizeStock(Record):
    raw: str
    lowest_price: Money | None


class StoreOffer(Record):
    """A retailer the aggregator names. Its price is often not disclosed."""

    retailer: str
    url: str | None
    price: Money | None
    sizes_in_stock: list[str] = Field(default_factory=list)


class Listing(Record):
    id: str  # immutable observation snapshot ID
    offer_key: str
    provider: str
    provider_listing_id: str
    product_id: str | None
    variant_id: str | None
    retailer: str  # who the link goes to: the aggregator itself or a named retailer
    source_kind: Literal["aggregator", "retailer", "marketplace", "demo_catalog"]
    canonical_url: str
    image_urls: list[str]
    title: str
    brand: str | None
    price: Money | None
    price_basis: PriceBasis
    seller_visibility: SellerVisibility
    stores_carrying: int | None = None
    hidden_store_count: int | None = None
    store_offers: list[StoreOffer] = Field(default_factory=list)
    shipping_minor: int | None
    condition: Literal["new", "used", "unknown"]
    size: SizePref | None
    sizes_in_stock: list[SizeStock] | None  # None = not checked
    availability: Literal["in_stock", "out_of_stock", "unknown"]
    material_text: str | None
    color_text: str | None
    style_code: str | None = None
    checked_at: datetime
    detail_checked: bool
    evidence_ids: list[str]
    mode: ResultMode
    warnings: list[str] = Field(default_factory=list)


class ConstraintCheck(Record):
    constraint: str
    state: CheckState
    detail: str
    evidence_ids: list[str] = Field(default_factory=list)


class OutboundLink(Record):
    token: str
    kind: LinkKind
    label: str
    retailer: str
    price_note: str


class Recommendation(Record):
    id: str
    search_id: str
    garment_id: str
    listing_id: str
    section: Section
    identity_tier: EvidenceTier
    identity_evidence_ids: list[str]
    constraint_checks: list[ConstraintCheck]
    explanation: str
    warnings: list[str]
    rank: int
    ranking_version: str
    found_by: list[Literal["exact", "alternatives"]]
    links: list[OutboundLink]
    # Style-memory reasons this result was reordered (FEATURE_STYLE_MEMORY); empty when off.
    personalization: list[str] = Field(default_factory=list)


class SearchBudget(Mutable):
    max_tool_calls: int = 12
    used_tool_calls: int = 0
    max_detail_calls: int = 6
    used_detail_calls: int = 0
    max_rounds_per_worker: int = 3
    reasoning_calls: int = 0


class JobError(Record):
    code: str
    message: str
    retryable: bool


class SearchJob(Record):
    id: str
    session_id: str
    owner_id: str
    session_revision: int
    input_hash: str
    status: SearchStatus
    preference_snapshot: Preferences
    garment_id: str
    budget: SearchBudget
    deadline_at: datetime
    result_ids: list[str] = Field(default_factory=list)
    error: JobError | None = None
    worker_mode: Literal["grok", "rule_based"]
    catalog_mode: str
    created_at: datetime
    finished_at: datetime | None = None
    summary: str | None = None


class AgentEvent(Record):
    id: str
    job_id: str
    sequence: int
    stage: Literal[
        "locating_garment",
        "searching_original",
        "searching_alternatives",
        "verifying_listings",
        "ranking",
        "completed",
        "partial",
        "no_match",
        "failed",
        "superseded",
    ]
    summary: str
    tool_name: str | None = None
    worker: Literal["exact", "alternatives", "verifier", "system"] = "system"
    elapsed_ms: int | None = None
    evidence_ids: list[str] = Field(default_factory=list)
    result_ids: list[str] = Field(default_factory=list)
    at: datetime


class ReferralEvent(Record):
    id: str
    session_id: str
    recommendation_id: str
    listing_id: str
    link_token: str
    outbound_url: str
    link_kind: LinkKind
    occurred_at: datetime
    affiliate_configured: bool = False
    conversion_status: Literal["unknown", "confirmed", "reversed"] = "unknown"


class AnalysisJob(Record):
    id: str
    session_id: str
    owner_id: str
    media_id: str
    status: AnalysisStatus
    detection_mode: Literal["live", "unverified", "fixture", "unavailable"]
    frame_ids: list[str] = Field(default_factory=list)
    garment_ids: list[str] = Field(default_factory=list)
    shot_boundaries_ms: list[int] = Field(default_factory=list)
    issues: list[dict] = Field(default_factory=list)
    message: str | None = None
    created_at: datetime
    finished_at: datetime | None = None


class ApiError(Record):
    code: str
    message: str
    retryable: bool
    request_id: str
