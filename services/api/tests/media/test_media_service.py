import io

import pytest
from app.media.errors import (
    AssetNotFoundError,
    InvalidBoxError,
    MediaDecodeError,
    MediaLimitError,
    MediaTooLargeError,
    UnsupportedMediaError,
)
from app.media.geometry import coded_box_to_display, pixels_to_box01
from app.media.limits import MediaLimits
from app.media.service import MediaService, select_supporting_crops
from media_factory import (
    HAVE_FFMPEG,
    RED,
    color_segments_video,
    encode_with_orientation,
    find_color_box,
    marker_image,
    mean_color,
    rotated_marker_video,
    vfr_video,
)
from PIL import Image

needs_ffmpeg = pytest.mark.skipif(not HAVE_FFMPEG, reason="ffmpeg/ffprobe not installed")
OWNER = "owner-a"


def _is_red(rgb, tol=40):
    r, g, b = rgb
    return r > 255 - tol and g < tol and b < tol


def _ingest_bytes(media, data, owner=OWNER):
    return media.ingest(io.BytesIO(data), owner)


# ----------------------------------------------------------------- images
@pytest.mark.parametrize("orientation", [1, 3, 6, 8, 5])
def test_rotated_jpeg_crop_hits_intended_garment(media, orientation):
    """AT02: a box drawn on the displayed image crops the same pixels after EXIF rotation."""
    display = marker_image((400, 300), (40, 200, 140, 280))
    asset = _ingest_bytes(media, encode_with_orientation(display, orientation))
    assert (asset.width, asset.height) == (400, 300)
    assert asset.exif_orientation == orientation
    [frame] = media.extract_frames(asset.id, OWNER)
    assert frame.timestamp_ms is None  # stills never get an invented timestamp
    assert (frame.width, frame.height) == (400, 300)
    assert frame.transform.exif_orientation == orientation

    box = pixels_to_box01((40, 200, 140, 280), 400, 300)
    crop = media.crop(frame.asset_id, box, OWNER)
    img = Image.open(io.BytesIO(media.store.read_bytes(crop.crop_asset_id, OWNER)))
    assert _is_red(mean_color(img))
    assert crop.pixel_box == (40, 200, 140, 280)


def test_resized_png_keeps_normalized_box(media):
    display = marker_image((2000, 1000), (1500, 100, 1900, 600))
    asset = _ingest_bytes(media, encode_with_orientation(display, 1, fmt="PNG"))
    [frame] = media.extract_frames(asset.id, OWNER)
    assert (frame.width, frame.height) == (1280, 640)
    assert frame.transform.scale == pytest.approx(0.64)
    crop = media.crop(frame.asset_id, pixels_to_box01((1500, 100, 1900, 600), 2000, 1000), OWNER)
    img = Image.open(io.BytesIO(media.store.read_bytes(crop.crop_asset_id, OWNER)))
    assert crop.pixel_box == (960, 64, 1216, 384)
    assert _is_red(mean_color(img))


def test_crop_rejects_invalid_and_tiny_boxes(media):
    asset = _ingest_bytes(media, encode_with_orientation(marker_image((400, 300), (0, 0, 10, 10)), 1))
    [frame] = media.extract_frames(asset.id, OWNER)
    for bad in [(0.5, 0.5, 0.4, 0.9), (0, 0, 1.2, 1), (0.1, 0.1, 0.1, 0.5), (0.5, 0.5, 0.51, 0.51)]:
        with pytest.raises(InvalidBoxError):
            media.crop(frame.asset_id, bad, OWNER)


def test_select_supporting_crops_prefers_sharp_large_crops(media):
    img = Image.effect_noise((400, 300), 80).convert("RGB")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    asset = _ingest_bytes(media, buf.getvalue())
    [frame] = media.extract_frames(asset.id, OWNER)
    crops = [media.crop(frame.asset_id, b, OWNER) for b in [(0, 0, 0.2, 0.2), (0, 0, 0.9, 0.9), (0.5, 0.5, 0.7, 0.7), (0, 0, 0.5, 0.5)]]
    best = select_supporting_crops(crops)
    assert len(best) == 3
    assert best[0].box01 == (0, 0, 0.9, 0.9)


# ----------------------------------------------------------------- limits and failures
class _Endless:
    """A stream that never ends; ingest must stop at the byte cap."""

    def __init__(self, head: bytes):
        self.head = head
        self.read_total = 0

    def read(self, n):
        chunk = (self.head + b"\0" * n)[:n] if self.read_total == 0 else b"\0" * n
        self.read_total += len(chunk)
        return chunk


def test_oversized_image_stops_streaming_at_cap(store):
    media = MediaService(store, MediaLimits(max_image_bytes=3 * 1024 * 1024))
    src = _Endless(b"\x89PNG\r\n\x1a\n")
    with pytest.raises(MediaTooLargeError):
        media.ingest(src, OWNER)
    assert src.read_total <= 4 * 1024 * 1024
    assert not any(p.suffix == ".part" for p in store.root.iterdir())


@pytest.mark.parametrize(
    "data,err",
    [
        (b"", UnsupportedMediaError),
        (b"hello, this is a text file pretending to be video", UnsupportedMediaError),
        (b"GIF89a" + b"\0" * 100, UnsupportedMediaError),
        (b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 2000, UnsupportedMediaError),  # MP4 header, no streams
    ],
)
def test_unsupported_or_fake_media_rejected(media, data, err):
    if b"ftyp" in data and not HAVE_FFMPEG:
        pytest.skip("ffprobe needed")
    with pytest.raises(err):
        _ingest_bytes(media, data)


def test_truncated_jpeg_rejected(media):
    data = encode_with_orientation(Image.effect_noise((300, 300), 60).convert("RGB"), 1)
    with pytest.raises(MediaDecodeError):
        _ingest_bytes(media, data[: len(data) // 2])


def test_image_pixel_limit(store):
    media = MediaService(store, MediaLimits(max_image_pixels=10_000))
    with pytest.raises(MediaLimitError):
        _ingest_bytes(media, encode_with_orientation(marker_image((200, 200), (0, 0, 5, 5)), 1))


def test_ownership_enforced_and_ids_opaque(media):
    asset = _ingest_bytes(media, encode_with_orientation(marker_image((100, 100), (0, 0, 50, 50)), 1))
    with pytest.raises(AssetNotFoundError):
        media.get_media(asset.id, "owner-b")
    with pytest.raises(AssetNotFoundError):
        media.extract_frames(asset.id, "owner-b")
    with pytest.raises(AssetNotFoundError):
        media.store.read_bytes("../../etc/passwd", OWNER)
    other = _ingest_bytes(media, encode_with_orientation(marker_image((100, 100), (0, 0, 50, 50)), 1))
    assert other.sha256 == asset.sha256 and other.id != asset.id


# ----------------------------------------------------------------- video
@needs_ffmpeg
def test_video_frames_have_decode_timestamps_matching_content(media, tmp_path):
    """AT01: evenly spaced frames whose timestamps agree with what is on screen."""
    path = color_segments_video(tmp_path / "c.mp4", [("red", 2), ("green", 2), ("blue", 2)])
    asset = media.ingest(open(path, "rb"), OWNER)
    assert asset.kind == "video" and asset.duration_ms == pytest.approx(6000, abs=100)
    frames = media.extract_frames(asset.id, OWNER, max_frames=12)
    assert len(frames) == 12
    stamps = [f.timestamp_ms for f in frames]
    assert stamps == sorted(stamps) and stamps[0] == 0
    assert all(abs(t - 500 * i) <= 40 for i, t in enumerate(stamps))
    for f in frames:
        img = Image.open(io.BytesIO(media.store.read_bytes(f.asset_id, OWNER)))
        r, g, b = mean_color(img)
        expected = "red" if f.timestamp_ms < 2000 else "green" if f.timestamp_ms < 4000 else "blue"
        dominant = {"red": r, "green": g, "blue": b}
        assert max(dominant, key=dominant.get) == expected, (f.timestamp_ms, (r, g, b))


@needs_ffmpeg
def test_variable_frame_rate_uses_real_timestamps(media, tmp_path):
    """A constant-fps assumption would label blue frames as red; decode timestamps do not."""
    asset = media.ingest(open(vfr_video(tmp_path / "vfr.mp4"), "rb"), OWNER)
    frames = media.extract_frames(asset.id, OWNER, interval_ms=500, max_frames=12)
    assert len(frames) >= 7
    for f in frames:
        img = Image.open(io.BytesIO(media.store.read_bytes(f.asset_id, OWNER)))
        r, _, b = mean_color(img)
        assert (r > b) == (f.timestamp_ms < 1000), (f.timestamp_ms, r, b)
    late = [f.timestamp_ms for f in frames if f.timestamp_ms >= 1000]
    assert all(abs(t - round(t / 500) * 500) <= 100 for t in late)


@needs_ffmpeg
@pytest.mark.parametrize("ccw", [90, -90, 180])
def test_rotated_video_frames_are_display_oriented(media, tmp_path, ccw):
    asset = media.ingest(open(rotated_marker_video(tmp_path / "rot.mp4", ccw), "rb"), OWNER)
    expected_cw = (-ccw) % 360
    assert asset.rotation_degrees == expected_cw
    assert (asset.width, asset.height) == ((240, 320) if expected_cw in (90, 270) else (320, 240))
    [frame] = media.extract_frames(asset.id, OWNER, max_frames=1)
    assert (frame.width, frame.height) == (asset.width, asset.height)
    img = Image.open(io.BytesIO(media.store.read_bytes(frame.asset_id, OWNER)))
    found = pixels_to_box01(find_color_box(img, RED, tol=120), img.width, img.height)
    predicted = coded_box_to_display((0, 0, 0.25, 0.25), frame.transform.exif_orientation)
    assert found == pytest.approx(predicted, abs=0.03)
    crop = media.crop(frame.asset_id, predicted, OWNER)
    cimg = Image.open(io.BytesIO(media.store.read_bytes(crop.crop_asset_id, OWNER)))
    assert _is_red(mean_color(cimg), tol=70)


@needs_ffmpeg
def test_video_duration_limit(store, tmp_path):
    media = MediaService(store, MediaLimits(max_video_duration_ms=1500))
    path = color_segments_video(tmp_path / "long.mp4", [("red", 2)])
    with pytest.raises(MediaLimitError):
        media.ingest(open(path, "rb"), OWNER)


@needs_ffmpeg
def test_frame_caps_and_target_window(media, tmp_path):
    asset = media.ingest(open(color_segments_video(tmp_path / "c.mp4", [("red", 3), ("blue", 3)]), "rb"), OWNER)
    assert len(media.extract_frames(asset.id, OWNER, max_frames=500)) <= media.limits.max_initial_frames
    window = media.extract_frames(asset.id, OWNER, start_ms=2500, end_ms=3500, max_frames=50)
    assert 1 <= len(window) <= media.limits.max_target_frames
    assert all(2450 <= f.timestamp_ms <= 3550 for f in window)


@needs_ffmpeg
def test_shot_boundaries_detected(media, tmp_path):
    asset = media.ingest(open(color_segments_video(tmp_path / "c.mp4", [("red", 1), ("blue", 1)]), "rb"), OWNER)
    cuts = media.detect_shot_boundaries(asset.id, OWNER)
    assert len(cuts) == 1 and abs(cuts[0] - 1000) <= 50
