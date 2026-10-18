"""Group equivalent offers and compare their prices.

Equivalence is never upgraded beyond the evidence:
- ``identifier_match``: the offers share a GTIN, MPN, SKU, style code or catalog reference.
- ``approximate``: same page-evidenced brand and a near-identical title. Shown as "not confirmed".
- ``single``: everything else.
The lowest price is computed only over prices that came with page text, in one currency.
"""

from __future__ import annotations

import hashlib
import re

from app.contracts import Money
from app.contracts.research import OfferGroup, ProductIdentifiers, ResearchProduct

_STOP = frozenset({"the", "a", "an", "and", "with", "for", "in", "of", "by", "new", "mens", "men", "womens", "women",
                   "unisex", "size", "sizes", "us", "uk", "eu", "authentic", "official", "free", "shipping"})
_SIZE_TOKEN = re.compile(r"^(?:xxs|xs|s|m|l|xl|xxl|\d{1,3}(?:\.\d)?)$")
APPROX_MIN_JACCARD = 0.75


def _ident_keys(ids: ProductIdentifiers | None) -> set[str]:
    if not ids:
        return set()
    out = set()
    if ids.gtin:
        out.add("gtin:" + ids.gtin.lstrip("0"))
    for name in ("mpn", "sku", "style_code"):
        v = getattr(ids, name)
        if v and len(re.sub(r"[^A-Za-z0-9]", "", v)) >= 4:
            out.add(f"{name}:" + re.sub(r"[^A-Za-z0-9]", "", v).upper())
    if ids.catalog_ref:
        out.add("ref:" + ids.catalog_ref.strip().lower())
    return out


def _title_tokens(title: str, brand: str | None) -> set[str]:
    btoks = set(re.findall(r"[a-z0-9]+", (brand or "").lower()))
    toks = set(re.findall(r"[a-z0-9]+", title.lower()))
    return {t for t in toks if t not in _STOP and t not in btoks and not _SIZE_TOKEN.match(t)}


def _jaccard(a: set[str], b: set[str]) -> float:
    return len(a & b) / len(a | b) if a and b else 0.0


def group_offers(products: list[ResearchProduct], ids: dict[str, ProductIdentifiers | None], currency: str) -> list[ResearchProduct]:
    """Return products with ``offer_group`` set. ``ids`` maps product id -> submitted identifiers."""
    n = len(products)
    parent = list(range(n))
    how: dict[int, str] = {}

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i: int, j: int, kind: str) -> None:
        ri, rj = find(i), find(j)
        if ri != rj:
            parent[rj] = ri
        # identifier evidence outranks approximate for the whole group
        r = find(i)
        if how.get(r) != "identifier_match":
            how[r] = kind

    keys = [_ident_keys(ids.get(p.id)) for p in products]
    for i in range(n):
        for j in range(i + 1, n):
            if keys[i] & keys[j]:
                union(i, j, "identifier_match")
    for i in range(n):
        for j in range(i + 1, n):
            if find(i) == find(j):
                continue
            a, b = products[i], products[j]
            if not (a.brand and b.brand and a.brand.lower() == b.brand.lower()):
                continue
            if _jaccard(_title_tokens(a.title, a.brand), _title_tokens(b.title, b.brand)) >= APPROX_MIN_JACCARD:
                union(i, j, "approximate")

    groups: dict[int, list[int]] = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(i)
    out = list(products)
    for root, members in groups.items():
        kind = how.get(root, "single") if len(members) > 1 else "single"
        priced = [products[i].price for i in members
                  if products[i].price is not None and products[i].price.currency == currency]
        lowest = min(priced, key=lambda m: m.amount_minor) if priced else None
        gid = "og_" + hashlib.sha256("|".join(sorted(products[i].id for i in members)).encode()).hexdigest()[:12]
        if kind == "identifier_match":
            shared = set.intersection(*(keys[i] for i in members)) if all(keys[i] for i in members) else set()
            k = next(iter(sorted(shared)), "a shared identifier")
            basis = {"gtin": "Same GTIN", "mpn": "Same MPN", "sku": "Same SKU", "style_code": "Same style code",
                     "ref": "Same catalog product"}.get(k.split(":")[0], "Same identifier")
            basis = f"{basis} {k.split(':', 1)[1]}" if ":" in k and not k.startswith("ref:") else basis
        elif kind == "approximate":
            basis = "Same brand and near-identical title (not confirmed as the same product)"
        else:
            basis = "Only offer found for this product"
        uncertain = sum(1 for i in members if products[i].price is None)
        for i in members:
            p = products[i]
            out[i] = p.model_copy(update={"offer_group": OfferGroup(
                id=gid, equivalence=kind, basis=basis, offer_count=len(members), lowest_confirmed_price=lowest,
                is_lowest_confirmed=bool(lowest and p.price and p.price.currency == currency
                                         and p.price.amount_minor == lowest.amount_minor),
                uncertain_price_count=uncertain,
            )})
    return out


__all__ = ["group_offers", "APPROX_MIN_JACCARD", "Money"]
