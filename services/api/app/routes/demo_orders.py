"""Solana demo-merchant checkout routes (FEATURE_SOLANA). Contract: docs/contracts/solana-demo-checkout.md."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request, Response
from fastapi.responses import FileResponse
from pydantic import Field

from app.demo.catalog import demo_catalog_item
from app.demo.orders import (
    create_order,
    get_owned_order,
    public_order,
    transfer_request,
    verify_order,
)
from app.demo.receipts import get_receipt_for_order
from app.sessions.service import ApiProblem, idempotent

from .api import In
from .deps import current_owner, ensure_owner, limiter, require_mutation_header, state_of

router = APIRouter()
_STATIC = Path(__file__).resolve().parents[1] / "demo" / "static"
_PAY_HTML = _STATIC / "phantom_pay.html"
_ALLOWED_STATIC = {
    "checkout.bundle.js": "application/javascript; charset=utf-8",
    "checkout.bundle.js.map": "application/json; charset=utf-8",
}


class CreateDemoOrderIn(In):
    catalog_item_id: str = Field(min_length=1, max_length=80)
    idempotency_key: str | None = Field(default=None, max_length=100)


class VerifyDemoOrderIn(In):
    payment_signature: str | None = Field(default=None, min_length=64, max_length=128)
    buyer_wallet: str | None = Field(default=None, min_length=32, max_length=64)


def _require_flag(request: Request):
    st = state_of(request)
    if not st.settings.feature_solana:
        raise ApiProblem(404, "feature_disabled", "Solana demo checkout is turned off")
    return st


@router.get("/demo/solana-pay")
def phantom_pay_page(request: Request):
    """Stable ClipCart-styled Solana demo checkout page. Orders are created in-page."""
    _require_flag(request)
    if not _PAY_HTML.is_file():
        raise ApiProblem(404, "not_found", "Pay page missing")
    return FileResponse(_PAY_HTML, media_type="text/html; charset=utf-8")


@router.get("/demo/solana-pay/{asset}")
def phantom_pay_asset(asset: str, request: Request):
    """Browser bundle for the checkout page (esbuild + real buffer package)."""
    _require_flag(request)
    media = _ALLOWED_STATIC.get(asset)
    if not media:
        raise ApiProblem(404, "not_found", "Asset not found")
    path = _STATIC / asset
    if not path.is_file():
        raise ApiProblem(404, "not_found", "Asset not found")
    return FileResponse(path, media_type=media)


@router.get("/api/demo-catalog")
def demo_catalog(request: Request, response: Response) -> dict:
    st = _require_flag(request)
    ensure_owner(request, response)
    amount = int(st.settings.solana_demo_amount_lamports)
    item = demo_catalog_item(amount)
    return {
        "network": "devnet",
        "featureEnabled": True,
        "items": [item.wire()],
        "warnings": [
            "Demo purchase on Solana devnet",
            "Uses test funds only",
            "Does not purchase or fulfill external retailer listings",
        ],
    }


@router.post("/api/demo-orders")
def post_demo_order(body: CreateDemoOrderIn, request: Request, response: Response) -> dict:
    st = _require_flag(request)
    require_mutation_header(request)
    owner = ensure_owner(request, response)
    limiter.check(owner, "demo_orders", 10)
    replay, commit = idempotent(
        st.db, owner, "demo_order_create", body.idempotency_key, {"catalogItemId": body.catalog_item_id}
    )
    if replay is not None:
        return replay
    doc = create_order(st, owner, body.catalog_item_id)
    st.bump("demo_orders")
    resp = {"order": public_order(doc), "transferRequest": transfer_request(doc)}
    commit(resp)
    return resp


@router.get("/api/demo-orders/{order_id}")
def get_demo_order(order_id: str, request: Request) -> dict:
    st = _require_flag(request)
    owner = current_owner(request)
    doc = get_owned_order(st.db, order_id, owner)
    out: dict = {"order": public_order(doc)}
    if doc["status"] in ("awaiting_payment", "created", "verifying"):
        out["transferRequest"] = transfer_request(doc)
    receipt = get_receipt_for_order(st, doc)
    if receipt is not None:
        out["receipt"] = receipt
    return out


@router.post("/api/demo-orders/{order_id}/verify", response_model=None)
def post_verify_demo_order(order_id: str, body: VerifyDemoOrderIn, request: Request):
    st = _require_flag(request)
    require_mutation_header(request)
    owner = current_owner(request)
    limiter.check(owner, "demo_order_verify", 30)
    doc, meta = verify_order(
        st,
        owner,
        order_id,
        payment_signature=body.payment_signature,
        buyer_wallet=body.buyer_wallet,
    )
    payload = {"order": public_order(doc)}
    if doc["status"] in ("awaiting_payment", "created", "verifying"):
        payload["transferRequest"] = transfer_request(doc)
    if meta.code is None:
        return payload
    # Include order snapshot with structured error so the UI can poll/retry.
    from fastapi.responses import JSONResponse
    import uuid

    return JSONResponse(
        status_code=meta.http_status,
        content={
            "code": meta.code,
            "message": meta.message,
            "retryable": meta.retryable,
            "requestId": "req_" + uuid.uuid4().hex[:12],
            "order": public_order(doc),
        },
    )
