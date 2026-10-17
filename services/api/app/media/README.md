# Media and perception module (T02)

Owner: Codex lane (feat/perception). Integration owner: Claude.

## Handoff

```text
Task and owner:        T02 media/frame extraction, crop geometry, grouping, Perceptron adapter
Base commit and branch: ce146ce (main, README only) -> feat/perception
Allowed paths:         services/api/app/media/, services/api/app/providers/perceptron/,
                       services/api/tests/media/, services/api/tests/perception/
Forbidden/shared paths: app/contracts, routes, frontend, catalog, Grok workers, root deps, env templates
Input/output contract: SRS section 12 logical interfaces (no committed Claude contract existed yet)
Acceptance checks:     AT01, AT02, AT03 (live, needs key), AT04
Known blocker:         no PERCEPTRON_API_KEY available to this lane; no integration branch existed
Next integration step: Claude swaps app/media/types.py for app/contracts imports and wires routes
```

## Contract status

`types.py` is **provisional**. The repository had no `app/contracts` when this
was written, so the records mirror the SRS logical schema with camelCase JSON
aliases. When Claude's contracts land, import them here and delete the copies.
Proposed additions for the canonical `GarmentObservation`:

- `rawLabel`: provider mention text, diagnostics only.
- `modelGeneratedFields` and `userCorrectedFields`: FR05 provenance.

New records this module needs in the contract: `MediaAsset`, `FrameRef`,
`FrameTransform`, `CropRef`, `ProviderRequestMeta`, `ProviderIssue`,
`AnalysisResult`.

## Interfaces

```text
MediaService.ingest(upload, owner_id) -> MediaAsset
MediaService.extract_frames(media_id, owner_id, interval_ms=None, max_frames=None,
                            start_ms=None, end_ms=None) -> list[FrameRef]
MediaService.detect_shot_boundaries(media_id, owner_id) -> list[int]   # cut times, ms
MediaService.crop(frame_asset_id, box01, owner_id) -> CropRef
PerceptronPerceptionProvider.analyze(frame_refs, categories, RequestContext) -> AnalysisResult
GarmentGrouper().group(observations, shot_boundaries_ms, session_id=...) -> list[Garment]
manual_observation(...) / correct_observation(...)   # manual crop fallback, FR05 edits
```

`owner_id` is an explicit argument on every read, which the SRS signatures
leave implicit. `RequestContext` carries owner, request ID, deadline and a
cancel event.

## Geometry rules

- Boxes are `[xmin, ymin, xmax, ymax]` in `[0, 1]` on the displayed image,
  origin top-left, ordered, non-zero area. Invalid boxes raise; nothing clamps.
- Perceptron returns integers on a 0-1000 grid. They are converted once in the
  adapter and out-of-grid or degenerate boxes are dropped and counted.
- EXIF orientation 1-8 and video display rotation are applied before
  analysis. `FrameTransform` records coded size, orientation, oriented size and
  the uniform resize, so a box maps back to source pixels with
  `geometry.display_box_to_coded`.
- Video timestamps come from decoded frame PTS through ffmpeg `showinfo`,
  never from an assumed frame rate. Stills have `timestampMs: null`.

## Environment

| Variable | Purpose | Default |
| --- | --- | --- |
| `PERCEPTRON_API_KEY` | Live adapter credentials, read by the SDK | none |
| `PERCEPTRON_MODEL` | Model for smoke check | `perceptron-mk1.5` |
| `PERCEPTRON_BASE_URL` | Optional SDK base URL override | SDK default |
| `CLIPCART_LIVE_PERCEPTRON` | Set to `1` to enable the live pytest | off |
| `CLIPCART_LIVE_IMAGE` | Optional real image for the live pytest | synthetic |
| `CLIPCART_MAX_VIDEO_BYTES`, `CLIPCART_MAX_IMAGE_BYTES`, `CLIPCART_MAX_VIDEO_MS`, `CLIPCART_MAX_INITIAL_FRAMES`, `CLIPCART_FRAME_MAX_SIDE` | Limit overrides via `MediaLimits.from_env()` | SRS section 9 values |

## Dependency request (root files are Claude-owned)

- `perceptron==0.4.0`, `Pillow>=11`, `numpy>=1.26`, `pydantic>=2.7`
- Test: `pytest>=8`
- System: `ffmpeg` and `ffprobe` 6+ (tested with 7.1.1)

## Running

```bash
cd <repo root>
pytest services/api/tests/media services/api/tests/perception -q
# live smoke, makes real paid calls:
cd services/api && PERCEPTRON_API_KEY=... python -m app.providers.perceptron.smoke path/to/photo.jpg --frames 1
```

## Fixtures

`tests/perception/fixtures/perceptron_dev_fixture.json` is a hand-authored
**development fixture** for a synthetic clip generated at test time. The
fixture backend refuses files without a `fixture_label`, and results carry
`mode: "fixture"`. It must never be presented as a live result.

## Known limitations

- The live Perceptron path has not been run from this lane (no key). Box
  semantics follow SDK 0.4.0 source and docs, and need one live confirmation.
- The SDK exposes request timeout only as global settings; `SdkBackend` sets it
  once. Calls abandoned at the deadline finish in the background and are
  discarded.
- `personTrackId` is always null. Grouping relies on spatial continuity,
  attributes and shot cuts, so it stays conservative across people.
- Mirrored video display matrices are not handled; only 0/90/180/270 rotation.
- HEIC/WebP uploads are rejected, matching FR01.
- Local disk storage only; the store interface is small enough to swap.
