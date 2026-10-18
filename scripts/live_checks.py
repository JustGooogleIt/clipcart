"""Bounded live provider checks. Prints summaries only; never prints credentials.

    services/api/.venv/bin/python scripts/live_checks.py --image path/to/garment.jpg [--only perceptron,grok,atlas]

Spend per run: Perceptron <= 1 detect + 1 attribute call (one frame);
Grok <= 2 workers x 3 rounds; SoleScout calls are free. A missing variable
skips that check and names it.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services" / "api"))

from app.config import load_settings  # noqa: E402  (loads .env without printing it)

S = load_settings()


def perceptron_check(image: Path) -> dict:
    if not os.getenv("PERCEPTRON_API_KEY"):
        return {"check": "perceptron", "status": "skipped", "missing": "PERCEPTRON_API_KEY"}
    import perceptron
    from PIL import Image

    from app.media.context import RequestContext
    from app.media.service import MediaService
    from app.media.storage import LocalAssetStore
    from app.providers.perceptron.adapter import PerceptronPerceptionProvider
    from app.providers.perceptron.sdk import SdkBackend

    with tempfile.TemporaryDirectory() as root, open(image, "rb") as fh:
        media = MediaService(LocalAssetStore(root))
        asset = media.ingest(fh, "live-check")
        frames = media.extract_frames(asset.id, "live-check", max_frames=1)
        perceptron.configure(max_tokens=S.perceptron_max_tokens)
        prov = PerceptronPerceptionProvider(
            media, SdkBackend(model=S.perceptron_model, request_timeout_s=40), mode="live",
            model_id=S.perceptron_model, max_frames=1, max_attribute_calls=1, max_concurrency=1,
        )
        t0 = time.monotonic()
        res = prov.analyze(frames, ["jacket", "top", "bag"], RequestContext.with_timeout("live-check", "live", 90))
        obs = []
        for o in res.observations:
            crop = media.get_crop(o.crop_asset_id, "live-check")
            with Image.open(media.store.path(o.crop_asset_id, "live-check")) as im:
                ok_crop = im.size == (crop.width, crop.height)
            obs.append({
                "category": o.category, "rawLabel": o.raw_label, "box01": [round(v, 3) for v in o.box01],
                "cropPx": [crop.width, crop.height], "cropMatchesFile": ok_crop, "attributes": o.observed_attributes,
                "visibleText": o.visible_text, "providerRequestId": o.provider_request_id,
            })
        return {
            "check": "perceptron", "model": S.perceptron_model, "status": res.status, "elapsedS": round(time.monotonic() - t0, 1),
            "frame": [frames[0].width, frames[0].height], "observations": obs, "droppedDetections": res.dropped_detections,
            "requests": [{"purpose": r.purpose, "outcome": r.outcome, "requestId": r.provider_request_id,
                          "errorCode": r.error_code, "usage": r.usage} for r in res.requests],
            "issues": [i.model_dump() for i in res.issues],
        }


def grok_check() -> dict:
    if not os.getenv("XAI_API_KEY"):
        return {"check": "grok", "status": "skipped", "missing": "XAI_API_KEY"}
    from app.contracts import Preferences, SearchBudget
    from app.providers.catalog import get_catalog_provider
    from app.providers.grok.client import GrokClient
    from app.providers.status import ProviderStatus
    from app.shopping.budget import BudgetLedger
    from app.shopping.pipeline import run_search
    from app.shopping.rules import GarmentProfile

    catalog = get_catalog_provider("solescout")
    seen_urls: set[str] = set()
    orig_search, orig_detail = catalog.search, catalog.get_details

    def search(q, f, n):
        r = orig_search(q, f, n)
        seen_urls.update(x["canonicalUrl"] for x in r.listings)
        return r

    def detail(slug, v=None):
        r = orig_detail(slug, v)
        seen_urls.update(x["canonicalUrl"] for x in r.listings)
        seen_urls.update(s.get("url") for s in r.diagnostics.get("stores") or [] if s.get("url"))
        if r.diagnostics.get("comparison_url"):
            seen_urls.add(r.diagnostics["comparison_url"])
        return r

    catalog.search, catalog.get_details = search, detail
    events: list[str] = []
    grok_status = ProviderStatus("grok", True)
    ledger = BudgetLedger(SearchBudget(), time.monotonic() + 60)
    out = run_search(
        search_id="live-check", garment_id="g",
        profile=GarmentProfile(category="jacket", colors=["black"], description="black nylon bomber"),
        prefs=Preferences(max_item_price_minor=30000), provider=catalog, ledger=ledger,
        emit=lambda st, sm, **k: events.append(f"[{k.get('worker', 'system')}] {sm}"),
        catalog_status=ProviderStatus("solescout", True), grok_status=grok_status,
        grok_client_factory=lambda: GrokClient(model=S.xai_model, base_url=S.xai_base_url),
        is_current=lambda: True,
    )
    by_id = {L.id: L for L in out.listings}
    link_urls = {t.url for t in out.links}
    grounded = all(L.canonical_url in seen_urls for L in out.listings) and link_urls <= seen_urls
    return {
        "check": "grok", "model": S.xai_model, "status": out.status, "workerModes": out.worker_modes,
        "grokMode": grok_status.mode, "grokCalls": grok_status.calls, "grokFailures": grok_status.failures,
        "traceIds": [r["traceId"] for r in grok_status.snapshot()["recent"] if r["traceId"]][:6],
        "budget": ledger.budget.model_dump(),
        "groundedInCatalog": grounded, "everyResultHasEvidence": all(by_id[r.listing_id].evidence_ids for r in out.recommendations),
        "results": [{"section": r.section, "tier": r.identity_tier, "title": by_id[r.listing_id].title,
                     "price": r.links[0].price_note if r.links else None, "foundBy": r.found_by} for r in out.recommendations],
        "events": events,
    }


def atlas_check() -> dict:
    """Connect with the app's settings, round-trip a marker document, and make sure the app's indexes exist.

    Prints only the host, never the URI, user name or password.
    """
    uri = S.mongodb_uri
    if not uri:
        return {"check": "atlas", "status": "skipped", "missing": "MONGODB_URI"}
    import pymongo
    from pymongo.uri_parser import parse_uri

    from app.storage.db import COLLECTIONS, ensure_indexes

    parsed = parse_uri(uri)
    hosts = [h for h, _ in parsed["nodelist"]] or ["(srv)"]
    tls = bool(parsed["options"].get("tls") or parsed["options"].get("ssl") or uri.startswith("mongodb+srv://"))
    client = pymongo.MongoClient(uri, serverSelectionTimeoutMS=10000, appname="clipcart-live-check")
    db = client[S.mongodb_db]
    t0 = time.monotonic()
    db.command("ping")
    version = client.server_info().get("version")
    marker = {"_id": f"check-{uuid.uuid4().hex[:8]}", "at": time.time()}
    db["_healthcheck"].insert_one(marker)
    back = db["_healthcheck"].find_one({"_id": marker["_id"]})
    db["_healthcheck"].delete_one({"_id": marker["_id"]})
    round_trip = round(time.monotonic() - t0, 2)
    ensure_indexes(db)  # idempotent; the app does the same at startup
    indexed = {c: len(db[c].index_information()) for c in COLLECTIONS if c in db.list_collection_names()}
    client.close()
    return {"check": "atlas", "status": "ok" if back else "failed", "dbMode": S.db_mode, "database": S.mongodb_db,
            "host": hosts[0].split(".", 1)[-1] if S.db_mode == "atlas" else hosts[0], "tls": tls,
            "serverVersion": version, "roundTripS": round_trip, "indexesPerCollection": indexed}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--image", type=Path, help="real garment photo (JPEG/PNG) for the Perceptron check")
    ap.add_argument("--only", default="perceptron,grok,atlas")
    a = ap.parse_args()
    results = []
    for name in a.only.split(","):
        try:
            if name == "perceptron":
                results.append(perceptron_check(a.image) if a.image else {"check": name, "status": "skipped", "missing": "--image"})
            elif name == "grok":
                results.append(grok_check())
            elif name == "atlas":
                results.append(atlas_check())
        except Exception as exc:  # noqa: BLE001
            results.append({"check": name, "status": "error", "error": f"{type(exc).__name__}: {str(exc)[:200]}"})
    print(json.dumps(results, indent=2, default=str))
    return 0 if all(r["status"] in ("ok", "completed", "partial", "skipped") for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
