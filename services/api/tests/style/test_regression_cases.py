"""The saved Gemma action-interpretation failures stay well-formed and keep documenting what validation can't catch."""

import json
from pathlib import Path

from app.style.model import KINDS, validate_proposals

FILE = Path(__file__).resolve().parents[4] / "scripts" / "experiments" / "style_regression_cases.json"


def cases():
    return json.loads(FILE.read_text())["cases"]


def test_regression_file_is_well_formed():
    cs = cases()
    assert len({c["id"] for c in cs}) == len(cs) >= 6
    for c in cs:
        for kind, _value, action in c["expected"]:
            assert kind in KINDS and action in ("add", "set", "remove")


def test_recorded_avoid_as_remove_passes_validation():
    """Validation checks grounding, not intent: a misread 'remove' is well-formed and quoted.

    Notes never save, so the UI must show remove proposals distinctly and let the shopper decide.
    """
    hits = 0
    for c in cases():
        if c["failure"] != "avoid_read_as_remove" or not c["observed"]:
            continue
        props, _ = validate_proposals(c["observed"]["raw"], c["text"])
        got = {(p.kind, p.value["raw"] if isinstance(p.value, dict) else str(p.value), p.action) for p in props}
        assert got == {tuple(x) for x in c["observed"]["validatedProposals"]}
        assert any(a == "remove" for _, _, a in got) and not any(a == "remove" for _, _, a in c["expected"])
        hits += 1
    assert hits == 3
