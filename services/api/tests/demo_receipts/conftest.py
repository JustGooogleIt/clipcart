from __future__ import annotations

import sys
from pathlib import Path

import pytest

_API = Path(__file__).resolve().parents[2]
for p in (_API, _API / "tests" / "api", _API / "tests", _API / "tests" / "demo_orders"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from api.conftest import H, app_factory, new_client  # noqa: E402,F401
from demo_orders.conftest import BUYER, MERCHANT, SIG_OK, create_session  # noqa: E402,F401


class FakeMintAdapter:
    """In-memory Bubblegum stand-in. Unit tests never hit a live chain."""

    def __init__(self):
        self.build_calls = 0
        self.send_calls = 0
        self.signed_b64 = "c2lnbmVkLXR4LWJ5dGVz"
        self.signature = "MintSig" + "1" * 80
        self.asset_id = "Asset" + "1" * 40
        self.leaf_owner = BUYER
        self.finalize = True
        self.das_ready = True
        self.fail_send = False
        self.fail_build = False

    def require_devnet(self) -> str:
        from app.demo.rpc import DEVNET_GENESIS_HASH

        return DEVNET_GENESIS_HASH

    def build_sign_mint(self, *, tree: str, leaf_owner: str, name: str, uri: str) -> dict:
        self.build_calls += 1
        if self.fail_build:
            raise RuntimeError("build failed")
        return {
            "signedTxBase64": self.signed_b64,
            "signature": self.signature,
            "leafOwner": leaf_owner,
            "merkleTree": tree,
        }

    def send_signed(self, signed_tx_base64: str) -> str:
        self.send_calls += 1
        if self.fail_send:
            raise RuntimeError("broadcast uncertain")
        assert signed_tx_base64 == self.signed_b64
        return self.signature

    def confirm(self, signature: str) -> dict:
        return {
            "signature": signature,
            "confirmationStatus": "finalized" if self.finalize else "confirmed",
            "err": None,
            "finalized": self.finalize,
        }

    def parse_leaf(self, signature: str) -> dict:
        return {"assetId": self.asset_id, "owner": self.leaf_owner, "nonce": 0}

    def get_asset(self, asset_id: str) -> dict:
        if not self.das_ready:
            raise RuntimeError("DAS not ready")
        return {"assetId": asset_id, "owner": self.leaf_owner, "content": {"name": "ClipCart demo receipt"}}


@pytest.fixture
def cnft_app(app_factory, monkeypatch):
    def make(*, receipts: bool = True, solana: bool = True, adapter: FakeMintAdapter | None = None):
        if solana:
            monkeypatch.setenv("FEATURE_SOLANA", "1")
        else:
            monkeypatch.delenv("FEATURE_SOLANA", raising=False)
        if receipts:
            monkeypatch.setenv("FEATURE_SOLANA_CNFT_RECEIPTS", "1")
        else:
            monkeypatch.delenv("FEATURE_SOLANA_CNFT_RECEIPTS", raising=False)
        monkeypatch.setenv("SOLANA_NETWORK", "devnet")
        monkeypatch.setenv("SOLANA_RPC_URL", "https://example.invalid")
        monkeypatch.setenv("SOLANA_DEMO_MERCHANT_WALLET", MERCHANT)
        monkeypatch.setenv("SOLANA_DEMO_AMOUNT_LAMPORTS", "10000000")
        monkeypatch.setenv("SOLANA_CNFT_TREE_ADDRESS", "Tree" + "1" * 40)
        monkeypatch.setenv("SOLANA_CNFT_RECEIPT_AUTHORITY", "Auth" + "1" * 40)
        monkeypatch.setenv("SOLANA_CNFT_AUTHORITY_KEYPAIR_PATH", "/tmp/fake-cnft-authority.json")
        monkeypatch.setenv("SOLANA_DAS_RPC_URL", "https://das.example.invalid")
        monkeypatch.setenv("SOLANA_CNFT_METADATA_BASE_URL", "https://example.com/meta")
        # Offline tests use mongomock; durable-store gate is patched for unit coverage.
        monkeypatch.setattr("app.demo.receipts.require_durable_store", lambda settings: None)
        app = app_factory()
        client = new_client(app)
        fake = adapter or FakeMintAdapter()
        return client, app.state.clipcart, fake

    return make


def paid_demo_order(client, st, *, buyer: str = BUYER, sig: str = SIG_OK):
    from demo_orders.conftest import create_demo_order

    create_session(client)
    order = create_demo_order(client).json()["order"]
    st.db.demo_orders.update_one(
        {"_id": order["id"]},
        {
            "$set": {
                "status": "paid",
                "buyerWallet": buyer,
                "paymentSignature": sig,
                "receiptStatus": "eligible",
            }
        },
    )
    st.db.payment_signatures.insert_one({"_id": sig, "orderId": order["id"]})
    return st.db.demo_orders.find_one({"_id": order["id"]})
