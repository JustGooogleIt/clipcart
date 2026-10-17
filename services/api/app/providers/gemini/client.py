"""Minimal Gemini Interactions API client (POST /v1beta/interactions).

Sends a public YouTube URL as a ``video`` input. Gemini fetches the video;
ClipCart never downloads it. The key stays server-side (``GEMINI_API_KEY``).
Bounded per call: clipped interval, low resolution, 0.5 fps, capped output
tokens, low thinking, ``store: false``.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from typing import Any

import httpx

API_REVISION = "2026-05-20"  # pinned so default-revision changes don't break parsing

# Phrases in Gemini errors that mean "the video itself could not be read".
_VIDEO_ACCESS_HINTS = (
    "youtube", "video", "private", "unlisted", "not public", "public video", "unavailable", "could not fetch",
    "cannot fetch", "failed to fetch", "inaccessible", "permission to access", "age-restricted", "region",
)


class GeminiError(Exception):
    def __init__(self, code: str, message: str, *, retryable: bool = False, http_status: int | None = None,
                 request_id: str | None = None):
        super().__init__(message)
        self.code = code  # auth_error | rate_limited | timeout | unavailable | invalid_response | video_inaccessible | invalid_request
        self.message = message
        self.retryable = retryable
        self.http_status = http_status
        self.request_id = request_id


@dataclass(frozen=True)
class GeminiReply:
    text: str
    interaction_id: str | None
    model: str | None
    usage: dict | None
    elapsed_ms: int


def _classify(http_status: int, message: str, provider_status: str | None) -> tuple[str, bool]:
    m = message.lower()
    if http_status == 401 or (http_status == 403 and ("api key" in m or "api_key" in m or "unregistered caller" in m)):
        return "auth_error", False
    if http_status == 429 or provider_status == "RESOURCE_EXHAUSTED":
        return "rate_limited", True
    if http_status in (400, 403, 404) and any(h in m for h in _VIDEO_ACCESS_HINTS):
        return "video_inaccessible", False
    if http_status >= 500:
        return "unavailable", True
    return "invalid_request", False


class GeminiClient:
    def __init__(self, *, model: str, base_url: str = "https://generativelanguage.googleapis.com/v1beta",
                 api_key: str | None = None, http: httpx.Client | None = None):
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        self.http = http
        if not self.api_key:
            raise GeminiError("auth_error", "GEMINI_API_KEY not configured")

    def analyze_youtube(
        self,
        url: str,
        prompt: str,
        schema: dict,
        *,
        start_s: int,
        end_s: int,
        fps: float = 0.5,
        max_output_tokens: int = 2048,
        timeout_s: float = 120.0,
    ) -> GeminiReply:
        body: dict[str, Any] = {
            "model": self.model,
            "input": [
                {
                    "type": "video",
                    "uri": url,
                    "resolution": "low",
                    "processing": {"type": "static", "fps": fps, "start_offset": int(start_s), "end_offset": int(end_s)},
                },
                {"type": "text", "text": prompt},
            ],
            "response_format": {"type": "text", "mime_type": "application/json", "schema": schema},
            "generation_config": {"max_output_tokens": max_output_tokens, "thinking_level": "low"},
            "store": False,
        }
        headers = {"x-goog-api-key": self.api_key, "Api-Revision": API_REVISION, "Content-Type": "application/json"}
        t0 = time.monotonic()
        try:
            c = self.http or httpx
            resp = c.post(f"{self.base_url}/interactions", json=body, headers=headers, timeout=timeout_s)
        except httpx.TimeoutException as exc:
            raise GeminiError("timeout", "Gemini took too long to read the video", retryable=True) from exc
        except httpx.HTTPError as exc:
            raise GeminiError("unavailable", f"Could not reach Gemini ({type(exc).__name__})", retryable=True) from exc
        elapsed = int((time.monotonic() - t0) * 1000)
        try:
            data = resp.json()
        except ValueError:
            data = None
        if resp.status_code != 200:
            err = (data or {}).get("error") if isinstance(data, dict) else None
            msg = str((err or {}).get("message") or resp.text[:300] or f"HTTP {resp.status_code}")
            code, retryable = _classify(resp.status_code, msg, (err or {}).get("status"))
            raise GeminiError(code, msg[:300], retryable=retryable, http_status=resp.status_code)
        if not isinstance(data, dict):
            raise GeminiError("invalid_response", "Gemini returned a non-JSON body")
        iid = data.get("id")
        status = data.get("status")
        if status and status != "completed":
            errs = data.get("errors") or []
            msg = "; ".join(str(e.get("message", "")) for e in errs if isinstance(e, dict))[:300] or f"interaction {status}"
            code, retryable = _classify(400 if errs else 500, msg, None)
            if status == "incomplete" and not errs:
                code, retryable = "invalid_response", False
                msg = "Gemini stopped before finishing its answer (output limit)."
            raise GeminiError(code, msg, retryable=retryable, request_id=iid)
        texts: list[str] = []
        for step in data.get("steps") or []:
            if isinstance(step, dict) and step.get("type") == "model_output":
                for part in step.get("content") or []:
                    if isinstance(part, dict) and part.get("type") == "text" and isinstance(part.get("text"), str):
                        texts.append(part["text"])
        if not texts and isinstance(data.get("output_text"), str):
            texts.append(data["output_text"])
        if not texts:
            raise GeminiError("invalid_response", "Gemini returned no text output", request_id=iid)
        return GeminiReply("".join(texts), iid, data.get("model"), data.get("usage"), elapsed)


def parse_json_text(text: str) -> Any:
    t = text.strip()
    if t.startswith("```"):
        t = t.strip("`")
        t = t[t.find("\n") + 1 :] if "\n" in t else t
    return json.loads(t)
