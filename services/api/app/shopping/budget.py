"""Shared, thread-safe per-search budget (SRS section 10).

Checked atomically *before* dispatch. Cache hits skip the paid-call budget
but still count against the loop cap so a worker cannot spin forever.
"""

from __future__ import annotations

import threading
import time

from app.contracts import SearchBudget


class BudgetExceeded(Exception):
    def __init__(self, kind: str):
        super().__init__(f"{kind} budget exhausted")
        self.kind = kind


class BudgetLedger:
    def __init__(self, budget: SearchBudget, deadline_monotonic: float, loop_cap: int = 24):
        self.budget = budget
        self.deadline = deadline_monotonic
        self.loop_cap = loop_cap
        self.loops = 0
        self._lock = threading.Lock()

    def remaining_s(self) -> float:
        return self.deadline - time.monotonic()

    def _check_deadline(self) -> None:
        if self.remaining_s() <= 0.5:
            raise BudgetExceeded("deadline")

    def take_tool(self, *, detail: bool = False, cached: bool = False) -> None:
        with self._lock:
            self._check_deadline()
            if self.loops >= self.loop_cap:
                raise BudgetExceeded("loop")
            if not cached:
                if self.budget.used_tool_calls >= self.budget.max_tool_calls:
                    raise BudgetExceeded("tool_calls")
                if detail and self.budget.used_detail_calls >= self.budget.max_detail_calls:
                    raise BudgetExceeded("detail_calls")
                self.budget.used_tool_calls += 1
                if detail:
                    self.budget.used_detail_calls += 1
            self.loops += 1

    def take_reasoning(self) -> None:
        with self._lock:
            self._check_deadline()
            self.budget.reasoning_calls += 1

    def detail_left(self) -> int:
        with self._lock:
            return min(
                self.budget.max_detail_calls - self.budget.used_detail_calls,
                self.budget.max_tool_calls - self.budget.used_tool_calls,
            )
