"""Subprocess bridge to the pinned Bubblegum V2 Node worker. Never logs secrets."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from app.config import API_ROOT


class CnftWorkerError(Exception):
    def __init__(self, message: str, *, retryable: bool = True):
        super().__init__(message)
        self.retryable = retryable


def default_worker_dir() -> Path:
    return API_ROOT / "cnft_worker"


def run_worker(
    command: str,
    *,
    worker_dir: Path,
    args: list[str] | None = None,
    timeout_s: float = 120.0,
) -> dict[str, Any]:
    cli = worker_dir / "src" / "cli.mjs"
    if not cli.is_file():
        raise CnftWorkerError(f"cnft worker missing at {cli}", retryable=False)
    cmd = ["node", str(cli), command, *(args or [])]
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(worker_dir),
            capture_output=True,
            text=True,
            timeout=timeout_s,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise CnftWorkerError(f"cnft worker timed out on {command}", retryable=True) from exc
    # stdout is JSON only; stderr may contain SDK noise — never treat as secret log dump.
    line = (proc.stdout or "").strip().splitlines()[-1] if (proc.stdout or "").strip() else ""
    if not line:
        raise CnftWorkerError(
            f"cnft worker returned no JSON for {command} (exit {proc.returncode})",
            retryable=True,
        )
    try:
        body = json.loads(line)
    except json.JSONDecodeError as exc:
        raise CnftWorkerError(f"cnft worker invalid JSON for {command}", retryable=True) from exc
    if not body.get("ok"):
        raise CnftWorkerError(str(body.get("error") or f"{command} failed"), retryable=True)
    return body
