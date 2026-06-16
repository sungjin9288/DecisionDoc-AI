#!/usr/bin/env python3
"""Validate a local Report Workflow review packet handoff manifest."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
from typing import Any, Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_VALIDATOR_PATH = REPO_ROOT / "scripts/validate_report_quality_review_packet_evidence.py"
EXPECTED_SCHEMA = "decisiondoc_report_quality_review_packet_handoff.v1"
FORBIDDEN_TRUE_KEYS = {
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
    if not path.exists():
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


def validate_review_packet_handoff_manifest(
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
            "report_type": "report_quality_review_packet_handoff_validation",
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

    pipeline_path = _resolve_path(
        handoff.get("pipeline_manifest_path"),
        field="pipeline_manifest_path",
        errors=errors,
    )
    evidence_validation: dict[str, Any] = {}
    if pipeline_path is not None:
        evidence_validation = _EVIDENCE_VALIDATOR.validate_review_packet_evidence_manifest(
            pipeline_path,
            require_ready=require_ready,
        )
        if require_ready and evidence_validation.get("ok") is not True:
            errors.append("pipeline evidence validation must pass")
        expected_hash = handoff.get("pipeline_manifest_sha256")
        if expected_hash and expected_hash != _sha256(pipeline_path):
            errors.append("pipeline_manifest_sha256 does not match pipeline_manifest_path")

    handoff_index_path = _resolve_path(
        handoff.get("handoff_index_path"),
        field="handoff_index_path",
        errors=errors,
    )
    if handoff_index_path is not None:
        index_text = handoff_index_path.read_text(encoding="utf-8")
        if "Report Quality Review Packet Handoff" not in index_text:
            errors.append("handoff index is missing title")
        if "training_authorized: `false`" not in index_text:
            errors.append("handoff index must show training_authorized=false")

    readiness = _as_dict(handoff.get("readiness"))
    if require_ready and readiness.get("ok") is not True:
        errors.append("handoff readiness.ok must be true")

    validation = _as_dict(handoff.get("validation"))
    if require_ready and validation.get("ok") is not True:
        errors.append("embedded evidence validation.ok must be true")

    handoff_files = _as_dict(handoff.get("handoff_files"))
    for name, record_value in handoff_files.items():
        record = _as_dict(record_value)
        path = _resolve_path(record.get("path"), field=f"handoff_files.{name}.path", errors=errors)
        if record.get("exists") is not True:
            errors.append(f"handoff_files.{name}.exists must be true")
        if path is not None and record.get("sha256") and record.get("sha256") != _sha256(path):
            errors.append(f"handoff_files.{name}.sha256 does not match file")

    reviewer_actions = handoff.get("reviewer_actions")
    if not isinstance(reviewer_actions, list) or len(reviewer_actions) < 3:
        errors.append("reviewer_actions must include at least three actions")
    elif not any("Do not start provider fine-tune" in str(item) for item in reviewer_actions):
        errors.append("reviewer_actions must explicitly prohibit provider fine-tune")

    for finding in _scan_forbidden_true(handoff):
        errors.append(f"handoff_manifest: {finding}")

    counts = _as_dict(handoff.get("counts"))
    evidence_counts = _as_dict(evidence_validation.get("readiness"))
    if require_ready and evidence_counts.get("ok") is False:
        errors.append("evidence readiness embedded in handoff must be ok")
    if require_ready and counts.get("ready_artifacts", 0) < 1:
        errors.append("ready_artifacts must be at least 1")

    return {
        "report_type": "report_quality_review_packet_handoff_validation",
        "ok": not errors,
        "require_ready": require_ready,
        "handoff_manifest_path": str(resolved_handoff_manifest),
        "schema_version": handoff.get("schema_version"),
        "pipeline_manifest_path": str(pipeline_path) if pipeline_path is not None else "",
        "handoff_index_path": str(handoff_index_path) if handoff_index_path is not None else "",
        "handoff_file_count": len(handoff_files),
        "readiness": readiness,
        "errors": errors,
        "warnings": warnings,
    }


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate a local review packet handoff manifest.")
    parser.add_argument("handoff_manifest", type=Path, help="Path to *-handoff-manifest.json")
    parser.add_argument("--allow-not-ready", action="store_true")
    parser.add_argument("--json", action="store_true", help="Print machine-readable validation result.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(list(argv) if argv is not None else None)
    result = validate_review_packet_handoff_manifest(
        args.handoff_manifest,
        require_ready=not args.allow_not_ready,
    )
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    elif result["ok"]:
        print("PASS report quality review packet handoff validated")
        print(f"handoff_file_count={result['handoff_file_count']}")
        print(f"require_ready={str(result['require_ready']).lower()}")
        for warning in result["warnings"]:
            print(f"WARN {warning}")
    else:
        print("FAIL report quality review packet handoff validation failed")
        for error in result["errors"]:
            print(f"ERROR {error}")
        for warning in result["warnings"]:
            print(f"WARN {warning}")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
