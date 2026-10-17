# YouTube → temp cache → Perceptron (feasibility spike)

Isolated under `experiments/youtube-capture/`. Does **not** edit `apps/web` or the main ClipCart API.

## Primary path (chosen)

1. Paste a YouTube URL.
2. **yt-dlp** downloads a **bounded** clip (default ≤90s, ≤720p) into a local **TTL cache** (`cache/`, 1 hour).
3. **ffmpeg** samples ≤6 JPEG frames with accurate timestamps.
4. **Perceptron** (`PERCEPTRON_MODEL`, default `perceptron-mk1.5`) detects jackets/tops/bags.
5. UI overlays boxes on the extracted frames.

Re-analyzing the same URL within the TTL is a **cache hit** (no re-download).

> This is an explicit temporary-download path. It is **not** tab-share capture and **not** “link-only without bytes.”

Optional legacy endpoint `POST /api/detect-frame` still accepts tab-capture uploads for comparison.

## Setup

```bash
source .venv/bin/activate
pip install -r experiments/youtube-capture/requirements.txt
# system: ffmpeg / ffprobe
export PERCEPTRON_API_KEY=…   # or repo .env (gitignored)
./experiments/youtube-capture/scripts/run.sh
# http://127.0.0.1:8765
```

## Reproduce

1. Open http://127.0.0.1:8765 in Chrome.
2. Paste a **permitted** YouTube URL (fashion clip for garment proof).
3. Click **Download cache & detect**.
4. Confirm boxes on at least one frame.

CLI smoke:

```bash
curl -sS http://127.0.0.1:8765/api/analyze-youtube \
  -H 'Content-Type: application/json' \
  -d '{"youtubeUrl":"https://www.youtube.com/watch?v=aqz-KE-bpKQ","frameCount":2,"mode":"live"}'
```

## Docs

- `FINDINGS.md` — what worked / failed
- `CONTRACT.md` — Claude integration surface
