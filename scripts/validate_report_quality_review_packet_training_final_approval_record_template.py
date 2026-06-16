#!/usr/bin/env python3
"""Validate a pending final approval record template for report quality training planning."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
from typing import Any, Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
PACKET_REVIEW_VALIDATOR_PATH = (
    REPO_ROOT / "scripts/validate_report_quality_review_packet_training_final_approval_packet_review.py"
)
EXPECTED_SCHEMA = "decisiondoc_report_quality_training_final_approval_record_template.v1"
REQUIRED_APPROVER_ROLES = {
    "ML/AI Owner",
    "Product/PM",
    "Compliance/Security",
    "Release Owner",
}
FORBIDDEN_TRUE_KEYS = {
    "actual_training_approval_recorded",
    "approval_record_completed",
    "approval_effective",
    "final_training_approval_granted",
    "server_file_written",
    "persisted_learning_artifact",
    "external_dataset_upload_authorized",
    "external_dataset_upload_started",
    "external_upload_allowed",
    "provider_api_calls_allowed",
    "provider_fine_tune_api_call_authorized",
    "provider_fine_tune_api_called",
    "provider_job_creation_authorized",
    "provider_job_polling_authorized",
    "provider_job_created",
    "provider_job_polled",
    "provider_job_started",
    "training_execution_authorized",
    "training_execution_allowed",
    "training_execution_started",
    "model_promotion_authorized",
    "model_promotion_allowed",
    "model_promotion_started",
}


def _load_packet_review_validator():
    spec = importlib.util.spec_from_file_location(
        "validate_report_quality_review_packet_training_final_approval_packet_review",
        PACKET_REVIEW_VALIDATOR_PATH,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed to load final approval packet review validator: {PACKET_REVIEW_VALIDATOR_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_PACKET_REVIEW_VALIDATOR = _load_packet_review_validator()


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path}: JSON root must be an object")
    return payload


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _resolve_path(path_value: Any, *, field: str, errors: list[str]) -> Path | None:
    if not isinstance(path_value, str) or not path_value.strip():
        errors.append(f"{field} must be a non-empty path")
        return None
    path = Path(path_value).expanduser().resolve()
    if not path.exists() or not path.is_file():
        errors.append(f"{field} does not exist: {path}")
        return None
    return path


def _validate_hash(*, path: Path | None, expected_hash: Any, field: str, errors: list[str]) -> None:
    if path is None:
        return
    if not isinstance(expected_hash, str) or not expected_hash.strip():
        errors.append(f"{field} must be non-empty")
    elif expected_hash != _sha256(path):
        errors.append(f"{field} does not match referenced file")


def _scan_forbidden_true(value: Any, *, path: str = "$") -> list[str]:
    findings: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}"
            if key in FORBIDDEN_TRUE_KEYS and child is not False:
                findings.append(f"{child_path} must be false")
            findings.extend(_scan_forbidden_true(child, path=child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            findings.extend(_scan_forbidden_true(child, path=f"{path}[{index}]"))
    return findings


def validate_training_final_approval_record_template(
    record_template_path: Path,
    *,
    require_ready: bool = True,
) -> dict[str, Any]:
    resolved_template = record_template_path.expanduser().resolve()
    errors: list[str] = []
    warnings: list[str] = []
    try:
        record = _load_json(resolved_template)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return {
            "report_type": "report_quality_training_final_approval_record_template_validation",
            "ok": False,
            "require_ready": require_ready,
            "record_template_path": str(resolved_template),
            "errors": [str(exc)],
            "warnings": [],
        }

    if record.get("schema_version") != EXPECTED_SCHEMA:
        errors.append(f"schema_version must be {EXPECTED_SCHEMA!r}")
    if record.get("report_type") != "report_quality_training_final_approval_record_template":
        errors.append("report_type must be report_quality_training_final_approval_record_template")
    if not isinstance(record.get("template_id"), str) or not record.get("template_id", "").strip():
        errors.append("template_id must be non-empty")

    recorded_template_path = _resolve_path(
        record.get("record_template_path"),
        field="record_template_path",
        errors=errors,
    )
    if recorded_template_path is not None and recorded_template_path != resolved_template:
        warnings.append("record_template_path points to a different path than the validated template")

    markdown_path = _resolve_path(record.get("record_markdown_path"), field="record_markdown_path", errors=errors)
    if markdown_path is not None:
        markdown = markdown_path.read_text(encoding="utf-8")
        if "Report Quality Training Final Approval Record Template" not in markdown:
            errors.append("record markdown is missing title")
        if "final_training_approval_granted: `false`" not in markdown:
            errors.append("record markdown must show final_training_approval_granted=false")

    packet_review_path = _resolve_path(record.get("packet_review_path"), field="packet_review_path", errors=errors)
    _validate_hash(
        path=packet_review_path,
        expected_hash=record.get("packet_review_sha256"),
        field="packet_review_sha256",
        errors=errors,
    )
    packet_review_validation: dict[str, Any] = {}
    if packet_review_path is not None:
        packet_review = _load_json(packet_review_path)
        packet_review_validation = _PACKET_REVIEW_VALIDATOR.validate_training_final_approval_packet_review(
            packet_review,
            require_complete=True,
        )
        if require_ready and packet_review_validation.get("ok") is not True:
            errors.append("final approval packet review validation must pass")
        if packet_review.get("decision") != "packet_review_complete":
            errors.append("packet review decision must be packet_review_complete")
        if packet_review.get("requested_next_step") != "prepare_final_approval_record_template":
            errors.append("packet review requested_next_step must be prepare_final_approval_record_template")

    packet_path = _resolve_path(record.get("packet_manifest_path"), field="packet_manifest_path", errors=errors)
    _validate_hash(
        path=packet_path,
        expected_hash=record.get("packet_manifest_sha256"),
        field="packet_manifest_sha256",
        errors=errors,
    )

    embedded_review_validation = _as_dict(record.get("packet_review_validation"))
    if require_ready and embedded_review_validation.get("ok") is not True:
        errors.append("embedded packet_review_validation.ok must be true")

    approval_state = _as_dict(record.get("approval_state"))
    if approval_state.get("template_only") is not True:
        errors.append("approval_state.template_only must be true")
    if approval_state.get("status") != "pending_manual_final_approval":
        errors.append("approval_state.status must be pending_manual_final_approval")

    approvals = _as_list(record.get("required_approvals"))
    roles = {str(_as_dict(item).get("role")) for item in approvals}
    missing_roles = sorted(REQUIRED_APPROVER_ROLES - roles)
    if missing_roles:
        errors.append(f"required_approvals missing roles: {', '.join(missing_roles)}")
    for index, item in enumerate(approvals, start=1):
        approval = _as_dict(item)
        if approval.get("decision") != "pending":
            errors.append(f"required_approvals[{index}].decision must be pending")
        for field in ("approver_name", "title_or_team", "approved_at"):
            if str(approval.get(field, "")).strip():
                errors.append(f"required_approvals[{index}].{field} must be blank in template")
        if not isinstance(approval.get("conditions"), list):
            errors.append(f"required_approvals[{index}].conditions must be a list")

    source_files = _as_dict(record.get("source_files"))
    missing_file_count = 0
    for name, record_value in source_files.items():
        file_record = _as_dict(record_value)
        path = _resolve_path(file_record.get("path"), field=f"source_files.{name}.path", errors=errors)
        if file_record.get("exists") is not True:
            errors.append(f"source_files.{name}.exists must be true")
            missing_file_count += 1
        _validate_hash(
            path=path,
            expected_hash=file_record.get("sha256"),
            field=f"source_files.{name}.sha256",
            errors=errors,
        )
    counts = _as_dict(record.get("counts"))
    if counts.get("source_file_count") != len(source_files):
        errors.append("counts.source_file_count must match source_files length")
    if counts.get("missing_file_count") != missing_file_count:
        errors.append("counts.missing_file_count must match missing source files")
    if counts.get("required_approval_count") != len(REQUIRED_APPROVER_ROLES):
        errors.append("counts.required_approval_count must match required approver roles")

    job_spec = _as_dict(record.get("job_spec_snapshot"))
    execution_steps = _as_list(job_spec.get("execution_steps"))
    if len(execution_steps) < 5:
        errors.append("job_spec_snapshot.execution_steps must include at least five steps")
    for index, step_value in enumerate(execution_steps, start=1):
        step = _as_dict(step_value)
        if step.get("status") != "not_started":
            errors.append(f"job_spec_snapshot.execution_steps[{index}].status must be not_started")

    operator_actions = record.get("operator_actions")
    if not isinstance(operator_actions, list) or len(operator_actions) < 3:
        errors.append("operator_actions must include at least three actions")
    else:
        action_text = "\n".join(str(item) for item in operator_actions)
        if "Do not mark any approval" not in action_text:
            errors.append("operator_actions must prohibit marking approval in the generated template")
        if "Do not upload datasets" not in action_text:
            errors.append("operator_actions must explicitly prohibit dataset upload")

    for finding in _scan_forbidden_true(record):
        errors.append(f"training_final_approval_record_template: {finding}")

    return {
        "report_type": "report_quality_training_final_approval_record_template_validation",
        "ok": not errors,
        "require_ready": require_ready,
        "record_template_path": str(resolved_template),
        "schema_version": record.get("schema_version"),
        "template_only": approval_state.get("template_only") is True,
        "approval_granted": approval_state.get("final_training_approval_granted") is True,
        "packet_review_validation_ok": packet_review_validation.get("ok") if packet_review_validation else None,
        "required_approval_count": len(approvals),
        "errors": errors,
        "warnings": warnings,
    }


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate a pending report quality final approval record template.")
    parser.add_argument("record_template", type=Path, help="Path to *-training-final-approval-record-template.json.")
    parser.add_argument("--allow-not-ready", action="store_true")
    parser.add_argument("--json", action="store_true", help="Print machine-readable validation result.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(list(argv) if argv is not None else None)
    result = validate_training_final_approval_record_template(
        args.record_template,
        require_ready=not args.allow_not_ready,
    )
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    elif result["ok"]:
        print("PASS report quality training final approval record template validated")
        print(f"template_only={str(result['template_only']).lower()}")
        print(f"approval_granted={str(result['approval_granted']).lower()}")
        print("training_boundary=not_authorized")
        for warning in result["warnings"]:
            print(f"WARN {warning}")
    else:
        print("FAIL report quality training final approval record template validation failed")
        for error in result["errors"]:
            print(f"ERROR {error}")
        for warning in result["warnings"]:
            print(f"WARN {warning}")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
