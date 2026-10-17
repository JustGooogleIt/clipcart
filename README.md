# ClipCart

Fashion shopping agent for DubHacks. Spec: [`docs/ClipCart_SRS.md`](docs/ClipCart_SRS.md).

## Ownership (short)

| Area | Owner |
| --- | --- |
| App / UI / contracts / Grok / Atlas | Claude Code |
| Media + Perceptron | Codex |
| Catalog access + listing evidence | Cursor teammate (`feat/catalog-access`) |

## Catalog (this teammate slice)

Docs: [`docs/provider-access.md`](docs/provider-access.md), [`docs/evaluation.md`](docs/evaluation.md).

```bash
# Live SoleScout (no key)
python3 scripts/catalog_smoke.py --query "denim jacket" --limit 3

# Labeled fixtures
CATALOG_PROVIDER=fixture python3 scripts/catalog_smoke.py --query "leather jacket"
```

Env template: [`docs/catalog.env.example`](docs/catalog.env.example).
