# Solana demo cNFT receipts — verification evidence

Stacked on payment PR #13 (`feat/solana-demo-checkout`). **No new payment.**

## Offline (complete)

| Check | Result |
| --- | --- |
| `tests/demo_receipts` + `tests/demo_orders` | **20 passed** (FakeMintAdapter / FakeRpc only) |
| Atomic claim + idempotent remint | No second `build_sign_mint` after success |
| Uncertain broadcast | `needs_reconciliation`; reconcile uses persisted signed tx |
| `local_memory` live mint | Refused (`cnft_durable_required`) |
| Genesis constant | `EtWTRABZaYq6iMfeYKouRu166VU2xqa1wcaWoxPkrZBG` |
| UI/API contract | `docs/contracts/solana-cnft-receipts.md` |

Pinned worker SDKs (`services/api/cnft_worker/package.json`):

- `@metaplex-foundation/mpl-bubblegum@6.0.0`
- `@metaplex-foundation/umi@1.6.0`
- `@metaplex-foundation/umi-bundle-defaults@1.6.0`
- `@metaplex-foundation/digital-asset-standard-api@2.1.1`

## Live provision (bounded; blocked on faucet)

| Step | Result |
| --- | --- |
| `getGenesisHash` via worker | Pass (devnet) |
| Generate receipt authority (mode `0600`, under `.data/cnft/`, gitignored) | Pass |
| Authority public key | `7DYdA9NWaGS3QxGP4uBWve5KAML4s3yZjuKDeBkpaUUT` |
| Devnet airdrop to authority | **Blocked** — public RPC `requestAirdrop` 429; faucet requires captcha/GitHub |
| Create private Bubblegum V2 tree (`maxDepth=5`, `maxBuffer=8`, `canopy=3`, `public=false`) | **Not run** (authority balance 0) |
| Mint receipt to paid buyer `8W3Rgm2M…Swjo` | **Not run** |
| DAS `getAsset` | **Not run** — configure `SOLANA_DAS_RPC_URL` (Helius/Triton DAS-enabled devnet) locally |

Preserved payment (unchanged):

- Signature `3KjLMeXJUjidmxgbsvqWZQVCfHeBAupHnTk8rdc2EkNjr12A7iCCRXsgkbYqyjLVsioAPmsoDGPtA2Psz51HkbJh`
- Buyer `8W3Rgm2MFFkA3SP1TcUuvVaHMAPhJshZ4rdgJw2QSwjo` (~0.99 SOL remaining on buyer; **not** used as fee payer)

## Public metadata hosting

Committed demo metadata (after push):

- https://raw.githubusercontent.com/JustGooogleIt/clipcart/feat/cnft-receipts/docs/contracts/cnft-receipt-demo-metadata.json
- Image: `docs/contracts/cnft-receipt-demo-mark.svg` on the same branch

Set `SOLANA_CNFT_METADATA_BASE_URL` to that JSON URL (or its directory) in local `.env` only.

## DAS-enabled RPC (identify)

Public `https://api.devnet.solana.com` is **not** DAS-complete for cNFT reads. Use a DAS-enabled provider in local config only, e.g.:

- Helius: `https://devnet.helius-rpc.com/?api-key=<LOCAL>`
- Triton / other Metaplex DAS partners

Never commit API keys.

## Resume live mint (operator)

1. Fund `7DYdA9NWaGS3QxGP4uBWve5KAML4s3yZjuKDeBkpaUUT` with ≥1 SOL on **devnet** (human faucet / CLI when rate limits allow).
2. Local `.env` (flag off in committed example):

```text
FEATURE_SOLANA=true
FEATURE_SOLANA_CNFT_RECEIPTS=true
SOLANA_CNFT_AUTHORITY_KEYPAIR_PATH=services/api/.data/cnft/receipt-authority.json
SOLANA_CNFT_RECEIPT_AUTHORITY=7DYdA9NWaGS3QxGP4uBWve5KAML4s3yZjuKDeBkpaUUT
SOLANA_CNFT_METADATA_BASE_URL=https://raw.githubusercontent.com/JustGooogleIt/clipcart/feat/cnft-receipts/docs/contracts/cnft-receipt-demo-metadata.json
SOLANA_DAS_RPC_URL=<local DAS URL>
MONGODB_URI=<already required for durable attempts>
```

3. `node services/api/cnft_worker/src/cli.mjs create-tree --keypair … --max-depth 5 --max-buffer 8 --canopy 3`
4. Set `SOLANA_CNFT_TREE_ADDRESS` from the JSON result.
5. `python services/api/scripts/cnft_live_mint_preserved_order.py`

## Limitations

- Live tree + mint **not completed** in this session (faucet rate limit / captcha).
- Wallet UI visibility of the cNFT is **untested** — do not claim Phantom shows it.
- Payment PR #13 remains separate; this PR stacks on it and must stay draft until live mint evidence exists or the integration owner accepts the faucet limitation.
