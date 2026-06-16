#!/usr/bin/env python3
"""Summarize report quality training no-cost archive closure manifests."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
from typing import Any, Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
ARCHIVE_VALIDATOR_PATH = REPO_ROOT / "scripts/validate_report_quality_review_packet_training_no_cost_archive_closure.py"
EXPECTED_SCHEMA = "decisiondoc_report_quality_training_no_cost_archive_closure_summary.v1"


def _load_archive_validator():
    spec = importlib.util.spec_from_file_location(
        "validate_report_quality_review_packet_training_no_cost_archive_closure",
        ARCHIVE_VALIDATOR_PATH,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed to load no-cost archive closure validator: {ARCHIVE_VALIDATOR_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_ARCHIVE_VALIDATOR = _load_archive_validator()


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


def summarize_no_cost_archive_closure(
    path: Path,
    payload: dict[str, Any],
    *,
    require_ready: bool = True,
) -> dict[str, Any]:
    validation = _ARCHIVE_VALIDATOR.validate_training_no_cost_archive_closure(path, require_ready=require_ready)
    closure_state = _as_dict(payload.get("closure_state"))
    counts = _as_dict(payload.get("counts"))
    return {
        "path": str(path),
        "sha256": _sha256(path),
        "schema_version": payload.get("schema_version"),
        "generated_at": payload.get("generated_at", ""),
        "status": closure_state.get("status", ""),
        "archive_only": closure_state.get("archive_only") is True,
        "aws_cost_boundary": validation.get("aws_cost_boundary", ""),
        "operation_resume_approved": closure_state.get("operation_resume_approved") is True,
        "service_operation_allowed": closure_state.get("service_operation_allowed") is True,
        "aws_cost_increase_allowed": closure_state.get("aws_cost_increase_allowed") is True,
        "provider_fine_tune_api_called": closure_state.get("provider_fine_tune_api_called") is True,
        "external_dataset_upload_started": closure_state.get("external_dataset_upload_started") is True,
        "training_execution_started": closure_state.get("training_execution_started") is True,
        "model_promotion_started": closure_state.get("model_promotion_started") is True,
        "source_file_count": counts.get("source_file_count", 0),
        "missing_file_count": counts.get("missing_file_count", 0),
        "freeze_count": counts.get("freeze_count", 0),
        "no_cost_hold_count": counts.get("no_cost_hold_count", 0),
        "validation": {
            "ok": validation.get("ok") is True,
            "errors": validation.get("errors", []),
            "warnings": validation.get("warnings", []),
            "signoff_validation_ok": validation.get("signoff_validation_ok"),
        },
    }


def build_training_no_cost_archive_closure_summary(
    paths: Sequence[Path],
    *,
    generated_at: str | None = None,
    require_ready: bool = True,
) -> dict[str, Any]:
    closures: list[dict[str, Any]] = []
    load_errors: list[dict[str, str]] = []
    for path in _expand_paths(paths):
        try:
            closures.append(summarize_no_cost_archive_closure(path, _load_json(path), require_ready=require_ready))
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            load_errors.append({"path": str(path), "error": str(exc)})

    valid_count = sum(1 for closure in closures if closure["validation"]["ok"])
    archived_hold_count = sum(
        1
        for closure in closures
        if closure["archive_only"]
        and closure["status"] == "archived_no_cost_hold"
        and closure["aws_cost_boundary"] == "no_cost_increase"
        and not closure["operation_resume_approved"]
        and not closure["service_operation_allowed"]
        and not closure["aws_cost_increase_allowed"]
        and not closure["provider_fine_tune_api_called"]
        and not closure["external_dataset_upload_started"]
        and not closure["training_execution_started"]
        and not closure["model_promotion_started"]
    )
    invalid_count = len(closures) - valid_count
    blocker_reasons: list[str] = []
    if load_errors:
        blocker_reasons.append("archive_closure_load_errors")
    if not closures:
        blocker_reasons.append("no_archive_closure_manifests")
    if invalid_count:
        blocker_reasons.append("invalid_archive_closure_manifests")
    if archived_hold_count != len(closures):
        blocker_reasons.append("archive_closure_not_confirmed_for_all_manifests")
    ok = not blocker_reasons
    return {
        "report_type": "report_quality_training_no_cost_archive_closure_summary",
        "schema_version": EXPECTED_SCHEMA,
        "generated_at": generated_at or _now_iso(),
        "read_only": True,
        "require_ready": require_ready,
        "ok": ok,
        "readiness": {
            "status": "all_archive_closures_confirm_no_cost_hold" if ok else "follow_up_required",
            "blocker_reasons": blocker_reasons,
            "operation_resume_approved": False,
            "aws_cost_increase_allowed": False,
            "service_operation_allowed": False,
            "external_dataset_upload_authorized": False,
            "provider_fine_tune_api_call_authorized": False,
            "provider_job_creation_authorized": False,
            "training_execution_authorized": False,
            "model_promotion_authorized": False,
        },
        "counts": {
            "archive_closure_count": len(closures),
            "valid_archive_closure_count": valid_count,
            "invalid_archive_closure_count": invalid_count,
            "archived_no_cost_hold_count": archived_hold_count,
            "load_error_count": len(load_errors),
        },
        "closures": closures,
        "load_errors": load_errors,
        "side_effect_boundary": {
            "reads_local_archive_closures": True,
            "writes_summary_only": True,
            "server_file_written": False,
            "persisted_learning_artifact": False,
            "operation_resume_approved": False,
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


def render_training_no_cost_archive_closure_summary_markdown(summary: dict[str, Any]) -> str:
    counts = _as_dict(summary.get("counts"))
    readiness = _as_dict(summary.get("readiness"))
    blockers = _as_list(readiness.get("blocker_reasons"))
    closures = _as_list(summary.get("closures"))
    rows = "\n".join(
        "| {status} | {valid} | {cost_boundary} | {resume} | `{path}` |".format(
            status=closure.get("status", "-"),
            valid=str(_as_dict(closure.get("validation")).get("ok") is True).lower(),
            cost_boundary=closure.get("aws_cost_boundary", "-"),
            resume=str(closure.get("operation_resume_approved") is True).lower(),
            path=closure.get("path", ""),
        )
        for closure in closures
    )
    if not rows:
        rows = "| - | - | - | - | - |"
    blocker_text = "\n".join(f"- `{item}`" for item in blockers) if blockers else "- none"
    return f"""# Report Quality Training No-Cost Archive Closure Summary

- generated_at: `{summary.get('generated_at', '-')}`
- status: `{readiness.get('status', '-')}`
- ok: `{str(summary.get('ok') is True).lower()}`
- archive_closure_count: `{counts.get('archive_closure_count', 0)}`
- valid_archive_closure_count: `{counts.get('valid_archive_closure_count', 0)}`
- invalid_archive_closure_count: `{counts.get('invalid_archive_closure_count', 0)}`
- archived_no_cost_hold_count: `{counts.get('archived_no_cost_hold_count', 0)}`
- operation_resume_approved: `false`
- aws_cost_increase_allowed: `false`
- service_operation_allowed: `false`
- training_execution_authorized: `false`
- model_promotion_authorized: `false`

## Archive Closures

| status | valid | aws_cost_boundary | operation_resume_approved | path |
| --- | --- | --- | --- | --- |
{rows}

## Blockers

{blocker_text}

## Side-Effect Boundary

- server_file_written: `false`
- persisted_learning_artifact: `false`
- operation_resume_approved: `false`
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
    parser = argparse.ArgumentParser(description="Summarize report quality training no-cost archive closures.")
    parser.add_argument("closures", nargs="+", type=Path, help="No-cost archive closure manifest JSON file(s) or directories.")
    parser.add_argument("--generated-at", help="Optional ISO timestamp for deterministic output.")
    parser.add_argument("--allow-not-ready", action="store_true")
    parser.add_argument("--output", type=Path, help="Optional output path for summary JSON.")
    parser.add_argument("--markdown", type=Path, help="Optional output path for summary Markdown.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable summary JSON to stdout.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(list(argv) if argv is not None else None)
    summary = build_training_no_cost_archive_closure_summary(
        args.closures,
        generated_at=args.generated_at,
        require_ready=not args.allow_not_ready,
    )
    summary_text = json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output:
        _write_text_atomic(args.output.expanduser().resolve(), summary_text)
    if args.markdown:
        _write_text_atomic(
            args.markdown.expanduser().resolve(),
            render_training_no_cost_archive_closure_summary_markdown(summary),
        )

    if args.json:
        print(summary_text, end="")
    else:
        print(f"Report quality training no-cost archive closure summary: {'PASS' if summary['ok'] else 'FAIL'}")
        print(f"archive_closure_count={summary['counts']['archive_closure_count']}")
        print(f"valid_archive_closure_count={summary['counts']['valid_archive_closure_count']}")
        print("aws_cost_boundary=no_cost_increase")
        print("training_boundary=not_authorized")
    return 0 if summary["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
