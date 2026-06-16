#!/usr/bin/env python3
"""Summarize report quality training no-cost operator handoff sign-offs."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
from typing import Any, Sequence
from uuid import uuid4


REPO_ROOT = Path(__file__).resolve().parents[1]
SIGNOFF_VALIDATOR_PATH = (
    REPO_ROOT / "scripts/validate_report_quality_review_packet_training_no_cost_operator_handoff_signoff.py"
)
EXPECTED_SCHEMA = "decisiondoc_report_quality_training_no_cost_operator_handoff_signoff_summary.v1"


def _load_signoff_validator():
    spec = importlib.util.spec_from_file_location(
        "validate_report_quality_review_packet_training_no_cost_operator_handoff_signoff",
        SIGNOFF_VALIDATOR_PATH,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed to load no-cost operator handoff signoff validator: {SIGNOFF_VALIDATOR_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_SIGNOFF_VALIDATOR = _load_signoff_validator()


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


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_text_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.tmp.{uuid4().hex}")
    with tmp.open("w", encoding="utf-8") as f:
        f.write(text)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


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


def summarize_no_cost_operator_handoff_signoff(
    path: Path,
    payload: dict[str, Any],
    *,
    require_complete: bool = True,
) -> dict[str, Any]:
    validation = _SIGNOFF_VALIDATOR.validate_training_no_cost_operator_handoff_signoff(
        payload,
        require_complete=require_complete,
    )
    signoff_boundary = _as_dict(payload.get("signoff_boundary"))
    generation_boundary = _as_dict(payload.get("generation_boundary"))
    reviewer = _as_dict(payload.get("reviewer"))
    acknowledgements = _as_dict(payload.get("acknowledgements"))
    findings = _as_dict(payload.get("findings"))
    return {
        "path": str(path),
        "sha256": _sha256(path),
        "schema_version": payload.get("schema_version"),
        "signoff_id": payload.get("signoff_id", ""),
        "created_at": payload.get("created_at", ""),
        "decision": payload.get("decision", ""),
        "reviewer_name": reviewer.get("name", ""),
        "reviewer_title_or_team": reviewer.get("title_or_team", ""),
        "reviewed_at": reviewer.get("reviewed_at", ""),
        "handoff_manifest_path": payload.get("handoff_manifest_path", ""),
        "handoff_manifest_sha256": payload.get("handoff_manifest_sha256", ""),
        "summary": findings.get("summary", ""),
        "evidence_reviewed_count": len(_as_list(payload.get("evidence_reviewed"))),
        "completed": validation.get("completed") is True,
        "actual_operation_resume_approved": signoff_boundary.get("actual_operation_resume_approved") is True,
        "service_operation_authorized": signoff_boundary.get("service_operation_authorized") is True,
        "aws_cost_increase_authorized": signoff_boundary.get("aws_cost_increase_authorized") is True,
        "external_dataset_upload_authorized": signoff_boundary.get("external_dataset_upload_authorized") is True,
        "provider_fine_tune_api_call_authorized": signoff_boundary.get(
            "provider_fine_tune_api_call_authorized"
        )
        is True,
        "provider_job_creation_authorized": signoff_boundary.get("provider_job_creation_authorized") is True,
        "training_execution_authorized": signoff_boundary.get("training_execution_authorized") is True,
        "model_promotion_authorized": signoff_boundary.get("model_promotion_authorized") is True,
        "generation_provider_job_created": generation_boundary.get("provider_job_created") is True,
        "generation_training_execution_started": generation_boundary.get("training_execution_started") is True,
        "acknowledgements": {
            "operator_handoff_reviewed": acknowledgements.get("operator_handoff_reviewed") is True,
            "service_lock_report_summary_validated": (
                acknowledgements.get("service_lock_report_summary_validated") is True
            ),
            "linked_service_lock_files_checked": (
                acknowledgements.get("linked_service_lock_files_checked") is True
            ),
            "service_operation_lock_acknowledged": (
                acknowledgements.get("service_operation_lock_acknowledged") is True
            ),
            "resume_block_acknowledged": acknowledgements.get("resume_block_acknowledged") is True,
            "aws_no_cost_boundary_acknowledged": (
                acknowledgements.get("aws_no_cost_boundary_acknowledged") is True
            ),
            "no_runtime_services_acknowledged": (
                acknowledgements.get("no_runtime_services_acknowledged") is True
            ),
            "no_provider_calls_acknowledged": acknowledgements.get("no_provider_calls_acknowledged") is True,
            "no_training_execution_acknowledged": (
                acknowledgements.get("no_training_execution_acknowledged") is True
            ),
            "no_model_promotion_acknowledged": (
                acknowledgements.get("no_model_promotion_acknowledged") is True
            ),
            "resume_requires_separate_approval_acknowledged": (
                acknowledgements.get("resume_requires_separate_approval_acknowledged") is True
            ),
        },
        "validation": {
            "ok": validation.get("ok") is True,
            "completed": validation.get("completed") is True,
            "errors": validation.get("errors", []),
            "warnings": validation.get("warnings", []),
            "handoff_validation_ok": validation.get("handoff_validation_ok"),
        },
    }


def _confirms_operator_handoff(signoff: dict[str, Any]) -> bool:
    acknowledgements = _as_dict(signoff.get("acknowledgements"))
    return (
        signoff["validation"]["ok"]
        and signoff["completed"]
        and signoff["decision"] == "accepted"
        and signoff["validation"]["handoff_validation_ok"] is True
        and acknowledgements.get("operator_handoff_reviewed") is True
        and acknowledgements.get("service_lock_report_summary_validated") is True
        and acknowledgements.get("linked_service_lock_files_checked") is True
        and acknowledgements.get("service_operation_lock_acknowledged") is True
        and acknowledgements.get("resume_block_acknowledged") is True
        and acknowledgements.get("aws_no_cost_boundary_acknowledged") is True
        and acknowledgements.get("no_runtime_services_acknowledged") is True
        and acknowledgements.get("no_provider_calls_acknowledged") is True
        and acknowledgements.get("no_training_execution_acknowledged") is True
        and acknowledgements.get("no_model_promotion_acknowledged") is True
        and acknowledgements.get("resume_requires_separate_approval_acknowledged") is True
        and not signoff["actual_operation_resume_approved"]
        and not signoff["service_operation_authorized"]
        and not signoff["aws_cost_increase_authorized"]
        and not signoff["external_dataset_upload_authorized"]
        and not signoff["provider_fine_tune_api_call_authorized"]
        and not signoff["provider_job_creation_authorized"]
        and not signoff["training_execution_authorized"]
        and not signoff["model_promotion_authorized"]
        and not signoff["generation_provider_job_created"]
        and not signoff["generation_training_execution_started"]
    )


def build_training_no_cost_operator_handoff_signoff_summary(
    paths: Sequence[Path],
    *,
    generated_at: str | None = None,
    require_complete: bool = True,
) -> dict[str, Any]:
    signoffs: list[dict[str, Any]] = []
    load_errors: list[dict[str, str]] = []
    for path in _expand_paths(paths):
        try:
            signoffs.append(
                summarize_no_cost_operator_handoff_signoff(
                    path,
                    _load_json(path),
                    require_complete=require_complete,
                )
            )
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            load_errors.append({"path": str(path), "error": str(exc)})

    valid_count = sum(1 for signoff in signoffs if signoff["validation"]["ok"])
    completed_count = sum(1 for signoff in signoffs if signoff["completed"])
    accepted_count = sum(1 for signoff in signoffs if signoff["decision"] == "accepted")
    operator_handoff_review_count = sum(1 for signoff in signoffs if _confirms_operator_handoff(signoff))
    invalid_count = len(signoffs) - valid_count
    blocker_reasons: list[str] = []
    if load_errors:
        blocker_reasons.append("operator_handoff_signoff_load_errors")
    if not signoffs:
        blocker_reasons.append("no_operator_handoff_signoffs")
    if invalid_count:
        blocker_reasons.append("invalid_operator_handoff_signoffs")
    if completed_count != len(signoffs):
        blocker_reasons.append("operator_handoff_signoff_not_completed_for_all_records")
    if accepted_count != len(signoffs):
        blocker_reasons.append("operator_handoff_signoff_not_accepted_for_all_records")
    if operator_handoff_review_count != len(signoffs):
        blocker_reasons.append("operator_handoff_signoff_does_not_confirm_service_lock_for_all_records")
    ok = not blocker_reasons
    return {
        "report_type": "report_quality_training_no_cost_operator_handoff_signoff_summary",
        "schema_version": EXPECTED_SCHEMA,
        "generated_at": generated_at or _now_iso(),
        "read_only": True,
        "require_complete": require_complete,
        "ok": ok,
        "readiness": {
            "status": "all_operator_handoff_signoffs_confirm_service_lock" if ok else "follow_up_required",
            "blocker_reasons": blocker_reasons,
            "service_operation_locked": True,
            "resume_blocked": True,
            "operation_resume_approved": False,
            "service_operation_allowed": False,
            "aws_cost_increase_allowed": False,
            "external_dataset_upload_authorized": False,
            "provider_fine_tune_api_call_authorized": False,
            "provider_job_creation_authorized": False,
            "training_execution_authorized": False,
            "model_promotion_authorized": False,
        },
        "counts": {
            "signoff_count": len(signoffs),
            "valid_signoff_count": valid_count,
            "invalid_signoff_count": invalid_count,
            "completed_signoff_count": completed_count,
            "accepted_signoff_count": accepted_count,
            "operator_handoff_review_count": operator_handoff_review_count,
            "load_error_count": len(load_errors),
        },
        "signoffs": signoffs,
        "load_errors": load_errors,
        "side_effect_boundary": {
            "reads_local_operator_handoff_signoffs": True,
            "writes_summary_only": True,
            "server_file_written": False,
            "persisted_learning_artifact": False,
            "operation_resume_approved": False,
            "service_operation_allowed": False,
            "aws_deploy_started": False,
            "aws_resource_created": False,
            "aws_runtime_enabled": False,
            "aws_cost_increase_allowed": False,
            "scheduled_job_enabled": False,
            "cloudwatch_polling_started": False,
            "external_dataset_upload_started": False,
            "provider_fine_tune_api_called": False,
            "provider_job_created": False,
            "provider_job_polled": False,
            "training_execution_started": False,
            "model_promotion_started": False,
        },
    }


def render_training_no_cost_operator_handoff_signoff_summary_markdown(summary: dict[str, Any]) -> str:
    counts = _as_dict(summary.get("counts"))
    readiness = _as_dict(summary.get("readiness"))
    blockers = _as_list(readiness.get("blocker_reasons"))
    signoffs = _as_list(summary.get("signoffs"))
    rows = "\n".join(
        "| {signoff_id} | {decision} | {completed} | {valid} | {operator_handoff} | {reviewer} | `{path}` |".format(
            signoff_id=signoff.get("signoff_id", "-"),
            decision=signoff.get("decision", "-"),
            completed=str(signoff.get("completed") is True).lower(),
            valid=str(_as_dict(signoff.get("validation")).get("ok") is True).lower(),
            operator_handoff=str(_confirms_operator_handoff(signoff)).lower(),
            reviewer=signoff.get("reviewer_name", "-") or "-",
            path=signoff.get("path", ""),
        )
        for signoff in signoffs
    )
    if not rows:
        rows = "| - | - | - | - | - | - | - |"
    blocker_text = "\n".join(f"- `{item}`" for item in blockers) if blockers else "- none"
    return f"""# Report Quality Training No-Cost Operator Handoff Sign-Off Summary

- generated_at: `{summary.get('generated_at', '-')}`
- status: `{readiness.get('status', '-')}`
- ok: `{str(summary.get('ok') is True).lower()}`
- service_operation_locked: `true`
- resume_blocked: `true`
- signoff_count: `{counts.get('signoff_count', 0)}`
- valid_signoff_count: `{counts.get('valid_signoff_count', 0)}`
- completed_signoff_count: `{counts.get('completed_signoff_count', 0)}`
- accepted_signoff_count: `{counts.get('accepted_signoff_count', 0)}`
- operator_handoff_review_count: `{counts.get('operator_handoff_review_count', 0)}`
- operation_resume_approved: `false`
- service_operation_allowed: `false`
- aws_cost_increase_allowed: `false`
- training_execution_authorized: `false`
- model_promotion_authorized: `false`

## Sign-Offs

| signoff_id | decision | completed | valid | operator_handoff | reviewer | path |
| --- | --- | --- | --- | --- | --- | --- |
{rows}

## Blockers

{blocker_text}

## Side-Effect Boundary

- server_file_written: `false`
- persisted_learning_artifact: `false`
- operation_resume_approved: `false`
- service_operation_allowed: `false`
- aws_deploy_started: `false`
- aws_resource_created: `false`
- aws_runtime_enabled: `false`
- aws_cost_increase_allowed: `false`
- scheduled_job_enabled: `false`
- cloudwatch_polling_started: `false`
- external_dataset_upload_started: `false`
- provider_fine_tune_api_called: `false`
- provider_job_created: `false`
- provider_job_polled: `false`
- training_execution_started: `false`
- model_promotion_started: `false`
"""


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Summarize report quality training no-cost operator handoff sign-offs."
    )
    parser.add_argument(
        "signoffs",
        nargs="+",
        type=Path,
        help="No-cost operator handoff sign-off JSON file(s) or directories.",
    )
    parser.add_argument("--generated-at", help="Optional ISO timestamp for deterministic output.")
    parser.add_argument("--allow-incomplete", action="store_true")
    parser.add_argument("--output", type=Path, help="Optional output path for summary JSON.")
    parser.add_argument("--markdown", type=Path, help="Optional output path for summary Markdown.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable summary JSON to stdout.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(list(argv) if argv is not None else None)
    summary = build_training_no_cost_operator_handoff_signoff_summary(
        args.signoffs,
        generated_at=args.generated_at,
        require_complete=not args.allow_incomplete,
    )
    summary_text = json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output:
        _write_text_atomic(args.output.expanduser().resolve(), summary_text)
    if args.markdown:
        _write_text_atomic(
            args.markdown.expanduser().resolve(),
            render_training_no_cost_operator_handoff_signoff_summary_markdown(summary),
        )

    if args.json:
        print(summary_text, end="")
    else:
        print(
            "Report quality training no-cost operator handoff signoff summary: "
            f"{'PASS' if summary['ok'] else 'FAIL'}"
        )
        print(f"signoff_count={summary['counts']['signoff_count']}")
        print(f"valid_signoff_count={summary['counts']['valid_signoff_count']}")
        print(f"completed_signoff_count={summary['counts']['completed_signoff_count']}")
        print(f"accepted_signoff_count={summary['counts']['accepted_signoff_count']}")
        print(f"operator_handoff_review_count={summary['counts']['operator_handoff_review_count']}")
        print("aws_cost_boundary=no_cost_increase")
        print("training_boundary=not_authorized")
    return 0 if summary["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
