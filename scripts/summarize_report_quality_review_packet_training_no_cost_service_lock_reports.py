#!/usr/bin/env python3
"""Summarize report quality training no-cost service lock reports."""
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
SERVICE_LOCK_REPORT_VALIDATOR_PATH = (
    REPO_ROOT / "scripts/validate_report_quality_review_packet_training_no_cost_service_lock_report.py"
)
EXPECTED_SCHEMA = "decisiondoc_report_quality_training_no_cost_service_lock_report_summary.v1"


def _load_service_lock_report_validator():
    spec = importlib.util.spec_from_file_location(
        "validate_report_quality_review_packet_training_no_cost_service_lock_report",
        SERVICE_LOCK_REPORT_VALIDATOR_PATH,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed to load no-cost service lock report validator: {SERVICE_LOCK_REPORT_VALIDATOR_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_SERVICE_LOCK_REPORT_VALIDATOR = _load_service_lock_report_validator()


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


def summarize_no_cost_service_lock_report(
    path: Path,
    payload: dict[str, Any],
    *,
    require_ready: bool = True,
) -> dict[str, Any]:
    validation = _SERVICE_LOCK_REPORT_VALIDATOR.validate_training_no_cost_service_lock_report(
        path,
        require_ready=require_ready,
    )
    report_state = _as_dict(payload.get("report_state"))
    counts = _as_dict(payload.get("counts"))
    service_lock_check = _as_dict(payload.get("service_lock_check"))
    return {
        "path": str(path),
        "sha256": _sha256(path),
        "schema_version": payload.get("schema_version"),
        "generated_at": payload.get("generated_at", ""),
        "status": report_state.get("status", ""),
        "ready": report_state.get("ready") is True,
        "read_only_report": report_state.get("read_only_report") is True,
        "service_operation_locked": report_state.get("service_operation_locked") is True,
        "resume_blocked": report_state.get("resume_blocked") is True,
        "service_lock_check_ok": service_lock_check.get("ok") is True,
        "aws_cost_boundary": validation.get("aws_cost_boundary", ""),
        "operation_resume_approved": report_state.get("operation_resume_approved") is True,
        "service_operation_allowed": report_state.get("service_operation_allowed") is True,
        "aws_cost_increase_allowed": report_state.get("aws_cost_increase_allowed") is True,
        "external_dataset_upload_authorized": report_state.get("external_dataset_upload_authorized") is True,
        "provider_fine_tune_api_call_authorized": (
            report_state.get("provider_fine_tune_api_call_authorized") is True
        ),
        "provider_job_creation_authorized": report_state.get("provider_job_creation_authorized") is True,
        "training_execution_authorized": report_state.get("training_execution_authorized") is True,
        "model_promotion_authorized": report_state.get("model_promotion_authorized") is True,
        "closeout_receipt_count": counts.get("closeout_receipt_count", 0),
        "valid_closeout_receipt_count": counts.get("valid_closeout_receipt_count", 0),
        "ready_closeout_receipt_count": counts.get("ready_closeout_receipt_count", 0),
        "final_hold_count": counts.get("final_hold_count", 0),
        "active_final_hold_count": counts.get("active_final_hold_count", 0),
        "signoff_count": counts.get("signoff_count", 0),
        "service_lock_review_count": counts.get("service_lock_review_count", 0),
        "validation": {
            "ok": validation.get("ok") is True,
            "errors": validation.get("errors", []),
            "warnings": validation.get("warnings", []),
            "summary_check_ok": validation.get("summary_check_ok"),
        },
    }


def _confirms_service_lock_report(report: dict[str, Any]) -> bool:
    return (
        report["validation"]["ok"]
        and report["ready"]
        and report["read_only_report"]
        and report["status"] == "no_cost_service_lock_report_ready"
        and report["service_operation_locked"]
        and report["resume_blocked"]
        and report["service_lock_check_ok"]
        and report["aws_cost_boundary"] == "no_cost_increase"
        and not report["operation_resume_approved"]
        and not report["service_operation_allowed"]
        and not report["aws_cost_increase_allowed"]
        and not report["external_dataset_upload_authorized"]
        and not report["provider_fine_tune_api_call_authorized"]
        and not report["provider_job_creation_authorized"]
        and not report["training_execution_authorized"]
        and not report["model_promotion_authorized"]
    )


def build_training_no_cost_service_lock_report_summary(
    paths: Sequence[Path],
    *,
    generated_at: str | None = None,
    require_ready: bool = True,
) -> dict[str, Any]:
    service_lock_reports: list[dict[str, Any]] = []
    load_errors: list[dict[str, str]] = []
    for path in _expand_paths(paths):
        try:
            service_lock_reports.append(
                summarize_no_cost_service_lock_report(path, _load_json(path), require_ready=require_ready)
            )
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            load_errors.append({"path": str(path), "error": str(exc)})

    valid_count = sum(1 for report in service_lock_reports if report["validation"]["ok"])
    ready_count = sum(1 for report in service_lock_reports if _confirms_service_lock_report(report))
    invalid_count = len(service_lock_reports) - valid_count
    blocker_reasons: list[str] = []
    if load_errors:
        blocker_reasons.append("service_lock_report_load_errors")
    if not service_lock_reports:
        blocker_reasons.append("no_service_lock_reports")
    if invalid_count:
        blocker_reasons.append("invalid_service_lock_reports")
    if ready_count != len(service_lock_reports):
        blocker_reasons.append("service_lock_report_not_confirmed_for_all_reports")
    ok = not blocker_reasons
    return {
        "report_type": "report_quality_training_no_cost_service_lock_report_summary",
        "schema_version": EXPECTED_SCHEMA,
        "generated_at": generated_at or _now_iso(),
        "read_only": True,
        "require_ready": require_ready,
        "ok": ok,
        "readiness": {
            "status": "all_service_lock_reports_confirm_no_cost_service_lock" if ok else "follow_up_required",
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
            "service_lock_report_count": len(service_lock_reports),
            "valid_service_lock_report_count": valid_count,
            "invalid_service_lock_report_count": invalid_count,
            "ready_service_lock_report_count": ready_count,
            "closeout_receipt_count": sum(
                int(report.get("closeout_receipt_count") or 0) for report in service_lock_reports
            ),
            "ready_closeout_receipt_count": sum(
                int(report.get("ready_closeout_receipt_count") or 0) for report in service_lock_reports
            ),
            "final_hold_count": sum(int(report.get("final_hold_count") or 0) for report in service_lock_reports),
            "active_final_hold_count": sum(
                int(report.get("active_final_hold_count") or 0) for report in service_lock_reports
            ),
            "signoff_count": sum(int(report.get("signoff_count") or 0) for report in service_lock_reports),
            "service_lock_review_count": sum(
                int(report.get("service_lock_review_count") or 0) for report in service_lock_reports
            ),
            "load_error_count": len(load_errors),
        },
        "service_lock_reports": service_lock_reports,
        "load_errors": load_errors,
        "side_effect_boundary": {
            "reads_local_service_lock_reports": True,
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


def render_training_no_cost_service_lock_report_summary_markdown(summary: dict[str, Any]) -> str:
    counts = _as_dict(summary.get("counts"))
    readiness = _as_dict(summary.get("readiness"))
    blockers = _as_list(readiness.get("blocker_reasons"))
    reports = _as_list(summary.get("service_lock_reports"))
    rows = "\n".join(
        "| {status} | {ready} | {locked} | {blocked} | {valid} | {cost_boundary} | `{path}` |".format(
            status=report.get("status", "-"),
            ready=str(report.get("ready") is True).lower(),
            locked=str(report.get("service_operation_locked") is True).lower(),
            blocked=str(report.get("resume_blocked") is True).lower(),
            valid=str(_as_dict(report.get("validation")).get("ok") is True).lower(),
            cost_boundary=report.get("aws_cost_boundary", "-"),
            path=report.get("path", ""),
        )
        for report in reports
    )
    if not rows:
        rows = "| - | - | - | - | - | - | - |"
    blocker_text = "\n".join(f"- `{item}`" for item in blockers) if blockers else "- none"
    return f"""# Report Quality Training No-Cost Service Lock Report Summary

- generated_at: `{summary.get('generated_at', '-')}`
- status: `{readiness.get('status', '-')}`
- ok: `{str(summary.get('ok') is True).lower()}`
- service_operation_locked: `true`
- resume_blocked: `true`
- service_lock_report_count: `{counts.get('service_lock_report_count', 0)}`
- valid_service_lock_report_count: `{counts.get('valid_service_lock_report_count', 0)}`
- invalid_service_lock_report_count: `{counts.get('invalid_service_lock_report_count', 0)}`
- ready_service_lock_report_count: `{counts.get('ready_service_lock_report_count', 0)}`
- closeout_receipt_count: `{counts.get('closeout_receipt_count', 0)}`
- ready_closeout_receipt_count: `{counts.get('ready_closeout_receipt_count', 0)}`
- final_hold_count: `{counts.get('final_hold_count', 0)}`
- active_final_hold_count: `{counts.get('active_final_hold_count', 0)}`
- operation_resume_approved: `false`
- service_operation_allowed: `false`
- aws_cost_increase_allowed: `false`
- training_execution_authorized: `false`
- model_promotion_authorized: `false`

## Service Lock Reports

| status | ready | service_operation_locked | resume_blocked | valid | aws_cost_boundary | path |
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
    parser = argparse.ArgumentParser(description="Summarize report quality training no-cost service lock reports.")
    parser.add_argument(
        "service_lock_reports",
        nargs="+",
        type=Path,
        help="No-cost service lock report JSON file(s) or directories.",
    )
    parser.add_argument("--generated-at", help="Optional ISO timestamp for deterministic output.")
    parser.add_argument("--allow-not-ready", action="store_true")
    parser.add_argument("--output", type=Path, help="Optional output path for summary JSON.")
    parser.add_argument("--markdown", type=Path, help="Optional output path for summary Markdown.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable summary JSON to stdout.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(list(argv) if argv is not None else None)
    summary = build_training_no_cost_service_lock_report_summary(
        args.service_lock_reports,
        generated_at=args.generated_at,
        require_ready=not args.allow_not_ready,
    )
    summary_text = json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output:
        _write_text_atomic(args.output.expanduser().resolve(), summary_text)
    if args.markdown:
        _write_text_atomic(
            args.markdown.expanduser().resolve(),
            render_training_no_cost_service_lock_report_summary_markdown(summary),
        )

    if args.json:
        print(summary_text, end="")
    else:
        print(f"Report quality training no-cost service lock report summary: {'PASS' if summary['ok'] else 'FAIL'}")
        print(f"service_lock_report_count={summary['counts']['service_lock_report_count']}")
        print(f"valid_service_lock_report_count={summary['counts']['valid_service_lock_report_count']}")
        print(f"ready_service_lock_report_count={summary['counts']['ready_service_lock_report_count']}")
        print("service_operation_locked=true")
        print("aws_cost_boundary=no_cost_increase")
        print("training_boundary=not_authorized")
    return 0 if summary["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
