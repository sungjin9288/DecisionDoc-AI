from __future__ import annotations

import json
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

import pytest

from app.services.procurement_decision_package_service import (
    EXPLICIT_AUTHORIZATION_BOUNDARY,
    LOCAL_DEMO_SAMPLE_INPUT_PATH,
    REVIEW_RECEIPT_COMPLETED,
    REVIEW_RECEIPT_FIELD_ORDER,
    REVIEW_RECEIPT_PENDING,
    REVIEW_RECEIPT_SCHEMA_VERSION,
    build_and_write,
    build_pending_procurement_review_receipt,
    build_procurement_review_packet,
    record_procurement_review_decision,
    validate_procurement_review_receipt,
)


ROOT = Path(__file__).resolve().parents[1]
SAMPLE_INPUT_PATH = ROOT / LOCAL_DEMO_SAMPLE_INPUT_PATH
RECEIPT_SCRIPT = ROOT / "scripts" / "manage_procurement_review_receipt.py"
REVIEWER = "executive-reviewer"
REVIEWED_AT = "2026-07-13T14:30:00Z"


def _packet_content(tmp_path: Path, *, opportunity_id: str | None = None) -> bytes:
    sample_input_path = SAMPLE_INPUT_PATH
    if opportunity_id is not None:
        sample_input = json.loads(SAMPLE_INPUT_PATH.read_text(encoding="utf-8"))
        sample_input["opportunity"]["opportunity_id"] = opportunity_id
        sample_input_path = tmp_path / f"{opportunity_id}.json"
        sample_input_path.write_text(
            json.dumps(sample_input, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    source_dir = tmp_path / (opportunity_id or "package")
    build_and_write(sample_input_path=sample_input_path, output_dir=source_dir)
    packet_content, _ = build_procurement_review_packet(source_dir)
    return packet_content


def _run_receipt_cli(*args: str) -> tuple[subprocess.CompletedProcess[str], dict[str, object]]:
    run = subprocess.run(
        [sys.executable, str(RECEIPT_SCRIPT), *args],
        check=False,
        capture_output=True,
        text=True,
    )
    return run, json.loads(run.stdout)


def test_pending_receipt_is_deterministic_and_packet_bound(tmp_path: Path) -> None:
    packet_content = _packet_content(tmp_path)

    first = build_pending_procurement_review_receipt(packet_content)
    second = build_pending_procurement_review_receipt(packet_content)
    validation = validate_procurement_review_receipt(first, packet_content)

    assert first == second
    assert tuple(first) == REVIEW_RECEIPT_FIELD_ORDER
    assert first["schema_version"] == REVIEW_RECEIPT_SCHEMA_VERSION
    assert first["status"] == REVIEW_RECEIPT_PENDING
    assert first["reviewer"] == REVIEWER
    assert first["decision"] is first["rationale"] is first["reviewed_at"] is None
    assert first["operational_approval"] is False
    assert validation["receipt_valid"] is True
    assert validation["authorization_boundary"] == EXPLICIT_AUTHORIZATION_BOUNDARY


def test_recorded_receipt_is_completed_without_operational_approval(tmp_path: Path) -> None:
    packet_content = _packet_content(tmp_path)
    pending = build_pending_procurement_review_receipt(packet_content)

    completed = record_procurement_review_decision(
        pending,
        packet_content,
        reviewer=REVIEWER,
        decision="accepted",
        rationale="Proceed with package review handoff after gap owners are assigned.",
        reviewed_at="2026-07-13T14:30:00+00:00",
    )
    validation = validate_procurement_review_receipt(completed, packet_content)

    assert completed["status"] == REVIEW_RECEIPT_COMPLETED
    assert completed["decision"] == "accepted"
    assert completed["reviewed_at"] == REVIEWED_AT
    assert completed["operational_approval"] is False
    assert validation["review_status"] == REVIEW_RECEIPT_COMPLETED
    assert validation["receipt_valid"] is True


@pytest.mark.parametrize(
    ("overrides", "error"),
    [
        ({"reviewer": "another-reviewer"}, "reviewer does not match"),
        ({"decision": "approved"}, "decision is invalid"),
        ({"rationale": "   "}, "rationale must be non-empty"),
        ({"reviewed_at": "2026-07-13T23:30:00+09:00"}, "must use UTC"),
    ],
)
def test_record_rejects_invalid_review_input(
    tmp_path: Path,
    overrides: dict[str, str],
    error: str,
) -> None:
    packet_content = _packet_content(tmp_path)
    pending = build_pending_procurement_review_receipt(packet_content)
    review = {
        "reviewer": REVIEWER,
        "decision": "accepted",
        "rationale": "Reviewed against the package evidence.",
        "reviewed_at": REVIEWED_AT,
        **overrides,
    }

    with pytest.raises(ValueError, match=error):
        record_procurement_review_decision(pending, packet_content, **review)


def test_receipt_rejects_stale_packet_authority_drift_and_re_record(
    tmp_path: Path,
) -> None:
    packet_content = _packet_content(tmp_path)
    another_packet = _packet_content(
        tmp_path,
        opportunity_id="local-procurement-demo-002",
    )
    pending = build_pending_procurement_review_receipt(packet_content)

    with pytest.raises(ValueError, match="packet_sha256 is inconsistent"):
        validate_procurement_review_receipt(pending, another_packet)

    elevated = deepcopy(pending)
    elevated["operational_approval"] = 0
    with pytest.raises(ValueError, match="operational_approval is inconsistent"):
        validate_procurement_review_receipt(elevated, packet_content)

    reordered = {"status": pending["status"]}
    reordered.update({key: value for key, value in pending.items() if key != "status"})
    with pytest.raises(ValueError, match="fields are invalid"):
        validate_procurement_review_receipt(reordered, packet_content)

    completed = record_procurement_review_decision(
        pending,
        packet_content,
        reviewer=REVIEWER,
        decision="changes_requested",
        rationale="Assign owners to all unresolved evidence gaps.",
        reviewed_at=REVIEWED_AT,
    )
    with pytest.raises(ValueError, match="already completed"):
        record_procurement_review_decision(
            completed,
            packet_content,
            reviewer=REVIEWER,
            decision="accepted",
            rationale="Attempted second decision.",
            reviewed_at=REVIEWED_AT,
        )


def test_receipt_cli_runs_init_record_validate_and_json_failure(tmp_path: Path) -> None:
    packet_content = _packet_content(tmp_path)
    packet_path = tmp_path / "procurement-review.zip"
    packet_path.write_bytes(packet_content)
    receipt_path = tmp_path / "procurement-review-receipt.json"

    init_run, init_result = _run_receipt_cli(
        "init",
        str(packet_path),
        "--receipt",
        str(receipt_path),
    )
    pending_content = receipt_path.read_bytes()
    invalid_run, invalid_result = _run_receipt_cli(
        "record",
        str(packet_path),
        "--receipt",
        str(receipt_path),
        "--reviewer",
        "another-reviewer",
        "--decision",
        "accepted",
        "--rationale",
        "This invalid review must not change the receipt.",
        "--reviewed-at",
        REVIEWED_AT,
    )
    assert invalid_run.returncode == 1
    assert invalid_run.stderr == ""
    assert invalid_result["status"] == "failed"
    assert receipt_path.read_bytes() == pending_content

    record_run, record_result = _run_receipt_cli(
        "record",
        str(packet_path),
        "--receipt",
        str(receipt_path),
        "--reviewer",
        REVIEWER,
        "--decision",
        "accepted",
        "--rationale",
        "Reviewed against the packet evidence and explicit boundary.",
        "--reviewed-at",
        REVIEWED_AT,
    )
    validate_run, validate_result = _run_receipt_cli(
        "validate",
        str(packet_path),
        "--receipt",
        str(receipt_path),
    )

    assert init_run.returncode == record_run.returncode == validate_run.returncode == 0
    assert init_run.stderr == record_run.stderr == validate_run.stderr == ""
    assert init_result["review_status"] == REVIEW_RECEIPT_PENDING
    assert record_result["review_status"] == REVIEW_RECEIPT_COMPLETED
    assert validate_result["decision"] == "accepted"
    assert validate_result["receipt_valid"] is True
    assert validate_result["operational_approval"] is False

    failure_run, failure_result = _run_receipt_cli(
        "init",
        str(packet_path),
        "--receipt",
        str(receipt_path),
    )
    assert failure_run.returncode == 1
    assert failure_run.stderr == ""
    assert failure_result["status"] == "failed"
    assert failure_result["error_type"] == "ValueError"
    assert "Traceback" not in failure_run.stdout
