# Smallest ClipCart contract (download-cache + auto-scan)

Spike: `experiments/youtube-capture/`. Product path (on `feat/youtube-product` / `integration`):
`POST /api/sessions/{id}/youtube-analyze` in `services/api` + URL paste in `apps/web`.
This folder remains the reference spike; prefer the product route for demos.

## Browser → API

```http
POST /api/sessions/{id}/youtube-analyze
Content-Type: application/json

{
  "youtubeUrl": "https://www.youtube.com/watch?v=…",
  "expectedRevision": 1
}
```

`frameCount` is **not** a product control. The server scans the whole cached clip locally and budgets model calls internally (`maxDetectFrames`, default ~10).

## Backend pipeline

1. Validate YouTube URL / video id.
2. **Cache lookup** by `videoId` (TTL, e.g. 1h). On miss: yt-dlp download bounded section (≤90s) + ≤720p into private object/temp storage. Prefer mobile `player_client` (e.g. android); cookies as fallback for bot walls.
3. **Local full-clip scan**: ffmpeg dense samples + scene cuts → score sharpness / fashion usefulness → pick temporally diverse top-K stills.
4. Existing Perceptron detect adapter on each selected still (budgeted); optional IoU cleanup.
5. Return observations with `source: youtube_download_cache_autoscans`, `timeSec`, `box01`, `mode: live|geometry_only`.
6. Purge expired cache entries; never commit media.

## Response sketch

```json
{
  "videoId": "…",
  "cacheHit": true,
  "scan": { "candidateCount": 64, "selectedCount": 10, "sceneCutCount": 33 },
  "garmentFrames": 10,
  "frames": [
    {
      "timeSec": 4.2,
      "artifactPath": "artifacts/run_…/selected_00_4.20s.jpg",
      "detection": {
        "boxes": [{ "box01": [0.2, 0.1, 0.7, 0.9], "label": "coat or jacket or blazer" }]
      }
    }
  ],
  "whyNotEveryFrame": "…",
  "warnings": ["Temporary YouTube download was used; full-clip scan is local."]
}
```

## UI responsibilities

- Paste URL + progress (downloading / scanning / detecting). No manual “how many frames” control.
- Explain: whole clip scanned locally; model sees best stills only (cost/latency).
- Show honest “downloaded for analysis” labeling.
- Display result strip + boxes; optional YouTube embed for watch-along only (not the pixel source).

## Non-goals

- Do not silently pretend this is tab-capture or link-only.
- Do not keep unbounded archives of YouTube files.
- Do not send every FPS frame to Perceptron.
