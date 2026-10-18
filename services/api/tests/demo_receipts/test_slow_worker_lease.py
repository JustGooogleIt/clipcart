"""Duplicate-mint race with a slow worker: the lease must outlive the worker, and only the lease holder may persist
(and so broadcast) a signed transaction. Runs on mongomock, or on real MongoDB via CLIPCART_TEST_MONGODB_URI."""

import threading
import time
from datetime import timedelta

import app.demo.receipts as R
from app.sessions.service import now


def test_lease_outlives_worker_timeouts():
    assert R._BUILD_LEASE_TTL_S > 30 + 90  # devnet check + build/sign worker timeouts


def _attempt(db, oid="dmo_lease"):
    db.receipt_mint_attempts.insert_one({"_id": oid, "orderId": oid, "status": "claimed", "signedTxBase64": None,
                                         "mintSignature": None})
    return oid


def test_unexpired_lease_blocks_a_second_builder(app_factory):
    db = app_factory().state.clipcart.db
    oid = _attempt(db)
    first = R._acquire_build_lease(db, oid)
    assert first and first["leaseId"]
    assert R._acquire_build_lease(db, oid) is None  # held: nobody else builds while the holder can still sign


def test_expired_lease_takeover_never_lets_the_old_holder_persist(app_factory):
    db = app_factory().state.clipcart.db
    oid = _attempt(db)
    old = R._acquire_build_lease(db, oid)
    db.receipt_mint_attempts.update_one({"_id": oid}, {"$set": {"leaseExpiresAt": (now() - timedelta(seconds=1)).isoformat()}})
    new = R._acquire_build_lease(db, oid)
    assert new and new["leaseId"] != old["leaseId"]
    lost = db.receipt_mint_attempts.find_one_and_update(
        {"_id": oid, "status": "building", "leaseId": old["leaseId"], "signedTxBase64": None},
        {"$set": {"status": "signed", "signedTxBase64": "old"}})
    assert lost is None  # the slow original holder can't persist, so it can't broadcast


def test_slow_worker_takeover_after_forced_expiry_still_sends_once(cnft_app, monkeypatch):
    """Worker slower than the lease (forced tiny TTL): a takeover may build, but only the current lease holder can
    persist a signed tx, so exactly one transaction is ever broadcast."""
    from concurrent.futures import ThreadPoolExecutor

    from app.sessions.service import ApiProblem

    from demo_receipts.conftest import paid_demo_order
    from demo_receipts.test_concurrent_mint import SlowFakeMint

    fake = SlowFakeMint()
    fake.delay_s = 0.5
    c, st, _ = cnft_app(adapter=fake)
    order = paid_demo_order(c, st)
    monkeypatch.setattr(R, "_BUILD_LEASE_TTL_S", 0.2)

    def one(delay):
        time.sleep(delay)
        try:
            return R.mint_receipt(st, order["ownerId"], order["id"], adapter=fake)
        except ApiProblem as exc:
            return exc.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        out = list(pool.map(one, [0, 0.3]))  # second arrives after the first's lease expired, while it still builds
    assert fake.send_calls == 1, out
    att = st.db.receipt_mint_attempts.find_one({"_id": order["id"]})
    assert att["status"] in ("submitted", "confirmed") and att["signedTxBase64"]
