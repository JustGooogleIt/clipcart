"""Smallest end-to-end probe of a Grok Bot webhook routine -> callback bridge.

Proves three things or reports which one failed:
  1. trigger:  POST to the routine's webhook URL returns 200 (run started).
  2. payload:  the Bot read our JSON body (it must echo the nonce we sent).
  3. callback: the Bot made an authenticated HTTPS POST back to us, unattended.

Setup (once, by a person, in the Cursor desktop app >= 0.53; see docs/grok-bot-bridge.md):
  - Ask your Bot to create a routine with a webhook trigger and this instruction:
      "When triggered, read the JSON body. Send an HTTP POST to body.callbackUrl with header
       Authorization set to body.callbackAuthorization and JSON body
       {"probeId": body.probeId, "nonce": body.nonce, "echo": "pong"}. Do nothing else."
  - Add an Allow rule for POST requests to your tunnel host so the unattended call is not held for approval.
  - Expose this machine's PROBE_PORT over public HTTPS (any tunnel) as PROBE_PUBLIC_BASE_URL.

Run:
  GROK_BOT_WEBHOOK_URL=... GROK_BOT_WEBHOOK_KEY=... PROBE_PUBLIC_BASE_URL=https://<tunnel> \
    python3 scripts/experiments/grokbot_bridge_probe.py

Prints a JSON report. Never prints the webhook key or the callback token. One webhook call, no retries.
"""

from __future__ import annotations

import hmac
import json
import os
import secrets
import sys
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

REQUIRED = ("GROK_BOT_WEBHOOK_URL", "GROK_BOT_WEBHOOK_KEY", "PROBE_PUBLIC_BASE_URL")


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


def main() -> int:
    missing = [k for k in REQUIRED if not os.getenv(k)]
    if missing:
        print(json.dumps({"ran": False, "missing": missing}, indent=2))
        return 2
    url, key = os.environ["GROK_BOT_WEBHOOK_URL"], os.environ["GROK_BOT_WEBHOOK_KEY"]
    base = os.environ["PROBE_PUBLIC_BASE_URL"].rstrip("/")
    port = int(os.getenv("PROBE_PORT", "8765"))
    wait_s = int(os.getenv("PROBE_WAIT_S", "600"))
    local_test = os.getenv("PROBE_INSECURE_LOCAL_TEST") == "1"  # offline self-test only: allows http://127.0.0.1
    if not local_test and not (url.startswith("https://") and base.startswith("https://")):
        print(json.dumps({"ran": False, "error": "webhook URL and public base URL must be https"}))
        return 2

    probe_id = "probe_" + secrets.token_hex(6)
    nonce = secrets.token_urlsafe(16)
    cb_token = secrets.token_urlsafe(24)  # one-time; valid only for this probe
    report: dict = {"ran": True, "probeId": probe_id, "trigger": None, "callback": None}
    got = threading.Event()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):  # keep tokens out of logs
            pass

        def do_POST(self):  # noqa: N802
            ok_path = self.path == f"/probe/{probe_id}"
            auth_ok = hmac.compare_digest(self.headers.get("Authorization", ""), f"Bearer {cb_token}")
            length = min(int(self.headers.get("Content-Length") or 0), 65536)
            raw = self.rfile.read(length)
            try:
                body = json.loads(raw or b"{}")
            except ValueError:
                body = {}
            accepted = ok_path and auth_ok and report["callback"] is None
            if accepted:
                report["callback"] = {
                    "receivedAfterS": round(time.monotonic() - t_sent, 1),
                    "authOk": True,
                    "nonceEchoed": hmac.compare_digest(str(body.get("nonce", "")), nonce),
                    "probeIdEchoed": body.get("probeId") == probe_id,
                    "echo": body.get("echo"),
                    "extraKeys": sorted(set(body) - {"probeId", "nonce", "echo"})[:10],
                }
                got.set()
            else:
                report.setdefault("rejectedCallbacks", []).append({"pathOk": ok_path, "authOk": auth_ok})
            self.send_response(200 if accepted else 401)
            self.end_headers()

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()

    payload = {
        "type": "clipcart.bridge_probe",
        "probeId": probe_id,
        "nonce": nonce,
        "callbackUrl": f"{base}/probe/{probe_id}",
        "callbackAuthorization": f"Bearer {cb_token}",
    }
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), method="POST",
                                 headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    t_sent = time.monotonic()
    try:
        with urllib.request.build_opener(_NoRedirect).open(req, timeout=8) as r:
            body = r.read(2048)
            report["trigger"] = {"status": r.status, "runStarted": r.status == 200,
                                 "responseHasAnswer": "pong" in body.decode("utf-8", "replace")}
    except urllib.error.HTTPError as e:
        report["trigger"] = {"status": e.code, "runStarted": False}
    except (urllib.error.URLError, TimeoutError) as e:
        report["trigger"] = {"status": None, "runStarted": False, "error": type(e).__name__}

    if report["trigger"]["runStarted"]:
        got.wait(wait_s)
    server.shutdown()
    report["verdict"] = {
        "triggerProven": bool(report["trigger"]["runStarted"]),
        "payloadAccessProven": bool(report["callback"] and report["callback"]["nonceEchoed"]),
        "callbackProven": bool(report["callback"] and report["callback"]["authOk"]),
    }
    print(json.dumps(report, indent=2))
    return 0 if all(report["verdict"].values()) else 1


if __name__ == "__main__":
    sys.exit(main())
