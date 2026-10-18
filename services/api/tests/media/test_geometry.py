import math

import pytest
from app.media.errors import InvalidBoxError
from app.media.geometry import (
    box01_to_pixels,
    coded_box_to_display,
    display_box_to_coded,
    fit_within,
    iou,
    oriented_size,
    perceptron_box_to_box01,
    pixels_to_box01,
    rotation_to_orientation,
    validate_box01,
)
from media_factory import _DISPLAY_TO_CODED_OP, RED, find_color_box, marker_image
from PIL import ImageOps


@pytest.mark.parametrize(
    "box",
    [
        (0.5, 0.1, 0.4, 0.9),  # xmin > xmax
        (0.1, 0.9, 0.4, 0.2),  # ymin > ymax
        (0.2, 0.2, 0.2, 0.5),  # zero width
        (0.2, 0.3, 0.6, 0.3),  # zero height
        (-0.01, 0.1, 0.5, 0.5),  # below range
        (0.1, 0.1, 1.0001, 0.5),  # above range
        (0.1, 0.1, math.nan, 0.5),
        (0.1, 0.1, math.inf, 0.5),
        (0.1, 0.1, 0.5),  # wrong length
        (0.1, 0.1, 0.5, 0.5, 0.6),
        ("0.1", 0.1, 0.5, 0.5),
        (True, 0.1, 0.5, 0.5),
    ],
)
def test_invalid_boxes_rejected(box):
    with pytest.raises(InvalidBoxError):
        validate_box01(box)


def test_valid_box_passes_and_full_frame_allowed():
    assert validate_box01([0, 0, 1, 1]) == (0.0, 0.0, 1.0, 1.0)


def test_pixel_rect_covers_box_and_roundtrips():
    rect = box01_to_pixels((0.25, 0.5, 0.75, 1.0), 400, 300)
    assert rect == (100, 150, 300, 300)
    assert pixels_to_box01(rect, 400, 300) == (0.25, 0.5, 0.75, 1.0)
    # Fractional edges expand outward rather than shaving garment pixels.
    assert box01_to_pixels((0.101, 0.101, 0.499, 0.499), 100, 100) == (10, 10, 50, 50)


def test_tiny_box_rejected_by_min_side():
    with pytest.raises(InvalidBoxError):
        box01_to_pixels((0.5, 0.5, 0.505, 0.6), 1000, 1000, min_side=16)


def test_perceptron_grid_conversion_orders_corners_and_rejects_out_of_grid():
    assert perceptron_box_to_box01(600, 800, 200, 100) == (0.2, 0.1, 0.6, 0.8)
    assert perceptron_box_to_box01(0, 0, 1000, 1000) == (0.0, 0.0, 1.0, 1.0)
    for bad in [(0, 0, 1001, 500), (-1, 0, 500, 500), (100, 100, 100, 400), (0, 0, math.nan, 9)]:
        with pytest.raises(InvalidBoxError):
            perceptron_box_to_box01(*bad)


@pytest.mark.parametrize("orientation", range(1, 9))
def test_orientation_mapping_matches_pillow(orientation):
    """Coded marker position, after Pillow's EXIF transpose, equals our mapping."""
    display_size = (400, 300)
    display_rect = (40, 200, 140, 280)  # red block near bottom-left of the displayed image
    display = marker_image(display_size, display_rect)
    op = _DISPLAY_TO_CODED_OP[orientation]
    coded = display.transpose(op) if op else display.copy()
    coded_rect = find_color_box(coded, RED)
    cw, ch = coded.size
    coded_box = pixels_to_box01(coded_rect, cw, ch)

    exif = coded.getexif()
    exif[274] = orientation
    coded.info["exif"] = exif.tobytes()
    shown = ImageOps.exif_transpose(coded)
    assert shown.size == display_size == oriented_size(cw, ch, orientation)
    shown_box = pixels_to_box01(find_color_box(shown, RED), *shown.size)

    mapped = coded_box_to_display(coded_box, orientation)
    assert mapped == pytest.approx(shown_box, abs=1e-9)
    assert display_box_to_coded(mapped, orientation) == pytest.approx(coded_box, abs=1e-9)


def test_rotation_to_orientation():
    assert [rotation_to_orientation(d) for d in (0, 90, 180, 270, -90, 450)] == [1, 6, 3, 8, 8, 6]
    with pytest.raises(ValueError):
        rotation_to_orientation(45)


def test_fit_within_is_uniform_and_never_upscales():
    assert fit_within(1920, 1080, 1280) == (1280, 720, pytest.approx(1280 / 1920))
    assert fit_within(640, 480, 1280) == (640, 480, 1.0)
    w, h, s = fit_within(1080, 1920, 1280)
    assert (w, h) == (720, 1280)


def test_iou():
    assert iou((0, 0, 0.5, 0.5), (0, 0, 0.5, 0.5)) == pytest.approx(1.0)
    assert iou((0, 0, 0.5, 0.5), (0.5, 0.5, 1, 1)) == 0.0
