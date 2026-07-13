from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

import pytest

from app.services.procurement_decision_package_service import (
    CLI_CONTRACT_MANIFEST_FAILURE_FIELDS_BY_CASE,
    CLI_CONTRACT_MANIFEST_SUCCESS_FIELDS_BY_CASE,
    EXPLICIT_AUTHORIZATION_BOUNDARY,
    LOCAL_DEMO_SAMPLE_INPUT_PATH,
    REVIEW_RECEIPT_COMPLETED,
    REVIEW_RECEIPT_FIELD_ORDER,
    REVIEW_RECEIPT_PENDING,
    REVIEW_RECEIPT_SCHEMA_VERSION,
    REVIEW_DRAFT_FIELD_ORDER,
    REVIEW_DRAFT_REVIEW_FIELD_ORDER,
    REVIEW_DRAFT_SCHEMA_VERSION,
    REVIEW_DRAFT_SOURCE_FIELD_ORDER,
    apply_procurement_review_draft,
    build_and_write,
    build_pending_procurement_review_receipt,
    build_procurement_review_packet,
    record_procurement_review_decision,
    render_procurement_review_receipt_workspace,
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


def _receipt_content(receipt: dict[str, object]) -> bytes:
    return (json.dumps(receipt, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _review_draft(
    packet_content: bytes,
    receipt_content: bytes,
    **review_overrides: object,
) -> dict[str, object]:
    review = {
        "reviewer": REVIEWER,
        "decision": "accepted",
        "rationale": "Reviewed against the packet evidence and explicit boundary.",
        "reviewed_at": REVIEWED_AT,
        **review_overrides,
    }
    return {
        "schema_version": REVIEW_DRAFT_SCHEMA_VERSION,
        "source": {
            "packet_sha256": hashlib.sha256(packet_content).hexdigest(),
            "packet_size_bytes": len(packet_content),
            "receipt_sha256": hashlib.sha256(receipt_content).hexdigest(),
            "receipt_size_bytes": len(receipt_content),
        },
        "review": review,
        "authorization_boundary": EXPLICIT_AUTHORIZATION_BOUNDARY,
        "operational_approval": False,
    }


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


def test_browser_review_draft_is_source_bound_and_applies_once(tmp_path: Path) -> None:
    packet_content = _packet_content(tmp_path)
    pending = build_pending_procurement_review_receipt(packet_content)
    pending_content = _receipt_content(pending)
    draft = _review_draft(packet_content, pending_content)

    completed = apply_procurement_review_draft(
        pending,
        draft,
        packet_content,
        receipt_content=pending_content,
    )

    assert tuple(draft) == REVIEW_DRAFT_FIELD_ORDER
    assert tuple(draft["source"]) == REVIEW_DRAFT_SOURCE_FIELD_ORDER
    assert tuple(draft["review"]) == REVIEW_DRAFT_REVIEW_FIELD_ORDER
    assert completed["status"] == REVIEW_RECEIPT_COMPLETED
    assert completed["decision"] == "accepted"
    assert completed["operational_approval"] is False

    with pytest.raises(ValueError, match="already completed"):
        apply_procurement_review_draft(
            completed,
            draft,
            packet_content,
            receipt_content=_receipt_content(completed),
        )


def test_browser_review_draft_rejects_stale_or_elevated_input(tmp_path: Path) -> None:
    packet_content = _packet_content(tmp_path)
    pending = build_pending_procurement_review_receipt(packet_content)
    pending_content = _receipt_content(pending)

    mismatched_content = b"{}\n"
    mismatched_source = _review_draft(packet_content, mismatched_content)
    with pytest.raises(ValueError, match="content does not match the receipt"):
        apply_procurement_review_draft(
            pending,
            mismatched_source,
            packet_content,
            receipt_content=mismatched_content,
        )

    stale = _review_draft(packet_content, pending_content)
    stale["source"]["receipt_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="source.receipt_sha256 is stale"):
        apply_procurement_review_draft(
            pending,
            stale,
            packet_content,
            receipt_content=pending_content,
        )

    elevated = _review_draft(packet_content, pending_content)
    elevated["operational_approval"] = True
    with pytest.raises(ValueError, match="must not authorize operational action"):
        apply_procurement_review_draft(
            pending,
            elevated,
            packet_content,
            receipt_content=pending_content,
        )

    wrong_reviewer = _review_draft(
        packet_content,
        pending_content,
        reviewer="another-reviewer",
    )
    with pytest.raises(ValueError, match="reviewer does not match"):
        apply_procurement_review_draft(
            pending,
            wrong_reviewer,
            packet_content,
            receipt_content=pending_content,
        )


def test_review_receipt_workspace_renders_pending_and_completed_states(tmp_path: Path) -> None:
    packet_content = _packet_content(tmp_path)
    pending = build_pending_procurement_review_receipt(packet_content)
    pending_content = _receipt_content(pending)

    pending_html = render_procurement_review_receipt_workspace(
        pending,
        packet_content,
        receipt_content=pending_content,
        packet_path="procurement-review.zip",
        receipt_path="procurement_review_receipt.json",
    )

    assert 'data-review-receipt-workspace' in pending_html
    assert f'data-draft-schema-version="{REVIEW_DRAFT_SCHEMA_VERSION}"' in pending_html
    assert hashlib.sha256(packet_content).hexdigest() in pending_html
    assert hashlib.sha256(pending_content).hexdigest() in pending_html
    assert 'data-review-draft-form' in pending_html
    assert 'link.download = "procurement_review_draft.json"' in pending_html
    assert "operational_approval: false" in pending_html
    assert "fetch(" not in pending_html

    completed = record_procurement_review_decision(
        pending,
        packet_content,
        reviewer=REVIEWER,
        decision="changes_requested",
        rationale="Assign owners to unresolved evidence gaps.",
        reviewed_at=REVIEWED_AT,
    )
    completed_html = render_procurement_review_receipt_workspace(
        completed,
        packet_content,
        receipt_content=_receipt_content(completed),
    )
    assert "검토 완료" in completed_html
    assert "changes_requested" in completed_html
    assert "Assign owners to unresolved evidence gaps." in completed_html
    assert 'data-review-draft-form' not in completed_html


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


def test_receipt_cli_renders_and_applies_browser_draft(tmp_path: Path) -> None:
    packet_content = _packet_content(tmp_path)
    packet_path = tmp_path / "procurement-review.zip"
    packet_path.write_bytes(packet_content)
    receipt_path = tmp_path / "procurement-review-receipt.json"
    draft_path = tmp_path / "procurement-review-draft.json"
    workspace_path = tmp_path / "procurement-review-form.html"

    init_run, _ = _run_receipt_cli(
        "init",
        str(packet_path),
        "--receipt",
        str(receipt_path),
    )
    pending_content = receipt_path.read_bytes()
    draft_path.write_text(
        json.dumps(
            _review_draft(packet_content, pending_content),
            ensure_ascii=False,
            indent=2,
        ) + "\n",
        encoding="utf-8",
    )
    render_run, render_result = _run_receipt_cli(
        "render",
        str(packet_path),
        "--receipt",
        str(receipt_path),
        "--output",
        workspace_path.name,
    )
    apply_run, apply_result = _run_receipt_cli(
        "apply-draft",
        str(packet_path),
        "--receipt",
        str(receipt_path),
        "--draft",
        str(draft_path),
    )

    assert init_run.returncode == render_run.returncode == apply_run.returncode == 0
    expected_success_fields = CLI_CONTRACT_MANIFEST_SUCCESS_FIELDS_BY_CASE[
        "review_receipt_manager"
    ]
    assert tuple(render_result) == expected_success_fields
    assert tuple(apply_result) == expected_success_fields
    assert render_result["operation"] == "render"
    assert workspace_path.is_file()
    assert 'data-review-draft-form' in workspace_path.read_text(encoding="utf-8")
    assert apply_result["operation"] == "apply-draft"
    assert apply_result["review_status"] == REVIEW_RECEIPT_COMPLETED
    assert apply_result["decision"] == "accepted"
    assert apply_result["operational_approval"] is False

    completed_content = receipt_path.read_bytes()
    second_run, second_result = _run_receipt_cli(
        "apply-draft",
        str(packet_path),
        "--receipt",
        str(receipt_path),
        "--draft",
        str(draft_path),
    )
    assert second_run.returncode == 1
    assert tuple(second_result) == CLI_CONTRACT_MANIFEST_FAILURE_FIELDS_BY_CASE[
        "review_receipt_manager"
    ]
    assert second_result["status"] == "failed"
    assert receipt_path.read_bytes() == completed_content
