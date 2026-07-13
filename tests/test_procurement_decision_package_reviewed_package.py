from __future__ import annotations

import hashlib
import io
import json
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

from app.services.procurement_decision_package_service import (
    CLI_CONTRACT_MANIFEST_FAILURE_FIELDS_BY_CASE,
    CLI_CONTRACT_MANIFEST_SUCCESS_FIELDS_BY_CASE,
    EXCLUDED_ACTION_ORDER,
    LOCAL_DEMO_SAMPLE_INPUT_PATH,
    REVIEWED_PACKAGE_ENTRY_ORDER,
    REVIEWED_PACKAGE_MANIFEST_FIELD_ORDER,
    REVIEWED_PACKAGE_MANIFEST_NAME,
    REVIEWED_PACKAGE_SCHEMA_VERSION,
    REVIEWED_PACKAGE_SOURCE_FIELD_ORDER,
    REVIEWED_PACKAGE_STATUS,
    build_and_write,
    build_pending_procurement_review_receipt,
    build_procurement_review_packet,
    build_procurement_reviewed_package,
    record_procurement_review_decision,
    verify_procurement_reviewed_package,
)


ROOT = Path(__file__).resolve().parents[1]
SAMPLE_INPUT_PATH = ROOT / LOCAL_DEMO_SAMPLE_INPUT_PATH
SCRIPT = ROOT / "scripts" / "manage_procurement_reviewed_package.py"
REVIEWED_AT = "2026-07-13T15:30:00Z"


def _receipt_content(receipt: dict[str, object]) -> bytes:
    return (json.dumps(receipt, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _review_sources(
    tmp_path: Path,
    *,
    decision: str = "accepted",
) -> tuple[bytes, dict[str, object], bytes]:
    source_dir = tmp_path / "package"
    build_and_write(sample_input_path=SAMPLE_INPUT_PATH, output_dir=source_dir)
    packet_content, _ = build_procurement_review_packet(source_dir)
    pending = build_pending_procurement_review_receipt(packet_content)
    receipt = record_procurement_review_decision(
        pending,
        packet_content,
        reviewer=pending["reviewer"],
        decision=decision,
        rationale="Review outcome recorded against the exact packet evidence.",
        reviewed_at=REVIEWED_AT,
    )
    return packet_content, receipt, _receipt_content(receipt)


def _entries(content: bytes) -> dict[str, bytes]:
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        return {name: archive.read(name) for name in archive.namelist()}


def _rewrite(entries: dict[str, bytes]) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        for name, content in entries.items():
            archive.writestr(name, content)
    return output.getvalue()


def _run_cli(*args: str) -> tuple[subprocess.CompletedProcess[str], dict[str, object]]:
    run = subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        check=False,
        capture_output=True,
        text=True,
    )
    return run, json.loads(run.stdout)


@pytest.mark.parametrize("decision", ["accepted", "changes_requested", "rejected"])
def test_reviewed_package_is_deterministic_for_every_completed_decision(
    tmp_path: Path,
    decision: str,
) -> None:
    packet_content, receipt, receipt_content = _review_sources(
        tmp_path,
        decision=decision,
    )

    first, manifest = build_procurement_reviewed_package(
        packet_content,
        receipt,
        receipt_content=receipt_content,
    )
    second, _ = build_procurement_reviewed_package(
        packet_content,
        receipt,
        receipt_content=receipt_content,
    )
    result = verify_procurement_reviewed_package(first)

    assert first == second
    assert tuple(manifest) == REVIEWED_PACKAGE_MANIFEST_FIELD_ORDER
    assert tuple(manifest["source"]) == REVIEWED_PACKAGE_SOURCE_FIELD_ORDER
    assert manifest["schema_version"] == REVIEWED_PACKAGE_SCHEMA_VERSION
    assert manifest["status"] == REVIEWED_PACKAGE_STATUS
    assert manifest["decision"] == decision
    assert manifest["excluded_actions"] == EXCLUDED_ACTION_ORDER
    assert manifest["operational_approval"] is False
    assert result["package_verified"] is True
    assert result["entry_count"] == len(REVIEWED_PACKAGE_ENTRY_ORDER)


def test_reviewed_package_rejects_pending_or_mismatched_receipt(tmp_path: Path) -> None:
    packet_content, _, _ = _review_sources(tmp_path)
    pending = build_pending_procurement_review_receipt(packet_content)
    pending_content = _receipt_content(pending)

    with pytest.raises(ValueError, match="requires a completed"):
        build_procurement_reviewed_package(
            packet_content,
            pending,
            receipt_content=pending_content,
        )
    with pytest.raises(ValueError, match="content does not match"):
        build_procurement_reviewed_package(
            packet_content,
            pending,
            receipt_content=b"{}\n",
        )


def test_reviewed_package_rejects_entry_order_and_source_tamper(tmp_path: Path) -> None:
    packet_content, receipt, receipt_content = _review_sources(tmp_path)
    package_content, _ = build_procurement_reviewed_package(
        packet_content,
        receipt,
        receipt_content=receipt_content,
    )
    entries = _entries(package_content)

    reordered = {
        REVIEWED_PACKAGE_MANIFEST_NAME: entries[REVIEWED_PACKAGE_MANIFEST_NAME],
        **{
            name: content
            for name, content in entries.items()
            if name != REVIEWED_PACKAGE_MANIFEST_NAME
        },
    }
    with pytest.raises(ValueError, match="entries must match the expected order"):
        verify_procurement_reviewed_package(_rewrite(reordered))

    tampered = dict(entries)
    tampered["procurement_review_receipt.json"] += b"\n"
    with pytest.raises(ValueError, match="source.receipt_sha256 is invalid"):
        verify_procurement_reviewed_package(_rewrite(tampered))

    tampered = dict(entries)
    tampered["procurement_review_packet.zip"] += b"\n"
    with pytest.raises(ValueError, match="receipt packet_sha256 is inconsistent"):
        verify_procurement_reviewed_package(_rewrite(tampered))


def test_reviewed_package_rejects_manifest_authority_drift(tmp_path: Path) -> None:
    packet_content, receipt, receipt_content = _review_sources(tmp_path)
    package_content, _ = build_procurement_reviewed_package(
        packet_content,
        receipt,
        receipt_content=receipt_content,
    )
    entries = _entries(package_content)
    manifest = json.loads(entries[REVIEWED_PACKAGE_MANIFEST_NAME])
    manifest["operational_approval"] = True
    entries[REVIEWED_PACKAGE_MANIFEST_NAME] = (
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
    ).encode("utf-8")

    with pytest.raises(ValueError, match="must not grant operational approval"):
        verify_procurement_reviewed_package(_rewrite(entries))


def test_reviewed_package_cli_creates_verifies_and_preserves_history(tmp_path: Path) -> None:
    packet_content, receipt, receipt_content = _review_sources(tmp_path)
    packet_path = tmp_path / "review-packet.zip"
    receipt_path = tmp_path / "review-receipt.json"
    output_path = tmp_path / "reviewed-package.zip"
    packet_path.write_bytes(packet_content)
    receipt_path.write_bytes(receipt_content)

    create_run, create_result = _run_cli(
        "create",
        str(packet_path),
        "--receipt",
        str(receipt_path),
        "--output",
        str(output_path),
    )
    verify_run, verify_result = _run_cli("verify", str(output_path))

    assert create_run.returncode == verify_run.returncode == 0
    assert create_run.stderr == verify_run.stderr == ""
    expected_success = CLI_CONTRACT_MANIFEST_SUCCESS_FIELDS_BY_CASE[
        "reviewed_package_manager"
    ]
    assert tuple(create_result) == expected_success
    assert tuple(verify_result) == expected_success
    assert create_result["operation"] == "create"
    assert verify_result["operation"] == "verify"
    assert create_result["package_sha256"] == hashlib.sha256(
        output_path.read_bytes()
    ).hexdigest()
    assert verify_result["package_verified"] is True
    assert verify_result["operational_approval"] is False

    original_content = output_path.read_bytes()
    second_run, second_result = _run_cli(
        "create",
        str(packet_path),
        "--receipt",
        str(receipt_path),
        "--output",
        str(output_path),
    )
    assert second_run.returncode == 1
    assert tuple(second_result) == CLI_CONTRACT_MANIFEST_FAILURE_FIELDS_BY_CASE[
        "reviewed_package_manager"
    ]
    assert "refusing to overwrite" in second_result["error"]
    assert output_path.read_bytes() == original_content
