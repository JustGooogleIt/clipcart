"""Provider-neutral shopping research jobs (FEATURE_AGENT_RESEARCH).

An external research agent (a Grok Bot routine, an xAI API agent, or the
labelled development fixture) receives garment context and submits products.
ClipCart validates every submission against ``ResearchSubmission`` and stores
only ``ResearchProduct`` records it has checked. Agent claims are never shown
as ClipCart-verified facts: an agent "exact" match becomes identity tier
"likely" at most, and prices are labelled ``agent_observed``.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field

from .base import Record
from .shopping import ConstraintCheck, JobError, Money, OutboundLink, Preferences, WarningCode

# "solescout": catalog-backed fallback (named store records). "manual": waits for a labelled manual import.
# Bridge providers ("grok_bot", "xai_api") are not implemented: see docs/grok-bot-bridge.md.
ResearchProviderName = Literal["fixture", "solescout", "manual", "grok_bot"]
ResultSource = Literal["provider", "manual_import"]
ProductSource = Literal["agent", "catalog", "manual_import"]
ResearchJobStatus = Literal["pending", "completed", "failed", "expired"]


# ---------------------------------------------------------------- job input
class ResearchGarmentContext(Record):
    garment_id: str
    garment_source: Literal["media", "gemini_youtube"]
    category: str
    description: str | None = None
    colors: list[str] = Field(default_factory=list)
    pattern: list[str] = Field(default_factory=list)
    cut: list[str] = Field(default_factory=list)
    details: list[str] = Field(default_factory=list)
    visible_text: list[str] = Field(default_factory=list)
    timestamp_ms: int | None = None
    crop_asset_id: str | None = None  # internal; a bridge would send a short-lived signed URL, never the raw ID


# ---------------------------------------------------------------- provider submission (strict input)
class SubmittedPrice(Record):
    amount_minor: int = Field(ge=0, le=10_000_000)
    currency: str = Field(pattern=r"^[A-Z]{3}$")


class SubmittedVariant(Record):
    """A size or variant as the page showed it. ``available`` False is kept, never dropped."""

    label: str = Field(min_length=1, max_length=40)
    available: bool | None = None
    price: SubmittedPrice | None = None
    price_excerpt: str | None = Field(default=None, max_length=160)


class PageEvidence(Record):
    field: Literal["title", "price", "availability", "size", "condition", "brand", "identifier", "image"]
    excerpt: str = Field(min_length=1, max_length=200)


class ProductIdentifiers(Record):
    gtin: str | None = Field(default=None, pattern=r"^\d{8,14}$")
    mpn: str | None = Field(default=None, max_length=40)
    sku: str | None = Field(default=None, max_length=40)
    style_code: str | None = Field(default=None, max_length=40)
    catalog_ref: str | None = Field(default=None, max_length=120)  # e.g. "solescout:<slug>"; set by catalog sources


class SubmittedProduct(Record):
    retailer: str = Field(min_length=1, max_length=80)
    product_url: str = Field(min_length=8, max_length=2048)
    title: str = Field(min_length=1, max_length=200)
    match_type: Literal["exact", "similar"]
    observed_price: SubmittedPrice | None = None
    price_excerpt: str | None = Field(default=None, max_length=160)  # text shown on the page next to the price
    availability: Literal["in_stock", "out_of_stock", "unknown"] = "unknown"
    sizes_available: list[str] = Field(default_factory=list, max_length=30)  # only sizes the page showed as available
    source_url: str | None = Field(default=None, max_length=2048)  # page the evidence came from, if not product_url
    observed_at: datetime
    uncertainty: str | None = Field(default=None, max_length=300)
    # v2, all optional (docs/contracts/agent-research.md "v2 fields")
    image_url: str | None = Field(default=None, max_length=2048)
    brand: str | None = Field(default=None, max_length=60)  # kept only with page/catalog evidence
    condition: Literal["new", "used", "pre_owned", "unknown"] = "unknown"
    seller_kind: Literal["retailer", "marketplace", "resale", "unknown"] = "unknown"
    variants: list[SubmittedVariant] = Field(default_factory=list, max_length=60)
    evidence: list[PageEvidence] = Field(default_factory=list, max_length=12)
    identifiers: ProductIdentifiers | None = None


class ResearchSubmission(Record):
    job_id: str
    products: list[SubmittedProduct] = Field(max_length=20)
    notes: str | None = Field(default=None, max_length=500)


# ---------------------------------------------------------------- verified output
class RejectedItem(Record):
    index: int
    reason: str
    domain: str | None = None


class ResearchVariant(Record):
    label: str
    availability: Literal["available", "unavailable", "unknown"]
    price: Money | None = None  # only with the page text that shows it


class OfferGroup(Record):
    """Offers ClipCart treats as the same product, for price comparison."""

    id: str
    equivalence: Literal["identifier_match", "approximate", "single"]
    basis: str  # e.g. "Same GTIN 00012345678905" or "Same brand and near-identical title (not confirmed)"
    offer_count: int
    lowest_confirmed_price: Money | None  # among offers whose price came with page text; same currency only
    is_lowest_confirmed: bool
    uncertain_price_count: int


class StyleHints(Record):
    """Compact, soft hints from the shopper's style profile. Never hard constraints."""

    colors_like: list[str] = Field(default_factory=list, max_length=5)
    colors_avoid: list[str] = Field(default_factory=list, max_length=5)
    brands_like: list[str] = Field(default_factory=list, max_length=5)
    brands_avoid: list[str] = Field(default_factory=list, max_length=5)
    materials_avoid: list[str] = Field(default_factory=list, max_length=5)
    tones_like: list[str] = Field(default_factory=list, max_length=5)


class ResearchProduct(Record):
    id: str
    job_id: str
    section: Literal["primary", "needs_checking", "excluded"]
    retailer: str  # as reported by the agent
    domain: str  # from the URL, which ClipCart checked
    title: str
    match_claim: Literal["exact", "similar"]  # what the agent said
    identity_tier: Literal["likely", "similar"]  # what ClipCart shows; never "verified" from an agent claim
    price: Money | None
    price_basis: Literal["agent_observed", "unknown"]
    price_excerpt: str | None
    availability: Literal["in_stock", "out_of_stock", "unknown"]
    sizes_available: list[str]
    constraint_checks: list[ConstraintCheck]
    observed_at: datetime  # when the agent (or fixture capture) saw the page
    validated_at: datetime  # when ClipCart validated the submission
    verification: Literal["url_checked_page_not_fetched"]
    uncertainty: str | None
    warnings: list[str]
    links: list[OutboundLink]
    mode: Literal["live", "fixture", "manual"]
    # v2, additive
    source: ProductSource = "agent"
    image_url: str | None = None
    brand: str | None = None
    brand_basis: Literal["page_text", "catalog_record"] | None = None
    condition: Literal["new", "used", "unknown"] = "unknown"
    seller_kind: Literal["retailer", "marketplace", "resale", "unknown"] = "unknown"
    variants: list[ResearchVariant] = Field(default_factory=list)
    evidence: list[PageEvidence] = Field(default_factory=list)
    offer_group: OfferGroup | None = None
    warning_codes: list[WarningCode] = Field(default_factory=list)


class ResearchJob(Record):
    id: str
    session_id: str
    provider: ResearchProviderName
    mode: Literal["live", "fixture", "manual"]
    status: ResearchJobStatus
    garment: ResearchGarmentContext
    preferences: Preferences
    created_at: datetime
    expires_at: datetime
    finished_at: datetime | None = None
    products: list[ResearchProduct] = Field(default_factory=list)
    rejected: list[RejectedItem] = Field(default_factory=list)
    agent_notes: str | None = None
    error: JobError | None = None
    summary: str | None = None
    style_hints: StyleHints | None = None
    result_source: ResultSource = "provider"
