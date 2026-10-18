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
    "style_events",
    "style_memories",
    "research_jobs",
    "demo_orders",
    "payment_signatures",
    "receipt_mint_attempts",
)


def connect(settings: Settings) -> Any:
    if settings.mongodb_uri:
        kwargs: dict[str, Any] = {"serverSelectionTimeoutMS": 8000, "appname": "clipcart"}
        try:
            import certifi

            kwargs["tlsCAFile"] = certifi.where()
        except ImportError:
            pass
        client = pymongo.MongoClient(settings.mongodb_uri, **kwargs)
    else:
        import mongomock

        client = mongomock.MongoClient()
    db = client[settings.mongodb_db]
    ensure_indexes(db)
    return db


def _drop_index_if_present(db: Any, collection: str, name: str) -> None:
    coll = db[collection]
    try:
        info = coll.index_information()
    except Exception:  # noqa: BLE001
        return
    if name in info:
        coll.drop_index(name)


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
    db.research_jobs.create_index([("sessionId", ASCENDING), ("createdAt", DESCENDING)])
    db.research_jobs.create_index([("status", ASCENDING), ("expiresAt", ASCENDING)])
    db.style_events.create_index([("ownerId", ASCENDING), ("occurredAt", DESCENDING)])
    db.style_events.create_index([("ownerId", ASCENDING), ("type", ASCENDING)])
    db.style_memories.create_index([("ownerId", ASCENDING), ("status", ASCENDING), ("kind", ASCENDING)])
    db.referrals.create_index([("sessionId", ASCENDING), ("occurredAt", DESCENDING)])
    db.demo_orders.create_index([("ownerId", ASCENDING), ("createdAt", DESCENDING)])
    db.demo_orders.create_index([("paymentReference", ASCENDING)], unique=True)
    # Paid signatures only. Sparse unique still indexes BSON null, so a second unpaid
    # order (paymentSignature: null) fails on real MongoDB with E11000.
    _drop_index_if_present(db, "demo_orders", "paymentSignature_1")
    db.demo_orders.create_index(
        [("paymentSignature", ASCENDING)],
        unique=True,
        name="paymentSignature_paid_unique",
        partialFilterExpression={"paymentSignature": {"$type": "string"}},
    )
    db.payment_signatures.create_index([("orderId", ASCENDING)])
    # One mint attempt record per demo order (atomic claim for cNFT receipts).
    db.receipt_mint_attempts.create_index([("orderId", ASCENDING)], unique=True)
    _drop_index_if_present(db, "receipt_mint_attempts", "mintSignature_1")
    db.receipt_mint_attempts.create_index(
        [("mintSignature", ASCENDING)],
        unique=True,
        name="mintSignature_present_unique",
        partialFilterExpression={"mintSignature": {"$type": "string"}},
    )


def ping(db: Any) -> bool:
    try:
        db.command("ping")
        return True
    except Exception:  # noqa: BLE001
        return False
