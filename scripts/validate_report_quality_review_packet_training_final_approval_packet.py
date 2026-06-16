#!/usr/bin/env python3
"""Validate a local report quality training final approval packet draft."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
from typing import Any, Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
PLAN_REVIEW_VALIDATOR_PATH = REPO_ROOT / "scripts/validate_report_quality_review_packet_training_experiment_plan_review.py"
EXPECTED_SCHEMA = "decisiondoc_report_quality_training_final_approval_packet.v1"
REQUIRED_APPROVER_ROLES = {
    "ML/AI Owner",
    "Product/PM",
    "Compliance/Security",
    "Release Owner",
}
FORBIDDEN_TRUE_KEYS = {
    "actual_training_approval_recorded",
    "final_training_approval_granted",
    "server_file_written",
    "persisted_learning_artifact",
    "external_dataset_upload_started",
    "external_upload_allowed",
    "provider_api_calls_allowed",
    "provider_fine_tune_api_called",
    "provider_job_created",
    "provider_job_polled",
    "provider_job_started",
    "training_execution_allowed",
    "training_execution_started",
    "model_promotion_allowed",
    "model_promotion_started",
}


def _load_plan_review_validator():
    spec = importlib.util.spec_from_file_location(
        "validate_report_quality_review_packet_training_experiment_plan_review",
        PLAN_REVIEW_VALIDATOR_PATH,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed to load plan review validator: {PLAN_REVIEW_VALIDATOR_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_PLAN_REVIEW_VALIDATOR = _load_plan_review_validator()


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


def validate_training_final_approval_packet(
    packet_manifest_path: Path,
    *,
    require_ready: bool = True,
) -> dict[str, Any]:
    resolved_packet = packet_manifest_path.expanduser().resolve()
    errors: list[str] = []
    warnings: list[str] = []
    try:
        packet = _load_json(resolved_packet)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return {
            "report_type": "report_quality_training_final_approval_packet_validation",
            "ok": False,
            "require_ready": require_ready,
            "packet_manifest_path": str(resolved_packet),
            "errors": [str(exc)],
            "warnings": [],
        }

    if packet.get("schema_version") != EXPECTED_SCHEMA:
        errors.append(f"schema_version must be {EXPECTED_SCHEMA!r}")

    recorded_packet_path = _resolve_path(
        packet.get("packet_manifest_path"),
        field="packet_manifest_path",
        errors=errors,
    )
    if recorded_packet_path is not None and recorded_packet_path != resolved_packet:
        warnings.append("packet_manifest_path points to a different path than the validated manifest")

    markdown_path = _resolve_path(packet.get("packet_markdown_path"), field="packet_markdown_path", errors=errors)
    if markdown_path is not None:
        markdown = markdown_path.read_text(encoding="utf-8")
        if "Report Quality Training Final Approval Packet" not in markdown:
            errors.append("packet markdown is missing title")
        if "final_training_approval_granted: `false`" not in markdown:
            errors.append("packet markdown must show final_training_approval_granted=false")
        if "training_execution_allowed: `false`" not in markdown:
            errors.append("packet markdown must show training_execution_allowed=false")

    review_path = _resolve_path(packet.get("plan_review_path"), field="plan_review_path", errors=errors)
    _validate_hash(
        path=review_path,
        expected_hash=packet.get("plan_review_sha256"),
        field="plan_review_sha256",
        errors=errors,
    )
    review_validation: dict[str, Any] = {}
    if review_path is not None:
        review_record = _load_json(review_path)
        review_validation = _PLAN_REVIEW_VALIDATOR.validate_training_experiment_plan_review(
            review_record,
            require_complete=True,
        )
        if require_ready and review_validation.get("ok") is not True:
            errors.append("training experiment plan review validation must pass")
        if review_record.get("decision") != "planning_complete":
            errors.append("plan review decision must be planning_complete")
        if review_record.get("requested_next_step") != "prepare_final_approval_packet":
            errors.append("plan review requested_next_step must be prepare_final_approval_packet")

    plan_path = _resolve_path(packet.get("plan_manifest_path"), field="plan_manifest_path", errors=errors)
    _validate_hash(
        path=plan_path,
        expected_hash=packet.get("plan_manifest_sha256"),
        field="plan_manifest_sha256",
        errors=errors,
    )

    embedded_review_validation = _as_dict(packet.get("plan_review_validation"))
    if require_ready and embedded_review_validation.get("ok") is not True:
        errors.append("embedded plan_review_validation.ok must be true")

    readiness = _as_dict(packet.get("readiness"))
    if require_ready and readiness.get("ok") is not True:
        errors.append("readiness.ok must be true")
    if readiness.get("approval_packet_only") is not True:
        errors.append("readiness.approval_packet_only must be true")
    if require_ready and _as_list(readiness.get("missing_files")):
        errors.append("readiness.missing_files must be empty")

    counts = _as_dict(packet.get("counts"))
    if require_ready and int(counts.get("ready_artifacts") or 0) < 1:
        errors.append("counts.ready_artifacts must be at least 1")
    if require_ready and int(counts.get("completed_signoff_count") or 0) < 1:
        errors.append("counts.completed_signoff_count must be at least 1")

    roles = set(str(role) for role in _as_list(packet.get("required_final_approver_roles")))
    missing_roles = sorted(REQUIRED_APPROVER_ROLES - roles)
    if missing_roles:
        errors.append(f"required_final_approver_roles missing: {', '.join(missing_roles)}")

    source_files = _as_dict(packet.get("source_files"))
    missing_file_count = 0
    for name, record_value in source_files.items():
        record = _as_dict(record_value)
        path = _resolve_path(record.get("path"), field=f"source_files.{name}.path", errors=errors)
        if record.get("exists") is not True:
            errors.append(f"source_files.{name}.exists must be true")
            missing_file_count += 1
        _validate_hash(
            path=path,
            expected_hash=record.get("sha256"),
            field=f"source_files.{name}.sha256",
            errors=errors,
        )
    if counts.get("source_file_count") != len(source_files):
        errors.append("counts.source_file_count must match source_files length")
    if counts.get("missing_file_count") != missing_file_count:
        errors.append("counts.missing_file_count must match missing source files")

    job_spec = _as_dict(packet.get("job_spec_snapshot"))
    execution_steps = _as_list(job_spec.get("execution_steps"))
    if len(execution_steps) < 5:
        errors.append("job_spec_snapshot.execution_steps must include at least five steps")
    for index, step_value in enumerate(execution_steps, start=1):
        step = _as_dict(step_value)
        if step.get("status") != "not_started":
            errors.append(f"job_spec_snapshot.execution_steps[{index}].status must be not_started")

    operator_actions = packet.get("operator_actions")
    if not isinstance(operator_actions, list) or len(operator_actions) < 3:
        errors.append("operator_actions must include at least three actions")
    else:
        action_text = "\n".join(str(item) for item in operator_actions)
        if "separate approval artifact" not in action_text:
            errors.append("operator_actions must require a separate approval artifact")
        if "Do not upload datasets" not in action_text:
            errors.append("operator_actions must explicitly prohibit dataset upload")

    for finding in _scan_forbidden_true(packet):
        errors.append(f"training_final_approval_packet: {finding}")

    return {
        "report_type": "report_quality_training_final_approval_packet_validation",
        "ok": not errors,
        "require_ready": require_ready,
        "packet_manifest_path": str(resolved_packet),
        "schema_version": packet.get("schema_version"),
        "approval_packet_only": readiness.get("approval_packet_only") is True,
        "plan_review_validation_ok": review_validation.get("ok") if review_validation else None,
        "source_file_count": len(source_files),
        "errors": errors,
        "warnings": warnings,
    }


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate a local report quality final approval packet draft.")
    parser.add_argument("packet_manifest", type=Path, help="Path to *-training-final-approval-packet-manifest.json.")
    parser.add_argument("--allow-not-ready", action="store_true")
    parser.add_argument("--json", action="store_true", help="Print machine-readable validation result.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(list(argv) if argv is not None else None)
    result = validate_training_final_approval_packet(
        args.packet_manifest,
        require_ready=not args.allow_not_ready,
    )
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    elif result["ok"]:
        print("PASS report quality training final approval packet validated")
        print(f"approval_packet_only={str(result['approval_packet_only']).lower()}")
        print(f"source_file_count={result['source_file_count']}")
        print("training_boundary=not_authorized")
        for warning in result["warnings"]:
            print(f"WARN {warning}")
    else:
        print("FAIL report quality training final approval packet validation failed")
        for error in result["errors"]:
            print(f"ERROR {error}")
        for warning in result["warnings"]:
            print(f"WARN {warning}")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
