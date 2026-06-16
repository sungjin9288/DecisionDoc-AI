#!/usr/bin/env python3
"""Create a local no-cost freeze manifest for report quality training planning."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import re
from typing import Any, Sequence
from uuid import uuid4


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TEMPLATE_PATH = REPO_ROOT / "docs/specs/report_quality_learning/training_no_cost_freeze_template.json"
RECORD_TEMPLATE_VALIDATOR_PATH = (
    REPO_ROOT / "scripts/validate_report_quality_review_packet_training_final_approval_record_template.py"
)
FREEZE_VALIDATOR_PATH = REPO_ROOT / "scripts/validate_report_quality_review_packet_training_no_cost_freeze.py"
EXPECTED_SCHEMA = "decisiondoc_report_quality_training_no_cost_freeze.v1"
FREEZE_ID_PATTERN = re.compile(r"rqp_training_no_cost_freeze_[A-Za-z0-9_-]{8,96}")


def _load_module(path: Path, module_name: str):
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed to load {module_name}: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_RECORD_TEMPLATE_VALIDATOR = _load_module(
    RECORD_TEMPLATE_VALIDATOR_PATH,
    "validate_report_quality_review_packet_training_final_approval_record_template",
)
_FREEZE_VALIDATOR = _load_module(
    FREEZE_VALIDATOR_PATH,
    "validate_report_quality_review_packet_training_no_cost_freeze",
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


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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


def _write_text_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def _safe_freeze_id(value: str | None) -> str:
    freeze_id = (
        value.strip()
        if isinstance(value, str) and value.strip()
        else f"rqp_training_no_cost_freeze_{uuid4().hex}"
    )
    if not FREEZE_ID_PATTERN.fullmatch(freeze_id):
        raise ValueError("freeze id must match rqp_training_no_cost_freeze_[A-Za-z0-9_-]{8,96}")
    return freeze_id


def _default_output_path(record_template_path: Path, suffix: str) -> Path:
    name = record_template_path.name
    if name.endswith("-training-final-approval-record-template.json"):
        base = name.removesuffix("-training-final-approval-record-template.json")
    else:
        base = record_template_path.stem
    return record_template_path.with_name(f"{base}{suffix}")


def create_training_no_cost_freeze_manifest(
    *,
    approval_record_template_path: Path,
    output_manifest: Path | None = None,
    output_markdown: Path | None = None,
    template_path: Path = DEFAULT_TEMPLATE_PATH,
    freeze_id: str | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    resolved_record = approval_record_template_path.expanduser().resolve()
    resolved_template = template_path.expanduser().resolve()
    record = _load_json(resolved_record)
    record_validation = _RECORD_TEMPLATE_VALIDATOR.validate_training_final_approval_record_template(
        resolved_record,
    )
    if record_validation.get("ok") is not True:
        errors = "; ".join(record_validation.get("errors") or ["final approval record template validation failed"])
        raise ValueError(f"final approval record template is not ready for no-cost freeze: {errors}")

    output_manifest = (
        output_manifest.expanduser().resolve()
        if output_manifest is not None
        else _default_output_path(resolved_record, "-training-no-cost-freeze-manifest.json")
    )
    output_markdown = (
        output_markdown.expanduser().resolve()
        if output_markdown is not None
        else _default_output_path(resolved_record, "-training-no-cost-freeze.md")
    )

    source_files = {
        "approval_record_template": _file_record(str(resolved_record)),
        "approval_record_markdown": _file_record(record.get("record_markdown_path")),
        "packet_review_record": _file_record(record.get("packet_review_path")),
        "packet_manifest": _file_record(record.get("packet_manifest_path")),
    }
    for key, source_record in sorted(_as_dict(record.get("source_files")).items()):
        source_files[f"approval_record_source_{key}"] = _file_record(_as_dict(source_record).get("path"))

    missing_files = sorted(name for name, source_record in source_files.items() if source_record.get("exists") is not True)
    record_counts = _as_dict(record.get("counts"))
    template = _load_json(resolved_template)
    freeze = dict(template)
    freeze.update(
        {
            "report_type": "report_quality_training_no_cost_freeze",
            "schema_version": EXPECTED_SCHEMA,
            "freeze_id": _safe_freeze_id(freeze_id),
            "generated_at": generated_at or _now_iso(),
            "freeze_manifest_path": str(output_manifest),
            "freeze_markdown_path": str(output_markdown),
            "approval_record_template_path": str(resolved_record),
            "approval_record_template_sha256": _sha256(resolved_record),
            "approval_record_template_validation": record_validation,
            "freeze_state": {
                "freeze_only": True,
                "status": "no_cost_hold",
                "actual_training_approval_recorded": False,
                "final_training_approval_granted": False,
                "approval_record_completed": False,
                "service_operation_allowed": False,
                "aws_deploy_started": False,
                "aws_resource_created": False,
                "aws_runtime_enabled": False,
                "aws_cost_increase_allowed": False,
                "scheduled_job_enabled": False,
                "cloudwatch_polling_started": False,
                "external_upload_allowed": False,
                "provider_api_calls_allowed": False,
                "provider_job_started": False,
                "training_execution_allowed": False,
                "model_promotion_allowed": False,
            },
            "source_files": source_files,
            "job_spec_snapshot": _as_dict(record.get("job_spec_snapshot")),
            "counts": {
                "ready_artifacts": record_counts.get("ready_artifacts", 0),
                "completed_signoff_count": record_counts.get("completed_signoff_count", 0),
                "source_file_count": len(source_files),
                "missing_file_count": len(missing_files),
            },
            "operator_actions": [
                "Keep this pipeline in no-cost hold until a separate human decision explicitly resumes work.",
                "Do not deploy AWS resources, enable scheduled jobs, or start runtime services while this freeze is active.",
                "Do not call provider APIs, upload datasets, create provider jobs, start training, or promote models while this freeze is active.",
            ],
            "resume_requirements": [
                "manual final approval record completed outside this template",
                "AWS budget and runtime cost review completed",
                "provider API key and dataset upload approval completed",
                "offline eval and rollback plan confirmed before any training run",
            ],
            "cost_boundary": {
                "reads_local_approval_record_template": True,
                "writes_local_freeze_files": True,
                "server_file_written": False,
                "persisted_learning_artifact": False,
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
            "generation_context": {
                "report_type": "report_quality_training_no_cost_freeze_generation",
                "generated_from_template": str(resolved_template),
                "approval_record_template_validation": record_validation,
                "approval_record_template_state": _as_dict(record.get("approval_state")),
                "missing_files": missing_files,
                "freeze_scope": (
                    "This generated artifact freezes the local report quality training planning chain. "
                    "It cannot approve training, operate AWS resources, call providers, upload datasets, "
                    "create jobs, start training, or promote models."
                ),
            },
            "generation_boundary": {
                "actual_training_approval_recorded": False,
                "final_training_approval_granted": False,
                "server_file_written": False,
                "persisted_learning_artifact": False,
                "external_dataset_upload_started": False,
                "provider_fine_tune_api_called": False,
                "provider_job_created": False,
                "provider_job_polled": False,
                "training_execution_started": False,
                "model_promotion_started": False,
            },
        }
    )
    _write_text_atomic(output_manifest, json.dumps(freeze, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    _write_text_atomic(output_markdown, render_training_no_cost_freeze_markdown(freeze))
    return freeze


def render_training_no_cost_freeze_markdown(freeze: dict[str, Any]) -> str:
    freeze_state = _as_dict(freeze.get("freeze_state"))
    counts = _as_dict(freeze.get("counts"))
    files = _as_dict(freeze.get("source_files"))
    rows = "\n".join(
        "| {name} | {exists} | `{path}` |".format(
            name=name,
            exists="yes" if _as_dict(file_record).get("exists") else "no",
            path=_as_dict(file_record).get("path", ""),
        )
        for name, file_record in files.items()
    )
    if not rows:
        rows = "| - | - | - |"
    return f"""# Report Quality Training No-Cost Freeze

- generated_at: `{freeze.get('generated_at', '-')}`
- status: `{freeze_state.get('status', '-')}`
- freeze_only: `true`
- service_operation_allowed: `false`
- aws_deploy_started: `false`
- aws_resource_created: `false`
- aws_runtime_enabled: `false`
- aws_cost_increase_allowed: `false`
- scheduled_job_enabled: `false`
- cloudwatch_polling_started: `false`
- final_training_approval_granted: `false`
- training_execution_allowed: `false`
- provider_api_calls_allowed: `false`
- external_upload_allowed: `false`
- provider_job_started: `false`
- model_promotion_allowed: `false`
- ready_artifacts: `{counts.get('ready_artifacts', 0)}`
- completed_signoff_count: `{counts.get('completed_signoff_count', 0)}`

## Source Files

| file | exists | path |
| --- | --- | --- |
{rows}

## Operator Actions

{chr(10).join(f"- {item}" for item in freeze.get('operator_actions', []))}

## Resume Requirements

{chr(10).join(f"- {item}" for item in freeze.get('resume_requirements', []))}

## Cost Boundary

- server_file_written: `false`
- persisted_learning_artifact: `false`
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
    parser = argparse.ArgumentParser(description="Create a local no-cost freeze manifest for report quality training.")
    parser.add_argument(
        "approval_record_template",
        type=Path,
        help="Path to *-training-final-approval-record-template.json.",
    )
    parser.add_argument("--template", type=Path, default=DEFAULT_TEMPLATE_PATH)
    parser.add_argument("--output-manifest", type=Path, default=None)
    parser.add_argument("--output-markdown", type=Path, default=None)
    parser.add_argument("--freeze-id", help="Optional deterministic id matching rqp_training_no_cost_freeze_*.")
    parser.add_argument("--generated-at", help="Optional ISO timestamp for deterministic generation.")
    parser.add_argument("--json", action="store_true", help="Print generated freeze manifest JSON to stdout.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(list(argv) if argv is not None else None)
    try:
        freeze = create_training_no_cost_freeze_manifest(
            approval_record_template_path=args.approval_record_template,
            output_manifest=args.output_manifest,
            output_markdown=args.output_markdown,
            template_path=args.template,
            freeze_id=args.freeze_id,
            generated_at=args.generated_at,
        )
        validation = _FREEZE_VALIDATOR.validate_training_no_cost_freeze(
            Path(freeze["freeze_manifest_path"]),
        )
    except Exception as exc:
        result = {"ok": False, "error": str(exc)}
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        else:
            print("FAIL report quality training no-cost freeze generation failed")
            print(f"ERROR {exc}")
        return 1

    if args.json:
        print(json.dumps(freeze, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print("Report quality training no-cost freeze: PASS")
        print(f"freeze_only={str(freeze['freeze_state']['freeze_only']).lower()}")
        print("aws_cost_boundary=no_cost_increase")
        print("training_boundary=not_authorized")
    return 0 if validation["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
