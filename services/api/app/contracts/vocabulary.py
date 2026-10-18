"""Static vocabulary served by GET /api/categories.

Categories: docs/contracts/accessories.md. Style tags and tones: docs/contracts/style-memory.md.
"""

from __future__ import annotations

from typing import Literal

from .base import Record
from .media import Category
from .style_memory import StyleTag, Tone

CategoryFamily = Literal["apparel", "bag", "watch", "jewelry", "other"]
SizeRule = Literal["clothing", "ring", "none"]
AttributeKey = Literal["color", "pattern", "cut", "details"]


class CategoryInfo(Record):
    id: Category
    label: str
    family: CategoryFamily
    size_rule: SizeRule
    attribute_keys: list[AttributeKey]


class CategoriesResponse(Record):
    """What GET /api/categories returns. Static; no auth."""

    categories: list[CategoryInfo]
    style_tags: list[StyleTag]
    tones: list[Tone]
