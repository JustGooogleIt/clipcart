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

from app.style.model import PROPOSAL_SCHEMA, _SYSTEM, OllamaStyleModel, rule_based_proposals, validate_proposals  # noqa: E402

CASES = [
    ("I'm a medium and I never wear leather", {("size", "M"), ("material_avoid", "leather")}),
    ("No orange please, I hate it", {("color_avoid", "orange")}),
    ("I love black and navy, budget of $150", {("color_like", "black"), ("color_like", "navy"), ("budget_max", "15000")}),
    ("Women's fit, size 8", {("fit", "womens"), ("size", "8")}),
    ("Actually leather is fine now", set()),  # a removal, not an add; expected no add proposals
    ("I like Acne Studios but avoid Gucci", {("brand_like", "Acne Studios"), ("brand_avoid", "Gucci")}),
    ("Nothing in wool, I'm allergic to wool", {("material_avoid", "wool")}),
    ("My name is Maria and I usually buy tops", set()),  # must not infer fit from a name
    ("I'm 6 foot tall and broad shouldered", set()),  # must not infer a size from body description
    ("Under $80, no polyester, prefer green", {("budget_max", "8000"), ("material_avoid", "polyester"), ("color_like", "green")}),
]


def key(p) -> tuple[str, str]:
    v = p.value
    if isinstance(v, dict):
        v = v.get("raw") or str(v.get("amountMinor"))
    return (p.kind, str(v))


def score(pred: set, exp: set) -> tuple[int, int, int]:
    return len(pred & exp), len(pred - exp), len(exp - pred)


def run_rules() -> dict:
    tp = fp = fn = 0
    lat = []
    for text, exp in CASES:
        t0 = time.perf_counter()
        pred = {key(p) for p in rule_based_proposals(text)}
        lat.append((time.perf_counter() - t0) * 1000)
        a, b, c = score(pred, exp)
        tp, fp, fn = tp + a, fp + b, fn + c
    return {"mode": "rule_based", "precision": round(tp / max(1, tp + fp), 2), "recall": round(tp / max(1, tp + fn), 2),
            "fp": fp, "fn": fn, "medianMs": round(statistics.median(lat), 2)}


def run_model(base: str, tag: str, timeout: float) -> dict:
    m = OllamaStyleModel(base_url=base, model=tag, timeout_s=timeout)
    tp = fp = fn = invalid = rejected = 0
    walls, evals, loads = [], [], []
    m.chat_json(_SYSTEM, "warm up: I'm a medium", PROPOSAL_SCHEMA)  # first call loads weights; reported separately
    for text, exp in CASES:
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
    a = ap.parse_args()
    report = {"cases": len(CASES), "results": [run_rules()]}
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
            report["results"].append(run_model(a.base, tag, a.timeout))
        except Exception as exc:  # noqa: BLE001
            report["results"].append({"mode": "model", "model": tag, "error": f"{type(exc).__name__}: {exc}"[:200]})
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
