"""Contract answers for the UI lane (#26): typed vocabulary, research health modes, typed job errors, warning codes."""

from typing import get_args

import pytest
from shopping.fakes import FakeCatalog, item

from app.contracts import CategoriesResponse, ResearchJob, StyleTag, Tone, WarningCode
from app.style.tags import STYLE_TAGS
from app.style.vocab import TONES

from .conftest import new_client
from .test_accessories_api import WATCHES, _search, _session_with_item


def test_categories_response_is_the_generated_shape_and_carries_the_style_vocabulary(app_factory):
    body = new_client(app_factory()).get("/api/categories").json()
    parsed = CategoriesResponse.model_validate(body)  # extra keys or wrong enums would raise
    assert [c.id for c in parsed.categories][-1] == "other"
    assert body["styleTags"] == list(get_args(StyleTag)) == list(STYLE_TAGS)
    assert body["tones"] == list(get_args(Tone)) == list(TONES)
    ring = next(c for c in body["categories"] if c["id"] == "ring")
    assert ring == {"id": "ring", "label": "Ring", "family": "jewelry", "sizeRule": "ring", "attributeKeys": ["color", "cut", "details"]}


@pytest.mark.parametrize(
    ("provider", "catalog", "mode"),
    [
        ("fixture", None, "fixture"),
        ("manual", None, "manual"),
        ("solescout", "fixture", "fixture"),  # SoleScout fallback over the fixture catalog is fixture data
        ("solescout", "live", "live"),
        ("grok_bot", None, None),  # not implemented: no job can start, so there is no mode
    ],
)
def test_health_research_mode_matches_what_jobs_get(app_factory, monkeypatch, provider, catalog, mode):
    monkeypatch.setenv("FEATURE_AGENT_RESEARCH", "1")
    monkeypatch.setenv("RESEARCH_PROVIDER", provider)
    monkeypatch.setenv("CATALOG_PROVIDER", "fixture" if catalog == "fixture" else "solescout")
    app = app_factory(FakeCatalog([item("a", "Black Nylon Bomber Jacket", 70)]) if catalog == "live" else None)
    h = new_client(app).get("/api/health").json()
    assert h["research"] == {"provider": provider, "mode": mode}
    if provider != "grok_bot":
        from app.research.providers import get_provider

        assert get_provider(provider, app.state.clipcart).mode == mode


def test_health_research_is_null_when_the_flag_is_off(app_factory, monkeypatch):
    monkeypatch.setenv("RESEARCH_PROVIDER", "manual")
    assert new_client(app_factory()).get("/api/health").json()["research"] == {"provider": None, "mode": None}


def test_research_job_error_is_a_typed_job_error():
    schema = ResearchJob.model_json_schema(by_alias=True)
    refs = [x.get("$ref") for x in schema["properties"]["error"]["anyOf"]]
    assert "#/$defs/JobError" in refs
    assert set(schema["$defs"]["JobError"]["required"]) == {"code", "message", "retryable"}


def test_seller_claims_have_a_stable_warning_code(app_factory):
    c = new_client(app_factory(FakeCatalog(WATCHES, {s: {"sizes": ["M"], "carrying": 1} for s in ("w1", "w2", "w3", "w4")})))
    s, _ = _session_with_item(c, "watch", "silver-tone round watch on a metal bracelet")
    out = _search(c, s)
    by_title = {r["listing"]["title"]: r["recommendation"] for r in out["results"]}
    claims, seiko = by_title["14K Gold Diamond Watch Authentic"], by_title["Seiko silver-tone automatic watch"]
    assert "seller_claims_unverified" in claims["warningCodes"]
    assert "seller_claims_unverified" not in seiko["warningCodes"]
    for rec in by_title.values():
        assert set(rec["warningCodes"]) <= set(get_args(WarningCode))
        # every code ClipCart adds has its readable warning alongside
        assert ("seller_claims_unverified" in rec["warningCodes"]) == any("seller's description" in w for w in rec["warnings"])
