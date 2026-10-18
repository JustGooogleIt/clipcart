"""Canonical ClipCart contracts. Pydantic is the source of truth; JSON Schema and
TypeScript in packages/contracts are generated from these models."""

from .base import Record
from .media import (
    AnalysisResult,
    CropRef,
    FrameRef,
    FrameTransform,
    Garment,
    GarmentObservation,
    MediaAsset,
    ProviderIssue,
    ProviderRequestMeta,
)
from .demo_orders import DemoCatalogItem, DemoMerchantOrder
from .research import ResearchJob, ResearchProduct, ResearchSubmission, SubmittedProduct
from .style_memory import (
    InterpretationApplied,
    InterpretationRejected,
    InterpretationRun,
    InterpretationRunResult,
    StyleEvent,
    StyleInterpretations,
    StyleMemory,
    StyleModelInfo,
    StyleNoteResult,
    StyleNoteUsage,
    StyleProfile,
    StyleProfileView,
    StyleProposal,
    StyleTag,
    Tone,
)
from .vocabulary import CategoriesResponse, CategoryInfo
from .shopping import (
    AgentEvent,
    AnalysisJob,
    ApiError,
    ConstraintCheck,
    Evidence,
    EvidenceClaim,
    JobError,
    Listing,
    Money,
    OutboundLink,
    PreferencePatch,
    Preferences,
    Recommendation,
    ReferralEvent,
    SearchBudget,
    SearchJob,
    ShoppingSession,
    SizePref,
    SizeStock,
    StoreOffer,
    WarningCode,
)

__all__ = [
    "AgentEvent", "AnalysisJob", "CategoriesResponse", "CategoryInfo", "InterpretationApplied",
    "InterpretationRejected", "InterpretationRun", "InterpretationRunResult", "StyleInterpretations", "StyleTag", "Tone",
    "WarningCode", "AnalysisResult", "ApiError", "ConstraintCheck", "CropRef", "DemoCatalogItem", "DemoMerchantOrder",
    "Evidence", "EvidenceClaim",
    "FrameRef", "FrameTransform", "Garment", "GarmentObservation", "JobError", "Listing", "MediaAsset", "Money",
    "OutboundLink", "PreferencePatch", "Preferences", "ProviderIssue", "ProviderRequestMeta", "Recommendation", "Record",
    "ReferralEvent", "StyleEvent", "StyleMemory", "StyleModelInfo", "StyleNoteResult", "StyleNoteUsage", "StyleProfile", "StyleProfileView", "StyleProposal", "ResearchJob", "ResearchProduct", "ResearchSubmission", "SubmittedProduct", "SearchBudget", "SearchJob", "ShoppingSession", "SizePref", "SizeStock", "StoreOffer",
]
