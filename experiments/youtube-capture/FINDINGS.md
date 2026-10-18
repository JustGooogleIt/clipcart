# Findings — YouTube auto-scan → Perceptron spike

Date: 2026-10-17  
Branch: `feat/youtube-tab-capture`  
Server: `http://127.0.0.1:8765` · spike `0.3.0`

## Product decision

Primary path: **temporary yt-dlp download + TTL cache → local full-clip scan → Perceptron on best stills**.

We do **not** send every decoded frame to Perceptron. A 90s clip at 30fps is ~2700 model calls. Instead ffmpeg walks the whole cached clip (dense samples + scene cuts), ranks stills for sharpness/fashion usefulness, then Mk1.5 runs on ~10 diverse frames.

## Verdict

**Works end-to-end on a fashion lookbook.**

Live proof (`https://www.youtube.com/watch?v=7-etsr5-Z8A`, Winter coats & jackets lookbook):

| Metric | Value |
| --- | --- |
| Local candidates scanned | 64 across ~90s |
| Scene cuts | 33 |
| Frames sent to Perceptron | 10 |
| Frames with garment boxes | **10 / 10** |
| Labels seen | coat/jacket, top, sweater, pants, dress/skirt, bag |
| Elapsed (cold download + scan + detect) | ~182s |

Overlay collage: `artifacts/fashion-scan-collage.jpg` (gitignored runtime artifact).

## Verified

| Step | Result |
| --- | --- |
| `POST /api/analyze-youtube` auto-scan | Works |
| yt-dlp via `player_client=android` (no cookies) | Works (avoids “page needs to be reloaded” / bot wall) |
| Cookie fallback + retryable errors | Implemented |
| Local full-clip scan + diverse top-K | Works |
| Box cleanup (tiny / IoU suppress) | Implemented |
| UI “Scan video” (no frame-count control) | Implemented |

## Blockers / limitations

| Issue | Detail |
| --- | --- |
| Download ToS / ethics | Temporary YouTube bytes via yt-dlp. Label honestly; TTL purge (1h). |
| Latency | Cold path ~2–3 min (download + ~10 model calls). Cache hit skips download. |
| Not production | Isolated under `experiments/youtube-capture/`; no main API change. |

## Reproduce

```bash
source .venv/bin/activate
pip install -r experiments/youtube-capture/requirements.txt
# PERCEPTRON_API_KEY in repo .env (gitignored)
./experiments/youtube-capture/scripts/run.sh
# http://127.0.0.1:8765 → Scan video

curl -sS http://127.0.0.1:8765/api/analyze-youtube \
  -H 'Content-Type: application/json' \
  -d '{"youtubeUrl":"https://www.youtube.com/watch?v=7-etsr5-Z8A","mode":"live"}'
```

## Claude integration

See `CONTRACT.md` (`youtube_download_cache` / auto-scan source, TTL, honest download labeling).
