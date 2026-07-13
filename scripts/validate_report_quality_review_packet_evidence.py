#!/usr/bin/env python3
"""Validate local evidence generated from Report Workflow review packets."""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any, Sequence


EXPECTED_SCHEMA = "decisiondoc_report_quality_review_packet_evidence_pipeline.v1"
EXPECTED_OUTPUT_SCHEMAS = {
    "review_packet_manifest": "decisiondoc_report_quality_review_packet_batch_manifest.v1",
    "artifact_export_manifest": "decisiondoc_report_quality_review_packet_artifact_export.v1",
    "artifact_batch_manifest": "decisiondoc_report_quality_correction_batch_manifest.v1",
}
REQUIRED_OUTPUTS = (
    "review_packet_manifest",
    "review_packet_summary",
    "artifact_jsonl",
    "artifact_export_manifest",
    "artifact_batch_manifest",
    "artifact_batch_summary",
    "pipeline_manifest",
)
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


def _jsonl_identity(path: Path) -> dict[str, Any]:
    artifact_ids: list[str] = []
    tenant_ids: set[str] = set()
    for line_no, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not raw_line.strip():
            continue
        payload = json.loads(raw_line)
        if not isinstance(payload, dict):
            raise ValueError(f"line {line_no}: artifact root must be an object")
        artifact_id = str(payload.get("artifact_id") or "").strip()
        workflow = _as_dict(payload.get("workflow_reference"))
        tenant_id = str(workflow.get("tenant_id") or "").strip()
        if not artifact_id:
            raise ValueError(f"line {line_no}: artifact_id must be non-empty")
        if not tenant_id:
            raise ValueError(f"line {line_no}: workflow_reference.tenant_id must be non-empty")
        artifact_ids.append(artifact_id)
        tenant_ids.add(tenant_id)

    artifact_id_counts = Counter(artifact_ids)
    duplicate_artifact_ids = sorted(
        artifact_id
        for artifact_id, count in artifact_id_counts.items()
        if count > 1
    )
    return {
        "artifact_count": len(artifact_ids),
        "unique_artifact_count": len(set(artifact_ids)),
        "duplicate_artifact_ids": duplicate_artifact_ids,
        "tenant_count": len(tenant_ids),
        "single_tenant": len(tenant_ids) == 1,
    }


def _resolve_output(path_value: Any, *, field: str, errors: list[str]) -> Path | None:
    if not isinstance(path_value, str) or not path_value.strip():
        errors.append(f"outputs.{field} must be a non-empty path")
        return None
    path = Path(path_value).expanduser().resolve()
    if not path.exists():
        errors.append(f"outputs.{field} does not exist: {path}")
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


def _stage_ready(stage_name: str, manifest: dict[str, Any], *, require_ready: bool, errors: list[str]) -> None:
    readiness = _as_dict(manifest.get("readiness"))
    if require_ready and readiness.get("ok") is not True:
        errors.append(f"{stage_name}.readiness.ok must be true")


def validate_review_packet_evidence_manifest(
    manifest_path: Path,
    *,
    require_ready: bool = True,
) -> dict[str, Any]:
    resolved_manifest_path = manifest_path.expanduser().resolve()
    errors: list[str] = []
    warnings: list[str] = []
    try:
        manifest = _load_json(resolved_manifest_path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return {
            "report_type": "report_quality_review_packet_evidence_validation",
            "ok": False,
            "require_ready": require_ready,
            "manifest_path": str(resolved_manifest_path),
            "errors": [str(exc)],
            "warnings": [],
        }

    if manifest.get("schema_version") != EXPECTED_SCHEMA:
        errors.append(f"schema_version must be {EXPECTED_SCHEMA!r}")

    outputs = _as_dict(manifest.get("outputs"))
    output_paths: dict[str, Path] = {}
    for key in REQUIRED_OUTPUTS:
        resolved = _resolve_output(outputs.get(key), field=key, errors=errors)
        if resolved is not None:
            output_paths[key] = resolved

    if "pipeline_manifest" in output_paths and output_paths["pipeline_manifest"] != resolved_manifest_path:
        warnings.append("outputs.pipeline_manifest points to a different path than the validated manifest")

    loaded_outputs: dict[str, dict[str, Any]] = {}
    for key, expected_schema in EXPECTED_OUTPUT_SCHEMAS.items():
        path = output_paths.get(key)
        if path is None:
            continue
        try:
            loaded = _load_json(path)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            errors.append(f"{key}: {exc}")
            continue
        loaded_outputs[key] = loaded
        if loaded.get("schema_version") != expected_schema:
            errors.append(f"{key}.schema_version must be {expected_schema!r}")
        _stage_ready(key, loaded, require_ready=require_ready, errors=errors)

    _stage_ready("pipeline", manifest, require_ready=require_ready, errors=errors)

    for finding in _scan_forbidden_true(manifest):
        errors.append(f"pipeline_manifest: {finding}")
    for key, loaded in loaded_outputs.items():
        for finding in _scan_forbidden_true(loaded):
            errors.append(f"{key}: {finding}")

    artifact_jsonl = output_paths.get("artifact_jsonl")
    artifact_export = loaded_outputs.get("artifact_export_manifest") or {}
    artifact_batch = loaded_outputs.get("artifact_batch_manifest") or {}
    artifact_identity: dict[str, Any] | None = None
    if artifact_jsonl is not None:
        actual_hash = _sha256(artifact_jsonl)
        export_hash = _as_dict(artifact_export.get("output")).get("jsonl_sha256")
        batch_hash = _as_dict(artifact_batch.get("source")).get("jsonl_sha256")
        if export_hash and export_hash != actual_hash:
            errors.append("artifact_export_manifest.output.jsonl_sha256 does not match artifact_jsonl")
        if batch_hash and batch_hash != actual_hash:
            errors.append("artifact_batch_manifest.source.jsonl_sha256 does not match artifact_jsonl")
        try:
            artifact_identity = _jsonl_identity(artifact_jsonl)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            errors.append(f"artifact_jsonl identity validation failed: {exc}")

    pipeline_counts = _as_dict(manifest.get("counts"))
    packet_counts = _as_dict((loaded_outputs.get("review_packet_manifest") or {}).get("counts"))
    export_counts = _as_dict((loaded_outputs.get("artifact_export_manifest") or {}).get("counts"))
    artifact_counts = _as_dict((loaded_outputs.get("artifact_batch_manifest") or {}).get("counts"))
    if packet_counts and pipeline_counts.get("packet_count") != packet_counts.get("packet_count"):
        errors.append("pipeline counts.packet_count must match review packet manifest")
    if export_counts and pipeline_counts.get("exported_artifacts") != export_counts.get("exported_artifacts"):
        errors.append("pipeline counts.exported_artifacts must match artifact export manifest")
    if artifact_counts and pipeline_counts.get("ready_artifacts") != artifact_counts.get("ready_artifacts"):
        errors.append("pipeline counts.ready_artifacts must match artifact batch manifest")

    if artifact_identity is not None:
        for key in ("artifact_count", "unique_artifact_count", "tenant_count"):
            if key in artifact_counts and artifact_counts.get(key) != artifact_identity[key]:
                errors.append(f"artifact_batch_manifest.counts.{key} does not match artifact_jsonl")

        artifact_integrity = _as_dict(artifact_batch.get("integrity"))
        expected_integrity = {
            "unique_artifact_ids": not artifact_identity["duplicate_artifact_ids"],
            "duplicate_artifact_ids": artifact_identity["duplicate_artifact_ids"],
            "single_tenant": artifact_identity["single_tenant"],
        }
        for key, expected in expected_integrity.items():
            if key in artifact_integrity and artifact_integrity.get(key) != expected:
                errors.append(f"artifact_batch_manifest.integrity.{key} does not match artifact_jsonl")

        if require_ready and artifact_identity["duplicate_artifact_ids"]:
            errors.append("artifact_jsonl must have unique artifact_id values")
        if require_ready and not artifact_identity["single_tenant"]:
            errors.append("artifact_jsonl must contain exactly one tenant_id")

    return {
        "report_type": "report_quality_review_packet_evidence_validation",
        "ok": not errors,
        "require_ready": require_ready,
        "manifest_path": str(resolved_manifest_path),
        "schema_version": manifest.get("schema_version"),
        "readiness": manifest.get("readiness"),
        "output_count": len(output_paths),
        "validated_outputs": sorted(loaded_outputs),
        "errors": errors,
        "warnings": warnings,
    }


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate a local review packet evidence pipeline manifest.")
    parser.add_argument("manifest", type=Path, help="Path to *-evidence-pipeline-manifest.json")
    parser.add_argument("--allow-not-ready", action="store_true")
    parser.add_argument("--json", action="store_true", help="Print machine-readable validation result.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(list(argv) if argv is not None else None)
    result = validate_review_packet_evidence_manifest(
        args.manifest,
        require_ready=not args.allow_not_ready,
    )
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    elif result["ok"]:
        print("PASS report quality review packet evidence validated")
        print(f"output_count={result['output_count']}")
        print(f"require_ready={str(result['require_ready']).lower()}")
        for warning in result["warnings"]:
            print(f"WARN {warning}")
    else:
        print("FAIL report quality review packet evidence validation failed")
        for error in result["errors"]:
            print(f"ERROR {error}")
        for warning in result["warnings"]:
            print(f"WARN {warning}")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
