"""Session ownership, revisioned compare-and-update, and idempotency (SRS section 13)."""

from __future__ import annotations

import hashlib
import json
import secrets
from datetime import datetime, timezone
from typing import Any

from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from app.contracts import Preferences, ShoppingSession


class ApiProblem(Exception):
    def __init__(self, status: int, code: str, message: str, retryable: bool = False):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.retryable = retryable


def now() -> datetime:
    return datetime.now(timezone.utc)


def new_id(prefix: str) -> str:
    return f"{prefix}_{secrets.token_urlsafe(12)}"


def to_session(doc: dict) -> ShoppingSession:
    from app.contracts.base import from_doc

    return from_doc(ShoppingSession, doc)


def create_session(db: Any, owner_id: str) -> ShoppingSession:
    t = now()
    s = ShoppingSession(
        id=new_id("ses"),
        owner_id=owner_id,
        revision=1,
        media_id=None,
        selected_garment_id=None,
        preferences=Preferences(),
        active_search_id=None,
        created_at=t,
        updated_at=t,
    )
    db.sessions.insert_one({"_id": s.id, **s.wire()})
    return s


def get_owned(db: Any, session_id: str, owner_id: str) -> dict:
    doc = db.sessions.find_one({"_id": session_id, "ownerId": owner_id})
    if not doc:
        raise ApiProblem(404, "not_found", "Session not found")
    return doc


def _request_hash(payload: Any) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


def idempotent(db: Any, owner_id: str, scope: str, key: str | None, payload: Any):
    """Return (stored_response | None, commit_fn). Same key + same payload replays;
    same key + different payload is a 409."""
    if not key:
        return None, lambda resp: None
    if len(key) > 100:
        raise ApiProblem(422, "invalid_idempotency_key", "Idempotency key too long")
    h = _request_hash(payload)
    existing = db.idempotency.find_one({"ownerId": owner_id, "scope": scope, "key": key})
    if existing:
        if existing["requestHash"] != h:
            raise ApiProblem(409, "idempotency_conflict", "Idempotency key reused with different content")
        if existing.get("response") is not None:
            return existing["response"], lambda resp: None

    def commit(resp: Any) -> None:
        try:
            db.idempotency.insert_one(
                {"ownerId": owner_id, "scope": scope, "key": key, "requestHash": h, "response": resp, "createdAt": now()}
            )
        except DuplicateKeyError:
            pass

    return None, commit


def cas_update(db: Any, session_id: str, owner_id: str, expected_revision: int, set_fields: dict) -> dict:
    """Atomic compare-and-update on revision. Stale revision -> 409."""
    set_fields = {**set_fields, "updatedAt": now().isoformat()}
    doc = db.sessions.find_one_and_update(
        {"_id": session_id, "ownerId": owner_id, "revision": expected_revision},
        {"$set": set_fields, "$inc": {"revision": 1}},
        return_document=ReturnDocument.AFTER,
    )
    if doc is None:
        get_owned(db, session_id, owner_id)  # 404 if not owned
        raise ApiProblem(409, "stale_revision", "Session changed since you loaded it; refresh and retry", retryable=True)
    return doc


def supersede_active_search(db: Any, session_doc_before: dict) -> None:
    sid = session_doc_before.get("activeSearchId")
    if sid:
        db.search_jobs.update_one(
            {"_id": sid, "status": {"$in": ["queued", "running"]}},
            {"$set": {"status": "superseded", "finishedAt": now().isoformat()}},
        )
