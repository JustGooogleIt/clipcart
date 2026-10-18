"""Validate an agent submission into labelled ResearchProduct records.

Never upgrades an agent claim into a ClipCart-verified fact:
- identity tier is at most "likely" (agent said exact) or "similar";
- a price is kept only with the page excerpt that shows it, as agent_observed;
- sizes and availability are only what the agent says the page showed;
- ClipCart checks the URL but does not fetch the page.
"""

from __future__ import annotations

import hashlib
import secrets
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from typing import Any

from pydantic import ValidationError

from app.contracts import (
    ConstraintCheck,
    Listing,
    Money,
    OutboundLink,
    Preferences,
    ResearchProduct,
    SizeStock,
    SubmittedProduct,
)
from app.contracts.research import ProductIdentifiers, RejectedItem, ResearchVariant

from .compare import group_offers
from app.shopping.rules import check_constraints, money_str, section_for, title_matches_category

from .urlsafety import AGGREGATOR_DOMAINS, UrlCheck, check_url

MAX_PRIMARY = 5
MAX_NEEDS = 5
FIRST_WARNING = {
    "agent": "Found by a research agent; ClipCart checked the link but did not open the page.",
    "catalog": "From SoleScout's store record; ClipCart checked the link but did not open the store page.",
    "manual_import": "Imported manually; ClipCart checked the link but did not open the page.",
}


def _availability(sp: SubmittedProduct) -> str:
    if sp.availability != "unknown" or not sp.variants:
        return sp.availability
    states = [v.available for v in sp.variants]
    if any(a is True for a in states):
        return "in_stock"
    if states and all(a is False for a in states):
        return "out_of_stock"
    return "unknown"


def _checks(sp: SubmittedProduct, price: Money | None, prefs: Preferences, url: str,
            category: str | None = None, available_sizes: list[str] | None = None,
            availability: str | None = None, condition: str = "unknown") -> list[ConstraintCheck]:
    """Reuse the catalog rules on a transient Listing, then relabel price wording as agent-observed."""
    availability = availability or sp.availability
    shown = available_sizes if available_sizes is not None else sp.sizes_available
    sizes = None
    if availability == "in_stock" and shown:
        sizes = [SizeStock(raw=s[:20], lowest_price=price) for s in shown]
    elif availability == "out_of_stock":
        sizes = []
    transient = Listing(
        id="tmp", offer_key="tmp", provider="agent", provider_listing_id="tmp", product_id=None, variant_id=None,
        retailer=sp.retailer, source_kind="retailer", canonical_url=url, image_urls=[], title=sp.title, brand=None,
        price=price, price_basis="seller_offer" if price else "unknown", seller_visibility="named",
        shipping_minor=None, condition=condition, size=None, sizes_in_stock=sizes, availability=availability,
        material_text=None, color_text=None, checked_at=sp.observed_at, detail_checked=True, evidence_ids=[],
        mode="live",
    )
    out = []
    for c in check_constraints(transient, prefs, category):
        detail = c.detail.replace("Listed price", "Agent-observed price").replace("listed in stock", "shown as available by the agent")
        if c.constraint in ("size", "ring size") and c.state == "unknown" and sizes == []:
            detail = "Agent reported the item out of stock"
        out.append(c.model_copy(update={"detail": detail, "evidence_ids": []}))
    return out


def verify_submission(
    raw_products: list[Any],
    *,
    job_id: str,
    prefs: Preferences,
    mode: str,
    job_created_at: datetime,
    url_checker: Callable[[str], UrlCheck] = check_url,
    now: datetime | None = None,
    category: str | None = None,
    source: str = "agent",
) -> tuple[list[ResearchProduct], list[RejectedItem], list[tuple[str, str, str, str]]]:
    """Return (products, rejected, link_targets[(token, url, kind, product_id)]).

    ``source`` is set by the server (provider or import route), never by the submission itself.
    """
    now = now or datetime.now(timezone.utc)
    ids: dict[str, ProductIdentifiers | None] = {}
    products: list[ResearchProduct] = []
    rejected: list[RejectedItem] = []
    targets: list[tuple[str, str, str, str]] = []
    seen: set[str] = set()
    for i, raw in enumerate(raw_products[:20]):
        try:
            sp = SubmittedProduct.model_validate(raw)
        except ValidationError as exc:
            first = exc.errors()[0]
            rejected.append(RejectedItem(index=i, reason=f"invalid {'.'.join(str(x) for x in first['loc'])}: {first['msg']}"[:160]))
            continue
        chk = url_checker(sp.product_url)
        if not chk.ok:
            rejected.append(RejectedItem(index=i, reason=f"product_url rejected: {chk.reason}"))
            continue
        if category and not title_matches_category(sp.title, category):
            rejected.append(RejectedItem(index=i, reason=f"not a {category} (title: {sp.title[:60]})", domain=chk.domain))
            continue
        if chk.canonical in seen:
            rejected.append(RejectedItem(index=i, reason="duplicate product URL", domain=chk.domain))
            continue
        seen.add(chk.canonical)
        if sp.source_url and sp.source_url != sp.product_url and not url_checker(sp.source_url).ok:
            rejected.append(RejectedItem(index=i, reason="source_url rejected", domain=chk.domain))
            continue
        observed = sp.observed_at if sp.observed_at.tzinfo else sp.observed_at.replace(tzinfo=timezone.utc)
        if observed > now + timedelta(minutes=2):
            rejected.append(RejectedItem(index=i, reason="observed_at is in the future", domain=chk.domain))
            continue
        if mode == "live" and observed < job_created_at - timedelta(minutes=5):
            rejected.append(RejectedItem(index=i, reason="observed before this job started (stale evidence)", domain=chk.domain))
            continue

        warnings: list[str] = [FIRST_WARNING.get(source, FIRST_WARNING["agent"])]
        if mode != "live" and observed < now - timedelta(hours=24):
            warnings.append(f"Seen on {observed.date().isoformat()}; price and stock may have changed.")
        price = None
        if sp.observed_price and sp.price_excerpt and sp.price_excerpt.strip():
            price = Money(amount_minor=sp.observed_price.amount_minor, currency=sp.observed_price.currency)
        elif sp.observed_price:
            warnings.append("Agent gave a price without the page text showing it; price not shown.")
        is_aggregator = chk.domain in AGGREGATOR_DOMAINS
        if is_aggregator:
            price = None  # comparison pages show an aggregate, never a seller price
            warnings.append("Price comparison page, not a retailer checkout.")
        if mode == "fixture":
            warnings.append("Development fixture: not live research output.")
        # v2 fields: variants keep unavailable sizes; brand needs page or catalog evidence; images are URL-checked only.
        variants = [
            ResearchVariant(
                label=v.label[:40],
                availability="available" if v.available is True else "unavailable" if v.available is False else "unknown",
                price=Money(amount_minor=v.price.amount_minor, currency=v.price.currency) if v.price and (v.price_excerpt or "").strip() else None,
            )
            for v in sp.variants
        ]
        available_sizes = list(sp.sizes_available) or [v.label for v in variants if v.availability == "available"]
        availability = _availability(sp)
        condition = "used" if sp.condition == "pre_owned" else sp.condition
        brand, brand_basis = None, None
        if sp.brand:
            if source == "catalog":
                brand, brand_basis = sp.brand.strip(), "catalog_record"
            elif any(e.field == "brand" and sp.brand.lower() in e.excerpt.lower() for e in sp.evidence):
                brand, brand_basis = sp.brand.strip(), "page_text"
            else:
                warnings.append("Brand not shown in the page evidence; not used.")
        image_url = None
        if sp.image_url:
            ic = url_checker(sp.image_url)
            if ic.ok and (ic.canonical or "").startswith("https://"):
                image_url = ic.canonical
            else:
                warnings.append("Image link failed ClipCart's URL check; not shown.")
        tier = "likely" if sp.match_type == "exact" else "similar"
        if sp.match_type == "exact":
            warnings.append("Agent reported an exact match; not independently confirmed.")
        checks = _checks(sp, price, prefs, chk.canonical, category, available_sizes, availability, condition)
        section = section_for(checks)
        pid = "rp_" + hashlib.sha256(f"{job_id}|{chk.canonical}".encode()).hexdigest()[:20]
        links: list[OutboundLink] = []
        if section != "excluded":
            token = "lk_" + secrets.token_urlsafe(12)
            kind = "aggregator_product_page" if is_aggregator else "retailer_product_page"
            note = f"{money_str(price)} seen by the agent on {observed.date().isoformat()}" if price else "Price not confirmed"
            label = "Compare prices on SoleScout" if is_aggregator else f"View at {sp.retailer}"
            links.append(OutboundLink(token=token, kind=kind, label=label, retailer=sp.retailer, price_note=note))
            targets.append((token, chk.canonical, kind, pid))
        products.append(
            ResearchProduct(
                id=pid, job_id=job_id, section=section, retailer=sp.retailer, domain=chk.domain, title=sp.title,
                match_claim=sp.match_type, identity_tier=tier, price=price,
                price_basis="agent_observed" if price else "unknown", price_excerpt=sp.price_excerpt if price else None,
                availability=availability, sizes_available=[s[:20] for s in available_sizes],
                constraint_checks=checks, observed_at=observed, validated_at=now,
                verification="url_checked_page_not_fetched", uncertainty=sp.uncertainty, warnings=warnings,
                links=links, mode=mode, source=source, image_url=image_url, brand=brand, brand_basis=brand_basis,
                condition=condition, seller_kind=sp.seller_kind, variants=variants, evidence=sp.evidence,
            )
        )
        ids[pid] = sp.identifiers

    products = group_offers(products, ids, prefs.currency)  # before the result limit, so comparisons see every offer
    order = {"likely": 0, "similar": 1}

    def key(p: ResearchProduct):
        return (order[p.identity_tier], 0 if p.price else 1, p.price.amount_minor if p.price else 0)

    primary = sorted([p for p in products if p.section == "primary"], key=key)
    needs = sorted([p for p in products if p.section == "needs_checking"], key=key)
    excluded = [p for p in products if p.section == "excluded"]
    kept_ids = {p.id for p in primary[:MAX_PRIMARY] + needs[:MAX_NEEDS]}
    for p in primary[MAX_PRIMARY:] + needs[MAX_NEEDS:]:
        rejected.append(RejectedItem(index=-1, reason="over the result limit", domain=p.domain))
    final = [p for p in primary + needs if p.id in kept_ids] + excluded
    return final, rejected, [t for t in targets if t[3] in kept_ids]

