# Findings — YouTube download-cache → Perceptron spike

Date: 2026-10-17  
Branch: `feat/youtube-tab-capture`  
Server: `http://127.0.0.1:8765`

## Product decision

Switched primary path from tab-share (`getDisplayMedia`) to **temporary yt-dlp download + TTL cache + ffmpeg frames + Perceptron**, per team preference (lower UX friction; explicit download overhead bounded by cache).

## Verdict

**Download → frames → live Perceptron works** on a permitted Creative Commons clip (Big Buck Bunny), with local Chrome cookie auth for yt-dlp.

Garment-box quality on a **fashion** clip is still pending a team-owned fashion YouTube URL (BBB correctly returns 0 jacket/top/bag boxes).

## Verified

| Step | Result |
| --- | --- |
| `POST /api/analyze-youtube` | Works |
| yt-dlp bounded download (≤90s) into `cache/` | Works (after Chrome cookies) |
| Cache hit (no re-download) | Works (`cacheHit: true`, ~1.4s for 2 live frames on warm cache) |
| ffmpeg timestamped frames (≤6) | Works |
| Perceptron Mk1.5 on extracted frames | Works (`mode: live`, complete) |
| UI “Download cache & detect” | Implemented (no tab share required) |

Example warm-cache live call (`aqz-KE-bpKQ`, 2 frames): Perceptron returned 0 fashion boxes (expected for BBB). Media file: `cache/aqz-KE-bpKQ.mp4` (gitignored).

## Blockers / limitations

| Issue | Detail |
| --- | --- |
| YouTube bot check | Bare yt-dlp fails with “Sign in to confirm you’re not a bot”. Fix: `YOUTUBE_COOKIES_FROM_BROWSER=chrome` (default in `scripts/run.sh`) or `YOUTUBE_COOKIES_FILE`. |
| Fashion demo URL | Still need a team-owned fashion clip for jacket/top/bag proof. |
| ToS / ethics | This path **downloads** YouTube bytes temporarily. Label honestly in product UI; purge cache (TTL 1h). |
| Not tab-capture | Legacy `/api/detect-frame` remains but is not the primary demo. |

## Reproduce

```bash
source .venv/bin/activate
pip install -r experiments/youtube-capture/requirements.txt
# PERCEPTRON_API_KEY in .env (gitignored)
./experiments/youtube-capture/scripts/run.sh
# http://127.0.0.1:8765 → paste URL → Download cache & detect

curl -sS http://127.0.0.1:8765/api/analyze-youtube \
  -H 'Content-Type: application/json' \
  -d '{"youtubeUrl":"https://www.youtube.com/watch?v=YOUR_ID","frameCount":3,"mode":"live"}'
```

## Claude integration

See `CONTRACT.md` (`youtube_download_cache` source, cache hit, TTL, honest download labeling).
