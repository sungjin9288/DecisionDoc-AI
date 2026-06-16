#!/usr/bin/env python3
"""Summarize DocumentOps Phase 297 validated closure receipt records."""
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

from scripts.validate_documentops_phase296_validated_closure_receipt_summary_handoff_signoff_closure_receipt import (  # noqa: E402
    validate_documentops_phase296_validated_closure_receipt_summary_handoff_signoff_closure_receipt,
)


EXPECTED_SCHEMA = "decisiondoc_documentops_phase297_validated_closure_receipt_summary.v1"
DEFAULT_RECEIPT_PATH = (
    REPO_ROOT
    / "docs/specs/hermes_decisiondoc_agent/"
    "phase297_local_feature_completion_validated_closure_receipt_summary_handoff_signoff_closure_receipt/"
    "validated_closure_receipt_summary_handoff_signoff_closure_receipt.json"
)
FORBIDDEN_TRUE_KEYS = (
    "actual_reviewer_approval_recorded",
    "actual_reviewer_approval_recorded_by_receipt",
    "actual_reviewer_approval_recorded_by_summary",
    "actual_reviewer_approval_recorded_by_validator",
    "actual_operation_resume_approved",
    "service_resume_authorized",
    "service_operation_allowed",
    "service_operation_authorized",
    "production_ui_called",
    "production_uat_reexecuted",
    "production_download_open_verification_authorized",
    "aws_runtime_called",
    "aws_cost_increase_allowed",
    "aws_deploy_authorized",
    "aws_deploy_started",
    "aws_resource_creation_authorized",
    "aws_resource_created",
    "scheduled_job_authorized",
    "scheduled_job_enabled",
    "cloudwatch_polling_authorized",
    "cloudwatch_polling_started",
    "provider_api_calls_allowed",
    "provider_api_calls_authorized",
    "provider_fine_tune_api_called",
    "provider_job_creation_authorized",
    "provider_job_created",
    "provider_job_polling_authorized",
    "provider_job_polled",
    "external_upload_allowed",
    "external_dataset_upload_authorized",
    "external_dataset_uploaded",
    "training_execution_allowed",
    "training_execution_authorized",
    "training_execution_started",
    "model_candidate_emission_authorized",
    "model_candidate_emitted",
    "model_promotion_allowed",
    "model_promotion_authorized",
    "model_promoted",
    "model_training_started",
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


def _scan_forbidden_true(value: Any, *, path: str = "$") -> list[str]:
    findings: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}"
            if key in FORBIDDEN_TRUE_KEYS and child is True:
                findings.append(child_path.removeprefix("$."))
            findings.extend(_scan_forbidden_true(child, path=child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            findings.extend(_scan_forbidden_true(child, path=f"{path}[{index}]"))
    return findings


def summarize_receipt(path: Path, payload: dict[str, Any]) -> dict[str, Any]:
    validation = validate_documentops_phase296_validated_closure_receipt_summary_handoff_signoff_closure_receipt(
        path
    )
    source_gate = _as_dict(payload.get("source_closure_gate"))
    receipt_boundary = _as_dict(payload.get("receipt_boundary"))
    source_hashes = _as_dict(payload.get("source_hashes"))
    boundary_breaks = _scan_forbidden_true(payload)

    return {
        "path": str(path),
        "sha256": _sha256_file(path),
        "report_type": payload.get("report_type", ""),
        "phase": payload.get("phase"),
        "status": payload.get("status", ""),
        "created_at": payload.get("created_at", ""),
        "operator_decision": payload.get("operator_decision", ""),
        "source_gate_command": source_gate.get("command", ""),
        "source_gate_result": source_gate.get("result", ""),
        "closure_index_valid": source_gate.get("closure_index_valid") is True,
        "source_artifact_count": source_gate.get("source_artifact_count", 0),
        "probe_count": source_gate.get("probe_count", 0),
        "temporary_summary_readiness": source_gate.get("temporary_summary_readiness", ""),
        "temporary_summary_validation_ok": source_gate.get("temporary_summary_validation_ok") is True,
        "recommended_decision": source_gate.get("recommended_decision", ""),
        "phase296_closure_index_sha256": source_hashes.get("phase296_closure_index_sha256", ""),
        "phase296_closure_validator_sha256": source_hashes.get("phase296_closure_validator_sha256", ""),
        "phase297_closure_receipt_validator_sha256": source_hashes.get(
            "phase297_closure_receipt_validator_sha256", ""
        ),
        "boundary_breaks": boundary_breaks,
        "validation": {
            "ok": validation.get("ok") is True,
            "closure_receipt_valid": validation.get("closure_receipt_valid") is True,
            "source_closure_gate_valid": validation.get("source_closure_gate_valid") is True,
            "errors": validation.get("errors", []),
            "warnings": validation.get("warnings", []),
        },
        "side_effect_boundary": {
            "service_resume_authorized": receipt_boundary.get("service_resume_authorized") is True,
            "production_ui_called": receipt_boundary.get("production_ui_called") is True,
            "aws_runtime_called": receipt_boundary.get("aws_runtime_called") is True,
            "aws_cost_increase_allowed": receipt_boundary.get("aws_cost_increase_allowed") is True,
            "provider_api_calls_authorized": receipt_boundary.get("provider_api_calls_authorized") is True,
            "external_dataset_uploaded": receipt_boundary.get("external_dataset_uploaded") is True,
            "training_execution_started": receipt_boundary.get("training_execution_started") is True,
            "model_promoted": receipt_boundary.get("model_promoted") is True,
        },
    }


def build_documentops_phase297_validated_closure_receipt_summary(
    paths: Sequence[Path],
    *,
    generated_at: str | None = None,
) -> dict[str, Any]:
    receipts: list[dict[str, Any]] = []
    load_errors: list[dict[str, str]] = []
    for path in _expand_paths(paths):
        try:
            receipts.append(summarize_receipt(path, _load_json(path)))
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            load_errors.append({"path": str(path), "error": str(exc)})

    valid_count = sum(1 for receipt in receipts if receipt["validation"]["ok"])
    boundary_break_count = sum(1 for receipt in receipts if receipt["boundary_breaks"])
    invalid_count = len(receipts) - valid_count

    blocker_reasons: list[str] = []
    if load_errors:
        blocker_reasons.append("phase297_validated_closure_receipt_load_errors")
    if not receipts:
        blocker_reasons.append("no_phase297_validated_closure_receipts")
    if invalid_count:
        blocker_reasons.append("invalid_phase297_validated_closure_receipts")
    if boundary_break_count:
        blocker_reasons.append("phase297_validated_closure_receipt_boundary_breaks")

    status = (
        "all_phase297_validated_closure_receipts_confirm_no_cost_freeze"
        if not blocker_reasons
        else "follow_up_required"
    )

    return {
        "report_type": "document_ops_phase298_local_feature_completion_validated_closure_receipt_summary_handoff_signoff_closure_receipt_summary",
        "phase": 298,
        "schema_version": EXPECTED_SCHEMA,
        "generated_at": generated_at or _now_iso(),
        "read_only": True,
        "ok": not blocker_reasons,
        "readiness": {
            "status": status,
            "blocker_reasons": blocker_reasons,
            "service_freeze_preserved": True,
            "resume_requires_separate_approval": True,
            "service_resume_authorized": False,
            "production_ui_called": False,
            "aws_runtime_called": False,
            "aws_cost_increase_allowed": False,
            "provider_api_calls_authorized": False,
            "external_dataset_uploaded": False,
            "training_execution_started": False,
            "model_promoted": False,
            "aws_cost_boundary": "no_cost_increase",
            "training_boundary": "not_authorized",
        },
        "counts": {
            "receipt_count": len(receipts),
            "valid_receipt_count": valid_count,
            "invalid_receipt_count": invalid_count,
            "boundary_break_count": boundary_break_count,
            "load_error_count": len(load_errors),
        },
        "receipts": receipts,
        "load_errors": load_errors,
        "side_effect_boundary": {
            "reads_local_phase297_validated_closure_receipts": True,
            "writes_summary_only": True,
            "actual_reviewer_approval_recorded_by_summary": False,
            "service_resume_authorized": False,
            "production_ui_called": False,
            "aws_runtime_called": False,
            "aws_cost_increase_allowed": False,
            "provider_api_calls_authorized": False,
            "external_dataset_uploaded": False,
            "training_execution_started": False,
            "model_promoted": False,
        },
    }


def _render_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# DocumentOps Phase 297 Validated Closure Receipt Summary",
        "",
        f"- Status: `{summary['readiness']['status']}`",
        f"- Receipt count: `{summary['counts']['receipt_count']}`",
        f"- Valid receipt count: `{summary['counts']['valid_receipt_count']}`",
        f"- Invalid receipt count: `{summary['counts']['invalid_receipt_count']}`",
        f"- Boundary break count: `{summary['counts']['boundary_break_count']}`",
        f"- AWS cost boundary: `{summary['readiness']['aws_cost_boundary']}`",
        f"- Training boundary: `{summary['readiness']['training_boundary']}`",
        "",
        "## Receipts",
        "",
        "| Receipt | Valid | Source Gate | Decision | Boundary Breaks |",
        "|---|---|---|---|---|",
    ]
    for receipt in summary["receipts"]:
        lines.append(
            "| "
            f"`{Path(receipt['path']).name}` | "
            f"`{str(receipt['validation']['ok']).lower()}` | "
            f"`{receipt['source_gate_result']}` | "
            f"`{receipt['operator_decision']}` | "
            f"`{len(receipt['boundary_breaks'])}` |"
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
        description="Summarize DocumentOps Phase 297 validated closure receipt JSON records."
    )
    parser.add_argument(
        "receipts",
        nargs="*",
        type=Path,
        default=[DEFAULT_RECEIPT_PATH],
        help="Closure receipt JSON file(s) or directories. Defaults to the Phase 297 receipt.",
    )
    parser.add_argument("--generated-at", help="Optional ISO timestamp for deterministic summary output.")
    parser.add_argument("--output", type=Path, help="Optional output path for summary JSON.")
    parser.add_argument("--markdown-output", type=Path, help="Optional output path for summary Markdown.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(list(argv) if argv is not None else None)
    summary = build_documentops_phase297_validated_closure_receipt_summary(
        args.receipts,
        generated_at=args.generated_at,
    )
    if args.output:
        _write_text_atomic(
            args.output,
            json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        )
    if args.markdown_output:
        _write_text_atomic(args.markdown_output, _render_markdown(summary))
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if summary["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
