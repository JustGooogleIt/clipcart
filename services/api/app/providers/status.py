"""Process-wide provider status for health/diagnostics.

A provider is reported ``live`` only after a real call succeeded in this
process. A configured key alone is ``unverified``.
"""

from __future__ import annotations

import threading
from collections import deque
from datetime import datetime, timezone


class ProviderStatus:
    def __init__(self, name: str, configured: bool, mode_when_unconfigured: str = "unavailable"):
        self.name = name
        self.configured = configured
        self.mode_when_unconfigured = mode_when_unconfigured
        self.calls = 0
        self.failures = 0
        self.last_success_at: str | None = None
        self.last_error: dict | None = None
        self.recent: deque = deque(maxlen=20)
        self._lock = threading.Lock()

    def record(self, ok: bool, *, trace_id: str | None = None, code: str | None = None, note: str | None = None) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            self.calls += 1
            entry = {"at": now, "ok": ok, "traceId": trace_id, "code": code, "note": (note or "")[:160]}
            self.recent.appendleft(entry)
            if ok:
                self.last_success_at = now
            else:
                self.failures += 1
                self.last_error = entry

    @property
    def mode(self) -> str:
        if not self.configured:
            return self.mode_when_unconfigured
        return "live" if self.last_success_at else "unverified"

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "mode": self.mode,
                "configured": self.configured,
                "calls": self.calls,
                "failures": self.failures,
                "lastSuccessAt": self.last_success_at,
                "lastError": self.last_error,
                "recent": list(self.recent)[:8],
            }
