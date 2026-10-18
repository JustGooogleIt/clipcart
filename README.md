# ClipCart

Fashion shopping agent for DubHacks. Spec: [`docs/ClipCart_SRS.md`](docs/ClipCart_SRS.md).

## Run locally

Requirements: Python 3.11+, Node 20+, and `ffmpeg`/`ffprobe` on PATH.

```bash
cp .env.example .env      # optional: add PERCEPTRON_API_KEY, XAI_API_KEY, MONGODB_URI
scripts/dev.sh            # builds apps/web and serves UI + API on http://127.0.0.1:8000
```

Without keys, the app runs honestly in reduced modes: detection "not configured" with a manual box, rule-based search workers, and a local in-process store. Mode chips at the top and `#/diagnostics` show which modes are active.

Tests: `services/api/.venv/bin/python -m pytest services/api/tests -q`. Web typecheck: `cd apps/web && npx tsc -b`.

Live checks once keys exist (bounded spend, prints no secrets):

```bash
services/api/.venv/bin/python scripts/live_checks.py --image path/to/garment.jpg   # perceptron, grok, atlas
cd services/api
CLIPCART_LIVE_PERCEPTRON=1 PERCEPTRON_API_KEY=... .venv/bin/python -m pytest tests/perception/test_perceptron_live.py -s
PERCEPTRON_API_KEY=... .venv/bin/python -m app.providers.perceptron.smoke path/to/photo.jpg --frames 1
```

Status: [`docs/status.md`](docs/status.md). Decisions: [`docs/decisions.md`](docs/decisions.md).

## Ownership (short)

| Area | Owner |
| --- | --- |
| App / UI / contracts / Grok / Atlas | Claude Code |
| Media + Perceptron | Codex / Cursor lane (`feat/perception`) |
| Catalog access + listing evidence | Teammate (`feat/catalog-access`, merged) |

## Perception (media + Perceptron)

PR: https://github.com/JustGooogleIt/clipcart/pull/2  
Docs: [`docs/perception-handoff.md`](docs/perception-handoff.md), [`services/api/app/media/README.md`](services/api/app/media/README.md).

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install 'perceptron==0.4.0' 'Pillow>=11' 'numpy>=1.26' 'pydantic>=2.7' 'pytest>=8'
# also need ffmpeg/ffprobe on PATH
export PYTHONPATH=services/api
pytest services/api/tests/media services/api/tests/perception -q \
  --ignore=services/api/tests/perception/test_perceptron_live.py

# live smoke (requires key; exits 2 if missing)
cd services/api && PERCEPTRON_API_KEY=... python -m app.providers.perceptron.smoke ../path/to.jpg
```

Labeled sample (not live): [`fixtures/perception/sample_response.fixture.json`](fixtures/perception/sample_response.fixture.json).  
Env: [`docs/perception.env.example`](docs/perception.env.example).

## Catalog

PR: https://github.com/JustGooogleIt/clipcart/pull/1 (merged).  
Docs: [`docs/provider-access.md`](docs/provider-access.md).

```bash
python3 scripts/catalog_smoke.py --query "denim jacket" --limit 3
python3 -m unittest discover -s services/api/tests/catalog -v
```
