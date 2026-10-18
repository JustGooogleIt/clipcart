"""Hosted OpenAI-compatible style model: JSON extraction, auth, fallback, and honest hosting labels. No network."""

import json

import httpx
from api.conftest import H, new_client

from app.providers.status import ProviderStatus
from app.style.model import OpenAICompatibleStyleModel, _extract_json, propose

TEXT = "I'm a medium and I never wear leather"
GOOD = {"updates": [{"kind": "size", "value": "medium", "action": "set", "quote": "I'm a medium"},
                    {"kind": "material_avoid", "value": "leather", "action": "add", "quote": "I never wear leather"},
                    {"kind": "fit", "value": "womens", "action": "set", "quote": "womens"}]}


def hosted(content, status=200, capture=None, json_mode="prompt"):
    def handler(req):
        if capture is not None:
            capture.append((dict(req.headers), json.loads(req.content), str(req.url)))
        if isinstance(content, Exception):
            raise content
        return httpx.Response(status, json={"choices": [{"message": {"role": "assistant", "content": content},
                                                         "finish_reason": "stop"}],
                                            "usage": {"prompt_tokens": 350, "completion_tokens": 60}})
    return OpenAICompatibleStyleModel(base_url="http://gpu.test/v1/", api_key="test-key", model="gemma-12b",
                                      label="Gemma hosted on Lambda (not local)", json_mode=json_mode, max_tokens=200,
                                      http=httpx.Client(transport=httpx.MockTransport(handler)))


def test_hosted_output_is_validated_and_usage_reported():
    seen = []
    st = ProviderStatus("style_model", True)
    r = propose(TEXT, hosted("```json\n" + json.dumps(GOOD) + "\n```", capture=seen), st)
    assert r.mode == "model" and st.mode == "live"
    assert [(p.kind, p.action) for p in r.proposals] == [("size", "set"), ("material_avoid", "add")]
    assert r.rejected == 1  # "womens" is not in the shopper's text: prompt echo dropped
    assert r.timings["promptTokens"] == 350 and r.timings["completionTokens"] == 60
    headers, body, url = seen[0]
    assert url == "http://gpu.test/v1/chat/completions" and headers["authorization"] == "Bearer test-key"
    assert body["temperature"] == 0 and body["max_tokens"] == 200 and "response_format" not in body


def test_schema_mode_sends_response_format_and_caps_tokens():
    seen = []
    m = hosted(json.dumps(GOOD), capture=seen, json_mode="schema")
    m.chat_json("sys", TEXT, {"type": "object"}, max_tokens=999)
    body = seen[0][1]
    assert body["response_format"]["type"] == "json_schema" and body["max_tokens"] == 200


def test_unreachable_or_bad_status_or_prose_falls_back_to_rules():
    for model in (hosted(httpx.ConnectError("down")), hosted("{}", status=401), hosted("Sure! You like leather.")):
        st = ProviderStatus("style_model", True)
        r = propose(TEXT, model, st)
        assert r.mode == "rule_based" and st.mode != "live"
        assert {(p.kind, p.action) for p in r.proposals} == {("size", "set"), ("material_avoid", "add")}


def test_extract_json_variants():
    assert _extract_json('{"updates": []}') == {"updates": []}
    assert _extract_json('Here you go: {"updates": []} done') == {"updates": []}
    assert _extract_json("no json here") == "no json here"


def _app(app_factory, monkeypatch, **env):
    monkeypatch.setenv("FEATURE_STYLE_MEMORY", "1")
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    return app_factory()


def test_health_labels_hosted_model_remote_and_unverified_until_a_call(app_factory, monkeypatch):
    app = _app(app_factory, monkeypatch, STYLE_MODEL_PROVIDER="openai_compatible",
               STYLE_REMOTE_BASE_URL="http://127.0.0.1:9/v1", STYLE_REMOTE_API_KEY="k", STYLE_REMOTE_MODEL="gemma-12b",
               STYLE_MODEL_TIMEOUT_S="1")
    c = new_client(app)
    sm = c.get("/api/health").json()["providers"]["styleModel"]
    assert sm["hosting"] == "remote" and sm["label"] == "gemma-12b · hosted endpoint (not local)"
    assert sm["provider"] == "openai_compatible" and sm["model"] == "gemma-12b" and sm["mode"] != "live"
    c.post("/api/sessions", headers=H)
    r = c.post("/api/style/notes", headers=H, json={"text": TEXT}).json()  # nothing listens on :9
    assert r["mode"] == "rule_based" and r["hosting"] is None and r["provider"] == "Rule-based parser"
    assert c.get("/api/style/memories").json()["memories"] == []  # notes never save
    assert c.get("/api/health").json()["providers"]["styleModel"]["mode"] != "live"


def test_hosted_provider_without_key_is_not_configured(app_factory, monkeypatch):
    monkeypatch.delenv("STYLE_REMOTE_API_KEY", raising=False)
    app = _app(app_factory, monkeypatch, STYLE_MODEL_PROVIDER="openai_compatible",
               STYLE_REMOTE_BASE_URL="http://127.0.0.1:9/v1", STYLE_REMOTE_MODEL="gemma-12b")
    st = app.state.clipcart
    assert st.style_model() is None and st.status["style_model"].mode == "unavailable"


def test_live_reflects_the_latest_call_not_any_past_success(app_factory, monkeypatch):
    app = _app(app_factory, monkeypatch, STYLE_MODEL_PROVIDER="openai_compatible",
               STYLE_REMOTE_BASE_URL="http://127.0.0.1:9/v1", STYLE_REMOTE_API_KEY="k", STYLE_REMOTE_MODEL="m",
               STYLE_REMOTE_LABEL="Configured label")
    st = app.state.clipcart
    c = new_client(app)
    status = st.status["style_model"]
    status.record(True, note="propose")
    assert c.get("/api/health").json()["providers"]["styleModel"]["mode"] == "live"
    assert c.get("/api/health").json()["providers"]["styleModel"]["label"] == "Configured label"
    status.record(False, code="unavailable", note="down")
    c.post("/api/sessions", headers=H)
    assert c.get("/api/health").json()["providers"]["styleModel"]["mode"] == "unverified"
    assert c.get("/api/style/profile").json()["styleModel"]["mode"] == "unverified"
    status.record(True, note="propose")
    assert c.get("/api/style/profile").json()["styleModel"]["mode"] == "live"
