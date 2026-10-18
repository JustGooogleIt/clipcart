import io
import threading
import time
from pathlib import Path

import pytest
from app.media.context import RequestContext
from app.media.geometry import pixels_to_box01
from app.media.grouping import GarmentGrouper
from app.providers.perceptron.adapter import (
    PerceptronPerceptionProvider,
    category_from_label,
    correct_observation,
    manual_observation,
)
from app.providers.perceptron.fixture import FixtureBackend
from app.providers.perceptron.sdk import AttributeResponse, DetectResponse, RawDetection
from media_factory import HAVE_FFMPEG, encode_with_orientation, marker_image, mean_color, moving_box_video
from PIL import Image

perceptron_errors = pytest.importorskip("perceptron.errors")
OWNER = "owner-a"
FIXTURE = Path(__file__).parent / "fixtures" / "perceptron_dev_fixture.json"


class FakeBackend:
    def __init__(self, detect=None, describe=None):
        self._detect = detect or (lambda n: DetectResponse([], f"req-{n}", "perceptron-mk1.5", None, True))
        self._describe = describe or (lambda n, cat: AttributeResponse({}, f"attr-{n}", "perceptron-mk1.5", None))
        self.detect_calls = 0
        self.describe_calls = 0
        self.lock = threading.Lock()

    def detect(self, image_bytes, classes, *, max_outputs):
        with self.lock:
            self.detect_calls += 1
            n = self.detect_calls
        return self._detect(n)

    def describe(self, crop_bytes, category):
        with self.lock:
            self.describe_calls += 1
            n = self.describe_calls
        return self._describe(n, category)

    def describe_object(self, crop_bytes, query):
        with self.lock:
            self.describe_calls += 1
            n = self.describe_calls
        return AttributeResponse(
            {
                "what": query,
                "color": ["green"],
                "pattern": [],
                "form": ["potted"],
                "details": ["broad leaves"],
                "search_description": f"tall {query} with broad leaves in ceramic pot",
                "visible_text": [],
            },
            f"obj-{n}",
            "perceptron-mk1.5",
            None,
        )


@pytest.fixture
def frame(media):
    # Red "jacket" block at display pixels (40,200)-(140,280) on an EXIF-rotated photo.
    asset = media.ingest(io.BytesIO(encode_with_orientation(marker_image((400, 300), (40, 200, 140, 280)), 6)), OWNER)
    return media.extract_frames(asset.id, OWNER)[0]


@pytest.fixture
def frames3(media):
    out = []
    for i in range(3):
        img = marker_image((400, 300), (40 + i, 200, 140, 280))
        asset = media.ingest(io.BytesIO(encode_with_orientation(img, 1)), OWNER)
        out += media.extract_frames(asset.id, OWNER)
    return out


def ctx(seconds=10.0):
    return RequestContext.with_timeout(OWNER, "req-test", seconds)


def provider(media, backend, **kw):
    kw.setdefault("retry_base_delay_s", 0.01)
    kw.setdefault("min_call_budget_s", 0.05)
    return PerceptronPerceptionProvider(media, backend, **kw)


def _red_box_detection(label="jacket or coat"):
    # (40,200)-(140,280) on 400x300 -> 0..1000 grid
    return RawDetection(label, 100, 667, 350, 933)


def test_detection_converts_grid_once_and_crops_the_garment(media, frame):
    be = FakeBackend(detect=lambda n: DetectResponse([_red_box_detection()], "trace-123", "perceptron-mk1.5", {"total_tokens": 10}, True))
    res = provider(media, be, max_attribute_calls=0).analyze([frame], ["jacket", "top", "bag"], ctx())
    assert res.status == "ok" and res.mode == "live"
    [o] = res.observations
    assert o.box01 == pytest.approx(pixels_to_box01((40, 200, 140, 280), 400, 300), abs=0.002)
    assert o.category == "jacket" and o.raw_label == "jacket or coat"
    assert o.provider_request_id == "trace-123" and o.model_id == "perceptron-mk1.5"
    assert o.timestamp_ms is None and o.frame_asset_id == frame.asset_id
    assert o.model_generated_fields == ["box01", "category"] and not o.edited_by_user
    crop = Image.open(io.BytesIO(media.store.read_bytes(o.crop_asset_id, OWNER)))
    r, g, b = mean_color(crop)
    assert r > 200 and g < 60 and b < 60
    [meta] = res.requests
    assert meta.purpose == "detect" and meta.outcome == "ok" and meta.provider_request_id == "trace-123"


def test_attributes_keep_only_visible_fields(media, frame):
    be = FakeBackend(
        detect=lambda n: DetectResponse([_red_box_detection()], "t", "m", None, True),
        describe=lambda n, c: AttributeResponse(
            {
                "color": ["red", "Red", "  red "],
                "pattern": ["solid"],
                "cut": [],
                "details": ["zip front"],
                "visible_text": ["ACME"],
                "material": ["genuine leather"],
                "brand": ["Gucci"],
                "size": ["M"],
            },
            "attr-trace",
            "m",
            None,
        ),
    )
    [o] = provider(media, be).analyze([frame], ["jacket"], ctx()).observations
    assert o.observed_attributes == {"color": ["red"], "pattern": ["solid"], "details": ["zip front"]}
    assert o.visible_text == ["ACME"]
    assert "material" not in o.observed_attributes and "brand" not in o.observed_attributes
    assert set(o.model_generated_fields) >= {"color", "pattern", "details", "visible_text"}


def test_empty_detection_is_valid_ok_not_failure(media, frame):
    res = provider(media, FakeBackend()).analyze([frame], ["jacket"], ctx())
    assert res.status == "ok" and res.observations == [] and res.issues == []
    assert res.requests[0].outcome == "empty"


def test_invalid_and_duplicate_boxes_are_dropped_not_clamped(media, frame):
    dets = [
        RawDetection("jacket", 100, 100, 100, 600),  # zero width
        RawDetection("jacket", -5, 0, 500, 500),  # off-grid
        RawDetection("jacket", 0, 0, 1200, 500),  # off-grid
        RawDetection("jacket", 500, 500, 505, 505),  # too small to crop
        _red_box_detection("jacket"),
        _red_box_detection("jacket"),  # exact repeat
        RawDetection("sunglasses", 0, 0, 500, 500),  # not a requested category
    ]
    res = provider(media, FakeBackend(detect=lambda n: DetectResponse(dets, "t", "m", None, True)), max_attribute_calls=0).analyze(
        [frame], ["jacket", "bag"], ctx()
    )
    assert len(res.observations) == 1 and res.dropped_detections == 5


def test_auth_error_fails_fast_without_retry(media, frames3):
    def boom(n):
        raise perceptron_errors.AuthError("bad key", code="unauthorized", status_code=401, request_id="tr-auth")

    be = FakeBackend(detect=boom)
    res = provider(media, be, max_concurrency=1).analyze(frames3, ["jacket"], ctx())
    assert res.status == "failed"
    assert be.detect_calls == 1
    codes = [i.code for i in res.issues]
    assert codes[0] == "auth_error" and set(codes[1:]) <= {"cancelled"}
    assert res.issues[0].provider_request_id == "tr-auth" and not res.issues[0].retryable


def test_rate_limit_retried_once_then_succeeds(media, frame):
    def flaky(n):
        if n == 1:
            raise perceptron_errors.RateLimitError("slow down", retry_after=0.01)
        return DetectResponse([_red_box_detection()], "t2", "m", None, True)

    be = FakeBackend(detect=flaky)
    res = provider(media, be, max_attribute_calls=0).analyze([frame], ["jacket"], ctx())
    assert res.status == "ok" and len(res.observations) == 1 and be.detect_calls == 2
    assert [m.attempt for m in res.requests] == [1, 2]
    assert [m.error_code for m in res.requests] == ["rate_limited", None]


def test_persistent_timeout_gives_partial_with_truthful_issue(media, frames3):
    def slow_fail(n):
        if n <= 2:
            raise perceptron_errors.TimeoutError("deadline")
        return DetectResponse([], "ok", "m", None, True)

    be = FakeBackend(detect=slow_fail)
    res = provider(media, be, max_concurrency=1, max_attribute_calls=0).analyze(frames3[:2], ["jacket"], ctx())
    assert res.status == "partial"
    assert [i.code for i in res.issues] == ["timeout"]
    assert be.detect_calls == 3  # first frame: 2 attempts; second frame: 1


@pytest.mark.parametrize(
    "exc,code",
    [
        (lambda: perceptron_errors.QuotaExceededError("out of credit"), "rate_limited"),
        (lambda: perceptron_errors.TransportError("dns"), "unavailable"),
        (lambda: perceptron_errors.ServerError("bad", code="invalid_response"), "invalid_response"),
        (lambda: perceptron_errors.ParseError("bad markup"), "invalid_response"),
        (lambda: perceptron_errors.BadRequestError("renamed", code="model_renamed"), "unsupported_capability"),
        (lambda: perceptron_errors.PermissionDeniedError("nope"), "auth_error"),
    ],
)
def test_error_normalization(media, frame, exc, code):
    def fail(n):
        raise exc()

    res = provider(media, FakeBackend(detect=fail)).analyze([frame], ["jacket"], ctx())
    assert res.status == "failed" and res.issues[0].code == code


def test_deadline_bounds_total_time(media, frames3):
    def hang(n):
        time.sleep(2.0)
        return DetectResponse([], "late", "m", None, True)

    t0 = time.monotonic()
    res = provider(media, FakeBackend(detect=hang), max_concurrency=2).analyze(frames3, ["jacket"], ctx(0.6))
    assert time.monotonic() - t0 < 1.5
    assert res.status == "failed" and {i.code for i in res.issues} == {"timeout"}


def test_duplicate_frames_are_analyzed_once(media, frame):
    be = FakeBackend()
    provider(media, be).analyze([frame, frame, frame], ["jacket"], ctx())
    assert be.detect_calls == 1


def test_cancellation(media, frame):
    c = ctx()
    c.cancel_event.set()
    be = FakeBackend()
    res = provider(media, be).analyze([frame], ["jacket"], c)
    assert be.detect_calls == 0 and res.status == "failed" and res.issues[0].code == "cancelled"


def test_other_owner_cannot_analyze_frames(media, frame):
    from app.media.errors import AssetNotFoundError

    be = FakeBackend()
    with pytest.raises(AssetNotFoundError):
        provider(media, be).analyze([frame], ["jacket"], RequestContext.with_timeout("owner-b", "r", 5))
    assert be.detect_calls == 0  # no paid call before the ownership check


def test_manual_crop_fallback_and_user_correction(media, frame):
    box = pixels_to_box01((40, 200, 140, 280), 400, 300)
    m = manual_observation(media, frame, box, "jacket", OWNER)
    assert m.edited_by_user and m.provider_request_id is None and m.model_id == "manual"
    assert m.user_corrected_fields == ["box01", "category"] and m.model_generated_fields == []

    be = FakeBackend(detect=lambda n: DetectResponse([_red_box_detection("shirt")], "t", "m", None, True))
    [o] = provider(media, be, max_attribute_calls=0).analyze([frame], ["jacket", "top"], ctx()).observations
    assert o.category == "top"
    fixed = correct_observation(media, o, OWNER, category="jacket", box01=(0.05, 0.6, 0.4, 0.95))
    assert fixed.category == "jacket" and fixed.edited_by_user
    assert fixed.user_corrected_fields == ["box01", "category"] and fixed.model_generated_fields == []
    assert fixed.crop_asset_id != o.crop_asset_id and fixed.provider_request_id == o.provider_request_id


@pytest.mark.parametrize(
    "label,cat",
    [("jacket or coat", "jacket"), ("denim jacket", "jacket"), ("t-shirt", "top"), ("leather handbag", "bag"), ("shoe", "other"), (None, "other")],
)
def test_category_from_label(label, cat):
    assert category_from_label(label) == cat


# ------------------------------------------------------------- fixture path
@pytest.mark.skipif(not HAVE_FFMPEG, reason="ffmpeg needed")
def test_development_fixture_end_to_end(media, tmp_path):
    """Synthetic clip -> frames -> FIXTURE detections -> crops -> garments. Labelled mode=fixture."""
    asset = media.ingest(open(moving_box_video(tmp_path / "clip.mp4", seconds=3.0), "rb"), OWNER)
    frames = media.extract_frames(asset.id, OWNER, max_frames=4)
    # First decoded frame at or after each 750 ms grid point (30 fps clip).
    assert all(0 <= f.timestamp_ms - 750 * i < 34 for i, f in enumerate(frames))
    backend = FixtureBackend(FIXTURE)
    res = PerceptronPerceptionProvider(media, backend, mode="fixture", model_id="fixture").analyze(
        frames, ["jacket", "bag"], ctx()
    )
    assert res.mode == "fixture" and res.status == "ok"
    assert res.dropped_detections == 1 and len(res.observations) == 8
    # The jacket crops really contain the black block at the sampled time.
    for o in res.observations:
        if o.category == "jacket":
            r, g, b = mean_color(Image.open(io.BytesIO(media.store.read_bytes(o.crop_asset_id, OWNER))))
            assert max(r, g, b) < 90, (o.timestamp_ms, (r, g, b))
    garments = GarmentGrouper().group(res.observations, media.detect_shot_boundaries(asset.id, OWNER), session_id="s")
    assert sorted((g.label, len(g.observation_ids), g.grouping_basis) for g in garments) == [
        ("black jacket", 4, "within_shot"),
        ("blue bag", 4, "within_shot"),
    ]


def test_fixture_requires_explicit_label(tmp_path):
    p = tmp_path / "f.json"
    p.write_text('{"frames": []}')
    with pytest.raises(ValueError):
        FixtureBackend(p)
