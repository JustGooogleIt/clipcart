"""Benchmark Gemma (via Ollama) against the rule-based parser on ClipCart preference statements.

    services/api/.venv/bin/python scripts/experiments/style_model_bench.py --models gemma4:e4b gemma4:e2b

Never pulls a model: it checks /api/tags first and skips tags that aren't installed.
Reports wall/load/eval latency, schema-valid rate, and precision/recall of
validated proposals against hand-labelled expectations (written before running).
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "services" / "api"))

from app.style.model import (  # noqa: E402
    PROPOSAL_SCHEMA,
    _SYSTEM,
    OllamaStyleModel,
    OpenAICompatibleStyleModel,
    rule_based_proposals,
    validate_proposals,
)

# Labels are (kind, value, action) and were written before any model run.
# Cases 1-10 are the original set; case 5 is now labelled as the removal it is.
CASES = [
    ("I'm a medium and I never wear leather", {("size", "M", "set"), ("material_avoid", "leather", "add")}),
    ("No orange please, I hate it", {("color_avoid", "orange", "add")}),
    ("I love black and navy, budget of $150",
     {("color_like", "black", "add"), ("color_like", "navy", "add"), ("budget_max", "15000", "set")}),
    ("Women's fit, size 8", {("fit", "womens", "set"), ("size", "8", "set")}),
    ("Actually leather is fine now", {("material_avoid", "leather", "remove")}),
    ("I like Acne Studios but avoid Gucci", {("brand_like", "Acne Studios", "add"), ("brand_avoid", "Gucci", "add")}),
    ("Nothing in wool, I'm allergic to wool", {("material_avoid", "wool", "add")}),
    ("My name is Maria and I usually buy tops", set()),  # must not infer fit from a name
    ("I'm 6 foot tall and broad shouldered", set()),  # must not infer a size from body description
    ("Under $80, no polyester, prefer green",
     {("budget_max", "8000", "set"), ("material_avoid", "polyester", "add"), ("color_like", "green", "add")}),
    # correction: only the latest size
    ("I said medium earlier but actually I'm a large", {("size", "L", "set")}),
    # conflict: what they wear wins over what they admire
    ("Red is my favorite to look at but I never wear red", {("color_avoid", "red", "add")}),
    # ambiguous size: nothing clearly stated
    ("I'm somewhere between a small and a medium", set()),
    # negation: "don't mind" is not an avoid
    ("I don't mind wool, but I really don't like polyester", {("material_avoid", "polyester", "add")}),
    ("Not a fan of black, but navy is great", {("color_avoid", "black", "add"), ("color_like", "navy", "add")}),
    # purchase vs interest: a purchase for someone else is not a preference
    ("I bought a Patagonia fleece last month for my dad", set()),
    ("I just bought Nike sneakers, and honestly I love Nike", {("brand_like", "Nike", "add")}),
    # explicit take-back
    ("Please forget that I avoid orange", {("color_avoid", "orange", "remove")}),
]


REGRESSION_FILE = Path(__file__).with_name("style_regression_cases.json")


def regression_cases() -> list[tuple[str, set]]:
    """Known action-interpretation failures (add vs remove, purchase vs preference). See the JSON's $comment."""
    data = json.loads(REGRESSION_FILE.read_text())
    return [(c["text"], {tuple(x) for x in c["expected"]}) for c in data["cases"]]


def key(p) -> tuple[str, str, str]:
    v = p.value
    if isinstance(v, dict):
        v = v.get("raw") or str(v.get("amountMinor"))
    return (p.kind, str(v), p.action)


def score(pred: set, exp: set) -> tuple[int, int, int]:
    return len(pred & exp), len(pred - exp), len(exp - pred)


def run_remote(max_calls: int, out_path: str | None, cases: list | None = None) -> dict:
    """Hosted OpenAI-compatible model. Endpoint, key and model come from env and are never printed.

    No warm-up call: every request counts against ``max_calls``.
    """
    import os

    m = OpenAICompatibleStyleModel(base_url=os.environ["STYLE_REMOTE_BASE_URL"], api_key=os.environ["STYLE_REMOTE_API_KEY"],
                                   model=os.environ["STYLE_REMOTE_MODEL"], label="hosted", timeout_s=60,
                                   max_tokens=int(os.getenv("STYLE_REMOTE_MAX_TOKENS", "300")))
    tp = fp = fn = invalid = rejected = errors = 0
    walls, ptoks, ctoks, rows = [], [], [], []
    for i, (text, exp) in enumerate((cases or CASES)[:max_calls], 1):
        row = {"case": i, "text": text, "expected": sorted(map(list, exp))}
        try:
            raw, t = m.chat_json(_SYSTEM, text, PROPOSAL_SCHEMA)
        except Exception as exc:  # noqa: BLE001
            errors += 1
            fn += len(exp)
            rows.append({**row, "error": f"{type(exc).__name__}: {exc}"[:160]})
            continue
        walls.append(t["wallMs"])
        ptoks.append(t.get("promptTokens") or 0)
        ctoks.append(t.get("completionTokens") or 0)
        try:
            props, rej = validate_proposals(raw, text)
        except ValueError:
            invalid += 1
            props, rej = [], 0
        rejected += rej
        pred = {key(p) for p in props}
        a, b, c = score(pred, exp)
        tp, fp, fn = tp + a, fp + b, fn + c
        rows.append({**row, "predicted": sorted(map(list, pred)), "falsePositives": sorted(map(list, pred - exp)),
                     "missed": sorted(map(list, exp - pred)), "rejectedProposals": rej,
                     "malformed": not isinstance(raw, dict), "raw": raw if isinstance(raw, dict) else str(raw)[:300],
                     "wallMs": t["wallMs"], "promptTokens": t.get("promptTokens"),
                     "completionTokens": t.get("completionTokens"), "finishReason": t.get("finishReason")})
    res = {"mode": "model", "model": os.environ["STYLE_REMOTE_MODEL"], "hosting": "remote", "calls": len(rows),
           "precision": round(tp / max(1, tp + fp), 2), "recall": round(tp / max(1, tp + fn), 2), "tp": tp, "fp": fp,
           "fn": fn, "schemaInvalid": invalid, "rejectedProposals": rejected, "requestErrors": errors,
           "wallMsMedian": statistics.median(walls) if walls else None,
           "wallMsP95": sorted(walls)[int(0.95 * (len(walls) - 1))] if walls else None,
           "wallMsMax": max(walls) if walls else None,
           "promptTokensTotal": sum(ptoks), "completionTokensTotal": sum(ctoks),
           "completionTokensMax": max(ctoks) if ctoks else None}
    if out_path:
        Path(out_path).write_text(json.dumps({"summary": res, "cases": rows}, indent=2) + "\n")
    return res


def run_rules(cases: list | None = None) -> dict:
    tp = fp = fn = 0
    lat = []
    for text, exp in cases or CASES:
        t0 = time.perf_counter()
        pred = {key(p) for p in rule_based_proposals(text)}
        lat.append((time.perf_counter() - t0) * 1000)
        a, b, c = score(pred, exp)
        tp, fp, fn = tp + a, fp + b, fn + c
    return {"mode": "rule_based", "precision": round(tp / max(1, tp + fp), 2), "recall": round(tp / max(1, tp + fn), 2),
            "fp": fp, "fn": fn, "medianMs": round(statistics.median(lat), 2)}


def run_model(base: str, tag: str, timeout: float, cases: list | None = None) -> dict:
    m = OllamaStyleModel(base_url=base, model=tag, timeout_s=timeout)
    tp = fp = fn = invalid = rejected = 0
    walls, evals, loads = [], [], []
    m.chat_json(_SYSTEM, "warm up: I'm a medium", PROPOSAL_SCHEMA)  # first call loads weights; reported separately
    for text, exp in cases or CASES:
        raw, t = m.chat_json(_SYSTEM, text, PROPOSAL_SCHEMA)
        walls.append(t["wallMs"])
        evals.append(t.get("evalMs", 0))
        loads.append(t.get("loadMs", 0))
        try:
            props, rej = validate_proposals(raw, text)
        except ValueError:
            invalid += 1
            props, rej = [], 0
        rejected += rej
        a, b, c = score({key(p) for p in props}, exp)
        tp, fp, fn = tp + a, fp + b, fn + c
    return {"mode": "model", "model": tag, "precision": round(tp / max(1, tp + fp), 2), "recall": round(tp / max(1, tp + fn), 2),
            "fp": fp, "fn": fn, "schemaInvalid": invalid, "rejectedProposals": rejected,
            "wallMsMedian": statistics.median(walls), "wallMsP95": sorted(walls)[int(0.95 * (len(walls) - 1))],
            "evalMsMedian": statistics.median(evals), "loadMsMax": max(loads)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", nargs="*", default=["gemma4:e4b", "gemma4:e2b"])
    ap.add_argument("--base", default="http://127.0.0.1:11434")
    ap.add_argument("--timeout", type=float, default=60)
    ap.add_argument("--remote", action="store_true", help="use STYLE_REMOTE_* env (OpenAI-compatible); skips Ollama")
    ap.add_argument("--max-calls", type=int, default=18)
    ap.add_argument("--set", choices=["base", "regression", "all"], default="base",
                    help="base: the 18 labelled cases; regression: known action-interpretation failures")
    ap.add_argument("--out", help="write per-case JSON here (remote mode)")
    a = ap.parse_args()
    cases = {"base": CASES, "regression": regression_cases(), "all": CASES + regression_cases()}[a.set]
    report = {"set": a.set, "cases": len(cases), "results": [run_rules(cases)]}
    if a.remote:
        report["results"].append(run_remote(a.max_calls, a.out, cases))
        print(json.dumps(report, indent=2))
        return 0
    try:
        tags = {m["name"] for m in httpx.get(f"{a.base}/api/tags", timeout=3).json().get("models", [])}
        report["ollama"] = "reachable"
    except (httpx.HTTPError, ValueError):
        tags, report["ollama"] = set(), "unreachable"
    for tag in a.models:
        if tag not in tags:
            report["results"].append({"mode": "model", "model": tag, "skipped": "not installed or Ollama unreachable"})
            continue
        try:
            report["results"].append(run_model(a.base, tag, a.timeout, cases))
        except Exception as exc:  # noqa: BLE001
            report["results"].append({"mode": "model", "model": tag, "error": f"{type(exc).__name__}: {exc}"[:200]})
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
