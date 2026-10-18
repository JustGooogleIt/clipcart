"""Payment verification boundary tests. No live RPC."""

from __future__ import annotations

from app.demo.base58util import b58encode
from app.demo.rpc import DEVNET_GENESIS_HASH
from app.demo.verify import inspect_transaction, verify_payment
from demo_orders.conftest import BUYER, MERCHANT, OTHER, SIG_OK, SIG_OTHER, FakeRpc, transfer_tx


def test_inspect_accepts_exact_native_transfer():
    ref = "Ref" + "1" * 40
    # reference must be valid-looking in keys list only; inspect does not b58-check
    ref = BUYER  # reuse a 32-byte key as reference for the fixture
    tx = transfer_tx(source=BUYER, dest=MERCHANT, lamports=10_000_000, reference=ref)
    r = inspect_transaction(
        tx, recipient=MERCHANT, amount_lamports=10_000_000, payment_reference=ref, buyer_hint=BUYER
    )
    assert r.outcome == "paid" and r.buyer_wallet == BUYER


def test_inspect_rejects_wrong_amount_recipient_reference_buyer():
    ref = OTHER
    tx = transfer_tx(source=BUYER, dest=MERCHANT, lamports=10_000_000, reference=ref)
    assert (
        inspect_transaction(
            tx, recipient=MERCHANT, amount_lamports=9_999_999, payment_reference=ref, buyer_hint=None
        ).outcome
        == "mismatch"
    )
    assert (
        inspect_transaction(
            tx, recipient=OTHER, amount_lamports=10_000_000, payment_reference=ref, buyer_hint=None
        ).outcome
        == "mismatch"
    )
    missing_ref = b58encode(bytes([0x11] * 32))
    assert (
        inspect_transaction(
            tx, recipient=MERCHANT, amount_lamports=10_000_000, payment_reference=missing_ref, buyer_hint=None
        ).outcome
        == "mismatch"
    )
    assert (
        inspect_transaction(
            tx, recipient=MERCHANT, amount_lamports=10_000_000, payment_reference=ref, buyer_hint=OTHER
        ).outcome
        == "mismatch"
    )


def test_inspect_rejects_failed_transaction():
    ref = OTHER
    tx = transfer_tx(source=BUYER, dest=MERCHANT, lamports=10_000_000, reference=ref, err={"InstructionError": [0, "x"]})
    assert (
        inspect_transaction(
            tx, recipient=MERCHANT, amount_lamports=10_000_000, payment_reference=ref, buyer_hint=None
        ).outcome
        == "mismatch"
    )


def test_verify_payment_happy_path_by_reference():
    ref = OTHER
    tx = transfer_tx(source=BUYER, dest=MERCHANT, lamports=10_000_000, reference=ref)
    rpc = FakeRpc(
        statuses={SIG_OK: {"confirmationStatus": "confirmed", "err": None}},
        transactions={SIG_OK: tx},
        by_address={ref: [{"signature": SIG_OK, "err": None}]},
    )
    r = verify_payment(
        rpc,
        recipient=MERCHANT,
        amount_lamports=10_000_000,
        payment_reference=ref,
        signature_hint=None,
        buyer_hint=BUYER,
    )
    assert r.outcome == "paid" and r.payment_signature == SIG_OK and r.buyer_wallet == BUYER


def test_verify_payment_uses_signature_hint_and_rejects_wrong_network():
    ref = OTHER
    tx = transfer_tx(source=BUYER, dest=MERCHANT, lamports=10_000_000, reference=ref)
    rpc = FakeRpc(
        statuses={SIG_OK: {"confirmationStatus": "finalized", "err": None}},
        transactions={SIG_OK: tx},
        by_address={},
    )
    r = verify_payment(
        rpc,
        recipient=MERCHANT,
        amount_lamports=10_000_000,
        payment_reference=ref,
        signature_hint=SIG_OK,
        buyer_hint=None,
    )
    assert r.outcome == "paid"

    bad = FakeRpc(genesis="MainnetGenesisHashXXXX")
    assert (
        verify_payment(
            bad, recipient=MERCHANT, amount_lamports=10_000_000, payment_reference=ref
        ).outcome
        == "rpc_error"
    )
    assert bad.genesis != DEVNET_GENESIS_HASH


def test_verify_unconfirmed_and_missing_are_retryable():
    ref = OTHER
    rpc = FakeRpc(
        statuses={SIG_OK: {"confirmationStatus": "processed", "err": None}},
        transactions={},
        by_address={ref: [{"signature": SIG_OK, "err": None}]},
    )
    r = verify_payment(rpc, recipient=MERCHANT, amount_lamports=10_000_000, payment_reference=ref)
    assert r.outcome == "unconfirmed" and r.retryable

    empty = FakeRpc(by_address={ref: []})
    r2 = verify_payment(empty, recipient=MERCHANT, amount_lamports=10_000_000, payment_reference=ref)
    assert r2.outcome == "missing" and r2.retryable


def test_bad_hint_still_finds_good_reference_payment():
    ref = OTHER
    good = transfer_tx(source=BUYER, dest=MERCHANT, lamports=10_000_000, reference=ref)
    bad = transfer_tx(source=BUYER, dest=MERCHANT, lamports=1, reference=ref)
    rpc = FakeRpc(
        statuses={
            SIG_OTHER: {"confirmationStatus": "confirmed", "err": None},
            SIG_OK: {"confirmationStatus": "confirmed", "err": None},
        },
        transactions={SIG_OTHER: bad, SIG_OK: good},
        by_address={ref: [{"signature": SIG_OK, "err": None}]},
    )
    r = verify_payment(
        rpc,
        recipient=MERCHANT,
        amount_lamports=10_000_000,
        payment_reference=ref,
        signature_hint=SIG_OTHER,
        buyer_hint=None,
    )
    # Hint mismatches; reference scan still locates the correct transfer.
    assert r.outcome == "paid" and r.payment_signature == SIG_OK


def test_inspect_enforces_order_time_window():
    ref = OTHER
    bt = 1_700_000_100
    tx = transfer_tx(source=BUYER, dest=MERCHANT, lamports=10_000_000, reference=ref, block_time=bt)
    assert (
        inspect_transaction(
            tx,
            recipient=MERCHANT,
            amount_lamports=10_000_000,
            payment_reference=ref,
            buyer_hint=None,
            paid_not_before=bt - 10,
            paid_not_after=bt + 10,
        ).outcome
        == "paid"
    )
    assert (
        inspect_transaction(
            tx,
            recipient=MERCHANT,
            amount_lamports=10_000_000,
            payment_reference=ref,
            buyer_hint=None,
            paid_not_before=bt + 1,
            paid_not_after=bt + 10,
        ).detail
        == "transaction blockTime before order createdAt"
    )
    assert (
        inspect_transaction(
            tx,
            recipient=MERCHANT,
            amount_lamports=10_000_000,
            payment_reference=ref,
            buyer_hint=None,
            paid_not_before=bt - 10,
            paid_not_after=bt - 1,
        ).detail
        == "transaction blockTime after order expiresAt"
    )
    missing_bt = transfer_tx(
        source=BUYER, dest=MERCHANT, lamports=10_000_000, reference=ref, block_time=None
    )
    assert (
        inspect_transaction(
            missing_bt,
            recipient=MERCHANT,
            amount_lamports=10_000_000,
            payment_reference=ref,
            buyer_hint=None,
            paid_not_before=bt - 10,
            paid_not_after=bt + 10,
        ).detail
        == "transaction blockTime missing"
    )
