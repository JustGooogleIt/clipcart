"""Search pipeline: two bounded workers -> detail checks -> deterministic
verification -> at most three primary results (SRS section 10)."""

from __future__ import annotations

import hashlib
import secrets
import threading
from collections import Counter
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any

from app.contracts import Evidence, Listing, OutboundLink, Preferences, Recommendation
from app.providers.catalog import CatalogFilters
from app.providers.status import ProviderStatus

from .budget import BudgetLedger
from .rules import (
    RANKING_VERSION,
    TIER_ORDER,
    GarmentProfile,
    check_constraints,
    clear_mismatch,
    explanation,
    fabric_match,
    identity_tier,
    money_str,
    price_phrase,
    relevance,
    required_fabrics,
    section_for,
    title_matches_category,
)
from .tools import Candidate, ToolBox
from .workers import GrokWorker, RuleWorker

MAX_PRIMARY = 3
MAX_NEEDS_CHECKING = 3


@dataclass
class LinkTarget:
    token: str
    url: str
    kind: str
    recommendation_id: str
    listing_id: str


@dataclass
class SearchOutcome:
    status: str
    summary: str
    recommendations: list[Recommendation] = field(default_factory=list)
    listings: list[Listing] = field(default_factory=list)
    evidence: list[Evidence] = field(default_factory=list)
    links: list[LinkTarget] = field(default_factory=list)
    worker_modes: dict[str, str] = field(default_factory=dict)
    errors: list[dict] = field(default_factory=list)


def _links_for(rec_id: str, L: Listing, prefs: Preferences) -> tuple[list[OutboundLink], list[LinkTarget]]:
    links: list[OutboundLink] = []
    targets: list[LinkTarget] = []

    def add(url: str, kind: str, label: str, retailer: str, note: str) -> None:
        token = "lk_" + secrets.token_urlsafe(12)
        links.append(OutboundLink(token=token, kind=kind, label=label, retailer=retailer, price_note=note))
        targets.append(LinkTarget(token, url, kind, rec_id, L.id))

    if L.source_kind == "retailer" and L.provider == "solescout":
        # Direct store offer surfaced by SoleScout: the store link carries the store's own price.
        add(L.canonical_url, "retailer_product_page", f"View at {L.retailer}", L.retailer, price_phrase(L, prefs))
        for s in L.store_offers[:1]:
            if s.url and s.retailer == "SoleScout comparison":
                note = "Other sellers' prices; cheapest names may be hidden"
                add(s.url, "aggregator_product_page", "Compare prices on SoleScout", "SoleScout", note)
    elif L.source_kind == "aggregator":
        add(L.canonical_url, "aggregator_product_page", "Compare prices on SoleScout", "SoleScout", price_phrase(L, prefs))
        for s in L.store_offers[:2]:
            if s.url:
                note = f"{money_str(s.price)} listed for this store" if s.price else "SoleScout shows no price for this store"
                add(s.url, "retailer_product_page", f"{s.retailer} product page", s.retailer, note)
    else:
        add(L.canonical_url, "retailer_product_page", f"View at {L.retailer}", L.retailer, price_phrase(L, prefs))
    return links, targets


def run_search(
    *,
    search_id: str,
    garment_id: str,
    profile: GarmentProfile,
    prefs: Preferences,
    provider: Any,
    ledger: BudgetLedger,
    emit: Callable[..., None],
    catalog_status: ProviderStatus,
    grok_status: ProviderStatus,
    grok_client_factory: Callable[[], Any] | None,
    is_current: Callable[[], bool],
) -> SearchOutcome:
    filters = CatalogFilters(
        category=profile.category,
        country=prefs.country,
        currency=prefs.currency,
        max_price_minor=prefs.max_item_price_minor,
        size_raw=prefs.size.raw if prefs.size else None,
        colors=tuple(prefs.colors),
        excluded_materials=tuple(prefs.excluded_materials),
        condition=prefs.condition,
    )
    tools = ToolBox(provider, ledger, filters, emit, catalog_status)
    emit("locating_garment", f"Searching for the selected {profile.label or profile.category}", worker="system")

    workers: dict[str, Any] = {}
    client = None
    if grok_client_factory is not None:
        try:
            client = grok_client_factory()
        except Exception as exc:  # noqa: BLE001
            emit("locating_garment", f"Grok client unavailable ({type(exc).__name__}); using rule-based search")
    for role in ("exact", "alternatives"):
        workers[role] = (
            GrokWorker(role, tools, client, ledger, grok_status, max_rounds=ledger.budget.max_rounds_per_worker)
            if client
            else RuleWorker(role, tools)
        )

    with ThreadPoolExecutor(max_workers=2, thread_name_prefix="worker") as pool:
        futs = {role: pool.submit(w.run, profile, prefs) for role, w in workers.items()}
        for role, f in futs.items():
            try:
                f.result(timeout=max(1.0, ledger.remaining_s()))
            except Exception as exc:  # noqa: BLE001
                tools.errors.append({"code": "worker_error", "message": type(exc).__name__, "worker": role})
                emit("failed", f"{role} worker stopped: {type(exc).__name__}", worker=role)
    worker_modes = {
        role: ("rule_based_fallback" if getattr(w, "used_fallback", False) else w.mode) for role, w in workers.items()
    }

    if not is_current():
        return SearchOutcome("superseded", "A newer search replaced this one", worker_modes=worker_modes)

    cands: list[Candidate] = list(tools.candidates.values())
    if not cands:
        status = "failed" if tools.errors else "no_match"
        msg = "Catalog search failed" if tools.errors else "No listings found for this garment"
        return SearchOutcome(status, msg, worker_modes=worker_modes, errors=tools.errors)

    off_cat = [c for c in cands if not title_matches_category(c.listing.title, profile.category)]
    cands = [c for c in cands if c not in off_cat]
    if off_cat:
        emit("verifying_listings", f"Set aside {len(off_cat)} result{'s' if len(off_cat) != 1 else ''} that are not a {profile.category}",
             worker="verifier")

    # When fabric is known and SoleScout returned fabric matches, drop lookalikes
    # in the wrong material (e.g. blue track jackets for a denim trucker).
    if required_fabrics(profile):
        with_fabric = [c for c in cands if fabric_match(c.listing, profile)]
        if with_fabric:
            skipped = len(cands) - len(with_fabric)
            cands = with_fabric
            if skipped:
                emit(
                    "verifying_listings",
                    f"Kept {len(with_fabric)} {required_fabrics(profile)[0]} match{'es' if len(with_fabric) != 1 else ''}; "
                    f"set aside {skipped} without that fabric",
                    worker="verifier",
                )

    def pre_score(c: Candidate) -> tuple:
        tier, _ = identity_tier(c.listing, profile)
        return (
            TIER_ORDER[tier],
            0 if fabric_match(c.listing, profile) else 1,
            0 if c.submitted_by else 1,
            -relevance(c.listing, profile, prefs),
            0 if "exact" in c.found_by else 1,
        )

    cands.sort(key=pre_score)
    # Search-level data can already prove a violation (an aggregate lowest
    # price above budget means every listed offer is above it, or the title
    # names an excluded material). Spend detail calls only on the rest.
    def already_excluded(c: Candidate) -> bool:
        return any(k.state == "violated" and k.constraint != "size" for k in check_constraints(c.listing, prefs))

    detail_threads = []
    for c in [c for c in cands if not already_excluded(c)]:
        if ledger.detail_left() <= 0 or ledger.remaining_s() < 3:
            break
        if not c.listing.detail_checked:
            t = threading.Thread(target=tools.get_listing_details, args=("verifier", c.id), daemon=True)
            t.start()
            detail_threads.append(t)
            if len(detail_threads) >= 6:
                break
    for t in detail_threads:
        t.join(timeout=max(0.5, ledger.remaining_s() - 1))

    if not is_current():
        return SearchOutcome("superseded", "A newer search replaced this one", worker_modes=worker_modes)

    emit("ranking", "Applying budget, size and material rules", worker="verifier")
    scored = []
    exclusions: Counter = Counter()
    weak = 0
    original_over_budget = None
    for c in cands:
        L = c.listing
        checks = check_constraints(L, prefs)
        tier, reason = identity_tier(L, profile)
        sec = section_for(checks)
        if sec == "excluded":
            violated = [k.constraint for k in checks if k.state == "violated"]
            for v in violated:
                exclusions[v] += 1
            if tier in ("verified", "likely") and violated == ["budget"] and original_over_budget is None:
                original_over_budget = (c, checks, tier, reason)
            continue
        if tier == "similar" and clear_mismatch(L, profile, prefs):
            weak += 1  # wrong named color or conflicting fabric — not a useful option
            continue
        scored.append((sec, c, checks, tier, reason))

    def rank_key(item) -> tuple:
        sec, c, checks, tier, _ = item
        size_ok = any(k.constraint == "size" and k.state == "satisfied" for k in checks)
        price = c.listing.price.amount_minor if c.listing.price else 10**12
        return (
            TIER_ORDER[tier],
            0 if fabric_match(c.listing, profile) else 1,
            -relevance(c.listing, profile, prefs),
            0 if c.listing.availability == "in_stock" else 1,
            0 if size_ok else 1,
            price,
        )

    primary = sorted([s for s in scored if s[0] == "primary"], key=rank_key)[:MAX_PRIMARY]
    needs = sorted([s for s in scored if s[0] == "needs_checking"], key=rank_key)[:MAX_NEEDS_CHECKING]

    out = SearchOutcome("completed", "", worker_modes=worker_modes, errors=tools.errors)
    seen_ev: set[str] = set()

    def add_rec(section: str, c: Candidate, checks, tier, reason, rank: int) -> None:
        L = c.listing
        rec_id = "rec_" + hashlib.sha256(f"{search_id}|{L.id}|{section}".encode()).hexdigest()[:20]
        links, targets = _links_for(rec_id, L, prefs)
        warnings = list(L.warnings)
        if L.availability == "unknown":
            warnings.append("Availability unknown")
        if L.mode in ("fixture", "catalog"):
            warnings.append("Fixture data: not a live result")
        out.recommendations.append(
            Recommendation(
                id=rec_id,
                search_id=search_id,
                garment_id=garment_id,
                listing_id=L.id,
                section=section,
                identity_tier=tier,
                identity_evidence_ids=L.evidence_ids if tier != "similar" else [],
                constraint_checks=checks,
                explanation=explanation(L, profile, tier, reason, prefs),
                warnings=list(dict.fromkeys(warnings)),
                rank=rank,
                ranking_version=RANKING_VERSION,
                found_by=sorted(c.found_by & {"exact", "alternatives"}) or ["alternatives"],
                links=links,
            )
        )
        out.listings.append(L)
        out.links.extend(targets)
        for e in c.evidence:
            if e.id not in seen_ev:
                seen_ev.add(e.id)
                out.evidence.append(e)

    for i, (_sec, c, checks, tier, reason) in enumerate(primary, 1):
        add_rec("primary", c, checks, tier, reason, i)
    for i, (_sec, c, checks, tier, reason) in enumerate(needs, 1):
        add_rec("needs_checking", c, checks, tier, reason, i)
    if original_over_budget:
        c, checks, tier, reason = original_over_budget
        add_rec("original_over_budget", c, checks, tier, reason, 1)
        emit("ranking", f"Possible original found but it is above your budget: {price_phrase(c.listing, prefs)}",
             worker="verifier")

    for constraint, n in exclusions.items():
        label = {
            "budget": f"above your {money_str_budget(prefs)} budget",
            "size": f"not listed in size {prefs.size.raw if prefs.size else ''}",
            "condition": "in the wrong condition",
        }.get(constraint, f"that conflict with '{constraint}' (title mentions it)")
        emit("ranking", f"Excluded {n} result{'s' if n != 1 else ''} {label}", worker="verifier")

    if weak:
        emit("ranking", f"Set aside {weak} clear mismatch{'es' if weak != 1 else ''} (wrong color or conflicting fabric)",
             worker="verifier")
    n_p, n_n = len(primary), len(needs)
    if n_p == 0 and n_n == 0:
        out.status = "partial" if tools.errors else "no_match"
        if exclusions:
            out.summary = f"No listings met your constraints ({sum(exclusions.values())} excluded)"
        elif weak:
            out.summary = f"Catalog returned options, but all conflicted with the garment look ({weak} mismatched)"
        else:
            out.summary = "No listings found for this garment"
    else:
        out.status = "partial" if tools.errors else "completed"
        bits = []
        if n_p:
            bits.append(f"{n_p} recommended")
        if n_n:
            bits.append(f"{n_n} need checking")
        out.summary = ", ".join(bits)
    return out


def money_str_budget(prefs: Preferences) -> str:
    if prefs.max_item_price_minor is None:
        return ""
    from app.contracts import Money

    return money_str(Money(amount_minor=prefs.max_item_price_minor, currency=prefs.currency))
