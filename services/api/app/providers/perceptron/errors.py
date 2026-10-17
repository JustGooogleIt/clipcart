"""Normalize Perceptron SDK exceptions into the SRS provider error codes."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class NormalizedError:
    code: str  # auth_error | rate_limited | unavailable | timeout | invalid_response | unsupported_capability
    message: str
    retryable: bool
    request_id: str | None
    retry_after: float | None = None


def normalize_exception(exc: BaseException) -> NormalizedError:
    request_id = getattr(exc, "request_id", None)
    name_chain = {cls.__name__ for cls in type(exc).__mro__}
    sdk_code = getattr(exc, "code", None)
    retry_after = getattr(exc, "retry_after", None)
    msg = str(exc)[:300] or type(exc).__name__

    if "AuthError" in name_chain:  # includes PermissionDeniedError
        return NormalizedError("auth_error", "Perceptron rejected the credentials", False, request_id)
    if "QuotaExceededError" in name_chain:
        return NormalizedError("rate_limited", "Perceptron quota exhausted", False, request_id)
    if "RateLimitError" in name_chain:
        return NormalizedError("rate_limited", "Perceptron rate limit", True, request_id, retry_after)
    if "TimeoutError" in name_chain or isinstance(exc, TimeoutError):
        return NormalizedError("timeout", "Perceptron request timed out", True, request_id)
    if name_chain & {"ParseError", "ExpectationError", "AnchorError"}:
        return NormalizedError("invalid_response", msg, False, request_id)
    if "ServerError" in name_chain:
        if sdk_code in ("invalid_response", "invalid_stream_chunk"):
            return NormalizedError("invalid_response", msg, False, request_id)
        return NormalizedError("unavailable", "Perceptron server error", True, request_id)
    if "TransportError" in name_chain or isinstance(exc, ConnectionError):
        return NormalizedError("unavailable", "Could not reach Perceptron", True, request_id)
    if "BadRequestError" in name_chain:
        if sdk_code and (str(sdk_code).startswith("unsupported") or sdk_code == "model_renamed"):
            return NormalizedError("unsupported_capability", msg, False, request_id)
        if "NotFoundError" in name_chain:
            return NormalizedError("unsupported_capability", msg, False, request_id)
        return NormalizedError("invalid_response", msg, False, request_id)
    return NormalizedError("unavailable", f"Unexpected provider failure: {type(exc).__name__}", False, request_id)
