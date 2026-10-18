"""features.solanaCnftReceipts: true only when both Solana flags are on, so the UI can hide mint controls up front."""

import pytest
from api.conftest import new_client


@pytest.mark.parametrize(("solana", "receipts", "expected"), [("0", "0", False), ("1", "0", False), ("0", "1", False), ("1", "1", True)])
def test_receipts_flag_in_health(app_factory, monkeypatch, solana, receipts, expected):
    monkeypatch.setenv("FEATURE_SOLANA", solana)
    monkeypatch.setenv("FEATURE_SOLANA_CNFT_RECEIPTS", receipts)
    f = new_client(app_factory()).get("/api/health").json()["features"]
    assert f["solana"] is (solana == "1") and f["solanaCnftReceipts"] is expected
