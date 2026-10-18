"""Find-in-video: normalize query + API path with fixture perception."""

from __future__ import annotations

from app.jobs.find_in_media import normalize_find_query

from .conftest import H, bootstrap, new_client, wait


def test_normalize_keeps_descriptive_phrase():
    assert normalize_find_query("find me the tall monstera in the speckled ceramic pot") == (
        "tall monstera in the speckled ceramic pot"
    )
    assert normalize_find_query("Look for that abstract oil painting with gold frame") == (
        "abstract oil painting with gold frame"
    )
    q = normalize_find_query("find the distressed light-wash denim trucker with copper rivets")
    assert "denim" in q and "rivets" in q and len(q.split()) >= 5


def test_find_in_media_without_perceptron_is_honest(app_factory):
    c = new_client(app_factory())
    s, _g, _a = bootstrap(c)
    r = c.post(
        f"/api/sessions/{s['id']}/find-in-media",
        headers=H,
        json={"text": "find me the plant by the window", "expectedRevision": s["revision"], "startSearch": False},
    )
    assert r.status_code == 503
    assert r.json()["code"] == "perception_unavailable"


def test_find_in_media_with_fixture_detects_or_reports_not_found(app_factory, monkeypatch):
    monkeypatch.setenv("PERCEPTION_PROVIDER", "fixture")
    c = new_client(app_factory())
    s = c.post("/api/sessions", headers=H).json()["session"]
    from .conftest import jpeg_bytes

    v = c.post(
        f"/api/media/uploads?sessionId={s['id']}&expectedRevision={s['revision']}",
        content=jpeg_bytes(),
        headers=H,
    ).json()
    s = v["session"]
    wait(lambda: c.get(f"/api/analysis/{s['analysisId']}").json(), lambda a: a["status"] not in ("queued", "running"))
    s = c.get(f"/api/sessions/{s['id']}").json()["session"]
    r = c.post(
        f"/api/sessions/{s['id']}/find-in-media",
        headers=H,
        json={
            "text": "find me the tall green plant in a ceramic pot",
            "expectedRevision": s["revision"],
            "startSearch": False,
        },
    )
    # Fixture frames detect clothing labels; open-vocab still returns boxes for any class string.
    assert r.status_code in (200, 404)
    if r.status_code == 200:
        body = r.json()
        assert body["applied"] is True
        assert body["find"]["garmentId"]
        g = next(x for x in body["garments"] if x["id"] == body["find"]["garmentId"])
        assert g["category"] == "other"
        assert g.get("userDescription")
        assert len(g["userDescription"].split()) >= 2


def test_rule_queries_other_keeps_full_description():
    from app.contracts import Preferences
    from app.shopping.rules import GarmentProfile
    from app.shopping.workers import rule_queries

    prof = GarmentProfile(
        category="other",
        colors=["green", "cream"],
        cut=["potted", "tall"],
        details=[
            "tall monstera deliciosa in speckled cream ceramic pot with trailing aerial roots",
            "fenestrated leaves",
            "glossy surface",
        ],
        description="tall monstera deliciosa in speckled cream ceramic pot with trailing aerial roots",
    )
    qs = rule_queries("exact", prof, Preferences())
    assert qs
    assert any("monstera" in q for q in qs)
    assert not any(q.strip() in {"green plant", "plant"} for q in qs)
