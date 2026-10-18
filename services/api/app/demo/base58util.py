"""Minimal base58 encode/decode for Solana pubkeys and signatures. No signing keys."""

from __future__ import annotations

_ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def b58encode(raw: bytes) -> str:
    n = int.from_bytes(raw, "big")
    out: list[str] = []
    while n > 0:
        n, rem = divmod(n, 58)
        out.append(_ALPHABET[rem])
    pad = 0
    for b in raw:
        if b == 0:
            pad += 1
        else:
            break
    return ("1" * pad) + ("".join(reversed(out)) if out else "")


def b58decode(text: str) -> bytes:
    if not text or any(c not in _ALPHABET for c in text):
        raise ValueError("invalid base58")
    n = 0
    for c in text:
        n = n * 58 + _ALPHABET.index(c)
    raw = n.to_bytes((n.bit_length() + 7) // 8 or 1, "big")
    pad = 0
    for c in text:
        if c == "1":
            pad += 1
        else:
            break
    return b"\x00" * pad + (raw if n else b"")


def is_pubkey(text: str) -> bool:
    try:
        return len(b58decode(text)) == 32
    except ValueError:
        return False
