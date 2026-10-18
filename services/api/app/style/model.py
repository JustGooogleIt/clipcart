"""Gemma via Ollama: propose preference updates from text, and phrase personalized explanations.

The model never writes memories. Every output is validated in code; anything
invalid is dropped, and if the model is unavailable or its output is unusable
the rule-based proposer and template explanations are used instead.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

from app.contracts import Preferences, StyleProposal
from app.shopping.refine import parse_refinement

from .vocab import COLORS, MATERIALS, ONE_ACTIVE, InvalidMemory, normalize

KINDS = ["size", "fit", "budget_max", "color_like", "color_avoid", "material_like", "material_avoid",
         "brand_like", "brand_avoid"]
PROPOSAL_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "updates": {
            "type": "array",
            "maxItems": 6,
            "items": {
                "type": "object",
                "properties": {
                    "kind": {"type": "string", "enum": KINDS},
                    "value": {"type": "string"},
                    "action": {"type": "string", "enum": ["add", "set", "remove"]},
                    "quote": {"type": "string"},
                },
                "required": ["kind", "value", "action", "quote"],
            },
        }
    },
    "required": ["updates"],
}
EXPLAIN_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"sentence": {"type": "string"}, "used_facts": {"type": "array", "items": {"type": "integer"}}},
    "required": ["sentence", "used_facts"],
}
_SYSTEM = (
    "You extract a shopper's clothing preferences. Output only JSON matching the schema. "
    "Use only these kinds: " + ", ".join(KINDS) + ". "
    "size: a size label like M or 32. fit: womens, mens or unisex. budget_max: a USD amount like 120. "
    "color_*: one color word. material_*: one material word. brand_*: a brand name exactly as written. "
    "action: set for size/fit/budget_max, add or remove for the others (remove = the shopper takes it back). "
    "quote: the exact words from the text that state it. Skip anything not clearly stated. "
    "Never infer size from body descriptions, fit from names, or brands from styles."
)
_BANNED = re.compile(r"[\d$€£%]|\b(price|priced|cost|cheap|cheaper|sale|deal|discount|stock|available|availability|ships|"
                     r"shipping|deliver|guarantee|authentic|genuine|retailer|store|seller|buy now|in stock)\b", re.I)


class ModelUnavailable(Exception):
    pass


@dataclass
class ProposalResult:
    mode: str  # model | rule_based
    model: str | None
    proposals: list[StyleProposal]
    rejected: int = 0
    note: str | None = None
    timings: dict = field(default_factory=dict)


class OllamaStyleModel:
    hosting = "local"

    def __init__(self, *, base_url: str, model: str, timeout_s: float = 8.0, http: httpx.Client | None = None):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.label = f"{model} via local Ollama"
        self.timeout_s = timeout_s
        self.http = http

    def chat_json(self, system: str, user: str, schema: dict, *, max_tokens: int = 300) -> tuple[Any, dict]:
        body = {
            "model": self.model,
            "messages": [{"role": "system", "content": system + "\nJSON schema: " + json.dumps(schema)},
                         {"role": "user", "content": user}],
            "format": schema,
            "stream": False,
            "options": {"temperature": 0, "num_predict": max_tokens},
            "keep_alive": "10m",
        }
        t0 = time.monotonic()
        try:
            c = self.http or httpx
            r = c.post(f"{self.base_url}/api/chat", json=body,
                       timeout=httpx.Timeout(self.timeout_s, connect=1.5))
        except httpx.HTTPError as exc:
            raise ModelUnavailable(f"ollama unreachable: {type(exc).__name__}") from exc
        if r.status_code != 200:
            raise ModelUnavailable(f"ollama HTTP {r.status_code}: {r.text[:120]}")
        try:
            data = r.json()
            content = data["message"]["content"]
        except (ValueError, KeyError, TypeError) as exc:
            raise ModelUnavailable("ollama returned an unexpected body") from exc
        timings = {"wallMs": int((time.monotonic() - t0) * 1000)}
        for k in ("total_duration", "load_duration", "prompt_eval_duration", "eval_duration"):
            if isinstance(data.get(k), (int, float)):
                timings[k.replace("_duration", "Ms")] = int(data[k] / 1e6)
        for k in ("prompt_eval_count", "eval_count"):
            if isinstance(data.get(k), int):
                timings[k] = data[k]
        try:
            return json.loads(content), timings
        except (TypeError, json.JSONDecodeError):
            return content, timings  # caller validates and treats as malformed


def _extract_json(content: Any) -> Any:
    """Parse a JSON object from model text: plain JSON, fenced JSON, or the first {...} block."""
    if not isinstance(content, str):
        return content
    t = content.strip()
    if t.startswith("```"):
        t = t.strip("`")
        t = t[t.find("\n") + 1:] if "\n" in t else t
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        a, b = t.find("{"), t.rfind("}")
        if a != -1 and b > a:
            try:
                return json.loads(t[a:b + 1])
            except json.JSONDecodeError:
                pass
    return content  # caller treats non-dict as malformed


class OpenAICompatibleStyleModel:
    """Hosted model behind an OpenAI-compatible /chat/completions API (e.g. vLLM on a Lambda GPU).

    Not local: shopper text is sent to the configured endpoint. ``json_mode`` is
    "prompt" (ask for JSON and extract it) or "schema" (``response_format``
    json_schema, for servers whose guided decoding is known to work).
    """

    hosting = "remote"

    def __init__(self, *, base_url: str, api_key: str, model: str, label: str, timeout_s: float = 20.0,
                 json_mode: str = "prompt", max_tokens: int = 300, http: httpx.Client | None = None):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.label = label
        self.timeout_s = timeout_s
        self.json_mode = json_mode
        self.max_tokens = max_tokens
        self.http = http

    def chat_json(self, system: str, user: str, schema: dict, *, max_tokens: int = 300) -> tuple[Any, dict]:
        body: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system + "\nRespond with only one JSON object matching this schema: "
                 + json.dumps(schema)},
                {"role": "user", "content": user},
            ],
            "temperature": 0,
            "max_tokens": min(max_tokens, self.max_tokens),
        }
        if self.json_mode == "schema":
            body["response_format"] = {"type": "json_schema", "json_schema": {"name": "clipcart_style", "schema": schema}}
        t0 = time.monotonic()
        try:
            c = self.http or httpx
            r = c.post(f"{self.base_url}/chat/completions", json=body,
                       headers={"Authorization": f"Bearer {self.api_key}"},
                       timeout=httpx.Timeout(self.timeout_s, connect=3.0))
        except httpx.HTTPError as exc:
            raise ModelUnavailable(f"hosted model unreachable: {type(exc).__name__}") from exc
        if r.status_code != 200:
            raise ModelUnavailable(f"hosted model HTTP {r.status_code}")
        try:
            data = r.json()
            content = data["choices"][0]["message"]["content"]
            finish = data["choices"][0].get("finish_reason")
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise ModelUnavailable("hosted model returned an unexpected body") from exc
        usage = data.get("usage") or {}
        timings = {"wallMs": int((time.monotonic() - t0) * 1000), "finishReason": finish,
                   "promptTokens": usage.get("prompt_tokens"), "completionTokens": usage.get("completion_tokens")}
        return _extract_json(content), timings


def validate_proposals(raw: Any, text: str) -> tuple[list[StyleProposal], int]:
    """Keep only proposals whose kind/value pass the vocabulary and whose quote is in the text."""
    if not isinstance(raw, dict) or not isinstance(raw.get("updates"), list):
        raise ValueError("model output is not {updates: [...]}")
    low = " ".join(text.lower().split())
    out: list[StyleProposal] = []
    rejected = 0
    for u in raw["updates"][:6]:
        try:
            kind, action, quote = u["kind"], u["action"], " ".join(str(u["quote"]).split())
            if kind not in KINDS or action not in ("add", "set", "remove"):
                raise InvalidMemory("bad kind/action")
            if (kind in ONE_ACTIVE) != (action == "set"):
                raise InvalidMemory("action does not fit kind")
            if not quote or quote.lower() not in low:
                raise InvalidMemory("quote not found in the shopper's text")
            value = normalize(kind, u["value"])
            if kind.startswith(("color_", "material_", "brand_")) and str(value).lower() not in quote.lower():
                raise InvalidMemory("value is not in its quote")
            out.append(StyleProposal(kind=kind, value=value, action=action, quote=quote[:160]))
        except (InvalidMemory, KeyError, TypeError):
            rejected += 1
    return out, rejected


_AVOID = r"(?:hate|no|avoid|don'?t (?:like|want|wear)|never wear|not into|allergic to)"
_LIKE = r"(?:love|like|prefer|into|always wear|mostly wear)"


def rule_based_proposals(text: str) -> list[StyleProposal]:
    """Deterministic fallback. Conservative: only clear statements, each with its exact quote."""
    t = text.replace("’", "'")
    out: list[StyleProposal] = []

    def add(kind, value, action, quote):
        try:
            v = normalize(kind, value)
        except InvalidMemory:
            return
        if not any(p.kind == kind and p.value == v for p in out):
            out.append(StyleProposal(kind=kind, value=v, action=action, quote=quote.strip()[:160]))

    for m in re.finditer(rf"\b{_AVOID}\s+(?:anything\s+|wearing\s+)?([a-z]+(?:\s+leather)?)", t, re.I):
        w = m.group(1).lower()
        if w in COLORS:
            add("color_avoid", w, "add", m.group(0))
        elif w in MATERIALS:
            add("material_avoid", w, "add", m.group(0))
    sep = r"\s*(?:,\s*(?:and|or)\b|,|\band\b|\bor\b|&)\s*"
    for m in re.finditer(rf"\b{_LIKE}\s+([a-z]+(?:{sep}[a-z]+)*)", t, re.I):
        words = [w for w in re.finditer(r"[a-z]+", m.group(1), re.I) if w.group(0).lower() in COLORS]
        if words:  # quote stops at the last color, so "love brown, I hate…" quotes "love brown"
            quote = t[m.start():m.start(1) + words[-1].end()]
            for w in words:
                add("color_like", w.group(0).lower(), "add", quote)
    # Sizes only from explicit wording; never from heights, weights or body descriptions.
    not_body = r"(?!\s*(?:'|\"|ft\b|foot\b|feet\b|in\b|inch|cm\b|kg\b|lb|pounds\b|tall\b|years?\b|yo\b))"
    m = re.search(rf"\b(?:i'?m|i am|i wear)\s+(?:a\s+|an\s+|size\s+)?(xxs|xs|small|medium|large|xl|xxl|s|m|l|\d{{1,2}}){not_body}\b",
                  t, re.I) or re.search(rf"\bsize\s+(xxs|xs|xl|xxl|s|m|l|\d{{1,2}}){not_body}\b", t, re.I)
    if m:
        add("size", m.group(1), "set", m.group(0))
    m = re.search(r"\b(women'?s|men'?s|unisex)\s+(?:fit|sizing|cut|clothes|section)\b", t, re.I)
    if m:
        add("fit", m.group(1), "set", m.group(0))
    interp = parse_refinement(t, Preferences())
    if interp.patch.max_item_price_minor is not None:
        q = re.search(r"(?:under|below|less than|max(?:imum)?|at most|up to|no more than|budget(?: of| is)?)\s*\$?\s*\d[\d.]*", t, re.I)
        if q:
            add("budget_max", {"amountMinor": interp.patch.max_item_price_minor, "currency": "USD"}, "set", q.group(0))
    return out


def propose(text: str, model: OllamaStyleModel | None, status=None) -> ProposalResult:
    if model is not None:
        try:
            raw, timings = model.chat_json(_SYSTEM, text, PROPOSAL_SCHEMA)
            proposals, rejected = validate_proposals(raw, text)
            if status:
                status.record(True, note="propose")
            return ProposalResult("model", model.model, proposals, rejected, timings=timings)
        except ModelUnavailable as exc:
            if status:
                status.record(False, code="unavailable", note=str(exc))
            note = "Style model unavailable; used the rule-based parser."
        except ValueError as exc:
            if status:
                status.record(False, code="invalid_output", note=str(exc))
            note = "Style model output was invalid; used the rule-based parser."
    else:
        note = "Style model is off; used the rule-based parser."
    return ProposalResult("rule_based", None, rule_based_proposals(text), 0, note=note)


def validate_explanation(raw: Any, facts: list[str]) -> str | None:
    if not isinstance(raw, dict) or not isinstance(raw.get("sentence"), str):
        return None
    s = " ".join(raw["sentence"].split())
    used = raw.get("used_facts")
    if not s or len(s) > 180 or _BANNED.search(s):
        return None
    if not isinstance(used, list) or not used or any(not isinstance(i, int) or not 0 <= i < len(facts) for i in used):
        return None
    return s


def explain(facts: list[str], model: OllamaStyleModel | None, status=None) -> tuple[str, str]:
    """Return (sentence, mode). Facts are already-verified personalization reasons."""
    template = facts[0] if facts else ""
    if model is None or not facts:
        return template, "template"
    try:
        raw, _ = model.chat_json(
            "Write one short sentence (under 25 words) telling a shopper why a clothing result fits their saved style. "
            "Use only the numbered facts. Never mention prices, numbers, stock, sellers or stores.",
            "\n".join(f"{i}. {f}" for i, f in enumerate(facts)), EXPLAIN_SCHEMA, max_tokens=80)
    except ModelUnavailable as exc:
        if status:
            status.record(False, code="unavailable", note=str(exc))
        return template, "template"
    s = validate_explanation(raw, facts)
    if status:
        status.record(s is not None, code=None if s else "invalid_output", note="explain")
    return (s, "model") if s else (template, "template")
