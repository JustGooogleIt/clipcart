# ClipCart Chrome extension

Pause a video → click ClipCart → **Shop this frame** → crop the piece → **Open in ClipCart**.
The studio opens with the cropped frame uploaded and garment detection queued, exactly as if it had been uploaded in the app.

Manifest V3, plain JavaScript, no build step. How the image reaches ClipCart, and the provenance fields it sends (page address and title, stored as a `browser_capture`): [HANDOFF.md](HANDOFF.md).

## Install (unpacked)

1. Start ClipCart: `scripts/dev.sh` from the repo root (serves UI + API on `http://127.0.0.1:8000`).
   Fixture mode works too: `CATALOG_PROVIDER=fixture PERCEPTION_PROVIDER=fixture scripts/dev.sh`.
2. Chrome → `chrome://extensions` → turn on **Developer mode** → **Load unpacked** → pick `apps/browser-extension/`.
3. Pin ClipCart from the puzzle-piece menu so the button stays in the toolbar.

Requires Chrome 116 or newer.

## ClipCart address

The default is `http://127.0.0.1:8000`. To change it, open the popup → **Settings** (or right-click the toolbar button → Options) and enter the address, for example `http://127.0.0.1:5173` for `npm run dev` in `apps/web` (Vite proxies `/api` to the backend). Any `127.0.0.1` or `localhost` port works without a prompt; other hosts ask for permission once.

## Use

1. Pause the video on the look you want.
2. Click the ClipCart button → **Shop this frame**. The visible tab is captured at that moment and a preview tab opens.
3. Drag around the piece (Escape or **Clear crop** to redo). Skip the crop to send the whole frame.
4. **Open in ClipCart**. A ClipCart tab opens on the studio with the frame loaded.

**Cancel** (or closing the preview tab) throws the capture away. Nothing leaves the browser before step 4.

What the extension handles:

| Case | Behaviour |
| --- | --- |
| `chrome://`, extension pages, Web Store, `file://` | Button disabled with an explanation |
| Capture refused or failed | Readable error in the popup; try again |
| Protected video that captures black | Warning on the preview |
| ClipCart not running / wrong address | "Can't reach ClipCart at …" with Retry and **Change address**; nothing opens |
| No permission for a custom address | **Allow** button on the preview |
| Double clicks / repeated clicks | One upload per capture; afterwards the button only switches to the ClipCart tab |
| Two sends for one capture at once (e.g. a duplicated preview tab) | The worker claims the capture synchronously; the second gets "Already sending this frame" |
| Upload succeeded but the ClipCart tab was closed mid-handoff | Recorded as sent first, then the studio opens in a new tab; never re-uploaded |
| Upload rejected (size, rate limit, session) | ClipCart's message, with Retry |

## Files

```
manifest.json        MV3 manifest: activeTab, scripting, storage; host access to 127.0.0.1 and localhost
src/background.js    service worker: capture, capture store, handoff to ClipCart
src/handoff.js       function injected into a ClipCart tab; does the same-origin upload
src/popup.*          toolbar popup ("Shop this frame")
src/crop.*           extension-owned crop preview
src/options.*        ClipCart address
src/config.js        settings and pure helpers (unit tested)
src/ui.css           tokens shared with the approved landing design
test/                unit tests, Chromium end-to-end test, fixture video page
```

## Testing

```bash
cd apps/browser-extension
npm install            # playwright-core only, for the end-to-end test
npm test               # unit tests (node:test)
CLIPCART_URL=http://127.0.0.1:8000 CHROME_PATH=/path/to/chromium npm run test:e2e
```

The end-to-end test loads the unpacked extension into Chromium, drives it against a running ClipCart server, checks ClipCart's `/api/diagnostics` counts at every step, and writes screenshots to `test/out/`.

### What was actually tested (2026-10-18, Chromium 141 headless, Linux, fixture ClipCart server on `integration` a1741a8)

Real:
- The extension's service worker, popup, crop and settings code, loaded unpacked.
- `chrome.tabs.captureVisibleTab` on a page served from a host the extension has no permission for; the capture is checked to be that page.
- Cropping with mouse drags; Escape; the uploaded media's size equals the crop.
- The handoff against the real FastAPI server: one new session, one upload, one analysis job per capture even after a double click and a third click; the studio resumes that session and draws its (fixture) detections; the capture is owned by the same `cc_owner` cookie as a session the browser created earlier.
- Browsing the video page, opening the popup, capturing, previewing and cropping create no sessions or analysis jobs.
- Server unavailable (nothing listening on the configured port): error with Retry, no tab opened, no upload.
- Cancel deletes the stored capture and closes the preview; a black frame shows the protected-video warning.
- With the shipped manifest and no toolbar click, capture is refused with a readable message.

Substituted, because automation can't click Chrome's toolbar:
- Chrome grants `activeTab` when the user clicks the toolbar button. The test copy of the manifest adds `<all_urls>` instead; the shipped manifest does not.
- The capture request is the same message the popup's button sends, sent from an extension page. The real action popup is opened once with `chrome.action.openPopup()` to confirm the wiring.
- The popup screenshot is the popup document rendered in a tab, with the "this is an extension page" error hidden.
- The video is a static test page showing a real frame from `downloads/fit-checks/fc01` at 0:22, not a playing video (headless Chromium here can't play H.264).

### Re-run (2026-10-17, Chrome for Testing 155 headless, macOS, fixture ClipCart server on `integration` 60c06d7 + this PR)

12/12 end-to-end steps pass. The added step is "two simultaneous sends for one capture upload once". The upload step now also checks the provenance: `browser_capture`, the page URL and the page title, plus the studio's "Browser capture · …" label. Sending two messages at once to the original service worker produced 2 uploads and 2 sessions. The fixed worker produced 1 upload and 1 session, with the second message refused as "in progress".

Not tested yet: a real toolbar click in desktop Chrome on macOS, real YouTube / TikTok / Instagram players, DRM sites, live Perceptron, an `https` ClipCart deployment.
