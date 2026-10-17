"""Typed media errors. Each maps to an HTTP status the route layer can use."""

from __future__ import annotations


class MediaError(Exception):
    code = "media_error"
    http_status = 400
    retryable = False

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class UnsupportedMediaError(MediaError):
    code = "unsupported_media"
    http_status = 415


class MediaTooLargeError(MediaError):
    code = "media_too_large"
    http_status = 413


class MediaLimitError(MediaError):
    """Duration, dimensions or pixel count exceed the configured limit."""

    code = "media_limit_exceeded"
    http_status = 422


class MediaDecodeError(MediaError):
    code = "media_decode_failed"
    http_status = 422


class MediaTimeoutError(MediaError):
    code = "media_timeout"
    http_status = 503
    retryable = True


class InvalidBoxError(MediaError):
    code = "invalid_box"
    http_status = 422


class AssetNotFoundError(MediaError):
    """Raised for both missing assets and assets owned by someone else."""

    code = "not_found"
    http_status = 404
