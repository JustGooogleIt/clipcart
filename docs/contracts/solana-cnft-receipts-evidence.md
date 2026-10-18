# Solana demo cNFT receipts — verification evidence

Stacked on payment PR #13 (`feat/solana-demo-checkout`). **No new payment. No second tree/mint.**

Frozen for Terminal integration review (~2026-10-18 09:00 PT).

## Offline (complete)

| Check | Result |
| --- | --- |
| `tests/demo_receipts` + `tests/demo_orders` | **20 passed** (FakeMintAdapter / FakeRpc only; re-run 2026-10-18) |
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

## Live provision + mint (complete)

| Step | Result |
| --- | --- |
| `getGenesisHash` via public RPC | Pass (devnet) |
| Receipt authority (mode `0600`, gitignored under `.data/cnft/`) | `7DYdA9NWaGS3QxGP4uBWve5KAML4s3yZjuKDeBkpaUUT` |
| Authority funded | Pass (operator-funded; not faucet in-session) |
| Private Bubblegum V2 tree | `HaWhPiE6wEBENDnjWZh3KH3vS8R34cpmvui25itZ6aRD` (`maxDepth=3`, `maxBuffer=8`, `canopy=3`, `public=false`) |
| Tree create signature | `5o4ygUZpcPF5RiBtWrHuskv1e7J2Kb7U6BWAzqePMgYkwTVg484sDJVtEipNtnFWPDMvbTKRjdxGn6dnK1BS7FBL` |
| Mint to paid buyer `8W3Rgm2M…Swjo` | Pass |
| Mint signature | `Hfs1KdaiKLstxgXrbw7xzuiAL5CREUVFpw92pGQLdJCM6xjgiAnTadqH2WNaSwFFJKTRgvsNLwjmEDJmvim8KbD` |
| Asset ID | `HEtzjRrzUzYrSo2AaQJJsb5UXAXRXb8phLBchW7KUEhq` |
| DAS `getAsset` buyer ownership | Pass — `owner == 8W3Rgm2MFFkA3SP1TcUuvVaHMAPhJshZ4rdgJw2QSwjo` |

Machine-readable revalidation (no DAS URL/key):
[`solana-cnft-live-mint-evidence.json`](./solana-cnft-live-mint-evidence.json).

Preserved payment (unchanged; see also `solana-demo-live-verify-evidence.md`):

- Signature `3KjLMeXJUjidmxgbsvqWZQVCfHeBAupHnTk8rdc2EkNjr12A7iCCRXsgkbYqyjLVsioAPmsoDGPtA2Psz51HkbJh`
- Buyer `8W3Rgm2MFFkA3SP1TcUuvVaHMAPhJshZ4rdgJw2QSwjo`
- Order id `dmo_V-lqM-ub8XR8bsg5`
- Reference `HDKkghtD6ZYWBPEPPwFQrY1BL9TfVLM3H4J1ffFy8WyL`

## Public metadata hosting

Live mint used the public gist (private-repo raw GitHub 404):

- `https://gist.githubusercontent.com/JustGooogleIt/0d8fd0741788906da0165de7a7d6a98e/raw/cnft-receipt-demo-metadata.json`

Committed copies on this branch (optional alternate):

- https://raw.githubusercontent.com/JustGooogleIt/clipcart/feat/cnft-receipts/docs/contracts/cnft-receipt-demo-metadata.json
- Image: `docs/contracts/cnft-receipt-demo-mark.svg`

## DAS-enabled RPC

Public `https://api.devnet.solana.com` is **not** DAS-complete for cNFT reads. Local `.env` only: `SOLANA_DAS_RPC_URL` (e.g. Helius devnet). Never commit API keys.

## Operator freeze rules

1. **Do not** create another tree, payment, or mint.
2. Preserve durable `receipt_mint_attempts`, reconciliation, and this evidence.
3. Keep authority keypair local (`services/api/.data/cnft/receipt-authority.json`, mode `0600`).
4. Leave port **8000** and `main` to Terminal; do not merge #13/#29 from this lane.
5. Committed `.env.example` keeps both feature flags **false**.

## Limitations

- Wallet UI visibility of the cNFT is **untested** — do not claim Phantom shows it.
- Durable Mongo attempt rows for the live mint require operator `MONGODB_URI`; on-chain evidence above is independent and finalized.
