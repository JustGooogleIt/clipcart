"""Live Perceptron smoke check.

    cd services/api
    PERCEPTRON_API_KEY=... python -m app.providers.perceptron.smoke path/to/image_or_clip

Ingests the file into a temporary owner-scoped store, extracts frames, makes
real Perceptron calls and prints the AnalysisResult JSON (camelCase). Exits
with status 2 and makes no request when credentials are missing.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import uuid

from app.media.context import RequestContext
from app.media.grouping import GarmentGrouper
from app.media.service import MediaService
from app.media.storage import LocalAssetStore

from .adapter import PerceptronPerceptionProvider
from .sdk import SdkBackend


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("path")
    ap.add_argument("--frames", type=int, default=4)
    ap.add_argument("--attributes", type=int, default=2, help="max attribute calls")
    ap.add_argument("--deadline", type=float, default=60.0)
    ap.add_argument("--model", default=os.getenv("PERCEPTRON_MODEL", "perceptron-mk1.5"))
    args = ap.parse_args(argv)

    if not os.getenv("PERCEPTRON_API_KEY"):
        print("PERCEPTRON_API_KEY is not set; no live request was made.", file=sys.stderr)
        return 2

    owner = "smoke-owner"
    with tempfile.TemporaryDirectory() as root, open(args.path, "rb") as fh:
        media = MediaService(LocalAssetStore(root))
        asset = media.ingest(fh, owner)
        frames = media.extract_frames(asset.id, owner, max_frames=args.frames)
        cuts = media.detect_shot_boundaries(asset.id, owner)
        provider = PerceptronPerceptionProvider(
            media,
            SdkBackend(model=args.model, request_timeout_s=min(30.0, args.deadline)),
            mode="live",
            model_id=args.model,
            max_frames=args.frames,
            max_attribute_calls=args.attributes,
        )
        ctx = RequestContext.with_timeout(owner, f"smoke-{uuid.uuid4().hex[:8]}", args.deadline)
        result = provider.analyze(frames, ["jacket", "top", "bag"], ctx)
        garments = GarmentGrouper().group(result.observations, cuts, session_id="smoke-session")
        out = {
            "media": asset.model_dump(mode="json", by_alias=True, exclude={"owner_id", "storage_key"}),
            "frames": [f.model_dump(mode="json", by_alias=True) for f in frames],
            "shotBoundariesMs": cuts,
            "analysis": result.model_dump(mode="json", by_alias=True),
            "garments": [g.model_dump(mode="json", by_alias=True) for g in garments],
        }
        print(json.dumps(out, indent=2))
        return 0 if result.status != "failed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
