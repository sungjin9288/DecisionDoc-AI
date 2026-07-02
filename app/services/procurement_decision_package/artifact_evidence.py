"""Artifact fingerprint/inventory validation and demo evidence receipt handling.

This module is intentionally local and deterministic. It does not call providers,
AWS, training, model promotion, or service-resume paths.
"""
from __future__ import annotations

import hashlib
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from app.services.procurement_decision_package.constants import (
    ARTIFACT_INVENTORY_TABLE_BODY_OFFSET,
    ARTIFACT_INVENTORY_TABLE_HEADER,
    ARTIFACT_INVENTORY_TABLE_SEPARATOR,
    DECISION_PACKAGE_DOCUMENT_PATH,
    DECISION_PACKAGE_NAME,
    DECISION_PACKAGE_ROOT_PATH,
    DECISION_SUMMARY_NAME,
    DEMO_RECEIPT_REQUIRED_MARKERS,
    DEMO_RECEIPT_VALIDATION_SUMMARY_FIELDS,
    EVIDENCE_SUMMARY_NAME,
    EVIDENCE_SUMMARY_REQUIRED_MARKERS,
    INCLUDED_ARTIFACT_ORDER,
    JSON_ARTIFACT_PACKAGE_FIELDS,
    NON_AUTHORIZATION_MARKER,
    PACKAGE_EVIDENCE_TYPES,
    SIGNOFF_SUMMARY_NAME,
    SIGNOFF_SUMMARY_REQUIRED_MARKERS,
    VALIDATION_SUMMARY_NAME,
    _DemoReceiptContext,
    _DemoReceiptValidationSummary,
)
from app.services.procurement_decision_package.field_validators import (
    _require_non_empty_string_field,
)
from app.services.procurement_decision_package.json_helpers import (
    _bool_label,
    _field_path,
    _is_non_negative_int,
    _is_sha256_hex,
    _missing_values,
    _require_exact_ordered_values,
    _require_mapping,
    _require_non_empty_list,
    _require_non_empty_string_list,
    _require_unique_values,
    load_json,
)
from app.services.procurement_decision_package.package_document_validation import (
    validate_json_artifact_matches_package,
    validate_package_document_for_path,
)

def validate_local_package_artifacts(output_dir: Path) -> dict[str, Any]:
    package_doc_path = output_dir / DECISION_PACKAGE_NAME

    validate_package_artifact_files(output_dir)

    package_doc = load_json(package_doc_path)
    package = validate_package_document_for_path(
        package_doc,
        path=DECISION_PACKAGE_DOCUMENT_PATH,
    )
    validate_local_package_coverage(package, path=DECISION_PACKAGE_ROOT_PATH)

    for artifact_name, package_field in JSON_ARTIFACT_PACKAGE_FIELDS.items():
        validate_json_artifact_matches_package(
            output_dir,
            package_doc,
            package,
            artifact_name=artifact_name,
            package_field=package_field,
        )

    validate_markdown_artifact_files(output_dir)
    return package


def validate_local_package_coverage(package: dict[str, Any], *, path: str) -> None:
    _require_non_empty_list(
        package.get("hard_filters"),
        _field_path(path, "hard_filters"),
    )

    _require_local_soft_fit_coverage(
        package.get("soft_fit_score"),
        path=_field_path(path, "soft_fit_score"),
    )

    evidence_summary_path = _field_path(path, "evidence_summary")
    evidence_summary = _require_non_empty_list(
        package.get("evidence_summary"),
        evidence_summary_path,
    )
    _require_package_evidence_types(evidence_summary, evidence_summary_path)

    _require_non_empty_list(
        package.get("bid_readiness_checklist"),
        _field_path(path, "bid_readiness_checklist"),
    )


def _require_local_soft_fit_coverage(value: object, *, path: str) -> None:
    soft_fit_score = _require_mapping(value, path)
    _require_non_empty_list(
        soft_fit_score.get("factors"),
        _field_path(path, "factors"),
    )


def _require_package_evidence_types(evidence_summary: Sequence[Any], path: str) -> None:
    missing_types = _missing_values(
        PACKAGE_EVIDENCE_TYPES,
        [
            item.get("type")
            for item in evidence_summary
            if isinstance(item, dict)
        ],
    )
    if missing_types:
        raise ValueError(f"{path} must include source_fact and missing_evidence")


def build_artifact_fingerprint(path: Path) -> dict[str, object]:
    artifact_bytes = path.read_bytes()
    return {
        "sha256": hashlib.sha256(artifact_bytes).hexdigest(),
        "size_bytes": len(artifact_bytes),
    }


def build_artifact_inventory(output_dir: Path) -> dict[str, dict[str, object]]:
    inventory: dict[str, dict[str, object]] = {}
    for artifact_name in INCLUDED_ARTIFACT_ORDER:
        inventory[artifact_name] = build_artifact_fingerprint(
            output_dir / artifact_name
        )
    return inventory


def validate_artifact_fingerprint(value: Any, *, path: str) -> dict[str, object]:
    fingerprint = _require_mapping(value, path)

    sha256 = fingerprint.get("sha256")
    sha256_path = _field_path(path, "sha256")
    if not _is_sha256_hex(sha256):
        raise ValueError(f"{sha256_path} must be a 64-character hex string")

    size_bytes = fingerprint.get("size_bytes")
    size_bytes_path = _field_path(path, "size_bytes")
    if not _is_non_negative_int(size_bytes):
        raise ValueError(f"{size_bytes_path} must be a non-negative integer")
    return fingerprint


def validate_artifact_inventory(value: Any, *, path: str) -> dict[str, Any]:
    artifact_inventory = _require_mapping(value, path)
    _require_exact_ordered_values(
        list(artifact_inventory),
        INCLUDED_ARTIFACT_ORDER,
        path=path,
        missing_label="artifacts",
        unknown_label="artifacts",
    )
    return artifact_inventory


def validate_artifact_list(value: Any, *, path: str) -> list[str]:
    artifacts = _require_non_empty_string_list(value, path)
    _require_unique_values(artifacts, path)
    _require_exact_ordered_values(
        artifacts,
        INCLUDED_ARTIFACT_ORDER,
        path=path,
        missing_label="package artifacts",
        unknown_label="package artifacts",
    )
    return artifacts


def validate_package_artifact_files(output_dir: Path) -> None:
    if not output_dir.exists() or not output_dir.is_dir():
        raise FileNotFoundError(f"package output directory not found: {output_dir}")
    missing_artifacts = [
        artifact_name
        for artifact_name in INCLUDED_ARTIFACT_ORDER
        if not (output_dir / artifact_name).is_file()
    ]
    if missing_artifacts:
        raise ValueError(
            f"missing package artifacts: {', '.join(missing_artifacts)}"
        )


def render_artifact_inventory_row(
    artifact_name: str,
    fingerprint: dict[str, object],
) -> str:
    return (
        f"| {artifact_name} | {fingerprint['size_bytes']} | "
        f"{fingerprint['sha256']} |"
    )


def build_artifact_inventory_rows(value: Any, *, path: str) -> list[str]:
    return list(_build_artifact_inventory_row_map(value, path=path).values())


def _build_artifact_inventory_row_map(value: Any, *, path: str) -> dict[str, str]:
    artifact_inventory = validate_artifact_inventory(value, path=path)
    rows: dict[str, str] = {}
    for artifact_name in INCLUDED_ARTIFACT_ORDER:
        fingerprint = validate_artifact_fingerprint(
            artifact_inventory.get(artifact_name),
            path=_field_path(path, artifact_name),
        )
        rows[artifact_name] = render_artifact_inventory_row(
            artifact_name,
            fingerprint,
        )
    return rows


def render_demo_evidence_receipt(demo_result: dict[str, object]) -> str:
    context = _require_demo_receipt_context(demo_result)
    summary_and_table_header_lines = _build_demo_evidence_receipt_lines(
        demo_result=demo_result,
        artifact_check=context.artifact_check,
        operator_summary=context.operator_summary,
        next_review_action=context.next_review_action,
    )
    artifact_inventory_rows = build_artifact_inventory_rows(
        context.artifact_inventory,
        path="artifact_inventory",
    )
    receipt_lines = [
        *summary_and_table_header_lines,
        *artifact_inventory_rows,
        "",
    ]
    return "\n".join(receipt_lines)


def _require_demo_receipt_context(
    demo_result: dict[str, object],
) -> _DemoReceiptContext:
    artifact_check = _require_mapping(
        demo_result.get("artifact_check"),
        "artifact_check",
    )
    artifact_inventory = _require_mapping(
        demo_result.get("artifact_inventory"),
        "artifact_inventory",
    )
    output_dir = demo_result.get("output_dir")
    if not isinstance(output_dir, str):
        raise ValueError("output_dir must be a string")
    validation_summary = _load_demo_receipt_validation_summary(output_dir)
    return _DemoReceiptContext(
        artifact_check=artifact_check,
        artifact_inventory=artifact_inventory,
        operator_summary=validation_summary.operator_summary,
        next_review_action=validation_summary.next_review_action,
    )


def _load_demo_receipt_validation_summary(
    output_dir: str,
) -> _DemoReceiptValidationSummary:
    validation_summary = load_json(Path(output_dir) / VALIDATION_SUMMARY_NAME)
    return _DemoReceiptValidationSummary(
        operator_summary=_require_non_empty_string_field(
            validation_summary,
            "operator_summary",
            path="validation_summary",
        ),
        next_review_action=_require_non_empty_string_field(
            validation_summary,
            "next_review_action",
            path="validation_summary",
        ),
    )


def _build_demo_evidence_receipt_lines(
    *,
    demo_result: dict[str, object],
    artifact_check: dict[str, Any],
    operator_summary: str,
    next_review_action: str,
) -> list[str]:
    summary_lines = [
        f"- status: {artifact_check.get('status')}",
        f"- recommendation: {demo_result.get('recommendation')}",
        f"- authorization_boundary: {demo_result.get('authorization_boundary')}",
        _demo_receipt_bool_line(
            "operational_approval",
            artifact_check.get("operational_approval"),
        ),
        _demo_receipt_bool_line(
            "demo_result_checked",
            artifact_check.get("demo_result_checked"),
        ),
        _demo_receipt_bool_line(
            "artifact_inventory_checked",
            artifact_check.get("artifact_inventory_checked"),
        ),
        _demo_receipt_bool_line(
            "demo_receipt_checked",
            artifact_check.get("demo_receipt_checked"),
        ),
        f"- operator_summary: {operator_summary}",
        f"- next_review_action: {next_review_action}",
    ]
    return [
        "# Procurement Decision Package Demo Evidence Receipt",
        "",
        "## Summary",
        "",
        *summary_lines,
        "",
        "## Boundary",
        "",
        _demo_evidence_receipt_boundary_text(),
        "",
        "## Artifact Inventory",
        "",
        ARTIFACT_INVENTORY_TABLE_HEADER,
        ARTIFACT_INVENTORY_TABLE_SEPARATOR,
    ]


def _demo_receipt_bool_line(field: str, value: Any) -> str:
    return f"- {field}: {_bool_label(value)}"


def _demo_evidence_receipt_boundary_text() -> str:
    return (
        "This receipt does not authorize provider API execution, AWS runtime "
        "execution, dataset upload, training execution, model promotion, "
        "production service resume, bid submission, legal approval, or "
        "contractual commitment."
    )


def validate_demo_evidence_receipt_text(
    receipt_text: str,
    *,
    artifact_inventory: Any,
    validation_summary: Any,
    inventory_path: str = "demo_run_result.artifact_inventory",
) -> None:
    missing_markers = _missing_markers(DEMO_RECEIPT_REQUIRED_MARKERS, receipt_text)
    if missing_markers:
        raise ValueError(
            f"demo evidence receipt missing markers: {', '.join(missing_markers)}"
        )

    _require_demo_receipt_artifact_inventory_rows(
        receipt_text,
        artifact_inventory=artifact_inventory,
        inventory_path=inventory_path,
    )
    validation_summary = _require_mapping(validation_summary, "validation_summary")
    for field in DEMO_RECEIPT_VALIDATION_SUMMARY_FIELDS:
        if f"{field}: {validation_summary[field]}" not in receipt_text:
            raise ValueError(
                "demo evidence receipt missing validation summary field: "
                f"{field}"
            )


def _require_demo_receipt_artifact_inventory_rows(
    receipt_text: str,
    *,
    artifact_inventory: Any,
    inventory_path: str,
) -> None:
    expected_row_map = _build_artifact_inventory_row_map(
        artifact_inventory,
        path=inventory_path,
    )
    for artifact_name, expected_row in expected_row_map.items():
        if expected_row not in receipt_text:
            raise ValueError(
                f"demo evidence receipt missing artifact inventory row: "
                f"{artifact_name}"
            )

    expected_rows = list(expected_row_map.values())
    receipt_rows = _artifact_inventory_rows_from_receipt(receipt_text)
    if receipt_rows != expected_rows:
        raise ValueError(
            "demo evidence receipt artifact inventory rows "
            "must match the expected order"
        )

def _artifact_inventory_rows_from_receipt(receipt_text: str) -> list[str]:
    receipt_lines = receipt_text.splitlines()
    try:
        table_header_index = receipt_lines.index(ARTIFACT_INVENTORY_TABLE_HEADER)
    except ValueError as exc:
        raise ValueError(
            "demo evidence receipt missing artifact inventory table header"
        ) from exc
    table_body_start = table_header_index + ARTIFACT_INVENTORY_TABLE_BODY_OFFSET
    table_body_end = table_body_start + len(INCLUDED_ARTIFACT_ORDER)
    return receipt_lines[table_body_start:table_body_end]


def validate_demo_evidence_receipt_file(
    *,
    receipt_path: Path,
    demo_result: dict[str, Any],
    artifact_inventory: Any,
    validation_summary: Any,
) -> None:
    if demo_result.get("demo_receipt_path") != str(receipt_path):
        raise ValueError(
            "demo_run_result.demo_receipt_path must match "
            "the checked receipt file"
        )
    if not receipt_path.is_file():
        raise ValueError("demo evidence receipt file is missing")

    validate_demo_evidence_receipt_text(
        receipt_path.read_text(encoding="utf-8"),
        artifact_inventory=artifact_inventory,
        validation_summary=validation_summary,
    )


def validate_signoff_summary_text(signoff_summary: str) -> None:
    missing_markers = _missing_markers(
        SIGNOFF_SUMMARY_REQUIRED_MARKERS,
        signoff_summary,
    )
    if missing_markers:
        raise ValueError(
            f"{SIGNOFF_SUMMARY_NAME} missing sign-off markers: "
            f"{', '.join(missing_markers)}"
        )


def validate_decision_summary_text(decision_summary: str) -> None:
    if NON_AUTHORIZATION_MARKER not in decision_summary:
        raise ValueError(
            f"{DECISION_SUMMARY_NAME} must include the non-authorization boundary"
        )


def validate_evidence_summary_text(evidence_summary: str) -> None:
    missing_markers = _missing_markers(
        EVIDENCE_SUMMARY_REQUIRED_MARKERS,
        evidence_summary,
    )
    if missing_markers:
        raise ValueError(
            f"{EVIDENCE_SUMMARY_NAME} missing evidence type markers: "
            f"{', '.join(missing_markers)}"
        )


def _missing_markers(markers: Sequence[str], text: str) -> list[str]:
    return [marker for marker in markers if marker not in text]


def validate_markdown_artifact_files(output_dir: Path) -> None:
    validate_signoff_summary_text(
        (output_dir / SIGNOFF_SUMMARY_NAME).read_text(encoding="utf-8")
    )
    validate_decision_summary_text(
        (output_dir / DECISION_SUMMARY_NAME).read_text(encoding="utf-8")
    )
    validate_evidence_summary_text(
        (output_dir / EVIDENCE_SUMMARY_NAME).read_text(encoding="utf-8")
    )
