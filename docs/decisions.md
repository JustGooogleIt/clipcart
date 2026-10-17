# Decisions

| Date | Decision | Why |
| --- | --- | --- |
| 2026-10-17 | Canonical Pydantic contracts live in `services/api/app/contracts`. JSON Schema and TypeScript are generated into `packages/contracts` (`scripts/gen_contracts.py`, `npm run gen:types`). | One source of truth (SRS §8). |
| 2026-10-17 | Media records are promoted unchanged from PR #2. `app/media/types.py` re-exports them. | Honors the perception owner's handoff without forking the schema. |
| 2026-10-17 | `Listing.priceBasis`, `sellerVisibility`, `storeOffers` and `OutboundLink.kind` are added to the SRS Listing. | SoleScout prices are the lowest across often-hidden retailers. Without these fields, the UI could imply a named store's price or a retailer checkout. |
| 2026-10-17 | SoleScout adapter: detail listings keep the retailer as "SoleScout (aggregator)". Visible stores are exposed in diagnostics with their own, usually null, prices. | The adapter labeled the $1,300 hidden-seller lowest price as "GOAT" during a live check. A regression test was added. The catalog owner was informed through this log. |
| 2026-10-17 | Constraint unknowns go to "Needs checking" and never to "Recommended". Material exclusions are violated only on title evidence, and faux mentions stay unknown. | SRS §11, AT10. |
| 2026-10-17 | Sizes are never converted across systems. Alpha versus numeric is unknown. | SRS §11. |
| 2026-10-17 | The Grok runtime uses the xAI OpenAI-compatible `/v1/chat/completions` with function tools. The model is `grok-4.3`, configurable through `XAI_MODEL`. It is limited to 3 rounds per worker and shares a budget of 12 tool calls, 6 detail calls and 60 s. Auth or other failures fall back to rule-based queries, labeled `rule_based_fallback`. | SRS §10. Keeps the demo usable without overstating agentic mode. |
| 2026-10-17 | Local development without `MONGODB_URI` uses mongomock, reported as `local_memory`. | SRS §4 fallback. It is never presented as Atlas. |
| 2026-10-17 | Uploads use a raw-body POST, streamed with a 150 MB cap before decoding. Multipart is not used. | Starlette multipart would buffer the whole file before the limit could apply. |
| 2026-10-17 | Cross-site mutation is blocked by a required `X-ClipCart-Request` header. Same-origin serving needs no CORS. | SRS §20 without a token store. |
| 2026-10-17 | Python's CA bundle comes from certifi when `SSL_CERT_FILE` is unset. | The python.org macOS build failed TLS to SoleScout. |
