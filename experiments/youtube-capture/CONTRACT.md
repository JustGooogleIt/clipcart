# Smallest ClipCart contract (download-cache path)

Spike: `experiments/youtube-capture/`. Agree before merging into `apps/web` / `services/api`.

## Browser → API

```http
POST /api/sessions/{id}/youtube-analyze
Content-Type: application/json

{
  "youtubeUrl": "https://www.youtube.com/watch?v=…",
  "frameCount": 3,
  "expectedRevision": 1
}
```

## Backend pipeline

1. Validate YouTube URL / video id.
2. **Cache lookup** by `videoId` (TTL, e.g. 1h). On miss: yt-dlp download bounded section (≤90s) + ≤720p into private object/temp storage.
3. ffmpeg sample ≤6 frames with decode timestamps.
4. Existing Perceptron detect adapter on each frame (budgeted).
5. Return observations with `source: youtube_download_cache`, `timestampMs`, `box01`, `mode: live|cached`.
6. Purge expired cache entries; never commit media.

## Response sketch

```json
{
  "videoId": "…",
  "cacheHit": true,
  "frames": [
    {
      "timestampMs": 4200,
      "frameAssetId": "…",
      "observations": [{ "box01": [0.2, 0.1, 0.7, 0.9], "category": "jacket", "providerRequestId": "…" }]
    }
  ],
  "warnings": ["Temporary YouTube download was used; not a tab-share flow."]
}
```

## UI responsibilities

- Paste URL + progress (downloading / cache hit / detecting).
- Show honest “downloaded for analysis” labeling.
- Display frame strip + boxes; optional YouTube embed for human watch-along only (not the pixel source).

## Non-goals

- Do not silently pretend this is tab-capture or link-only.
- Do not keep unbounded archives of YouTube files.
