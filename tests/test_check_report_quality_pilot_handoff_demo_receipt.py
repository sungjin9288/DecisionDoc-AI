from __future__ import annotations

import copy
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

from scripts import check_report_quality_pilot_handoff_demo_receipt as checker
from scripts import run_report_quality_pilot_handoff_demo as demo


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "scripts/check_report_quality_pilot_handoff_demo_receipt.py"


@pytest.fixture(scope="module")
def valid_receipt() -> dict:
    return demo.run_demo()


def _write_receipt(path: Path, receipt: dict) -> bytes:
    content = (
        json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    path.write_bytes(content)
    return content


def _tamper(receipt: dict, case: str) -> None:
    if case == "extra_field":
        receipt["unexpected"] = True
    elif case == "human_review_claim":
        receipt["execution_mode"]["human_review_claimed"] = True
    elif case == "artifact_count":
        receipt["api_pilot_package"]["artifact_count"] = 2
    elif case == "artifact_order":
        receipt["handoff"]["ordered_artifact_ids"].reverse()
    elif case == "invalid_sha256":
        receipt["handoff"]["package_sha256"] = "not-a-sha256"
    elif case == "completed_stages":
        receipt["completed_stages"].pop()
    elif case == "training_authorized":
        receipt["handoff"]["training_authorized"] = True
    elif case == "external_action":
        receipt["external_actions"]["provider_api_execution"] = True
    elif case == "secret_value":
        receipt["api_pilot_package"]["ordered_artifact_ids"][0] = (
            "sk-secret-value-that-must-not-be-recorded"
        )
        receipt["handoff"]["ordered_artifact_ids"][0] = (
            "sk-secret-value-that-must-not-be-recorded"
        )
    elif case == "non_utc_timestamp":
        receipt["generated_at"] = "2026-07-15T09:00:00+09:00"
    else:
        raise AssertionError(f"unknown tamper case: {case}")


def test_pilot_handoff_demo_receipt_checker_accepts_generated_receipt(
    tmp_path: Path,
    valid_receipt: dict,
) -> None:
    receipt_path = tmp_path / "demo-receipt.json"
    content = _write_receipt(receipt_path, valid_receipt)

    result = checker.check_demo_receipt(receipt_path)

    assert result["ok"] is True
    assert result["receipt_sha256"] == hashlib.sha256(content).hexdigest()
    assert result["receipt_schema_version"] == demo.SCHEMA_VERSION
    assert result["summary"] == {
        "artifact_count": 3,
        "source_bound": True,
        "simulated_review": True,
        "human_review_claimed": False,
        "training_authorized": False,
        "completed_stage_count": 8,
    }
    assert result["side_effect_boundary"]["writes_local_files"] is False
    assert all(
        value is False
        for key, value in result["side_effect_boundary"].items()
        if key not in {"reads_local_receipt", "writes_local_files"}
    )


@pytest.mark.parametrize(
    ("case", "message"),
    [
        ("extra_field", "fields drifted"),
        ("human_review_claim", "execution_mode"),
        ("artifact_count", "three ready artifacts"),
        ("artifact_order", "artifact order"),
        ("invalid_sha256", "lowercase SHA-256"),
        ("completed_stages", "completed_stages"),
        ("training_authorized", "training_authorized=false"),
        ("external_action", "external_actions"),
        ("secret_value", "secret value"),
        ("non_utc_timestamp", "must use UTC"),
    ],
)
def test_pilot_handoff_demo_receipt_checker_rejects_tampering(
    tmp_path: Path,
    valid_receipt: dict,
    case: str,
    message: str,
) -> None:
    receipt = copy.deepcopy(valid_receipt)
    _tamper(receipt, case)
    receipt_path = tmp_path / f"{case}.json"
    _write_receipt(receipt_path, receipt)

    with pytest.raises(ValueError, match=message):
        checker.check_demo_receipt(receipt_path)


def test_pilot_handoff_demo_receipt_checker_cli_rejects_symlink(
    tmp_path: Path,
    valid_receipt: dict,
) -> None:
    receipt_path = tmp_path / "demo-receipt.json"
    _write_receipt(receipt_path, valid_receipt)

    completed = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), str(receipt_path), "--json"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    result = json.loads(completed.stdout)
    assert result["ok"] is True
    assert result["summary"]["human_review_claimed"] is False
    assert result["side_effect_boundary"]["writes_local_files"] is False

    receipt_link = tmp_path / "receipt-link.json"
    receipt_link.symlink_to(receipt_path)
    rejected = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), str(receipt_link), "--json"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert rejected.returncode == 1
    assert "symlink demo receipt files are not allowed" in rejected.stderr
