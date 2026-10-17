# Perception handoff for Claude (integration owner)

Branch: `feat/perception`  
PR: https://github.com/JustGooogleIt/clipcart/pull/2  
Base: latest `main` (includes catalog merge)  
Owner paths: `services/api/app/media/`, `services/api/app/providers/perceptron/`,  
`services/api/tests/media/`, `services/api/tests/perception/`

## Interface freeze (coordinate here)

Claude has not yet committed `app/contracts`. This branch freezes the **logical** T02 surface against SRS §12 and exposes provisional Pydantic models in `app/media/types.py` (camelCase aliases).

| Call | Returns |
| --- | --- |
| `MediaService.ingest(upload, owner_id)` | `MediaAsset` |
| `MediaService.extract_frames(media_id, owner_id, interval_ms?, max_frames?, …)` | `FrameRef[]` |
| `MediaService.detect_shot_boundaries(media_id, owner_id)` | `list[int]` cut times ms |
| `MediaService.crop(frame_asset_id, box01, owner_id)` | `CropRef` |
| `PerceptronPerceptionProvider.analyze(frame_refs, categories, RequestContext)` | `AnalysisResult` |
| `GarmentGrouper().group(observations, shot_boundaries_ms, session_id=…)` | `Garment[]` |

Please **import these shapes into `app/contracts`** (or generate them) and tell this lane to delete the copies. Proposed observation extensions already on the wire:

- `rawLabel`, `modelGeneratedFields`, `userCorrectedFields`

Additional contract records needed: `MediaAsset`, `FrameRef`, `FrameTransform`, `CropRef`, `ProviderRequestMeta`, `ProviderIssue`, `AnalysisResult`, `RequestContext`.

Do **not** silently change box semantics: `[xmin,ymin,xmax,ymax]` in `[0,1]`, top-left origin, validated (never clamped).

## What works offline (verified)

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install 'perceptron==0.4.0' 'Pillow>=11' 'numpy>=1.26' 'pydantic>=2.7' 'pytest>=8'
# system: ffmpeg/ffprobe 6+
export PYTHONPATH=services/api
pytest services/api/tests/media services/api/tests/perception -q \
  --ignore=services/api/tests/perception/test_perceptron_live.py
# -> 88 passed
```

Fixture path produces selectable jacket/top garments with `mode: "fixture"` — see  
`services/api/tests/perception/fixtures/example_analysis.fixture.json`  
and `fixtures/perception/sample_response.fixture.json`.

## Live Perceptron

**Blocked in this environment:** `PERCEPTRON_API_KEY` is unset.

```bash
cd services/api
PERCEPTRON_API_KEY=... python -m app.providers.perceptron.smoke path/to/photo.jpg --frames 1
# without key -> exit 2, no network call
```

Optional live pytest:

```bash
CLIPCART_LIVE_PERCEPTRON=1 PERCEPTRON_API_KEY=... \
  pytest services/api/tests/perception/test_perceptron_live.py -s
```

## Claude integration checklist

1. Merge/approve this PR (or cherry-pick owned paths).
2. Promote `app/media/types.py` into `app/contracts`; keep aliases stable.
3. Wire `POST /api/media/uploads`, analysis job, and garment selection to `MediaService` + `PerceptronPerceptionProvider`.
4. Surface `analysis.mode` (`live` | `fixture`) in UI/diagnostics — never present fixture as live (AT25).
5. Install deps at root when you own lockfiles: `perceptron`, `Pillow`, `numpy`, `pydantic` (+ system ffmpeg).
6. Set `PERCEPTRON_API_KEY` in deploy/demo env; run smoke on the demo clip.

## Out of scope on this branch

UI, catalog adapter, Grok workers, Mongo models, Photon, Solana.
