"""Live Perceptron smoke check. Skipped unless explicitly enabled.

    CLIPCART_LIVE_PERCEPTRON=1 PERCEPTRON_API_KEY=... pytest services/api/tests/perception/test_perceptron_live.py -s
"""

import io
import os

import pytest
from app.media.context import RequestContext
from media_factory import encode_with_orientation, marker_image

pytestmark = pytest.mark.skipif(
    not (os.getenv("CLIPCART_LIVE_PERCEPTRON") == "1" and os.getenv("PERCEPTRON_API_KEY")),
    reason="live Perceptron check disabled (set CLIPCART_LIVE_PERCEPTRON=1 and PERCEPTRON_API_KEY)",
)


def test_live_detect_returns_request_id_and_valid_boxes(media):
    from app.providers.perceptron.adapter import PerceptronPerceptionProvider
    from app.providers.perceptron.sdk import SdkBackend

    path = os.getenv("CLIPCART_LIVE_IMAGE")
    data = open(path, "rb").read() if path else encode_with_orientation(marker_image((640, 480), (200, 100, 440, 420)), 1)
    asset = media.ingest(io.BytesIO(data), "live-owner")
    frames = media.extract_frames(asset.id, "live-owner")
    model = os.getenv("PERCEPTRON_MODEL", "perceptron-mk1.5")
    prov = PerceptronPerceptionProvider(
        media, SdkBackend(model=model, request_timeout_s=30), mode="live", model_id=model, max_attribute_calls=1
    )
    res = prov.analyze(frames, ["jacket", "top", "bag"], RequestContext.with_timeout("live-owner", "live", 60))
    print(res.model_dump_json(by_alias=True, indent=2))
    assert res.status in ("ok", "partial"), res.issues
    assert res.requests and res.requests[0].provider_request_id
    for o in res.observations:
        assert 0 <= o.box01[0] < o.box01[2] <= 1 and 0 <= o.box01[1] < o.box01[3] <= 1
