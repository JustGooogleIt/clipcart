# YouTube tab capture → Perceptron (feasibility spike)

Isolated under `experiments/youtube-capture/`. Does **not** edit `apps/web` or the main ClipCart API.

## What it does

1. Paste a YouTube URL → embed via **YouTube IFrame Player API** (playback time).
2. User clicks **Share tab** → browser **`getDisplayMedia`** prompt (prefer current tab).
3. Sample ≤6 visible frames from the capture stream, each tagged with `player.getCurrentTime()`.
4. POST stills to a tiny local FastAPI app → **Perceptron** detect (`PERCEPTRON_MODEL`, default `perceptron-mk1.5`).
5. Draw returned boxes on the captured bitmap; stop/discard the MediaStream.

No YouTube downloader. No full recording retained (only optional JPEG stills under `artifacts/`).

## Setup

```bash
# from repo root
python3 -m venv .venv && source .venv/bin/activate
pip install -r experiments/youtube-capture/requirements.txt

# put PERCEPTRON_API_KEY in repo .env or export it (never commit)
export PERCEPTRON_API_KEY=…
export PERCEPTRON_MODEL=perceptron-mk1.5

chmod +x experiments/youtube-capture/scripts/run.sh
./experiments/youtube-capture/scripts/run.sh
# open http://127.0.0.1:8765 in Chrome
```

## Reproduce (Chrome desktop)

1. Open http://127.0.0.1:8765
2. Load a **permitted** YouTube URL (see `fixtures/VIDEO.md`). For garments, use a team fashion clip.
3. Play the video.
4. **Share tab** → choose this Chrome tab (not the whole screen if possible).
5. **Sample & detect** (1–6 frames). Confirm boxes overlay the garment on at least one still.
6. Sharing stops automatically after sampling; stream is discarded.

Geometry-only (no Perceptron spend): check “Geometry only”.

Still → Perceptron without tab share (labeled non-tab path):

```bash
.venv/bin/python experiments/youtube-capture/scripts/detect_still.py path/to/garment.jpg
```

## Real vs mocked

| Step | Real? |
| --- | --- |
| YouTube IFrame playback + `getCurrentTime` | Real (YouTube API) |
| Tab pixels via `getDisplayMedia` | Real (requires human Chrome prompt) |
| Perceptron Mk1.5 detect | Real when `PERCEPTRON_API_KEY` is set |
| Link-only / download bytes | **Not implemented** — do not claim |

## Docs

- `FINDINGS.md` — proof results, coordinate mismatches, blockers
- `CONTRACT.md` — smallest integration surface for Claude
