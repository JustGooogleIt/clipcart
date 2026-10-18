#!/usr/bin/env python3
"""One-shot: seed the preserved paid demo order and mint a cNFT receipt (devnet).

Requires durable MongoDB, FEATURE flags, tree + authority + metadata URL in env.
Never prints key material.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import timedelta
from pathlib import Path

API_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(API_ROOT))

from app.demo.catalog import DEMO_CATALOG_ITEM_ID, FULFILLMENT_TERMS, MERCHANT_ID, MERCHANT_LABEL
from app.demo.receipts import mint_receipt
from app.demo.verify import explorer_tx_url
from app.main import create_app
from app.sessions.service import now

PRESERVED = {
    "order_id": "dmo_V-lqM-ub8XR8bsg5",
    "buyer": "8W3Rgm2MFFkA3SP1TcUuvVaHMAPhJshZ4rdgJw2QSwjo",
    "merchant": "3yVVaxvuDpXBJWFGetwdCAC3bRXoo4d7bjXeX5Xn8y73",
    "payment_signature": "3KjLMeXJUjidmxgbsvqWZQVCfHeBAupHnTk8rdc2EkNjr12A7iCCRXsgkbYqyjLVsioAPmsoDGPtA2Psz51HkbJh",
    "reference": "HDKkghtD6ZYWBPEPPwFQrY1BL9TfVLM3H4J1ffFy8WyL",
    "owner_id": "own_cnft_receipt_smoke_01",
}


def main() -> int:
    os.environ["FEATURE_SOLANA"] = "true"
    os.environ["FEATURE_SOLANA_CNFT_RECEIPTS"] = "true"
    app = create_app()
    st = app.state.clipcart
    if st.settings.db_mode == "local_memory":
        print(json.dumps({"ok": False, "error": "MONGODB_URI required for live mint"}))
        return 2
    t = now()
    oid = PRESERVED["order_id"]
    doc = {
        "_id": oid,
        "id": oid,
        "ownerId": PRESERVED["owner_id"],
        "catalogItemId": DEMO_CATALOG_ITEM_ID,
        "merchantId": MERCHANT_ID,
        "recipientWallet": PRESERVED["merchant"],
        "buyerWallet": PRESERVED["buyer"],
        "network": "devnet",
        "assetMint": None,
        "amountAtomic": "10000000",
        "paymentReference": PRESERVED["reference"],
        "expiresAt": (t + timedelta(days=30)).isoformat(),
        "status": "paid",
        "paymentSignature": PRESERVED["payment_signature"],
        "receiptStatus": "eligible",
        "receiptAssetId": None,
        "receiptMintSignature": None,
        "createdAt": (t - timedelta(hours=1)).isoformat(),
        "updatedAt": t.isoformat(),
        "merchantLabel": MERCHANT_LABEL,
        "fulfillmentTerms": FULFILLMENT_TERMS,
        "uiLabel": "Demo purchase on Solana devnet",
        "explorerPaymentUrl": explorer_tx_url(PRESERVED["payment_signature"]),
        "verificationError": None,
    }
    st.db.demo_orders.delete_one({"_id": oid})
    st.db.receipt_mint_attempts.delete_one({"_id": oid})
    st.db.payment_signatures.delete_one({"_id": PRESERVED["payment_signature"]})
    st.db.demo_orders.insert_one(doc)
    st.db.payment_signatures.insert_one(
        {"_id": PRESERVED["payment_signature"], "orderId": oid, "claimedAt": t.isoformat()}
    )
    order, receipt = mint_receipt(st, PRESERVED["owner_id"], oid)
    print(
        json.dumps(
            {
                "ok": True,
                "orderId": order["id"],
                "orderStatus": order["status"],
                "receiptStatus": order.get("receiptStatus"),
                "receipt": receipt,
                "paymentExplorer": explorer_tx_url(PRESERVED["payment_signature"]),
            },
            indent=2,
        )
    )
    return 0 if order.get("receiptStatus") in ("confirmed", "minting", "needs_reconciliation") else 1


if __name__ == "__main__":
    raise SystemExit(main())
