"""DEVELOPMENT FIXTURE backend. Not a live Perceptron integration.

Replays recorded/synthetic detections so the rest of the app can be built
without credentials. Results produced through this backend carry
``mode="fixture"`` and must be labelled as fixtures wherever they are shown
(SRS section 5, AT25).
"""

from __future__ import annotations

import json
from pathlib import Path

from .sdk import AttributeResponse, DetectResponse, RawDetection


class FixtureBackend:
    """Replays a fixture file keyed by frame index (calls are counted in order)."""

    def __init__(self, path: str | Path):
        data = json.loads(Path(path).read_text())
        if data.get("fixture_label") is None or "NOT A LIVE" not in data["fixture_label"].upper():
            raise ValueError("fixture file must carry an explicit fixture_label")
        self.label = data["fixture_label"]
        self.model = data.get("model_id", "fixture")
        self._frames = data["frames"]
        self._attributes = data.get("attributes", {})
        self._calls = 0

    def detect(self, image_bytes: bytes, classes: list[str], *, max_outputs: int) -> DetectResponse:
        entry = self._frames[self._calls % len(self._frames)]
        self._calls += 1
        dets = [RawDetection(d["label"], *d["box_0_1000"]) for d in entry["detections"]][:max_outputs]
        return DetectResponse(
            detections=dets,
            request_id=f"fixture-{entry['frame_index']}",
            model=self.model,
            usage=None,
            complete=True,
        )

    def describe(self, crop_bytes: bytes, category: str) -> AttributeResponse:
        return AttributeResponse(
            attributes=self._attributes.get(category, {}),
            request_id="fixture-attributes",
            model=self.model,
            usage=None,
        )

    def describe_object(self, crop_bytes: bytes, query: str) -> AttributeResponse:
        attrs = self._attributes.get("object") or self._attributes.get("other") or {
            "what": query,
            "color": ["green"],
            "pattern": [],
            "form": ["potted"],
            "details": ["broad leaves", "ceramic pot"],
            "search_description": query,
            "visible_text": [],
        }
        return AttributeResponse(
            attributes=attrs,
            request_id="fixture-object-attributes",
            model=self.model,
            usage=None,
        )
