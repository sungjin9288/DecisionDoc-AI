from __future__ import annotations

import json
from pathlib import Path

from scripts.assert_pilot_delivery_ready import assert_pilot_delivery_ready


def test_assert_pilot_delivery_ready_passes_for_ready_status(tmp_path):
    status_file = tmp_path / "latest-pilot-delivery-status.json"
    status_file.write_text(
        json.dumps(
            {
                "status": "PASS",
                "stale": False,
                "receipt_matches": True,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    result = assert_pilot_delivery_ready(status_file=status_file)

    assert result["ok"] is True
    assert result["errors"] == []


def test_assert_pilot_delivery_ready_fails_for_stale_or_mismatch(tmp_path):
    status_file = tmp_path / "latest-pilot-delivery-status.json"
    status_file.write_text(
        json.dumps(
            {
                "status": "FAIL",
                "stale": True,
                "receipt_matches": False,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    result = assert_pilot_delivery_ready(status_file=status_file)

    assert result["ok"] is False
    assert "status is FAIL" in result["errors"]
    assert "delivery artifacts are stale" in result["errors"]
    assert "receipt does not match current verification" in result["errors"]
