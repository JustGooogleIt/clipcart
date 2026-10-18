"""Style memory service: append-only events, stated/inferred memories, deterministic inference, compact profile.

Invariants:
- Everything is keyed by ownerId; reads and writes filter on it.
- retailer_click never creates a purchase or a memory.
- verified_order is created only by ``record_verified_order`` (server-side, paid orders).
- Stated memories override inferred ones; a user-removed memory is never re-inferred.
"""

from __future__ import annotations

import hashlib
from collections import defaultdict
from typing import Any

from pymongo import DESCENDING

from app.contracts import StyleProfile
from app.contracts.style_memory import OwnedItem, ProfileEntry, StyleEvent, StyleItem, StyleMemory
from app.sessions.service import ApiProblem, new_id, now

from .vocab import ONE_ACTIVE, PAIRS, InvalidMemory, colors_in, normalize, same_value

LIKE_THRESHOLD = 2  # saved/purchased items supporting a brand or color
AVOID_THRESHOLD = 2  # rejected items
PURCHASE_BRAND_THRESHOLD = 1
API_EVENT_TYPES = {"saved_item", "rejected_item", "user_confirmed_purchase"}
_SOURCE_FOR = {"saved_item": "result_card", "rejected_item": "result_card", "user_confirmed_purchase": "purchase_confirmation"}


def _clean(doc: dict) -> dict:
    return {k: v for k, v in doc.items() if k not in ("_id", "ownerId")}


def _ev(doc: dict) -> StyleEvent:
    return StyleEvent.model_validate(_clean(doc))


def _mem(doc: dict) -> StyleMemory:
    return StyleMemory.model_validate(_clean(doc))


def _key(value: Any) -> str:
    return str(value).lower() if isinstance(value, str) else repr(sorted(value.items())) if isinstance(value, dict) else repr(value)


# ------------------------------------------------------------------ items from stored records
def item_from_recommendation(db, owner: str, recommendation_id: str) -> StyleItem:
    rec = db.recommendations.find_one({"id": recommendation_id, "ownerId": owner})
    if not rec:
        raise ApiProblem(404, "not_found", "Result not found")
    L = db.listings.find_one({"id": rec["listingId"]}) or {}
    g = db.garments.find_one({"id": rec.get("garmentId"), "ownerId": owner}) or {}
    host = _host(L.get("canonicalUrl"))
    pk = f"{L.get('provider')}:{L.get('providerListingId')}" if L.get("providerListingId") else None
    return StyleItem(
        recommendation_id=recommendation_id, listing_id=rec["listingId"], offer_key=L.get("offerKey"), product_key=pk,
        title=str(L.get("title") or "Untitled")[:200], brand=L.get("brand"), domain=host, category=g.get("category"),
    )


# ------------------------------------------------------------------ events
def add_event(db, owner: str, etype: str, *, origin: str, source: str, item: StyleItem | None = None,
              memory_id: str | None = None, link_kind: str | None = None, order_id: str | None = None) -> StyleEvent:
    ev = StyleEvent(id=new_id("sev"), type=etype, origin=origin, source=source, occurred_at=now(), item=item,
                    memory_id=memory_id, link_kind=link_kind, order_id=order_id)
    db.style_events.insert_one({"_id": ev.id, "ownerId": owner, **ev.wire()})
    return ev


def record_api_event(db, owner: str, etype: str, recommendation_id: str) -> tuple[StyleEvent, dict]:
    if etype not in API_EVENT_TYPES:
        raise ApiProblem(422, "event_type_not_allowed",
                         "Only saved_item, rejected_item and user_confirmed_purchase can be recorded here")
    item = item_from_recommendation(db, owner, recommendation_id)
    ev = add_event(db, owner, etype, origin="stated", source=_SOURCE_FOR[etype], item=item)
    return ev, rebuild_inferred(db, owner)


def _host(url: str | None) -> str | None:
    from urllib.parse import urlparse

    return (urlparse(url or "").hostname or "").removeprefix("www.") or None


def record_retailer_click(db, owner: str, listing_id: str, recommendation_id: str | None, link_kind: str,
                          target_url: str | None = None) -> StyleEvent:
    """Server-side only, from /go. A click is interest, never a purchase, and creates no memory.

    ``domain`` is the host the shopper was sent to (the redirect target), falling back to the listing's URL.
    """
    L = db.listings.find_one({"id": listing_id}) or {}
    pk = f"{L.get('provider')}:{L.get('providerListingId')}" if L.get("providerListingId") else None
    item = StyleItem(recommendation_id=recommendation_id, listing_id=listing_id, offer_key=L.get("offerKey"),
                     product_key=pk, title=str(L.get("title") or "Untitled")[:200], brand=L.get("brand"),
                     domain=_host(target_url) or _host(L.get("canonicalUrl")))
    return add_event(db, owner, "retailer_click", origin="inferred", source="outbound_link", item=item, link_kind=link_kind)


def record_verified_order(db, owner: str, order: dict, item: StyleItem) -> tuple[StyleEvent, dict]:
    """Server-side hook for verified ClipCart demo orders. Requires a paid order owned by this owner."""
    if order.get("ownerId") != owner or order.get("status") != "paid" or not order.get("paymentSignature"):
        raise ValueError("only a verified, paid order of this owner can be recorded")
    ev = add_event(db, owner, "verified_order", origin="stated", source="clipcart_order", item=item, order_id=order["id"])
    return ev, rebuild_inferred(db, owner)


def delete_event(db, owner: str, event_id: str) -> dict:
    res = db.style_events.delete_one({"_id": event_id, "ownerId": owner})
    if not res.deleted_count:
        raise ApiProblem(404, "not_found", "Event not found")
    return rebuild_inferred(db, owner)


def list_events(db, owner: str, limit: int = 50) -> list[dict]:
    cur = db.style_events.find({"ownerId": owner}).sort("occurredAt", DESCENDING).limit(max(1, min(limit, 200)))
    return [_ev(d).wire() for d in cur]


# ------------------------------------------------------------------ memories
def add_stated_memory(db, owner: str, kind: str, value: Any, source: str) -> tuple[StyleMemory, list[str]]:
    try:
        value = normalize(kind, value)
    except InvalidMemory as exc:
        raise ApiProblem(422, "invalid_memory", str(exc)) from None
    t = now()
    active = list(db.style_memories.find({"ownerId": owner, "status": "active"}))
    for d in active:  # same stated memory already active: refresh instead of duplicating
        if d["origin"] == "stated" and d["kind"] == kind and same_value(d["value"], value):
            db.style_memories.update_one({"_id": d["_id"]}, {"$set": {"updatedAt": t.isoformat()}})
            return _mem(db.style_memories.find_one({"_id": d["_id"]})), []
    mid = new_id("mem")
    ev = add_event(db, owner, "explicit_preference", origin="stated", source=source, memory_id=mid)
    mem = StyleMemory(id=mid, kind=kind, value=value, origin="stated", source=source, status="active",
                      source_event_ids=[ev.id], evidence_count=1, created_at=t, updated_at=t)
    overridden = []
    for d in active:
        conflict = (
            (kind in ONE_ACTIVE and d["kind"] == kind)
            or (d["kind"] == kind and same_value(d["value"], value))  # inferred twin replaced by the stated one
            or (PAIRS.get(kind) == d["kind"] and same_value(d["value"], value))
        )
        if conflict:
            db.style_memories.update_one({"_id": d["_id"]}, {"$set": {"status": "overridden", "overriddenBy": mid,
                                                                       "updatedAt": t.isoformat()}})
            overridden.append(d["id"])
    db.style_memories.insert_one({"_id": mid, "ownerId": owner, **mem.wire()})
    return mem, overridden


def remove_memory(db, owner: str, memory_id: str) -> StyleMemory:
    d = db.style_memories.find_one({"_id": memory_id, "ownerId": owner})
    if not d:
        raise ApiProblem(404, "not_found", "Memory not found")
    db.style_memories.update_one({"_id": memory_id}, {"$set": {"status": "removed", "updatedAt": now().isoformat()}})
    rebuild_inferred(db, owner)  # an overridden inferred twin may become active again, or stay suppressed
    return _mem(db.style_memories.find_one({"_id": memory_id}))


def list_memories(db, owner: str, status: str = "active") -> list[dict]:
    q: dict = {"ownerId": owner}
    if status != "all":
        q["status"] = status
    return [_mem(d).wire() for d in db.style_memories.find(q).sort("updatedAt", DESCENDING)]


def _inferred_id(owner: str, kind: str, value: Any) -> str:
    return "mem_i" + hashlib.sha256(f"{owner}|{kind}|{_key(value)}".encode()).hexdigest()[:20]


def rebuild_inferred(db, owner: str) -> dict:
    """Recompute inferred memories from events. Deterministic; removed memories suppress re-inference."""
    support: dict[tuple[str, str], list[str]] = defaultdict(list)
    display: dict[tuple[str, str], Any] = {}
    purchase_brand: dict[str, list[str]] = defaultdict(list)
    for e in db.style_events.find({"ownerId": owner, "type": {"$in": ["saved_item", "rejected_item",
                                                                       "user_confirmed_purchase", "verified_order"]}}):
        item = e.get("item") or {}
        like = e["type"] != "rejected_item"
        kinds = ("brand_like", "color_like") if like else ("brand_avoid", "color_avoid")
        brand = (item.get("brand") or "").strip()
        if brand:
            k = (kinds[0], brand.lower())
            support[k].append(e["id"])
            display[k] = brand
            if e["type"] in ("user_confirmed_purchase", "verified_order"):
                purchase_brand[brand.lower()].append(e["id"])
        for c in colors_in(item.get("title")):
            support[(kinds[1], c)].append(e["id"])
            display[(kinds[1], c)] = c
    existing = {d["_id"]: d for d in db.style_memories.find({"ownerId": owner})}
    removed = {(d["kind"], _key(d["value"])) for d in existing.values() if d["status"] == "removed"}
    stated = [d for d in existing.values() if d["origin"] == "stated" and d["status"] == "active"]
    t = now().isoformat()
    want: dict[str, dict] = {}
    for (kind, vkey), ids in support.items():
        n = len(set(ids))
        threshold = AVOID_THRESHOLD if kind.endswith("_avoid") else LIKE_THRESHOLD
        if kind == "brand_like" and len(set(purchase_brand.get(vkey, []))) >= PURCHASE_BRAND_THRESHOLD:
            threshold = 1
        if n < threshold or (kind, vkey) in removed:
            continue
        value = display[(kind, vkey)]
        blocker = next((d for d in stated if (d["kind"] == kind and same_value(d["value"], value))
                        or (PAIRS.get(kind) == d["kind"] and same_value(d["value"], value))), None)
        mid = _inferred_id(owner, kind, value)
        src = "rejected_items" if kind.endswith("_avoid") else ("purchases" if purchase_brand.get(vkey) and kind == "brand_like" else "saved_items")
        want[mid] = {"id": mid, "kind": kind, "value": value, "origin": "inferred", "source": src,
                     "status": "overridden" if blocker else "active", "overriddenBy": blocker["id"] if blocker else None,
                     "sourceEventIds": sorted(set(ids))[:20], "evidenceCount": n}
    changes = {"added": [], "updated": [], "removed": []}
    for mid, d in existing.items():
        if d["origin"] == "inferred" and d["status"] != "removed" and mid not in want:
            db.style_memories.delete_one({"_id": mid})  # evidence gone: derived memory disappears
            changes["removed"].append(mid)
    for mid, w in want.items():
        old = existing.get(mid)
        if old is None:
            db.style_memories.insert_one({"_id": mid, "ownerId": owner, **w, "createdAt": t, "updatedAt": t})
            changes["added"].append(mid)
        elif old["status"] != "removed":
            fields = {k: w[k] for k in ("status", "overriddenBy", "sourceEventIds", "evidenceCount", "source")}
            if any(old.get(k) != v for k, v in fields.items()):
                db.style_memories.update_one({"_id": mid}, {"$set": {**fields, "updatedAt": t}})
                changes["updated"].append(mid)
    return changes


# ------------------------------------------------------------------ profile
def build_profile(db, owner: str) -> StyleProfile:
    active = [_mem(d) for d in db.style_memories.find({"ownerId": owner, "status": "active"})]

    def entries(kind: str) -> list[ProfileEntry]:
        ms = sorted((m for m in active if m.kind == kind),
                    key=lambda m: (m.origin != "stated", -m.evidence_count, -m.updated_at.timestamp()))
        return [ProfileEntry(value=m.value, origin=m.origin, memory_id=m.id,
                             evidence_count=m.evidence_count if m.origin == "inferred" else None) for m in ms[:5]]

    def one(kind: str) -> ProfileEntry | None:
        e = entries(kind)
        return e[0] if e else None

    owned = []
    for d in db.style_events.find({"ownerId": owner, "type": {"$in": ["user_confirmed_purchase", "verified_order"]}}) \
            .sort("occurredAt", DESCENDING).limit(5):
        it = d.get("item") or {}
        owned.append(OwnedItem(title=it.get("title") or "Untitled", brand=it.get("brand"), source=d["type"], at=d["occurredAt"]))
    rejected = []
    for d in db.style_events.find({"ownerId": owner, "type": "rejected_item"}).sort("occurredAt", DESCENDING).limit(200):
        k = (d.get("item") or {}).get("productKey")
        if k and k not in rejected:
            rejected.append(k)
    stamps = [m.updated_at for m in active]
    return StyleProfile(
        size=one("size"), fit=one("fit"), budget_max=one("budget_max"),
        colors_like=entries("color_like"), colors_avoid=entries("color_avoid"),
        materials_avoid=entries("material_avoid"), materials_like=entries("material_like"),
        brands_like=entries("brand_like"), brands_avoid=entries("brand_avoid"),
        recently_owned=owned, rejected_product_keys=rejected, updated_at=max(stamps) if stamps else None,
    )


def public_profile(profile: StyleProfile) -> dict:
    """Validated against StyleProfileView so the wire shape matches the generated UI types exactly."""
    from app.contracts import StyleProfileView

    d = profile.model_dump()
    d["rejected_offer_count"] = len(d.pop("rejected_product_keys", []))
    return StyleProfileView.model_validate(d).wire()
