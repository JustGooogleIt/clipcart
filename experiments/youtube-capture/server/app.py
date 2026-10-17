"""Isolated YouTube → temp cache → auto-scan frames → Perceptron spike.

Primary path: yt-dlp (TTL cache) + local full-clip scan + Perceptron on best frames.
Does NOT modify ClipCart's main API. Never logs or returns the API key.
"""

from __future__ import annotations

import io
import os
import time
import uuid
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image
from pydantic import BaseModel, Field

from cache import CacheError, download_youtube, purge_expired
from frames import scan_video_for_detect

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"
ARTIFACTS = ROOT / "artifacts"
ARTIFACTS.mkdir(parents=True, exist_ok=True)

_env_path = ROOT.parents[1] / ".env"
if _env_path.is_file():
    for line in _env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key, val = key.strip(), val.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = val

MODEL = os.getenv("PERCEPTRON_MODEL", "perceptron-mk1.5")
MAX_DETECT_FRAMES = int(os.getenv("YOUTUBE_MAX_DETECT_FRAMES", "10"))
CLASSES = [
    "coat or jacket or blazer",
    "sweater or hoodie or knit",
    "shirt or blouse or top",
    "dress or skirt",
    "pants or jeans or trousers",
    "bag or handbag or backpack",
]

app = FastAPI(title="ClipCart YouTube auto-scan spike", version="0.3.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _key_configured() -> bool:
    return bool(os.getenv("PERCEPTRON_API_KEY", "").strip())


def _luminance_stats(img: Image.Image) -> dict[str, float]:
    grey = img.convert("L").resize((64, 64))
    pixels = list(grey.getdata())
    mean = sum(pixels) / max(len(pixels), 1)
    mn, mx = min(pixels), max(pixels)
    return {"mean": round(mean, 2), "min": float(mn), "max": float(mx)}


def _is_black_frame(stats: dict[str, float]) -> bool:
    return stats["mean"] < 8.0 and stats["max"] < 20.0


def _box_area01(box01: list[float]) -> float:
    x0, y0, x1, y1 = box01
    return max(0.0, x1 - x0) * max(0.0, y1 - y0)


def _iou01(a: list[float], b: list[float]) -> float:
    ax0, ay0, ax1, ay1 = a
    bx0, by0, bx1, by1 = b
    ix0, iy0 = max(ax0, bx0), max(ay0, by0)
    ix1, iy1 = min(ax1, bx1), min(ay1, by1)
    inter = max(0.0, ix1 - ix0) * max(0.0, iy1 - iy0)
    if inter <= 0:
        return 0.0
    union = _box_area01(a) + _box_area01(b) - inter
    return inter / union if union > 0 else 0.0


def _clean_boxes(boxes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Drop tiny / near-duplicate boxes so overlays read cleanly."""
    filtered: list[dict[str, Any]] = []
    for b in boxes:
        box01 = b.get("box01") or []
        if len(box01) != 4:
            continue
        area = _box_area01(box01)
        # Ignore speckles / near-full-frame nonsense
        if area < 0.01 or area > 0.92:
            continue
        w = box01[2] - box01[0]
        h = box01[3] - box01[1]
        if w < 0.04 or h < 0.04:
            continue
        filtered.append(b)

    # Prefer larger boxes first; suppress heavy overlaps (same or any label).
    ranked = sorted(filtered, key=lambda b: _box_area01(b["box01"]), reverse=True)
    kept: list[dict[str, Any]] = []
    for b in ranked:
        if any(_iou01(b["box01"], k["box01"]) >= 0.55 for k in kept):
            continue
        kept.append(b)
    # Stable-ish reading order: top-to-bottom
    kept.sort(key=lambda b: (b["box01"][1], b["box01"][0]))
    return kept


def _perceptron_detect(image_bytes: bytes) -> dict[str, Any]:
    if not _key_configured():
        raise HTTPException(
            status_code=503,
            detail={
                "code": "perceptron_key_missing",
                "message": "PERCEPTRON_API_KEY is not set in the environment or repo .env",
            },
        )
    try:
        import perceptron as p
    except ImportError as exc:
        raise HTTPException(
            status_code=503,
            detail={"code": "perceptron_sdk_missing", "message": str(exc)},
        ) from exc

    p.configure(provider="perceptron", timeout=45.0)
    t0 = time.perf_counter()
    res = p.detect(
        p.image(image_bytes),
        classes=CLASSES,
        max_outputs=8,
        model=MODEL,
    )
    elapsed_ms = int((time.perf_counter() - t0) * 1000)
    boxes = []
    for b in res.boxes or []:
        boxes.append(
            {
                "label": b.mention,
                "box1000": {
                    "xmin": b.top_left.x,
                    "ymin": b.top_left.y,
                    "xmax": b.bottom_right.x,
                    "ymax": b.bottom_right.y,
                },
                "box01": [
                    b.top_left.x / 1000.0,
                    b.top_left.y / 1000.0,
                    b.bottom_right.x / 1000.0,
                    b.bottom_right.y / 1000.0,
                ],
            }
        )
    cleaned = _clean_boxes(boxes)
    return {
        "mode": "live",
        "model": res.model or MODEL,
        "requestId": res.request_id,
        "elapsedMs": elapsed_ms,
        "complete": res.complete,
        "text": res.text,
        "boxes": cleaned,
        "rawBoxCount": len(boxes),
        "usage": res.usage,
    }


class AnalyzeBody(BaseModel):
    youtubeUrl: str
    # Optional override; default is auto-scan (ignore manual frame counts).
    maxDetectFrames: int | None = Field(default=None, ge=1, le=12)
    mode: Literal["live", "geometry_only"] = "live"


@app.get("/api/health")
def health() -> dict[str, Any]:
    purge_expired()
    return {
        "ok": True,
        "spike": "youtube-auto-scan",
        "primaryPath": "yt-dlp cache → local full-clip scan → Perceptron on best frames",
        "perceptronConfigured": _key_configured(),
        "model": MODEL,
        "maxDetectFrames": MAX_DETECT_FRAMES,
        "note": (
            "The whole cached clip is scanned locally (scene + dense samples). "
            "Only the sharpest diverse frames are sent to Perceptron — not every frame."
        ),
    }


@app.post("/api/analyze-youtube")
def analyze_youtube(body: AnalyzeBody) -> dict[str, Any]:
    t0 = time.perf_counter()
    try:
        cached = download_youtube(body.youtubeUrl)
    except CacheError as exc:
        status = 400 if exc.code in {"invalid_url"} else 502
        if exc.code == "yt_dlp_missing":
            status = 503
        raise HTTPException(
            status_code=status, detail={"code": exc.code, "message": exc.message}
        ) from exc

    run_id = uuid.uuid4().hex[:10]
    frame_dir = ARTIFACTS / f"run_{run_id}"
    max_detect = body.maxDetectFrames or MAX_DETECT_FRAMES
    try:
        samples, scan_stats = scan_video_for_detect(
            cached.path,
            frame_dir,
            max_detect_frames=max_detect,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=500,
            detail={"code": "frame_scan_failed", "message": str(exc)[:300]},
        ) from exc

    frames_out: list[dict[str, Any]] = []
    garment_hits = 0
    for sample in samples:
        raw = sample.path.read_bytes()
        img = Image.open(io.BytesIO(raw)).convert("RGB")
        stats = _luminance_stats(img)
        black = _is_black_frame(stats)
        entry: dict[str, Any] = {
            "index": sample.index,
            "timeSec": sample.time_sec,
            "artifactPath": str(sample.path.relative_to(ROOT)),
            "imageSize": {"width": img.width, "height": img.height},
            "sharpness": sample.sharpness,
            "score": sample.score,
            "pickReason": sample.reason,
            "luminance": stats,
            "blackFrame": black,
        }
        if black:
            entry["detection"] = {
                "mode": "skipped",
                "reason": "black_frame",
                "boxes": [],
            }
        elif body.mode == "geometry_only":
            entry["detection"] = {
                "mode": "geometry_only",
                "reason": "perceptron_not_called",
                "boxes": [],
            }
        else:
            try:
                det = _perceptron_detect(raw)
            except HTTPException:
                raise
            except Exception as exc:  # noqa: BLE001
                raise HTTPException(
                    status_code=502,
                    detail={"code": "perceptron_failed", "message": str(exc)[:300]},
                ) from exc
            entry["detection"] = det
            if det.get("boxes"):
                garment_hits += 1
        frames_out.append(entry)

    return {
        "source": "youtube_download_cache_autoscans",
        "youtubeUrl": body.youtubeUrl,
        "videoId": cached.video_id,
        "title": cached.title,
        "cacheHit": cached.cached,
        "cachedMedia": cached.path.name,
        "durationS": cached.duration_s or scan_stats.get("durationS"),
        "elapsedMs": int((time.perf_counter() - t0) * 1000),
        "mode": body.mode,
        "scan": scan_stats,
        "garmentFrames": garment_hits,
        "frames": frames_out,
        "whyNotEveryFrame": (
            "Sending every decoded frame to Perceptron would explode cost and latency "
            f"(e.g. 90s × 30fps ≈ 2700 calls). We scan the whole clip locally, then run "
            f"the model on up to {max_detect} sharp, time-diverse stills."
        ),
        "warnings": [
            "Temporary YouTube download via yt-dlp (TTL cache).",
            "Full-clip scan is local; Perceptron sees selected stills only.",
        ],
    }


@app.post("/api/detect-frame")
async def detect_frame(
    file: UploadFile = File(...),
    youtubeUrl: str = Form(...),
    videoId: str = Form(...),
    playerTimeSec: float = Form(...),
    sampleIndex: int = Form(...),
    captureWidth: int = Form(...),
    captureHeight: int = Form(...),
    playerWidth: int = Form(0),
    playerHeight: int = Form(0),
    mode: Literal["live", "geometry_only"] = Form("live"),
) -> dict[str, Any]:
    """Legacy tab-capture upload path."""
    if sampleIndex < 0 or sampleIndex >= 12:
        raise HTTPException(status_code=400, detail="sampleIndex out of range")
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="empty frame")
    try:
        img = Image.open(io.BytesIO(raw)).convert("RGB")
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"invalid image: {exc}") from exc
    stats = _luminance_stats(img)
    frame_id = f"ytf_{uuid.uuid4().hex[:12]}"
    out_path = ARTIFACTS / f"{frame_id}.jpg"
    img.save(out_path, format="JPEG", quality=90)
    result: dict[str, Any] = {
        "frameId": frame_id,
        "youtubeUrl": youtubeUrl,
        "videoId": videoId,
        "playerTimeSec": playerTimeSec,
        "sampleIndex": sampleIndex,
        "imageSize": {"width": img.width, "height": img.height},
        "captureSize": {"width": captureWidth, "height": captureHeight},
        "playerSize": {"width": playerWidth, "height": playerHeight},
        "luminance": stats,
        "blackFrame": _is_black_frame(stats),
        "artifactPath": str(out_path.relative_to(ROOT)),
        "path": "legacy_tab_capture",
    }
    if result["blackFrame"]:
        result["detection"] = {"mode": "skipped", "reason": "black_frame", "boxes": []}
        return result
    if mode == "geometry_only":
        result["detection"] = {
            "mode": "geometry_only",
            "reason": "perceptron_not_called",
            "boxes": [],
        }
        return result
    result["detection"] = _perceptron_detect(raw)
    return result


@app.get("/")
def index() -> FileResponse:
    return FileResponse(WEB / "index.html")


app.mount("/static", StaticFiles(directory=WEB), name="static")
app.mount("/artifacts", StaticFiles(directory=ARTIFACTS), name="artifacts")
