"""Research providers. Only the labelled development fixture exists today.

A bridge provider (Grok Bot webhook routine, xAI API agent) must implement
``dispatch`` and deliver results through ``service.ingest_submission``. See
docs/grok-bot-bridge.md for why the Grok Bot bridge is not implemented.
"""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from app.config import REPO_ROOT

FIXTURE_PATH = REPO_ROOT / "fixtures" / "research" / "dev_research_result.json"


@dataclass(frozen=True)
class DispatchResult:
    accepted: bool
    detail: str
    retryable: bool = False


class ResearchProvider(Protocol):
    name: str
    mode: str  # live | fixture

    def dispatch(self, job: dict, deliver: Any) -> DispatchResult: ...


class FixtureResearchProvider:
    """Delivers a captured, labelled fixture submission after a short delay (simulates async research)."""

    name = "fixture"
    mode = "fixture"

    def __init__(self, path: Path = FIXTURE_PATH, delay_s: float = 1.5):
        data = json.loads(Path(path).read_text())
        if "NOT GROK BOT OUTPUT" not in str(data.get("fixture_label", "")).upper():
            raise ValueError("research fixture must carry an explicit fixture_label")
        self.products = data["products"]
        self.notes = data.get("notes")
        self.delay_s = delay_s

    def dispatch(self, job: dict, deliver: Any) -> DispatchResult:
        payload = {"jobId": job["id"], "products": self.products, "notes": self.notes}
        t = threading.Timer(self.delay_s, deliver, args=(job["id"], payload))
        t.daemon = True
        t.start()
        return DispatchResult(True, "fixture delivery scheduled")


def get_provider(name: str) -> ResearchProvider:
    if name == "fixture":
        return FixtureResearchProvider()
    raise ValueError(f"research provider {name!r} is not implemented (bridge not proven; see docs/grok-bot-bridge.md)")
