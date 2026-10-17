"""Canonical media/perception records (integration owner: Claude).

Promoted unchanged from the T02 provisional ``app/media/types.py`` (PR #2),
including its proposed provenance fields. ``app/media/types.py`` re-exports
these so the media module keeps its imports. Wire format is camelCase.
"""

from __future__ import annotations

import math
from datetime import datetime
from typing import Literal

from pydantic import Field, field_validator

from .base import Record as _Record

Category = Literal["jacket", "top", "bag", "other"]
GroupingBasis = Literal["single", "within_shot", "user_confirmed"]
SourceType = Literal["upload_image", "upload_video", "youtube_download"]
MediaKind = Literal["image", "video"]
ProviderErrorCode = Literal[
    "auth_error",
    "rate_limited",
    "unavailable",
    "timeout",
    "invalid_response",
    "unsupported_capability",
    "cancelled",
]


Box01 = tuple[float, float, float, float]


class FrameTransform(_Record):
    """How a stored frame's pixels relate to the original coded media pixels.

    Pipeline: coded pixels -> orientation (EXIF orientation 1..8 or video
    display rotation) -> oriented pixels -> uniform resize -> stored frame.
    The resize is uniform with no padding or cropping, so a normalized box in
    the stored frame is the same normalized box in the oriented source.
    """

    source_width: int = Field(gt=0)  # coded (pre-orientation) width
    source_height: int = Field(gt=0)
    exif_orientation: int = Field(ge=1, le=8)  # 1 = identity; video rotation is mapped onto 1/6/3/8
    rotation_degrees: int  # clockwise display rotation applied (0/90/180/270)
    oriented_width: int = Field(gt=0)
    oriented_height: int = Field(gt=0)
    output_width: int = Field(gt=0)
    output_height: int = Field(gt=0)
    scale: float = Field(gt=0)  # output / oriented, identical on both axes up to rounding


class MediaAsset(_Record):
    id: str
    owner_id: str
    sha256: str
    mime: Literal["image/jpeg", "image/png", "video/mp4", "video/quicktime"]
    kind: MediaKind
    width: int  # display (oriented) width
    height: int
    duration_ms: int | None
    source_type: SourceType
    canonical_source_url: str | None = None
    storage_key: str
    byte_size: int
    rotation_degrees: int = 0
    exif_orientation: int = 1
    created_at: datetime


class FrameRef(_Record):
    asset_id: str
    media_id: str
    index: int = Field(ge=0)
    timestamp_ms: int | None  # null for still images; decode timestamp relative to stream start
    pts_seconds: float | None  # raw presentation timestamp reported by the decoder
    width: int
    height: int
    transform: FrameTransform
    sharpness: float  # variance of Laplacian on a grey copy (<=512px); higher = sharper


class CropRef(_Record):
    crop_asset_id: str
    frame_asset_id: str
    box01: Box01
    pixel_box: tuple[int, int, int, int]  # [x0, y0, x1, y1) in frame pixels
    frame_width: int
    frame_height: int
    width: int
    height: int
    sharpness: float


class GarmentObservation(_Record):
    """Mirrors SRS ``GarmentObservation`` plus explicit provenance fields."""

    id: str
    media_id: str
    frame_asset_id: str
    timestamp_ms: int | None
    box01: Box01
    crop_asset_id: str
    category: Category
    person_track_id: str | None
    observed_attributes: dict[str, list[str]]
    visible_text: list[str]
    provider_request_id: str | None
    model_id: str
    edited_by_user: bool
    # Fields below are extensions proposed for the canonical contract.
    raw_label: str | None = None  # provider's own mention text, kept for diagnostics
    model_generated_fields: list[str] = Field(default_factory=list)
    user_corrected_fields: list[str] = Field(default_factory=list)

    @field_validator("box01")
    @classmethod
    def _valid_box(cls, v: Box01) -> Box01:
        from app.media.geometry import validate_box01

        return validate_box01(v)


class Garment(_Record):
    id: str
    session_id: str
    observation_ids: list[str] = Field(min_length=1)
    representative_crop_id: str
    label: str
    grouping_basis: GroupingBasis
    # Integration addition: optional words the shopper typed about the garment.
    user_description: str | None = Field(default=None, max_length=200)


class ProviderRequestMeta(_Record):
    provider: str
    model_id: str | None
    frame_asset_id: str | None
    crop_asset_id: str | None
    purpose: Literal["detect", "attributes"]
    provider_request_id: str | None
    started_at: datetime
    elapsed_ms: int
    outcome: Literal["ok", "empty", "error"]
    error_code: ProviderErrorCode | None = None
    usage: dict | None = None
    attempt: int = 1


class ProviderIssue(_Record):
    code: ProviderErrorCode
    message: str
    retryable: bool
    frame_asset_id: str | None = None
    provider_request_id: str | None = None


class AnalysisResult(_Record):
    """Return value of ``PerceptionProvider.analyze``.

    ``status`` separates a valid empty result from adapter failure:
    ok (every frame analyzed), partial (some frames failed or the deadline hit),
    failed (no frame analyzed successfully).
    """

    status: Literal["ok", "partial", "failed"]
    mode: Literal["live", "fixture"]
    observations: list[GarmentObservation]
    requests: list[ProviderRequestMeta]
    issues: list[ProviderIssue]
    dropped_detections: int = 0  # provider boxes rejected by geometry validation


def finite(value: float) -> bool:
    return isinstance(value, (int, float)) and math.isfinite(value)
