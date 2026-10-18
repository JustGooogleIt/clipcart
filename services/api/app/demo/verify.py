"""Independent Solana Pay transfer verification. Client signature/buyer are hints only."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from app.demo.rpc import SYSTEM_PROGRAM_ID, SolanaRpc

Outcome = Literal[
    "paid",
    "unconfirmed",
    "missing",
    "mismatch",
    "rpc_error",
]


@dataclass(frozen=True)
class VerifyResult:
    outcome: Outcome
    payment_signature: str | None = None
    buyer_wallet: str | None = None
    detail: str | None = None
    retryable: bool = False


def _account_keys(tx: dict) -> list[str]:
    message = (tx.get("transaction") or {}).get("message") or {}
    keys = message.get("accountKeys") or []
    out: list[str] = []
    for k in keys:
        if isinstance(k, str):
            out.append(k)
        elif isinstance(k, dict):
            out.append(k.get("pubkey") or "")
    return [k for k in out if k]


def _iter_instructions(tx: dict) -> list[dict]:
    message = (tx.get("transaction") or {}).get("message") or {}
    instr = list(message.get("instructions") or [])
    meta = tx.get("meta") or {}
    for inner in meta.get("innerInstructions") or []:
        instr.extend(inner.get("instructions") or [])
    return instr


def _native_transfers(tx: dict) -> list[tuple[str, str, int]]:
    """Return (source, destination, lamports) for SystemProgram transfer instructions."""
    found: list[tuple[str, str, int]] = []
    for ix in _iter_instructions(tx):
        program = ix.get("programId") or ix.get("program") or ""
        parsed = ix.get("parsed")
        if isinstance(parsed, dict):
            if parsed.get("type") != "transfer":
                continue
            info = parsed.get("info") or {}
            try:
                lamports = int(info["lamports"])
            except (KeyError, TypeError, ValueError):
                continue
            src, dst = info.get("source"), info.get("destination")
            if src and dst:
                found.append((src, dst, lamports))
            continue
        # Unparsed fallback: system transfer layout is rare without jsonParsed; skip.
        if program == SYSTEM_PROGRAM_ID:
            continue
    return found


def inspect_transaction(
    tx: dict,
    *,
    recipient: str,
    amount_lamports: int,
    payment_reference: str,
    buyer_hint: str | None,
) -> VerifyResult:
    meta = tx.get("meta") or {}
    if meta.get("err") is not None:
        return VerifyResult("mismatch", detail="transaction failed on chain", retryable=False)

    keys = _account_keys(tx)
    if payment_reference not in keys:
        return VerifyResult("mismatch", detail="payment reference account missing", retryable=False)

    transfers = _native_transfers(tx)
    matching = [(s, d, lam) for s, d, lam in transfers if d == recipient and lam == amount_lamports]
    if not matching:
        return VerifyResult(
            "mismatch",
            detail="no native SOL transfer matching recipient and amount",
            retryable=False,
        )

    source, _, _ = matching[0]
    if buyer_hint and buyer_hint != source:
        return VerifyResult(
            "mismatch",
            detail="buyer wallet does not match transfer source",
            retryable=False,
        )
    return VerifyResult("paid", buyer_wallet=source, detail="ok", retryable=False)


def _status_confirmed(status: dict | None) -> bool | None:
    """True if confirmed/finalized success; False if failed; None if not yet known."""
    if status is None:
        return None
    if status.get("err") is not None:
        return False
    conf = status.get("confirmationStatus")
    if conf in ("confirmed", "finalized"):
        return True
    if status.get("confirmations") is None and conf is None:
        return None
    if conf == "processed":
        return None
    return None


def find_candidate_signatures(
    rpc: SolanaRpc,
    *,
    payment_reference: str,
    signature_hint: str | None,
) -> list[str]:
    ordered: list[str] = []
    if signature_hint:
        ordered.append(signature_hint)
    try:
        for row in rpc.signatures_for_address(payment_reference, limit=20):
            sig = row.get("signature")
            if sig and sig not in ordered and row.get("err") is None:
                ordered.append(sig)
    except Exception:  # noqa: BLE001 — reference scan is best-effort after hint
        if not ordered:
            raise
    return ordered


def verify_payment(
    rpc: SolanaRpc,
    *,
    recipient: str,
    amount_lamports: int,
    payment_reference: str,
    signature_hint: str | None = None,
    buyer_hint: str | None = None,
) -> VerifyResult:
    try:
        rpc.require_devnet()
    except Exception as exc:  # noqa: BLE001
        from app.demo.rpc import RpcError

        retryable = exc.retryable if isinstance(exc, RpcError) else True
        return VerifyResult("rpc_error", detail=str(exc), retryable=retryable)

    try:
        candidates = find_candidate_signatures(
            rpc, payment_reference=payment_reference, signature_hint=signature_hint
        )
    except Exception as exc:  # noqa: BLE001
        return VerifyResult("rpc_error", detail=str(exc), retryable=True)

    if not candidates:
        return VerifyResult("missing", detail="no transaction found for payment reference", retryable=True)

    saw_unconfirmed = False
    last_mismatch: str | None = None

    for sig in candidates:
        try:
            statuses = rpc.get_signature_statuses([sig])
            status = statuses[0] if statuses else None
            confirmed = _status_confirmed(status)
            if confirmed is False:
                last_mismatch = "transaction failed"
                continue
            if confirmed is None and status is None:
                # May still be retrievable via getTransaction for history.
                pass
            elif confirmed is None:
                saw_unconfirmed = True
                continue

            tx = rpc.get_transaction(sig)
            if tx is None:
                saw_unconfirmed = True
                continue

            checked = inspect_transaction(
                tx,
                recipient=recipient,
                amount_lamports=amount_lamports,
                payment_reference=payment_reference,
                buyer_hint=buyer_hint,
            )
            if checked.outcome == "paid":
                return VerifyResult(
                    "paid",
                    payment_signature=sig,
                    buyer_wallet=checked.buyer_wallet,
                    detail=checked.detail,
                    retryable=False,
                )
            last_mismatch = checked.detail
            # Keep scanning other reference signatures; a bad client hint is not proof.
        except Exception as exc:  # noqa: BLE001
            return VerifyResult("rpc_error", detail=str(exc), retryable=True)

    if saw_unconfirmed:
        return VerifyResult("unconfirmed", detail="payment not yet confirmed", retryable=True)
    if last_mismatch:
        # A confirmed on-reference transaction existed but did not match terms.
        return VerifyResult("mismatch", detail=last_mismatch, retryable=False)
    return VerifyResult("missing", detail="no matching payment found", retryable=True)


def explorer_tx_url(signature: str) -> str:
    return f"https://explorer.solana.com/tx/{signature}?cluster=devnet"
