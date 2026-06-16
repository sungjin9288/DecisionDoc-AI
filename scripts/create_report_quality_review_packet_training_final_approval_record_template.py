#!/usr/bin/env python3
"""Create a pending final approval record template for report quality training planning."""
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
DEFAULT_TEMPLATE_PATH = REPO_ROOT / "docs/specs/report_quality_learning/training_final_approval_record_template.json"
PACKET_REVIEW_VALIDATOR_PATH = (
    REPO_ROOT / "scripts/validate_report_quality_review_packet_training_final_approval_packet_review.py"
)
RECORD_VALIDATOR_PATH = (
    REPO_ROOT / "scripts/validate_report_quality_review_packet_training_final_approval_record_template.py"
)
EXPECTED_SCHEMA = "decisiondoc_report_quality_training_final_approval_record_template.v1"
RECORD_TEMPLATE_ID_PATTERN = re.compile(r"rqp_training_final_approval_record_template_[A-Za-z0-9_-]{8,96}")
REQUIRED_APPROVER_ROLES = [
    "ML/AI Owner",
    "Product/PM",
    "Compliance/Security",
    "Release Owner",
]


def _load_module(path: Path, module_name: str):
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed to load {module_name}: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_PACKET_REVIEW_VALIDATOR = _load_module(
    PACKET_REVIEW_VALIDATOR_PATH,
    "validate_report_quality_review_packet_training_final_approval_packet_review",
)
_RECORD_VALIDATOR = _load_module(
    RECORD_VALIDATOR_PATH,
    "validate_report_quality_review_packet_training_final_approval_record_template",
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


def _safe_template_id(value: str | None) -> str:
    template_id = (
        value.strip()
        if isinstance(value, str) and value.strip()
        else f"rqp_training_final_approval_record_template_{uuid4().hex}"
    )
    if not RECORD_TEMPLATE_ID_PATTERN.fullmatch(template_id):
        raise ValueError(
            "template id must match rqp_training_final_approval_record_template_[A-Za-z0-9_-]{8,96}"
        )
    return template_id


def _default_output_path(packet_review_path: Path, suffix: str) -> Path:
    name = packet_review_path.name
    if name.endswith("-training-final-approval-packet-review.json"):
        base = name.removesuffix("-training-final-approval-packet-review.json")
    else:
        base = packet_review_path.stem
    return packet_review_path.with_name(f"{base}{suffix}")


def _pending_approvals() -> list[dict[str, Any]]:
    return [
        {
            "role": role,
            "approver_name": "",
            "title_or_team": "",
            "decision": "pending",
            "approved_at": "",
            "conditions": [],
        }
        for role in REQUIRED_APPROVER_ROLES
    ]


def create_training_final_approval_record_template(
    *,
    packet_review_path: Path,
    output_path: Path | None = None,
    output_markdown: Path | None = None,
    template_path: Path = DEFAULT_TEMPLATE_PATH,
    template_id: str | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    resolved_review = packet_review_path.expanduser().resolve()
    resolved_template = template_path.expanduser().resolve()
    packet_review = _load_json(resolved_review)
    packet_review_validation = _PACKET_REVIEW_VALIDATOR.validate_training_final_approval_packet_review(
        packet_review,
        require_complete=True,
    )
    if packet_review_validation.get("ok") is not True:
        errors = "; ".join(packet_review_validation.get("errors") or ["packet review validation failed"])
        raise ValueError(f"final approval packet review is not complete: {errors}")
    if packet_review.get("decision") != "packet_review_complete":
        raise ValueError("final approval record template requires packet review decision=packet_review_complete")
    if packet_review.get("requested_next_step") != "prepare_final_approval_record_template":
        raise ValueError(
            "final approval record template requires requested_next_step=prepare_final_approval_record_template"
        )

    packet_manifest_path = Path(str(packet_review["packet_manifest_path"])).expanduser().resolve()
    packet = _load_json(packet_manifest_path)
    output_path = (
        output_path.expanduser().resolve()
        if output_path is not None
        else _default_output_path(resolved_review, "-training-final-approval-record-template.json")
    )
    output_markdown = (
        output_markdown.expanduser().resolve()
        if output_markdown is not None
        else _default_output_path(resolved_review, "-training-final-approval-record-template.md")
    )

    source_files = {
        "packet_review_record": _file_record(str(resolved_review)),
        "packet_manifest": _file_record(str(packet_manifest_path)),
        "packet_markdown": _file_record(packet.get("packet_markdown_path")),
    }
    for key, record in sorted(_as_dict(packet.get("source_files")).items()):
        source_files[f"packet_source_{key}"] = _file_record(_as_dict(record).get("path"))

    missing_files = sorted(name for name, record in source_files.items() if record.get("exists") is not True)
    packet_counts = _as_dict(packet.get("counts"))
    template = _load_json(resolved_template)
    record = dict(template)
    record.update(
        {
            "report_type": "report_quality_training_final_approval_record_template",
            "schema_version": EXPECTED_SCHEMA,
            "template_id": _safe_template_id(template_id),
            "generated_at": generated_at or _now_iso(),
            "record_template_path": str(output_path),
            "record_markdown_path": str(output_markdown),
            "packet_review_path": str(resolved_review),
            "packet_review_sha256": _sha256(resolved_review),
            "packet_manifest_path": str(packet_manifest_path),
            "packet_manifest_sha256": _sha256(packet_manifest_path),
            "packet_review_validation": packet_review_validation,
            "approval_state": {
                "template_only": True,
                "status": "pending_manual_final_approval",
                "approval_record_completed": False,
                "final_training_approval_granted": False,
                "approval_effective": False,
                "training_execution_allowed": False,
                "external_upload_allowed": False,
                "provider_api_calls_allowed": False,
                "provider_job_started": False,
                "model_promotion_allowed": False,
            },
            "required_approvals": _pending_approvals(),
            "source_files": source_files,
            "job_spec_snapshot": _as_dict(packet.get("job_spec_snapshot")),
            "counts": {
                "ready_artifacts": packet_counts.get("ready_artifacts", 0),
                "completed_signoff_count": packet_counts.get("completed_signoff_count", 0),
                "source_file_count": len(source_files),
                "missing_file_count": len(missing_files),
                "required_approval_count": len(REQUIRED_APPROVER_ROLES),
            },
            "operator_actions": [
                "Humans may fill this template later only after all final approver roles review the packet.",
                "Do not mark any approval, final approval grant, execution authorization, or provider job state in the generated template.",
                "Do not upload datasets, call provider fine-tune APIs, create or poll provider jobs, start training, or promote models from this template.",
            ],
            "approval_boundary": {
                "actual_training_approval_recorded": False,
                "final_training_approval_granted": False,
                "server_file_written": False,
                "persisted_learning_artifact": False,
                "external_dataset_upload_authorized": False,
                "provider_fine_tune_api_call_authorized": False,
                "provider_job_creation_authorized": False,
                "provider_job_polling_authorized": False,
                "training_execution_authorized": False,
                "model_promotion_authorized": False,
            },
            "side_effect_boundary": {
                "reads_local_packet_review_record": True,
                "writes_local_final_approval_record_template_files": True,
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
            "generation_context": {
                "report_type": "report_quality_training_final_approval_record_template_generation",
                "generated_from_template": str(resolved_template),
                "packet_review_decision": packet_review.get("decision"),
                "packet_review_requested_next_step": packet_review.get("requested_next_step"),
                "packet_review_validation": packet_review_validation,
                "packet_readiness": _as_dict(packet.get("readiness")),
                "packet_counts": packet_counts,
                "required_final_approver_roles": _as_list(packet.get("required_final_approver_roles")),
                "missing_files": missing_files,
                "review_scope": (
                    "This generated artifact is a pending final approval record template only. It cannot "
                    "record final approval, upload datasets, call provider APIs, create or poll provider "
                    "jobs, start training, or promote models."
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
    _write_text_atomic(output_path, json.dumps(record, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    _write_text_atomic(output_markdown, render_training_final_approval_record_template_markdown(record))
    return record


def render_training_final_approval_record_template_markdown(record: dict[str, Any]) -> str:
    approval_state = _as_dict(record.get("approval_state"))
    counts = _as_dict(record.get("counts"))
    files = _as_dict(record.get("source_files"))
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
    approvals = "\n".join(
        "- {role}: `{decision}`".format(
            role=_as_dict(approval).get("role", "-"),
            decision=_as_dict(approval).get("decision", "-"),
        )
        for approval in record.get("required_approvals", [])
    )
    return f"""# Report Quality Training Final Approval Record Template

- generated_at: `{record.get('generated_at', '-')}`
- status: `{approval_state.get('status', '-')}`
- template_only: `true`
- approval_record_completed: `false`
- final_training_approval_granted: `false`
- training_execution_allowed: `false`
- provider_api_calls_allowed: `false`
- external_upload_allowed: `false`
- provider_job_started: `false`
- model_promotion_allowed: `false`
- ready_artifacts: `{counts.get('ready_artifacts', 0)}`
- completed_signoff_count: `{counts.get('completed_signoff_count', 0)}`

## Required Approvals

{approvals}

## Source Files

| file | exists | path |
| --- | --- | --- |
{rows}

## Operator Actions

{chr(10).join(f"- {item}" for item in record.get('operator_actions', []))}

## Side-Effect Boundary

- actual_training_approval_recorded: `false`
- final_training_approval_granted: `false`
- server_file_written: `false`
- persisted_learning_artifact: `false`
- external_dataset_upload_started: `false`
- provider_fine_tune_api_called: `false`
- provider_job_created: `false`
- provider_job_polled: `false`
- training_execution_started: `false`
- model_promotion_started: `false`
"""


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Create a pending report quality final approval record template.")
    parser.add_argument("packet_review", type=Path, help="Path to completed training final approval packet review JSON.")
    parser.add_argument("--template", type=Path, default=DEFAULT_TEMPLATE_PATH)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--markdown", type=Path, default=None)
    parser.add_argument(
        "--template-id",
        help="Optional deterministic id matching rqp_training_final_approval_record_template_[A-Za-z0-9_-]{8,96}.",
    )
    parser.add_argument("--generated-at", help="Optional ISO timestamp for deterministic generation.")
    parser.add_argument("--json", action="store_true", help="Print generated template JSON to stdout.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(list(argv) if argv is not None else None)
    try:
        record = create_training_final_approval_record_template(
            packet_review_path=args.packet_review,
            output_path=args.output,
            output_markdown=args.markdown,
            template_path=args.template,
            template_id=args.template_id,
            generated_at=args.generated_at,
        )
        validation = _RECORD_VALIDATOR.validate_training_final_approval_record_template(
            Path(record["record_template_path"]),
        )
    except Exception as exc:
        result = {"ok": False, "error": str(exc)}
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        else:
            print("FAIL report quality training final approval record template generation failed")
            print(f"ERROR {exc}")
        return 1

    if args.json:
        print(json.dumps(record, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print("Report quality training final approval record template: PASS")
        print(f"template_only={str(record['approval_state']['template_only']).lower()}")
        print(f"approval_granted={str(record['approval_state']['final_training_approval_granted']).lower()}")
        print("training_boundary=not_authorized")
    return 0 if validation["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
