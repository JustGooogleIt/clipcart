"""Owner-scoped demo order create / get / verify with atomic signature claims."""

from __future__ import annotations

import secrets
from datetime import timedelta
from typing import Any

from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from app.contracts.base import from_doc
from app.contracts.demo_orders import DemoMerchantOrder
from app.demo.base58util import b58encode, is_pubkey
from app.demo.catalog import (
    DEFAULT_AMOUNT_LAMPORTS,
    FULFILLMENT_TERMS,
    MERCHANT_LABEL,
    get_catalog_item,
)
from app.demo.rpc import SolanaRpc
from app.demo.verify import explorer_tx_url, parse_order_unix, verify_payment
from app.sessions.service import ApiProblem, new_id, now


class VerifyMeta:
    def __init__(
        self,
        http_status: int,
        code: str | None,
        message: str | None,
        retryable: bool,
        *,
        rpc_invoked: bool = False,
    ):
        self.http_status = http_status
        self.code = code
        self.message = message
        self.retryable = retryable
        # False when returning an already-paid order without calling Solana RPC.
        self.rpc_invoked = rpc_invoked


def _new_reference() -> str:
    return b58encode(secrets.token_bytes(32))


def public_order(doc: dict) -> dict:
    order = from_doc(DemoMerchantOrder, doc)
    wire = order.wire()
    wire.pop("ownerId", None)
    # Display helpers already on the record; strip verification internals from clients.
    wire.pop("verificationError", None)
    return wire


def transfer_request(doc: dict) -> dict:
    lamports = int(doc["amountAtomic"])
    sol = lamports / 1_000_000_000
    amount = f"{sol:.2f}".rstrip("0").rstrip(".") if sol >= 0.01 else f"{sol:.9f}".rstrip("0").rstrip(".")
    if amount == "":
        amount = "0"
    # Fixed demo price is always 0.01 SOL for the controlled item.
    if lamports == DEFAULT_AMOUNT_LAMPORTS:
        amount = "0.01"
    return {
        "recipient": doc["recipientWallet"],
        "amount": amount,
        "splToken": None,
        "reference": doc["paymentReference"],
        "label": doc.get("merchantLabel") or MERCHANT_LABEL,
        "message": f"ClipCart demo order {doc['id']}",
        "memo": None,
    }


def _expire_if_needed(db: Any, doc: dict) -> dict:
    if doc["status"] in ("paid", "failed", "expired"):
        return doc
    expires = doc.get("expiresAt")
    if isinstance(expires, str):
        from datetime import datetime

        expires_dt = datetime.fromisoformat(expires.replace("Z", "+00:00"))
    else:
        expires_dt = expires
    if expires_dt and expires_dt <= now():
        updated = db.demo_orders.find_one_and_update(
            {"_id": doc["_id"], "status": {"$nin": ["paid", "failed", "expired"]}},
            {"$set": {"status": "expired", "updatedAt": now().isoformat()}},
            return_document=ReturnDocument.AFTER,
        )
        return updated or doc
    return doc


def require_solana_config(settings: Any) -> tuple[str, int, str]:
    wallet = (settings.solana_demo_merchant_wallet or "").strip()
    if not wallet or not is_pubkey(wallet):
        raise ApiProblem(
            503,
            "solana_not_configured",
            "Demo merchant wallet is not configured for Solana checkout",
            retryable=True,
        )
    rpc_url = (settings.solana_rpc_url or "").strip()
    if not rpc_url:
        raise ApiProblem(503, "solana_not_configured", "Solana RPC URL is not configured", retryable=True)
    if settings.solana_network != "devnet":
        raise ApiProblem(503, "solana_not_configured", "Only Solana devnet is supported", retryable=False)
    amount = int(settings.solana_demo_amount_lamports)
    if amount != DEFAULT_AMOUNT_LAMPORTS:
        # Keep the controlled demo item fixed at 0.01 SOL; misconfiguration is refused.
        raise ApiProblem(
            503,
            "solana_not_configured",
            "Demo amount must be 10000000 lamports (0.01 SOL)",
            retryable=False,
        )
    return wallet, amount, rpc_url


def create_order(st: Any, owner_id: str, catalog_item_id: str) -> dict:
    recipient, amount, _rpc = require_solana_config(st.settings)
    item = get_catalog_item(catalog_item_id, amount)
    if item is None:
        raise ApiProblem(404, "not_found", "Demo catalog item not found")

    t = now()
    ttl = int(st.settings.solana_demo_order_ttl_s)
    oid = new_id("dmo")
    order = DemoMerchantOrder(
        id=oid,
        owner_id=owner_id,
        catalog_item_id=item.id,
        merchant_id=item.merchant_id,
        recipient_wallet=recipient,
        buyer_wallet=None,
        network="devnet",
        asset_mint=None,
        amount_atomic=item.amount_atomic,
        payment_reference=_new_reference(),
        expires_at=t + timedelta(seconds=ttl),
        status="awaiting_payment",
        payment_signature=None,
        receipt_status="ineligible",
        receipt_asset_id=None,
        receipt_mint_signature=None,
        created_at=t,
        updated_at=t,
        merchant_label=item.merchant_label,
        fulfillment_terms=item.fulfillment_terms or FULFILLMENT_TERMS,
        ui_label="Demo purchase on Solana devnet",
        explorer_payment_url=None,
        verification_error=None,
    )
    doc = {"_id": order.id, **order.wire()}
    st.db.demo_orders.insert_one(doc)
    return doc


def get_owned_order(db: Any, order_id: str, owner_id: str) -> dict:
    doc = db.demo_orders.find_one({"_id": order_id, "ownerId": owner_id})
    if not doc:
        raise ApiProblem(404, "not_found", "Demo order not found")
    return _expire_if_needed(db, doc)


def _claim_signature(db: Any, signature: str, order_id: str) -> None:
    try:
        db.payment_signatures.insert_one(
            {"_id": signature, "orderId": order_id, "claimedAt": now().isoformat()}
        )
    except DuplicateKeyError:
        existing = db.payment_signatures.find_one({"_id": signature})
        if not existing or existing.get("orderId") != order_id:
            raise ApiProblem(
                409,
                "signature_reused",
                "This payment signature is already claimed by another order",
            ) from None


def _mark_paid(db: Any, order_id: str, *, signature: str, buyer: str) -> dict:
    _claim_signature(db, signature, order_id)
    updated = db.demo_orders.find_one_and_update(
        {
            "_id": order_id,
            "status": {"$in": ["awaiting_payment", "verifying", "created"]},
        },
        {
            "$set": {
                "status": "paid",
                "paymentSignature": signature,
                "buyerWallet": buyer,
                "receiptStatus": "eligible",
                "explorerPaymentUrl": explorer_tx_url(signature),
                "verificationError": None,
                "updatedAt": now().isoformat(),
            }
        },
        return_document=ReturnDocument.AFTER,
    )
    if updated is None:
        # Race: another request paid it, or status moved.
        current = db.demo_orders.find_one({"_id": order_id})
        if current and current.get("status") == "paid":
            if current.get("paymentSignature") == signature:
                return current
            raise ApiProblem(409, "signature_reused", "Order already paid with a different signature")
        raise ApiProblem(409, "order_conflict", "Order could not be marked paid", retryable=True)
    return updated


def verify_order(
    st: Any,
    owner_id: str,
    order_id: str,
    *,
    payment_signature: str | None,
    buyer_wallet: str | None,
    rpc: SolanaRpc | None = None,
) -> tuple[dict, VerifyMeta]:
    doc = get_owned_order(st.db, order_id, owner_id)
    if doc["status"] == "paid":
        # Idempotent replay — must not be counted as a fresh Solana RPC verification.
        return doc, VerifyMeta(
            http_status=200, code=None, message=None, retryable=False, rpc_invoked=False
        )
    if doc["status"] == "expired":
        raise ApiProblem(410, "order_expired", "This demo order expired; create a new one")
    if doc["status"] == "failed":
        raise ApiProblem(409, "order_failed", "This demo order can no longer be paid")

    if buyer_wallet and not is_pubkey(buyer_wallet):
        raise ApiProblem(422, "invalid_buyer_wallet", "buyerWallet must be a base58 pubkey")
    if payment_signature is not None and (len(payment_signature) < 64 or len(payment_signature) > 128):
        raise ApiProblem(422, "invalid_signature", "paymentSignature looks invalid")

    recipient, amount, rpc_url = require_solana_config(st.settings)
    paid_not_before = parse_order_unix(doc.get("createdAt"))
    paid_not_after = parse_order_unix(doc.get("expiresAt"))
    st.db.demo_orders.update_one(
        {"_id": order_id, "status": {"$in": ["awaiting_payment", "created"]}},
        {"$set": {"status": "verifying", "updatedAt": now().isoformat()}},
    )

    owned_rpc = rpc is None
    rpc = rpc or SolanaRpc(rpc_url)
    try:
        result = verify_payment(
            rpc,
            recipient=recipient,
            amount_lamports=amount,
            payment_reference=doc["paymentReference"],
            signature_hint=payment_signature,
            buyer_hint=buyer_wallet,
            paid_not_before=paid_not_before,
            paid_not_after=paid_not_after,
        )
    finally:
        if owned_rpc:
            rpc.close()

    if result.outcome == "paid" and result.payment_signature and result.buyer_wallet:
        try:
            paid = _mark_paid(
                st.db,
                order_id,
                signature=result.payment_signature,
                buyer=result.buyer_wallet,
            )
        except ApiProblem as exc:
            if exc.code == "signature_reused":
                # Roll verifying back only if still verifying.
                st.db.demo_orders.update_one(
                    {"_id": order_id, "status": "verifying"},
                    {"$set": {"status": "awaiting_payment", "updatedAt": now().isoformat()}},
                )
            raise
        return paid, VerifyMeta(
            http_status=200, code=None, message=None, retryable=False, rpc_invoked=True
        )

    if result.outcome in ("unconfirmed", "missing", "rpc_error"):
        st.db.demo_orders.update_one(
            {"_id": order_id, "status": "verifying"},
            {
                "$set": {
                    "status": "awaiting_payment",
                    "verificationError": result.detail,
                    "updatedAt": now().isoformat(),
                }
            },
        )
        refreshed = st.db.demo_orders.find_one({"_id": order_id})
        code = {
            "unconfirmed": "payment_unconfirmed",
            "missing": "payment_missing",
            "rpc_error": "rpc_unavailable",
        }[result.outcome]
        return refreshed, VerifyMeta(
            http_status=409,
            code=code,
            message=result.detail or "Payment not yet verifiable",
            retryable=True,
            rpc_invoked=True,
        )

    # mismatch — definitive rejection of this verification attempt
    st.db.demo_orders.update_one(
        {"_id": order_id, "status": {"$in": ["verifying", "awaiting_payment"]}},
        {
            "$set": {
                "status": "failed",
                "verificationError": result.detail,
                "updatedAt": now().isoformat(),
            }
        },
    )
    refreshed = st.db.demo_orders.find_one({"_id": order_id})
    return refreshed, VerifyMeta(
        http_status=422,
        code="payment_mismatch",
        message=result.detail or "Payment does not match this order",
        retryable=False,
        rpc_invoked=True,
    )
