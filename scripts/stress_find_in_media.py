#!/usr/bin/env python3
"""Live stress harness for find-in-media (needs API on :8000 + Perceptron)."""

from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request
from http.cookiejar import CookieJar
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = "http://127.0.0.1:8000"
H = {"Content-Type": "application/json", "X-ClipCart-Request": "1"}
_JAR = CookieJar()
_OPENER = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(_JAR))


def req(method: str, path: str, body: dict | None = None, data: bytes | None = None, ctype: str | None = None):
    headers = dict(H)
    if ctype:
        headers["Content-Type"] = ctype
    elif data is not None:
        headers["Content-Type"] = "application/octet-stream"
    payload = data if data is not None else (None if body is None else json.dumps(body).encode())
    r = urllib.request.Request(f"{BASE}{path}", data=payload, headers=headers, method=method)
    try:
        with _OPENER.open(r, timeout=180) as resp:
            raw = resp.read()
            return resp.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw) if raw else {"message": str(e)}
        except Exception:
            return e.code, {"message": raw.decode("utf-8", "replace")[:300]}


def wait_analysis(aid: str, timeout=120):
    t0 = time.time()
    while time.time() - t0 < timeout:
        st, a = req("GET", f"/api/analysis/{aid}")
        if st == 200 and a.get("status") not in ("queued", "running"):
            return a
        time.sleep(0.5)
    raise SystemExit("analysis timeout")


def main() -> int:
    st, health = req("GET", "/api/health")
    print("health", health.get("api"), "perc", health.get("providers", {}).get("perceptron", {}).get("mode"))
    yt_on = bool((health.get("features") or {}).get("youtubeDownload"))
    st, sess = req("POST", "/api/sessions", {})
    s = sess["session"]
    print("session", s["id"], "youtube", yt_on)

    if yt_on:
        st, up = req(
            "POST",
            f"/api/sessions/{s['id']}/youtube-analyze",
            {
                "youtubeUrl": "https://www.youtube.com/shorts/zf6CmntK3BY",
                "expectedRevision": s["revision"],
            },
        )
        if st >= 400:
            print("youtube fail", st, up)
            return 1
        s = up["session"]
    else:
        clip = ROOT / "downloads" / "fit-checks" / "fc01_zf6CmntK3BY.mp4"
        if not clip.exists():
            print("missing", clip)
            return 2
        # Stream file without holding an extra copy; smaller clips preferred.
        data = clip.read_bytes()
        st, up = req(
            "POST",
            f"/api/media/uploads?sessionId={s['id']}&expectedRevision={s['revision']}",
            data=data,
            ctype="application/octet-stream",
        )
        if st >= 400:
            print("upload fail", st, up)
            return 1
        s = up["session"]

    a = wait_analysis(s["analysisId"])
    print("analysis", a.get("status"), "frames", len(a.get("frames") or []), "garments", len(a.get("garmentIds") or []))
    st, view = req("GET", f"/api/sessions/{s['id']}")
    s = view["session"]
    rev = s["revision"]

    cases = [
        ("vague", "thing"),
        ("short", "find the plant"),
        ("short_ok", "find the jacket"),
        ("rich_missing", "find me the tall monstera in a speckled ceramic pot by the window"),
        ("apparel_rich", "find me the blue denim trucker jacket with chest pockets"),
        ("apparel_short", "find the jacket"),
        ("painting", "find me the abstract painting with a gold ornate frame on the wall behind him"),
        ("bag", "find me the bag he's carrying"),
        ("repeat", "find me the blue denim trucker jacket with chest pockets"),
    ]
    results = []
    for name, text in cases:
        t0 = time.time()
        st, body = req(
            "POST",
            f"/api/sessions/{s['id']}/find-in-media",
            {"text": text, "expectedRevision": rev, "startSearch": False},
        )
        ms = int((time.time() - t0) * 1000)
        if st == 200:
            rev = body["session"]["revision"]
            g = next(x for x in body["garments"] if x["id"] == body["find"]["garmentId"])
            desc = g.get("userDescription") or ""
            row = {
                "case": name,
                "status": st,
                "ms": ms,
                "label": g.get("label"),
                "category": g.get("category"),
                "desc_words": len(desc.split()),
                "desc": desc[:160],
                "reply": (body.get("reply") or "")[:120],
            }
        else:
            row = {
                "case": name,
                "status": st,
                "ms": ms,
                "code": body.get("code"),
                "message": (body.get("message") or "")[:160],
            }
            # keep revision on 409
            if st == 409:
                st2, view = req("GET", f"/api/sessions/{s['id']}")
                rev = view["session"]["revision"]
        results.append(row)
        print(json.dumps(row, ensure_ascii=False))

    # One find that starts search
    st, body = req(
        "POST",
        f"/api/sessions/{s['id']}/find-in-media",
        {
            "text": "find me the denim jacket",
            "expectedRevision": rev,
            "startSearch": True,
        },
    )
    print("search_start", st, "searchId", body.get("searchId"), "summary_pending")
    if body.get("searchId"):
        sid = body["searchId"]
        for _ in range(60):
            st, sv = req("GET", f"/api/searches/{sid}")
            job = sv.get("job") or {}
            if job.get("status") not in ("queued", "running"):
                titles = [r.get("listing", {}).get("title") for r in (sv.get("results") or [])][:5]
                print("search_done", job.get("status"), job.get("summary"), titles)
                break
            time.sleep(0.5)

    out = ROOT / "downloads" / "fit-checks" / "eval" / "find_stress.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"results": results}, indent=2))
    print("wrote", out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
