#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence


EXPECTED_SCHEMA = "decisiondoc_report_quality_correction_artifact.v1"
MIN_OVERALL_SCORE = 0.80
MIN_REQUIRED_DIMENSION_SCORE = 0.75
MIN_VISUAL_DESIGN_SCORE = 0.70
MIN_EXPORT_READINESS_SCORE = 0.80
REQUIRED_DIMENSIONS = (
    "logic",
    "evidence",
    "audience_fit",
    "slide_structure",
    "visual_design",
    "public_sector_tone",
    "export_readiness",
    "learning_value",
)
FORBIDDEN_BOUNDARY_KEYS = (
    "external_dataset_upload_authorized",
    "provider_fine_tune_api_call_authorized",
    "provider_job_creation_authorized",
    "provider_job_polling_authorized",
    "training_execution_authorized",
    "model_candidate_emission_authorized",
    "model_promotion_authorized",
)
FORBIDDEN_CONTENT_KEYS = {
    "content_base64",
    "raw_attachment",
    "raw_attachments",
    "file_bytes",
    "bytes",
    "secret",
    "api_key",
    "private_key",
}


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


def _scan_forbidden_content_keys(value: Any, *, path: str = "$") -> list[str]:
    findings: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            key_text = str(key).lower()
            child_path = f"{path}.{key}"
            if key_text in FORBIDDEN_CONTENT_KEYS:
                findings.append(child_path)
            findings.extend(_scan_forbidden_content_keys(child, path=child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            findings.extend(_scan_forbidden_content_keys(child, path=f"{path}[{index}]"))
    return findings


def validate_correction_artifact(payload: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []

    if payload.get("schema_version") != EXPECTED_SCHEMA:
        errors.append(f"schema_version must be {EXPECTED_SCHEMA!r}")
    if not _non_empty_string(payload.get("artifact_id")):
        errors.append("artifact_id must be non-empty")
    if not _non_empty_string(payload.get("created_at")):
        errors.append("created_at must be non-empty")

    workflow = _as_dict(payload.get("workflow_reference"), field="workflow_reference", errors=errors)
    profile = _as_dict(payload.get("document_profile"), field="document_profile", errors=errors)
    quality = _as_dict(payload.get("quality_baseline"), field="quality_baseline", errors=errors)
    before = _as_dict(payload.get("before"), field="before", errors=errors)
    correction = _as_dict(payload.get("correction"), field="correction", errors=errors)
    after = _as_dict(payload.get("after"), field="after", errors=errors)
    labels = _as_dict(payload.get("learning_labels"), field="learning_labels", errors=errors)
    boundary = _as_dict(payload.get("training_boundary"), field="training_boundary", errors=errors)

    for field in ("tenant_id", "report_workflow_id", "source_material_policy"):
        if not _non_empty_string(workflow.get(field)):
            errors.append(f"workflow_reference.{field} must be non-empty")
    if workflow.get("source_material_policy") != "metadata_only":
        errors.append("workflow_reference.source_material_policy must be metadata_only")

    for field in ("document_type", "audience", "domain", "language"):
        if not _non_empty_string(profile.get(field)):
            errors.append(f"document_profile.{field} must be non-empty")

    hard_failures = _as_list(quality.get("hard_failures"), field="quality_baseline.hard_failures", errors=errors)
    dimension_scores = _as_dict(
        quality.get("dimension_scores"),
        field="quality_baseline.dimension_scores",
        errors=errors,
    )
    overall_score = _score(quality.get("overall_score"))
    if overall_score is None:
        errors.append("quality_baseline.overall_score must be a number between 0.0 and 1.0")

    dimension_values: dict[str, float] = {}
    for dimension in REQUIRED_DIMENSIONS:
        value = _score(dimension_scores.get(dimension))
        if value is None:
            errors.append(f"quality_baseline.dimension_scores.{dimension} must be a number between 0.0 and 1.0")
        else:
            dimension_values[dimension] = value

    _as_list(before.get("slide_outline_summary"), field="before.slide_outline_summary", errors=errors)
    _as_list(before.get("visible_claims"), field="before.visible_claims", errors=errors)
    _as_list(after.get("slide_outline_summary"), field="after.slide_outline_summary", errors=errors)

    change_requests = _as_list(correction.get("change_requests"), field="correction.change_requests", errors=errors)
    for index, item in enumerate(change_requests):
        if not isinstance(item, dict):
            errors.append(f"correction.change_requests[{index}] must be an object")
            continue
        for field in ("target", "issue", "correction", "rationale"):
            if not _non_empty_string(item.get(field)):
                errors.append(f"correction.change_requests[{index}].{field} must be non-empty")

    rationale_by_dimension = _as_dict(
        correction.get("rationale_by_dimension"),
        field="correction.rationale_by_dimension",
        errors=errors,
    )
    for dimension in REQUIRED_DIMENSIONS:
        if dimension not in rationale_by_dimension:
            errors.append(f"correction.rationale_by_dimension.{dimension} is required")

    for key in FORBIDDEN_BOUNDARY_KEYS:
        if boundary.get(key) is not False:
            errors.append(f"training_boundary.{key} must be false")

    for path in _scan_forbidden_content_keys(payload):
        errors.append(f"forbidden raw or secret-like content key found at {path}")

    accepted = labels.get("accepted_for_learning") is True
    ready_for_learning = False
    if accepted:
        if workflow.get("learning_opt_in") is not True:
            errors.append("accepted artifacts require workflow_reference.learning_opt_in=true")
        if not _non_empty_string(correction.get("reviewer")):
            errors.append("accepted artifacts require correction.reviewer")
        if not _non_empty_string(correction.get("reviewed_at")):
            errors.append("accepted artifacts require correction.reviewed_at")
        if labels.get("human_review_status") != "accepted":
            errors.append("accepted artifacts require learning_labels.human_review_status=accepted")
        if labels.get("forbidden_terms_scan") != "pass":
            errors.append("accepted artifacts require learning_labels.forbidden_terms_scan=pass")
        if labels.get("privacy_security_scan") != "pass":
            errors.append("accepted artifacts require learning_labels.privacy_security_scan=pass")
        if hard_failures:
            errors.append("accepted artifacts must have no quality_baseline.hard_failures")
        if overall_score is not None and overall_score < MIN_OVERALL_SCORE:
            errors.append(f"accepted artifacts require overall_score >= {MIN_OVERALL_SCORE:.2f}")
        for dimension, value in dimension_values.items():
            minimum = MIN_REQUIRED_DIMENSION_SCORE
            if dimension == "visual_design":
                minimum = MIN_VISUAL_DESIGN_SCORE
            elif dimension == "export_readiness":
                minimum = MIN_EXPORT_READINESS_SCORE
            if value < minimum:
                errors.append(f"accepted artifacts require {dimension} >= {minimum:.2f}")
        if not _non_empty_string(after.get("planning_summary")):
            errors.append("accepted artifacts require after.planning_summary")
        if not _non_empty_string(after.get("final_output_reference")):
            warnings.append("accepted artifact has no after.final_output_reference")
        ready_for_learning = not errors

    return {
        "ok": not errors,
        "ready_for_learning": ready_for_learning,
        "errors": errors,
        "warnings": warnings,
        "artifact_id": payload.get("artifact_id"),
        "schema_version": payload.get("schema_version"),
    }


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("artifact root must be an object")
    return payload


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate a DecisionDoc report quality correction artifact.")
    parser.add_argument("artifact", type=Path, help="Path to correction artifact JSON.")
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print machine-readable validation result.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(list(argv) if argv is not None else None)
    try:
        payload = _load_json(args.artifact)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        result = {
            "ok": False,
            "ready_for_learning": False,
            "errors": [str(exc)],
            "warnings": [],
            "artifact_id": None,
            "schema_version": None,
        }
    else:
        result = validate_correction_artifact(payload)

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    elif result["ok"]:
        print("PASS report quality correction artifact validated")
        print(f"ready_for_learning={str(result['ready_for_learning']).lower()}")
        if result["artifact_id"]:
            print(f"artifact_id={result['artifact_id']}")
        for warning in result["warnings"]:
            print(f"WARN {warning}")
    else:
        print("FAIL report quality correction artifact validation failed")
        print(f"ready_for_learning={str(result['ready_for_learning']).lower()}")
        for error in result["errors"]:
            print(f"ERROR {error}")
        for warning in result["warnings"]:
            print(f"WARN {warning}")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
