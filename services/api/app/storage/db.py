"""MongoDB access. Atlas (or any MongoDB) when MONGODB_URI is set; otherwise an
in-process mongomock database that is explicitly reported as local_memory and
is NOT Atlas-track completion (SRS section 4)."""

from __future__ import annotations

from typing import Any

import pymongo
from pymongo import ASCENDING, DESCENDING

from app.config import Settings

COLLECTIONS = (
    "sessions",
    "media_assets",
    "analysis_jobs",
    "garment_observations",
    "garments",
    "offers",
    "listings",
    "evidence",
    "search_jobs",
    "agent_events",
    "recommendations",
    "outbound_links",
    "referrals",
    "idempotency",
)


def connect(settings: Settings) -> Any:
    if settings.mongodb_uri:
        client = pymongo.MongoClient(settings.mongodb_uri, serverSelectionTimeoutMS=8000, appname="clipcart")
    else:
        import mongomock

        client = mongomock.MongoClient()
    db = client[settings.mongodb_db]
    ensure_indexes(db)
    return db


def ensure_indexes(db: Any) -> None:
    db.sessions.create_index([("ownerId", ASCENDING)])
    db.idempotency.create_index([("ownerId", ASCENDING), ("scope", ASCENDING), ("key", ASCENDING)], unique=True)
    db.search_jobs.create_index([("status", ASCENDING), ("leaseExpiresAt", ASCENDING)])
    db.search_jobs.create_index([("sessionId", ASCENDING), ("createdAt", DESCENDING)])
    db.agent_events.create_index([("jobId", ASCENDING), ("sequence", ASCENDING)], unique=True)
    db.listings.create_index([("offerKey", ASCENDING), ("checkedAt", DESCENDING)])
    # variantKey is "" for a product-level offer: an explicit null strategy for the unique index.
    db.offers.create_index(
        [("provider", ASCENDING), ("providerListingId", ASCENDING), ("variantKey", ASCENDING)], unique=True
    )
    db.recommendations.create_index([("searchId", ASCENDING), ("rank", ASCENDING)])
    db.garments.create_index([("sessionId", ASCENDING)])
    db.garment_observations.create_index([("mediaId", ASCENDING)])
    db.referrals.create_index([("sessionId", ASCENDING), ("occurredAt", DESCENDING)])


def ping(db: Any) -> bool:
    try:
        db.command("ping")
        return True
    except Exception:  # noqa: BLE001
        return False
