import json
import time

from app.contracts import Preferences, SearchBudget
from app.providers.grok.client import GrokError, GrokReply
from app.providers.status import ProviderStatus
from app.shopping.budget import BudgetLedger
from app.shopping.pipeline import run_search
from app.shopping.rules import GarmentProfile
from app.shopping.tools import clear_cache

from .fakes import FakeCatalog, item

ITEMS = [item("a", "Black Nylon Bomber Jacket", 70), item("b", "Black Satin Bomber Jacket", 95)]


def call(name, args, i):
    return {"id": f"c{i}", "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}


class ScriptedGrok:
    """Plays a fixed tool-call script per worker role, keyed by the system prompt."""

    def __init__(self):
        self.calls = 0

    def chat(self, messages, tools, *, timeout_s, tool_choice="auto"):
        self.calls += 1
        role = "exact" if messages[0]["content"].startswith("EXACT") else "alternatives"
        tool_msgs = [m for m in messages if m["role"] == "tool"]
        if not tool_msgs:
            q = "black bomber jacket" if role == "exact" else "nylon bomber jacket"
            msg = {"role": "assistant", "content": None, "tool_calls": [call("search_catalog", {"query": q}, 1)]}
        else:
            ids = [r["candidate_id"] for r in json.loads(tool_msgs[-1]["content"]).get("results", [])][:2]
            msg = {"role": "assistant", "content": None, "tool_calls": [call("submit_candidates", {"candidate_ids": ids}, 2)]}
        return GrokReply(msg, msg["tool_calls"], {"total_tokens": 10}, "grok-test", f"trace-{self.calls}", 5)


class AuthFailGrok:
    def chat(self, *a, **k):
        raise GrokError("auth_error", "bad key", trace_id="t-auth")


def run(client):
    clear_cache()
    grok_status = ProviderStatus("grok", True)
    events = []
    led = BudgetLedger(SearchBudget(), time.monotonic() + 20)
    out = run_search(
        search_id="s", garment_id="g", profile=GarmentProfile(category="jacket", colors=["black"], description="black bomber"),
        prefs=Preferences(), provider=FakeCatalog(ITEMS, {"a": {"sizes": ["M"]}, "b": {"sizes": ["M"]}}), ledger=led,
        emit=lambda st, sm, **k: events.append(sm), catalog_status=ProviderStatus("solescout", True),
        grok_status=grok_status, grok_client_factory=lambda: client, is_current=lambda: True,
    )
    return out, events, led, grok_status


def test_grok_workers_make_real_tool_calls_within_budget():
    out, events, led, st = run(ScriptedGrok())
    assert out.worker_modes == {"exact": "grok", "alternatives": "grok"}
    assert led.budget.reasoning_calls == 4 and led.budget.used_tool_calls <= 12
    assert st.mode == "live" and st.calls == 4
    assert any("nylon bomber jacket" in e for e in events) and out.recommendations


def test_grok_auth_failure_falls_back_to_labeled_rules():
    out, events, _, st = run(AuthFailGrok())
    assert out.worker_modes == {"exact": "rule_based_fallback", "alternatives": "rule_based_fallback"}
    assert st.mode == "unverified" and st.failures == 2
    assert any("unavailable (auth_error)" in e for e in events) and out.recommendations
