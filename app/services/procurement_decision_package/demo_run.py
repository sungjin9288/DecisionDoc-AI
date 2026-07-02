"""Local demo run orchestration: seed, export, and evidence validation.

This module is intentionally local and deterministic. It does not call providers,
AWS, training, model promotion, or service-resume paths.
"""
from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from app.services.procurement_decision_package.constants import (
    DEFAULT_DEMO_DATA_DIR,
    DEFAULT_DEMO_OUT_DIR,
    DEMO_EVIDENCE_CHECK_FIELDS,
    DEMO_PROJECT_ID,
    DEMO_RECEIPT_NAME,
    DEMO_RESULT_NAME,
    DEMO_TENANT_ID,
    EVIDENCE_FILE_FIELDS,
    EXPLICIT_AUTHORIZATION_BOUNDARY,
    EXTERNAL_RUNTIME_ACTION_ORDER,
    GATE_NAME,
    INCLUDED_ARTIFACT_ORDER,
    PROCUREMENT_DECISION_PACKAGE_SAMPLE_VALIDATION_SCHEMA_PURPOSE,
    PROCUREMENT_DECISION_PACKAGE_SCHEMA_PURPOSE,
    VALIDATION_SUMMARY_NAME,
)
from app.services.procurement_decision_package.artifact_evidence import (
    build_artifact_fingerprint,
    build_artifact_inventory,
    validate_artifact_fingerprint,
    validate_artifact_inventory,
    validate_artifact_list,
    validate_demo_evidence_receipt_file,
    validate_local_package_artifacts,
    render_demo_evidence_receipt,
)
from app.services.procurement_decision_package.artifact_writers import (
    write_json_atomic,
    write_text_atomic,
)
from app.services.procurement_decision_package.cli_manifest_check import (
    _require_passed_status,
)
from app.services.procurement_decision_package.json_helpers import (
    _exception_fields,
    _field_path,
    _optional_path,
    _project_fields,
    _require_boolean_fields,
    _require_mapping,
    load_json,
)
from app.services.procurement_decision_package.package_builder import (
    export_project_decision_package,
    seed_demo_decision_record,
)

def validate_demo_run_result(
    demo_result: dict[str, Any],
    *,
    output_dir: Path,
    demo_result_path: Path,
    require_demo_result_checked: bool = True,
) -> dict[str, Any]:
    artifact_check_path = _demo_run_result_field_path("artifact_check")
    artifact_check = _require_mapping(
        demo_result.get("artifact_check"),
        artifact_check_path,
    )
    _require_passed_status(artifact_check, artifact_check_path)
    _require_boolean_fields(
        artifact_check,
        ("operational_approval",),
        expected=False,
        path=artifact_check_path,
    )
    if require_demo_result_checked:
        _require_boolean_fields(
            artifact_check,
            ("demo_result_checked",),
            expected=True,
            path=artifact_check_path,
        )

    recorded_demo_result_path = demo_result.get("demo_result_path")
    expected_demo_result_path = str(demo_result_path)
    recorded_output_dir = demo_result.get("output_dir")
    expected_output_dir = str(output_dir)

    if recorded_demo_result_path != expected_demo_result_path:
        raise ValueError(
            "demo_run_result.demo_result_path must match "
            "the checked evidence file"
        )

    if recorded_output_dir != expected_output_dir:
        raise ValueError(
            "demo_run_result.output_dir must match "
            "the checked output directory"
        )

    validate_artifact_list(
        demo_result.get("artifacts"),
        path=_demo_run_result_field_path("artifacts"),
    )
    return artifact_check


def _demo_run_result_field_path(field: str) -> str:
    return f"demo_run_result.{field}"


def validate_artifact_inventory_matches_files(
    value: Any,
    *,
    output_dir: Path,
    path: str,
) -> dict[str, Any]:
    artifact_inventory = validate_artifact_inventory(value, path=path)
    for artifact_name in INCLUDED_ARTIFACT_ORDER:
        recorded_fingerprint = validate_artifact_fingerprint(
            artifact_inventory.get(artifact_name),
            path=_field_path(path, artifact_name),
        )
        current_fingerprint = build_artifact_fingerprint(output_dir / artifact_name)
        recorded_sha256 = recorded_fingerprint.get("sha256")
        current_sha256 = current_fingerprint["sha256"]
        recorded_size_bytes = recorded_fingerprint.get("size_bytes")
        current_size_bytes = current_fingerprint["size_bytes"]

        if recorded_sha256 != current_sha256:
            raise ValueError(f"artifact inventory sha256 mismatch: {artifact_name}")

        if recorded_size_bytes != current_size_bytes:
            raise ValueError(f"artifact inventory size mismatch: {artifact_name}")

    return artifact_inventory


def validate_demo_evidence_files(
    output_dir: Path,
    *,
    require_demo_result_checked: bool = True,
    require_demo_receipt: bool = True,
) -> dict[str, bool]:
    evidence_flags = {field: False for field in DEMO_EVIDENCE_CHECK_FIELDS}
    demo_result_path = output_dir / DEMO_RESULT_NAME
    if not demo_result_path.exists():
        return evidence_flags

    demo_result = load_json(demo_result_path)
    validate_demo_run_result(
        demo_result,
        output_dir=output_dir,
        demo_result_path=demo_result_path,
        require_demo_result_checked=require_demo_result_checked,
    )
    validate_artifact_inventory_matches_files(
        demo_result.get("artifact_inventory"),
        output_dir=output_dir,
        path=_demo_run_result_field_path("artifact_inventory"),
    )
    evidence_flags["artifact_inventory_checked"] = True

    if require_demo_receipt:
        validation_summary = load_json(output_dir / VALIDATION_SUMMARY_NAME)
        validate_demo_evidence_receipt_file(
            receipt_path=output_dir / DEMO_RECEIPT_NAME,
            demo_result=demo_result,
            artifact_inventory=demo_result.get("artifact_inventory"),
            validation_summary=validation_summary,
        )
        evidence_flags["demo_receipt_checked"] = True

    evidence_flags["demo_result_checked"] = True
    return evidence_flags


def build_package_artifact_check_result(
    output_dir: Path,
    *,
    require_demo_result_checked: bool = True,
    require_demo_receipt: bool = True,
) -> dict[str, object]:
    package = validate_local_package_artifacts(output_dir)
    demo_evidence_flags = validate_demo_evidence_files(
        output_dir,
        require_demo_result_checked=require_demo_result_checked,
        require_demo_receipt=require_demo_receipt,
    )
    artifact_count = len(INCLUDED_ARTIFACT_ORDER)
    recommendation = package["recommendation"]

    return {
        "status": "passed",
        "output_dir": str(output_dir),
        "artifact_count": artifact_count,
        "recommendation": recommendation,
        "authorization_boundary": EXPLICIT_AUTHORIZATION_BOUNDARY,
        "operational_approval": False,
        **demo_evidence_flags,
    }


def build_package_artifact_check_failure_result(
    output_dir: Path,
    exc: Exception,
) -> dict[str, object]:
    return {
        "status": "failed",
        "output_dir": str(output_dir),
        **_exception_fields(exc),
    }


def gate_demo_output(output_dir: Path) -> dict[str, object]:
    artifact_check_result = build_package_artifact_check_result(output_dir)
    demo_result_path = output_dir / DEMO_RESULT_NAME
    demo_receipt_path = output_dir / DEMO_RECEIPT_NAME
    if not demo_result_path.is_file():
        raise ValueError(f"demo result file is missing: {demo_result_path}")

    if not demo_receipt_path.is_file():
        raise ValueError(f"demo evidence receipt is missing: {demo_receipt_path}")

    demo_result = load_json(demo_result_path)
    artifact_list_path = _demo_run_result_field_path("artifacts")
    artifacts = validate_artifact_list(
        demo_result.get("artifacts"),
        path=artifact_list_path,
    )
    demo_evidence_flags = _project_fields(
        artifact_check_result,
        DEMO_EVIDENCE_CHECK_FIELDS,
    )

    return {
        "status": "passed",
        "gate": GATE_NAME,
        "output_dir": str(output_dir),
        "demo_result_path": str(demo_result_path),
        "demo_receipt_path": str(demo_receipt_path),
        "operational_approval": artifact_check_result["operational_approval"],
        "artifact_count": artifact_check_result["artifact_count"],
        "excluded_external_actions": list(EXTERNAL_RUNTIME_ACTION_ORDER),
        "recommendation": artifact_check_result["recommendation"],
        "authorization_boundary": artifact_check_result["authorization_boundary"],
        "artifacts": artifacts,
        **demo_evidence_flags,
    }


def build_gate_failure_result(output_dir: Path, exc: Exception) -> dict[str, object]:
    return {
        "status": "failed",
        "gate": GATE_NAME,
        "output_dir": str(output_dir),
        **_exception_fields(exc),
    }


def build_sample_builder_failure_result(
    *,
    sample_input_path: Path,
    output_dir: Path,
    exc: Exception,
) -> dict[str, object]:
    return {
        "schema_purpose": PROCUREMENT_DECISION_PACKAGE_SCHEMA_PURPOSE,
        "status": "failed",
        "sample_input": str(sample_input_path),
        "output_dir": str(output_dir),
        **_exception_fields(exc),
    }


def build_sample_validation_failure_result(
    *,
    sample_input_path: Path,
    expected_package_path: Path,
    exc: Exception,
) -> dict[str, object]:
    return {
        "schema_purpose": PROCUREMENT_DECISION_PACKAGE_SAMPLE_VALIDATION_SCHEMA_PURPOSE,
        "status": "failed",
        "sample_input": str(sample_input_path),
        "expected_package": str(expected_package_path),
        **_exception_fields(exc),
    }


def build_export_package_failure_result(
    *,
    data_dir: Path,
    tenant_id: str,
    project_id: str,
    out_dir: Path | None,
    exc: Exception,
) -> dict[str, object]:
    return {
        "status": "failed",
        "schema_purpose": PROCUREMENT_DECISION_PACKAGE_SCHEMA_PURPOSE,
        "data_dir": str(data_dir),
        "tenant_id": tenant_id,
        "project_id": project_id,
        "output_dir": _optional_path(out_dir),
        **_exception_fields(exc),
    }


def build_demo_run_result(
    export_result: dict[str, object],
    *,
    output_dir: Path,
    artifact_check: dict[str, object],
    seeded_decision_id: str,
    demo_tenant_id: str,
    demo_project_id: str,
    clean_output: bool,
) -> dict[str, object]:
    return {
        "status": export_result["status"],
        "schema_purpose": export_result["schema_purpose"],
        "output_dir": export_result["output_dir"],
        "demo_tenant_id": demo_tenant_id,
        "demo_project_id": demo_project_id,
        "seeded_decision_id": seeded_decision_id,
        "demo_result_path": str(output_dir / DEMO_RESULT_NAME),
        "demo_receipt_path": str(output_dir / DEMO_RECEIPT_NAME),
        "artifact_check": artifact_check,
        "artifact_inventory": build_artifact_inventory(output_dir),
        "artifacts": export_result["artifacts"],
        "tenant_id": export_result["tenant_id"],
        "project_id": export_result["project_id"],
        "decision_id": export_result["decision_id"],
        "recommendation": export_result["recommendation"],
        "authorization_boundary": export_result["authorization_boundary"],
        "clean_output": clean_output,
    }


def build_demo_run_failure_result(
    *,
    data_dir: Path,
    out_dir: Path,
    clean_output: bool,
    exc: Exception,
) -> dict[str, object]:
    return {
        "schema_purpose": PROCUREMENT_DECISION_PACKAGE_SCHEMA_PURPOSE,
        "status": "failed",
        "data_dir": str(data_dir),
        "output_dir": str(out_dir),
        "clean_output": clean_output,
        **_exception_fields(exc),
    }


def write_demo_evidence_state(
    demo_result: dict[str, object],
    *,
    demo_result_path: Path,
    artifact_check: dict[str, object],
    receipt_path: Path | None = None,
) -> dict[str, object]:
    demo_result["artifact_check"] = artifact_check
    write_json_atomic(demo_result_path, demo_result)

    if receipt_path is not None:
        write_text_atomic(receipt_path, render_demo_evidence_receipt(demo_result))

    return demo_result


def write_validated_demo_evidence(
    demo_result: dict[str, object],
    *,
    output_dir: Path,
    demo_result_path: Path,
    receipt_path: Path,
    initial_artifact_check: dict[str, object],
) -> dict[str, object]:
    write_demo_evidence_state(
        demo_result,
        demo_result_path=demo_result_path,
        artifact_check=initial_artifact_check,
    )
    first_written_artifact_check = build_package_artifact_check_result(
        output_dir,
        require_demo_result_checked=False,
        require_demo_receipt=False,
    )
    write_demo_evidence_state(
        demo_result,
        demo_result_path=demo_result_path,
        artifact_check=first_written_artifact_check,
    )
    receipt_ready_artifact_check = build_package_artifact_check_result(
        output_dir,
        require_demo_receipt=False,
    )
    write_demo_evidence_state(
        demo_result,
        demo_result_path=demo_result_path,
        artifact_check=receipt_ready_artifact_check,
        receipt_path=receipt_path,
    )
    final_artifact_check = build_package_artifact_check_result(output_dir)
    return write_demo_evidence_state(
        demo_result,
        demo_result_path=demo_result_path,
        artifact_check=final_artifact_check,
        receipt_path=receipt_path,
    )


def run_demo(
    *,
    data_dir: Path = DEFAULT_DEMO_DATA_DIR,
    out_dir: Path = DEFAULT_DEMO_OUT_DIR,
    reviewer_owner: str = "executive-reviewer",
    clean_output: bool = False,
) -> dict[str, object]:
    output_dir = out_dir
    prepare_demo_output_dir(output_dir, clean_output=clean_output)

    seeded_decision_id = seed_demo_decision_record(data_dir=data_dir)
    export_result = export_demo_decision_package(
        data_dir=data_dir,
        out_dir=output_dir,
        reviewer_owner=reviewer_owner,
    )
    initial_artifact_check_result = build_package_artifact_check_result(output_dir)
    demo_run_result = build_demo_run_result(
        export_result,
        output_dir=output_dir,
        artifact_check=initial_artifact_check_result,
        seeded_decision_id=seeded_decision_id,
        demo_tenant_id=DEMO_TENANT_ID,
        demo_project_id=DEMO_PROJECT_ID,
        clean_output=clean_output,
    )
    return write_validated_demo_evidence(
        demo_run_result,
        output_dir=output_dir,
        demo_result_path=output_dir / DEMO_RESULT_NAME,
        receipt_path=output_dir / DEMO_RECEIPT_NAME,
        initial_artifact_check=initial_artifact_check_result,
    )


def prepare_demo_output_dir(out_dir: Path, *, clean_output: bool) -> None:
    if clean_output and out_dir.exists():
        shutil.rmtree(out_dir)


def export_demo_decision_package(
    *,
    data_dir: Path,
    out_dir: Path,
    reviewer_owner: str,
) -> dict[str, object]:
    return export_project_decision_package(
        data_dir=data_dir,
        tenant_id=DEMO_TENANT_ID,
        project_id=DEMO_PROJECT_ID,
        out_dir=out_dir,
        reviewer_owner=reviewer_owner,
    )


def build_evidence_files(
    *,
    demo_result_path: object | None = None,
    demo_receipt_path: object | None = None,
    gate_result_path: object | None = None,
    smoke_result_path: object | None = None,
    smoke_check_result_path: object | None = None,
) -> dict[str, object | None]:
    evidence_file_slots = {
        "demo_result": _optional_path(demo_result_path),
        "demo_receipt": _optional_path(demo_receipt_path),
        "gate_result": _optional_path(gate_result_path),
        "smoke_result": _optional_path(smoke_result_path),
        "smoke_check_result": _optional_path(smoke_check_result_path),
    }

    return _project_fields(evidence_file_slots, EVIDENCE_FILE_FIELDS)
