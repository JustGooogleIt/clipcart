"""Minimal xAI chat-completions client for bounded tool-calling workers.

Uses the documented OpenAI-compatible endpoint ``POST {base}/chat/completions``
with ``tools``. The key stays server-side (``XAI_API_KEY``).
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any

import httpx


class GrokError(Exception):
    def __init__(self, code: str, message: str, *, retryable: bool = False, trace_id: str | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable
        self.trace_id = trace_id


@dataclass
class GrokReply:
    message: dict
    tool_calls: list[dict]
    usage: dict | None
    model: str | None
    trace_id: str | None
    elapsed_ms: int


class GrokClient:
    def __init__(self, *, model: str, base_url: str, api_key: str | None = None):
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key or os.getenv("XAI_API_KEY")
        if not self.api_key:
            raise GrokError("auth_error", "XAI_API_KEY not configured")

    def chat(self, messages: list[dict], tools: list[dict], *, timeout_s: float, tool_choice: str = "auto") -> GrokReply:
        if timeout_s <= 1:
            raise GrokError("timeout", "no time left for a reasoning call", retryable=False)
        body: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "tools": tools,
            "tool_choice": tool_choice,
            "temperature": 0.2,
            "max_tokens": 800,
        }
        t0 = time.monotonic()
        try:
            resp = httpx.post(
                f"{self.base_url}/chat/completions",
                json=body,
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=timeout_s,
            )
        except httpx.TimeoutException as exc:
            raise GrokError("timeout", "Grok request timed out", retryable=True) from exc
        except httpx.HTTPError as exc:
            raise GrokError("unavailable", f"Could not reach xAI: {type(exc).__name__}", retryable=True) from exc
        trace = resp.headers.get("x-request-id") or resp.headers.get("x-trace-id")
        if resp.status_code in (401, 403):
            raise GrokError("auth_error", "xAI rejected the API key", trace_id=trace)
        if resp.status_code == 429:
            raise GrokError("rate_limited", "xAI rate limit", retryable=True, trace_id=trace)
        if resp.status_code == 404 or (resp.status_code == 400 and "model" in resp.text.lower()):
            raise GrokError("unsupported_capability", f"xAI model/endpoint rejected: {resp.text[:200]}", trace_id=trace)
        if resp.status_code >= 500:
            raise GrokError("unavailable", f"xAI HTTP {resp.status_code}", retryable=True, trace_id=trace)
        if resp.status_code != 200:
            raise GrokError("invalid_response", f"xAI HTTP {resp.status_code}: {resp.text[:200]}", trace_id=trace)
        try:
            data = resp.json()
            msg = data["choices"][0]["message"]
        except (ValueError, KeyError, IndexError) as exc:
            raise GrokError("invalid_response", "Malformed xAI response", trace_id=trace) from exc
        return GrokReply(
            message=msg,
            tool_calls=list(msg.get("tool_calls") or []),
            usage=data.get("usage"),
            model=data.get("model"),
            trace_id=trace or data.get("id"),
            elapsed_ms=int((time.monotonic() - t0) * 1000),
        )
