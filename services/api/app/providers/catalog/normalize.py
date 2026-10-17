from __future__ import annotations

import hashlib
import re
import uuid
from datetime import datetime, timezone
from typing import Any

from .types import Evidence, Listing, Money, SizeInfo


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def dollars_to_minor(amount: Any, currency: str = "USD") -> Money | None:
    if amount is None:
        return None
    try:
        # SoleScout returns whole USD; keep integers exact.
        dollars = float(amount)
    except (TypeError, ValueError):
        return None
    return {"amountMinor": int(round(dollars * 100)), "currency": currency}


def stable_id(*parts: str) -> str:
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:24]
    return f"lst_{digest}"


def evidence_id(*parts: str) -> str:
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:24]
    return f"ev_{digest}"


_LEATHER_RE = re.compile(r"\bleather\b", re.I)


def material_hint_from_title(title: str | None) -> str | None:
    if not title:
        return None
    # Check faux leather before bare leather.
    if re.search(r"\bfaux\s+leather\b", title, re.I):
        return "faux leather (title mention)"
    if _LEATHER_RE.search(title):
        # Title text only — not composition certification.
        return "leather (title mention)"
    return None


def availability_from_sizes(
    sizes_in_stock: list[Any] | None, stores: list[Any] | None
) -> str:
    if sizes_in_stock:
        return "in_stock"
    if stores:
        # A named store without sizes still does not prove stock.
        return "unknown"
    return "unknown"


def size_from_variant(variant_id: str | None, sizes_in_stock: list[Any] | None) -> SizeInfo | None:
    if variant_id:
        return {"raw": variant_id, "system": None}
    if sizes_in_stock and len(sizes_in_stock) == 1:
        raw = str(sizes_in_stock[0].get("size") or "").strip()
        if raw:
            return {"raw": raw, "system": None}
    return None


def new_opaque_id(prefix: str = "id") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


def build_evidence(
    *,
    provider: str,
    source_url: str | None,
    retrieved_at: str,
    claims: list[dict[str, Any]],
    raw_ref: str | None,
    source_type: str = "merchant_api",
) -> Evidence:
    eid = evidence_id(provider, source_url or "", retrieved_at, raw_ref or "")
    return {
        "id": eid,
        "sourceType": source_type,  # type: ignore[typeddict-item]
        "sourceUrl": source_url,
        "provider": provider,
        "retrievedAt": retrieved_at,
        "claims": claims,  # type: ignore[typeddict-item]
        "rawResponseRef": raw_ref,
    }
