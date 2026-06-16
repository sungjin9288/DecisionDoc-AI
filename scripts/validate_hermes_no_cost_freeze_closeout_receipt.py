#!/usr/bin/env python3
"""Validate the Hermes no-cost freeze closeout receipt."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.check_hermes_no_cost_freeze_gate import check_hermes_no_cost_freeze_gate  # noqa: E402


DEFAULT_RECEIPT_PATH = (
    REPO_ROOT
    / "docs/specs/hermes_decisiondoc_agent/phase45_no_cost_freeze_closeout_receipt/no_cost_freeze_closeout_receipt.json"
)
EXPECTED_REPORT_TYPE = "document_ops_phase45_no_cost_freeze_closeout_receipt"
EXPECTED_VALIDATION_REPORT_TYPE = "document_ops_phase45_no_cost_freeze_closeout_receipt_validation"
EXPECTED_STATUS = "no_cost_freeze_closeout_receipt_recorded_no_aws_no_training_authorization"
REQUIRED_SOURCE_HASH_PATHS = {
    "handoff_manifest_sha256": "docs/specs/hermes_decisiondoc_agent/phase20_release_handoff/handoff_manifest.json",
    "phase43_evidence_sha256": "docs/specs/hermes_decisiondoc_agent/phase43_local_export_openability_evidence/local_export_openability_evidence.json",
    "phase44_gate_guide_sha256": "docs/specs/hermes_decisiondoc_agent/phase44_no_cost_freeze_gate/NO_COST_FREEZE_GATE.md",
    "phase44_gate_checker_sha256": "scripts/check_hermes_no_cost_freeze_gate.py",
}
REQUIRED_CLOSEOUT_TRUE_FIELDS = (
    "no_cost_freeze_gate_valid",
    "release_handoff_valid",
    "local_export_openability_valid",
    "service_freeze_preserved",
    "resume_requires_separate_approval",
)
REQUIRED_CLOSEOUT_FALSE_FIELDS = (
    "service_resume_authorized",
    "production_ui_called",
    "aws_runtime_called",
    "aws_cost_increase_allowed",
    "external_dataset_upload_authorized",
    "provider_fine_tune_api_called",
    "provider_job_creation_authorized",
    "provider_job_polling_authorized",
    "training_execution_authorized",
    "model_candidate_emission_authorized",
    "model_promotion_authorized",
)


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path}: JSON root must be an object")
    return payload


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_hermes_no_cost_freeze_closeout_receipt(receipt_path: Path = DEFAULT_RECEIPT_PATH) -> dict[str, Any]:
    resolved_receipt = receipt_path.expanduser().resolve()
    errors: list[str] = []
    warnings: list[str] = []
    try:
        receipt = _load_json(resolved_receipt)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return {
            "report_type": EXPECTED_VALIDATION_REPORT_TYPE,
            "ok": False,
            "receipt_path": str(resolved_receipt),
            "errors": [str(exc)],
            "warnings": [],
        }

    if receipt.get("report_type") != EXPECTED_REPORT_TYPE:
        errors.append(f"report_type must be {EXPECTED_REPORT_TYPE}")
    if receipt.get("phase") != 45:
        errors.append("phase must be 45")
    if receipt.get("status") != EXPECTED_STATUS:
        errors.append(f"status must be {EXPECTED_STATUS}")
    if receipt.get("operator_decision") != "keep_service_frozen":
        errors.append("operator_decision must be keep_service_frozen")

    source_gate = _as_dict(receipt.get("source_gate"))
    if source_gate.get("command") != "python3 scripts/check_hermes_no_cost_freeze_gate.py":
        errors.append("source_gate.command must be python3 scripts/check_hermes_no_cost_freeze_gate.py")
    if source_gate.get("result") != "pass":
        errors.append("source_gate.result must be pass")
    if source_gate.get("service_operation_state") != "freeze_recommended":
        errors.append("source_gate.service_operation_state must be freeze_recommended")

    closeout = _as_dict(receipt.get("closeout_boundary"))
    for field in REQUIRED_CLOSEOUT_TRUE_FIELDS:
        if closeout.get(field) is not True:
            errors.append(f"closeout_boundary.{field} must be true")
    for field in REQUIRED_CLOSEOUT_FALSE_FIELDS:
        if closeout.get(field) is not False:
            errors.append(f"closeout_boundary.{field} must be false")
    if closeout.get("aws_cost_boundary") != "no_cost_increase":
        errors.append("closeout_boundary.aws_cost_boundary must be no_cost_increase")
    if closeout.get("training_boundary") != "not_authorized":
        errors.append("closeout_boundary.training_boundary must be not_authorized")

    source_hashes = _as_dict(receipt.get("source_hashes"))
    for hash_key, relative_path in REQUIRED_SOURCE_HASH_PATHS.items():
        path = REPO_ROOT / relative_path
        if not path.exists():
            errors.append(f"source_hashes.{hash_key} source path must exist: {relative_path}")
            continue
        expected_hash = _sha256_file(path)
        if source_hashes.get(hash_key) != expected_hash:
            errors.append(f"source_hashes.{hash_key} must match {relative_path}")

    gate_result = check_hermes_no_cost_freeze_gate()
    if gate_result.get("ok") is not True:
        errors.append("source_gate must still pass check_hermes_no_cost_freeze_gate.py")
        for error in gate_result.get("errors", []):
            errors.append(f"source_gate: {error}")

    return {
        "report_type": EXPECTED_VALIDATION_REPORT_TYPE,
        "ok": not errors,
        "receipt_path": str(resolved_receipt),
        "closeout_receipt_valid": not errors,
        "service_operation_state": "freeze_preserved",
        "aws_cost_boundary": closeout.get("aws_cost_boundary", ""),
        "training_boundary": closeout.get("training_boundary", ""),
        "errors": errors,
        "warnings": warnings,
    }


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate the Hermes no-cost freeze closeout receipt.")
    parser.add_argument(
        "receipt",
        nargs="?",
        type=Path,
        default=DEFAULT_RECEIPT_PATH,
        help="Path to no_cost_freeze_closeout_receipt.json.",
    )
    parser.add_argument("--json", action="store_true", help="Print machine-readable validation result.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(list(argv) if argv is not None else None)
    result = validate_hermes_no_cost_freeze_closeout_receipt(args.receipt)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    elif result["ok"]:
        print("PASS hermes no-cost freeze closeout receipt validated")
        print(f"closeout_receipt_valid={str(result['closeout_receipt_valid']).lower()}")
        print(f"service_operation_state={result['service_operation_state']}")
        print(f"aws_cost_boundary={result['aws_cost_boundary']}")
        print(f"training_boundary={result['training_boundary']}")
        for warning in result["warnings"]:
            print(f"WARN {warning}")
    else:
        print("FAIL hermes no-cost freeze closeout receipt validation failed")
        for error in result["errors"]:
            print(f"ERROR {error}")
        for warning in result["warnings"]:
            print(f"WARN {warning}")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
