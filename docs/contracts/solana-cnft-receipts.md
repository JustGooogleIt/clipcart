# Contract: Solana demo cNFT receipts (devnet, Bubblegum V2)

Status: additive UI + API contract for stacked PR `feat/cnft-receipts` (bases on payment PR #13).
Compressed NFT minting is **optional** and behind `FEATURE_SOLANA_CNFT_RECEIPTS` (default **off**).
Checkout payment success must not depend on mint success.

## Flags

```text
FEATURE_SOLANA=false                 # payment path (unchanged)
FEATURE_SOLANA_CNFT_RECEIPTS=false   # this PR; requires payment flag on for mint routes
```

Leave port **8000** and existing flags unchanged in committed `.env`.

## Eligibility (server-enforced)

A receipt mint may proceed only when **all** are true:

1. `FEATURE_SOLANA` and `FEATURE_SOLANA_CNFT_RECEIPTS` are on.
2. Persistence is durable (`MONGODB_URI` set). Live mint refuses `local_memory`.
3. Order `status === "paid"` with server-verified `paymentSignature` and `buyerWallet`.
4. Order is a ClipCart demo merchant order (not a retailer click, saved item, or self-report).
5. Amount, recipient, and payment signature are taken from **server records**, never from the browser body as proof.
6. Devnet genesis hash matches `EtWTRABZaYq6iMfeYKouRu166VU2xqa1wcaWoxPkrZBG` before provision/mint.

Mint leaf owner is always the order’s recorded `buyerWallet` (not the fee payer, not a browser-supplied wallet).

## Receipt states (existing enum)

`receiptStatus`: `ineligible` → `eligible` → `minting` → `confirmed` | `failed` | `needs_reconciliation`

| State | Meaning |
| --- | --- |
| `eligible` | Payment verified; no successful mint yet |
| `minting` | Attempt claimed; signed tx may be persisted / in flight |
| `confirmed` | Mint tx finalized; asset id known (DAS may still be pending) |
| `failed` | Terminal mint failure after reconciliation (no silent retry storm) |
| `needs_reconciliation` | Outcome uncertain; must reconcile existing attempt before any new tx |

## UI card (additive)

Frontend may render a receipt card when `receipt` is present on order GET/mint responses:

```json
{
  "receipt": {
    "status": "confirmed",
    "assetId": "<base58 or null>",
    "mintSignature": "<base58 or null>",
    "explorerMintUrl": "https://explorer.solana.com/tx/<sig>?cluster=devnet",
    "buyerWallet": "<base58>",
    "merkleTree": "<base58 or null>",
    "indexingStatus": "ready",
    "metadataUri": "https://…/cnft-receipt-demo-metadata.json",
    "label": "ClipCart demo receipt · Devnet · No retailer fulfillment."
  }
}
```

`indexingStatus`: `pending` | `ready` | `unavailable`

- `pending`: mint signature preserved; DAS has not returned the asset yet — **do not mint again**.
- `ready`: DAS returned the asset; ownership/tree/metadata checks passed.
- `unavailable`: DAS not configured or errored; still do not remint when `mintSignature` exists.

**Wallet visibility:** do not claim Phantom (or any wallet) shows the cNFT until explicitly tested. Copy may say “mint confirmed on-chain” / “indexing pending”.

## API

### `POST /api/demo-orders/{id}/receipt/mint`

Headers: `X-ClipCart-Request: 1`, owner cookie. Empty body (or ignored hints only).

Returns `{ "order": {…}, "receipt": {…} }`.

Repeated calls return the existing attempt/receipt (idempotent). Never creates a second mint tx while an attempt is `signed`, `submitted`, `confirmed`, or `needs_reconciliation`.

| HTTP | code | When |
| --- | --- | --- |
| 404 | `feature_disabled` | Either Solana flag off |
| 404 | `not_found` | Wrong owner / unknown order |
| 409 | `receipt_ineligible` | Order not paid / not demo-eligible |
| 503 | `cnft_not_configured` | Tree, authority, DAS URL, or durable DB missing |
| 503 | `cnft_durable_required` | Attempted live mint on `local_memory` |
| 200 | — | Existing or newly progressed receipt |

Mint failure leaves payment `status: paid` and sets `receiptStatus` to `failed` or `needs_reconciliation` without failing checkout.

### `GET /api/demo-orders/{id}`

When receipts flag is on and an attempt/receipt exists, response may include `receipt` (same card shape). Payment fields unchanged.

## Metadata rules

On-chain / JSON metadata must clearly state:

> ClipCart demo receipt · Devnet · No retailer fulfillment.

Include minimal facts only: demo order id, amount display, payment signature (public), network, merchant label. **Do not** publish session ids, wardrobe history, or personal preferences.

## Reliability

1. Atomically claim one mint attempt per `orderId` (unique index).
2. Persist the **signed** transaction bytes + intent before broadcast.
3. On timeout/restart: reload attempt; confirm/reconcile signature before building another tx.
4. Uncertain broadcast → `needs_reconciliation`, never a duplicate mint.
5. Unit tests use a fake mint adapter; live Bubblegum calls are opt-in scripts only.

## Env (names only; secrets local)

```text
FEATURE_SOLANA_CNFT_RECEIPTS=false
SOLANA_CNFT_TREE_ADDRESS=
SOLANA_CNFT_RECEIPT_AUTHORITY=          # public pubkey only in env
SOLANA_CNFT_AUTHORITY_KEYPAIR_PATH=     # local path; never commit the file
SOLANA_DAS_RPC_URL=                     # DAS-enabled devnet RPC (e.g. Helius); local only
SOLANA_CNFT_METADATA_BASE_URL=          # public HTTPS base for metadata JSON
SOLANA_CNFT_WORKER_DIR=services/api/cnft_worker
```

Authority key material: generate locally with mode `0600`, never log or return in API responses.
