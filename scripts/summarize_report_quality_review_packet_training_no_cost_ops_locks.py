#!/usr/bin/env python3
"""Summarize report quality training no-cost ops lock manifests."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
from typing import Any, Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
OPS_LOCK_VALIDATOR_PATH = REPO_ROOT / "scripts/validate_report_quality_review_packet_training_no_cost_ops_lock.py"
EXPECTED_SCHEMA = "decisiondoc_report_quality_training_no_cost_ops_lock_summary.v1"


def _load_ops_lock_validator():
    spec = importlib.util.spec_from_file_location(
        "validate_report_quality_review_packet_training_no_cost_ops_lock",
        OPS_LOCK_VALIDATOR_PATH,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed to load no-cost ops lock validator: {OPS_LOCK_VALIDATOR_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_OPS_LOCK_VALIDATOR = _load_ops_lock_validator()


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
    tmp = path.with_name(f"{path.name}.tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


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


def summarize_no_cost_ops_lock(
    path: Path,
    payload: dict[str, Any],
    *,
    require_ready: bool = True,
) -> dict[str, Any]:
    validation = _OPS_LOCK_VALIDATOR.validate_training_no_cost_ops_lock(path, require_ready=require_ready)
    lock_state = _as_dict(payload.get("lock_state"))
    counts = _as_dict(payload.get("counts"))
    return {
        "path": str(path),
        "sha256": _sha256(path),
        "schema_version": payload.get("schema_version"),
        "generated_at": payload.get("generated_at", ""),
        "status": lock_state.get("status", ""),
        "lock_only": lock_state.get("lock_only") is True,
        "service_operation_locked": lock_state.get("service_operation_locked") is True,
        "resume_blocked": lock_state.get("resume_blocked") is True,
        "aws_cost_boundary": validation.get("aws_cost_boundary", ""),
        "operation_resume_approved": lock_state.get("operation_resume_approved") is True,
        "service_operation_allowed": lock_state.get("service_operation_allowed") is True,
        "aws_cost_increase_allowed": lock_state.get("aws_cost_increase_allowed") is True,
        "provider_fine_tune_api_call_authorized": lock_state.get(
            "provider_fine_tune_api_call_authorized"
        )
        is True,
        "external_dataset_upload_authorized": lock_state.get("external_dataset_upload_authorized") is True,
        "training_execution_authorized": lock_state.get("training_execution_authorized") is True,
        "model_promotion_authorized": lock_state.get("model_promotion_authorized") is True,
        "source_file_count": counts.get("source_file_count", 0),
        "missing_file_count": counts.get("missing_file_count", 0),
        "resume_guard_count": counts.get("resume_guard_count", 0),
        "active_resume_guard_count": counts.get("active_resume_guard_count", 0),
        "validation": {
            "ok": validation.get("ok") is True,
            "errors": validation.get("errors", []),
            "warnings": validation.get("warnings", []),
            "summary_validation_ok": validation.get("summary_validation_ok"),
        },
    }


def build_training_no_cost_ops_lock_summary(
    paths: Sequence[Path],
    *,
    generated_at: str | None = None,
    require_ready: bool = True,
) -> dict[str, Any]:
    ops_locks: list[dict[str, Any]] = []
    load_errors: list[dict[str, str]] = []
    for path in _expand_paths(paths):
        try:
            ops_locks.append(summarize_no_cost_ops_lock(path, _load_json(path), require_ready=require_ready))
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            load_errors.append({"path": str(path), "error": str(exc)})

    valid_count = sum(1 for ops_lock in ops_locks if ops_lock["validation"]["ok"])
    active_lock_count = sum(
        1
        for ops_lock in ops_locks
        if ops_lock["validation"]["ok"]
        and ops_lock["lock_only"]
        and ops_lock["status"] == "no_cost_ops_lock_active"
        and ops_lock["service_operation_locked"]
        and ops_lock["resume_blocked"]
        and ops_lock["aws_cost_boundary"] == "no_cost_increase"
        and not ops_lock["operation_resume_approved"]
        and not ops_lock["service_operation_allowed"]
        and not ops_lock["aws_cost_increase_allowed"]
        and not ops_lock["provider_fine_tune_api_call_authorized"]
        and not ops_lock["external_dataset_upload_authorized"]
        and not ops_lock["training_execution_authorized"]
        and not ops_lock["model_promotion_authorized"]
    )
    invalid_count = len(ops_locks) - valid_count
    blocker_reasons: list[str] = []
    if load_errors:
        blocker_reasons.append("ops_lock_load_errors")
    if not ops_locks:
        blocker_reasons.append("no_ops_lock_manifests")
    if invalid_count:
        blocker_reasons.append("invalid_ops_lock_manifests")
    if active_lock_count != len(ops_locks):
        blocker_reasons.append("ops_lock_not_confirmed_for_all_manifests")
    ok = not blocker_reasons
    return {
        "report_type": "report_quality_training_no_cost_ops_lock_summary",
        "schema_version": EXPECTED_SCHEMA,
        "generated_at": generated_at or _now_iso(),
        "read_only": True,
        "require_ready": require_ready,
        "ok": ok,
        "readiness": {
            "status": "all_ops_locks_confirm_no_cost_service_lock" if ok else "follow_up_required",
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
            "ops_lock_count": len(ops_locks),
            "valid_ops_lock_count": valid_count,
            "invalid_ops_lock_count": invalid_count,
            "active_ops_lock_count": active_lock_count,
            "load_error_count": len(load_errors),
        },
        "ops_locks": ops_locks,
        "load_errors": load_errors,
        "side_effect_boundary": {
            "reads_local_ops_locks": True,
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


def render_training_no_cost_ops_lock_summary_markdown(summary: dict[str, Any]) -> str:
    counts = _as_dict(summary.get("counts"))
    readiness = _as_dict(summary.get("readiness"))
    blockers = _as_list(readiness.get("blocker_reasons"))
    ops_locks = _as_list(summary.get("ops_locks"))
    rows = "\n".join(
        "| {status} | {locked} | {blocked} | {valid} | {cost_boundary} | `{path}` |".format(
            status=ops_lock.get("status", "-"),
            locked=str(ops_lock.get("service_operation_locked") is True).lower(),
            blocked=str(ops_lock.get("resume_blocked") is True).lower(),
            valid=str(_as_dict(ops_lock.get("validation")).get("ok") is True).lower(),
            cost_boundary=ops_lock.get("aws_cost_boundary", "-"),
            path=ops_lock.get("path", ""),
        )
        for ops_lock in ops_locks
    )
    if not rows:
        rows = "| - | - | - | - | - | - |"
    blocker_text = "\n".join(f"- `{item}`" for item in blockers) if blockers else "- none"
    return f"""# Report Quality Training No-Cost Ops Lock Summary

- generated_at: `{summary.get('generated_at', '-')}`
- status: `{readiness.get('status', '-')}`
- ok: `{str(summary.get('ok') is True).lower()}`
- service_operation_locked: `true`
- resume_blocked: `true`
- ops_lock_count: `{counts.get('ops_lock_count', 0)}`
- valid_ops_lock_count: `{counts.get('valid_ops_lock_count', 0)}`
- invalid_ops_lock_count: `{counts.get('invalid_ops_lock_count', 0)}`
- active_ops_lock_count: `{counts.get('active_ops_lock_count', 0)}`
- operation_resume_approved: `false`
- service_operation_allowed: `false`
- aws_cost_increase_allowed: `false`
- training_execution_authorized: `false`
- model_promotion_authorized: `false`

## Ops Locks

| status | service_operation_locked | resume_blocked | valid | aws_cost_boundary | path |
| --- | --- | --- | --- | --- | --- |
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
    parser = argparse.ArgumentParser(description="Summarize report quality training no-cost ops locks.")
    parser.add_argument("ops_locks", nargs="+", type=Path, help="No-cost ops lock manifest JSON file(s) or directories.")
    parser.add_argument("--generated-at", help="Optional ISO timestamp for deterministic output.")
    parser.add_argument("--allow-not-ready", action="store_true")
    parser.add_argument("--output", type=Path, help="Optional output path for summary JSON.")
    parser.add_argument("--markdown", type=Path, help="Optional output path for summary Markdown.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable summary JSON to stdout.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(list(argv) if argv is not None else None)
    summary = build_training_no_cost_ops_lock_summary(
        args.ops_locks,
        generated_at=args.generated_at,
        require_ready=not args.allow_not_ready,
    )
    summary_text = json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output:
        _write_text_atomic(args.output.expanduser().resolve(), summary_text)
    if args.markdown:
        _write_text_atomic(
            args.markdown.expanduser().resolve(),
            render_training_no_cost_ops_lock_summary_markdown(summary),
        )

    if args.json:
        print(summary_text, end="")
    else:
        print(f"Report quality training no-cost ops lock summary: {'PASS' if summary['ok'] else 'FAIL'}")
        print(f"ops_lock_count={summary['counts']['ops_lock_count']}")
        print(f"valid_ops_lock_count={summary['counts']['valid_ops_lock_count']}")
        print(f"active_ops_lock_count={summary['counts']['active_ops_lock_count']}")
        print("service_operation_locked=true")
        print("aws_cost_boundary=no_cost_increase")
        print("training_boundary=not_authorized")
    return 0 if summary["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
