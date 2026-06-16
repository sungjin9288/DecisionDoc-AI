#!/usr/bin/env python3
"""Create a no-cost operator handoff closeout package from a validated receipt summary."""
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
SUMMARY_VALIDATOR_PATH = (
    REPO_ROOT
    / "scripts/validate_report_quality_review_packet_training_no_cost_operator_handoff_closeout_receipt_summary.py"
)
EXPECTED_SCHEMA = "decisiondoc_report_quality_training_no_cost_operator_handoff_closeout_package.v1"


def _load_summary_validator():
    spec = importlib.util.spec_from_file_location(
        "validate_report_quality_review_packet_training_no_cost_operator_handoff_closeout_receipt_summary",
        SUMMARY_VALIDATOR_PATH,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed to load no-cost operator handoff closeout summary validator: {SUMMARY_VALIDATOR_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_SUMMARY_VALIDATOR = _load_summary_validator()


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
    if name.endswith("-training-no-cost-operator-handoff-closeout-receipt-summary.json"):
        base = name.removesuffix("-training-no-cost-operator-handoff-closeout-receipt-summary.json")
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


def create_training_no_cost_operator_handoff_closeout_package(
    *,
    operator_handoff_closeout_receipt_summary_path: Path,
    summary_markdown_path: Path | None = None,
    output_manifest: Path | None = None,
    output_markdown: Path | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    resolved_summary = operator_handoff_closeout_receipt_summary_path.expanduser().resolve()
    summary = _load_json(resolved_summary)
    summary_validation = (
        _SUMMARY_VALIDATOR.validate_training_no_cost_operator_handoff_closeout_receipt_summary(resolved_summary)
    )
    if summary_validation["ok"] is not True:
        raise ValueError(
            "no-cost operator handoff closeout receipt summary validation failed: "
            + "; ".join(str(error) for error in summary_validation["errors"])
        )

    resolved_summary_markdown = (
        summary_markdown_path.expanduser().resolve()
        if summary_markdown_path is not None
        else _default_summary_markdown(resolved_summary)
    )
    output_manifest = (
        output_manifest.expanduser().resolve()
        if output_manifest is not None
        else _default_output_path(
            resolved_summary,
            "-training-no-cost-operator-handoff-closeout-package-manifest.json",
        )
    )
    output_markdown = (
        output_markdown.expanduser().resolve()
        if output_markdown is not None
        else _default_output_path(resolved_summary, "-training-no-cost-operator-handoff-closeout-package.md")
    )

    source_files: dict[str, dict[str, Any]] = {
        "operator_handoff_closeout_receipt_summary_json": _file_record(str(resolved_summary)),
    }
    if resolved_summary_markdown is not None:
        _add_source_file(
            source_files,
            "operator_handoff_closeout_receipt_summary_markdown",
            str(resolved_summary_markdown),
        )
    for index, receipt in enumerate(_as_list(summary.get("receipts")), start=1):
        receipt_payload = _as_dict(receipt)
        _add_source_file(source_files, f"operator_handoff_closeout_receipt_{index}", receipt_payload.get("path"))
    missing_files = sorted(name for name, record in source_files.items() if record.get("exists") is not True)
    readiness = _as_dict(summary.get("readiness"))
    counts = _as_dict(summary.get("counts"))

    package = {
        "report_type": "report_quality_training_no_cost_operator_handoff_closeout_package",
        "schema_version": EXPECTED_SCHEMA,
        "generated_at": generated_at or _now_iso(),
        "operator_handoff_closeout_package_manifest_path": str(output_manifest),
        "operator_handoff_closeout_package_markdown_path": str(output_markdown),
        "operator_handoff_closeout_receipt_summary_path": str(resolved_summary),
        "operator_handoff_closeout_receipt_summary_sha256": _sha256(resolved_summary),
        "summary_validation": summary_validation,
        "package_state": {
            "ready": True,
            "status": "no_cost_operator_handoff_closeout_package_ready",
            "package_only": True,
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
        "confirmed_summary_state": {
            "status": readiness.get("status"),
            "service_operation_locked": readiness.get("service_operation_locked") is True,
            "resume_blocked": readiness.get("resume_blocked") is True,
            "operation_resume_approved": readiness.get("operation_resume_approved") is True,
            "service_operation_allowed": readiness.get("service_operation_allowed") is True,
            "aws_cost_increase_allowed": readiness.get("aws_cost_increase_allowed") is True,
            "training_execution_authorized": readiness.get("training_execution_authorized") is True,
            "model_promotion_authorized": readiness.get("model_promotion_authorized") is True,
        },
        "counts": {
            "receipt_count": counts.get("receipt_count", 0),
            "valid_receipt_count": counts.get("valid_receipt_count", 0),
            "ready_receipt_count": counts.get("ready_receipt_count", 0),
            "signoff_count": counts.get("signoff_count", 0),
            "operator_handoff_review_count": counts.get("operator_handoff_review_count", 0),
            "package_source_file_count": len(source_files),
            "package_missing_file_count": len(missing_files),
        },
        "source_files": source_files,
        "operator_actions": [
            "Keep service operation disabled and keep resume blocked after this closeout package.",
            "Use this package only as local operator handoff closeout evidence.",
            "Do not deploy AWS resources, enable runtime services, scheduled jobs, or CloudWatch polling from this package.",
            "Do not call provider APIs, upload datasets, create provider jobs, or poll provider jobs from this package.",
            "Do not execute training or promote models from this package.",
            "Resume only after separate human approval, AWS budget review, provider approval, offline eval plan, and rollback plan are complete.",
        ],
        "package_boundary": {
            "reads_local_operator_handoff_closeout_receipt_summary": True,
            "writes_local_closeout_package_files": True,
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
    _write_text_atomic(output_manifest, json.dumps(package, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    _write_text_atomic(output_markdown, render_training_no_cost_operator_handoff_closeout_package_markdown(package))
    return package


def render_training_no_cost_operator_handoff_closeout_package_markdown(package: dict[str, Any]) -> str:
    state = _as_dict(package.get("package_state"))
    counts = _as_dict(package.get("counts"))
    source_files = _as_dict(package.get("source_files"))
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
    return f"""# Report Quality Training No-Cost Operator Handoff Closeout Package

- generated_at: `{package.get('generated_at', '-')}`
- status: `{state.get('status', '-')}`
- package_ready: `{str(state.get('ready') is True).lower()}`
- package_only: `true`
- service_operation_locked: `true`
- resume_blocked: `true`
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

## Source Files

| file | exists | path |
| --- | --- | --- |
{rows}

## Operator Actions

{chr(10).join(f"- {item}" for item in package.get('operator_actions', []))}

## Package Boundary

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
    parser = argparse.ArgumentParser(description="Create a no-cost operator handoff closeout package.")
    parser.add_argument(
        "operator_handoff_closeout_receipt_summary",
        type=Path,
        help="Path to *-training-no-cost-operator-handoff-closeout-receipt-summary.json.",
    )
    parser.add_argument("--summary-markdown", type=Path, default=None)
    parser.add_argument("--output-manifest", type=Path, default=None)
    parser.add_argument("--output-markdown", type=Path, default=None)
    parser.add_argument("--generated-at", help="Optional ISO timestamp for deterministic output.")
    parser.add_argument("--json", action="store_true", help="Print generated closeout package JSON to stdout.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(list(argv) if argv is not None else None)
    try:
        package = create_training_no_cost_operator_handoff_closeout_package(
            operator_handoff_closeout_receipt_summary_path=args.operator_handoff_closeout_receipt_summary,
            summary_markdown_path=args.summary_markdown,
            output_manifest=args.output_manifest,
            output_markdown=args.output_markdown,
            generated_at=args.generated_at,
        )
    except Exception as exc:
        result = {"ok": False, "error": str(exc)}
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        else:
            print("FAIL report quality training no-cost operator handoff closeout package generation failed")
            print(f"ERROR {exc}")
        return 1

    if args.json:
        print(json.dumps(package, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print("Report quality training no-cost operator handoff closeout package: PASS")
        print(f"package_ready={str(package['package_state']['ready']).lower()}")
        print(f"service_operation_locked={str(package['package_state']['service_operation_locked']).lower()}")
        print(f"resume_blocked={str(package['package_state']['resume_blocked']).lower()}")
        print("aws_cost_boundary=no_cost_increase")
        print("training_boundary=not_authorized")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
