"""Local smoke-test gate that runs the demo, gates it, and records evidence.

This module is intentionally local and deterministic. It does not call providers,
AWS, training, model promotion, or service-resume paths.
"""
from __future__ import annotations

from pathlib import Path

from app.services.procurement_decision_package.constants import (
    DEFAULT_DEMO_DATA_DIR,
    DEFAULT_DEMO_OUT_DIR,
    DEMO_EVIDENCE_CHECK_FIELDS,
    GATE_RESULT_NAME,
    SMOKE_NAME,
)
from app.services.procurement_decision_package.artifact_writers import write_json_atomic
from app.services.procurement_decision_package.demo_run import (
    build_evidence_files,
    gate_demo_output,
    run_demo,
)
from app.services.procurement_decision_package.json_helpers import (
    _exception_fields,
    _optional_path,
    _project_fields,
)

def _build_smoke_gate_result(
    *,
    data_dir: Path,
    out_dir: Path,
    demo_result: dict[str, object],
    gate_result: dict[str, object],
    gate_result_path: Path | None,
    evidence_files: dict[str, object | None],
    gate_result_written: bool,
    clean_output: bool,
) -> dict[str, object]:
    demo_evidence_flags = _project_fields(
        gate_result,
        DEMO_EVIDENCE_CHECK_FIELDS,
    )

    return {
        "status": "passed",
        "smoke": SMOKE_NAME,
        "output_dir": str(out_dir),
        "demo_result_path": demo_result["demo_result_path"],
        "gate_result_path": _optional_path(gate_result_path),
        "smoke_result_path": None,
        "smoke_check_result_path": None,
        "evidence_files": evidence_files,
        "operational_approval": gate_result["operational_approval"],
        "data_dir": str(data_dir),
        "demo_tenant_id": demo_result["demo_tenant_id"],
        "demo_project_id": demo_result["demo_project_id"],
        "seeded_decision_id": demo_result["seeded_decision_id"],
        "demo_receipt_path": demo_result["demo_receipt_path"],
        "gate_result_written": gate_result_written,
        "smoke_result_written": False,
        "smoke_check_result_written": False,
        "package_artifacts_checked": False,
        "smoke_result_checked": False,
        **demo_evidence_flags,
        "artifact_count": gate_result["artifact_count"],
        "excluded_external_actions": gate_result["excluded_external_actions"],
        "recommendation": gate_result["recommendation"],
        "authorization_boundary": gate_result["authorization_boundary"],
        "clean_output": clean_output,
    }


def smoke_demo_gate(
    *,
    data_dir: Path = DEFAULT_DEMO_DATA_DIR,
    out_dir: Path = DEFAULT_DEMO_OUT_DIR,
    reviewer_owner: str = "executive-reviewer",
    clean_output: bool = True,
    write_gate_result: bool = True,
    gate_result_path: Path | None = None,
) -> dict[str, object]:
    output_dir = out_dir
    demo_result = run_demo(
        data_dir=data_dir,
        out_dir=output_dir,
        reviewer_owner=reviewer_owner,
        clean_output=clean_output,
    )
    gate_result = gate_demo_output(output_dir)
    recorded_gate_result_path = None
    if write_gate_result:
        recorded_gate_result_path = gate_result_path or output_dir / GATE_RESULT_NAME
        write_json_atomic(recorded_gate_result_path, gate_result)

    evidence_files = build_evidence_files(
        demo_result_path=demo_result["demo_result_path"],
        demo_receipt_path=demo_result["demo_receipt_path"],
        gate_result_path=recorded_gate_result_path,
    )
    return _build_smoke_gate_result(
        data_dir=data_dir,
        out_dir=output_dir,
        demo_result=demo_result,
        gate_result=gate_result,
        gate_result_path=recorded_gate_result_path,
        evidence_files=evidence_files,
        gate_result_written=write_gate_result,
        clean_output=clean_output,
    )


def build_smoke_failure_result(
    *,
    data_dir: Path,
    out_dir: Path,
    clean_output: bool,
    gate_result_path: Path | None,
    gate_result_written: bool,
    smoke_result_path: Path | None,
    smoke_result_written: bool,
    smoke_check_result_path: Path | None,
    smoke_check_result_written: bool,
    exc: Exception,
) -> dict[str, object]:
    evidence_files = build_evidence_files(
        gate_result_path=gate_result_path,
        smoke_result_path=smoke_result_path,
        smoke_check_result_path=smoke_check_result_path,
    )

    return {
        "status": "failed",
        "smoke": SMOKE_NAME,
        "data_dir": str(data_dir),
        "output_dir": str(out_dir),
        "clean_output": clean_output,
        "gate_result_path": _optional_path(gate_result_path),
        "smoke_result_path": _optional_path(smoke_result_path),
        "smoke_check_result_path": _optional_path(smoke_check_result_path),
        "evidence_files": evidence_files,
        "gate_result_written": gate_result_written,
        "smoke_result_written": smoke_result_written,
        "smoke_check_result_written": smoke_check_result_written,
        "package_artifacts_checked": False,
        "smoke_result_checked": False,
        **_exception_fields(exc),
    }
