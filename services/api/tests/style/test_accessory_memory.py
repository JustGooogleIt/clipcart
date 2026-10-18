"""Accessory memory kinds: tone like/avoid and ring size; tone nudges apply to watches and jewelry only."""

from datetime import datetime, timezone

import pytest
from api.conftest import H, new_client

from app.contracts import Listing, StyleProfile
from app.contracts.style_memory import ProfileEntry
from app.style.personalize import style_score
from app.style.vocab import InvalidMemory, normalize


@pytest.mark.parametrize("raw,out", [("gold", "gold-tone"), ("Gold Tone", "gold-tone"), ("rose gold", "rose-gold-tone"),
                                     ("silver", "silver-tone"), ("two tone", "two-tone")])
def test_tone_values_normalize(raw, out):
    assert normalize("tone_like", raw) == out


def test_invalid_tone_and_ring_size_rejected():
    with pytest.raises(InvalidMemory):
        normalize("tone_avoid", "platinum")
    with pytest.raises(InvalidMemory):
        normalize("ring_size", "M")
    assert normalize("ring_size", {"raw": "6.5"}) == {"raw": "6.5", "system": "us"}


def _l(title):
    return Listing(id="l", offer_key="k", provider="p", provider_listing_id="x", product_id=None, variant_id=None,
                   retailer="R", source_kind="retailer", canonical_url="https://r.example", image_urls=[], title=title,
                   brand=None, price=None, price_basis="unknown", seller_visibility="named", shipping_minor=None,
                   condition="unknown", size=None, sizes_in_stock=None, availability="unknown", material_text=None,
                   color_text=None, checked_at=datetime.now(timezone.utc), detail_checked=False, evidence_ids=[], mode="live")


def test_tone_preference_nudges_jewelry_but_not_jackets():
    prof = StyleProfile(tones_like=[ProfileEntry(value="gold-tone", origin="stated", memory_id="m1")])
    s, why = style_score(_l("Gold hoop earrings"), prof, "earrings")
    assert s > 0 and why == ["You said you like gold-tone"]
    assert style_score(_l("Jacket with gold buttons"), prof, "jacket") == (0.0, [])


def test_memory_api_accepts_accessory_kinds(app_factory, monkeypatch):
    monkeypatch.setenv("FEATURE_STYLE_MEMORY", "1")
    c = new_client(app_factory())
    c.post("/api/sessions", headers=H)
    assert c.post("/api/style/memories", headers=H, json={"kind": "tone_like", "value": "gold", "source": "style_panel"}).status_code == 201
    r1 = c.post("/api/style/memories", headers=H, json={"kind": "ring_size", "value": {"raw": "7"}, "source": "style_panel"})
    r2 = c.post("/api/style/memories", headers=H, json={"kind": "ring_size", "value": "8", "source": "style_panel"})
    assert r1.status_code == r2.status_code == 201 and r2.json()["overridden"] == [r1.json()["memory"]["id"]]
    prof = c.get("/api/style/profile").json()["profile"]
    assert prof["tonesLike"][0]["value"] == "gold-tone" and prof["ringSize"]["value"] == {"raw": "8", "system": "us"}
    assert c.post("/api/style/memories", headers=H, json={"kind": "tone_like", "value": "platinum"}).status_code == 422
