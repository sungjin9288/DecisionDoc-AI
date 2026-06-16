#!/usr/bin/env python3
"""Create a local no-cost ops lock from resume guard summaries."""
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
EXPECTED_SCHEMA = "decisiondoc_report_quality_training_no_cost_ops_lock.v1"
SUMMARY_SCHEMA = "decisiondoc_report_quality_training_no_cost_resume_guard_summary.v1"


def _load_module(path: Path, module_name: str):
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed to load {module_name}: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_OPS_LOCK_VALIDATOR = _load_module(
    OPS_LOCK_VALIDATOR_PATH,
    "validate_report_quality_review_packet_training_no_cost_ops_lock",
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


def _file_record(path_value: Any) -> dict[str, Any]:
    if not isinstance(path_value, str) or not path_value.strip():
        return {"path": "", "exists": False, "sha256": ""}
    path = Path(path_value).expanduser().resolve()
    exists = path.exists() and path.is_file()
    return {
        "path": str(path),
        "exists": exists,
        "sha256": _sha256(path) if exists else "",
    }


def _default_output_path(summary_path: Path, suffix: str) -> Path:
    name = summary_path.name
    if name.endswith("-training-no-cost-resume-guard-summary.json"):
        base = name.removesuffix("-training-no-cost-resume-guard-summary.json")
    else:
        base = summary_path.stem
    return summary_path.with_name(f"{base}{suffix}")


def _default_summary_markdown(summary_path: Path) -> Path | None:
    candidate = summary_path.with_suffix(".md")
    return candidate if candidate.exists() and candidate.is_file() else None


def _add_source_file(source_files: dict[str, dict[str, Any]], name: str, path_value: Any) -> None:
    record = _file_record(path_value)
    if record["path"] and all(existing.get("path") != record["path"] for existing in source_files.values()):
        source_files[name] = record


def validate_resume_guard_summary_ready(summary: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    if summary.get("schema_version") != SUMMARY_SCHEMA:
        errors.append(f"summary.schema_version must be {SUMMARY_SCHEMA!r}")
    if summary.get("report_type") != "report_quality_training_no_cost_resume_guard_summary":
        errors.append("summary.report_type must be report_quality_training_no_cost_resume_guard_summary")
    if summary.get("ok") is not True:
        errors.append("summary.ok must be true")
    if summary.get("read_only") is not True:
        errors.append("summary.read_only must be true")
    readiness = _as_dict(summary.get("readiness"))
    if readiness.get("status") != "all_resume_guards_confirm_no_cost_block":
        errors.append("summary.readiness.status must confirm no-cost resume blocks")
    if readiness.get("resume_blocked") is not True:
        errors.append("summary.readiness.resume_blocked must be true")
    for key in (
        "operation_resume_approved",
        "aws_cost_increase_allowed",
        "service_operation_allowed",
        "external_dataset_upload_authorized",
        "provider_fine_tune_api_call_authorized",
        "provider_job_creation_authorized",
        "training_execution_authorized",
        "model_promotion_authorized",
    ):
        if readiness.get(key) is not False:
            errors.append(f"summary.readiness.{key} must be false")

    counts = _as_dict(summary.get("counts"))
    resume_guard_count = counts.get("resume_guard_count")
    if not isinstance(resume_guard_count, int) or resume_guard_count < 1:
        errors.append("summary.counts.resume_guard_count must be at least 1")
    for field in ("valid_resume_guard_count", "active_resume_guard_count"):
        if counts.get(field) != resume_guard_count:
            errors.append(f"summary.counts.{field} must match resume_guard_count")
    if counts.get("invalid_resume_guard_count") != 0:
        errors.append("summary.counts.invalid_resume_guard_count must be 0")
    if counts.get("load_error_count") != 0:
        errors.append("summary.counts.load_error_count must be 0")

    boundary = _as_dict(summary.get("side_effect_boundary"))
    for key in (
        "server_file_written",
        "persisted_learning_artifact",
        "operation_resume_approved",
        "service_operation_allowed",
        "aws_deploy_started",
        "aws_resource_created",
        "aws_runtime_enabled",
        "aws_cost_increase_allowed",
        "scheduled_job_enabled",
        "cloudwatch_polling_started",
        "external_dataset_upload_started",
        "provider_fine_tune_api_called",
        "provider_job_created",
        "provider_job_polled",
        "training_execution_started",
        "model_promotion_started",
    ):
        if boundary.get(key) is not False:
            errors.append(f"summary.side_effect_boundary.{key} must be false")
    return {"ok": not errors, "errors": errors}


def create_training_no_cost_ops_lock(
    *,
    resume_guard_summary_path: Path,
    summary_markdown_path: Path | None = None,
    output_manifest: Path | None = None,
    output_markdown: Path | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    resolved_summary = resume_guard_summary_path.expanduser().resolve()
    summary = _load_json(resolved_summary)
    summary_validation = validate_resume_guard_summary_ready(summary)
    if summary_validation["ok"] is not True:
        raise ValueError(
            "no-cost resume guard summary is not ready for ops lock: "
            + "; ".join(summary_validation["errors"])
        )

    resolved_summary_markdown = (
        summary_markdown_path.expanduser().resolve()
        if summary_markdown_path is not None
        else _default_summary_markdown(resolved_summary)
    )
    output_manifest = (
        output_manifest.expanduser().resolve()
        if output_manifest is not None
        else _default_output_path(resolved_summary, "-training-no-cost-ops-lock-manifest.json")
    )
    output_markdown = (
        output_markdown.expanduser().resolve()
        if output_markdown is not None
        else _default_output_path(resolved_summary, "-training-no-cost-ops-lock.md")
    )

    source_files: dict[str, dict[str, Any]] = {
        "resume_guard_summary_json": _file_record(str(resolved_summary)),
    }
    if resolved_summary_markdown is not None:
        _add_source_file(source_files, "resume_guard_summary_markdown", str(resolved_summary_markdown))
    for index, guard in enumerate(_as_list(summary.get("guards")), start=1):
        guard_payload = _as_dict(guard)
        _add_source_file(source_files, f"resume_guard_manifest_{index}", guard_payload.get("path"))
    missing_files = sorted(name for name, record in source_files.items() if record.get("exists") is not True)
    counts = _as_dict(summary.get("counts"))

    ops_lock = {
        "report_type": "report_quality_training_no_cost_ops_lock",
        "schema_version": EXPECTED_SCHEMA,
        "generated_at": generated_at or _now_iso(),
        "ops_lock_manifest_path": str(output_manifest),
        "ops_lock_markdown_path": str(output_markdown),
        "resume_guard_summary_path": str(resolved_summary),
        "resume_guard_summary_sha256": _sha256(resolved_summary),
        "summary_validation": summary_validation,
        "lock_state": {
            "ok": True,
            "status": "no_cost_ops_lock_active",
            "lock_only": True,
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
            "resume_guard_count": counts.get("resume_guard_count", 0),
            "valid_resume_guard_count": counts.get("valid_resume_guard_count", 0),
            "active_resume_guard_count": counts.get("active_resume_guard_count", 0),
            "source_file_count": len(source_files),
            "missing_file_count": len(missing_files),
        },
        "source_files": source_files,
        "lock_controls": [
            "Keep service operation disabled unless a separate resume approval artifact is created.",
            "Do not deploy AWS resources, enable runtime services, scheduled jobs, or CloudWatch polling from this lock.",
            "Do not call provider APIs, upload datasets, create provider jobs, or poll provider jobs from this lock.",
            "Do not start training execution or promote models from this lock.",
        ],
        "unlock_prerequisites": [
            "Separate human approval explicitly granting service resume.",
            "AWS budget review, cost cap confirmation, and owner acknowledgement.",
            "Provider approval for any dataset upload, provider job creation, or fine-tune API call.",
            "Offline eval plan, rollback plan, and model promotion approval recorded in a new approval artifact.",
            "A new implementation task that intentionally changes this lock state from blocked to approved.",
        ],
        "lock_boundary": {
            "reads_local_resume_guard_summary": True,
            "writes_local_ops_lock_files": True,
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
    _write_text_atomic(output_manifest, json.dumps(ops_lock, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    _write_text_atomic(output_markdown, render_training_no_cost_ops_lock_markdown(ops_lock))
    return ops_lock


def render_training_no_cost_ops_lock_markdown(ops_lock: dict[str, Any]) -> str:
    lock_state = _as_dict(ops_lock.get("lock_state"))
    counts = _as_dict(ops_lock.get("counts"))
    source_files = _as_dict(ops_lock.get("source_files"))
    rows = "\n".join(
        "| {name} | {exists} | `{path}` |".format(
            name=name,
            exists="yes" if _as_dict(record).get("exists") else "no",
            path=_as_dict(record).get("path", ""),
        )
        for name, record in source_files.items()
    )
    if not rows:
        rows = "| - | - | - |"
    return f"""# Report Quality Training No-Cost Ops Lock

- generated_at: `{ops_lock.get('generated_at', '-')}`
- status: `{lock_state.get('status', '-')}`
- ops_lock_active: `{str(lock_state.get('ok') is True).lower()}`
- lock_only: `true`
- service_operation_locked: `true`
- resume_blocked: `true`
- resume_guard_count: `{counts.get('resume_guard_count', 0)}`
- valid_resume_guard_count: `{counts.get('valid_resume_guard_count', 0)}`
- active_resume_guard_count: `{counts.get('active_resume_guard_count', 0)}`
- operation_resume_approved: `false`
- service_operation_allowed: `false`
- aws_cost_increase_allowed: `false`
- provider_fine_tune_api_call_authorized: `false`
- external_dataset_upload_authorized: `false`
- training_execution_authorized: `false`
- model_promotion_authorized: `false`

## Lock Controls

{chr(10).join(f"- {item}" for item in ops_lock.get('lock_controls', []))}

## Unlock Prerequisites

{chr(10).join(f"- {item}" for item in ops_lock.get('unlock_prerequisites', []))}

## Source Files

| file | exists | path |
| --- | --- | --- |
{rows}

## Lock Boundary

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
    parser = argparse.ArgumentParser(description="Create a local no-cost ops lock manifest.")
    parser.add_argument(
        "resume_guard_summary",
        type=Path,
        help="Path to *-training-no-cost-resume-guard-summary.json.",
    )
    parser.add_argument("--summary-markdown", type=Path, default=None)
    parser.add_argument("--output-manifest", type=Path, default=None)
    parser.add_argument("--output-markdown", type=Path, default=None)
    parser.add_argument("--generated-at", help="Optional ISO timestamp for deterministic output.")
    parser.add_argument("--json", action="store_true", help="Print generated ops lock manifest JSON to stdout.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(list(argv) if argv is not None else None)
    try:
        ops_lock = create_training_no_cost_ops_lock(
            resume_guard_summary_path=args.resume_guard_summary,
            summary_markdown_path=args.summary_markdown,
            output_manifest=args.output_manifest,
            output_markdown=args.output_markdown,
            generated_at=args.generated_at,
        )
        validation = _OPS_LOCK_VALIDATOR.validate_training_no_cost_ops_lock(
            Path(ops_lock["ops_lock_manifest_path"]),
        )
    except Exception as exc:
        result = {"ok": False, "error": str(exc)}
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        else:
            print("FAIL report quality training no-cost ops lock generation failed")
            print(f"ERROR {exc}")
        return 1

    if args.json:
        print(json.dumps(ops_lock, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print("Report quality training no-cost ops lock: PASS")
        print(f"ops_lock_active={str(ops_lock['lock_state']['ok']).lower()}")
        print(f"service_operation_locked={str(ops_lock['lock_state']['service_operation_locked']).lower()}")
        print(f"resume_blocked={str(ops_lock['lock_state']['resume_blocked']).lower()}")
        print("aws_cost_boundary=no_cost_increase")
        print("training_boundary=not_authorized")
    return 0 if validation["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
