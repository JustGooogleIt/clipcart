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
from .research import ResearchJob, ResearchProduct, ResearchSubmission, SubmittedProduct
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
)

__all__ = [
    "AgentEvent", "AnalysisJob", "AnalysisResult", "ApiError", "ConstraintCheck", "CropRef", "Evidence", "EvidenceClaim",
    "FrameRef", "FrameTransform", "Garment", "GarmentObservation", "JobError", "Listing", "MediaAsset", "Money",
    "OutboundLink", "PreferencePatch", "Preferences", "ProviderIssue", "ProviderRequestMeta", "Recommendation", "Record",
    "ReferralEvent", "ResearchJob", "ResearchProduct", "ResearchSubmission", "SubmittedProduct", "SearchBudget", "SearchJob", "ShoppingSession", "SizePref", "SizeStock", "StoreOffer",
]
