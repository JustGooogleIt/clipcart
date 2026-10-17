# Contract: public YouTube URL analysis (Gemini)

Status: **proposed, backend implemented on `feat/youtube-gemini`**. The UI session must confirm before any `apps/web/` change.
Owner: Claude (backend integration). Flag: `FEATURE_YOUTUBE_GEMINI` (default off). Key: `GEMINI_API_KEY`.

This path is separate from uploaded media and Perceptron. Gemini reads a **public** YouTube URL itself. ClipCart never downloads video bytes and never uses the YouTube Data API. The only YouTube call ClipCart makes is the public oEmbed metadata endpoint, which returns the title and channel.

## Rendering rules (must hold in the UI)

1. Gemini garments have **no boxes, crops, frames or pixel coordinates**. Never draw them on a frame or show them as a crop. Show the description, colors and timestamps as text.
2. Label every item and result from this path as found by Gemini in a YouTube video, using `source` / `garmentSource == "gemini_youtube"`. Don't call it Perceptron and don't call it "detected" in the Perceptron sense.
3. Timestamps are approximate and model-reported. A timestamp may link to the YouTube player at that second (`canonicalUrl&t=<seconds>s`). It must not be presented as a frame we extracted.
4. Show `message` verbatim for every non-`completed` status.

## Endpoints

All routes return `404 {code: "feature_disabled"}` when the flag is off. Mutations need the `X-ClipCart-Request: 1` header and the owner cookie, as elsewhere.

### `POST /api/sessions/{sessionId}/youtube-analyses`

```json
{ "url": "https://youtu.be/jNQXAC9IVRw", "startS": 0, "endS": 19, "idempotencyKey": "uuid" }
```

`startS` and `endS` are optional. The default window is `0` to `YOUTUBE_DEFAULT_WINDOW_S` (180 s), and the maximum window is 600 s.

Immediate errors, with no Gemini call:

| HTTP | `code` | When |
| --- | --- | --- |
| 400 | `invalid_url` | Not a link, or no valid 11-character video ID |
| 422 | `unsupported_url` | Playlist, channel, `/live/`, `/clip/`, non-YouTube host |
| 422 | `invalid_interval` | End is not after start, or the window is over 600 s |
| 503 | `provider_not_configured` | `GEMINI_API_KEY` missing on the server |
| 429 | `rate_limited` | More than 10 analyses per 10 minutes per browser |

Success returns `{ "analysis": YouTubeAnalysis }` with `status: "queued"`. Poll the GET endpoint.

### `GET /api/youtube-analyses/{analysisId}` → `{ "analysis": YouTubeAnalysis }`

### `POST /api/youtube-analyses/{analysisId}/garments/{garmentId}/select`

```json
{ "expectedRevision": 7, "idempotencyKey": "uuid" }
```

This creates a search garment (`source: "gemini_youtube"`) and sets it as `session.selectedGarmentId`. It returns `{ garmentId, ...SessionView }`. Then use the existing `POST /api/sessions/{id}/searches` and `GET /api/searches/{id}` unchanged.

## `YouTubeAnalysis`

```json
{
  "id": "yta_…",
  "sessionId": "ses_…",
  "source": "gemini_youtube",
  "status": "completed",
  "videoId": "jNQXAC9IVRw",
  "canonicalUrl": "https://www.youtube.com/watch?v=jNQXAC9IVRw",
  "title": "Me at the zoo",
  "channel": "jawed",
  "interval": { "startS": 0, "endS": 19 },
  "model": "gemini-3.8-flash",
  "providerRequestId": "int_…",
  "garments": [
    {
      "id": "ytg_…",
      "source": "gemini_youtube",
      "category": "jacket",
      "description": "Dark zip-up jacket with a collar",
      "colors": ["black"],
      "pattern": [],
      "visibleText": [],
      "personLabel": "person_1",
      "timestamps": [{ "seconds": 4, "label": "00:04" }, { "seconds": 11, "label": "00:11" }]
    }
  ],
  "droppedItems": 0,
  "message": null,
  "errorCode": null,
  "cached": false,
  "createdAt": "2026-10-17T…Z",
  "finishedAt": "2026-10-17T…Z"
}
```

| `status` | Meaning | Gemini called? |
| --- | --- | --- |
| `queued`, `running` | In progress; keep polling | — |
| `completed` | One or more garments listed | yes |
| `no_garments` | Gemini read the window and found no jacket, top or bag | yes |
| `not_found` | YouTube oEmbed says the video doesn't exist or was removed | **no** |
| `private_or_restricted` | Gemini couldn't read it (private, unlisted, age- or region-restricted). If YouTube lists it publicly but Gemini can't read it, the message starts "YouTube lists this video…", which is the usual unlisted case | yes |
| `provider_error` | `errorCode` is `auth_error`, `rate_limited`, `timeout`, `unavailable`, `invalid_request` or `invalid_response` | yes |

`cached: true` means an identical video, window and model was analyzed within the last hour, so no new Gemini call was made.

## Session view additions (additive JSON; the existing UI ignores them)

```json
"youtube": {
  "latestAnalysis": YouTubeAnalysis | null,
  "selectedGarment": {
    "id": "gar_…", "source": "gemini_youtube", "category": "jacket", "label": "black jacket",
    "representativeCropId": null, "observationIds": [],
    "youtube": { "analysisId": "yta_…", "garmentId": "ytg_…", "videoId": "…", "canonicalUrl": "…",
                 "description": "…", "colors": ["black"], "pattern": [], "visibleText": [], "personLabel": "person_1",
                 "timestamps": [{ "seconds": 4, "label": "00:04" }] }
  } | null
}
```

The block appears only when the flag is on. The existing `garments` array never contains Gemini garments. If a Gemini garment is selected, `session.selectedGarmentId` points to `youtube.selectedGarment.id`, and the current UI's "Find it" button stays disabled until it learns this.

## Search result additions

- `SearchJob.garmentSource`: `"media" | "gemini_youtube"` (default `"media"`).
- `Recommendation.garmentSource`: same values.
- Gemini-sourced recommendations also carry the warning "Garment described by Gemini from a YouTube video; no crop was compared". The UI shouldn't show "Your garment" crop evidence for them.

## Generated types (pending UI agreement)

`packages/contracts` is not regenerated on this branch. After the UI session agrees, run:

```bash
services/api/.venv/bin/python scripts/gen_contracts.py && (cd apps/web && npm run gen:types)
```

This adds `YouTubeAnalysis`, `YouTubeGarment`, `YouTubeInterval` and `YouTubeTimestamp`, plus the optional `garmentSource` on `SearchJob` and `Recommendation`. No existing field changes type.
