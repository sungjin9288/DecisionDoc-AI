#!/usr/bin/env python3
"""Validate a persisted Report Quality review decision application receipt."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any, Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.services.report_quality_learning import validate_correction_artifact  # noqa: E402
from scripts.report_quality_pilot_pack_provenance import (  # noqa: E402
    PACK_BINDING_SCHEMA,
    load_pilot_pack,
    require_current_pack_binding,
)


RECEIPT_SCHEMA = "decisiondoc_report_quality_review_decision_application_receipt.v1"
NO_EXTERNAL_ACTION_KEYS = (
    "external_dataset_upload_started",
    "provider_fine_tune_api_called",
    "provider_job_created",
    "training_execution_started",
    "model_promotion_started",
)


def _read_json(path: Path) -> tuple[dict[str, Any], str]:
    if path.is_symlink():
        raise ValueError(f"{path}: symlink JSON files are not allowed")
    content = path.read_bytes()
    payload = json.loads(content.decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path}: JSON root must be an object")
    return payload, hashlib.sha256(content).hexdigest()


def _pack_local_path(pack_dir: Path, value: Any, *, field: str) -> Path:
    if not isinstance(value, str) or not value or Path(value).name != value:
        raise ValueError(f"{field} must be a pack-local filename")
    path = pack_dir / value
    if not path.is_file():
        raise ValueError(f"{field} does not exist: {path}")
    return path


def _binding_artifacts(binding: Any, *, field: str) -> list[dict[str, Any]]:
    if not isinstance(binding, dict):
        raise ValueError(f"{field} must be an object")
    if binding.get("schema_version") != PACK_BINDING_SCHEMA:
        raise ValueError(f"{field}.schema_version is unsupported")
    artifacts = binding.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        raise ValueError(f"{field}.artifacts must be a non-empty list")
    if any(
        not isinstance(item, dict)
        or not isinstance(item.get("artifact_id"), str)
        or not isinstance(item.get("draft_sha256"), str)
        or not re.fullmatch(r"[0-9a-f]{64}", item["draft_sha256"])
        for item in artifacts
    ):
        raise ValueError(f"{field}.artifacts entries are invalid")
    artifact_ids = [item["artifact_id"] for item in artifacts]
    if len(set(artifact_ids)) != len(artifact_ids):
        raise ValueError(f"{field}.artifacts must have unique artifact_id values")
    return artifacts


def _decision_items(decision_file: dict[str, Any]) -> list[dict[str, Any]]:
    decisions = decision_file.get("decisions")
    if not isinstance(decisions, list) or not decisions:
        raise ValueError("decision file must contain a non-empty decisions list")
    if any(not isinstance(item, dict) for item in decisions):
        raise ValueError("decision file decisions must be objects")
    artifact_ids = [str(item.get("artifact_id") or "") for item in decisions]
    if any(not artifact_id for artifact_id in artifact_ids) or len(set(artifact_ids)) != len(artifact_ids):
        raise ValueError("decision file artifact_id values must be non-empty and unique")
    return decisions


def validate_review_decision_receipt(receipt_path: Path) -> dict[str, Any]:
    expanded_receipt_path = receipt_path.expanduser()
    if expanded_receipt_path.is_symlink():
        raise ValueError("symlink receipt files are not allowed")
    resolved_receipt_path = expanded_receipt_path.resolve()
    receipt, receipt_sha256 = _read_json(resolved_receipt_path)
    if receipt.get("report_type") != "report_quality_review_decision_application_receipt":
        raise ValueError("receipt report_type is unsupported")
    if receipt.get("schema_version") != RECEIPT_SCHEMA:
        raise ValueError("receipt schema_version is unsupported")

    pack_dir = resolved_receipt_path.parent
    if receipt.get("receipt_path") != resolved_receipt_path.name:
        raise ValueError("receipt_path does not match the receipt filename")
    if receipt.get("pack_dir") != str(pack_dir):
        raise ValueError("pack_dir does not match the receipt directory")

    decision_record = receipt.get("decision_file")
    if not isinstance(decision_record, dict):
        raise ValueError("decision_file must be an object")
    decision_path = _pack_local_path(pack_dir, decision_record.get("path"), field="decision_file.path")
    decision_file, decision_sha256 = _read_json(decision_path)
    if decision_record.get("sha256") != decision_sha256:
        raise ValueError("decision_file.sha256 does not match the current decision file")

    before_binding = receipt.get("pack_binding_before")
    after_binding = receipt.get("pack_binding_after")
    before_artifacts = _binding_artifacts(before_binding, field="pack_binding_before")
    after_artifacts = _binding_artifacts(after_binding, field="pack_binding_after")
    if before_binding.get("pack_dir") != str(pack_dir) or after_binding.get("pack_dir") != str(pack_dir):
        raise ValueError("receipt pack bindings do not match the receipt directory")
    if before_binding.get("source_manifest") != after_binding.get("source_manifest"):
        raise ValueError("source manifest binding changed during decision application")

    binding_present = decision_record.get("pack_binding_present") is True
    decision_binding = decision_file.get("pack_binding")
    if binding_present != isinstance(decision_binding, dict):
        raise ValueError("decision_file.pack_binding_present does not match the decision file")
    if binding_present and decision_binding != before_binding:
        raise ValueError("decision file pack_binding does not match pack_binding_before")
    if after_binding.get("source_manifest") is not None and not binding_present:
        raise ValueError("source-bound receipt requires a bound decision file")

    current_snapshot = load_pilot_pack(pack_dir)
    require_current_pack_binding(current_snapshot, after_binding)

    decisions = _decision_items(decision_file)
    transitions = receipt.get("artifacts")
    if not isinstance(transitions, list) or any(not isinstance(item, dict) for item in transitions):
        raise ValueError("receipt artifacts must be a list of objects")
    decision_ids = [str(item.get("artifact_id") or "") for item in decisions]
    transition_ids = [str(item.get("artifact_id") or "") for item in transitions]
    if transition_ids != decision_ids:
        raise ValueError("receipt artifact order or membership does not match the decision file")

    before_hashes = {item["artifact_id"]: item["draft_sha256"] for item in before_artifacts}
    after_hashes = {item["artifact_id"]: item["draft_sha256"] for item in after_artifacts}
    current_drafts = {draft.artifact_id: draft for draft in current_snapshot.drafts}
    if any(artifact_id not in before_hashes or artifact_id not in after_hashes for artifact_id in decision_ids):
        raise ValueError("receipt decisions must reference artifacts in both pack bindings")
    for decision, transition in zip(decisions, transitions, strict=True):
        artifact_id = transition["artifact_id"]
        if not isinstance(transition.get("ready_for_learning"), bool):
            raise ValueError(f"{artifact_id}: ready_for_learning must be a boolean")
        current_validation = validate_correction_artifact(current_drafts[artifact_id].payload)
        if transition["ready_for_learning"] is not bool(current_validation.get("ready_for_learning")):
            raise ValueError(f"{artifact_id}: ready_for_learning does not match current validation")
        if transition.get("decision") != decision.get("decision"):
            raise ValueError(f"{artifact_id}: receipt decision does not match the decision file")
        if transition.get("before_draft_sha256") != before_hashes.get(artifact_id):
            raise ValueError(f"{artifact_id}: before draft SHA-256 does not match")
        if transition.get("after_draft_sha256") != after_hashes.get(artifact_id):
            raise ValueError(f"{artifact_id}: after draft SHA-256 does not match")
        expected_changed = before_hashes.get(artifact_id) != after_hashes.get(artifact_id)
        if transition.get("changed") is not expected_changed:
            raise ValueError(f"{artifact_id}: changed flag does not match the draft hashes")

    operation = receipt.get("operation")
    if not isinstance(operation, dict):
        raise ValueError("operation must be an object")
    if operation.get("ok") is not True or operation.get("dry_run") is not False:
        raise ValueError("operation must record a successful non-dry-run application")
    if operation.get("decision_count") != len(decisions) or operation.get("applied_count") != len(decisions):
        raise ValueError("operation counts do not match the decision file")
    if not isinstance(operation.get("require_ready"), bool):
        raise ValueError("operation.require_ready must be a boolean")
    if operation["require_ready"] and any(item.get("ready_for_learning") is not True for item in transitions):
        raise ValueError("require_ready receipt contains a non-ready artifact")

    boundary = receipt.get("side_effect_boundary")
    if not isinstance(boundary, dict):
        raise ValueError("side_effect_boundary must be an object")
    if boundary.get("writes_local_application_receipt") is not True:
        raise ValueError("receipt must record writes_local_application_receipt=true")
    if boundary.get("writes_local_draft_json") is not True:
        raise ValueError("receipt must record writes_local_draft_json=true")
    if any(boundary.get(key) is not False for key in NO_EXTERNAL_ACTION_KEYS):
        raise ValueError("receipt no-training side-effect boundary is invalid")

    return {
        "report_type": "report_quality_review_decision_application_receipt_validation",
        "ok": True,
        "receipt_path": str(resolved_receipt_path),
        "receipt_sha256": receipt_sha256,
        "pack_dir": str(pack_dir),
        "decision_path": str(decision_path),
        "decision_sha256": decision_sha256,
        "artifact_count": len(transitions),
        "source_bound": after_binding.get("source_manifest") is not None,
        "side_effect_boundary": {
            "reads_local_receipt": True,
            "reads_local_decision_json": True,
            "reads_local_draft_json": True,
            "writes_local_files": False,
            "external_dataset_upload_started": False,
            "provider_fine_tune_api_called": False,
            "provider_job_created": False,
            "training_execution_started": False,
            "model_promotion_started": False,
        },
    }


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("receipt_path", type=Path)
    parser.add_argument("--json", action="store_true", help="Print machine-readable validation output.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(list(argv) if argv is not None else None)
    try:
        result = validate_review_decision_receipt(args.receipt_path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR {exc}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print("PASS report quality review decision application receipt validated")
        print(f"receipt_path={result['receipt_path']}")
        print(f"artifact_count={result['artifact_count']}")
        print(f"source_bound={result['source_bound']}")
        print("training_boundary=not_authorized")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
