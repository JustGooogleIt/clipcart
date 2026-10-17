"""Normalized catalog adapter errors (SRS §12)."""

from __future__ import annotations


class CatalogProviderError(Exception):
    """Adapter failure distinct from an empty-but-valid search result."""

    def __init__(self, code: str, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable


# code values: auth_error | rate_limited | unavailable | timeout |
# invalid_response | unsupported_capability
