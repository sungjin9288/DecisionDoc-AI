#!/usr/bin/env python3
"""Summarize DocumentOps Phase 157 validated handoff sign-off records."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
from typing import Any, Sequence
from uuid import uuid4


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.validate_documentops_phase156_validated_closure_receipt_summary_handoff_signoff_closure_receipt_summary_handoff_signoff import (  # noqa: E402
    validate_documentops_phase156_validated_closure_receipt_summary_handoff_signoff,
)


EXPECTED_SCHEMA = "decisiondoc_documentops_phase157_validated_closure_receipt_summary_handoff_signoff_summary.v1"
REPORT_TYPE = "document_ops_phase159_local_feature_completion_validated_closure_receipt_summary_handoff_signoff_summary"
PENDING_STATUS = "pending_phase156_validated_closure_receipt_summary_handoff_signoff_review_no_training_authorization"
ACCEPTED_STATUS = "all_phase156_validated_closure_receipt_summary_handoff_signoffs_accepted_no_cost_boundary_preserved"
FORBIDDEN_TRUE_KEYS = (
    "actual_reviewer_approval_recorded",
    "actual_reviewer_approval_recorded_by_template",
    "actual_reviewer_approval_recorded_by_summary",
    "actual_reviewer_approval_recorded_by_validator",
    "actual_reviewer_approval_recorded_by_signoff",
    "actual_operation_resume_approved",
    "service_operation_allowed",
    "service_operation_authorized",
    "service_resume_authorized",
    "production_ui_called",
    "production_uat_reexecuted",
    "production_download_open_verification_authorized",
    "aws_runtime_called",
    "aws_cost_increase_allowed",
    "aws_deploy_authorized",
    "aws_resource_creation_authorized",
    "scheduled_job_authorized",
    "cloudwatch_polling_authorized",
    "provider_api_calls_allowed",
    "provider_api_calls_authorized",
    "provider_fine_tune_api_called",
    "provider_job_creation_authorized",
    "provider_job_polling_authorized",
    "external_upload_allowed",
    "external_dataset_upload_authorized",
    "training_execution_allowed",
    "training_execution_authorized",
    "model_candidate_emission_authorized",
    "model_promotion_allowed",
    "model_promotion_authorized",
    "aws_deploy_started",
    "aws_resource_created",
    "scheduled_job_enabled",
    "cloudwatch_polling_started",
    "provider_job_created",
    "provider_job_polled",
    "external_dataset_uploaded",
    "training_execution_started",
    "model_candidate_emitted",
    "model_training_started",
    "model_promoted",
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path}: JSON root must be an object")
    return payload


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_text_atomic(path: Path, text: str) -> Path:
    resolved = path.expanduser().resolve()
    resolved.parent.mkdir(parents=True, exist_ok=True)
    tmp = resolved.with_name(f"{resolved.name}.tmp.{uuid4().hex}")
    with tmp.open("w", encoding="utf-8") as handle:
        handle.write(text)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, resolved)
    return resolved


def _expand_paths(paths: Sequence[Path]) -> list[Path]:
    expanded: list[Path] = []
    for path in paths:
        candidate = path.expanduser()
        if candidate.is_dir():
            expanded.extend(sorted(item for item in candidate.glob("*.json") if item.is_file()))
        else:
            expanded.append(candidate)
    seen: set[Path] = set()
    deduped: list[Path] = []
    for path in expanded:
        resolved = path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        deduped.append(resolved)
    return deduped


def _forbidden_true_findings(*boundaries: tuple[str, dict[str, Any]]) -> list[str]:
    findings: list[str] = []
    for boundary_name, boundary in boundaries:
        for key in FORBIDDEN_TRUE_KEYS:
            if boundary.get(key) is True:
                findings.append(f"{boundary_name}.{key}")
    return findings


def summarize_signoff(path: Path, payload: dict[str, Any], *, require_complete: bool) -> dict[str, Any]:
    validation = validate_documentops_phase156_validated_closure_receipt_summary_handoff_signoff(
        payload,
        require_complete=require_complete,
    )
    reviewer = _as_dict(payload.get("reviewer"))
    findings = _as_dict(payload.get("findings"))
    acknowledgements = _as_dict(payload.get("acknowledgements"))
    signoff_boundary = _as_dict(payload.get("signoff_boundary"))
    generation_boundary = _as_dict(payload.get("generation_boundary"))
    boundary_breaks = _forbidden_true_findings(
        ("signoff_boundary", signoff_boundary),
        ("generation_boundary", generation_boundary),
    )
    acknowledgement_total = len(acknowledgements)
    acknowledgement_checked = sum(1 for value in acknowledgements.values() if value is True)

    return {
        "path": str(path),
        "sha256": _sha256_file(path),
        "schema_version": payload.get("schema_version", ""),
        "phase": payload.get("phase"),
        "signoff_id": payload.get("signoff_id", ""),
        "created_at": payload.get("created_at", ""),
        "decision": payload.get("decision", ""),
        "completed": validation.get("completed") is True,
        "accepted": payload.get("decision") == "accepted" and validation.get("completed") is True,
        "reviewer_name": reviewer.get("name", ""),
        "reviewer_title_or_team": reviewer.get("title_or_team", ""),
        "reviewed_at": reviewer.get("reviewed_at", ""),
        "summary": findings.get("summary", ""),
        "evidence_reviewed_count": len(_as_list(payload.get("evidence_reviewed"))),
        "acknowledgements_checked_count": acknowledgement_checked,
        "acknowledgements_total_count": acknowledgement_total,
        "source_handoff_path": _as_dict(payload.get("source_handoff")).get("path", ""),
        "source_handoff_sha256": _as_dict(payload.get("source_handoff")).get("sha256", ""),
        "boundary_breaks": boundary_breaks,
        "validation": {
            "ok": validation.get("ok") is True,
            "completed": validation.get("completed") is True,
            "source_handoff_validation_ok": validation.get("source_handoff_validation_ok"),
            "errors": validation.get("errors", []),
            "warnings": validation.get("warnings", []),
        },
        "side_effect_boundary": {
            "service_resume_authorized": signoff_boundary.get("service_resume_authorized") is True,
            "production_ui_called": signoff_boundary.get("production_ui_called") is True,
            "aws_runtime_called": signoff_boundary.get("aws_runtime_called") is True,
            "aws_cost_increase_allowed": signoff_boundary.get("aws_cost_increase_allowed") is True,
            "provider_api_calls_authorized": signoff_boundary.get("provider_api_calls_authorized") is True,
            "external_dataset_upload_authorized": (
                signoff_boundary.get("external_dataset_upload_authorized") is True
            ),
            "training_execution_authorized": signoff_boundary.get("training_execution_authorized") is True,
            "model_promotion_authorized": signoff_boundary.get("model_promotion_authorized") is True,
            "generation_training_execution_started": generation_boundary.get("training_execution_started") is True,
            "generation_model_promoted": generation_boundary.get("model_promoted") is True,
        },
    }


def build_documentops_phase157_validated_closure_receipt_summary_handoff_signoff_summary(
    paths: Sequence[Path],
    *,
    generated_at: str | None = None,
    require_complete: bool = False,
) -> dict[str, Any]:
    signoffs: list[dict[str, Any]] = []
    load_errors: list[dict[str, str]] = []
    for path in _expand_paths(paths):
        try:
            signoffs.append(summarize_signoff(path, _load_json(path), require_complete=require_complete))
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            load_errors.append({"path": str(path), "error": str(exc)})

    valid_count = sum(1 for signoff in signoffs if signoff["validation"]["ok"])
    completed_count = sum(1 for signoff in signoffs if signoff["completed"])
    accepted_count = sum(1 for signoff in signoffs if signoff["accepted"])
    pending_count = sum(1 for signoff in signoffs if signoff["decision"] == "pending")
    boundary_break_count = sum(1 for signoff in signoffs if signoff["boundary_breaks"])
    invalid_count = len(signoffs) - valid_count
    all_valid_no_boundary_break = bool(signoffs) and not load_errors and invalid_count == 0 and boundary_break_count == 0
    all_completed_accepted = all_valid_no_boundary_break and completed_count == len(signoffs) and accepted_count == len(signoffs)

    blocker_reasons: list[str] = []
    if load_errors:
        blocker_reasons.append("signoff_load_errors")
    if not signoffs:
        blocker_reasons.append("no_signoff_records")
    if invalid_count:
        blocker_reasons.append("invalid_signoff_records")
    if boundary_break_count:
        blocker_reasons.append("signoff_boundary_breaks")
    if require_complete and not all_completed_accepted:
        blocker_reasons.append("completed_accepted_signoffs_required")

    if blocker_reasons:
        status = "follow_up_required"
    elif all_completed_accepted:
        status = ACCEPTED_STATUS
    else:
        status = PENDING_STATUS

    return {
        "report_type": REPORT_TYPE,
        "schema_version": EXPECTED_SCHEMA,
        "generated_at": generated_at or _now_iso(),
        "read_only": True,
        "require_complete": require_complete,
        "ok": not blocker_reasons,
        "completion_ready": all_completed_accepted,
        "readiness": {
            "status": status,
            "blocker_reasons": blocker_reasons,
            "service_freeze_preserved": True,
            "resume_requires_separate_approval": True,
            "service_resume_authorized": False,
            "aws_cost_increase_allowed": False,
            "provider_api_calls_authorized": False,
            "external_dataset_upload_authorized": False,
            "training_execution_authorized": False,
            "model_promotion_authorized": False,
            "aws_cost_boundary": "no_cost_increase",
            "training_boundary": "not_authorized",
        },
        "counts": {
            "signoff_count": len(signoffs),
            "valid_signoff_count": valid_count,
            "invalid_signoff_count": invalid_count,
            "pending_signoff_count": pending_count,
            "completed_signoff_count": completed_count,
            "accepted_signoff_count": accepted_count,
            "boundary_break_count": boundary_break_count,
            "load_error_count": len(load_errors),
        },
        "signoffs": signoffs,
        "load_errors": load_errors,
        "side_effect_boundary": {
            "reads_local_signoff_records": True,
            "writes_summary_only": True,
            "actual_reviewer_approval_recorded_by_summary": False,
            "service_resume_authorized": False,
            "production_ui_called": False,
            "aws_runtime_called": False,
            "aws_cost_increase_allowed": False,
            "provider_api_calls_authorized": False,
            "external_dataset_upload_authorized": False,
            "training_execution_started": False,
            "model_promoted": False,
        },
    }


def _render_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# DocumentOps Phase 157 Validated Closure Receipt Summary Handoff Sign-Off Summary",
        "",
        f"- Status: `{summary['readiness']['status']}`",
        f"- Sign-off count: `{summary['counts']['signoff_count']}`",
        f"- Valid sign-off count: `{summary['counts']['valid_signoff_count']}`",
        f"- Completed sign-off count: `{summary['counts']['completed_signoff_count']}`",
        f"- Accepted sign-off count: `{summary['counts']['accepted_signoff_count']}`",
        f"- AWS cost boundary: `{summary['readiness']['aws_cost_boundary']}`",
        f"- Training boundary: `{summary['readiness']['training_boundary']}`",
        "",
        "## Sign-Off Records",
        "",
        "| Sign-off ID | Decision | Valid | Completed | Accepted | Boundary Breaks |",
        "|---|---|---|---|---|---|",
    ]
    for signoff in summary["signoffs"]:
        lines.append(
            "| "
            f"`{signoff['signoff_id']}` | "
            f"`{signoff['decision']}` | "
            f"`{str(signoff['validation']['ok']).lower()}` | "
            f"`{str(signoff['completed']).lower()}` | "
            f"`{str(signoff['accepted']).lower()}` | "
            f"`{len(signoff['boundary_breaks'])}` |"
        )
    lines.extend(
        [
            "",
            "## Boundary",
            "",
            "This summary is read-only local evidence. It does not authorize service resume, "
            "production UI re-execution, AWS runtime calls, provider calls, dataset upload, "
            "training execution, or model promotion.",
            "",
        ]
    )
    return "\n".join(lines)


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Summarize DocumentOps Phase 157 validated handoff sign-off JSON records."
    )
    parser.add_argument("signoffs", nargs="+", type=Path, help="Sign-off JSON file(s) or directories.")
    parser.add_argument("--generated-at", help="Optional ISO timestamp for deterministic summary output.")
    parser.add_argument("--require-complete", action="store_true")
    parser.add_argument("--output", type=Path, help="Optional output path for summary JSON.")
    parser.add_argument("--markdown-output", type=Path, help="Optional output path for summary Markdown.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(list(argv) if argv is not None else None)
    summary = build_documentops_phase157_validated_closure_receipt_summary_handoff_signoff_summary(
        args.signoffs,
        generated_at=args.generated_at,
        require_complete=bool(args.require_complete),
    )
    if args.output:
        _write_text_atomic(args.output, json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    if args.markdown_output:
        _write_text_atomic(args.markdown_output, _render_markdown(summary))
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if summary["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
