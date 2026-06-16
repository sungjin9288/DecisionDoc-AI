#!/usr/bin/env python3
"""Create a no-cost operator handoff from a service lock report summary."""
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
SERVICE_LOCK_REPORT_SUMMARY_VALIDATOR_PATH = (
    REPO_ROOT / "scripts/validate_report_quality_review_packet_training_no_cost_service_lock_report_summary.py"
)
EXPECTED_SCHEMA = "decisiondoc_report_quality_training_no_cost_operator_handoff.v1"


def _load_service_lock_report_summary_validator():
    spec = importlib.util.spec_from_file_location(
        "validate_report_quality_review_packet_training_no_cost_service_lock_report_summary",
        SERVICE_LOCK_REPORT_SUMMARY_VALIDATOR_PATH,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(
            "failed to load no-cost service lock report summary validator: "
            f"{SERVICE_LOCK_REPORT_SUMMARY_VALIDATOR_PATH}"
        )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_SUMMARY_VALIDATOR = _load_service_lock_report_summary_validator()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path}: JSON root must be an object")
    return payload


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


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


def _default_output_path(summary_path: Path, suffix: str) -> Path:
    name = summary_path.name
    if name.endswith("-training-no-cost-service-lock-report-summary.json"):
        base = name.removesuffix("-training-no-cost-service-lock-report-summary.json")
    else:
        base = summary_path.stem
    return summary_path.with_name(f"{base}{suffix}")


def create_training_no_cost_operator_handoff(
    *,
    service_lock_report_summary_path: Path,
    output_manifest: Path | None = None,
    output_markdown: Path | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    resolved_summary = service_lock_report_summary_path.expanduser().resolve()
    summary = _load_json(resolved_summary)
    summary_validation = _SUMMARY_VALIDATOR.validate_training_no_cost_service_lock_report_summary(resolved_summary)
    if summary_validation["ok"] is not True:
        raise ValueError(
            "no-cost service lock report summary validation failed: "
            + "; ".join(str(error) for error in summary_validation["errors"])
        )

    output_manifest = (
        output_manifest.expanduser().resolve()
        if output_manifest is not None
        else _default_output_path(resolved_summary, "-training-no-cost-operator-handoff-manifest.json")
    )
    output_markdown = (
        output_markdown.expanduser().resolve()
        if output_markdown is not None
        else _default_output_path(resolved_summary, "-training-no-cost-operator-handoff.md")
    )
    readiness = _as_dict(summary.get("readiness"))
    counts = _as_dict(summary.get("counts"))
    handoff = {
        "report_type": "report_quality_training_no_cost_operator_handoff",
        "schema_version": EXPECTED_SCHEMA,
        "generated_at": generated_at or _now_iso(),
        "operator_handoff_manifest_path": str(output_manifest),
        "operator_handoff_markdown_path": str(output_markdown),
        "service_lock_report_summary_path": str(resolved_summary),
        "service_lock_report_summary_sha256": _sha256(resolved_summary),
        "summary_validation": summary_validation,
        "handoff_state": {
            "ready": True,
            "status": "no_cost_operator_handoff_ready",
            "read_only_handoff": True,
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
            "service_lock_report_count": counts.get("service_lock_report_count", 0),
            "valid_service_lock_report_count": counts.get("valid_service_lock_report_count", 0),
            "ready_service_lock_report_count": counts.get("ready_service_lock_report_count", 0),
            "closeout_receipt_count": counts.get("closeout_receipt_count", 0),
            "ready_closeout_receipt_count": counts.get("ready_closeout_receipt_count", 0),
            "final_hold_count": counts.get("final_hold_count", 0),
            "active_final_hold_count": counts.get("active_final_hold_count", 0),
            "signoff_count": counts.get("signoff_count", 0),
            "service_lock_review_count": counts.get("service_lock_review_count", 0),
        },
        "operator_actions": [
            "Keep service operation disabled and keep resume blocked.",
            "Do not deploy AWS resources or enable runtime services from this handoff.",
            "Do not enable scheduled jobs or CloudWatch polling from this handoff.",
            "Do not call provider APIs, upload datasets, create provider jobs, or poll provider jobs from this handoff.",
            "Do not execute training or promote models from this handoff.",
            "Resume only after separate human approval, AWS budget review, provider approval, offline eval plan, and rollback plan are complete.",
        ],
        "handoff_boundary": {
            "reads_local_service_lock_report_summary": True,
            "writes_local_handoff_files": True,
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
    _write_text_atomic(output_manifest, json.dumps(handoff, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    _write_text_atomic(output_markdown, render_training_no_cost_operator_handoff_markdown(handoff))
    return handoff


def render_training_no_cost_operator_handoff_markdown(handoff: dict[str, Any]) -> str:
    state = _as_dict(handoff.get("handoff_state"))
    counts = _as_dict(handoff.get("counts"))
    return f"""# Report Quality Training No-Cost Operator Handoff

- generated_at: `{handoff.get('generated_at', '-')}`
- status: `{state.get('status', '-')}`
- handoff_ready: `{str(state.get('ready') is True).lower()}`
- service_operation_locked: `true`
- resume_blocked: `true`
- operation_resume_approved: `false`
- service_operation_allowed: `false`
- aws_cost_increase_allowed: `false`
- provider_fine_tune_api_call_authorized: `false`
- external_dataset_upload_authorized: `false`
- training_execution_authorized: `false`
- model_promotion_authorized: `false`
- service_lock_report_count: `{counts.get('service_lock_report_count', 0)}`
- ready_service_lock_report_count: `{counts.get('ready_service_lock_report_count', 0)}`
- closeout_receipt_count: `{counts.get('closeout_receipt_count', 0)}`
- ready_closeout_receipt_count: `{counts.get('ready_closeout_receipt_count', 0)}`

## Operator Actions

{chr(10).join(f"- {item}" for item in handoff.get('operator_actions', []))}

## Handoff Boundary

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
    parser = argparse.ArgumentParser(description="Create a no-cost operator handoff manifest.")
    parser.add_argument(
        "service_lock_report_summary",
        type=Path,
        help="Path to *-training-no-cost-service-lock-report-summary.json.",
    )
    parser.add_argument("--output-manifest", type=Path, default=None)
    parser.add_argument("--output-markdown", type=Path, default=None)
    parser.add_argument("--generated-at", help="Optional ISO timestamp for deterministic output.")
    parser.add_argument("--json", action="store_true", help="Print generated operator handoff JSON to stdout.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(list(argv) if argv is not None else None)
    try:
        handoff = create_training_no_cost_operator_handoff(
            service_lock_report_summary_path=args.service_lock_report_summary,
            output_manifest=args.output_manifest,
            output_markdown=args.output_markdown,
            generated_at=args.generated_at,
        )
    except Exception as exc:
        result = {"ok": False, "error": str(exc)}
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        else:
            print("FAIL report quality training no-cost operator handoff generation failed")
            print(f"ERROR {exc}")
        return 1

    if args.json:
        print(json.dumps(handoff, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print("Report quality training no-cost operator handoff: PASS")
        print(f"operator_handoff_ready={str(handoff['handoff_state']['ready']).lower()}")
        print(f"service_operation_locked={str(handoff['handoff_state']['service_operation_locked']).lower()}")
        print(f"resume_blocked={str(handoff['handoff_state']['resume_blocked']).lower()}")
        print("aws_cost_boundary=no_cost_increase")
        print("training_boundary=not_authorized")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
