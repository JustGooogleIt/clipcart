"""Multiple unpaid demo orders must coexist on durable Mongo (partial unique signature)."""

from __future__ import annotations

from api.conftest import H
from demo_orders.conftest import create_session


def test_multiple_unpaid_orders_coexist(solana_app):
    c, st, _ = solana_app()
    create_session(c)
    o1 = c.post(
        "/api/demo-orders",
        headers=H,
        json={"catalogItemId": "demo_item_clipcart_jacket_01", "idempotencyKey": "unpaid-a"},
    ).json()["order"]
    o2 = c.post(
        "/api/demo-orders",
        headers=H,
        json={"catalogItemId": "demo_item_clipcart_jacket_01", "idempotencyKey": "unpaid-b"},
    ).json()["order"]
    assert o1["id"] != o2["id"]
    assert o1["status"] == "awaiting_payment"
    assert o2["status"] == "awaiting_payment"
    assert o1["paymentSignature"] is None
    assert o2["paymentSignature"] is None
    assert st.db.demo_orders.count_documents({"_id": {"$in": [o1["id"], o2["id"]]}}) == 2
