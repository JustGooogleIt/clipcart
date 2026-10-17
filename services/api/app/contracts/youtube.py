"""Public YouTube URL analysis via Gemini (feature flag FEATURE_YOUTUBE_GEMINI).

These records are deliberately separate from the Perceptron media records:
they carry no boxes, crops, frames or pixel provenance. Every garment here is
a model-written description of a public video with approximate timestamps,
labelled ``source = "gemini_youtube"``. UI must never draw these as boxes or
show them as crops.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field, model_validator

from .base import Record

YouTubeAnalysisStatus = Literal[
    "queued",
    "running",
    "completed",  # at least one garment found
    "no_garments",  # Gemini read the video and found no jackets, tops or bags
    "not_found",  # YouTube says the video does not exist or was removed
    "private_or_restricted",  # not readable: private, unlisted, age/region restricted
    "provider_error",  # Gemini failed (auth, quota, timeout, malformed output)
]
GarmentCategory = Literal["jacket", "top", "bag", "other"]


class YouTubeInterval(Record):
    start_s: int = Field(ge=0, le=86_400)
    end_s: int = Field(gt=0, le=86_400)

    @model_validator(mode="after")
    def _ordered(self) -> YouTubeInterval:
        if self.end_s <= self.start_s:
            raise ValueError("end_s must be after start_s")
        if self.end_s - self.start_s > 600:
            raise ValueError("interval may be at most 600 seconds")
        return self


class YouTubeTimestamp(Record):
    seconds: int = Field(ge=0)
    label: str  # "MM:SS" or "H:MM:SS", as written for display


class YouTubeGarment(Record):
    id: str
    source: Literal["gemini_youtube"] = "gemini_youtube"
    category: GarmentCategory
    description: str = Field(max_length=240)
    colors: list[str] = Field(default_factory=list, max_length=4)
    pattern: list[str] = Field(default_factory=list, max_length=3)
    visible_text: list[str] = Field(default_factory=list, max_length=4)  # text Gemini says it read on the garment
    person_label: str | None = None  # local label like "person_1"; never an identity
    timestamps: list[YouTubeTimestamp] = Field(min_length=1, max_length=5)  # approximate, model-reported


class YouTubeAnalysis(Record):
    id: str
    session_id: str
    source: Literal["gemini_youtube"] = "gemini_youtube"
    status: YouTubeAnalysisStatus
    video_id: str
    canonical_url: str
    title: str | None = None  # from YouTube oEmbed metadata, when available
    channel: str | None = None
    interval: YouTubeInterval
    model: str
    provider_request_id: str | None = None
    garments: list[YouTubeGarment] = Field(default_factory=list, max_length=8)
    dropped_items: int = 0  # model items rejected by validation (bad category, timestamps outside the interval)
    message: str | None = None  # shopper-facing explanation for non-completed states
    error_code: str | None = None
    cached: bool = False  # result reused from an identical recent analysis (no new Gemini call)
    created_at: datetime
    finished_at: datetime | None = None
