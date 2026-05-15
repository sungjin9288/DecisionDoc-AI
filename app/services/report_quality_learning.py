"""Report quality correction artifacts for pre-fine-tuning learning gates."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
import uuid


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


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


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
            child_path = f"{path}.{key}"
            if str(key).lower() in FORBIDDEN_CONTENT_KEYS:
                findings.append(child_path)
            findings.extend(_scan_forbidden_content_keys(child, path=child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            findings.extend(_scan_forbidden_content_keys(child, path=f"{path}[{index}]"))
    return findings


def _dimension_floor(dimension: str) -> float:
    if dimension == "visual_design":
        return MIN_VISUAL_DESIGN_SCORE
    if dimension == "export_readiness":
        return MIN_EXPORT_READINESS_SCORE
    return MIN_REQUIRED_DIMENSION_SCORE


def validate_correction_artifact(payload: dict[str, Any]) -> dict[str, Any]:
    """Validate a before/after correction artifact without starting training."""
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
        if workflow.get("workflow_status") != "final_approved":
            errors.append("accepted artifacts require workflow_reference.workflow_status=final_approved")
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
            minimum = _dimension_floor(dimension)
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


def _default_dimension_scores(value: float = 0.0) -> dict[str, float]:
    return {dimension: value for dimension in REQUIRED_DIMENSIONS}


def _default_rationale(value: str = "") -> dict[str, str]:
    return {dimension: value for dimension in REQUIRED_DIMENSIONS}


def _slide_issue_summary(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for item in snapshot.get("slide_outline") or []:
        if not isinstance(item, dict):
            continue
        result.append({
            "slide_no": item.get("page") or len(result) + 1,
            "title": item.get("title") or "",
            "message": item.get("core_message") or item.get("message") or "",
            "issue": "",
        })
    return result


def _after_slide_summary(snapshot: dict[str, Any], provided: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if provided:
        return provided
    result: list[dict[str, Any]] = []
    for item in snapshot.get("slide_outline") or []:
        if not isinstance(item, dict):
            continue
        result.append({
            "slide_no": item.get("page") or len(result) + 1,
            "title": item.get("title") or "",
            "message": item.get("core_message") or item.get("message") or "",
            "layout": item.get("layout") or item.get("layout_hint") or "",
            "visual_asset": item.get("visual_type") or item.get("visual") or "",
        })
    return result


def _planning_summary(snapshot: dict[str, Any]) -> str:
    planning = snapshot.get("planning") if isinstance(snapshot.get("planning"), dict) else {}
    bits = [
        planning.get("planning_brief") or "",
        planning.get("executive_message") or "",
        snapshot.get("goal") or "",
    ]
    return "\n".join(str(item).strip() for item in bits if str(item).strip())


def build_correction_artifact_from_snapshot(
    snapshot: dict[str, Any],
    correction: dict[str, Any],
    *,
    artifact_id: str | None = None,
) -> dict[str, Any]:
    """Build a metadata-only correction artifact from a report workflow snapshot."""
    artifact_id = artifact_id or f"rqa_{uuid.uuid4().hex}"
    dimension_scores = correction.get("dimension_scores")
    if not isinstance(dimension_scores, dict):
        dimension_scores = _default_dimension_scores()
    rationale_by_dimension = correction.get("rationale_by_dimension")
    if not isinstance(rationale_by_dimension, dict):
        rationale_by_dimension = _default_rationale()
    final_output_reference = (
        correction.get("final_output_reference")
        or f"report_workflow_snapshot:{snapshot.get('report_workflow_id', '')}"
    )
    learning = snapshot.get("learning") if isinstance(snapshot.get("learning"), dict) else {}
    source = snapshot.get("source") if isinstance(snapshot.get("source"), dict) else {}
    promotion = snapshot.get("promotion") if isinstance(snapshot.get("promotion"), dict) else {}
    return {
        "schema_version": EXPECTED_SCHEMA,
        "artifact_id": artifact_id,
        "created_at": _now_iso(),
        "workflow_reference": {
            "tenant_id": snapshot.get("tenant_id", ""),
            "report_workflow_id": snapshot.get("report_workflow_id", ""),
            "workflow_status": snapshot.get("status", ""),
            "project_id": promotion.get("project_id") or "",
            "learning_opt_in": bool(learning.get("learning_opt_in", False)),
            "source_material_policy": "metadata_only",
            "source_bundle_id": source.get("source_bundle_id") or "",
            "source_request_id": source.get("source_request_id") or "",
            "snapshot_version": snapshot.get("export_version", ""),
        },
        "document_profile": {
            "document_type": snapshot.get("report_type") or "proposal_deck",
            "audience": snapshot.get("audience") or "unspecified",
            "domain": correction.get("domain") or snapshot.get("client") or "general",
            "language": correction.get("language") or "ko",
            "slide_count": len(snapshot.get("slide_outline") or []),
        },
        "quality_baseline": {
            "overall_score": correction.get("overall_score", 0.0),
            "hard_failures": list(correction.get("hard_failures") or []),
            "dimension_scores": dimension_scores,
        },
        "before": {
            "planning_summary": correction.get("before_planning_summary") or _planning_summary(snapshot),
            "slide_outline_summary": list(correction.get("before_slide_outline_summary") or _slide_issue_summary(snapshot)),
            "visible_claims": list(correction.get("visible_claims") or []),
        },
        "correction": {
            "reviewer": correction.get("reviewer") or correction.get("username") or "",
            "reviewed_at": correction.get("reviewed_at") or "",
            "change_requests": list(correction.get("change_requests") or []),
            "rationale_by_dimension": rationale_by_dimension,
        },
        "after": {
            "planning_summary": correction.get("after_planning_summary") or "",
            "slide_outline_summary": _after_slide_summary(snapshot, list(correction.get("after_slide_outline_summary") or [])),
            "final_output_reference": final_output_reference,
        },
        "learning_labels": {
            "accepted_for_learning": bool(correction.get("accepted_for_learning", False)),
            "task_types": list(correction.get("task_types") or ["proposal_planning", "slide_message_design"]),
            "skills": list(correction.get("skills") or ["policy-planning", "evidence-gap-review"]),
            "confirmed_claims": list(correction.get("confirmed_claims") or []),
            "assumed_claims": list(correction.get("assumed_claims") or []),
            "todo_claims": list(correction.get("todo_claims") or []),
            "forbidden_terms_scan": correction.get("forbidden_terms_scan") or "not_run",
            "privacy_security_scan": correction.get("privacy_security_scan") or "not_run",
            "human_review_status": correction.get("human_review_status") or "pending",
        },
        "training_boundary": {key: False for key in FORBIDDEN_BOUNDARY_KEYS},
    }
