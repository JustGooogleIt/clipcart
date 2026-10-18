# Solana demo checkout — preserved payment evidence

**Do not request another payment.** This documents the one successful 0.01 SOL
devnet transfer used for PR #13 verification.

## Transaction (preserved)

| Field | Value |
| --- | --- |
| Signature | `3KjLMeXJUjidmxgbsvqWZQVCfHeBAupHnTk8rdc2EkNjr12A7iCCRXsgkbYqyjLVsioAPmsoDGPtA2Psz51HkbJh` |
| Explorer | https://explorer.solana.com/tx/3KjLMeXJUjidmxgbsvqWZQVCfHeBAupHnTk8rdc2EkNjr12A7iCCRXsgkbYqyjLVsioAPmsoDGPtA2Psz51HkbJh?cluster=devnet |
| Network | Solana **devnet** |
| Recipient (merchant) | `3yVVaxvuDpXBJWFGetwdCAC3bRXoo4d7bjXeX5Xn8y73` |
| Source (buyer) | `8W3Rgm2MFFkA3SP1TcUuvVaHMAPhJshZ4rdgJw2QSwjo` |
| Amount | `10000000` lamports (0.01 SOL) |
| Payment reference | `HDKkghtD6ZYWBPEPPwFQrY1BL9TfVLM3H4J1ffFy8WyL` |
| `blockTime` | `1792306975` (`2026-10-18T07:02:55Z`) |
| Confirmation | `finalized`, `err: null` |

Machine-readable snapshot from the direct live revalidation:
[`solana-demo-live-verify-evidence.json`](./solana-demo-live-verify-evidence.json).

## Verification method ledger

| Check | Source | Result |
| --- | --- | --- |
| `getGenesisHash` == `EtWTRABZaYq6iMfeYKouRu166VU2xqa1wcaWoxPkrZBG` | **Direct live RPC** `https://api.devnet.solana.com` via `SolanaRpc` (`trust_env=False`) | Pass |
| `getSignatureStatuses` finalized / ok | **Direct live RPC** | Pass |
| `getTransaction` jsonParsed | **Direct live RPC** | Pass |
| Native transfer recipient + exact lamports | Live tx body + `inspect_transaction` | Pass |
| Reference account in keys | Live tx body | Pass |
| Transfer source (buyer) | Live tx body | Pass |
| `meta.err` null / success | Live status + tx | Pass |
| `blockTime` within order `[createdAt, expiresAt]` | Live `blockTime` vs reconstructed smoke order window (created ≤ `blockTime` ≤ created+TTL) | Pass |
| Already-paid HTTP idempotent replay | **Not counted** as RPC verification (`VerifyMeta.rpc_invoked=False`) | N/A |

### Historical (not production proof)

Earlier smoke runs hit `rpc_unavailable` because the agent sandbox’s HTTP proxy
403’d Solana CONNECT / blocked DNS. A **browser-captured** tx was temporarily
served by a local fixture RPC to exercise the mark-paid path. That fixture path
is **removed** from the tree; FakeRpc remains **unit-test only**. Production
`POST /api/demo-orders/{id}/verify` never accepts browser-posted transaction
JSON and never points `SOLANA_RPC_URL` at a fixture by default.

## Production invariants

1. Evidence comes only from `SOLANA_RPC_URL` through `SolanaRpc`.
2. Client `paymentSignature` / `buyerWallet` are search hints only.
3. `trust_env=False` applies only to the default httpx client constructed inside
   `SolanaRpc` (not process-wide).
4. Devnet genesis constant matches Anza/docs: `…WoxPkrZBG` (not the prior typo).

## Remaining limitations

- Cursor agent sandboxes may still be unable to reach public Solana RPC without
  elevated/unsandboxed network; operators should verify from a normal host with
  `SOLANA_RPC_URL=https://api.devnet.solana.com`.
- Port **8000** (main ClipCart) stays untouched; smoke used other ports with
  process-only `FEATURE_SOLANA=true`.
- NFT / Bubblegum minting remains out of scope (`receiptStatus: eligible` only).
