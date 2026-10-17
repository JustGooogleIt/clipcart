# ClipCart

Fashion shopping agent for DubHacks. Spec: [`docs/ClipCart_SRS.md`](docs/ClipCart_SRS.md).

## Ownership (short)

| Area | Owner |
| --- | --- |
| App / UI / contracts / Grok / Atlas | Claude Code |
| Media + Perceptron | Codex |
| Catalog access + listing evidence | Cursor teammate (`feat/catalog-access`) |

## Catalog (this teammate slice)

PR: https://github.com/JustGooogleIt/clipcart/pull/1  
Docs: [`docs/provider-access.md`](docs/provider-access.md), [`docs/evaluation.md`](docs/evaluation.md), [`docs/teammate-blockers.md`](docs/teammate-blockers.md).

```bash
# Live SoleScout (no key)
python3 scripts/catalog_smoke.py --query "denim jacket" --limit 3

# Labeled fixtures
CATALOG_PROVIDER=fixture python3 scripts/catalog_smoke.py --query "leather jacket"

# Offline tests (stdlib unittest; no venv required)
python3 -m unittest discover -s services/api/tests/catalog -v
```

Env template: [`docs/catalog.env.example`](docs/catalog.env.example).
