# Grok Bot as shopping research agent: bridge findings

## Status (2026-10-18)

- **Callback probe passed** (`probe_3a9b8b501a75`):
  - **Trigger:** the webhook returned 200 and a run started. Its response held no answer.
  - **Payload:** the Bot echoed the exact nonce and probe ID.
  - **Callback:** an authenticated POST with the one-time token arrived **14.1 s** after the trigger.
- **Unattended operation is unverified.** The owner hasn't yet confirmed whether they approved an action in Cursor during the run. Until they do, treat the bridge as "works, possibly with a person approving".
- **Research is not yet operational.** Health reports `research.status: "unverified"` for a configured `grok_bot` until a Bot research job completes with the Bot's own results. A manual import doesn't count. Only then does health report `operational` and the UI read Live. `research.mode: "live"` describes the data source only; it never claims the provider works.

### Certificates (macOS, python.org Python)

The python.org build of Python 3.11 here ships with no CA bundle. Run without one, the probe failed at the TLS handshake with `CERTIFICATE_VERIFY_FAILED`, before anything was sent. **Don't disable verification.** Point Python at a trusted bundle instead, for example the API venv's certifi:

```
SSL_CERT_FILE="$(services/api/.venv/bin/python -c 'import certifi; print(certifi.where())')" \
  python3 scripts/experiments/grokbot_bridge_probe.py
```

Alternatively, run the python.org "Install Certificates.command" once. The API server itself uses httpx with certifi and needs neither.

### Local configuration

Settings live only in gitignored, `chmod 600` files in the integration worktree: `grokbot-probe.local.env` for the probe routine, and `grokbot-research.local.env` for the research routine. The research file holds the webhook URL and key, `CLIPCART_PUBLIC_BASE_URL` (a tunnel to the ClipCart server, not to the probe port) and a persistent `RESEARCH_URL_SECRET`.

## Prove the callback: the smallest exact setup (owner, done once)

Rechecked 2026-10-18 against [Cursor help: Grok Bot routines](https://cursor.com/help/grok-bot/routines), the [Grok Bot FAQ](https://cursor.com/help/grok-bot/faqs.md) and [xAI: approvals, security and privacy](https://docs.x.ai/grok-bot/approvals-security-and-privacy).

1. **Tunnel.** In one terminal, run `brew install cloudflared`, then `cloudflared tunnel --url http://127.0.0.1:8765`. That's a quick tunnel and needs no account. Copy the `https://….trycloudflare.com` address it prints. Quick tunnels can expire; one stopped answering with "Tunnel not found" after several hours, and a new tunnel gets a new address.
2. **Routine.** In the Grok Bot **desktop app** (only desktop shows webhook details), send the Bot exactly this:
   > Create a routine named "ClipCart callback probe" with a webhook trigger and no schedule. Instruction: When triggered, read the JSON body. Send an HTTP POST to body.callbackUrl with header Authorization set to body.callbackAuthorization and JSON body {"probeId": body.probeId, "nonce": body.nonce, "echo": "pong"}. Do nothing else.
3. **Webhook URL and key.** Click the Bot's name, then **Details**, then **Routines**, then the routine. In the **Webhook** section, copy **POST to** and **key**. A Grok or SuperGrok subscription is not an xAI API key, and this needs none.
4. **Allow rule.** Go to **Settings → General → Auto-review → Allow automatically** and add a narrow rule: *"Allow the ClipCart callback probe routine to send one HTTP POST to https://<your-tunnel-host>/probe/ with the Authorization header from its trigger body."*
   - **Why:** approvals for routine-started work expire after about 10 minutes and the action doesn't run.
   - **Caveat:** Allow rules apply only when the automated review finds no other reason to stop. A community report says the review still weighs recent typed chat, so also type in the Bot chat: *"I'm about to trigger the ClipCart callback probe; it should POST the nonce back to my tunnel."* That part is undocumented.
5. **Run the probe once** from the repo root, in the same shell, with no secrets in files. It makes **one webhook call**, which spends Bot usage, and waits up to 10 minutes:
   ```
   GROK_BOT_WEBHOOK_URL='<POST to>' GROK_BOT_WEBHOOK_KEY='<key>' PROBE_PUBLIC_BASE_URL='https://<tunnel-host>' \
     python3 scripts/experiments/grokbot_bridge_probe.py
   ```
   It prints `verdict.triggerProven`, `payloadAccessProven` and `callbackProven`. The webhook's 200 response only means a run started. **It never contains results.**

**Reading the verdict:**
- **All three true:** the unattended callback works. Point the dormant provider below at the same routine design.
- **Trigger proven, no callback:** check the Bot chat for an "Expired" approval card. If you approve it in time and the probe then passes, the path works only with a person in the loop, not unattended.
- **Trigger fails:** re-copy the current key, and check the routine isn't paused.

**If the callback can't be made reliable,** bring results in through the **labelled manual import** (`POST /api/research-jobs/{id}/import`, contract v2). It also works on failed and expired jobs.

## The `grok_bot` provider

The provider is implemented (`app/research/grokbot.py`) and tested against a simulated Bot. A real research run is pending (see Status). It is **not selected by default**: `RESEARCH_PROVIDER` defaults to `fixture`, and `FEATURE_AGENT_RESEARCH` is off. To try it after the probe passes, set these in the process environment only:

```
FEATURE_AGENT_RESEARCH=1 RESEARCH_PROVIDER=grok_bot \
GROK_BOT_WEBHOOK_URL=<research routine POST to> GROK_BOT_WEBHOOK_KEY=<its key> \
CLIPCART_PUBLIC_BASE_URL=https://<tunnel-host-pointing-at-:8000>   # tunnel to the ClipCart server, not the probe port
```

1. **Dispatch.** The provider POSTs `{jobId, expiresAt, garment (with a signed cropUrl, never an asset id), preferences, styleHints, instructions, callbackUrl, callbackAuthorization, resultSchema}` with `Authorization: Bearer <key>`.
   - **Timeout:** 8 s, with one retry on a network error only.
   - **Failure:** any non-200 answer fails the job with `dispatch_failed`. The manual import still works afterwards.
2. **Callback.** `POST /api/research-jobs/{id}/results` with `Authorization: Bearer <one-time token>`. Only the token's SHA-256 is stored, and it's compared in constant time. The body is capped at 256 KB. The results go through the same validation as every submission and are labelled `source: "agent"`. The token is used up on acceptance. A late callback after expiry is refused with 409.
3. **Crop link.** `GET /api/research-crops/{signed}` serves the crop as an HMAC-signed link that expires with the job (15 min) and sends `no-store`. Set `RESEARCH_URL_SECRET` so links survive a restart; otherwise each server start makes a new secret.

**Research routine instruction**, for a second routine named "ClipCart research". Its body includes the same text as `instructions`:
> When triggered, follow body.instructions exactly. Research only the item in body.garment for body.preferences, using several independent retailers and resale marketplaces, and report only pages you opened. Send exactly one HTTP POST to body.callbackUrl with header Authorization set to body.callbackAuthorization and a JSON body matching body.resultSchema. Do nothing else.

That routine needs its own narrow Allow rule, for POST to `https://<tunnel-host>/api/research-jobs/`. **No retailer coverage is claimed** until a real run's results have been retrieved and checked.

Original findings (2026-10-17), kept for reference. The callback step in the table below has since been proven by the probe; unattended operation and real research are still to be confirmed (see Status).

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
