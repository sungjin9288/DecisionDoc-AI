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
    DECISION_PACKAGE_NAME,
    EXPLICIT_AUTHORIZATION_BOUNDARY,
    INCLUDED_ARTIFACT_ORDER,
    LOCAL_DEMO_SAMPLE_INPUT_PATH,
    PACKET_MANIFEST_NAME,
    PACKET_SCHEMA_VERSION,
    PACKET_STATUS,
    PROCUREMENT_REVIEW_NAME,
    build_and_write,
    build_procurement_review_packet,
    verify_procurement_review_packet,
)


ROOT = Path(__file__).resolve().parents[1]
SAMPLE_INPUT_PATH = ROOT / LOCAL_DEMO_SAMPLE_INPUT_PATH
PACKET_SCRIPT = ROOT / "scripts" / "manage_procurement_decision_review_packet.py"


def _source_package(tmp_path: Path) -> Path:
    source_dir = tmp_path / "package"
    build_and_write(sample_input_path=SAMPLE_INPUT_PATH, output_dir=source_dir)
    return source_dir


def _packet_entries(packet: bytes) -> dict[str, bytes]:
    with zipfile.ZipFile(io.BytesIO(packet)) as archive:
        return {name: archive.read(name) for name in archive.namelist()}


def _rewrite_packet(entries: dict[str, bytes]) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        for name, content in entries.items():
            archive.writestr(name, content)
    return output.getvalue()


def _run_packet_cli(*args: str) -> tuple[subprocess.CompletedProcess[str], dict[str, object]]:
    run = subprocess.run(
        [sys.executable, str(PACKET_SCRIPT), *args],
        check=False,
        capture_output=True,
        text=True,
    )
    return run, json.loads(run.stdout)


def test_packet_is_deterministic_and_self_verifying(tmp_path: Path) -> None:
    source_dir = _source_package(tmp_path)

    first_packet, first_manifest = build_procurement_review_packet(source_dir)
    second_packet, second_manifest = build_procurement_review_packet(source_dir)
    verification = verify_procurement_review_packet(first_packet)

    assert first_packet == second_packet
    assert first_manifest == second_manifest
    assert first_manifest["status"] == PACKET_STATUS
    assert first_manifest["operational_approval"] is False
    assert [record["path"] for record in first_manifest["artifacts"]] == INCLUDED_ARTIFACT_ORDER
    assert verification == {
        "schema_version": PACKET_SCHEMA_VERSION,
        "package_id": "local-procurement-demo-001-package",
        "recommendation": "CONDITIONAL_GO",
        "artifact_count": len(INCLUDED_ARTIFACT_ORDER),
        "entry_count": len(INCLUDED_ARTIFACT_ORDER) + 1,
        "authorization_boundary": EXPLICIT_AUTHORIZATION_BOUNDARY,
        "operational_approval": False,
        "packet_verified": True,
    }
    with zipfile.ZipFile(io.BytesIO(first_packet)) as archive:
        assert archive.namelist() == [*INCLUDED_ARTIFACT_ORDER, PACKET_MANIFEST_NAME]


def test_packet_builder_rejects_source_symlink(tmp_path: Path) -> None:
    source_dir = _source_package(tmp_path)
    summary_path = source_dir / "decision_summary.md"
    outside_path = tmp_path / "outside.md"
    outside_path.write_bytes(summary_path.read_bytes())
    summary_path.unlink()
    summary_path.symlink_to(outside_path)

    with pytest.raises(ValueError, match="regular file inside the source directory"):
        build_procurement_review_packet(source_dir)


def test_packet_verifier_rejects_tampering_and_extra_entries(tmp_path: Path) -> None:
    packet, _ = build_procurement_review_packet(_source_package(tmp_path))
    entries = _packet_entries(packet)
    entries[PROCUREMENT_REVIEW_NAME] += b"\n<!-- tampered -->\n"

    with pytest.raises(ValueError, match="artifact size is invalid"):
        verify_procurement_review_packet(_rewrite_packet(entries))

    entries = _packet_entries(packet)
    entries["../outside.txt"] = b"outside"
    with pytest.raises(ValueError, match="entries must match the expected order"):
        verify_procurement_review_packet(_rewrite_packet(entries))


def test_packet_verifier_rechecks_embedded_package_semantics(tmp_path: Path) -> None:
    packet, _ = build_procurement_review_packet(_source_package(tmp_path))
    entries = _packet_entries(packet)
    package_doc = json.loads(entries[DECISION_PACKAGE_NAME])
    package_doc["package"]["recommendation"] = "GO"
    package_content = (json.dumps(package_doc, indent=2) + "\n").encode("utf-8")
    entries[DECISION_PACKAGE_NAME] = package_content

    packet_manifest = json.loads(entries[PACKET_MANIFEST_NAME])
    packet_manifest["recommendation"] = "GO"
    decision_record = next(
        record
        for record in packet_manifest["artifacts"]
        if record["path"] == DECISION_PACKAGE_NAME
    )
    decision_record["size_bytes"] = len(package_content)
    decision_record["sha256"] = hashlib.sha256(package_content).hexdigest()
    entries[PACKET_MANIFEST_NAME] = (
        json.dumps(packet_manifest, ensure_ascii=False, indent=2) + "\n"
    ).encode("utf-8")

    with pytest.raises(ValueError, match="proposal_handoff.recommendation"):
        verify_procurement_review_packet(_rewrite_packet(entries))


def test_packet_cli_creates_verifies_and_reports_failures(tmp_path: Path) -> None:
    source_dir = _source_package(tmp_path)
    packet_path = tmp_path / "procurement-review.zip"

    create_run, create_result = _run_packet_cli(
        "create",
        str(source_dir),
        "--packet",
        str(packet_path),
    )
    verify_run, verify_result = _run_packet_cli("verify", str(packet_path))

    assert create_run.returncode == verify_run.returncode == 0
    assert create_run.stderr == verify_run.stderr == ""
    assert create_result["status"] == verify_result["status"] == "passed"
    assert create_result["operation"] == "create"
    assert verify_result["operation"] == "verify"
    assert create_result["packet_sha256"] == verify_result["packet_sha256"]
    assert create_result["packet_verified"] is verify_result["packet_verified"] is True
    assert create_result["operational_approval"] is False

    failure_run, failure_result = _run_packet_cli(
        "create",
        str(tmp_path / "missing"),
        "--packet",
        str(tmp_path / "missing.zip"),
    )
    assert failure_run.returncode == 1
    assert failure_run.stderr == ""
    assert failure_result["status"] == "failed"
    assert failure_result["error_type"] == "FileNotFoundError"
    assert "Traceback" not in failure_run.stdout
