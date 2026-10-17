import json

import pytest
from api.conftest import H, new_client, wait
from shopping.fakes import FakeCatalog, item

import app.youtube.service as yts
from app.providers.gemini.client import GeminiError, GeminiReply
from app.youtube.oembed import OEmbedResult

URL = "https://youtu.be/jNQXAC9IVRw"
ONE_JACKET = {"garments": [{"category": "jacket", "description": "Dark zip-up bomber jacket with ribbed collar",
                            "colors": ["black"], "timestamps": ["00:04", "00:11"], "person_label": "person_1"}]}


class FakeGemini:
    calls = 0

    def __init__(self, result):
        self.result = result

    def analyze_youtube(self, url, prompt, schema, **kw):
        FakeGemini.calls += 1
        if isinstance(self.result, Exception):
            raise self.result
        return GeminiReply(json.dumps(self.result), "int_fake", "gemini-test", {"total_tokens": 1}, 5)


@pytest.fixture
def yt_app(app_factory, monkeypatch):
    def make(result=ONE_JACKET, oembed=OEmbedResult("ok", "Me at the zoo", "jawed", 200), flag=True, key=True):
        if flag:
            monkeypatch.setenv("FEATURE_YOUTUBE_GEMINI", "1")
        if key:
            monkeypatch.setenv("GEMINI_API_KEY", "test-key")
        yts.clear_cache()
        FakeGemini.calls = 0
        monkeypatch.setattr(yts, "probe", lambda url: oembed)
        monkeypatch.setattr(yts, "_default_client_factory", lambda s: (lambda: FakeGemini(result)))
        return new_client(app_factory(FakeCatalog([item("a", "Black Nylon Bomber Jacket", 70),
                                                   item("b", "Black Satin Bomber Jacket", 95)],
                                                  {s: {"sizes": ["M"], "hidden": 1, "carrying": 2} for s in "ab"})))
    return make


def start(c, url=URL, **extra):
    s = c.post("/api/sessions", headers=H).json()["session"]
    r = c.post(f"/api/sessions/{s['id']}/youtube-analyses", headers=H, json={"url": url, **extra})
    return s, r


def finished(c, aid):
    return wait(lambda: c.get(f"/api/youtube-analyses/{aid}").json()["analysis"], lambda a: a["status"] not in ("queued", "running"))


def test_flag_off_and_missing_key(app_factory, yt_app, monkeypatch):
    c = new_client(app_factory())
    _, r = start(c)
    assert r.status_code == 404 and r.json()["code"] == "feature_disabled"
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    c = yt_app(key=False)
    _, r = start(c)
    assert r.status_code == 503 and r.json()["code"] == "provider_not_configured"


@pytest.mark.parametrize("url,status,code", [
    ("https://www.youtube.com/playlist?list=PL1", 422, "unsupported_url"),
    ("https://vimeo.com/1", 422, "unsupported_url"),
    ("https://www.youtube.com/watch?v=bad", 400, "invalid_url"),
])
def test_bad_urls_rejected_before_any_call(yt_app, url, status, code):
    c = yt_app()
    _, r = start(c, url=url)
    assert r.status_code == status and r.json()["code"] == code and FakeGemini.calls == 0


def test_interval_bounds(yt_app):
    c = yt_app()
    _, r = start(c, startS=0, endS=900)
    assert r.status_code == 422 and r.json()["code"] == "invalid_interval"


def test_completed_select_and_search_are_labeled_gemini_youtube(yt_app):
    c = yt_app()
    s, r = start(c)
    a = finished(c, r.json()["analysis"]["id"])
    assert a["status"] == "completed" and a["source"] == "gemini_youtube" and a["title"] == "Me at the zoo"
    g = a["garments"][0]
    assert g["source"] == "gemini_youtube" and [t["label"] for t in g["timestamps"]] == ["00:04", "00:11"]
    assert not ({"box01", "cropAssetId", "frameAssetId"} & set(g))  # never boxes or crops
    sess = c.get(f"/api/sessions/{s['id']}").json()["session"]
    sel = c.post(f"/api/youtube-analyses/{a['id']}/garments/{g['id']}/select", headers=H,
                 json={"expectedRevision": sess["revision"]}).json()
    assert sel["session"]["selectedGarmentId"] == sel["garmentId"]
    assert sel["youtube"]["selectedGarment"]["representativeCropId"] is None
    assert sel["garments"] == []  # Perceptron/manual garment list is untouched
    r = c.post(f"/api/sessions/{s['id']}/searches", headers=H, json={"expectedRevision": sel["session"]["revision"]}).json()
    out = wait(lambda: c.get(f"/api/searches/{r['searchId']}").json(), lambda o: o["job"]["status"] not in ("queued", "running"))
    assert out["job"]["garmentSource"] == "gemini_youtube" and out["results"]
    for x in out["results"]:
        assert x["recommendation"]["garmentSource"] == "gemini_youtube"
        assert any("YouTube" in w for w in x["recommendation"]["warnings"])
    ev = " ".join(e["summary"] for e in out["events"])
    assert "black" in ev and "bomber" in ev  # the Gemini description drove the catalog query


def test_no_garments(yt_app):
    c = yt_app(result={"garments": []})
    _, r = start(c)
    a = finished(c, r.json()["analysis"]["id"])
    assert a["status"] == "no_garments" and a["garments"] == [] and "didn't find" in a["message"]


def test_not_found_skips_gemini(yt_app):
    c = yt_app(oembed=OEmbedResult("not_found", http_status=404))
    _, r = start(c)
    a = finished(c, r.json()["analysis"]["id"])
    assert a["status"] == "not_found" and FakeGemini.calls == 0


def test_private_and_unlisted_are_reported_honestly(yt_app):
    err = GeminiError("video_inaccessible", "The video is not public", http_status=400)
    c = yt_app(result=err, oembed=OEmbedResult("restricted", http_status=401))
    _, r = start(c)
    a = finished(c, r.json()["analysis"]["id"])
    assert a["status"] == "private_or_restricted" and "private" in a["message"]
    c = yt_app(result=err, oembed=OEmbedResult("ok", "Some unlisted video", "x", 200))  # oEmbed works for unlisted
    _, r = start(c)
    a = finished(c, r.json()["analysis"]["id"])
    assert a["status"] == "private_or_restricted" and a["message"].startswith("YouTube lists this video")


def test_restricted_embed_but_public_video_still_analyzed(yt_app):
    c = yt_app(oembed=OEmbedResult("restricted", http_status=401))
    _, r = start(c)
    assert finished(c, r.json()["analysis"]["id"])["status"] == "completed"


@pytest.mark.parametrize("err,code", [
    (GeminiError("auth_error", "bad key"), "auth_error"),
    (GeminiError("rate_limited", "quota", retryable=True), "rate_limited"),
    (GeminiError("timeout", "slow", retryable=True), "timeout"),
])
def test_provider_errors(yt_app, err, code):
    c = yt_app(result=err)
    _, r = start(c)
    a = finished(c, r.json()["analysis"]["id"])
    assert a["status"] == "provider_error" and a["errorCode"] == code
    h = c.get("/api/health").json()["providers"]["gemini"]
    assert h["mode"] == "unverified" and h["failures"] == 1


def test_malformed_model_output(yt_app):
    c = yt_app(result={"items": "nope"})
    _, r = start(c)
    a = finished(c, r.json()["analysis"]["id"])
    assert a["status"] == "provider_error" and a["errorCode"] == "invalid_response"


def test_identical_request_reuses_cached_result(yt_app):
    c = yt_app()
    _, r1 = start(c)
    finished(c, r1.json()["analysis"]["id"])
    _, r2 = start(c)
    a2 = finished(c, r2.json()["analysis"]["id"])
    assert a2["cached"] is True and FakeGemini.calls == 1


def test_ownership(yt_app, app_factory):
    c = yt_app()
    _, r = start(c)
    aid = r.json()["analysis"]["id"]
    other = new_client(c.app)
    other.post("/api/sessions", headers=H)
    assert other.get(f"/api/youtube-analyses/{aid}").status_code == 404
