"""Isolated YouTube tab-capture → Perceptron detect spike.

Does NOT modify ClipCart's main API. Run only from experiments/youtube-capture.
Never logs or returns the API key.
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

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"
ARTIFACTS = ROOT / "artifacts"
ARTIFACTS.mkdir(parents=True, exist_ok=True)

# Load optional local .env without requiring python-dotenv.
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
MAX_FRAMES_PER_SESSION = 6
CLASSES = ["jacket or coat", "top or shirt or sweater", "bag or handbag or backpack"]

app = FastAPI(title="ClipCart YouTube tab-capture spike", version="0.1.0")
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


def _perceptron_detect(image_bytes: bytes) -> dict[str, Any]:
    """Live Perceptron detect. Raises HTTPException on failure."""
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

    # Do not pass or print the key; SDK reads PERCEPTRON_API_KEY.
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
        # Provider grid is 0..1000 → normalize to box01 for overlays.
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
    return {
        "mode": "live",
        "model": res.model or MODEL,
        "requestId": res.request_id,
        "elapsedMs": elapsed_ms,
        "complete": res.complete,
        "text": res.text,
        "boxes": boxes,
        # Never include usage secrets; usage counts are fine.
        "usage": res.usage,
    }


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {
        "ok": True,
        "spike": "youtube-tab-capture",
        "perceptronConfigured": _key_configured(),
        "model": MODEL,
        "maxFrames": MAX_FRAMES_PER_SESSION,
        "note": "Isolated experiment; not the ClipCart production API.",
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
    if sampleIndex < 0 or sampleIndex >= MAX_FRAMES_PER_SESSION:
        raise HTTPException(status_code=400, detail="sampleIndex out of range (max 6)")

    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="empty frame")
    if len(raw) > 8_000_000:
        raise HTTPException(status_code=413, detail="frame too large")

    try:
        img = Image.open(io.BytesIO(raw)).convert("RGB")
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"invalid image: {exc}") from exc

    stats = _luminance_stats(img)
    black = _is_black_frame(stats)
    frame_id = f"ytf_{uuid.uuid4().hex[:12]}"
    # Persist only the sampled still for local review (not a recording).
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
        "blackFrame": black,
        "artifactPath": str(out_path.relative_to(ROOT)),
        "coordinateNotes": [
            "Boxes are relative to the uploaded capture bitmap (tab share crop), not the YouTube coded frame.",
            "Player chrome, letterboxing, and OS scale can shift garment pixels vs the embedded player rectangle.",
            "Compare playerSize vs captureSize / imageSize when overlaying on the iframe.",
        ],
    }

    if black:
        result["detection"] = {
            "mode": "skipped",
            "reason": "black_frame",
            "boxes": [],
        }
        return result

    if mode == "geometry_only":
        result["detection"] = {
            "mode": "geometry_only",
            "reason": "perceptron_not_called",
            "boxes": [],
        }
        return result

    try:
        result["detection"] = _perceptron_detect(raw)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        # Do not leak env; message only.
        raise HTTPException(
            status_code=502,
            detail={"code": "perceptron_failed", "message": str(exc)[:300]},
        ) from exc

    return result


@app.get("/")
def index() -> FileResponse:
    return FileResponse(WEB / "index.html")


app.mount("/static", StaticFiles(directory=WEB), name="static")
