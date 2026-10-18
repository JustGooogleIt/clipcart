"""Gemma/Ollama adapter: schema validation, grounding, fallback. No network (mock transport)."""

import json

import httpx
import pytest

from app.providers.status import ProviderStatus
from app.style.model import OllamaStyleModel, explain, propose, rule_based_proposals, validate_explanation, validate_proposals

TEXT = "I'm a medium, I hate orange and I never wear leather. Love Acne Studios."


def ollama(content, status=200, capture=None):
    def handler(req):
        if capture is not None:
            capture.append(json.loads(req.content))
        if isinstance(content, Exception):
            raise content
        return httpx.Response(status, json={"message": {"role": "assistant", "content": content}, "done": True,
                                            "total_duration": 900_000_000, "load_duration": 100_000_000, "eval_count": 40})
    return OllamaStyleModel(base_url="http://ollama.test", model="gemma4:e4b", http=httpx.Client(transport=httpx.MockTransport(handler)))


def ups(*items):
    return json.dumps({"updates": [dict(zip(("kind", "value", "action", "quote"), i)) for i in items]})


def test_valid_model_output_is_grounded_and_typed():
    seen = []
    m = ollama(ups(("size", "medium", "set", "I'm a medium"), ("color_avoid", "orange", "add", "I hate orange"),
                   ("material_avoid", "leather", "add", "I never wear leather"), ("brand_like", "Acme Studios", "add", "Love Acne Studios")), capture=seen)
    st = ProviderStatus("style_model", True)
    r = propose(TEXT, m, st)
    assert r.mode == "model" and st.mode == "live"
    assert [(p.kind, p.value) for p in r.proposals] == [("size", {"raw": "M", "system": "alpha"}), ("color_avoid", "orange"),
                                                        ("material_avoid", "leather")]
    assert r.rejected == 1  # "Acme Studios" is not in its quote: hallucinated brand dropped
    body = seen[0]
    assert body["format"]["required"] == ["updates"] and body["options"]["temperature"] == 0 and body["stream"] is False


@pytest.mark.parametrize("bad", [
    ups(("size", "M", "set", "I am a size M")),            # quote not in text
    ups(("color_avoid", "blurple", "add", "I hate orange")),  # value outside vocabulary
    ups(("color_avoid", "orange", "set", "I hate orange")),   # wrong action for kind
    ups(("brand_like", "orange", "add", "I hate orange")),    # color dressed up as a brand
    ups(("height", "6ft", "set", "I'm a medium")),            # unknown kind
])
def test_invalid_items_rejected(bad):
    props, rejected = validate_proposals(json.loads(bad), TEXT)
    assert props == [] and rejected == 1


@pytest.mark.parametrize("content", ["not json at all", json.dumps({"items": []}), json.dumps([1, 2])])
def test_malformed_output_falls_back_to_rules(content):
    st = ProviderStatus("style_model", True)
    r = propose(TEXT, ollama(content), st)
    assert r.mode == "rule_based" and "invalid" in r.note and st.failures == 1
    assert {(p.kind, str(p.value)) for p in r.proposals} >= {("color_avoid", "orange"), ("material_avoid", "leather")}


@pytest.mark.parametrize("err", [httpx.ConnectError("refused"), httpx.ReadTimeout("slow")])
def test_model_unavailable_falls_back(err):
    st = ProviderStatus("style_model", True)
    r = propose(TEXT, ollama(err), st)
    assert r.mode == "rule_based" and "unavailable" in r.note and st.mode == "unverified"


def test_ollama_http_error_falls_back():
    assert propose(TEXT, ollama("{}", status=404)).mode == "rule_based"


def test_rule_based_parser_is_conservative():
    props = rule_based_proposals("I'm a medium, I hate orange, I never wear leather, budget of $120, women's fit")
    got = {p.kind: p.value for p in props}
    assert got["size"] == {"raw": "M", "system": "alpha"} and got["color_avoid"] == "orange"
    assert got["material_avoid"] == "leather" and got["budget_max"] == {"amountMinor": 12000, "currency": "USD"}
    assert got["fit"] == "womens"
    assert all(p.quote.lower() in "i'm a medium, i hate orange, i never wear leather, budget of $120, women's fit" for p in props)
    assert not any(p.kind == "fit" for p in rule_based_proposals("My name is Maria and I wear size M"))  # never fit from names


@pytest.mark.parametrize("text", ["I'm 6 foot tall and broad shouldered", "I'm 6' 2\"", "I am 5 ft 4", "I'm 32 years old",
                                  "I'm 70 kg", "I'm 180 cm"])
def test_rule_parser_never_reads_body_measurements_as_size(text):
    assert not any(p.kind == "size" for p in rule_based_proposals(text))


@pytest.mark.parametrize("text,size", [("size 8 please", "8"), ("I'm a medium", "M"), ("I wear an XL", "XL"), ("I'm 32 waist", "32")])
def test_rule_parser_explicit_sizes(text, size):
    got = [p.value["raw"] for p in rule_based_proposals(text) if p.kind == "size"]
    assert got == [size]


def test_rule_parser_like_quote_stops_at_last_color():
    text = "I'm a medium, I love brown, I hate orange and I never wear leather"
    likes = [p for p in rule_based_proposals(text) if p.kind == "color_like"]
    assert [(p.value, p.quote) for p in likes] == [("brown", "love brown")]
    assert [p.quote for p in rule_based_proposals("I love black and navy, or green")] == ["love black and navy, or green"] * 3


def test_rule_parser_color_lists():
    got = {p.value for p in rule_based_proposals("I love black and navy, or green") if p.kind == "color_like"}
    assert got == {"black", "navy", "green"}


@pytest.mark.parametrize("sentence,ok", [
    ("It matches the black you said you like.", True),
    ("Only $80 and in stock now!", False),
    ("Available at Farfetch with free shipping.", False),
    ("A 2024 classic you saved.", False),
    ("", False),
])
def test_explanation_validator(sentence, ok):
    assert (validate_explanation({"sentence": sentence, "used_facts": [0]}, ["You said you like black"]) is not None) is ok


def test_explain_falls_back_to_template():
    facts = ["You said you like black"]
    assert explain(facts, ollama(json.dumps({"sentence": "Cheap at $20", "used_facts": [0]}))) == (facts[0], "template")
    assert explain(facts, ollama(httpx.ConnectError("x"))) == (facts[0], "template")
    assert explain(facts, ollama(json.dumps({"sentence": "It is the black you asked for.", "used_facts": [0]})))[1] == "model"
