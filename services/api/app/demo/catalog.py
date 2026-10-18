"""One controlled ClipCart demo merchant catalog item. Server-priced; not a retailer SKU."""

from __future__ import annotations

from app.contracts.demo_orders import DemoCatalogItem

DEMO_CATALOG_ITEM_ID = "demo_item_clipcart_jacket_01"
DEFAULT_AMOUNT_LAMPORTS = 10_000_000  # 0.01 native SOL
MERCHANT_ID = "clipcart_demo"
MERCHANT_LABEL = "ClipCart demo merchant"
FULFILLMENT_TERMS = (
    "Demo only. No shipment or retailer fulfillment. Test SOL on Solana devnet. "
    "This is not a SoleScout or third-party retailer purchase."
)


def amount_atomic(lamports: int) -> str:
    return str(lamports)


def demo_catalog_item(lamports: int = DEFAULT_AMOUNT_LAMPORTS) -> DemoCatalogItem:
    return DemoCatalogItem(
        id=DEMO_CATALOG_ITEM_ID,
        merchant_id=MERCHANT_ID,
        merchant_label=MERCHANT_LABEL,
        title="ClipCart Demo Jacket (devnet)",
        description=(
            "Participating ClipCart demo merchant item for a wallet-approved "
            "Solana Pay transfer on devnet. Not a SoleScout listing."
        ),
        amount_atomic=amount_atomic(lamports),
        amount_display="0.01 SOL",
        asset_mint=None,
        network="devnet",
        fulfillment_terms=FULFILLMENT_TERMS,
        eligible_for_checkout=True,
    )


def get_catalog_item(catalog_item_id: str, lamports: int = DEFAULT_AMOUNT_LAMPORTS) -> DemoCatalogItem | None:
    item = demo_catalog_item(lamports)
    if catalog_item_id != item.id or not item.eligible_for_checkout:
        return None
    return item
