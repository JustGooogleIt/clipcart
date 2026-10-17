# Smallest ClipCart contract (for Claude)

Isolated spike path: `experiments/youtube-capture/`. Do **not** merge this into `apps/web` or `services/api` without an agreed import.

## Browser → API (proposed)

```http
POST /api/sessions/{id}/youtube-tab-samples
Content-Type: multipart/form-data
```

| Field | Type | Notes |
| --- | --- | --- |
| `file` | JPEG bytes | One visible tab-capture still (not a YouTube download) |
| `youtubeUrl` | string | Canonical watch URL |
| `videoId` | string | Parsed id |
| `playerTimeSec` | float | `YT.Player.getCurrentTime()` at grab |
| `sampleIndex` | int | 0..5 |
| `captureWidth` / `captureHeight` | int | MediaStream track / canvas size |
| `playerWidth` / `playerHeight` | int | iframe CSS pixel box |

Response (align with existing perception types):

```json
{
  "mode": "live",
  "source": "youtube_tab_capture",
  "playerTimeSec": 12.4,
  "frameAssetId": "…",
  "observations": [
    {
      "box01": [0.1, 0.2, 0.5, 0.8],
      "category": "jacket",
      "timestampMs": 12400,
      "providerRequestId": "…"
    }
  ],
  "warnings": [
    "Boxes are in capture-bitmap space; player chrome/letterbox may not match coded video."
  ]
}
```

## Frontend responsibilities (UI session)

1. YouTube IFrame Player API for playback + `getCurrentTime()`.
2. Explicit `getDisplayMedia` (prefer current tab); surface deny / ended / unsupported.
3. Sample ≤6 frames; stop all tracks afterward; never keep a MediaRecorder blob.
4. Discard black frames client-side or accept server `blackFrame: true`.
5. Draw boxes on the **captured** bitmap; do not assume iframe CSS rect == capture pixels.

## Backend responsibilities (API session)

1. Treat uploads as opaque user-approved screenshots of the tab.
2. Run existing Perceptron detect adapter (Mk1.5 / configured model).
3. Persist frame + observations with `sourceType: youtube_tab_capture` and player timestamp.
4. Feature-flag the route; do not claim “link-only analysis.”

## Explicit non-goals

- No YouTube downloader / yt-dlp.
- No assumption that YouTube Data API returns video bytes.
- No silent fixture substitution for live tab frames.
