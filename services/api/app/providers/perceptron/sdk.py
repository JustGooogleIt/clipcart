"""Thin wrapper over the official ``perceptron`` SDK (pinned 0.4.0).

Only this file imports the SDK. It returns provider-native coordinates (the
0..1000 grid) untouched; conversion to box01 happens once in ``adapter.py``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Protocol

ATTRIBUTE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "color": {"type": "array", "items": {"type": "string"}, "maxItems": 4},
        "pattern": {"type": "array", "items": {"type": "string"}, "maxItems": 3},
        "cut": {"type": "array", "items": {"type": "string"}, "maxItems": 4},
        "details": {"type": "array", "items": {"type": "string"}, "maxItems": 6},
        "visible_text": {"type": "array", "items": {"type": "string"}, "maxItems": 6},
    },
    "required": ["color", "pattern", "cut", "details", "visible_text"],
}

ATTRIBUTE_PROMPT = (
    "Describe only what is directly visible on this {category}. Return JSON with: "
    "color (main visible colors), pattern (e.g. solid, striped, plaid), cut (silhouette, length, "
    "collar, closure), details (pockets, hardware, trims, logos as seen), visible_text (exact text or "
    "logo lettering you can read, else empty). Do not guess brand, material or fabric composition, "
    "size, price or the wearer's identity. Use empty arrays when unsure."
)


@dataclass(frozen=True)
class RawDetection:
    label: str | None
    x1: float
    y1: float
    x2: float
    y2: float


@dataclass(frozen=True)
class DetectResponse:
    detections: list[RawDetection]
    request_id: str | None
    model: str | None
    usage: dict | None
    complete: bool
    parse_errors: int = 0
    raw_text: str | None = None


@dataclass(frozen=True)
class AttributeResponse:
    attributes: dict[str, list[str]]
    request_id: str | None
    model: str | None
    usage: dict | None
    raw_text: str | None = field(default=None, repr=False)


class PerceptronBackend(Protocol):
    def detect(self, image_bytes: bytes, classes: list[str], *, max_outputs: int) -> DetectResponse: ...

    def describe(self, crop_bytes: bytes, category: str) -> AttributeResponse: ...


class SdkBackend:
    """Calls the live Perceptron API through the SDK.

    Credentials come from ``PERCEPTRON_API_KEY`` (read by the SDK). The SDK
    keeps no retries of its own; the adapter owns retry/deadline policy.
    """

    def __init__(self, *, model: str, request_timeout_s: float):
        import perceptron  # imported lazily so tests and fixture mode do not need it

        self._p = perceptron
        self.model = model
        # The SDK only exposes timeout through global settings; set it once.
        perceptron.configure(timeout=request_timeout_s, provider="perceptron")

    def detect(self, image_bytes: bytes, classes: list[str], *, max_outputs: int) -> DetectResponse:
        p = self._p
        res = p.detect(p.image(image_bytes), classes=classes, max_outputs=max_outputs, model=self.model)
        dets = [
            RawDetection(
                label=b.mention,
                x1=b.top_left.x,
                y1=b.top_left.y,
                x2=b.bottom_right.x,
                y2=b.bottom_right.y,
            )
            for b in (res.boxes or [])
        ]
        return DetectResponse(
            detections=dets,
            request_id=res.request_id,
            model=res.model or self.model,
            usage=res.usage,
            complete=res.complete,
            parse_errors=len(res.errors or []),
            raw_text=res.text,
        )

    def describe(self, crop_bytes: bytes, category: str) -> AttributeResponse:
        p = self._p
        res = p.question(
            p.image(crop_bytes),
            ATTRIBUTE_PROMPT.format(category=category),
            expects="text",
            response_format=p.json_schema_format(ATTRIBUTE_SCHEMA, name="garment_attributes"),
            model=self.model,
        )
        try:
            data = json.loads(res.text or "")
        except json.JSONDecodeError:
            from perceptron.errors import ParseError

            raise ParseError("attribute response was not valid JSON", request_id=res.request_id) from None
        return AttributeResponse(
            attributes=data if isinstance(data, dict) else {},
            request_id=res.request_id,
            model=res.model or self.model,
            usage=res.usage,
            raw_text=res.text,
        )
