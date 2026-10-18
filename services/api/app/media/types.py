"""Compatibility re-export. Canonical definitions live in ``app.contracts.media``."""

from app.contracts.media import *  # noqa: F401,F403
from app.contracts.media import (  # noqa: F401
    AnalysisResult,
    Box01,
    Category,
    CropRef,
    FrameRef,
    FrameTransform,
    Garment,
    GarmentObservation,
    GroupingBasis,
    MediaAsset,
    ProviderErrorCode,
    ProviderIssue,
    ProviderRequestMeta,
    finite,
)
