# Solana demo checkout + cNFT receipts — Terminal handoff

**Status:** functionality frozen for integration review (target ~09:00 PT 2026-10-18).  
**Repo:** https://github.com/JustGooogleIt/clipcart  
**Lane:** Cursor agent (`feat/cnft-receipts` worktree). Port **8000** and `main` remain Terminal’s.

Do **not** create another tree, payment, or mint. Do **not** merge from this lane. Do **not** redesign checkout. Resolve review findings against frozen contracts below.

## Exact heads (freeze)

| PR | Branch | Base | Head SHA | Draft |
| --- | --- | --- | --- | --- |
| [#13](https://github.com/JustGooogleIt/clipcart/pull/13) | `feat/solana-demo-checkout` | `integration` | `1eb6c47a4f1e2bee53ce55aef2b5f35044820500` | yes |
| [#29](https://github.com/JustGooogleIt/clipcart/pull/29) | `feat/cnft-receipts` | `feat/solana-demo-checkout` | `df8f84ebf05d98f032a257f782bcda605f984ec6` | yes |

Stack: #13 ⊂ #29 (`feat/solana-demo-checkout` is an ancestor of `feat/cnft-receipts`).

## Contracts (coordinate generated types here)

| Surface | Path |
| --- | --- |
| Checkout / Solana Pay verify | `docs/contracts/solana-demo-checkout.md` |
| Payment live evidence | `docs/contracts/solana-demo-live-verify-evidence.md` (+ `.json`) |
| cNFT receipt API/UI | `docs/contracts/solana-cnft-receipts.md` |
| cNFT offline + live evidence | `docs/contracts/solana-cnft-receipts-evidence.md` |
| Live mint revalidation | `docs/contracts/solana-cnft-live-mint-evidence.json` |
| Prerequisites checklist | `docs/contracts/solana-cnft-prereqs.md` |

Please import wire shapes into Terminal’s `app/contracts` (or equivalent) from the JSON examples in those docs. Do not silently change payment verification semantics or receipt state machine.

## On-chain artifacts (preserved)

| Artifact | Value |
| --- | --- |
| Merkle tree | `HaWhPiE6wEBENDnjWZh3KH3vS8R34cpmvui25itZ6aRD` |
| Payment signature | `3KjLMeXJUjidmxgbsvqWZQVCfHeBAupHnTk8rdc2EkNjr12A7iCCRXsgkbYqyjLVsioAPmsoDGPtA2Psz51HkbJh` |
| Mint signature | `Hfs1KdaiKLstxgXrbw7xzuiAL5CREUVFpw92pGQLdJCM6xjgiAnTadqH2WNaSwFFJKTRgvsNLwjmEDJmvim8KbD` |
| Asset ID | `HEtzjRrzUzYrSo2AaQJJsb5UXAXRXb8phLBchW7KUEhq` |
| Buyer (leaf owner) | `8W3Rgm2MFFkA3SP1TcUuvVaHMAPhJshZ4rdgJw2QSwjo` |
| Merchant | `3yVVaxvuDpXBJWFGetwdCAC3bRXoo4d7bjXeX5Xn8y73` |
| Order id | `dmo_V-lqM-ub8XR8bsg5` |
| Payment reference | `HDKkghtD6ZYWBPEPPwFQrY1BL9TfVLM3H4J1ffFy8WyL` |
| Receipt authority (pubkey) | `7DYdA9NWaGS3QxGP4uBWve5KAML4s3yZjuKDeBkpaUUT` |

## Direct RPC + DAS ownership evidence

Revalidated at freeze (see `solana-cnft-live-mint-evidence.json`):

- Public RPC `https://api.devnet.solana.com`: genesis `EtWTRABZaYq6iMfeYKouRu166VU2xqa1wcaWoxPkrZBG`; payment + mint both `finalized` / `err: null`; tree account exists.
- DAS (`SOLANA_DAS_RPC_URL`, local secret omitted): `getAsset` → `owner == 8W3Rgm2MFFkA3SP1TcUuvVaHMAPhJshZ4rdgJw2QSwjo`, `compressed: true`, `tree` matches above, `leaf_id: 0`.

```bash
# Payment + mint status (public RPC)
curl -sS https://api.devnet.solana.com -H 'content-type: application/json' -d '{
  "jsonrpc":"2.0","id":1,"method":"getSignatureStatuses",
  "params":[[
    "3KjLMeXJUjidmxgbsvqWZQVCfHeBAupHnTk8rdc2EkNjr12A7iCCRXsgkbYqyjLVsioAPmsoDGPtA2Psz51HkbJh",
    "Hfs1KdaiKLstxgXrbw7xzuiAL5CREUVFpw92pGQLdJCM6xjgiAnTadqH2WNaSwFFJKTRgvsNLwjmEDJmvim8KbD"
  ],{"searchTransactionHistory":true}]
}'

# DAS ownership (requires local SOLANA_DAS_RPC_URL)
cd services/api/cnft_worker
node src/cli.mjs get-asset \
  --das-rpc "$SOLANA_DAS_RPC_URL" \
  --asset-id HEtzjRrzUzYrSo2AaQJJsb5UXAXRXb8phLBchW7KUEhq
# expect owner == 8W3Rgm2MFFkA3SP1TcUuvVaHMAPhJshZ4rdgJw2QSwjo
```

## Environment variable names (no secret values)

Payment (#13):

- `FEATURE_SOLANA` (committed default `false`)
- `SOLANA_NETWORK` (`devnet`)
- `SOLANA_RPC_URL`
- `SOLANA_DEMO_MERCHANT_WALLET`
- `SOLANA_DEMO_AMOUNT_LAMPORTS`
- `SOLANA_DEMO_ORDER_TTL_S`

Receipts (#29):

- `FEATURE_SOLANA_CNFT_RECEIPTS` (committed default `false`)
- `SOLANA_CNFT_TREE_ADDRESS`
- `SOLANA_CNFT_RECEIPT_AUTHORITY` (public pubkey only)
- `SOLANA_CNFT_AUTHORITY_KEYPAIR_PATH`
- `SOLANA_DAS_RPC_URL`
- `SOLANA_CNFT_METADATA_BASE_URL`
- `SOLANA_CNFT_WORKER_DIR` (optional; default `services/api/cnft_worker`)
- `MONGODB_URI` / `MONGODB_DB` (durable attempts; live mint refuses `local_memory`)

**Local signer file path (never commit):**  
`services/api/.data/cnft/receipt-authority.json` (mode `0600`, gitignored)

## Candidate backend + preserved receipt checks

Use a **non-8000** port. Enable flags in-process only; keep committed `.env.example` flags off.

```bash
# Offline combined suite (FakeRpc / FakeMintAdapter)
cd services/api
pytest tests/demo_orders tests/demo_receipts -q
# expected: 20 passed

# Candidate API (example port 8020 — do not take 8000)
cd services/api
FEATURE_SOLANA=true \
FEATURE_SOLANA_CNFT_RECEIPTS=true \
SOLANA_NETWORK=devnet \
SOLANA_RPC_URL=https://api.devnet.solana.com \
SOLANA_DEMO_MERCHANT_WALLET=3yVVaxvuDpXBJWFGetwdCAC3bRXoo4d7bjXeX5Xn8y73 \
SOLANA_CNFT_TREE_ADDRESS=HaWhPiE6wEBENDnjWZh3KH3vS8R34cpmvui25itZ6aRD \
SOLANA_CNFT_RECEIPT_AUTHORITY=7DYdA9NWaGS3QxGP4uBWve5KAML4s3yZjuKDeBkpaUUT \
SOLANA_CNFT_AUTHORITY_KEYPAIR_PATH=services/api/.data/cnft/receipt-authority.json \
SOLANA_CNFT_METADATA_BASE_URL=https://gist.githubusercontent.com/JustGooogleIt/0d8fd0741788906da0165de7a7d6a98e/raw/cnft-receipt-demo-metadata.json \
SOLANA_DAS_RPC_URL="$_YOUR_LOCAL_DAS_" \
MONGODB_URI="$_YOUR_LOCAL_MONGO_" \
uvicorn app.main:app --host 127.0.0.1 --port 8020

# Smoke UI (payment page; no new payment needed for review)
open http://127.0.0.1:8020/demo/solana-pay

# Preserved receipt — on-chain / DAS only (preferred; no remint)
node services/api/cnft_worker/src/cli.mjs get-asset \
  --das-rpc "$SOLANA_DAS_RPC_URL" \
  --asset-id HEtzjRrzUzYrSo2AaQJJsb5UXAXRXb8phLBchW7KUEhq

# If seeding the preserved order into durable Mongo for API GET:
# use scripts/cnft_live_mint_preserved_order.py ONLY after confirming no second mint
# will be built (existing confirmed attempt / remint guards). Prefer GET after seed:
#   GET /api/demo-orders/dmo_V-lqM-ub8XR8bsg5
# with owner cookie for own_cnft_receipt_smoke_01 — expect receipt card when seeded.
```

Idempotent mint route (must not create a second tx when attempt exists):

`POST /api/demo-orders/{order_id}/receipt/mint` — see contract.

## Review coordination

- Findings → comment on #13 / #29; this lane will fix quickly against frozen contracts.
- Generated contracts / dependency pins: align with worker `package.json` versions listed in the evidence doc.
- Private keys stay local. No force-push of `main`. No independent merge.
