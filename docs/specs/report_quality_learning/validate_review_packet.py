#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import sys
from typing import Any, Sequence


REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.services.report_quality_learning import (  # noqa: E402
    FORBIDDEN_BOUNDARY_KEYS,
    FORBIDDEN_CONTENT_KEYS,
    MIN_EXPORT_READINESS_SCORE,
    MIN_OVERALL_SCORE,
    MIN_REQUIRED_DIMENSION_SCORE,
    MIN_VISUAL_DESIGN_SCORE,
    REQUIRED_DIMENSIONS,
    correction_artifact_fingerprint,
    validate_correction_artifact,
)


EXPECTED_PACKET_VERSION = "decisiondoc_report_quality_review_packet.v1"
EXPECTED_SOURCE = "client_side_review_packet"
NO_SIDE_EFFECT_BOUNDARY_KEYS = (
    "server_file_written",
    "persisted_learning_artifact",
    *FORBIDDEN_BOUNDARY_KEYS,
)


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("review packet root must be an object")
    return payload


def _as_dict(value: Any, *, field: str, errors: list[str]) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    errors.append(f"{field} must be an object")
    return {}


def _as_list(value: Any, *, field: str, errors: list[str]) -> list[Any]:
    if isinstance(value, list):
        return value
    errors.append(f"{field} must be a list")
    return []


def _non_empty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _score(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        score = float(value)
        if 0.0 <= score <= 1.0:
            return score
    return None


def _dimension_floor(dimension: str) -> float:
    if dimension == "visual_design":
        return MIN_VISUAL_DESIGN_SCORE
    if dimension == "export_readiness":
        return MIN_EXPORT_READINESS_SCORE
    return MIN_REQUIRED_DIMENSION_SCORE


def _scan_forbidden_content_keys(value: Any, *, path: str = "$") -> list[str]:
    findings: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}"
            if str(key).lower() in FORBIDDEN_CONTENT_KEYS:
                findings.append(child_path)
            findings.extend(_scan_forbidden_content_keys(child, path=child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            findings.extend(_scan_forbidden_content_keys(child, path=f"{path}[{index}]"))
    return findings


def _validate_timestamp(value: Any, *, field: str, errors: list[str]) -> None:
    if not _non_empty_string(value):
        errors.append(f"{field} must be non-empty")
        return
    try:
        datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        errors.append(f"{field} must be ISO-8601 compatible")


def _validate_change_requests(payload: dict[str, Any], *, required: bool, errors: list[str]) -> None:
    change_requests = _as_list(payload.get("change_requests"), field="quality_payload.change_requests", errors=errors)
    if required and not change_requests:
        errors.append("ready review packets require quality_payload.change_requests")
    for index, item in enumerate(change_requests):
        if not isinstance(item, dict):
            errors.append(f"quality_payload.change_requests[{index}] must be an object")
            continue
        for field in ("target", "issue", "correction", "rationale"):
            if not _non_empty_string(item.get(field)):
                errors.append(f"quality_payload.change_requests[{index}].{field} must be non-empty")


def _validate_quality_payload(payload: dict[str, Any], *, require_ready: bool, errors: list[str]) -> bool:
    accepted = payload.get("accepted_for_learning") is True
    required = require_ready or accepted

    overall_score = _score(payload.get("overall_score"))
    if overall_score is None:
        errors.append("quality_payload.overall_score must be a number between 0.0 and 1.0")
    elif required and overall_score < MIN_OVERALL_SCORE:
        errors.append(f"ready review packets require overall_score >= {MIN_OVERALL_SCORE:.2f}")

    dimension_scores = _as_dict(
        payload.get("dimension_scores"),
        field="quality_payload.dimension_scores",
        errors=errors,
    )
    for dimension in REQUIRED_DIMENSIONS:
        value = _score(dimension_scores.get(dimension))
        if value is None:
            errors.append(f"quality_payload.dimension_scores.{dimension} must be a number between 0.0 and 1.0")
        elif required and value < _dimension_floor(dimension):
            errors.append(f"ready review packets require {dimension} >= {_dimension_floor(dimension):.2f}")

    hard_failures = _as_list(payload.get("hard_failures"), field="quality_payload.hard_failures", errors=errors)
    if required and hard_failures:
        errors.append("ready review packets require no quality_payload.hard_failures")

    _validate_change_requests(payload, required=required, errors=errors)

    rationale_by_dimension = _as_dict(
        payload.get("rationale_by_dimension"),
        field="quality_payload.rationale_by_dimension",
        errors=errors,
    )
    for dimension in REQUIRED_DIMENSIONS:
        if dimension not in rationale_by_dimension:
            errors.append(f"quality_payload.rationale_by_dimension.{dimension} is required")

    if required:
        if payload.get("accepted_for_learning") is not True:
            errors.append("ready review packets require quality_payload.accepted_for_learning=true")
        if payload.get("human_review_status") != "accepted":
            errors.append("ready review packets require quality_payload.human_review_status=accepted")
        if payload.get("forbidden_terms_scan") != "pass":
            errors.append("ready review packets require quality_payload.forbidden_terms_scan=pass")
        if payload.get("privacy_security_scan") != "pass":
            errors.append("ready review packets require quality_payload.privacy_security_scan=pass")
        if not _non_empty_string(payload.get("reviewer")):
            errors.append("ready review packets require quality_payload.reviewer")
        if not _non_empty_string(payload.get("reviewed_at")):
            errors.append("ready review packets require quality_payload.reviewed_at")
        if not _non_empty_string(payload.get("after_planning_summary")):
            errors.append("ready review packets require quality_payload.after_planning_summary")

    return accepted


def validate_review_packet(payload: dict[str, Any], *, require_ready: bool = False) -> dict[str, Any]:
    """Validate a client-side report quality review packet without side effects."""
    errors: list[str] = []
    warnings: list[str] = []

    if payload.get("packet_version") != EXPECTED_PACKET_VERSION:
        errors.append(f"packet_version must be {EXPECTED_PACKET_VERSION!r}")
    if payload.get("source") != EXPECTED_SOURCE:
        errors.append(f"source must be {EXPECTED_SOURCE!r}")
    if payload.get("server_file_written") is not False:
        errors.append("server_file_written must be false")
    if payload.get("preview_persisted") is True:
        errors.append("preview_persisted must remain false for client-side review packets")
    _validate_timestamp(payload.get("exported_at"), field="exported_at", errors=errors)

    workflow = _as_dict(payload.get("report_workflow"), field="report_workflow", errors=errors)
    if not _non_empty_string(workflow.get("report_workflow_id")):
        errors.append("report_workflow.report_workflow_id must be non-empty")
    if require_ready:
        if workflow.get("status") != "final_approved":
            errors.append("ready review packets require report_workflow.status=final_approved")
        if workflow.get("learning_opt_in") is not True:
            errors.append("ready review packets require report_workflow.learning_opt_in=true")

    quality_payload = _as_dict(payload.get("quality_payload"), field="quality_payload", errors=errors)
    accepted = _validate_quality_payload(quality_payload, require_ready=require_ready, errors=errors)

    checklist = _as_list(payload.get("checklist"), field="checklist", errors=errors)
    checklist_passed = 0
    checklist_pending = 0
    for index, item in enumerate(checklist):
        if not isinstance(item, dict):
            errors.append(f"checklist[{index}] must be an object")
            continue
        if item.get("pass") is True:
            checklist_passed += 1
        if item.get("pending") is True:
            checklist_pending += 1
        if not _non_empty_string(item.get("label")):
            errors.append(f"checklist[{index}].label must be non-empty")
    if require_ready and (not checklist or checklist_passed != len(checklist) or checklist_pending):
        errors.append("ready review packets require every checklist item to pass with no pending items")

    preview_validation = payload.get("preview_validation")
    preview = _as_dict(preview_validation, field="preview_validation", errors=errors) if preview_validation is not None else {}
    preview_ok = preview.get("ok") is True
    preview_ready = preview.get("ready_for_learning") is True
    preview_artifact = payload.get("preview_artifact")
    preview_artifact_validation: dict[str, Any] = {}
    preview_artifact_ok = False
    preview_artifact_ready = False
    preview_fingerprint = str(payload.get("preview_fingerprint") or "").strip()
    if isinstance(preview_artifact, dict):
        preview_artifact_validation = validate_correction_artifact(preview_artifact)
        preview_artifact_ok = preview_artifact_validation.get("ok") is True
        preview_artifact_ready = preview_artifact_validation.get("ready_for_learning") is True
        preview_artifact_id = preview_artifact_validation.get("artifact_id") or preview_artifact.get("artifact_id")
        if preview.get("artifact_id") and preview_artifact_id and preview.get("artifact_id") != preview_artifact_id:
            errors.append("preview_validation.artifact_id must match preview_artifact.artifact_id")
        if preview_fingerprint and preview_fingerprint != correction_artifact_fingerprint(preview_artifact):
            errors.append("preview_fingerprint must match preview_artifact content")
        for error in preview_artifact_validation.get("errors") or []:
            errors.append(f"preview_artifact: {error}")
    elif preview_artifact is not None:
        errors.append("preview_artifact must be an object when provided")
    if require_ready:
        if not preview_validation:
            errors.append("ready review packets require preview_validation")
        if not preview_ok:
            errors.append("ready review packets require preview_validation.ok=true")
        if not preview_ready:
            errors.append("ready review packets require preview_validation.ready_for_learning=true")
        if not isinstance(preview_artifact, dict):
            errors.append("ready review packets require preview_artifact")
        if not preview_artifact_ok:
            errors.append("ready review packets require preview_artifact validation ok=true")
        if not preview_artifact_ready:
            errors.append("ready review packets require preview_artifact ready_for_learning=true")
        if not preview_fingerprint:
            errors.append("ready review packets require preview_fingerprint")

    boundary = _as_dict(payload.get("training_boundary"), field="training_boundary", errors=errors)
    for key in NO_SIDE_EFFECT_BOUNDARY_KEYS:
        if boundary.get(key) is not False:
            errors.append(f"training_boundary.{key} must be false")

    for path in _scan_forbidden_content_keys(payload):
        errors.append(f"forbidden raw or secret-like content key found at {path}")

    if accepted and not require_ready:
        warnings.append("quality_payload is accepted; rerun with --require-ready before saving a learning artifact")

    ready_for_learning = (
        not errors
        and accepted
        and workflow.get("status") == "final_approved"
        and workflow.get("learning_opt_in") is True
        and preview_ok
        and preview_ready
        and preview_artifact_ok
        and preview_artifact_ready
        and bool(checklist)
        and checklist_passed == len(checklist)
        and checklist_pending == 0
    )

    if require_ready and not ready_for_learning:
        errors.append("review packet is not ready_for_learning")

    return {
        "report_type": "report_quality_review_packet_validation",
        "ok": not errors,
        "ready_for_learning": ready_for_learning and not errors,
        "require_ready": require_ready,
        "packet_version": payload.get("packet_version"),
        "report_workflow_id": workflow.get("report_workflow_id"),
        "preview_ok": preview_ok,
        "preview_ready_for_learning": preview_ready,
        "preview_artifact_ok": preview_artifact_ok,
        "preview_artifact_ready_for_learning": preview_artifact_ready,
        "preview_artifact_validation": preview_artifact_validation or None,
        "preview_persisted": payload.get("preview_persisted") is True,
        "checklist_count": len(checklist),
        "checklist_passed": checklist_passed,
        "checklist_pending": checklist_pending,
        "server_file_written": payload.get("server_file_written") is True,
        "training_boundary": {key: boundary.get(key) for key in NO_SIDE_EFFECT_BOUNDARY_KEYS},
        "errors": errors,
        "warnings": warnings,
    }


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate a DecisionDoc report quality review packet JSON.")
    parser.add_argument("packet", type=Path, help="Path to client-side Review packet JSON.")
    parser.add_argument(
        "--require-ready",
        action="store_true",
        help="Fail unless the packet satisfies final-approved, opt-in, preview-ready, checklist-pass gates.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print machine-readable validation result.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(list(argv) if argv is not None else None)
    try:
        payload = _load_json(args.packet)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        result = {
            "report_type": "report_quality_review_packet_validation",
            "ok": False,
            "ready_for_learning": False,
            "require_ready": bool(args.require_ready),
            "errors": [str(exc)],
            "warnings": [],
        }
    else:
        result = validate_review_packet(payload, require_ready=bool(args.require_ready))

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    elif result["ok"]:
        print("PASS report quality review packet validated")
        print(f"ready_for_learning={str(result['ready_for_learning']).lower()}")
        print(f"checklist_passed={result.get('checklist_passed', 0)}/{result.get('checklist_count', 0)}")
        print(f"preview_ready_for_learning={str(result.get('preview_ready_for_learning', False)).lower()}")
        print(f"preview_artifact_ready_for_learning={str(result.get('preview_artifact_ready_for_learning', False)).lower()}")
        for warning in result["warnings"]:
            print(f"WARN {warning}")
    else:
        print("FAIL report quality review packet validation failed")
        print(f"ready_for_learning={str(result.get('ready_for_learning', False)).lower()}")
        for error in result["errors"]:
            print(f"ERROR {error}")
        for warning in result["warnings"]:
            print(f"WARN {warning}")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
