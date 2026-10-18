"""Concurrent receipt mint must claim one attempt and build once (FakeMintAdapter only)."""

from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from api.conftest import H
from app.demo.receipts import mint_receipt
from demo_receipts.conftest import FakeMintAdapter, paid_demo_order


class SlowFakeMint(FakeMintAdapter):
    """Widen the race window so concurrent POSTs contend on the build lease."""

    def __init__(self, delay_s: float = 0.08):
        super().__init__()
        self.delay_s = delay_s
        self._lock = threading.Lock()

    def build_sign_mint(self, *, tree: str, leaf_owner: str, name: str, uri: str) -> dict:
        time.sleep(self.delay_s)
        with self._lock:
            return super().build_sign_mint(tree=tree, leaf_owner=leaf_owner, name=name, uri=uri)


def test_concurrent_receipt_requests_single_build(cnft_app, monkeypatch):
    fake = SlowFakeMint()
    c, st, _ = cnft_app(adapter=fake)
    order = paid_demo_order(c, st)
    monkeypatch.setattr("app.demo.receipts.WorkerMintAdapter", lambda settings: fake)
    owner = order["ownerId"]
    oid = order["id"]

    def one():
        return mint_receipt(st, owner, oid, adapter=fake)

    n = 8
    with ThreadPoolExecutor(max_workers=n) as pool:
        futs = [pool.submit(one) for _ in range(n)]
        results = [f.result(timeout=30) for f in as_completed(futs)]

    assert fake.build_calls == 1
    assert fake.send_calls == 1
    attempts = list(st.db.receipt_mint_attempts.find({"orderId": oid}))
    assert len(attempts) == 1
    assert attempts[0].get("status") == "confirmed"
    assert attempts[0].get("assetId") == fake.asset_id
    assert any(receipt.get("assetId") == fake.asset_id for _order, receipt in results)
    for _order, _receipt in results:
        assert _order["status"] == "paid"
    # Retry must reconcile the durable attempt — never a second build.
    _order, receipt = mint_receipt(st, owner, oid, adapter=fake)
    assert receipt["assetId"] == fake.asset_id
    assert fake.build_calls == 1


def test_restart_reconciles_signed_attempt_without_rebuild(cnft_app, monkeypatch):
    c, st, fake = cnft_app()
    order = paid_demo_order(c, st)
    monkeypatch.setattr("app.demo.receipts.WorkerMintAdapter", lambda settings: fake)

    # Simulate crash after signed bytes persisted, before/during broadcast.
    st.db.receipt_mint_attempts.insert_one(
        {
            "_id": order["id"],
            "orderId": order["id"],
            "status": "signed",
            "buyerWallet": order["buyerWallet"],
            "paymentSignature": order["paymentSignature"],
            "amountAtomic": order["amountAtomic"],
            "recipientWallet": order["recipientWallet"],
            "merkleTree": "Tree" + "1" * 40,
            "metadataUri": "https://example.com/meta.json",
            "signedTxBase64": fake.signed_b64,
            "mintSignature": fake.signature,
            "assetId": None,
            "indexingStatus": "pending",
            "error": None,
            "createdAt": "2026-01-01T00:00:00+00:00",
            "updatedAt": "2026-01-01T00:00:00+00:00",
        }
    )
    st.db.demo_orders.update_one(
        {"_id": order["id"]},
        {"$set": {"receiptStatus": "minting", "receiptMintSignature": fake.signature}},
    )

    r = c.post(f"/api/demo-orders/{order['id']}/receipt/mint", headers=H)
    assert r.status_code == 200
    assert r.json()["receipt"]["assetId"] == fake.asset_id
    # Signed attempt already has mintSignature — reconcile confirms/parses, never rebuilds.
    assert fake.build_calls == 0
    assert fake.send_calls == 0
    assert r.json()["order"]["receiptStatus"] == "confirmed"
