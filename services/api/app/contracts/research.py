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
from .shopping import ConstraintCheck, Money, OutboundLink, Preferences

ResearchProviderName = Literal["fixture"]  # bridge providers ("grok_bot", "xai_api") are not implemented yet
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


class ResearchSubmission(Record):
    job_id: str
    products: list[SubmittedProduct] = Field(max_length=20)
    notes: str | None = Field(default=None, max_length=500)


# ---------------------------------------------------------------- verified output
class RejectedItem(Record):
    index: int
    reason: str
    domain: str | None = None


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
    mode: Literal["live", "fixture"]


class ResearchJob(Record):
    id: str
    session_id: str
    provider: ResearchProviderName
    mode: Literal["live", "fixture"]
    status: ResearchJobStatus
    garment: ResearchGarmentContext
    preferences: Preferences
    created_at: datetime
    expires_at: datetime
    finished_at: datetime | None = None
    products: list[ResearchProduct] = Field(default_factory=list)
    rejected: list[RejectedItem] = Field(default_factory=list)
    agent_notes: str | None = None
    error: dict | None = None
    summary: str | None = None
