# Catalog fixtures

| Path | Purpose |
| --- | --- |
| `demo_catalog.json` | Labeled sourced listings + evidence (`mode: fixture`) |
| `search_examples.json` | Eight+ fashion search scenarios |
| `raw/` | Captured live SoleScout responses (not secrets) |

Run:

```bash
# Live
python3 scripts/catalog_smoke.py --query "canvas tote bag" --limit 3

# Fixture
CATALOG_PROVIDER=fixture python3 scripts/catalog_smoke.py --query "leather jacket"
```
