"""Solana JSON-RPC client via httpx. Used only against the configured network URL."""

from __future__ import annotations

from typing import Any

import httpx

# https://docs.anza.xyz/clusters/available — getGenesisHash for official Solana Devnet
DEVNET_GENESIS_HASH = "EtWTRABZaYq6iMfeYKouRu166VU2xqa1wcaWoxPkrZBG"
SYSTEM_PROGRAM_ID = "11111111111111111111111111111111"


class RpcError(Exception):
    def __init__(self, message: str, *, retryable: bool = True):
        super().__init__(message)
        self.retryable = retryable


class SolanaRpc:
    def __init__(
        self,
        url: str,
        client: httpx.Client | None = None,
        timeout_s: float = 20.0,
        *,
        trust_env: bool = False,
    ):
        """JSON-RPC client for Solana verification.

        ``trust_env`` defaults to False so this client alone ignores process
        ``HTTP(S)_PROXY`` settings. Agent/sandbox proxies often 403 Solana
        CONNECT tunnels; verification must hit ``url`` directly. Callers that
        inject a custom ``client`` keep that client's proxy policy unchanged.
        """
        self.url = url
        self._owned = client is None
        self.client = client or httpx.Client(timeout=timeout_s, trust_env=trust_env)

    def close(self) -> None:
        if self._owned:
            self.client.close()

    def call(self, method: str, params: list[Any] | None = None) -> Any:
        payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params or []}
        try:
            resp = self.client.post(self.url, json=payload)
            resp.raise_for_status()
            body = resp.json()
        except httpx.HTTPError as exc:
            raise RpcError(f"RPC transport error: {exc}", retryable=True) from exc
        if "error" in body:
            err = body["error"]
            raise RpcError(f"RPC {method}: {err.get('message', err)}", retryable=True)
        return body.get("result")

    def get_genesis_hash(self) -> str:
        return self.call("getGenesisHash")

    def require_devnet(self) -> None:
        genesis = self.get_genesis_hash()
        if genesis != DEVNET_GENESIS_HASH:
            raise RpcError(
                f"RPC is not Solana devnet (genesis {genesis[:12]}…)",
                retryable=False,
            )

    def get_signature_statuses(self, signatures: list[str]) -> list[dict | None]:
        result = self.call(
            "getSignatureStatuses",
            [signatures, {"searchTransactionHistory": True}],
        )
        return list((result or {}).get("value") or [])

    def get_transaction(self, signature: str) -> dict | None:
        return self.call(
            "getTransaction",
            [
                signature,
                {
                    "encoding": "jsonParsed",
                    "commitment": "confirmed",
                    "maxSupportedTransactionVersion": 0,
                },
            ],
        )

    def signatures_for_address(self, address: str, *, limit: int = 20) -> list[dict]:
        result = self.call(
            "getSignaturesForAddress",
            [address, {"limit": limit}],
        )
        return list(result or [])
