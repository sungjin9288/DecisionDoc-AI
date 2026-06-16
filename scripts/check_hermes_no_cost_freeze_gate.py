#!/usr/bin/env python3
"""Compose the Hermes/DecisionDoc no-cost freeze validators."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.validate_phase20_release_handoff_manifest import (  # noqa: E402
    validate_phase20_release_handoff_manifest,
)
from scripts.validate_phase43_local_export_openability_evidence import (  # noqa: E402
    validate_phase43_local_export_openability_evidence,
)


DEFAULT_MANIFEST_PATH = (
    REPO_ROOT
    / "docs/specs/hermes_decisiondoc_agent/phase20_release_handoff/handoff_manifest.json"
)
DEFAULT_PHASE43_EVIDENCE_PATH = (
    REPO_ROOT
    / "docs/specs/hermes_decisiondoc_agent/phase43_local_export_openability_evidence/local_export_openability_evidence.json"
)
EXPECTED_REPORT_TYPE = "document_ops_phase44_no_cost_freeze_gate"
EXPECTED_HANDOFF_STATUS = "no_cost_freeze_closeout_summary_validated_no_aws_no_training_authorization"
EXPECTED_PHASE43_STATUS = "local_export_openability_passed_no_aws_no_training_authorization"
RESTRICTED_FALSE_FIELDS = (
    "training_execution_authorized",
    "external_dataset_upload_authorized",
    "server_side_export_artifact_write_authorized",
    "provider_fine_tune_api_call_authorized",
    "provider_job_creation_authorized",
    "provider_job_polling_authorized",
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


def _append_prefixed_errors(errors: list[str], prefix: str, result: dict[str, Any]) -> None:
    for error in result.get("errors", []):
        errors.append(f"{prefix}: {error}")


def check_hermes_no_cost_freeze_gate(
    manifest_path: Path = DEFAULT_MANIFEST_PATH,
    phase43_evidence_path: Path = DEFAULT_PHASE43_EVIDENCE_PATH,
) -> dict[str, Any]:
    resolved_manifest = manifest_path.expanduser().resolve()
    resolved_evidence = phase43_evidence_path.expanduser().resolve()
    errors: list[str] = []
    warnings: list[str] = []

    handoff_result = validate_phase20_release_handoff_manifest(resolved_manifest)
    phase43_result = validate_phase43_local_export_openability_evidence(resolved_evidence)
    if not handoff_result.get("ok"):
        _append_prefixed_errors(errors, "handoff_manifest", handoff_result)
    if not phase43_result.get("ok"):
        _append_prefixed_errors(errors, "phase43_evidence", phase43_result)

    try:
        manifest = _load_json(resolved_manifest)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        manifest = {}
        errors.append(f"handoff_manifest: {exc}")
    try:
        phase43_evidence = _load_json(resolved_evidence)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        phase43_evidence = {}
        errors.append(f"phase43_evidence: {exc}")

    if manifest.get("status") != EXPECTED_HANDOFF_STATUS:
        errors.append(f"handoff_manifest.status must be {EXPECTED_HANDOFF_STATUS}")
    if manifest.get("recommended_decision") != EXPECTED_HANDOFF_STATUS:
        errors.append(f"handoff_manifest.recommended_decision must be {EXPECTED_HANDOFF_STATUS}")
    if phase43_evidence.get("status") != EXPECTED_PHASE43_STATUS:
        errors.append(f"phase43_evidence.status must be {EXPECTED_PHASE43_STATUS}")

    release_boundary = _as_dict(manifest.get("release_boundary"))
    for field in RESTRICTED_FALSE_FIELDS:
        if release_boundary.get(field) is not False:
            errors.append(f"handoff_manifest.release_boundary.{field} must be false")
    if release_boundary.get("phase44_no_cost_freeze_gate_completed") is not True:
        errors.append("handoff_manifest.release_boundary.phase44_no_cost_freeze_gate_completed must be true")

    phase_coverage = _as_dict(manifest.get("phase_coverage"))
    phase44 = _as_dict(phase_coverage.get("phase44"))
    if phase44.get("result") != "pass_no_cost_freeze_gate":
        errors.append("handoff_manifest.phase_coverage.phase44.result must be pass_no_cost_freeze_gate")
    for field in (
        "release_handoff_validator_passed",
        "local_export_openability_validator_passed",
        "service_freeze_recommended",
        "resume_requires_separate_approval",
    ):
        if phase44.get(field) is not True:
            errors.append(f"handoff_manifest.phase_coverage.phase44.{field} must be true")
    for field in (
        "production_ui_called",
        "aws_runtime_called",
        "aws_cost_increase_allowed",
        "training_authorized",
        "external_dataset_upload_authorized",
        "provider_fine_tune_api_called",
        "provider_job_creation_authorized",
        "model_promotion_authorized",
    ):
        if phase44.get(field) is not False:
            errors.append(f"handoff_manifest.phase_coverage.phase44.{field} must be false")

    no_cost_freeze_gate_valid = not errors
    return {
        "report_type": EXPECTED_REPORT_TYPE,
        "ok": no_cost_freeze_gate_valid,
        "manifest_path": str(resolved_manifest),
        "phase43_evidence_path": str(resolved_evidence),
        "no_cost_freeze_gate_valid": no_cost_freeze_gate_valid,
        "release_handoff_valid": handoff_result.get("ok") is True,
        "local_export_openability_valid": phase43_result.get("ok") is True,
        "service_operation_state": "freeze_recommended",
        "aws_cost_boundary": "no_cost_increase",
        "training_boundary": "not_authorized",
        "resume_requires_separate_approval": True,
        "external_side_effects_authorized": False,
        "errors": errors,
        "warnings": warnings,
    }


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Check the Hermes/DecisionDoc no-cost freeze gate.")
    parser.add_argument(
        "--manifest",
        type=Path,
        default=DEFAULT_MANIFEST_PATH,
        help="Path to phase20_release_handoff/handoff_manifest.json.",
    )
    parser.add_argument(
        "--phase43-evidence",
        type=Path,
        default=DEFAULT_PHASE43_EVIDENCE_PATH,
        help="Path to phase43 local_export_openability_evidence.json.",
    )
    parser.add_argument("--json", action="store_true", help="Print machine-readable validation result.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(list(argv) if argv is not None else None)
    result = check_hermes_no_cost_freeze_gate(args.manifest, args.phase43_evidence)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    elif result["ok"]:
        print("PASS hermes no-cost freeze gate validated")
        print(f"no_cost_freeze_gate_valid={str(result['no_cost_freeze_gate_valid']).lower()}")
        print(f"release_handoff_valid={str(result['release_handoff_valid']).lower()}")
        print(f"local_export_openability_valid={str(result['local_export_openability_valid']).lower()}")
        print(f"service_operation_state={result['service_operation_state']}")
        print(f"aws_cost_boundary={result['aws_cost_boundary']}")
        print(f"training_boundary={result['training_boundary']}")
        for warning in result["warnings"]:
            print(f"WARN {warning}")
    else:
        print("FAIL hermes no-cost freeze gate validation failed")
        for error in result["errors"]:
            print(f"ERROR {error}")
        for warning in result["warnings"]:
            print(f"WARN {warning}")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
