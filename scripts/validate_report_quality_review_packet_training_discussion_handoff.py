#!/usr/bin/env python3
"""Validate a local report quality training-discussion handoff manifest."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
from typing import Any, Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
READINESS_VALIDATOR_PATH = REPO_ROOT / "scripts/validate_report_quality_review_packet_training_readiness.py"
EXPECTED_SCHEMA = "decisiondoc_report_quality_review_packet_training_discussion_handoff.v1"
FORBIDDEN_TRUE_KEYS = {
    "actual_reviewer_approval_recorded",
    "server_file_written",
    "persisted_learning_artifact",
    "external_dataset_upload_started",
    "external_dataset_upload_authorized",
    "provider_fine_tune_api_called",
    "provider_fine_tune_api_call_authorized",
    "provider_job_created",
    "provider_job_creation_authorized",
    "training_execution_started",
    "training_execution_authorized",
    "model_promotion_started",
    "model_promotion_authorized",
}


def _load_readiness_validator():
    spec = importlib.util.spec_from_file_location(
        "validate_report_quality_review_packet_training_readiness",
        READINESS_VALIDATOR_PATH,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed to load readiness validator: {READINESS_VALIDATOR_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_READINESS_VALIDATOR = _load_readiness_validator()


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


def validate_training_discussion_handoff_manifest(
    handoff_manifest_path: Path,
    *,
    require_ready: bool = True,
) -> dict[str, Any]:
    resolved_handoff_manifest = handoff_manifest_path.expanduser().resolve()
    errors: list[str] = []
    warnings: list[str] = []
    try:
        handoff = _load_json(resolved_handoff_manifest)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return {
            "report_type": "report_quality_review_packet_training_discussion_handoff_validation",
            "ok": False,
            "require_ready": require_ready,
            "handoff_manifest_path": str(resolved_handoff_manifest),
            "errors": [str(exc)],
            "warnings": [],
        }

    if handoff.get("schema_version") != EXPECTED_SCHEMA:
        errors.append(f"schema_version must be {EXPECTED_SCHEMA!r}")

    recorded_manifest_path = _resolve_path(
        handoff.get("handoff_manifest_path"),
        field="handoff_manifest_path",
        errors=errors,
    )
    if recorded_manifest_path is not None and recorded_manifest_path != resolved_handoff_manifest:
        warnings.append("handoff_manifest_path points to a different path than the validated manifest")

    readiness_path = _resolve_path(
        handoff.get("readiness_manifest_path"),
        field="readiness_manifest_path",
        errors=errors,
    )
    readiness_validation: dict[str, Any] = {}
    if readiness_path is not None:
        expected_hash = handoff.get("readiness_manifest_sha256")
        if not isinstance(expected_hash, str) or not expected_hash.strip():
            errors.append("readiness_manifest_sha256 must be non-empty")
        elif expected_hash != _sha256(readiness_path):
            errors.append("readiness_manifest_sha256 does not match readiness_manifest_path")
        readiness_validation = _READINESS_VALIDATOR.validate_training_readiness_manifest(
            readiness_path,
            require_ready=require_ready,
        )
        if require_ready and readiness_validation.get("ok") is not True:
            errors.append("training readiness validation must pass")

    handoff_index_path = _resolve_path(
        handoff.get("handoff_index_path"),
        field="handoff_index_path",
        errors=errors,
    )
    if handoff_index_path is not None:
        index_text = handoff_index_path.read_text(encoding="utf-8")
        if "Report Quality Training Discussion Handoff" not in index_text:
            errors.append("handoff index is missing title")
        if "training_authorized: `false`" not in index_text:
            errors.append("handoff index must show training_authorized=false")

    embedded_validation = _as_dict(handoff.get("readiness_validation"))
    if require_ready and embedded_validation.get("ok") is not True:
        errors.append("embedded readiness_validation.ok must be true")

    readiness = _as_dict(handoff.get("readiness"))
    if require_ready and readiness.get("ok") is not True:
        errors.append("readiness.ok must be true")
    if require_ready and readiness.get("ready_for_training_discussion") is not True:
        errors.append("readiness.ready_for_training_discussion must be true")
    if require_ready and _as_list(readiness.get("missing_files")):
        errors.append("readiness.missing_files must be empty")

    handoff_files = _as_dict(handoff.get("handoff_files"))
    missing_file_count = 0
    for name, record_value in handoff_files.items():
        record = _as_dict(record_value)
        path = _resolve_path(record.get("path"), field=f"handoff_files.{name}.path", errors=errors)
        if record.get("exists") is not True:
            errors.append(f"handoff_files.{name}.exists must be true")
            missing_file_count += 1
        if path is not None:
            expected_hash = record.get("sha256")
            if not isinstance(expected_hash, str) or not expected_hash.strip():
                errors.append(f"handoff_files.{name}.sha256 must be non-empty")
            elif expected_hash != _sha256(path):
                errors.append(f"handoff_files.{name}.sha256 does not match file")

    training_readiness_record = _as_dict(handoff_files.get("training_readiness_manifest"))
    if readiness_path is not None and training_readiness_record:
        record_path = Path(str(training_readiness_record.get("path", ""))).expanduser().resolve()
        if record_path != readiness_path:
            errors.append("handoff_files.training_readiness_manifest.path must match readiness_manifest_path")

    counts = _as_dict(handoff.get("counts"))
    if counts.get("handoff_file_count") != len(handoff_files):
        errors.append("counts.handoff_file_count must match handoff_files length")
    if counts.get("missing_file_count") != missing_file_count:
        errors.append("counts.missing_file_count must match missing handoff files")
    if require_ready and int(counts.get("ready_artifacts") or 0) < 1:
        errors.append("counts.ready_artifacts must be at least 1")
    if require_ready and int(counts.get("completed_signoff_count") or 0) < 1:
        errors.append("counts.completed_signoff_count must be at least 1")
    if int(counts.get("invalid_signoff_count") or 0) != 0:
        errors.append("counts.invalid_signoff_count must be 0")

    operator_actions = handoff.get("operator_actions")
    if not isinstance(operator_actions, list) or len(operator_actions) < 4:
        errors.append("operator_actions must include at least four actions")
    else:
        action_text = "\n".join(str(item) for item in operator_actions)
        if "Do not upload datasets" not in action_text:
            errors.append("operator_actions must explicitly prohibit dataset upload")
        if "provider fine-tune" not in action_text:
            errors.append("operator_actions must explicitly prohibit provider fine-tune")
        if "start training" not in action_text:
            errors.append("operator_actions must explicitly prohibit training execution")

    for finding in _scan_forbidden_true(handoff):
        errors.append(f"training_discussion_handoff: {finding}")

    return {
        "report_type": "report_quality_review_packet_training_discussion_handoff_validation",
        "ok": not errors,
        "require_ready": require_ready,
        "handoff_manifest_path": str(resolved_handoff_manifest),
        "schema_version": handoff.get("schema_version"),
        "readiness_manifest_path": str(readiness_path) if readiness_path is not None else "",
        "handoff_index_path": str(handoff_index_path) if handoff_index_path is not None else "",
        "ready_for_training_discussion": readiness.get("ready_for_training_discussion") is True,
        "handoff_file_count": len(handoff_files),
        "readiness_validation_ok": readiness_validation.get("ok") if readiness_validation else None,
        "counts": counts,
        "errors": errors,
        "warnings": warnings,
    }


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate a local training-discussion handoff manifest.")
    parser.add_argument("handoff_manifest", type=Path, help="Path to *-training-discussion-handoff-manifest.json.")
    parser.add_argument("--allow-not-ready", action="store_true")
    parser.add_argument("--json", action="store_true", help="Print machine-readable validation result.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(list(argv) if argv is not None else None)
    result = validate_training_discussion_handoff_manifest(
        args.handoff_manifest,
        require_ready=not args.allow_not_ready,
    )
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    elif result["ok"]:
        print("PASS report quality training discussion handoff validated")
        print(f"ready_for_training_discussion={str(result['ready_for_training_discussion']).lower()}")
        print(f"handoff_file_count={result['handoff_file_count']}")
        print(f"require_ready={str(result['require_ready']).lower()}")
        print("training_boundary=not_authorized")
        for warning in result["warnings"]:
            print(f"WARN {warning}")
    else:
        print("FAIL report quality training discussion handoff validation failed")
        for error in result["errors"]:
            print(f"ERROR {error}")
        for warning in result["warnings"]:
            print(f"WARN {warning}")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
