#!/usr/bin/env python3
"""Smoke-check ClipCart catalog providers (live SoleScout or labeled fixtures)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services" / "api"))

from app.providers.catalog import (  # noqa: E402
    CatalogFilters,
    CatalogProviderError,
    get_catalog_provider,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider", default=None, help="solescout | fixture")
    parser.add_argument("--query", default="denim jacket")
    parser.add_argument("--limit", type=int, default=3)
    parser.add_argument("--detail", default=None, help="provider listing id / slug")
    parser.add_argument("--variant", default=None)
    parser.add_argument(
        "--resolve-first",
        action="store_true",
        help="After search, get_details on the first hit (honest destination)",
    )
    args = parser.parse_args()

    provider = get_catalog_provider(args.provider)
    filters = CatalogFilters(country="US", currency="USD")
    print(f"provider={provider.name}")

    try:
        if args.detail:
            result = provider.get_details(args.detail, args.variant)
        else:
            result = provider.search(args.query, filters, args.limit)
            if args.resolve_first and result.listings:
                slug = result.listings[0]["providerListingId"]
                detail = provider.get_details(slug, args.variant)
                payload = {
                    "mode": detail.mode,
                    "provider": detail.provider,
                    "query": args.query,
                    "resolvedFromSearch": slug,
                    "elapsed_ms": (result.elapsed_ms or 0) + (detail.elapsed_ms or 0),
                    "diagnostics": detail.diagnostics,
                    "listing_count": len(detail.listings),
                    "listings": detail.listings,
                    "evidence": detail.evidence,
                }
                print(json.dumps(payload, indent=2))
                return 0
    except CatalogProviderError as exc:
        print(json.dumps({"error": {"code": exc.code, "message": exc.message}}))
        return 2

    payload = {
        "mode": result.mode,
        "provider": result.provider,
        "query": result.query,
        "elapsed_ms": result.elapsed_ms,
        "diagnostics": result.diagnostics,
        "listing_count": len(result.listings),
        "listings": result.listings,
        "evidence": result.evidence,
    }
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
