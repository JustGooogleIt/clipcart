# Findings — YouTube tab capture → Perceptron spike

Date: 2026-10-17  
Branch: `feat/youtube-tab-capture`  
Environment: local spike server `http://127.0.0.1:8765`

## Verdict

**Partial proof (model path now live).** The isolated UI + API chain works, and **live Perceptron Mk1.5 detect succeeds** once `PERCEPTRON_API_KEY` is in the gitignored repo `.env`.

Still **not claimed complete**: end-to-end **visible YouTube tab pixels via `getDisplayMedia` → garment box**, because:

1. **`getDisplayMedia` tab share cannot be completed** inside the automated Cursor browser (no durable OS share picker). Needs a human in desktop Chrome.
2. Garment proof on a real fashion clip needs a **team-owned / permitted YouTube URL** (default Big Buck Bunny is wiring-only).

We do **not** claim a link-only flow. No YouTube downloader was used.

### Live Perceptron smoke (2026-10-17, after key provided)

- Endpoint: `POST /api/detect-frame` `mode=live` with synthetic jacket still + fake player timestamp `3.5s`
- Model: `perceptron-mk1.5`, `complete: true`, ~430–660 ms
- Result: **1 box** `jacket or coat` at `box01 ≈ [0.281, 0.166, 0.72, 0.877]`
- Overlay artifact: `artifacts/live-perceptron-synthetic-overlay.jpg`
- Key remains only in gitignored `.env` (never committed)

## What was verified (real)

| Step | Result |
| --- | --- |
| Spike server health | `GET /api/health` → `ok: true`, `perceptronConfigured: false`, model `perceptron-mk1.5` |
| Spike UI loads | Screenshot `artifacts/ui-spike-loaded.jpg` |
| YouTube IFrame API load | Status: `Player ready for aqz-KE-bpKQ…`; Share button enabled |
| Timestamped frame POST | `POST /api/detect-frame` with `playerTimeSec=1.25`, synthetic still → `geometry_only` success; JPEG written under `artifacts/` |
| Black-frame heuristic | Implemented (mean/max luminance); not triggered on synthetic still |
| Stream discard policy | Client stops all tracks after sampling / Stop sharing |
| Max frames | Enforced client (≤6) and server (`sampleIndex` 0..5) |

## What failed / blocked

| Step | Where it breaks |
| --- | --- |
| Tab permission / pixels | **Tab permission** — automated browser cannot finish `getDisplayMedia` |
| Model input (live) | **Unblocked** with local `.env` key — synthetic still → jacket box |
| Garment box on **tab capture** | **Still blocked** on tab permission (needs human Chrome share) |
| Fashion demo URL | Default CC Big Buck Bunny is wiring-only; garment proof needs a **team-owned** fashion clip (`fixtures/VIDEO.md`) |

## Coordinate mismatch notes (expected)

Boxes from Perceptron are in **capture-bitmap space** (the tab share crop), not YouTube’s coded frame and not necessarily the iframe CSS rectangle.

Likely mismatch sources (diagram: `artifacts/coordinate-spaces.png`):

- Player chrome / controls included in the share
- Letterboxing inside the player
- DevicePixelRatio / OS scaling (`captureWidth×captureHeight` vs CSS `playerWidth×playerHeight`)
- User shared a larger surface than “this tab”

Always overlay boxes on the captured still. Re-projecting onto the iframe requires an explicit crop mapping (not implemented in this spike).

## Reproduce

```bash
source .venv/bin/activate
pip install -r experiments/youtube-capture/requirements.txt
# REQUIRED for live Perceptron:
export PERCEPTRON_API_KEY=…   # or repo .env — never commit
./experiments/youtube-capture/scripts/run.sh
# Chrome: http://127.0.0.1:8765
# Load permitted URL → play → Share this tab → Sample & detect
```

Geometry-only API smoke (no key):

```bash
curl -sS -X POST http://127.0.0.1:8765/api/detect-frame \
  -F "file=@experiments/youtube-capture/fixtures/synthetic_jacket_still.jpg" \
  -F "youtubeUrl=https://www.youtube.com/watch?v=aqz-KE-bpKQ" \
  -F "videoId=aqz-KE-bpKQ" \
  -F "playerTimeSec=1.25" \
  -F "sampleIndex=0" \
  -F "captureWidth=640" -F "captureHeight=480" \
  -F "playerWidth=800" -F "playerHeight=450" \
  -F "mode=geometry_only"
```

## Browser limitations

- Desktop **Chrome/Chromium** required for reliable `preferCurrentTab` / tab share UX.
- Safari/Firefox support for `getDisplayMedia` options varies; unsupported browsers show an explicit message.
- Embedded Cursor/automation browsers often **cannot** complete the OS share prompt.
- YouTube may show ads/end screens in the shared pixels — those become model input.

## Next for a full proof (human + key)

1. Put `PERCEPTRON_API_KEY` in repo `.env` (gitignored).
2. Open the spike in desktop Chrome.
3. Paste a **team fashion** YouTube URL; play; share **this tab**; sample 1–3 frames.
4. Confirm a jacket/top/bag box aligns on the captured still; note any chrome/letterbox offset in a follow-up commit to this FINDINGS file.
5. Hand `CONTRACT.md` to Claude for production wiring behind a feature flag.
