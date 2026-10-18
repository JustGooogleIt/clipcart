"""Demo merchant checkout records (SRS §12 DemoMerchantOrder). Receipt minting is optional."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field

from .base import Record

DemoNetwork = Literal["devnet"]
DemoOrderStatus = Literal["created", "awaiting_payment", "verifying", "paid", "expired", "failed"]
ReceiptStatus = Literal[
    "ineligible",
    "eligible",
    "minting",
    "confirmed",
    "failed",
    "needs_reconciliation",
]


class DemoCatalogItem(Record):
    """Server-defined participating merchant inventory. Never derived from SoleScout listings."""

    id: str = Field(min_length=1, max_length=80)
    merchant_id: str = Field(min_length=1, max_length=80)
    merchant_label: str = Field(min_length=1, max_length=120)
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=500)
    amount_atomic: str = Field(pattern=r"^[0-9]+$")
    amount_display: str = Field(min_length=1, max_length=40)
    asset_mint: str | None = None
    network: DemoNetwork = "devnet"
    fulfillment_terms: str = Field(min_length=1, max_length=500)
    eligible_for_checkout: bool = True


class DemoMerchantOrder(Record):
    id: str
    owner_id: str
    catalog_item_id: str
    merchant_id: str
    recipient_wallet: str
    buyer_wallet: str | None
    network: DemoNetwork
    asset_mint: str | None
    amount_atomic: str
    payment_reference: str
    expires_at: datetime
    status: DemoOrderStatus
    payment_signature: str | None
    receipt_status: ReceiptStatus
    receipt_asset_id: str | None
    receipt_mint_signature: str | None = None
    created_at: datetime
    updated_at: datetime
    merchant_label: str = Field(default="ClipCart demo merchant", max_length=120)
    fulfillment_terms: str = Field(default="", max_length=500)
    ui_label: str = Field(default="Demo purchase on Solana devnet", max_length=120)
    explorer_payment_url: str | None = None
    verification_error: str | None = None


class DemoTransferRequest(Record):
    """Solana Pay-style transfer the wallet must send. ``reference`` goes on the transfer as a read-only non-signer key."""

    recipient: str
    amount: str  # SOL, e.g. "0.01"
    spl_token: str | None = None
    reference: str
    label: str
    message: str
    memo: str | None = None


class DemoReceipt(Record):
    """The order's demo cNFT receipt (``receipt`` on GET /api/demo-orders/{id} and POST …/receipt/mint).

    Ownership is shown only when ``status`` is ``confirmed``. Devnet only; no retailer fulfillment.
    """

    status: ReceiptStatus
    asset_id: str | None = None
    mint_signature: str | None = None
    explorer_mint_url: str | None = None
    buyer_wallet: str | None = None
    merkle_tree: str | None = None
    indexing_status: Literal["unavailable", "pending", "ready"]
    metadata_uri: str | None = None
    label: str
