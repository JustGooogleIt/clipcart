# Fit-check Shorts truth set (perception demo)

Owner: product / perception  
Updated: 2026-10-17

## Story

ClipCart’s pitch for fashion video: **paste a YouTube Short or upload a fit-check clip → we find the clothes → you shop**.

We keep a local set of **10 live YouTube Shorts** (guys, girls, street interviews). Instagram was skipped — verification was unreliable.

| Path | Role |
| --- | --- |
| Manifest | [`fixtures/fit-checks/youtube_shorts.json`](../fixtures/fit-checks/youtube_shorts.json) |
| Download | `services/api/.venv/bin/python scripts/download_fit_checks.py` → `downloads/fit-checks/` (gitignored) |
| Product | Upload MP4 **or** `POST /api/sessions/{id}/youtube-analyze` with the Short URL |

## Clips

1. Rich Paul street fit — `zf6CmntK3BY`
2. NYC street interviews — `fGZB8iLJJ7E`
3. Rate the fit 1-10 — `g5mXVuj-eEI`
4. Streetwear, Mexico City — `GArRdb6qAZ8`
5. Menswear outfit check — `BiF8fA2kMgE`
6. Polo fit check — `yJ4vevoYXHU`
7. Pullover fit, woman — `7aSXFmRYGSk`
8. OOTD, woman — `dAKca9yKo_U`
9. Casual fit check, woman — `k12-rM2V_pE`
10. Kurta and jeans, woman — `KGEXdHOOfWU`

## Live Perceptron smoke (2026-10-17)

Upload path, `perceptron-mk1.5`, 6 frames/clip, ranked sampling for ≤90s video:

| Clip | Status | Garments | Categories seen |
| --- | --- | --- | --- |
| fc01 Rich Paul | completed | 6 | jacket |
| fc02 NYC interviews | completed | 6 | jacket |
| fc03 Rate the fit | completed | 15 | jacket, top |
| fc04 Mexico City | completed | 3 | jacket, top |
| fc05 Menswear | completed | 7 | jacket, top |
| fc06 Polo | completed | 7 | top |
| fc07 Pullover | completed | 6 | top |
| fc08 OOTD | completed | 6 | bag, top |
| fc09 Casual | completed | 8 | bag, top |
| fc10 Kurta | completed | 4 | top |

**10/10 clips produced shoppable garments.** Spot-checked overlays were tight on jackets/tops.

Follow-up (same day) with **pants** category + ranked frames for ≤90s video:

| Check | Result |
| --- | --- |
| Upload `fc01` Rich Paul | jacket **+ pants** |
| Upload `fc10` Kurta Short | top **+ pants** |
| YouTube URL `shorts/7aSXFmRYGSk` | `youtube_download` → top + pants, garments present |

### Known limits (honest)

- Multi-person street interviews can fill the tray (pick the piece you want).
- Temporary YouTube download is labeled in the UI; not tab-share or link-only magic.

## Demo script

1. `./scripts/dev.sh` → http://127.0.0.1:8000  
2. Paste `https://www.youtube.com/shorts/zf6CmntK3BY` → **Scan video**, *or* upload `downloads/fit-checks/fc01_zf6CmntK3BY.mp4`.  
3. Select a jacket/top in the tray → set budget → **Find it**.  
4. Open a result via `/go/{token}` and note the SoleScout/source labeling.
