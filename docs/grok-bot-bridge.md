# Grok Bot as shopping research agent: bridge findings

Checked 2026-10-17 against official xAI and Cursor documentation. Status: **not proven; not implemented**. Only the provider-neutral job interface and a labelled fixture ship on `feat/grok-bot-research`.

## Proposed bridge versus documentation

| Step | Official documentation | Status |
| --- | --- | --- |
| 1. ClipCart triggers a Bot routine with job context | Cursor help, *Routines*: a routine can have a webhook trigger. The desktop app (0.53.0+) shows a POST URL and a key. Senders use `Authorization: Bearer <key>`. "You can send a JSON body. The Bot receives that body with the routine instruction." "A response of 200 means Grok Bot accepted the call and started a run. It does not mean the Bot has finished the instruction." | Documented, not yet exercised. This is a **bearer key**, not an HMAC signature, so "signed webhook" is not available as such. |
| 2. Bot researches products | xAI *Grok Bot*: Bots run on a persistent cloud computer with a browser. "Each run spends usage." | Documented in general terms |
| 3. Bot returns structured results to ClipCart | Not documented. Neither xAI nor Cursor describes a routine calling an external HTTP endpoint or a custom MCP tool. xAI *Approvals*: actions from work that started without you, "such as a routine, a trigger", wait for approval and expire after about 10 minutes unless an Allow rule matches. A Cursor community request (unofficial) reports webhook-started outbound POSTs being held by Auto Review. xAI *Connectors* documents custom MCP for Grok, not for Grok Bot routines. | **Unproven. This is the blocker.** |
| 4. ClipCart stores results and exposes polling | Ours | Implemented (provider-neutral) |

The webhook response never carries the Bot's answer, per the docs and confirmed by the probe self-test design. Results appear in the Bot's chat unless the Bot actively calls back.

A Grok, SuperGrok or Cursor subscription is **not** xAI API credit. The existing xAI API worker path (`XAI_API_KEY`) is separate and unchanged.

## Exact blocker

1. No routine exists that ClipCart can call. Creating one requires a person in the Cursor desktop app. No `GROK_BOT_WEBHOOK_URL` or `GROK_BOT_WEBHOOK_KEY` is available.
2. Unattended callback behavior is undocumented and may be held for approval. It must be observed, not assumed.
3. A public HTTPS endpoint is needed for the callback. No tunnel tool is installed here, and none was added.

## Smallest experiment (ready)

`scripts/experiments/grokbot_bridge_probe.py` sends one webhook POST (8 s timeout, one try, no redirects) with a nonce and a one-time callback token. It then waits on a local listener for the Bot to POST the nonce back. It prints a JSON verdict for trigger, payload access and callback, and never prints the key or token.

1. In Cursor desktop, ask your Bot to create a routine with a webhook trigger and this instruction:

   > When triggered, read the JSON body. Send an HTTP POST to body.callbackUrl with header Authorization set to body.callbackAuthorization and JSON body {"probeId": body.probeId, "nonce": body.nonce, "echo": "pong"}. Do nothing else.

2. Add an Allow rule for POST requests to your tunnel host. Without it, expect the call to wait for approval and expire.
3. Expose port 8765 over HTTPS with any tunnel, then run:

   ```bash
   GROK_BOT_WEBHOOK_URL=... GROK_BOT_WEBHOOK_KEY=... PROBE_PUBLIC_BASE_URL=https://<tunnel> \
     python3 scripts/experiments/grokbot_bridge_probe.py
   ```

Possible outcomes:
- All three proven: build the `grok_bot` provider (below).
- Trigger proven but no callback: the bridge is not viable unattended. Use an xAI API agent instead.

## If proven: what the `grok_bot` provider adds (not built)

- `dispatch`: POST the job context. The crop goes as a short-lived HMAC-signed URL, never a raw asset ID. Include a one-time per-job callback token stored hashed. Use an 8 s timeout, at most one retry on network error only, and treat any non-200 as `dispatch_failed`.
- Callback route `POST /api/research-jobs/{id}/results`: bearer token compared in constant time, body capped at 256 KB, validated against `ResearchSubmission`, then into `ingest_submission`, which already handles one-time acceptance, expiry, the strict schema, URL safety, deduplication and labelling.
- Secrets in env only. The key and tokens never reach the browser, logs or git.
