#!/usr/bin/env python3
"""Summarize report quality training no-cost operator handoff closeout packages."""
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
CLOSEOUT_PACKAGE_VALIDATOR_PATH = (
    REPO_ROOT / "scripts/validate_report_quality_review_packet_training_no_cost_operator_handoff_closeout_package.py"
)
EXPECTED_SCHEMA = "decisiondoc_report_quality_training_no_cost_operator_handoff_closeout_package_summary.v1"


def _load_closeout_package_validator():
    spec = importlib.util.spec_from_file_location(
        "validate_report_quality_review_packet_training_no_cost_operator_handoff_closeout_package",
        CLOSEOUT_PACKAGE_VALIDATOR_PATH,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed to load no-cost operator handoff closeout package validator: {CLOSEOUT_PACKAGE_VALIDATOR_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_CLOSEOUT_PACKAGE_VALIDATOR = _load_closeout_package_validator()


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


def summarize_no_cost_operator_handoff_closeout_package(
    path: Path,
    payload: dict[str, Any],
    *,
    require_ready: bool = True,
) -> dict[str, Any]:
    validation = _CLOSEOUT_PACKAGE_VALIDATOR.validate_training_no_cost_operator_handoff_closeout_package(
        path,
        require_ready=require_ready,
    )
    package_state = _as_dict(payload.get("package_state"))
    counts = _as_dict(payload.get("counts"))
    return {
        "path": str(path),
        "sha256": _sha256(path),
        "schema_version": payload.get("schema_version"),
        "generated_at": payload.get("generated_at", ""),
        "status": package_state.get("status", ""),
        "ready": package_state.get("ready") is True,
        "package_only": package_state.get("package_only") is True,
        "service_operation_locked": package_state.get("service_operation_locked") is True,
        "resume_blocked": package_state.get("resume_blocked") is True,
        "aws_cost_boundary": validation.get("aws_cost_boundary", ""),
        "operation_resume_approved": package_state.get("operation_resume_approved") is True,
        "service_operation_allowed": package_state.get("service_operation_allowed") is True,
        "aws_cost_increase_allowed": package_state.get("aws_cost_increase_allowed") is True,
        "external_dataset_upload_authorized": (
            package_state.get("external_dataset_upload_authorized") is True
        ),
        "provider_fine_tune_api_call_authorized": (
            package_state.get("provider_fine_tune_api_call_authorized") is True
        ),
        "provider_job_creation_authorized": package_state.get("provider_job_creation_authorized") is True,
        "training_execution_authorized": package_state.get("training_execution_authorized") is True,
        "model_promotion_authorized": package_state.get("model_promotion_authorized") is True,
        "receipt_count": counts.get("receipt_count", 0),
        "valid_receipt_count": counts.get("valid_receipt_count", 0),
        "ready_receipt_count": counts.get("ready_receipt_count", 0),
        "signoff_count": counts.get("signoff_count", 0),
        "operator_handoff_review_count": counts.get("operator_handoff_review_count", 0),
        "package_source_file_count": counts.get("package_source_file_count", 0),
        "package_missing_file_count": counts.get("package_missing_file_count", 0),
        "validation": {
            "ok": validation.get("ok") is True,
            "errors": validation.get("errors", []),
            "warnings": validation.get("warnings", []),
            "summary_validation_ok": validation.get("summary_validation_ok"),
        },
    }


def _confirms_operator_handoff_closeout_package(package: dict[str, Any]) -> bool:
    return (
        package["validation"]["ok"]
        and package["ready"]
        and package["package_only"]
        and package["status"] == "no_cost_operator_handoff_closeout_package_ready"
        and package["service_operation_locked"]
        and package["resume_blocked"]
        and package["aws_cost_boundary"] == "no_cost_increase"
        and not package["operation_resume_approved"]
        and not package["service_operation_allowed"]
        and not package["aws_cost_increase_allowed"]
        and not package["external_dataset_upload_authorized"]
        and not package["provider_fine_tune_api_call_authorized"]
        and not package["provider_job_creation_authorized"]
        and not package["training_execution_authorized"]
        and not package["model_promotion_authorized"]
    )


def build_training_no_cost_operator_handoff_closeout_package_summary(
    paths: Sequence[Path],
    *,
    generated_at: str | None = None,
    require_ready: bool = True,
) -> dict[str, Any]:
    packages: list[dict[str, Any]] = []
    load_errors: list[dict[str, str]] = []
    for path in _expand_paths(paths):
        try:
            packages.append(
                summarize_no_cost_operator_handoff_closeout_package(
                    path,
                    _load_json(path),
                    require_ready=require_ready,
                )
            )
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            load_errors.append({"path": str(path), "error": str(exc)})

    valid_count = sum(1 for package in packages if package["validation"]["ok"])
    ready_count = sum(1 for package in packages if _confirms_operator_handoff_closeout_package(package))
    invalid_count = len(packages) - valid_count
    blocker_reasons: list[str] = []
    if load_errors:
        blocker_reasons.append("operator_handoff_closeout_package_load_errors")
    if not packages:
        blocker_reasons.append("no_operator_handoff_closeout_packages")
    if invalid_count:
        blocker_reasons.append("invalid_operator_handoff_closeout_packages")
    if ready_count != len(packages):
        blocker_reasons.append("operator_handoff_closeout_package_not_confirmed_for_all_packages")
    ok = not blocker_reasons
    return {
        "report_type": "report_quality_training_no_cost_operator_handoff_closeout_package_summary",
        "schema_version": EXPECTED_SCHEMA,
        "generated_at": generated_at or _now_iso(),
        "read_only": True,
        "require_ready": require_ready,
        "ok": ok,
        "readiness": {
            "status": "all_operator_handoff_closeout_packages_confirm_service_lock"
            if ok
            else "follow_up_required",
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
            "package_count": len(packages),
            "valid_package_count": valid_count,
            "invalid_package_count": invalid_count,
            "ready_package_count": ready_count,
            "receipt_count": sum(int(package.get("receipt_count") or 0) for package in packages),
            "valid_receipt_count": sum(int(package.get("valid_receipt_count") or 0) for package in packages),
            "ready_receipt_count": sum(int(package.get("ready_receipt_count") or 0) for package in packages),
            "signoff_count": sum(int(package.get("signoff_count") or 0) for package in packages),
            "operator_handoff_review_count": sum(
                int(package.get("operator_handoff_review_count") or 0) for package in packages
            ),
            "package_source_file_count": sum(
                int(package.get("package_source_file_count") or 0) for package in packages
            ),
            "package_missing_file_count": sum(
                int(package.get("package_missing_file_count") or 0) for package in packages
            ),
            "load_error_count": len(load_errors),
        },
        "packages": packages,
        "load_errors": load_errors,
        "side_effect_boundary": {
            "reads_local_operator_handoff_closeout_packages": True,
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


def render_training_no_cost_operator_handoff_closeout_package_summary_markdown(
    summary: dict[str, Any],
) -> str:
    counts = _as_dict(summary.get("counts"))
    readiness = _as_dict(summary.get("readiness"))
    blockers = _as_list(readiness.get("blocker_reasons"))
    packages = _as_list(summary.get("packages"))
    rows = "\n".join(
        "| {status} | {ready} | {locked} | {blocked} | {valid} | {cost_boundary} | `{path}` |".format(
            status=package.get("status", "-"),
            ready=str(package.get("ready") is True).lower(),
            locked=str(package.get("service_operation_locked") is True).lower(),
            blocked=str(package.get("resume_blocked") is True).lower(),
            valid=str(_as_dict(package.get("validation")).get("ok") is True).lower(),
            cost_boundary=package.get("aws_cost_boundary", "-"),
            path=package.get("path", ""),
        )
        for package in packages
    )
    if not rows:
        rows = "| - | - | - | - | - | - | - |"
    blocker_text = "\n".join(f"- `{item}`" for item in blockers) if blockers else "- none"
    return f"""# Report Quality Training No-Cost Operator Handoff Closeout Package Summary

- generated_at: `{summary.get('generated_at', '-')}`
- status: `{readiness.get('status', '-')}`
- ok: `{str(summary.get('ok') is True).lower()}`
- service_operation_locked: `true`
- resume_blocked: `true`
- package_count: `{counts.get('package_count', 0)}`
- valid_package_count: `{counts.get('valid_package_count', 0)}`
- invalid_package_count: `{counts.get('invalid_package_count', 0)}`
- ready_package_count: `{counts.get('ready_package_count', 0)}`
- receipt_count: `{counts.get('receipt_count', 0)}`
- ready_receipt_count: `{counts.get('ready_receipt_count', 0)}`
- signoff_count: `{counts.get('signoff_count', 0)}`
- operator_handoff_review_count: `{counts.get('operator_handoff_review_count', 0)}`
- operation_resume_approved: `false`
- service_operation_allowed: `false`
- aws_cost_increase_allowed: `false`
- provider_fine_tune_api_call_authorized: `false`
- external_dataset_upload_authorized: `false`
- training_execution_authorized: `false`
- model_promotion_authorized: `false`

## Operator Handoff Closeout Packages

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
    parser = argparse.ArgumentParser(
        description="Summarize report quality training no-cost operator handoff closeout packages."
    )
    parser.add_argument(
        "operator_handoff_closeout_packages",
        nargs="+",
        type=Path,
        help="No-cost operator handoff closeout package manifest JSON file(s) or directories.",
    )
    parser.add_argument("--generated-at", help="Optional ISO timestamp for deterministic output.")
    parser.add_argument("--allow-not-ready", action="store_true")
    parser.add_argument("--output", type=Path, help="Optional output path for summary JSON.")
    parser.add_argument("--markdown", type=Path, help="Optional output path for summary Markdown.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable summary JSON to stdout.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(list(argv) if argv is not None else None)
    summary = build_training_no_cost_operator_handoff_closeout_package_summary(
        args.operator_handoff_closeout_packages,
        generated_at=args.generated_at,
        require_ready=not args.allow_not_ready,
    )
    summary_text = json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output:
        _write_text_atomic(args.output.expanduser().resolve(), summary_text)
    if args.markdown:
        _write_text_atomic(
            args.markdown.expanduser().resolve(),
            render_training_no_cost_operator_handoff_closeout_package_summary_markdown(summary),
        )

    if args.json:
        print(summary_text, end="")
    else:
        print(
            "Report quality training no-cost operator handoff closeout package summary: "
            f"{'PASS' if summary['ok'] else 'FAIL'}"
        )
        print(f"package_count={summary['counts']['package_count']}")
        print(f"valid_package_count={summary['counts']['valid_package_count']}")
        print(f"ready_package_count={summary['counts']['ready_package_count']}")
        print("service_operation_locked=true")
        print("aws_cost_boundary=no_cost_increase")
        print("training_boundary=not_authorized")
    return 0 if summary["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
