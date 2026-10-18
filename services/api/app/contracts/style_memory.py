"""Owner-scoped style memory (FEATURE_STYLE_MEMORY). Contract: docs/contracts/style-memory.md.

Events are append-only facts. Memories are derived preferences that are either
``stated`` by the shopper or ``inferred`` by deterministic rules. A model may
only propose updates; code validates them and the shopper saves them.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import Field

from .base import Record

StyleEventType = Literal[
    "explicit_preference",
    "saved_item",
    "rejected_item",
    "retailer_click",
    "user_confirmed_purchase",
    "verified_order",
]
Origin = Literal["stated", "inferred"]
MemoryKind = Literal[
    "size", "fit", "budget_max",
    "color_like", "color_avoid", "material_like", "material_avoid", "brand_like", "brand_avoid",
]
MemorySource = Literal[
    "preferences_form", "style_panel", "style_note", "chat_refinement", "saved_items", "rejected_items", "purchases",
]
MemoryStatus = Literal["active", "overridden", "removed"]


class StyleItem(Record):
    """Listing facts copied server-side from stored records; never client-supplied."""

    recommendation_id: str | None = None
    listing_id: str | None = None
    offer_key: str | None = None
    product_key: str | None = None  # provider:providerListingId, stable across search and detail snapshots
    title: str
    brand: str | None = None
    domain: str | None = None
    category: str | None = None


class StyleEvent(Record):
    id: str
    type: StyleEventType
    origin: Origin
    source: str
    occurred_at: datetime
    item: StyleItem | None = None
    memory_id: str | None = None  # for explicit_preference
    link_kind: str | None = None  # for retailer_click
    order_id: str | None = None  # for verified_order


class StyleMemory(Record):
    id: str
    kind: MemoryKind
    value: Any
    origin: Origin
    source: MemorySource
    status: MemoryStatus
    source_event_ids: list[str] = Field(default_factory=list)
    evidence_count: int = 1
    overridden_by: str | None = None
    created_at: datetime
    updated_at: datetime


class ProfileEntry(Record):
    value: Any
    origin: Origin
    memory_id: str
    evidence_count: int | None = None


class OwnedItem(Record):
    title: str
    brand: str | None
    source: Literal["user_confirmed_purchase", "verified_order"]
    at: datetime


class StyleProfile(Record):
    size: ProfileEntry | None = None
    fit: ProfileEntry | None = None
    budget_max: ProfileEntry | None = None
    colors_like: list[ProfileEntry] = Field(default_factory=list, max_length=5)
    colors_avoid: list[ProfileEntry] = Field(default_factory=list, max_length=5)
    materials_avoid: list[ProfileEntry] = Field(default_factory=list, max_length=5)
    materials_like: list[ProfileEntry] = Field(default_factory=list, max_length=5)
    brands_like: list[ProfileEntry] = Field(default_factory=list, max_length=5)
    brands_avoid: list[ProfileEntry] = Field(default_factory=list, max_length=5)
    recently_owned: list[OwnedItem] = Field(default_factory=list, max_length=5)
    rejected_product_keys: list[str] = Field(default_factory=list, max_length=200)  # internal to search; count is exposed
    updated_at: datetime | None = None


class StyleProposal(Record):
    kind: MemoryKind
    value: Any
    action: Literal["add", "set", "remove"]
    quote: str


class StyleModelInfo(Record):
    """Which reader handles style notes. Never claims local processing for a hosted model.

    mode: unavailable (feature or provider off), unverified (configured, no successful call yet),
    live (a real call succeeded since startup).
    """

    mode: Literal["unavailable", "unverified", "live"]
    provider: Literal["none", "ollama", "openai_compatible"] | None = None
    model: str | None = None
    hosting: Literal["local", "remote"] | None = None
    label: str | None = None


class StyleNoteUsage(Record):
    wall_ms: int | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None


class StyleNoteResult(Record):
    """What POST /api/style/notes returns. Proposals only; nothing is saved."""

    mode: Literal["model", "rule_based"]
    model: str | None = None
    hosting: Literal["local", "remote"] | None = None  # null when the rule parser answered
    provider: str  # display label, e.g. "Rule-based parser" or "Gemma hosted on Lambda (not local)"
    proposals: list[StyleProposal] = Field(default_factory=list)
    rejected_proposals: int = 0
    note: str | None = None
    usage: StyleNoteUsage | None = None


class StyleProfileView(Record):
    """What GET /api/style/profile returns: the profile without internal product keys."""

    size: ProfileEntry | None = None
    fit: ProfileEntry | None = None
    budget_max: ProfileEntry | None = None
    colors_like: list[ProfileEntry] = Field(default_factory=list, max_length=5)
    colors_avoid: list[ProfileEntry] = Field(default_factory=list, max_length=5)
    materials_avoid: list[ProfileEntry] = Field(default_factory=list, max_length=5)
    materials_like: list[ProfileEntry] = Field(default_factory=list, max_length=5)
    brands_like: list[ProfileEntry] = Field(default_factory=list, max_length=5)
    brands_avoid: list[ProfileEntry] = Field(default_factory=list, max_length=5)
    recently_owned: list[OwnedItem] = Field(default_factory=list, max_length=5)
    rejected_offer_count: int = 0
    updated_at: datetime | None = None
