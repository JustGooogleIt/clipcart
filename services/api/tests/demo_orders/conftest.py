from __future__ import annotations

import sys
from pathlib import Path

import pytest

_API = Path(__file__).resolve().parents[2]
for p in (_API, _API / "tests" / "api", _API / "tests"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from api.conftest import H, app_factory, new_client  # noqa: E402,F401
from app.demo.base58util import b58encode  # noqa: E402
from app.demo.rpc import DEVNET_GENESIS_HASH  # noqa: E402

MERCHANT = b58encode(bytes([0x42] * 32))
BUYER = b58encode(bytes([0x07] * 32))
OTHER = b58encode(bytes([0x09] * 32))
SIG_OK = "5" + "1" * 87  # plausible length; not validated cryptographically in unit tests
SIG_OTHER = "5" + "2" * 87


class FakeRpc:
    """In-memory Solana RPC stand-in. Unit tests never touch a live chain."""

    def __init__(
        self,
        *,
        genesis: str = DEVNET_GENESIS_HASH,
        statuses: dict[str, dict | None] | None = None,
        transactions: dict[str, dict | None] | None = None,
        by_address: dict[str, list[dict]] | None = None,
    ):
        self.genesis = genesis
        self.statuses = statuses or {}
        self.transactions = transactions or {}
        self.by_address = by_address or {}
        self.closed = False

    def close(self) -> None:
        self.closed = True

    def get_genesis_hash(self) -> str:
        return self.genesis

    def require_devnet(self) -> None:
        from app.demo.rpc import RpcError

        if self.genesis != DEVNET_GENESIS_HASH:
            raise RpcError(f"RPC is not Solana devnet (genesis {self.genesis[:12]}…)", retryable=False)

    def get_signature_statuses(self, signatures: list[str]) -> list[dict | None]:
        return [self.statuses.get(s) for s in signatures]

    def get_transaction(self, signature: str) -> dict | None:
        return self.transactions.get(signature)

    def signatures_for_address(self, address: str, *, limit: int = 20) -> list[dict]:
        rows = self.by_address.get(address, [])
        return rows[:limit]


def transfer_tx(*, source: str, dest: str, lamports: int, reference: str, err=None) -> dict:
    keys = [
        {"pubkey": source, "signer": True, "writable": True},
        {"pubkey": dest, "signer": False, "writable": True},
        {"pubkey": reference, "signer": False, "writable": False},
        {"pubkey": "11111111111111111111111111111111", "signer": False, "writable": False},
    ]
    return {
        "meta": {"err": err},
        "transaction": {
            "message": {
                "accountKeys": keys,
                "instructions": [
                    {
                        "programId": "11111111111111111111111111111111",
                        "program": "system",
                        "parsed": {
                            "type": "transfer",
                            "info": {"source": source, "destination": dest, "lamports": lamports},
                        },
                    }
                ],
            }
        },
    }


@pytest.fixture
def solana_app(app_factory, monkeypatch):
    def make(*, flag: bool = True, merchant: str = MERCHANT, rpc: FakeRpc | None = None):
        if flag:
            monkeypatch.setenv("FEATURE_SOLANA", "1")
        else:
            monkeypatch.delenv("FEATURE_SOLANA", raising=False)
        monkeypatch.setenv("SOLANA_NETWORK", "devnet")
        monkeypatch.setenv("SOLANA_RPC_URL", "https://example.invalid")
        monkeypatch.setenv("SOLANA_DEMO_MERCHANT_WALLET", merchant)
        monkeypatch.setenv("SOLANA_DEMO_AMOUNT_LAMPORTS", "10000000")
        monkeypatch.setenv("SOLANA_DEMO_ORDER_TTL_S", "900")
        app = app_factory()
        client = new_client(app)
        return client, app.state.clipcart, rpc

    return make


def create_session(client):
    return client.post("/api/sessions", headers=H).json()["session"]


def create_demo_order(client, catalog_item_id="demo_item_clipcart_jacket_01"):
    return client.post(
        "/api/demo-orders",
        headers=H,
        json={"catalogItemId": catalog_item_id, "idempotencyKey": "k1"},
    )
