"""Demo order HTTP API tests. RPC is faked; never hits a live chain."""

from __future__ import annotations

from datetime import timedelta

from api.conftest import H, new_client
from app.demo.verify import parse_order_unix
from app.sessions.service import now
from demo_orders.conftest import (
    BUYER,
    MERCHANT,
    SIG_OK,
    SIG_OTHER,
    FakeRpc,
    create_demo_order,
    create_session,
    transfer_tx,
)


def _mid_window(order: dict) -> int:
    """blockTime inside the order's [createdAt, expiresAt] for FakeRpc fixtures."""
    start = parse_order_unix(order["createdAt"]) or 0
    end = parse_order_unix(order["expiresAt"]) or (start + 900)
    return (start + end) // 2


def test_flag_off_disables_all_demo_routes(solana_app):
    c, _, _ = solana_app(flag=False)
    create_session(c)
    assert c.get("/api/demo-catalog").json()["code"] == "feature_disabled"
    assert create_demo_order(c).json()["code"] == "feature_disabled"
    assert c.get("/api/demo-orders/dmo_x").json()["code"] == "feature_disabled"
    assert c.post("/api/demo-orders/dmo_x/verify", headers=H, json={}).json()["code"] == "feature_disabled"


def test_catalog_and_create_pending_order(solana_app):
    c, _, _ = solana_app()
    create_session(c)
    cat = c.get("/api/demo-catalog").json()
    assert cat["featureEnabled"] is True
    assert cat["items"][0]["id"] == "demo_item_clipcart_jacket_01"
    assert cat["items"][0]["amountAtomic"] == "10000000"
    r = create_demo_order(c)
    assert r.status_code == 200
    body = r.json()
    order = body["order"]
    assert order["status"] == "awaiting_payment"
    assert order["receiptStatus"] == "ineligible"
    assert order["amountAtomic"] == "10000000"
    assert order["network"] == "devnet"
    assert order["recipientWallet"] == MERCHANT
    assert order["assetMint"] is None
    assert order["uiLabel"] == "Demo purchase on Solana devnet"
    assert "ownerId" not in order
    assert body["transferRequest"]["amount"] == "0.01"
    assert body["transferRequest"]["reference"] == order["paymentReference"]
    assert body["transferRequest"]["splToken"] is None
    # idempotent create
    assert create_demo_order(c).json()["order"]["id"] == order["id"]


def test_unknown_catalog_and_forbidden_client_price_fields(solana_app):
    c, _, _ = solana_app()
    create_session(c)
    assert create_demo_order(c, "listing_from_solescout").json()["code"] == "not_found"
    bad = c.post(
        "/api/demo-orders",
        headers=H,
        json={
            "catalogItemId": "demo_item_clipcart_jacket_01",
            "amountAtomic": "1",
            "recipientWallet": BUYER,
        },
    )
    assert bad.status_code == 422


def test_ownership(solana_app):
    c, _, _ = solana_app()
    create_session(c)
    order = create_demo_order(c).json()["order"]
    other = new_client(c.app)
    other.post("/api/sessions", headers=H)
    assert other.get(f"/api/demo-orders/{order['id']}").status_code == 404


def test_verify_paid_unconfirmed_mismatch_and_replay(solana_app, monkeypatch):
    c, st, _ = solana_app()
    create_session(c)
    order = create_demo_order(c).json()["order"]
    ref = order["paymentReference"]
    tx = transfer_tx(
        source=BUYER, dest=MERCHANT, lamports=10_000_000, reference=ref, block_time=_mid_window(order)
    )
    fake = FakeRpc(
        statuses={SIG_OK: {"confirmationStatus": "confirmed", "err": None}},
        transactions={SIG_OK: tx},
        by_address={ref: [{"signature": SIG_OK, "err": None}]},
    )
    monkeypatch.setattr("app.demo.orders.SolanaRpc", lambda url, **kw: fake)

    paid = c.post(
        f"/api/demo-orders/{order['id']}/verify",
        headers=H,
        json={"paymentSignature": SIG_OK, "buyerWallet": BUYER},
    )
    assert paid.status_code == 200
    body = paid.json()["order"]
    assert body["status"] == "paid"
    assert body["receiptStatus"] == "eligible"
    assert body["paymentSignature"] == SIG_OK
    assert body["buyerWallet"] == BUYER
    assert body["explorerPaymentUrl"].endswith("?cluster=devnet")
    assert "ownerId" not in body

    # Idempotent replay — already-paid short-circuit; must not require RPC.
    fake.transactions.clear()
    fake.statuses.clear()
    fake.by_address.clear()
    again = c.post(
        f"/api/demo-orders/{order['id']}/verify",
        headers=H,
        json={"paymentSignature": SIG_OK, "buyerWallet": BUYER},
    )
    assert again.status_code == 200 and again.json()["order"]["status"] == "paid"

    # Unconfirmed path on a fresh order
    order2 = c.post(
        "/api/demo-orders",
        headers=H,
        json={"catalogItemId": "demo_item_clipcart_jacket_01", "idempotencyKey": "k2"},
    ).json()["order"]
    ref2 = order2["paymentReference"]
    fake2 = FakeRpc(
        statuses={SIG_OK: {"confirmationStatus": "processed", "err": None}},
        transactions={},
        by_address={ref2: [{"signature": SIG_OK, "err": None}]},
    )
    monkeypatch.setattr("app.demo.orders.SolanaRpc", lambda url, **kw: fake2)
    unconfirmed = c.post(f"/api/demo-orders/{order2['id']}/verify", headers=H, json={})
    assert unconfirmed.status_code == 409
    assert unconfirmed.json()["code"] == "payment_unconfirmed"
    assert unconfirmed.json()["retryable"] is True
    assert unconfirmed.json()["order"]["status"] == "awaiting_payment"

    # Mismatch marks failed
    order3 = c.post(
        "/api/demo-orders",
        headers=H,
        json={"catalogItemId": "demo_item_clipcart_jacket_01", "idempotencyKey": "k3"},
    ).json()["order"]
    ref3 = order3["paymentReference"]
    bad_tx = transfer_tx(source=BUYER, dest=MERCHANT, lamports=1, reference=ref3)
    fake3 = FakeRpc(
        statuses={SIG_OTHER: {"confirmationStatus": "confirmed", "err": None}},
        transactions={SIG_OTHER: bad_tx},
        by_address={ref3: [{"signature": SIG_OTHER, "err": None}]},
    )
    monkeypatch.setattr("app.demo.orders.SolanaRpc", lambda url, **kw: fake3)
    mismatch = c.post(f"/api/demo-orders/{order3['id']}/verify", headers=H, json={})
    assert mismatch.status_code == 422
    assert mismatch.json()["code"] == "payment_mismatch"
    assert mismatch.json()["order"]["status"] == "failed"
    assert mismatch.json()["order"]["receiptStatus"] == "ineligible"


def test_signature_cannot_pay_two_orders(solana_app, monkeypatch):
    c, st, _ = solana_app()
    create_session(c)
    o1 = c.post(
        "/api/demo-orders",
        headers=H,
        json={"catalogItemId": "demo_item_clipcart_jacket_01", "idempotencyKey": "a"},
    ).json()["order"]
    o2 = c.post(
        "/api/demo-orders",
        headers=H,
        json={"catalogItemId": "demo_item_clipcart_jacket_01", "idempotencyKey": "b"},
    ).json()["order"]

    def rpc_for(order):
        ref = order["paymentReference"]
        tx = transfer_tx(
            source=BUYER,
            dest=MERCHANT,
            lamports=10_000_000,
            reference=ref,
            block_time=_mid_window(order),
        )
        return FakeRpc(
            statuses={SIG_OK: {"confirmationStatus": "confirmed", "err": None}},
            transactions={SIG_OK: tx},
            by_address={ref: [{"signature": SIG_OK, "err": None}]},
        )

    monkeypatch.setattr("app.demo.orders.SolanaRpc", lambda url, **kw: rpc_for(o1))
    assert c.post(f"/api/demo-orders/{o1['id']}/verify", headers=H, json={"paymentSignature": SIG_OK}).status_code == 200

    # Second order: same signature appears under its own reference in this fixture, but claim must fail.
    monkeypatch.setattr("app.demo.orders.SolanaRpc", lambda url, **kw: rpc_for(o2))
    reused = c.post(f"/api/demo-orders/{o2['id']}/verify", headers=H, json={"paymentSignature": SIG_OK})
    assert reused.status_code == 409
    assert reused.json()["code"] == "signature_reused"
    assert c.get(f"/api/demo-orders/{o2['id']}").json()["order"]["status"] != "paid"


def test_expired_order(solana_app):
    c, st, _ = solana_app()
    create_session(c)
    order = create_demo_order(c).json()["order"]
    st.db.demo_orders.update_one(
        {"_id": order["id"]},
        {"$set": {"expiresAt": (now() - timedelta(seconds=1)).isoformat()}},
    )
    got = c.get(f"/api/demo-orders/{order['id']}").json()["order"]
    assert got["status"] == "expired"
    verify = c.post(f"/api/demo-orders/{order['id']}/verify", headers=H, json={})
    assert verify.status_code == 410
    assert verify.json()["code"] == "order_expired"
