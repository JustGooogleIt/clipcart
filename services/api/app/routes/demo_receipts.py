"""cNFT receipt mint routes (FEATURE_SOLANA_CNFT_RECEIPTS). Contract: docs/contracts/solana-cnft-receipts.md."""

from __future__ import annotations

from fastapi import APIRouter, Request

from app.demo.orders import get_owned_order, public_order, transfer_request
from app.demo.receipts import get_receipt_for_order, mint_receipt
from app.sessions.service import ApiProblem

from .deps import current_owner, limiter, require_mutation_header, state_of

router = APIRouter()


def _require_solana(request: Request):
    st = state_of(request)
    if not st.settings.feature_solana:
        raise ApiProblem(404, "feature_disabled", "Solana demo checkout is turned off")
    return st


@router.post("/api/demo-orders/{order_id}/receipt/mint", response_model=None)
def post_mint_receipt(order_id: str, request: Request):
    st = _require_solana(request)
    if not st.settings.feature_solana_cnft_receipts:
        raise ApiProblem(404, "feature_disabled", "Solana cNFT receipts are turned off")
    require_mutation_header(request)
    owner = current_owner(request)
    limiter.check(owner, "demo_receipt_mint", 10)
    # Ensure ownership before mint (mint_receipt also checks).
    get_owned_order(st.db, order_id, owner)
    doc, receipt = mint_receipt(st, owner, order_id)
    out: dict = {"order": public_order(doc), "receipt": receipt}
    if doc["status"] in ("awaiting_payment", "created", "verifying"):
        out["transferRequest"] = transfer_request(doc)
    return out
