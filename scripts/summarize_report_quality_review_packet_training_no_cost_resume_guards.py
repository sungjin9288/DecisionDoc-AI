#!/usr/bin/env python3
"""Summarize report quality training no-cost resume guard manifests."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
from typing import Any, Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
GUARD_VALIDATOR_PATH = REPO_ROOT / "scripts/validate_report_quality_review_packet_training_no_cost_resume_guard.py"
EXPECTED_SCHEMA = "decisiondoc_report_quality_training_no_cost_resume_guard_summary.v1"


def _load_guard_validator():
    spec = importlib.util.spec_from_file_location(
        "validate_report_quality_review_packet_training_no_cost_resume_guard",
        GUARD_VALIDATOR_PATH,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed to load no-cost resume guard validator: {GUARD_VALIDATOR_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_GUARD_VALIDATOR = _load_guard_validator()


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


def summarize_no_cost_resume_guard(
    path: Path,
    payload: dict[str, Any],
    *,
    require_ready: bool = True,
) -> dict[str, Any]:
    validation = _GUARD_VALIDATOR.validate_training_no_cost_resume_guard(path, require_ready=require_ready)
    guard_state = _as_dict(payload.get("guard_state"))
    counts = _as_dict(payload.get("counts"))
    return {
        "path": str(path),
        "sha256": _sha256(path),
        "schema_version": payload.get("schema_version"),
        "generated_at": payload.get("generated_at", ""),
        "status": guard_state.get("status", ""),
        "guard_only": guard_state.get("guard_only") is True,
        "resume_blocked": guard_state.get("resume_blocked") is True,
        "aws_cost_boundary": validation.get("aws_cost_boundary", ""),
        "operation_resume_approved": guard_state.get("operation_resume_approved") is True,
        "service_operation_allowed": guard_state.get("service_operation_allowed") is True,
        "aws_cost_increase_allowed": guard_state.get("aws_cost_increase_allowed") is True,
        "provider_fine_tune_api_call_authorized": guard_state.get(
            "provider_fine_tune_api_call_authorized"
        )
        is True,
        "external_dataset_upload_authorized": guard_state.get("external_dataset_upload_authorized") is True,
        "training_execution_authorized": guard_state.get("training_execution_authorized") is True,
        "model_promotion_authorized": guard_state.get("model_promotion_authorized") is True,
        "source_file_count": counts.get("source_file_count", 0),
        "missing_file_count": counts.get("missing_file_count", 0),
        "signoff_count": counts.get("signoff_count", 0),
        "archive_only_review_count": counts.get("archive_only_review_count", 0),
        "validation": {
            "ok": validation.get("ok") is True,
            "errors": validation.get("errors", []),
            "warnings": validation.get("warnings", []),
            "summary_validation_ok": validation.get("summary_validation_ok"),
        },
    }


def build_training_no_cost_resume_guard_summary(
    paths: Sequence[Path],
    *,
    generated_at: str | None = None,
    require_ready: bool = True,
) -> dict[str, Any]:
    guards: list[dict[str, Any]] = []
    load_errors: list[dict[str, str]] = []
    for path in _expand_paths(paths):
        try:
            guards.append(summarize_no_cost_resume_guard(path, _load_json(path), require_ready=require_ready))
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            load_errors.append({"path": str(path), "error": str(exc)})

    valid_count = sum(1 for guard in guards if guard["validation"]["ok"])
    active_guard_count = sum(
        1
        for guard in guards
        if guard["validation"]["ok"]
        and guard["guard_only"]
        and guard["status"] == "no_cost_resume_guard_active"
        and guard["resume_blocked"]
        and guard["aws_cost_boundary"] == "no_cost_increase"
        and not guard["operation_resume_approved"]
        and not guard["service_operation_allowed"]
        and not guard["aws_cost_increase_allowed"]
        and not guard["provider_fine_tune_api_call_authorized"]
        and not guard["external_dataset_upload_authorized"]
        and not guard["training_execution_authorized"]
        and not guard["model_promotion_authorized"]
    )
    invalid_count = len(guards) - valid_count
    blocker_reasons: list[str] = []
    if load_errors:
        blocker_reasons.append("resume_guard_load_errors")
    if not guards:
        blocker_reasons.append("no_resume_guard_manifests")
    if invalid_count:
        blocker_reasons.append("invalid_resume_guard_manifests")
    if active_guard_count != len(guards):
        blocker_reasons.append("resume_guard_not_confirmed_for_all_manifests")
    ok = not blocker_reasons
    return {
        "report_type": "report_quality_training_no_cost_resume_guard_summary",
        "schema_version": EXPECTED_SCHEMA,
        "generated_at": generated_at or _now_iso(),
        "read_only": True,
        "require_ready": require_ready,
        "ok": ok,
        "readiness": {
            "status": "all_resume_guards_confirm_no_cost_block" if ok else "follow_up_required",
            "blocker_reasons": blocker_reasons,
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
            "resume_guard_count": len(guards),
            "valid_resume_guard_count": valid_count,
            "invalid_resume_guard_count": invalid_count,
            "active_resume_guard_count": active_guard_count,
            "load_error_count": len(load_errors),
        },
        "guards": guards,
        "load_errors": load_errors,
        "side_effect_boundary": {
            "reads_local_resume_guards": True,
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


def render_training_no_cost_resume_guard_summary_markdown(summary: dict[str, Any]) -> str:
    counts = _as_dict(summary.get("counts"))
    readiness = _as_dict(summary.get("readiness"))
    blockers = _as_list(readiness.get("blocker_reasons"))
    guards = _as_list(summary.get("guards"))
    rows = "\n".join(
        "| {status} | {blocked} | {valid} | {cost_boundary} | `{path}` |".format(
            status=guard.get("status", "-"),
            blocked=str(guard.get("resume_blocked") is True).lower(),
            valid=str(_as_dict(guard.get("validation")).get("ok") is True).lower(),
            cost_boundary=guard.get("aws_cost_boundary", "-"),
            path=guard.get("path", ""),
        )
        for guard in guards
    )
    if not rows:
        rows = "| - | - | - | - | - |"
    blocker_text = "\n".join(f"- `{item}`" for item in blockers) if blockers else "- none"
    return f"""# Report Quality Training No-Cost Resume Guard Summary

- generated_at: `{summary.get('generated_at', '-')}`
- status: `{readiness.get('status', '-')}`
- ok: `{str(summary.get('ok') is True).lower()}`
- resume_blocked: `true`
- resume_guard_count: `{counts.get('resume_guard_count', 0)}`
- valid_resume_guard_count: `{counts.get('valid_resume_guard_count', 0)}`
- invalid_resume_guard_count: `{counts.get('invalid_resume_guard_count', 0)}`
- active_resume_guard_count: `{counts.get('active_resume_guard_count', 0)}`
- operation_resume_approved: `false`
- service_operation_allowed: `false`
- aws_cost_increase_allowed: `false`
- training_execution_authorized: `false`
- model_promotion_authorized: `false`

## Resume Guards

| status | resume_blocked | valid | aws_cost_boundary | path |
| --- | --- | --- | --- | --- |
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
    parser = argparse.ArgumentParser(description="Summarize report quality training no-cost resume guards.")
    parser.add_argument("guards", nargs="+", type=Path, help="No-cost resume guard manifest JSON file(s) or directories.")
    parser.add_argument("--generated-at", help="Optional ISO timestamp for deterministic output.")
    parser.add_argument("--allow-not-ready", action="store_true")
    parser.add_argument("--output", type=Path, help="Optional output path for summary JSON.")
    parser.add_argument("--markdown", type=Path, help="Optional output path for summary Markdown.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable summary JSON to stdout.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(list(argv) if argv is not None else None)
    summary = build_training_no_cost_resume_guard_summary(
        args.guards,
        generated_at=args.generated_at,
        require_ready=not args.allow_not_ready,
    )
    summary_text = json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output:
        _write_text_atomic(args.output.expanduser().resolve(), summary_text)
    if args.markdown:
        _write_text_atomic(
            args.markdown.expanduser().resolve(),
            render_training_no_cost_resume_guard_summary_markdown(summary),
        )

    if args.json:
        print(summary_text, end="")
    else:
        print(f"Report quality training no-cost resume guard summary: {'PASS' if summary['ok'] else 'FAIL'}")
        print(f"resume_guard_count={summary['counts']['resume_guard_count']}")
        print(f"valid_resume_guard_count={summary['counts']['valid_resume_guard_count']}")
        print(f"active_resume_guard_count={summary['counts']['active_resume_guard_count']}")
        print("aws_cost_boundary=no_cost_increase")
        print("training_boundary=not_authorized")
    return 0 if summary["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
