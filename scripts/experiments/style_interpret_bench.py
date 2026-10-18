"""Bounded model test for style interpretations. One model call per case; never more than --max-calls.

    STYLE_REMOTE_BASE_URL=... STYLE_REMOTE_API_KEY=... STYLE_REMOTE_MODEL=... \\
      services/api/.venv/bin/python scripts/experiments/style_interpret_bench.py --max-calls 8

Every proposal goes through the same validation as production (app.style.interpret.apply_proposals) on an
in-memory database. Reports validated precision/recall against the labels, validation refusals by reason,
latency and token usage. Prints no secrets.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "services" / "api"))

import mongomock  # noqa: E402

from app.style.interpret import SCHEMA, SYSTEM, _event_view, apply_proposals  # noqa: E402
from app.style.model import OpenAICompatibleStyleModel  # noqa: E402
from app.style.tags import listing_facts  # noqa: E402

CASES = Path(__file__).with_name("style_interpret_cases.json")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-calls", type=int, default=8)
    a = ap.parse_args()
    for k in ("STYLE_REMOTE_BASE_URL", "STYLE_REMOTE_API_KEY", "STYLE_REMOTE_MODEL"):
        if not os.getenv(k):
            print(json.dumps({"skipped": f"{k} not set"}))
            return 2
    m = OpenAICompatibleStyleModel(base_url=os.environ["STYLE_REMOTE_BASE_URL"], api_key=os.environ["STYLE_REMOTE_API_KEY"],
                                   model=os.environ["STYLE_REMOTE_MODEL"], label="bench", timeout_s=60, max_tokens=400)
    tp = fp = fn = calls = 0
    reasons: Counter = Counter()
    walls, toks = [], []
    rows = []
    for case in json.loads(CASES.read_text())["cases"][: a.max_calls]:
        db = mongomock.MongoClient()["bench"]
        events = {}
        for i, e in enumerate(case["events"]):
            eid = f"sev_{case['id']}_{i}"
            events[eid] = {"_id": eid, "id": eid, "ownerId": "o", "type": e["type"], "occurredAt": datetime.now(timezone.utc).isoformat(),
                           "item": {"title": e["title"], "brand": e.get("brand"), "styleFacts": listing_facts(e["title"])}}
        calls += 1
        raw, t = m.chat_json(SYSTEM, json.dumps({"events": [_event_view(v) for v in events.values()]}), SCHEMA, max_tokens=400)
        applied, rejected = apply_proposals(db, "o", raw, events, now=datetime.now(timezone.utc))
        got = {(x["kind"], str(x["value"]).lower()) for x in applied}
        exp = {(k, v.lower()) for k, v in case["expect"]}
        tp, fp, fn = tp + len(got & exp), fp + len(got - exp), fn + len(exp - got)
        reasons.update(r["reason"].split(" (")[0].split(":")[0] for r in rejected)
        walls.append(t.get("wallMs") or 0)
        toks.append((t.get("promptTokens") or 0, t.get("completionTokens") or 0))
        rows.append({"case": case["id"], "applied": sorted(got), "missed": sorted(exp - got), "extra": sorted(got - exp),
                     "rejected": [(r["kind"], r["value"], r["reason"]) for r in rejected]})
    print(json.dumps({"model": m.model, "calls": calls, "precision": round(tp / max(1, tp + fp), 2), "recall": round(tp / max(1, tp + fn), 2),
                      "validationRefusals": dict(reasons), "wallMsMax": max(walls or [0]),
                      "promptTokens": sum(p for p, _ in toks), "completionTokens": sum(c for _, c in toks), "cases": rows}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
