"""Offline self-test of scripts/experiments/grokbot_bridge_probe.py against a fake Bot (no network)."""

import json
import os
import socket
import subprocess
import sys
import threading
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[4] / "scripts" / "experiments" / "grokbot_bridge_probe.py"


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def fake_bot(behavior):
    """Webhook endpoint: checks the bearer key, answers 200, then (maybe) calls back like a Bot would."""
    seen = {}

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_POST(self):  # noqa: N802
            seen["auth"] = self.headers.get("Authorization")
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            self.send_response(200 if seen["auth"] == "Bearer test-key" else 401)
            self.end_headers()
            self.wfile.write(b'{"status":"accepted"}')
            if behavior == "callback" and seen["auth"] == "Bearer test-key":
                def cb():
                    req = urllib.request.Request(body["callbackUrl"], method="POST",
                                                 data=json.dumps({"probeId": body["probeId"], "nonce": body["nonce"], "echo": "pong"}).encode(),
                                                 headers={"Authorization": body["callbackAuthorization"], "Content-Type": "application/json"})
                    urllib.request.urlopen(req, timeout=5).read()
                threading.Timer(0.3, cb).start()

    port = free_port()
    srv = ThreadingHTTPServer(("127.0.0.1", port), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, port, seen


def run_probe(bot_port, key="test-key", wait="5"):
    probe_port = free_port()
    env = {**os.environ, "GROK_BOT_WEBHOOK_URL": f"http://127.0.0.1:{bot_port}/hook", "GROK_BOT_WEBHOOK_KEY": key,
           "PROBE_PUBLIC_BASE_URL": f"http://127.0.0.1:{probe_port}", "PROBE_PORT": str(probe_port), "PROBE_WAIT_S": wait,
           "PROBE_INSECURE_LOCAL_TEST": "1"}
    p = subprocess.run([sys.executable, str(SCRIPT)], env=env, capture_output=True, text=True, timeout=30)
    return p.returncode, json.loads(p.stdout), p.stdout


def test_full_bridge_proven_with_fake_bot():
    srv, port, seen = fake_bot("callback")
    code, rep, out = run_probe(port)
    srv.shutdown()
    assert code == 0 and rep["verdict"] == {"triggerProven": True, "payloadAccessProven": True, "callbackProven": True}
    assert seen["auth"] == "Bearer test-key" and "test-key" not in out  # key sent, never printed


def test_trigger_only_when_bot_never_calls_back():
    srv, port, _ = fake_bot("silent")
    code, rep, _ = run_probe(port, wait="1")
    srv.shutdown()
    assert code == 1 and rep["verdict"]["triggerProven"] and not rep["verdict"]["callbackProven"]
    assert rep["trigger"]["responseHasAnswer"] is False  # the webhook response never carries the Bot's answer


def test_wrong_key_means_no_run():
    srv, port, _ = fake_bot("callback")
    code, rep, _ = run_probe(port, key="wrong", wait="1")
    srv.shutdown()
    assert code == 1 and rep["trigger"]["status"] == 401 and not any(rep["verdict"].values())
