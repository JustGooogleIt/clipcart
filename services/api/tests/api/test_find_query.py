"""Unit tests for find-in-video query helpers."""

from app.jobs.find_query import (
    compose_search_description,
    detect_classes_for_query,
    infer_category,
    normalize_find_query,
    query_too_vague,
)


def test_normalize_and_vague():
    assert normalize_find_query("find me the tall plant") == "tall plant"
    assert query_too_vague("thing")
    assert query_too_vague("something")
    assert query_too_vague("plant")  # single non-apparel noun — demand details
    assert query_too_vague("blue item")  # no concrete anchor
    assert query_too_vague("jacket") is None
    assert query_too_vague("denim jacket") is None
    assert query_too_vague("tall monstera in speckled pot") is None


def test_detect_classes_keep_full_phrase_first():
    q = "distressed light-wash denim trucker jacket with copper rivets"
    classes = detect_classes_for_query(q)
    assert classes[0] == q
    assert any("jacket" in c for c in classes)
    assert len(classes) >= 2


def test_infer_category_apparel():
    assert infer_category("blue denim trucker", "denim jacket") == "jacket"
    assert infer_category("leather tote on the chair", None) == "bag"
    assert infer_category("monstera in ceramic pot", "houseplant") == "other"


def test_compose_keeps_shopper_details():
    desc = compose_search_description(
        query="tall monstera in speckled cream ceramic pot",
        what="monstera plant",
        search_desc="green leafy plant",
        detail_bits=["fenestrated leaves", "aerial roots"],
    )
    assert "monstera" in desc.lower()
    assert "speckled" in desc.lower() or "Asked for" in desc
    assert len(desc.split()) >= 6
