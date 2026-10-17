"""Coordinate geometry for frames, crops and provider boxes.

Conventions (SRS section 9):
* Origin is the top-left of the *displayed* (orientation-corrected) image.
* Boxes are normalized ``(xmin, ymin, xmax, ymax)`` in ``[0, 1]``, ordered,
  with non-zero area.
* Provider coordinates are converted exactly once, in the provider adapter,
  using the functions here.

Orientation follows EXIF tag 274 semantics (1..8). Video display rotation is
mapped onto the equivalent orientation value so both share one code path.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

from .errors import InvalidBoxError

Box = tuple[float, float, float, float]

PERCEPTRON_GRID_MAX = 1000.0
_EPS = 1e-9

# For each orientation: map a displayed normalized point (u, v) to the coded
# (stored) normalized point (x, y). Display = what a viewer sees after the
# orientation is applied.
_DISPLAY_TO_CODED = {
    1: lambda u, v: (u, v),
    2: lambda u, v: (1 - u, v),  # mirror horizontal
    3: lambda u, v: (1 - u, 1 - v),  # rotate 180
    4: lambda u, v: (u, 1 - v),  # mirror vertical
    5: lambda u, v: (v, u),  # transpose
    6: lambda u, v: (v, 1 - u),  # rotate 90 CW for display
    7: lambda u, v: (1 - v, 1 - u),  # transverse
    8: lambda u, v: (1 - v, u),  # rotate 270 CW (90 CCW) for display
}
_CODED_TO_DISPLAY = {
    1: lambda x, y: (x, y),
    2: lambda x, y: (1 - x, y),
    3: lambda x, y: (1 - x, 1 - y),
    4: lambda x, y: (x, 1 - y),
    5: lambda x, y: (y, x),
    6: lambda x, y: (1 - y, x),
    7: lambda x, y: (1 - y, 1 - x),
    8: lambda x, y: (y, 1 - x),
}


def validate_box01(box: Sequence[float]) -> Box:
    """Return ``box`` as a tuple or raise ``InvalidBoxError``.

    No clamping happens here: a box outside ``[0, 1]`` is a caller bug or a
    provider defect and must be handled explicitly by the caller.
    """
    if isinstance(box, (str, bytes)) or len(box) != 4:
        raise InvalidBoxError("box01 must have exactly four numbers")
    vals = []
    for v in box:
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
            raise InvalidBoxError(f"box01 values must be finite numbers, got {v!r}")
        vals.append(float(v))
    xmin, ymin, xmax, ymax = vals
    if min(vals) < 0.0 or max(vals) > 1.0:
        raise InvalidBoxError(f"box01 values must be within [0, 1], got {vals}")
    if not (xmin < xmax and ymin < ymax):
        raise InvalidBoxError(f"box01 must be ordered with non-zero area, got {vals}")
    return (xmin, ymin, xmax, ymax)


def box01_to_pixels(box: Sequence[float], width: int, height: int, *, min_side: int = 1) -> tuple[int, int, int, int]:
    """Half-open pixel rectangle ``[x0, x1) x [y0, y1)`` that covers ``box``.

    Raises ``InvalidBoxError`` when the covered rectangle is smaller than
    ``min_side`` pixels on either axis.
    """
    if width <= 0 or height <= 0:
        raise InvalidBoxError("image dimensions must be positive")
    xmin, ymin, xmax, ymax = validate_box01(box)
    x0 = max(0, min(width - 1, math.floor(xmin * width + _EPS)))
    y0 = max(0, min(height - 1, math.floor(ymin * height + _EPS)))
    x1 = max(x0 + 1, min(width, math.ceil(xmax * width - _EPS)))
    y1 = max(y0 + 1, min(height, math.ceil(ymax * height - _EPS)))
    if (x1 - x0) < min_side or (y1 - y0) < min_side:
        raise InvalidBoxError(
            f"box covers {x1 - x0}x{y1 - y0}px on a {width}x{height} image; minimum side is {min_side}px"
        )
    return (x0, y0, x1, y1)


def pixels_to_box01(rect: Sequence[int], width: int, height: int) -> Box:
    x0, y0, x1, y1 = rect
    return validate_box01((x0 / width, y0 / height, x1 / width, y1 / height))


def perceptron_box_to_box01(x1: float, y1: float, x2: float, y2: float) -> Box:
    """Convert a Perceptron 0..1000-grid box (any corner order) to box01.

    The SDK documents integer coordinates on a normalized 0-1000 grid relative
    to the image it was sent. Values outside the grid are rejected rather than
    silently clamped.
    """
    coords = (x1, y1, x2, y2)
    for c in coords:
        if isinstance(c, bool) or not isinstance(c, (int, float)) or not math.isfinite(c):
            raise InvalidBoxError(f"provider coordinate is not a finite number: {c!r}")
        if c < 0 or c > PERCEPTRON_GRID_MAX:
            raise InvalidBoxError(f"provider coordinate {c} outside the 0..1000 grid")
    xmin, xmax = sorted((x1, x2))
    ymin, ymax = sorted((y1, y2))
    return validate_box01(
        (
            xmin / PERCEPTRON_GRID_MAX,
            ymin / PERCEPTRON_GRID_MAX,
            xmax / PERCEPTRON_GRID_MAX,
            ymax / PERCEPTRON_GRID_MAX,
        )
    )


def _map_box(box: Sequence[float], fn) -> Box:
    xmin, ymin, xmax, ymax = validate_box01(box)
    corners = [fn(xmin, ymin), fn(xmax, ymin), fn(xmin, ymax), fn(xmax, ymax)]
    xs = [c[0] for c in corners]
    ys = [c[1] for c in corners]
    return validate_box01((min(xs), min(ys), max(xs), max(ys)))


def display_box_to_coded(box: Sequence[float], orientation: int) -> Box:
    """Map a box on the displayed image to the coded (stored) pixel grid."""
    if orientation not in _DISPLAY_TO_CODED:
        raise ValueError(f"unknown orientation {orientation}")
    return _map_box(box, _DISPLAY_TO_CODED[orientation])


def coded_box_to_display(box: Sequence[float], orientation: int) -> Box:
    if orientation not in _CODED_TO_DISPLAY:
        raise ValueError(f"unknown orientation {orientation}")
    return _map_box(box, _CODED_TO_DISPLAY[orientation])


def oriented_size(width: int, height: int, orientation: int) -> tuple[int, int]:
    return (height, width) if orientation in (5, 6, 7, 8) else (width, height)


def rotation_to_orientation(clockwise_degrees: int) -> int:
    """Map a clockwise display rotation (0/90/180/270) to an EXIF orientation."""
    deg = clockwise_degrees % 360
    mapping = {0: 1, 90: 6, 180: 3, 270: 8}
    if deg not in mapping:
        raise ValueError(f"unsupported rotation {clockwise_degrees}; only multiples of 90 are supported")
    return mapping[deg]


def fit_within(width: int, height: int, max_side: int) -> tuple[int, int, float]:
    """Uniform downscale so the long side is at most ``max_side``. Never upscales."""
    long_side = max(width, height)
    if long_side <= max_side:
        return width, height, 1.0
    scale = max_side / long_side
    return max(1, round(width * scale)), max(1, round(height * scale)), scale


def area(box: Sequence[float]) -> float:
    xmin, ymin, xmax, ymax = box
    return max(0.0, xmax - xmin) * max(0.0, ymax - ymin)


def iou(a: Sequence[float], b: Sequence[float]) -> float:
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    union = area(a) + area(b) - inter
    return inter / union if union > 0 else 0.0


def center_distance(a: Sequence[float], b: Sequence[float]) -> float:
    ax, ay = (a[0] + a[2]) / 2, (a[1] + a[3]) / 2
    bx, by = (b[0] + b[2]) / 2, (b[1] + b[3]) / 2
    return math.hypot(ax - bx, ay - by)
