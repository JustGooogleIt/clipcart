"""Request context passed into media/perception calls (SRS section 12)."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field


@dataclass(frozen=True)
class RequestContext:
    owner_id: str
    request_id: str
    deadline_monotonic: float  # time.monotonic() value after which work must stop
    cancel_event: threading.Event = field(default_factory=threading.Event)

    @classmethod
    def with_timeout(cls, owner_id: str, request_id: str, seconds: float) -> RequestContext:
        return cls(owner_id=owner_id, request_id=request_id, deadline_monotonic=time.monotonic() + seconds)

    def remaining(self) -> float:
        return self.deadline_monotonic - time.monotonic()

    @property
    def cancelled(self) -> bool:
        return self.cancel_event.is_set()
