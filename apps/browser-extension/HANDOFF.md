# Browser extension ↔ ClipCart: contract and handoff

Owner: browser-extension lane (`apps/browser-extension/` and this file).
Backend, `apps/web/` and `packages/contracts/` stay with their current owners (Terminal Claude).
Checked against `integration` at `60c06d7` (after #15, #16 and #17). Change B below is implemented in this PR.

## Summary

| Step | Status |
| --- | --- |
| Popup → capture visible tab → extension crop preview | Works, no ClipCart calls |
| Hand the image to ClipCart under the user's own session | **Works with today's API, no web or backend change** |
| Studio opens with the frame loaded and analysis queued | Works (existing upload behavior) |
| Source page URL and title stored with the media | **Works.** Change B is implemented in this PR, and `SEND_PROVENANCE` is on |

## How the handoff works (no new endpoint)

The extension never calls the ClipCart API cross-origin. It opens a tab **on the ClipCart origin**
and runs the upload there, so the requests are same-origin requests from ClipCart's own page:

1. Service worker: `GET {base}/api/health` (reachability only; starts nothing). Fails → "Can't reach ClipCart" with Retry.
2. Opens a background tab at `{base}/api/health` (an inert same-origin JSON page, so the SPA's own boot can't race the upload).
3. Injects `src/handoff.js#uploadCaptureInPage` with `chrome.scripting.executeScript`. Content-script `fetch` uses the page's origin, so the browser attaches the user's existing `cc_owner` cookie (`HttpOnly; SameSite=Lax`) and the `X-ClipCart-Request: 1` header needs no CORS:
   - `POST /api/sessions` with `X-ClipCart-Request: 1` → new session `{session: {id, revision}}`. If the browser has no `cc_owner` yet, the existing `ensure_owner` sets one.
   - `POST /api/media/uploads?sessionId={id}&expectedRevision={revision}` with the JPEG as the raw body, `Content-Type: image/jpeg`, `X-ClipCart-Request: 1`. This is the existing explicit upload: it ingests the image and queues analysis exactly as an upload from the studio does.
4. Navigates that tab to `{base}/`. The app boots with `POST /api/sessions/resume`, which returns the owner's newest session: the one holding the capture.

Why a new session instead of the current one: the user's in-progress session (and any search) is left intact; the capture is the newest session, so it is what the studio resumes.

Why not `fetch` from the service worker: that relies on Chrome treating extension requests as first-party for `SameSite=Lax` cookies and on host permissions skipping the preflight that `require_mutation_header` counts on. Neither is part of ClipCart's contract, so the extension doesn't use it.

Verified in Chromium 141 against a fixture server (`test/e2e.mjs`): the capture lands as a new session owned by the same `cc_owner` as a session the browser created earlier, the studio resumes it, one analysis job is created per capture.

## Change B: provenance (backend + shared contract) — implemented

`POST /api/media/uploads` now takes optional `sourceUrl` and `sourceTitle`, and the extension sends them (`SEND_PROVENANCE = true`). The crop preview tells the user that the page address and title are saved with the frame. What landed, as originally requested:

- **URL:** `sourceUrl` must be `http(s)`, have a host, have no credentials and a valid port, and be at most 2048 characters. Anything else returns `422 invalid_request` before the body is read.
- **Title:** control characters become spaces, whitespace is collapsed, and the result is capped at 300 characters. A `sourceTitle` without a `sourceUrl` returns `422`.
- **Source type:** `sourceType` is `browser_capture` only when `sourceUrl` is sent. Plain uploads are unchanged.
- **Studio label:** the scene card reads "Browser capture · {title}", or the URL's host if there is no title.
- **Tests:** `services/api/tests/api/test_capture_provenance.py`.

The original request, kept for reference:

1. `services/api/app/contracts/media.py`
   - `SourceType = Literal["upload_image", "upload_video", "youtube_download", "browser_capture"]`
   - `MediaAsset`: add `source_title: str | None = None`
2. `services/api/app/media/service.py` `MediaService.ingest(...)`: add `source_title: str | None = None` and pass it to both `MediaAsset(...)` constructors (`canonical_source_url` already exists).
3. `services/api/app/routes/api.py` `upload(...)`: add optional query params and pass them through:

   ```python
   async def upload(request: Request, sessionId: str, expectedRevision: int,
                    sourceUrl: str | None = None, sourceTitle: str | None = None) -> dict:
       ...
       if sourceUrl is not None:
           if len(sourceUrl) > 2048 or not sourceUrl.startswith(("http://", "https://")):
               raise ApiProblem(422, "invalid_request", "sourceUrl must be an http(s) URL")
       title = " ".join(sourceTitle.split())[:300] if sourceTitle else None
       asset = await run_in_threadpool(lambda: st.media.ingest(
           spool, owner, source_url=sourceUrl,
           source_type="browser_capture" if sourceUrl else None, source_title=title))
   ```

   Request shape (unchanged otherwise):

   ```http
   POST /api/media/uploads?sessionId=ses_…&expectedRevision=1&sourceUrl=https%3A%2F%2Fwww.youtube.com%2Fwatch%3Fv%3D…&sourceTitle=Fit%20check
   Content-Type: image/jpeg
   X-ClipCart-Request: 1
   Cookie: cc_owner=…            (sent by the browser; same-origin)

   <JPEG bytes>
   ```

   Response: unchanged session view; `media.canonicalSourceUrl`, `media.sourceTitle`, `media.sourceType = "browser_capture"`.
4. `packages/contracts` (shared, TS + JSON schema): add `"browser_capture"` to the source type and optional `sourceTitle` on the media asset.
5. Optional web touch: show "From {title}" on the scene card when `sourceType === "browser_capture"`.

After B merges, the extension side is a one-line flip: `SEND_PROVENANCE = true`. `src/handoff.js` already appends `sourceUrl` and `sourceTitle` when it is on.

## Optional change C: an already-open ClipCart tab (web)

The extension opens a fresh ClipCart tab. A ClipCart tab that was already open keeps showing its older session until reloaded; nothing breaks (it still belongs to the same owner). If that becomes confusing, the smallest web change is: on `visibilitychange` to visible, call `api.latest()` and switch the view when its session id differs and the current session has no media. Not needed for the demo.

## Guarantees the extension keeps

- No model or provider calls from the extension; no provider keys. Opening the popup, capturing and cropping make no ClipCart calls except `GET /api/health`.
- The screenshot is taken before any extension UI is shown; the selection overlay exists only on the extension's own preview page. No content script runs on the video site.
- One upload per capture: the button locks while sending, the worker refuses a second send for the same capture, and once sent the button only focuses the ClipCart tab.
- Permissions: `activeTab`, `scripting`, `storage`; host access to `127.0.0.1` and `localhost` only. Other ClipCart addresses are requested at runtime from Settings.
- Captures live in `chrome.storage.session` (memory only) and are dropped on Cancel or when the preview tab closes.

## Not covered in this version

Video recording, shopping in a side panel, and choosing among several ClipCart tabs.
