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
    "tone_like", "tone_avoid", "ring_size",  # accessories (docs/contracts/accessories.md)
    "style_like", "style_avoid",  # vintage, minimalist, streetwear… (app/style/tags.py)
]
MemorySource = Literal[
    "preferences_form", "style_panel", "style_note", "chat_refinement", "saved_items", "rejected_items", "purchases",
    "model_interpretation",  # proposed by the style model from evidence, validated in code; never changes hard constraints
]
MemoryStatus = Literal["active", "overridden", "removed"]
# Style vocabulary for style_like / style_avoid and tone_like / tone_avoid values. app/style/tags.py and
# app/style/vocab.py read these, so the generated StyleTag / Tone types and GET /api/categories always agree.
StyleTag = Literal[
    "vintage", "minimalist", "streetwear", "workwear", "preppy", "athleisure", "y2k", "outdoor", "techwear",
    "western", "bohemian", "classic", "grunge", "punk",
]
Tone = Literal["gold-tone", "silver-tone", "rose-gold-tone", "black", "two-tone"]


class StyleTagFact(Record):
    """A style tag the listing's own text states, with the words that state it."""

    tag: str
    field: Literal["title", "material"]
    excerpt: str


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
    condition: str | None = None
    style_facts: list[StyleTagFact] = Field(default_factory=list)


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


class MemoryEvidence(Record):
    event_id: str
    type: str
    at: datetime
    excerpt: str | None = None


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
    confidence: float | None = None  # 1.0 stated; inferred from weighted evidence; model capped at 0.7
    last_evidence_at: datetime | None = None
    evidence: list[MemoryEvidence] = Field(default_factory=list, max_length=5)


class ProfileEntry(Record):
    value: Any
    origin: Origin
    memory_id: str
    evidence_count: int | None = None
    confidence: float | None = None
    source: str | None = None


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
    tones_like: list[ProfileEntry] = Field(default_factory=list, max_length=5)
    tones_avoid: list[ProfileEntry] = Field(default_factory=list, max_length=5)
    ring_size: ProfileEntry | None = None
    styles_like: list[ProfileEntry] = Field(default_factory=list, max_length=5)
    styles_avoid: list[ProfileEntry] = Field(default_factory=list, max_length=5)
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
    tones_like: list[ProfileEntry] = Field(default_factory=list, max_length=5)
    tones_avoid: list[ProfileEntry] = Field(default_factory=list, max_length=5)
    ring_size: ProfileEntry | None = None
    styles_like: list[ProfileEntry] = Field(default_factory=list, max_length=5)
    styles_avoid: list[ProfileEntry] = Field(default_factory=list, max_length=5)
    recently_owned: list[OwnedItem] = Field(default_factory=list, max_length=5)
    rejected_offer_count: int = 0
    updated_at: datetime | None = None


# ---------------------------------------------------------------- model interpretations (GET /api/style/interpretations)
class InterpretationApplied(Record):
    """A soft style memory the model proposed and validation accepted."""

    kind: MemoryKind
    value: str
    confidence: float
    evidence_event_ids: list[str]


class InterpretationRejected(Record):
    """A model proposal validation refused, with the reason. ``kind``/``value`` are what the model sent (truncated)."""

    kind: str | None = None
    value: str | None = None
    reason: str


class InterpretationRun(Record):
    id: str
    at: datetime
    model: str | None = None
    evidence_event_ids: list[str]
    status: Literal["running", "done"]
    applied: list[InterpretationApplied] = Field(default_factory=list)
    rejected: list[InterpretationRejected] = Field(default_factory=list)
    usage: StyleNoteUsage | None = None


class StyleInterpretations(Record):
    """What GET /api/style/interpretations returns.

    rankingInfluence: whether model-proposed memories may change result order (STYLE_MODEL_RANKING).
    styleModel: the configured reader; only ``mode: "live"`` means a model actually answered since startup.
    """

    status: Literal["idle", "debouncing", "waiting_for_model"]
    pending_events: int
    not_before: datetime | None = None
    runs: list[InterpretationRun] = Field(default_factory=list)
    ranking_influence: bool
    style_model: StyleModelInfo


class InterpretationRunResult(Record):
    """What POST /api/style/interpretations/run returns."""

    status: Literal["idle", "debouncing", "waiting_for_model", "already_running", "duplicate", "model_unavailable", "done"]
    pending_events: int | None = None
    run_id: str | None = None
    applied: list[InterpretationApplied] = Field(default_factory=list)
    rejected: list[InterpretationRejected] = Field(default_factory=list)
