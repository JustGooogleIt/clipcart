from datetime import datetime, timedelta, timezone

import pytest

from app.contracts import Preferences, SizePref
from app.research.urlsafety import UrlCheck, check_url
from app.research.verify import verify_submission

NOW = datetime(2026, 10, 17, 22, 0, tzinfo=timezone.utc)
CREATED = NOW - timedelta(minutes=3)


def no_dns(url):
    return check_url(url, resolve=False)


def prod(**kw):
    base = {"retailer": "Shop", "productUrl": "https://shop.example.com/p/1", "title": "Black Nylon Bomber Jacket",
            "matchType": "similar", "observedAt": (NOW - timedelta(minutes=1)).isoformat()}
    return {**base, **kw}


def run(items, prefs=None, mode="live"):
    return verify_submission(items, job_id="rsj_t", prefs=prefs or Preferences(), mode=mode, job_created_at=CREATED,
                             url_checker=no_dns, now=NOW)


@pytest.mark.parametrize("url,reason", [
    ("http://shop.com/p", "not https"),
    ("https://user:pw@shop.com/p", "credentials"),
    ("https://127.0.0.1/p", "IP address"),
    ("https://[::1]/p", "IP address"),
    ("https://localhost/p", "not a public domain"),
    ("https://admin.internal/p", "not a public domain"),
    ("https://shop.com:8443/p", "non-standard port"),
    ("javascript:alert(1)", "not https"),
])
def test_unsafe_urls(url, reason):
    r = check_url(url, resolve=False)
    assert not r.ok and reason in r.reason


def test_dns_must_resolve_public(monkeypatch):
    import app.research.urlsafety as u

    monkeypatch.setattr(u.socket, "getaddrinfo", lambda *a, **k: [(0, 0, 0, "", ("10.0.0.5", 443))])
    assert not check_url("https://looks-public.com/p").ok
    monkeypatch.setattr(u.socket, "getaddrinfo", lambda *a, **k: [(0, 0, 0, "", ("93.184.216.34", 443))])
    assert check_url("https://looks-public.com/p").ok


def test_canonical_strips_tracking_and_dedupes():
    out, rej, _ = run([prod(), prod(productUrl="https://Shop.example.com/p/1?utm_source=x#frag")])
    assert len(out) == 1 and rej[0].reason == "duplicate product URL"


def test_exact_claim_is_never_verified_and_price_needs_excerpt():
    out, _, _ = run([prod(matchType="exact", observedPrice={"amountMinor": 9000, "currency": "USD"})])
    p = out[0]
    assert p.identity_tier == "likely" and p.match_claim == "exact"
    assert p.price is None and p.price_basis == "unknown" and any("without the page text" in w for w in p.warnings)
    out, _, _ = run([prod(observedPrice={"amountMinor": 9000, "currency": "USD"}, priceExcerpt="$90.00")])
    assert out[0].price.amount_minor == 9000 and out[0].price_basis == "agent_observed"
    assert out[0].verification == "url_checked_page_not_fetched"


def test_aggregator_page_never_carries_a_price():
    out, _, targets = run([prod(productUrl="https://solescout.ai/product/x", observedPrice={"amountMinor": 5500, "currency": "USD"},
                                priceExcerpt="from $55")])
    assert out[0].price is None and targets[0][2] == "aggregator_product_page"


def test_constraints_and_sections():
    prefs = Preferences(max_item_price_minor=10000, size=SizePref(raw="M"), excluded_materials=["leather"])
    items = [
        prod(productUrl="https://a.com/1", observedPrice={"amountMinor": 8000, "currency": "USD"}, priceExcerpt="$80",
             availability="in_stock", sizesAvailable=["S", "M"]),
        prod(productUrl="https://a.com/2", observedPrice={"amountMinor": 15000, "currency": "USD"}, priceExcerpt="$150"),
        prod(productUrl="https://a.com/3", title="Black Leather Bomber Jacket"),
        prod(productUrl="https://a.com/4"),
    ]
    out, _, targets = run(items, prefs)
    by = {p.title + str(p.price): p for p in out}
    secs = sorted((p.section, p.domain) for p in out)
    assert ("excluded", "a.com") in secs
    first = next(p for p in out if p.price and p.price.amount_minor == 8000)
    states = {c.constraint: c.state for c in first.constraint_checks}
    assert states["budget"] == "satisfied" and states["size"] == "satisfied" and states["no leather"] == "unknown"
    assert first.section == "needs_checking"  # material unknown -> never fully confirmed
    assert any("Agent-observed price" in c.detail for c in first.constraint_checks)
    assert all(p.links == [] for p in out if p.section == "excluded")
    assert {t[3] for t in targets} == {p.id for p in out if p.section != "excluded"}
    assert by  # silence unused


def test_time_checks():
    _, rej, _ = run([prod(observedAt=(NOW + timedelta(hours=1)).isoformat())])
    assert "future" in rej[0].reason
    _, rej, _ = run([prod(observedAt=(CREATED - timedelta(days=2)).isoformat())])
    assert "stale" in rej[0].reason
    out, rej, _ = run([prod(observedAt=(CREATED - timedelta(days=2)).isoformat())], mode="fixture")
    assert out and not rej and any("Development fixture" in w for w in out[0].warnings)


def test_strict_schema_rejects_extra_and_bad_fields():
    _, rej, _ = run([prod(checkoutUrl="https://x.com/buy"), prod(matchType="perfect"), {"title": "x"}])
    assert len(rej) == 3 and all(r.reason.startswith("invalid") for r in rej)


def test_category_gate():
    out, rej, _ = verify_submission([prod(title="White Cotton T-shirt")], job_id="j", prefs=Preferences(), mode="live",
                                    job_created_at=CREATED, url_checker=no_dns, now=NOW, category="jacket")
    assert out == [] and rej[0].reason.startswith("not a jacket")


def test_url_checker_failures_reported():
    def fail(url):
        return UrlCheck(False, "domain does not resolve to a public address")

    _, rej, _ = verify_submission([prod()], job_id="j", prefs=Preferences(), mode="live", job_created_at=CREATED,
                                  url_checker=fail, now=NOW)
    assert "does not resolve" in rej[0].reason
