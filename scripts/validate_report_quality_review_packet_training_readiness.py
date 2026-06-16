#!/usr/bin/env python3
"""Validate a local report quality review packet training-discussion readiness manifest."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
from typing import Any, Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_VALIDATOR_PATH = REPO_ROOT / "scripts/validate_report_quality_review_packet_evidence.py"
EXPECTED_SCHEMA = "decisiondoc_report_quality_review_packet_training_readiness.v1"
EXPECTED_SIGNOFF_SUMMARY_SCHEMA = "decisiondoc_report_quality_review_packet_signoff_summary.v1"
FORBIDDEN_TRUE_KEYS = {
    "actual_reviewer_approval_recorded",
    "actual_reviewer_approval_recorded_by_summary",
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


def _load_evidence_validator():
    spec = importlib.util.spec_from_file_location(
        "validate_report_quality_review_packet_evidence",
        EVIDENCE_VALIDATOR_PATH,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed to load evidence validator: {EVIDENCE_VALIDATOR_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_EVIDENCE_VALIDATOR = _load_evidence_validator()


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


def _resolve_input_path(path_value: Any, *, field: str, errors: list[str]) -> Path | None:
    if not isinstance(path_value, str) or not path_value.strip():
        errors.append(f"inputs.{field} must be a non-empty path")
        return None
    path = Path(path_value).expanduser().resolve()
    if not path.exists():
        errors.append(f"inputs.{field} does not exist: {path}")
        return None
    return path


def _validate_hash(
    *,
    path: Path | None,
    expected_hash: Any,
    field: str,
    errors: list[str],
) -> None:
    if path is None:
        return
    if not isinstance(expected_hash, str) or not expected_hash.strip():
        errors.append(f"inputs.{field} must be non-empty")
        return
    if expected_hash != _sha256(path):
        errors.append(f"inputs.{field} does not match referenced file")


def _validate_signoff_summary(
    summary: dict[str, Any],
    *,
    require_ready: bool,
    errors: list[str],
) -> None:
    if summary.get("schema_version") != EXPECTED_SIGNOFF_SUMMARY_SCHEMA:
        errors.append(f"signoff_summary.schema_version must be {EXPECTED_SIGNOFF_SUMMARY_SCHEMA!r}")
    if summary.get("read_only") is not True:
        errors.append("signoff_summary.read_only must be true")
    if require_ready and summary.get("ok") is not True:
        errors.append("signoff_summary.ok must be true")

    readiness = _as_dict(summary.get("readiness"))
    counts = _as_dict(summary.get("counts"))
    if require_ready and readiness.get("require_complete_ok") is not True:
        errors.append("signoff_summary.readiness.require_complete_ok must be true")
    if require_ready and counts.get("completed_record_count") != counts.get("record_count"):
        errors.append("signoff_summary completed_record_count must equal record_count")
    if counts.get("invalid_record_count", 0) != 0:
        errors.append("signoff_summary.counts.invalid_record_count must be 0")
    if counts.get("record_count", 0) < 1:
        errors.append("signoff_summary.counts.record_count must be at least 1")

    for record in _as_list(summary.get("records")):
        record_dict = _as_dict(record)
        signoff_id = record_dict.get("signoff_id", "-")
        if require_ready and record_dict.get("completed") is not True:
            errors.append(f"signoff record {signoff_id} must be completed")
        if record_dict.get("boundary_ok") is not True:
            errors.append(f"signoff record {signoff_id} boundary_ok must be true")
        if require_ready and record_dict.get("handoff_validation_ok") is not True:
            errors.append(f"signoff record {signoff_id} handoff_validation_ok must be true")

    for finding in _scan_forbidden_true(summary):
        errors.append(f"signoff_summary: {finding}")


def validate_training_readiness_manifest(
    readiness_manifest_path: Path,
    *,
    require_ready: bool = True,
) -> dict[str, Any]:
    resolved_manifest = readiness_manifest_path.expanduser().resolve()
    errors: list[str] = []
    warnings: list[str] = []
    try:
        manifest = _load_json(resolved_manifest)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return {
            "report_type": "report_quality_review_packet_training_readiness_validation",
            "ok": False,
            "require_ready": require_ready,
            "readiness_manifest_path": str(resolved_manifest),
            "errors": [str(exc)],
            "warnings": [],
        }

    if manifest.get("schema_version") != EXPECTED_SCHEMA:
        errors.append(f"schema_version must be {EXPECTED_SCHEMA!r}")

    readiness = _as_dict(manifest.get("readiness"))
    if require_ready and readiness.get("ok") is not True:
        errors.append("readiness.ok must be true")
    if require_ready and readiness.get("ready_for_training_discussion") is not True:
        errors.append("readiness.ready_for_training_discussion must be true")

    inputs = _as_dict(manifest.get("inputs"))
    evidence_path = _resolve_input_path(
        inputs.get("evidence_manifest_path"),
        field="evidence_manifest_path",
        errors=errors,
    )
    signoff_summary_path = _resolve_input_path(
        inputs.get("signoff_summary_path"),
        field="signoff_summary_path",
        errors=errors,
    )
    _validate_hash(
        path=evidence_path,
        expected_hash=inputs.get("evidence_manifest_sha256"),
        field="evidence_manifest_sha256",
        errors=errors,
    )
    _validate_hash(
        path=signoff_summary_path,
        expected_hash=inputs.get("signoff_summary_sha256"),
        field="signoff_summary_sha256",
        errors=errors,
    )

    evidence_validation: dict[str, Any] = {}
    evidence_manifest: dict[str, Any] = {}
    if evidence_path is not None:
        evidence_validation = _EVIDENCE_VALIDATOR.validate_review_packet_evidence_manifest(
            evidence_path,
            require_ready=True,
        )
        if require_ready and evidence_validation.get("ok") is not True:
            errors.append("evidence pipeline validation must pass")
        try:
            evidence_manifest = _load_json(evidence_path)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            errors.append(f"failed to load evidence manifest: {exc}")

    signoff_summary: dict[str, Any] = {}
    if signoff_summary_path is not None:
        try:
            signoff_summary = _load_json(signoff_summary_path)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            errors.append(f"failed to load signoff summary: {exc}")
        else:
            _validate_signoff_summary(signoff_summary, require_ready=require_ready, errors=errors)

    requirements = _as_dict(manifest.get("requirements"))
    counts = _as_dict(manifest.get("counts"))
    min_ready_artifacts = int(requirements.get("min_ready_artifacts") or 0)
    if require_ready and requirements.get("require_completed_signoffs") is not True:
        errors.append("requirements.require_completed_signoffs must be true")
    if int(counts.get("ready_artifacts") or 0) < min_ready_artifacts:
        errors.append("counts.ready_artifacts must meet requirements.min_ready_artifacts")

    evidence_counts = _as_dict(evidence_manifest.get("counts"))
    signoff_counts = _as_dict(signoff_summary.get("counts"))
    if evidence_counts:
        for key in ("packet_count", "ready_packets", "exported_artifacts", "ready_artifacts"):
            if counts.get(key) != evidence_counts.get(key):
                errors.append(f"counts.{key} must match evidence manifest")
    if signoff_counts:
        expected_map = {
            "signoff_record_count": "record_count",
            "completed_signoff_count": "completed_record_count",
            "pending_signoff_count": "pending_record_count",
            "invalid_signoff_count": "invalid_record_count",
        }
        for target_key, source_key in expected_map.items():
            if counts.get(target_key) != signoff_counts.get(source_key):
                errors.append(f"counts.{target_key} must match signoff summary")

    validation_block = _as_dict(manifest.get("validations"))
    if require_ready and _as_dict(validation_block.get("evidence_pipeline")).get("ok") is not True:
        errors.append("validations.evidence_pipeline.ok must be true")
    if require_ready and validation_block.get("signoff_summary_ok") is not True:
        errors.append("validations.signoff_summary_ok must be true")
    if require_ready and validation_block.get("signoff_summary_require_complete_ok") is not True:
        errors.append("validations.signoff_summary_require_complete_ok must be true")

    for finding in _scan_forbidden_true(manifest):
        errors.append(f"training_readiness_manifest: {finding}")

    return {
        "report_type": "report_quality_review_packet_training_readiness_validation",
        "ok": not errors,
        "require_ready": require_ready,
        "readiness_manifest_path": str(resolved_manifest),
        "schema_version": manifest.get("schema_version"),
        "ready_for_training_discussion": readiness.get("ready_for_training_discussion") is True,
        "counts": counts,
        "evidence_validation_ok": evidence_validation.get("ok") if evidence_validation else None,
        "signoff_summary_ok": signoff_summary.get("ok") if signoff_summary else None,
        "errors": errors,
        "warnings": warnings,
    }


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate a report quality training-discussion readiness manifest.")
    parser.add_argument("readiness_manifest", type=Path, help="Path to *-training-readiness-manifest.json.")
    parser.add_argument("--allow-not-ready", action="store_true")
    parser.add_argument("--json", action="store_true", help="Print machine-readable validation result.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(list(argv) if argv is not None else None)
    result = validate_training_readiness_manifest(
        args.readiness_manifest,
        require_ready=not args.allow_not_ready,
    )
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    elif result["ok"]:
        print("PASS report quality review packet training readiness validated")
        print(f"ready_for_training_discussion={str(result['ready_for_training_discussion']).lower()}")
        print(f"require_ready={str(result['require_ready']).lower()}")
        for warning in result["warnings"]:
            print(f"WARN {warning}")
    else:
        print("FAIL report quality review packet training readiness validation failed")
        for error in result["errors"]:
            print(f"ERROR {error}")
        for warning in result["warnings"]:
            print(f"WARN {warning}")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
