"""Export canonical Pydantic contracts to packages/contracts/clipcart.schema.json.

Run: services/api/.venv/bin/python scripts/gen_contracts.py
Then: (cd apps/web && npm run gen:types) to regenerate TypeScript.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services" / "api"))

from pydantic.json_schema import models_json_schema  # noqa: E402

from app import contracts as C  # noqa: E402

MODELS = [
    C.Preferences, C.PreferencePatch, C.ShoppingSession, C.MediaAsset, C.FrameRef, C.GarmentObservation, C.Garment,
    C.AnalysisJob, C.Evidence, C.Listing, C.Recommendation, C.SearchJob, C.AgentEvent, C.ReferralEvent, C.ApiError,
    C.ResearchJob, C.ResearchSubmission,
    C.StyleEvent, C.StyleMemory, C.StyleProfileView, C.StyleProposal, C.StyleModelInfo, C.StyleNoteResult,
    C.StyleInterpretations, C.InterpretationRunResult, C.CategoriesResponse,
    C.DemoCatalogItem, C.DemoMerchantOrder, C.DemoTransferRequest, C.DemoReceipt,
]

_, schema = models_json_schema([(m, "serialization") for m in MODELS], by_alias=True, title="ClipCart contracts")
def _strip_property_titles(node):
    if isinstance(node, dict):
        props = node.get("properties")
        if isinstance(props, dict):
            for v in props.values():
                if isinstance(v, dict):
                    v.pop("title", None)
        for v in node.values():
            _strip_property_titles(v)
    elif isinstance(node, list):
        for v in node:
            _strip_property_titles(v)


_strip_property_titles(schema)
schema["$comment"] = "Generated from services/api/app/contracts by scripts/gen_contracts.py. Do not edit."
out = ROOT / "packages" / "contracts" / "clipcart.schema.json"
out.write_text(json.dumps(schema, indent=2, sort_keys=True) + "\n")
print(f"wrote {out.relative_to(ROOT)} with {len(schema.get('$defs', {}))} definitions")
