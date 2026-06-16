#!/usr/bin/env python3
"""Validate a human sign-off record for a report quality review packet handoff."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
from typing import Any, Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
HANDOFF_VALIDATOR_PATH = REPO_ROOT / "scripts/validate_report_quality_review_packet_handoff.py"
EXPECTED_SCHEMA = "decisiondoc_report_quality_review_packet_signoff.v1"
VALID_DECISIONS = {"pending", "accepted", "changes_requested", "rejected"}
COMPLETED_DECISIONS = {"accepted", "changes_requested", "rejected"}
REQUIRED_ACKS = (
    "review_packet_summary_checked",
    "artifact_batch_summary_checked",
    "pipeline_manifest_validated",
    "artifact_jsonl_validated",
    "no_training_authorized",
    "no_dataset_upload_authorized",
    "no_provider_fine_tune_authorized",
    "no_model_promotion_authorized",
)
FORBIDDEN_BOUNDARY_KEYS = (
    "server_file_written",
    "persisted_learning_artifact",
    "external_dataset_upload_authorized",
    "provider_fine_tune_api_call_authorized",
    "provider_job_creation_authorized",
    "training_execution_authorized",
    "model_promotion_authorized",
)


def _load_handoff_validator():
    spec = importlib.util.spec_from_file_location(
        "validate_report_quality_review_packet_handoff",
        HANDOFF_VALIDATOR_PATH,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed to load handoff validator: {HANDOFF_VALIDATOR_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_HANDOFF_VALIDATOR = _load_handoff_validator()


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path}: JSON root must be an object")
    return payload


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _non_empty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_review_packet_signoff(
    payload: dict[str, Any],
    *,
    require_complete: bool = False,
) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []

    if payload.get("schema_version") != EXPECTED_SCHEMA:
        errors.append(f"schema_version must be {EXPECTED_SCHEMA!r}")
    if not _non_empty_string(payload.get("signoff_id")):
        errors.append("signoff_id must be non-empty")
    if not _non_empty_string(payload.get("created_at")) and require_complete:
        errors.append("completed signoff requires created_at")

    decision = payload.get("decision")
    if decision not in VALID_DECISIONS:
        errors.append(f"decision must be one of {sorted(VALID_DECISIONS)}")
    completed = decision in COMPLETED_DECISIONS
    if require_complete and not completed:
        errors.append("signoff decision must be completed when --require-complete is used")

    reviewer = _as_dict(payload.get("reviewer"))
    if completed or require_complete:
        for field in ("name", "title_or_team", "reviewed_at"):
            if not _non_empty_string(reviewer.get(field)):
                errors.append(f"completed signoff requires reviewer.{field}")

    handoff_path_value = payload.get("handoff_manifest_path")
    handoff_validation: dict[str, Any] = {}
    if _non_empty_string(handoff_path_value):
        handoff_path = Path(str(handoff_path_value)).expanduser().resolve()
        if not handoff_path.exists():
            errors.append(f"handoff_manifest_path does not exist: {handoff_path}")
        else:
            expected_hash = payload.get("handoff_manifest_sha256")
            if expected_hash and expected_hash != _sha256(handoff_path):
                errors.append("handoff_manifest_sha256 does not match handoff_manifest_path")
            handoff_validation = _HANDOFF_VALIDATOR.validate_review_packet_handoff_manifest(handoff_path)
            if completed and handoff_validation.get("ok") is not True:
                errors.append("completed signoff requires valid handoff manifest")
    elif completed or require_complete:
        errors.append("completed signoff requires handoff_manifest_path")

    evidence_reviewed = _as_list(payload.get("evidence_reviewed"))
    if completed and not evidence_reviewed:
        errors.append("completed signoff requires evidence_reviewed")

    findings = _as_dict(payload.get("findings"))
    if decision == "accepted" and not _non_empty_string(findings.get("summary")):
        errors.append("accepted signoff requires findings.summary")
    if decision in {"changes_requested", "rejected"}:
        changes = _as_list(findings.get("changes_requested"))
        if not changes:
            errors.append(f"{decision} signoff requires findings.changes_requested")

    acknowledgements = _as_dict(payload.get("acknowledgements"))
    if completed:
        for key in REQUIRED_ACKS:
            if acknowledgements.get(key) is not True:
                errors.append(f"completed signoff requires acknowledgements.{key}=true")

    boundary = _as_dict(payload.get("signoff_boundary"))
    for key in FORBIDDEN_BOUNDARY_KEYS:
        if boundary.get(key) is not False:
            errors.append(f"signoff_boundary.{key} must be false")

    if completed:
        warnings.append("completed signoff records evidence review only; they do not authorize training")

    return {
        "report_type": "report_quality_review_packet_signoff_validation",
        "ok": not errors,
        "completed": completed and not errors,
        "require_complete": require_complete,
        "decision": decision,
        "signoff_id": payload.get("signoff_id"),
        "handoff_validation_ok": handoff_validation.get("ok") if handoff_validation else None,
        "errors": errors,
        "warnings": warnings,
    }


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate a report quality review packet sign-off record.")
    parser.add_argument("signoff", type=Path, help="Path to review packet sign-off JSON.")
    parser.add_argument("--require-complete", action="store_true")
    parser.add_argument("--json", action="store_true", help="Print machine-readable validation result.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(list(argv) if argv is not None else None)
    try:
        payload = _load_json(args.signoff)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        result = {
            "report_type": "report_quality_review_packet_signoff_validation",
            "ok": False,
            "completed": False,
            "require_complete": bool(args.require_complete),
            "errors": [str(exc)],
            "warnings": [],
        }
    else:
        result = validate_review_packet_signoff(payload, require_complete=bool(args.require_complete))

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    elif result["ok"]:
        print("PASS report quality review packet signoff validated")
        print(f"completed={str(result['completed']).lower()}")
        print(f"decision={result.get('decision')}")
        for warning in result["warnings"]:
            print(f"WARN {warning}")
    else:
        print("FAIL report quality review packet signoff validation failed")
        for error in result["errors"]:
            print(f"ERROR {error}")
        for warning in result["warnings"]:
            print(f"WARN {warning}")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
