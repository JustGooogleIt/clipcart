#!/usr/bin/env python3
"""Reproduce/verify Terminal Solana blockers against real MongoDB (Atlas).

Does not drop collections or delete payment evidence. Cleans only probe docs
created by this run. Uses FakeMintAdapter — no live payment/tree/mint.
"""

from __future__ import annotations

import json
import os
import sys
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import timedelta
from pathlib import Path

API_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(API_ROOT))

os.environ.setdefault("CLIPCART_SKIP_DOTENV", "0")

from app.demo.receipts import mint_receipt  # noqa: E402
from app.main import create_app  # noqa: E402
from app.sessions.service import now  # noqa: E402
from app.storage.db import ensure_indexes  # noqa: E402


class FakeMint:
    def __init__(self):
        self.build_calls = 0
        self.send_calls = 0
        self._lock = threading.Lock()
        self.signed_b64 = "c2lnbmVk"
        self.signature = "MintSigAtlas" + "9" * 70
        self.asset_id = "AssetAtlas" + "9" * 35
        self.leaf_owner = None

    def require_devnet(self) -> str:
        from app.demo.rpc import DEVNET_GENESIS_HASH

        return DEVNET_GENESIS_HASH

    def build_sign_mint(self, *, tree: str, leaf_owner: str, name: str, uri: str) -> dict:
        time.sleep(0.08)
        with self._lock:
            self.build_calls += 1
            self.leaf_owner = leaf_owner
            return {
                "signedTxBase64": self.signed_b64,
                "signature": self.signature,
                "leafOwner": leaf_owner,
                "merkleTree": tree,
            }

    def send_signed(self, signed_tx_base64: str) -> str:
        with self._lock:
            self.send_calls += 1
        return self.signature

    def confirm(self, signature: str) -> dict:
        return {"signature": signature, "confirmationStatus": "finalized", "err": None, "finalized": True}

    def parse_leaf(self, signature: str) -> dict:
        return {"assetId": self.asset_id, "owner": self.leaf_owner, "nonce": 0}

    def get_asset(self, asset_id: str) -> dict:
        return {"assetId": asset_id, "owner": self.leaf_owner}


def main() -> int:
    os.environ["FEATURE_SOLANA"] = "true"
    os.environ["FEATURE_SOLANA_CNFT_RECEIPTS"] = "true"
    os.environ.setdefault("SOLANA_CNFT_TREE_ADDRESS", "Tree" + "1" * 40)
    os.environ.setdefault("SOLANA_CNFT_RECEIPT_AUTHORITY", "Auth" + "1" * 40)
    os.environ.setdefault("SOLANA_CNFT_AUTHORITY_KEYPAIR_PATH", "/tmp/fake.json")
    os.environ.setdefault("SOLANA_DAS_RPC_URL", "https://das.example.invalid")
    os.environ.setdefault("SOLANA_CNFT_METADATA_BASE_URL", "https://example.com/meta.json")
    os.environ.setdefault("SOLANA_DEMO_MERCHANT_WALLET", "3yVVaxvuDpXBJWFGetwdCAC3bRXoo4d7bjXeX5Xn8y73")

    app = create_app()
    st = app.state.clipcart
    if st.settings.db_mode == "local_memory":
        print(json.dumps({"ok": False, "error": "MONGODB_URI required"}))
        return 2

    db = st.db
    ensure_indexes(db)
    uri = os.environ.get("MONGODB_URI", "")
    host = uri.split("@")[-1].split("/")[0] if "@" in uri else "(redacted)"
    tag = f"atlas_reg_{uuid.uuid4().hex[:10]}"
    owner = f"own_{tag}"
    buyer = "8W3Rgm2MFFkA3SP1TcUuvVaHMAPhJshZ4rdgJw2QSwjo"
    out: dict = {
        "ok": True,
        "mongodbHost": host,
        "mongodbDb": st.settings.mongodb_db,
        "dbMode": st.settings.db_mode,
        "checks": {},
    }

    # --- preserved receipt presence (read-only) ---
    pay = "3KjLMeXJUjidmxgbsvqWZQVCfHeBAupHnTk8rdc2EkNjr12A7iCCRXsgkbYqyjLVsioAPmsoDGPtA2Psz51HkbJh"
    asset = "HEtzjRrzUzYrSo2AaQJJsb5UXAXRXb8phLBchW7KUEhq"
    oid_preserved = "dmo_V-lqM-ub8XR8bsg5"
    preserved = (
        db.demo_orders.find_one({"_id": oid_preserved})
        or db.demo_orders.find_one({"paymentSignature": pay})
        or db.demo_orders.find_one({"receiptAssetId": asset})
        or db.receipt_mint_attempts.find_one({"_id": oid_preserved})
        or db.receipt_mint_attempts.find_one({"assetId": asset})
        or db.payment_signatures.find_one({"_id": pay})
    )
    out["preservedReceiptInAtlas"] = bool(preserved)
    out["preservedReceiptApiAvailable"] = False
    if preserved and preserved.get("ownerId") and preserved.get("receiptAssetId"):
        out["preservedReceiptApiAvailable"] = True
        out["preserved"] = {
            "orderId": preserved.get("_id") or preserved.get("orderId"),
            "ownerId": preserved.get("ownerId"),
            "receiptAssetId": preserved.get("receiptAssetId") or preserved.get("assetId"),
        }

    probe_ids: list[str] = []
    try:
        # 1) Multiple unpaid null signatures
        for i in range(2):
            oid = f"dmo_{tag}_u{i}"
            probe_ids.append(oid)
            db.demo_orders.insert_one(
                {
                    "_id": oid,
                    "id": oid,
                    "ownerId": owner,
                    "paymentReference": f"ref_{tag}_{i}",
                    "paymentSignature": None,
                    "status": "awaiting_payment",
                    "createdAt": now().isoformat(),
                    "updatedAt": now().isoformat(),
                }
            )
        out["checks"]["multipleUnpaidCoexist"] = (
            db.demo_orders.count_documents({"_id": {"$in": probe_ids}}) == 2
        )

        # 2) Payment signature uniqueness across paid orders
        paid_a, paid_b = f"dmo_{tag}_p0", f"dmo_{tag}_p1"
        probe_ids.extend([paid_a, paid_b])
        sig = f"Sig{tag}" + "1" * (88 - len(tag) - 3)
        for oid in (paid_a, paid_b):
            db.demo_orders.insert_one(
                {
                    "_id": oid,
                    "id": oid,
                    "ownerId": owner,
                    "paymentReference": f"ref_{oid}",
                    "paymentSignature": sig if oid == paid_a else None,
                    "status": "paid" if oid == paid_a else "awaiting_payment",
                    "buyerWallet": buyer,
                    "amountAtomic": "10000000",
                    "recipientWallet": st.settings.solana_demo_merchant_wallet,
                    "receiptStatus": "eligible" if oid == paid_a else "ineligible",
                    "createdAt": now().isoformat(),
                    "updatedAt": now().isoformat(),
                }
            )
        db.payment_signatures.insert_one({"_id": sig, "orderId": paid_a, "claimedAt": now().isoformat()})
        dup_ok = False
        try:
            db.demo_orders.update_one({"_id": paid_b}, {"$set": {"paymentSignature": sig}})
        except Exception:  # noqa: BLE001
            dup_ok = True
        # Also enforce via payment_signatures claim collection
        from pymongo.errors import DuplicateKeyError

        try:
            db.payment_signatures.insert_one({"_id": sig, "orderId": paid_b})
            claim_unique = False
        except DuplicateKeyError:
            claim_unique = True
        # Partial unique on demo_orders.paymentSignature
        from pymongo.errors import DuplicateKeyError as DKE

        try:
            db.demo_orders.insert_one(
                {
                    "_id": f"dmo_{tag}_dup",
                    "paymentReference": f"ref_{tag}_dup",
                    "paymentSignature": sig,
                    "ownerId": owner,
                    "status": "paid",
                }
            )
            probe_ids.append(f"dmo_{tag}_dup")
            order_sig_unique = False
        except DKE:
            order_sig_unique = True
        out["checks"]["paymentSignatureUnique"] = claim_unique and order_sig_unique

        # 3) Concurrent mint — one durable attempt, one build
        mint_oid = f"dmo_{tag}_m"
        probe_ids.append(mint_oid)
        db.demo_orders.insert_one(
            {
                "_id": mint_oid,
                "id": mint_oid,
                "ownerId": owner,
                "catalogItemId": "demo_item_clipcart_jacket_01",
                "merchantId": "clipcart_demo",
                "recipientWallet": st.settings.solana_demo_merchant_wallet,
                "buyerWallet": buyer,
                "network": "devnet",
                "amountAtomic": "10000000",
                "paymentReference": f"ref_{mint_oid}",
                "expiresAt": (now() + timedelta(days=1)).isoformat(),
                "status": "paid",
                "paymentSignature": f"Pay{tag}" + "2" * (88 - len(tag) - 3),
                "receiptStatus": "eligible",
                "receiptAssetId": None,
                "receiptMintSignature": None,
                "createdAt": now().isoformat(),
                "updatedAt": now().isoformat(),
                "merchantLabel": "ClipCart demo",
                "fulfillmentTerms": "demo",
                "uiLabel": "demo",
            }
        )
        db.payment_signatures.insert_one(
            {"_id": f"Pay{tag}" + "2" * (88 - len(tag) - 3), "orderId": mint_oid, "claimedAt": now().isoformat()}
        )
        fake = FakeMint()
        fake.leaf_owner = buyer

        def one():
            return mint_receipt(st, owner, mint_oid, adapter=fake)

        with ThreadPoolExecutor(max_workers=8) as pool:
            futs = [pool.submit(one) for _ in range(8)]
            for f in as_completed(futs):
                f.result(timeout=60)
        attempts = list(db.receipt_mint_attempts.find({"orderId": mint_oid}))
        out["checks"]["concurrentSingleAttempt"] = len(attempts) == 1
        out["checks"]["concurrentSingleBuild"] = fake.build_calls == 1
        out["checks"]["concurrentConfirmed"] = (
            len(attempts) == 1 and attempts[0].get("status") == "confirmed" and attempts[0].get("assetId") == fake.asset_id
        )

        # 4) Restart reconciles — no second build
        builds_before = fake.build_calls
        order, receipt = mint_receipt(st, owner, mint_oid, adapter=fake)
        out["checks"]["retryReconcilesNoRebuild"] = (
            fake.build_calls == builds_before and receipt.get("assetId") == fake.asset_id
        )
        out["checks"]["paymentUnchanged"] = order.get("status") == "paid"
    finally:
        # Clean only this run's probe docs (never payment evidence / other owners).
        if probe_ids:
            db.demo_orders.delete_many({"_id": {"$in": probe_ids}, "ownerId": owner})
            db.receipt_mint_attempts.delete_many({"_id": {"$in": probe_ids}})
            db.payment_signatures.delete_many({"orderId": {"$in": probe_ids}})

    out["ok"] = all(out["checks"].values())
    print(json.dumps(out, indent=2))
    return 0 if out["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
