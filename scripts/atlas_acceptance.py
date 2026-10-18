"""Atlas acceptance: connectivity, indexes, owner isolation and persistence through a server restart.

    services/api/.venv/bin/python scripts/atlas_acceptance.py            # needs MONGODB_URI (Atlas) in .env
    services/api/.venv/bin/python scripts/atlas_acceptance.py --rehearsal  # any MongoDB; reported as NOT Atlas

Starts its own API server on a free localhost port. That server uses fixture perception and a fixture catalog,
so no paid provider calls are made. FEATURE_STYLE_MEMORY=1 is set only in that child process, and .env is not
modified. Two separate owners act through the HTTP API. Their documents are deleted afterwards. The URI, user
name and password are never printed.
"""

from __future__ import annotations

import argparse
import io
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
API = ROOT / "services" / "api"
sys.path.insert(0, str(API))

from app.config import load_settings  # noqa: E402  (loads .env without printing it)

H = {"X-ClipCart-Request": "1"}
results: list[dict] = []


def step(name: str, ok: bool, **detail) -> bool:
    results.append({"step": name, "ok": bool(ok), **detail})
    print(f"{'PASS' if ok else 'FAIL'} {name}" + (f" {json.dumps(detail, default=str)}" if detail else ""), flush=True)
    return bool(ok)


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Server:
    def __init__(self, settings, port: int, media_root: str):
        self.port, self.proc = port, None
        self.env = {
            "HOME": os.environ.get("HOME", ""), "PATH": os.environ.get("PATH", ""),
            "CLIPCART_SKIP_DOTENV": "1", "MONGODB_URI": settings.mongodb_uri, "MONGODB_DB": settings.mongodb_db,
            "PERCEPTION_PROVIDER": "fixture", "CATALOG_PROVIDER": "fixture", "FEATURE_STYLE_MEMORY": "1",
            "CLIPCART_MEDIA_ROOT": media_root, "CLIPCART_WEB_DIST": str(Path(media_root) / "no-web"),
        }
        if os.environ.get("SSL_CERT_FILE"):
            self.env["SSL_CERT_FILE"] = os.environ["SSL_CERT_FILE"]

    def start(self, httpx) -> None:
        self.proc = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(self.port)],
            cwd=API, env=self.env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
        )
        deadline = time.time() + 45
        while time.time() < deadline:
            if self.proc.poll() is not None:
                err = (self.proc.stderr.read() or b"").decode(errors="replace")
                raise RuntimeError("server exited during startup: " + err.strip().splitlines()[-1][:300] if err else "")
            try:
                if httpx.get(f"http://127.0.0.1:{self.port}/api/health", timeout=2).status_code == 200:
                    return
            except httpx.HTTPError:
                pass
            time.sleep(0.5)
        raise RuntimeError("server did not become healthy in 45 s")

    def stop(self) -> None:
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=15)
            except subprocess.TimeoutExpired:
                self.proc.kill()


def jpeg() -> bytes:
    from PIL import Image, ImageDraw

    im = Image.new("RGB", (400, 300), (235, 232, 226))
    ImageDraw.Draw(im).rectangle((100, 60, 300, 260), fill=(15, 15, 15))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=90)
    return buf.getvalue()


def expected_indexes() -> dict[str, set]:
    import mongomock

    from app.storage.db import ensure_indexes

    db = mongomock.MongoClient()["x"]
    ensure_indexes(db)
    return {c: {tuple(v["key"]) for v in db[c].index_information().values()} for c in db.list_collection_names()}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rehearsal", action="store_true", help="allow a non-Atlas MongoDB; the result is NOT Atlas verification")
    ap.add_argument("--keep", action="store_true", help="keep the test owners' documents (default: delete them)")
    a = ap.parse_args()
    import httpx
    import pymongo

    from app.routes.deps import OWNER_COOKIE, owner_from_token
    from app.storage.db import COLLECTIONS

    s = load_settings()
    if not s.mongodb_uri:
        print(json.dumps({"verdict": "skipped", "missing": "MONGODB_URI"}))
        return 2
    if s.db_mode != "atlas" and not a.rehearsal:
        print(json.dumps({"verdict": "refused", "reason": "MONGODB_URI is not an Atlas (mongodb.net) URI; use --rehearsal"}))
        return 2
    label = "atlas" if s.db_mode == "atlas" else "REHEARSAL (not Atlas)"
    print(f"target: {label}, database {s.mongodb_db}", flush=True)

    port = free_port()
    media = tempfile.mkdtemp(prefix="cc-atlas-accept-")
    srv = Server(s, port, media)
    base = f"http://127.0.0.1:{port}"
    owners: list[str] = []
    try:
        srv.start(httpx)
        a_cli, b_cli = httpx.Client(base_url=base, timeout=30), httpx.Client(base_url=base, timeout=30)
        h = a_cli.get("/api/health").json()
        step("health reports the expected database mode", h["database"]["ok"] and h["database"]["mode"] == s.db_mode
             and h["database"]["note"] is None, mode=h["database"]["mode"], db_ok=h["database"]["ok"])

        client = pymongo.MongoClient(s.mongodb_uri, serverSelectionTimeoutMS=10000, appname="clipcart-acceptance")
        db = client[s.mongodb_db]
        want = expected_indexes()
        missing = {c: sorted(map(str, keys - {tuple(v["key"]) for v in db[c].index_information().values()}))
                   for c, keys in want.items()}
        missing = {c: m for c, m in missing.items() if m}
        step("app indexes exist on the server", not missing, collections=len(want), missing=missing)

        sa = a_cli.post("/api/sessions", headers=H).json()["session"]
        sb = b_cli.post("/api/sessions", headers=H).json()["session"]
        owners = [owner_from_token(c.cookies[OWNER_COOKIE]) for c in (a_cli, b_cli)]
        step("two owners have distinct sessions", sa["id"] != sb["id"] and owners[0] != owners[1])
        sa = a_cli.patch(f"/api/sessions/{sa['id']}", headers=H, json={
            "expectedRevision": sa["revision"], "preferences": {"maxItemPriceMinor": 9000, "colors": ["black"]}}).json()["session"]
        up = a_cli.post(f"/api/media/uploads?sessionId={sa['id']}&expectedRevision={sa['revision']}",
                        content=jpeg(), headers={**H, "Content-Type": "image/jpeg"})
        step("owner A uploads a frame (fixture detection)", up.status_code == 200, status=up.status_code)
        sa = up.json()["session"]
        for _ in range(60):
            an = a_cli.get(f"/api/analysis/{sa['analysisId']}").json()
            if an["status"] not in ("queued", "running"):
                break
            time.sleep(0.5)
        step("analysis finished", an["status"] not in ("queued", "running"), status=an["status"])
        mem = a_cli.post("/api/style/memories", headers=H, json={"kind": "color_like", "value": "brown", "source": "style_panel"})
        step("owner A saves a style memory", mem.status_code == 201, status=mem.status_code)
        mem_id = mem.json()["memory"]["id"]

        def isolation(tag: str) -> None:
            r = [b_cli.get(f"/api/sessions/{sa['id']}").status_code, b_cli.get(f"/api/analysis/{sa['analysisId']}").status_code]
            theirs = b_cli.get("/api/style/memories?status=all").json()["memories"]
            step(f"owner isolation {tag}", r == [404, 404] and theirs == [], b_sees_a=r, b_memories=len(theirs))

        isolation("before restart")
        srv.stop()
        srv.start(httpx)
        step("server restarted", True)
        got = a_cli.get(f"/api/sessions/{sa['id']}").json()["session"]
        step("session and preferences persisted", got["revision"] == sa["revision"]
             and got["preferences"]["maxItemPriceMinor"] == 9000 and got["mediaId"] == sa["mediaId"])
        latest = a_cli.get("/api/sessions/latest").json()
        step("latest session restores for owner A", latest["session"]["id"] == sa["id"] and latest["media"]["id"] == sa["mediaId"])
        an2 = a_cli.get(f"/api/analysis/{sa['analysisId']}").json()
        step("analysis persisted", an2["status"] == an["status"] and len(an2.get("frames") or []) == len(an.get("frames") or []))
        mems = a_cli.get("/api/style/memories").json()["memories"]
        step("style memory persisted", [m["id"] for m in mems] == [mem_id])
        isolation("after restart")
        step("owner B's own session persisted", b_cli.get(f"/api/sessions/{sb['id']}").status_code == 200)
    except Exception as exc:  # noqa: BLE001
        step("acceptance run", False, error=f"{type(exc).__name__}: {str(exc)[:300]}")
    finally:
        srv.stop()
        if owners and not a.keep:
            try:
                client = pymongo.MongoClient(s.mongodb_uri, serverSelectionTimeoutMS=10000)
                db = client[s.mongodb_db]
                deleted = {c: db[c].delete_many({"ownerId": {"$in": owners}}).deleted_count for c in COLLECTIONS}
                left = sum(db[c].count_documents({"ownerId": {"$in": owners}}) for c in COLLECTIONS)
                step("test documents deleted", left == 0, deleted=sum(deleted.values()), remaining=left)
            except Exception as exc:  # noqa: BLE001
                step("test documents deleted", False, error=type(exc).__name__)
    ok = all(r["ok"] for r in results)
    print(json.dumps({"target": label, "verdict": "pass" if ok else "fail",
                      "passed": sum(r["ok"] for r in results), "total": len(results)}))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
