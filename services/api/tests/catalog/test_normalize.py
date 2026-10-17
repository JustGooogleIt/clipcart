from __future__ import annotations

import sys
import unittest
from pathlib import Path

API_ROOT = Path(__file__).resolve().parents[2]  # services/api
sys.path.insert(0, str(API_ROOT))

from app.providers.catalog.normalize import (  # noqa: E402
    availability_from_sizes,
    dollars_to_minor,
    material_hint_from_title,
)


class NormalizeTests(unittest.TestCase):
    def test_dollars_to_minor_usd(self) -> None:
        self.assertEqual(
            dollars_to_minor(55), {"amountMinor": 5500, "currency": "USD"}
        )
        self.assertIsNone(dollars_to_minor(None))

    def test_material_hint_from_title(self) -> None:
        self.assertEqual(
            material_hint_from_title("about:blank Leather Jacket"),
            "leather (title mention)",
        )
        self.assertEqual(
            material_hint_from_title("Calvin Klein Jeans Faux Leather Moto"),
            "faux leather (title mention)",
        )
        self.assertIsNone(material_hint_from_title("Canvas Tote"))

    def test_availability_from_sizes(self) -> None:
        self.assertEqual(availability_from_sizes([{"size": "M"}], []), "in_stock")
        self.assertEqual(availability_from_sizes([], [{"name": "Store"}]), "unknown")
        self.assertEqual(availability_from_sizes([], []), "unknown")


if __name__ == "__main__":
    unittest.main()
