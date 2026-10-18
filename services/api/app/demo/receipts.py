"""Demo cNFT receipt minting (Bubblegum V2). Payment success is independent of mint."""

from __future__ import annotations

import secrets

from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Any, Protocol

from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from app.demo.cnft_worker import CnftWorkerError, default_worker_dir, run_worker
from app.demo.rpc import DEVNET_GENESIS_HASH
from app.demo.verify import explorer_tx_url
from app.sessions.service import ApiProblem, now

RECEIPT_LABEL = "ClipCart demo receipt · Devnet · No retailer fulfillment."
# A build lease outlives every step its holder can still be in: devnet check (30 s) + build/sign worker (90 s),
# plus margin. Only after it expires may another request take over, and the holder's signed write is conditional
# on still holding its lease id, so a worker that lost the lease never persists or broadcasts what it built.
_BUILD_LEASE_TTL_S = 180


class MintAdapter(Protocol):
    def require_devnet(self) -> str: ...
    def build_sign_mint(
        self, *, tree: str, leaf_owner: str, name: str, uri: str
    ) -> dict: ...
    def send_signed(self, signed_tx_base64: str) -> str: ...
    def confirm(self, signature: str) -> dict: ...
    def parse_leaf(self, signature: str) -> dict: ...
    def get_asset(self, asset_id: str) -> dict: ...


@dataclass
class WorkerMintAdapter:
    settings: Any

    def _worker_dir(self) -> Path:
        raw = (getattr(self.settings, "solana_cnft_worker_dir", None) or "").strip()
        return Path(raw) if raw else default_worker_dir()

    def _kp(self) -> str:
        path = (self.settings.solana_cnft_authority_keypair_path or "").strip()
        if not path:
            raise ApiProblem(503, "cnft_not_configured", "Receipt authority keypair path not configured")
        return path

    def _rpc(self) -> str:
        return (self.settings.solana_rpc_url or "").rstrip("/")

    def require_devnet(self) -> str:
        body = run_worker(
            "genesis",
            worker_dir=self._worker_dir(),
            args=["--rpc", self._rpc()],
            timeout_s=30,
        )
        if body.get("genesis") != DEVNET_GENESIS_HASH:
            raise ApiProblem(503, "cnft_not_configured", "RPC is not Solana devnet", retryable=False)
        return body["genesis"]

    def build_sign_mint(self, *, tree: str, leaf_owner: str, name: str, uri: str) -> dict:
        return run_worker(
            "build-sign-mint",
            worker_dir=self._worker_dir(),
            args=[
                "--rpc",
                self._rpc(),
                "--keypair",
                self._kp(),
                "--tree",
                tree,
                "--leaf-owner",
                leaf_owner,
                "--name",
                name,
                "--uri",
                uri,
                "--seller-fee-bps",
                "0",
            ],
            timeout_s=90,
        )

    def send_signed(self, signed_tx_base64: str) -> str:
        body = run_worker(
            "send-signed",
            worker_dir=self._worker_dir(),
            args=["--rpc", self._rpc(), "--keypair", self._kp(), "--signed-tx", signed_tx_base64],
            timeout_s=90,
        )
        return body["signature"]

    def confirm(self, signature: str) -> dict:
        return run_worker(
            "confirm",
            worker_dir=self._worker_dir(),
            args=["--rpc", self._rpc(), "--signature", signature],
            timeout_s=60,
        )

    def parse_leaf(self, signature: str) -> dict:
        return run_worker(
            "parse-leaf",
            worker_dir=self._worker_dir(),
            args=["--rpc", self._rpc(), "--signature", signature],
            timeout_s=60,
        )

    def get_asset(self, asset_id: str) -> dict:
        das = (self.settings.solana_das_rpc_url or "").strip()
        if not das:
            raise CnftWorkerError("SOLANA_DAS_RPC_URL not configured", retryable=False)
        return run_worker(
            "get-asset",
            worker_dir=self._worker_dir(),
            args=["--das-rpc", das, "--asset-id", asset_id],
            timeout_s=60,
        )


def require_cnft_flags(settings: Any) -> None:
    if not settings.feature_solana:
        raise ApiProblem(404, "feature_disabled", "Solana demo checkout is turned off")
    if not settings.feature_solana_cnft_receipts:
        raise ApiProblem(404, "feature_disabled", "Solana cNFT receipts are turned off")


def require_durable_store(settings: Any) -> None:
    if settings.db_mode == "local_memory":
        raise ApiProblem(
            503,
            "cnft_durable_required",
            "Live cNFT minting requires durable MongoDB persistence (MONGODB_URI)",
            retryable=False,
        )


def require_cnft_config(settings: Any) -> tuple[str, str, str]:
    tree = (settings.solana_cnft_tree_address or "").strip()
    authority = (settings.solana_cnft_receipt_authority or "").strip()
    meta_base = (settings.solana_cnft_metadata_base_url or "").strip().rstrip("/")
    if not tree or not authority or not meta_base:
        raise ApiProblem(
            503,
            "cnft_not_configured",
            "cNFT tree, receipt authority, or metadata base URL is not configured",
            retryable=True,
        )
    if settings.solana_network != "devnet":
        raise ApiProblem(503, "cnft_not_configured", "Only Solana devnet is supported", retryable=False)
    return tree, authority, meta_base


def receipt_card(order: dict, attempt: dict | None) -> dict:
    sig = (attempt or {}).get("mintSignature") or order.get("receiptMintSignature")
    asset = (attempt or {}).get("assetId") or order.get("receiptAssetId")
    indexing = (attempt or {}).get("indexingStatus") or (
        "ready" if asset else ("pending" if sig else "unavailable")
    )
    status = order.get("receiptStatus") or "ineligible"
    from app.contracts import DemoReceipt

    return DemoReceipt(
        status=status, asset_id=asset, mint_signature=sig, explorer_mint_url=explorer_tx_url(sig) if sig else None,
        buyer_wallet=order.get("buyerWallet"), merkle_tree=(attempt or {}).get("merkleTree"), indexing_status=indexing,
        metadata_uri=(attempt or {}).get("metadataUri"), label=RECEIPT_LABEL,
    ).wire()


def _eligible_order(doc: dict) -> None:
    if doc.get("status") != "paid":
        raise ApiProblem(409, "receipt_ineligible", "Only server-verified paid demo orders can mint receipts")
    if not doc.get("paymentSignature") or not doc.get("buyerWallet"):
        raise ApiProblem(409, "receipt_ineligible", "Paid order is missing verified payment fields")
    if doc.get("receiptStatus") == "ineligible":
        raise ApiProblem(409, "receipt_ineligible", "Order is not receipt-eligible")


def _claim_attempt(db: Any, order: dict, *, tree: str, metadata_uri: str) -> dict:
    """Insert the durable attempt row (unique _id/orderId). Concurrent callers share one row."""
    oid = order["id"]
    t = now().isoformat()
    doc = {
        "_id": oid,
        "orderId": oid,
        "status": "claimed",
        "buyerWallet": order["buyerWallet"],
        "paymentSignature": order["paymentSignature"],
        "amountAtomic": order["amountAtomic"],
        "recipientWallet": order["recipientWallet"],
        "merkleTree": tree,
        "metadataUri": metadata_uri,
        "signedTxBase64": None,
        "mintSignature": None,
        "assetId": None,
        "indexingStatus": "unavailable",
        "error": None,
        "createdAt": t,
        "updatedAt": t,
    }
    try:
        db.receipt_mint_attempts.insert_one(doc)
        return doc
    except DuplicateKeyError:
        existing = db.receipt_mint_attempts.find_one({"_id": oid})
        if not existing:
            raise ApiProblem(409, "order_conflict", "Receipt attempt conflict", retryable=True)
        return existing


def _attempt_has_mint_work(attempt: dict) -> bool:
    return bool(
        attempt.get("mintSignature")
        or attempt.get("signedTxBase64")
        or attempt.get("status") in ("signed", "submitted", "confirmed", "needs_reconciliation")
    )


def _acquire_build_lease(db: Any, order_id: str) -> dict | None:
    """Exactly one concurrent caller may build a mint tx for this attempt.

    Transitions claimed → building. A stale building lease (no signed tx) may be
    reclaimed after its lease expires (_BUILD_LEASE_TTL_S) so restart can finish without a second mint
    once a signed tx exists — callers must still reconcile before any new build.
    """
    t = now()
    lease = {"status": "building", "updatedAt": t.isoformat(), "leaseId": secrets.token_hex(12),
             "leaseExpiresAt": (t + timedelta(seconds=_BUILD_LEASE_TTL_S)).isoformat()}
    won = db.receipt_mint_attempts.find_one_and_update(
        {
            "_id": order_id,
            "status": "claimed",
            "signedTxBase64": None,
            "mintSignature": None,
        },
        {"$set": lease},
        return_document=ReturnDocument.AFTER,
    )
    if won:
        return won
    return db.receipt_mint_attempts.find_one_and_update(
        {
            "_id": order_id,
            "status": "building",
            "signedTxBase64": None,
            "mintSignature": None,
            "leaseExpiresAt": {"$lt": t.isoformat()},
        },
        {"$set": lease},
        return_document=ReturnDocument.AFTER,
    )


def _set_attempt(db: Any, order_id: str, **fields: Any) -> dict:
    fields["updatedAt"] = now().isoformat()
    updated = db.receipt_mint_attempts.find_one_and_update(
        {"_id": order_id},
        {"$set": fields},
        return_document=ReturnDocument.AFTER,
    )
    if not updated:
        raise ApiProblem(409, "order_conflict", "Receipt attempt missing", retryable=True)
    return updated


def _set_order_receipt(db: Any, order_id: str, **fields: Any) -> dict:
    fields["updatedAt"] = now().isoformat()
    updated = db.demo_orders.find_one_and_update(
        {"_id": order_id},
        {"$set": fields},
        return_document=ReturnDocument.AFTER,
    )
    if not updated:
        raise ApiProblem(404, "not_found", "Demo order not found")
    return updated


def _metadata_uri(base: str, order_id: str) -> str:
    del order_id  # reserved for per-order URIs later
    if base.endswith(".json"):
        return base
    return f"{base}/cnft-receipt-demo-metadata.json"


def _reconcile_existing(adapter: MintAdapter, db: Any, order: dict, attempt: dict) -> tuple[dict, dict]:
    """Confirm / parse an existing signed or submitted attempt. Never builds a new tx."""
    oid = order["id"]
    sig = attempt.get("mintSignature")
    signed = attempt.get("signedTxBase64")

    if attempt.get("status") == "confirmed" and attempt.get("assetId"):
        order = _set_order_receipt(
            db,
            oid,
            receiptStatus="confirmed",
            receiptAssetId=attempt["assetId"],
            receiptMintSignature=sig,
        )
        return order, attempt

    if not sig and signed:
        try:
            sig = adapter.send_signed(signed)
            attempt = _set_attempt(db, oid, status="submitted", mintSignature=sig)
        except Exception as exc:  # noqa: BLE001
            attempt = _set_attempt(
                db,
                oid,
                status="needs_reconciliation",
                error=type(exc).__name__,
            )
            order = _set_order_receipt(db, oid, receiptStatus="needs_reconciliation")
            return order, attempt

    if not sig:
        return order, attempt

    try:
        conf = adapter.confirm(sig)
    except Exception as exc:  # noqa: BLE001
        attempt = _set_attempt(db, oid, status="needs_reconciliation", error=type(exc).__name__)
        order = _set_order_receipt(db, oid, receiptStatus="needs_reconciliation", receiptMintSignature=sig)
        return order, attempt

    if not conf.get("finalized"):
        if conf.get("err") is not None:
            attempt = _set_attempt(db, oid, status="failed", error="mint transaction failed on chain")
            order = _set_order_receipt(db, oid, receiptStatus="failed", receiptMintSignature=sig)
            return order, attempt
        attempt = _set_attempt(db, oid, status="submitted", indexingStatus="pending")
        order = _set_order_receipt(db, oid, receiptStatus="minting", receiptMintSignature=sig)
        return order, attempt

    try:
        leaf = adapter.parse_leaf(sig)
        asset_id = leaf.get("assetId")
        owner = leaf.get("owner")
        if owner and owner != order.get("buyerWallet"):
            attempt = _set_attempt(
                db,
                oid,
                status="failed",
                assetId=asset_id,
                error="mint leaf owner does not match paid buyerWallet",
            )
            order = _set_order_receipt(db, oid, receiptStatus="failed", receiptMintSignature=sig)
            return order, attempt
        indexing = "pending"
        try:
            asset = adapter.get_asset(asset_id)
            if asset.get("owner") == order.get("buyerWallet"):
                indexing = "ready"
        except Exception:  # noqa: BLE001
            indexing = "pending"
        attempt = _set_attempt(
            db,
            oid,
            status="confirmed",
            assetId=asset_id,
            indexingStatus=indexing,
            error=None,
        )
        order = _set_order_receipt(
            db,
            oid,
            receiptStatus="confirmed",
            receiptAssetId=asset_id,
            receiptMintSignature=sig,
        )
        return order, attempt
    except Exception as exc:  # noqa: BLE001
        attempt = _set_attempt(
            db,
            oid,
            status="confirmed",
            indexingStatus="pending",
            error=type(exc).__name__,
        )
        order = _set_order_receipt(db, oid, receiptStatus="confirmed", receiptMintSignature=sig)
        return order, attempt


def mint_receipt(
    st: Any,
    owner_id: str,
    order_id: str,
    *,
    adapter: MintAdapter | None = None,
) -> tuple[dict, dict]:
    """Claim/reconcile/mint a cNFT receipt. Checkout payment is never rolled back."""
    require_cnft_flags(st.settings)
    require_durable_store(st.settings)
    tree, _authority, meta_base = require_cnft_config(st.settings)

    doc = st.db.demo_orders.find_one({"_id": order_id, "ownerId": owner_id})
    if not doc:
        raise ApiProblem(404, "not_found", "Demo order not found")
    _eligible_order(doc)

    adapter = adapter or WorkerMintAdapter(st.settings)
    metadata_uri = _metadata_uri(meta_base, order_id)

    existing = st.db.receipt_mint_attempts.find_one({"_id": order_id})
    if existing:
        if _attempt_has_mint_work(existing):
            order, attempt = _reconcile_existing(adapter, st.db, doc, existing)
            return order, receipt_card(order, attempt)
        if existing.get("status") == "failed":
            return doc, receipt_card(doc, existing)

    st.db.demo_orders.update_one(
        {"_id": order_id, "receiptStatus": {"$in": ["eligible", "failed"]}},
        {"$set": {"receiptStatus": "minting", "updatedAt": now().isoformat()}},
    )
    # Durable unique row first — concurrent POSTs share one attempt document.
    attempt = _claim_attempt(st.db, doc, tree=tree, metadata_uri=metadata_uri)
    if _attempt_has_mint_work(attempt):
        order, attempt = _reconcile_existing(adapter, st.db, doc, attempt)
        return order, receipt_card(order, attempt)
    if attempt.get("status") == "failed":
        return doc, receipt_card(doc, attempt)

    # Only the lease holder may call build_sign_mint (prevents double mint under concurrency).
    leased = _acquire_build_lease(st.db, order_id)
    if leased is None:
        attempt = st.db.receipt_mint_attempts.find_one({"_id": order_id}) or attempt
        if _attempt_has_mint_work(attempt):
            order, attempt = _reconcile_existing(adapter, st.db, doc, attempt)
            return order, receipt_card(order, attempt)
        raise ApiProblem(409, "receipt_mint_in_progress", "A receipt mint for this order is already in progress",
                         retryable=True)

    lease_id = leased["leaseId"]
    try:
        adapter.require_devnet()
        built = adapter.build_sign_mint(
            tree=tree,
            leaf_owner=doc["buyerWallet"],
            name=f"ClipCart demo receipt {order_id[-8:]}",
            uri=metadata_uri,
        )
        if built.get("leafOwner") != doc["buyerWallet"]:
            raise CnftWorkerError("worker leafOwner mismatch", retryable=False)
        # Persist signed bytes before broadcast so restart reconciles instead of reminting — but only while this
        # request still holds its lease. A holder that lost it discards what it built and never broadcasts.
        attempt = st.db.receipt_mint_attempts.find_one_and_update(
            {"_id": order_id, "status": "building", "leaseId": lease_id, "signedTxBase64": None},
            {"$set": {"status": "signed", "signedTxBase64": built["signedTxBase64"],
                      "mintSignature": built.get("signature"), "metadataUri": metadata_uri, "merkleTree": tree,
                      "updatedAt": now().isoformat()},
             "$unset": {"leaseId": "", "leaseExpiresAt": ""}},
            return_document=ReturnDocument.AFTER,
        )
        if attempt is None:
            raise ApiProblem(409, "receipt_mint_in_progress", "Another request took over this receipt mint",
                             retryable=True)
        try:
            sig = adapter.send_signed(built["signedTxBase64"])
        except Exception as exc:  # noqa: BLE001
            attempt = _set_attempt(
                st.db,
                order_id,
                status="needs_reconciliation",
                error=f"broadcast uncertain: {type(exc).__name__}",
            )
            order = _set_order_receipt(st.db, order_id, receiptStatus="needs_reconciliation")
            return order, receipt_card(order, attempt)
        attempt = _set_attempt(st.db, order_id, status="submitted", mintSignature=sig)
        order = _set_order_receipt(st.db, order_id, receiptStatus="minting", receiptMintSignature=sig)
        order, attempt = _reconcile_existing(adapter, st.db, order, attempt)
        return order, receipt_card(order, attempt)
    except ApiProblem:
        raise
    except Exception as exc:  # noqa: BLE001
        attempt = _set_attempt(st.db, order_id, status="failed", error=type(exc).__name__)
        order = _set_order_receipt(st.db, order_id, receiptStatus="failed")
        return order, receipt_card(order, attempt)


def get_receipt_for_order(st: Any, order: dict) -> dict | None:
    if not st.settings.feature_solana_cnft_receipts:
        return None
    if order.get("receiptStatus") in (None, "ineligible"):
        return None
    attempt = st.db.receipt_mint_attempts.find_one({"_id": order["id"]})
    return receipt_card(order, attempt)
