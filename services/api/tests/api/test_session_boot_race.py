"""Concurrent POST /api/sessions/resume (reported on #26: a fresh browser could end up uploading to a session its
owner cookie doesn't own, and the upload 404'd).

Cookie-less requests can't be told apart, so two of them mint two owners; the browser keeps one cookie. The server
guarantees what the web client's recovery relies on: one session per owner however many resumes race, and a resume
with the surviving cookie always lands on a session that accepts the upload.
"""

import threading

from api.conftest import H, jpeg_bytes, new_client


def _race(clients):
    barrier = threading.Barrier(len(clients))
    out = [None] * len(clients)

    def go(i, c):
        barrier.wait()
        out[i] = c.post("/api/sessions/resume", headers=H)

    threads = [threading.Thread(target=go, args=(i, c)) for i, c in enumerate(clients)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(10)
    return out


def _upload(c, s):
    return c.post(f"/api/media/uploads?sessionId={s['id']}&expectedRevision={s['revision']}", content=jpeg_bytes(), headers=H)


def test_concurrent_resumes_for_one_owner_share_one_session(app_factory, monkeypatch):
    import time

    import app.routes.api as api_routes

    real_create = api_routes.create_session

    def slow_create(db, owner):  # widen the find-then-create window so an unguarded resume reliably races
        time.sleep(0.05)
        return real_create(db, owner)

    monkeypatch.setattr(api_routes, "create_session", slow_create)
    app = app_factory()
    first = new_client(app)
    first.post("/api/sessions/resume", headers=H)  # sets the owner cookie
    st = app.state.clipcart
    st.db.sessions.delete_many({})  # cookie kept, sessions gone (e.g. local store after a restart)
    tabs = [new_client(app) for _ in range(6)]
    for t in tabs:
        t.cookies.update(first.cookies)
    out = _race(tabs)
    assert all(r.status_code == 200 for r in out)
    assert len({r.json()["session"]["id"] for r in out}) == 1
    assert st.db.sessions.count_documents({}) == 1
    assert _upload(tabs[0], out[-1].json()["session"]).status_code == 200


def test_cookieless_race_recovers_by_resuming_with_the_kept_cookie(app_factory):
    app = app_factory()
    a, b = new_client(app), new_client(app)  # two tabs of one fresh browser, before either has a cookie
    ra, rb = _race([a, b])
    sa, sb = ra.json()["session"], rb.json()["session"]
    assert sa["id"] != sb["id"] and a.cookies.get("cc_owner") != b.cookies.get("cc_owner")
    # The browser keeps the last cookie (b's). Tab a still shows sa: its upload is refused, never stored elsewhere.
    tab_a = new_client(app)
    tab_a.cookies.set("cc_owner", b.cookies.get("cc_owner"))
    refused = _upload(tab_a, sa)
    assert refused.status_code == 404 and refused.json()["code"] == "not_found"
    # Recovery (web: adoptCurrentSession): resume with the kept cookie lands on b's session, which takes the upload.
    again = tab_a.post("/api/sessions/resume", headers=H).json()["session"]
    assert again["id"] == sb["id"] and again["mediaId"] is None
    assert _upload(tab_a, again).status_code == 200
    assert tab_a.cookies.get("cc_owner") == b.cookies.get("cc_owner")  # resume with a cookie never mints a new one
