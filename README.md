# ClipCart

Fashion shopping agent for DubHacks. Spec: [`docs/ClipCart_SRS.md`](docs/ClipCart_SRS.md).

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
