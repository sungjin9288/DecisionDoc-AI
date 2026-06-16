#!/usr/bin/env python3
"""Create a local final approval packet draft for report quality training planning."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
from typing import Any, Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
PLAN_REVIEW_VALIDATOR_PATH = REPO_ROOT / "scripts/validate_report_quality_review_packet_training_experiment_plan_review.py"
PACKET_VALIDATOR_PATH = REPO_ROOT / "scripts/validate_report_quality_review_packet_training_final_approval_packet.py"
EXPECTED_SCHEMA = "decisiondoc_report_quality_training_final_approval_packet.v1"
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


_PLAN_REVIEW_VALIDATOR = _load_module(
    PLAN_REVIEW_VALIDATOR_PATH,
    "validate_report_quality_review_packet_training_experiment_plan_review",
)
_PACKET_VALIDATOR = _load_module(
    PACKET_VALIDATOR_PATH,
    "validate_report_quality_review_packet_training_final_approval_packet",
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


def _default_output_path(plan_review_path: Path, suffix: str) -> Path:
    name = plan_review_path.name
    if name.endswith("-training-experiment-plan-review.json"):
        base = name.removesuffix("-training-experiment-plan-review.json")
    else:
        base = plan_review_path.stem
    return plan_review_path.with_name(f"{base}{suffix}")


def create_training_final_approval_packet(
    *,
    plan_review_path: Path,
    output_manifest: Path | None = None,
    output_markdown: Path | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    resolved_review = plan_review_path.expanduser().resolve()
    plan_review = _load_json(resolved_review)
    review_validation = _PLAN_REVIEW_VALIDATOR.validate_training_experiment_plan_review(
        plan_review,
        require_complete=True,
    )
    if review_validation.get("ok") is not True:
        errors = "; ".join(review_validation.get("errors") or ["plan review validation failed"])
        raise ValueError(f"training experiment plan review is not complete: {errors}")
    if plan_review.get("decision") != "planning_complete":
        raise ValueError("final approval packet requires plan review decision=planning_complete")
    if plan_review.get("requested_next_step") != "prepare_final_approval_packet":
        raise ValueError("final approval packet requires requested_next_step=prepare_final_approval_packet")

    plan_path = Path(str(plan_review["plan_manifest_path"])).expanduser().resolve()
    plan = _load_json(plan_path)
    output_manifest = (
        output_manifest.expanduser().resolve()
        if output_manifest is not None
        else _default_output_path(resolved_review, "-training-final-approval-packet-manifest.json")
    )
    output_markdown = (
        output_markdown.expanduser().resolve()
        if output_markdown is not None
        else _default_output_path(resolved_review, "-training-final-approval-packet.md")
    )

    source_files = {
        "plan_review_record": _file_record(str(resolved_review)),
        "plan_manifest": _file_record(str(plan_path)),
        "plan_markdown": _file_record(plan.get("plan_markdown_path")),
        "discussion_decision_record": _file_record(plan.get("decision_record_path")),
        "discussion_handoff_manifest": _file_record(plan.get("discussion_handoff_manifest_path")),
    }
    for key, record in sorted(_as_dict(plan.get("source_files")).items()):
        source_files[f"plan_source_{key}"] = _file_record(_as_dict(record).get("path"))

    missing_files = sorted(name for name, record in source_files.items() if record.get("exists") is not True)
    counts = _as_dict(plan.get("counts"))
    packet = {
        "report_type": "report_quality_training_final_approval_packet",
        "schema_version": EXPECTED_SCHEMA,
        "generated_at": generated_at or _now_iso(),
        "packet_manifest_path": str(output_manifest),
        "packet_markdown_path": str(output_markdown),
        "plan_review_path": str(resolved_review),
        "plan_review_sha256": _sha256(resolved_review),
        "plan_manifest_path": str(plan_path),
        "plan_manifest_sha256": _sha256(plan_path),
        "plan_review_validation": review_validation,
        "readiness": {
            "ok": not missing_files,
            "status": "ready_for_manual_final_approval_packet_review" if not missing_files else "follow_up_required",
            "approval_packet_only": True,
            "final_training_approval_granted": False,
            "training_execution_allowed": False,
            "provider_api_calls_allowed": False,
            "external_upload_allowed": False,
            "provider_job_started": False,
            "model_promotion_allowed": False,
            "missing_files": missing_files,
        },
        "counts": {
            "ready_artifacts": counts.get("ready_artifacts", 0),
            "completed_signoff_count": counts.get("completed_signoff_count", 0),
            "source_file_count": len(source_files),
            "missing_file_count": len(missing_files),
        },
        "required_final_approver_roles": REQUIRED_APPROVER_ROLES,
        "source_files": source_files,
        "job_spec_snapshot": _as_dict(plan.get("job_spec")),
        "operator_actions": [
            "Review this packet with all required final approver roles before any execution request.",
            "Record final approval in a separate approval artifact; this packet does not grant approval.",
            "Do not upload datasets, call provider fine-tune APIs, create or poll provider jobs, start training, or promote models from this packet.",
        ],
        "side_effect_boundary": {
            "reads_local_plan_review_record": True,
            "writes_local_final_approval_packet_files": True,
            "actual_training_approval_recorded": False,
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
    _write_text_atomic(output_manifest, json.dumps(packet, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    _write_text_atomic(output_markdown, render_training_final_approval_packet_markdown(packet))
    return packet


def render_training_final_approval_packet_markdown(packet: dict[str, Any]) -> str:
    readiness = _as_dict(packet.get("readiness"))
    counts = _as_dict(packet.get("counts"))
    files = _as_dict(packet.get("source_files"))
    rows = "\n".join(
        "| {name} | {exists} | `{path}` |".format(
            name=name,
            exists="yes" if _as_dict(record).get("exists") else "no",
            path=_as_dict(record).get("path", ""),
        )
        for name, record in files.items()
    )
    if not rows:
        rows = "| - | - | - |"
    roles = "\n".join(f"- {role}" for role in packet.get("required_final_approver_roles", []))
    missing = readiness.get("missing_files") or []
    return f"""# Report Quality Training Final Approval Packet

- generated_at: `{packet.get('generated_at', '-')}`
- status: `{readiness.get('status', '-')}`
- approval_packet_only: `true`
- final_training_approval_granted: `false`
- training_execution_allowed: `false`
- provider_api_calls_allowed: `false`
- external_upload_allowed: `false`
- provider_job_started: `false`
- model_promotion_allowed: `false`
- ready_artifacts: `{counts.get('ready_artifacts', 0)}`
- completed_signoff_count: `{counts.get('completed_signoff_count', 0)}`

## Required Approver Roles

{roles}

## Source Files

| file | exists | path |
| --- | --- | --- |
{rows}

## Operator Actions

{chr(10).join(f"- {item}" for item in packet.get('operator_actions', []))}

## Blockers

{chr(10).join(f"- `{item}`" for item in missing) if missing else "- none"}

## Side-Effect Boundary

- actual_training_approval_recorded: `false`
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
    parser = argparse.ArgumentParser(description="Create a local report quality final approval packet draft.")
    parser.add_argument("plan_review", type=Path, help="Path to completed training experiment plan review JSON.")
    parser.add_argument("--output-manifest", type=Path, default=None)
    parser.add_argument("--output-markdown", type=Path, default=None)
    parser.add_argument("--generated-at", help="Optional ISO timestamp for deterministic output.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable packet manifest to stdout.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(list(argv) if argv is not None else None)
    try:
        packet = create_training_final_approval_packet(
            plan_review_path=args.plan_review,
            output_manifest=args.output_manifest,
            output_markdown=args.output_markdown,
            generated_at=args.generated_at,
        )
        packet_validation = _PACKET_VALIDATOR.validate_training_final_approval_packet(
            Path(packet["packet_manifest_path"]),
        )
    except Exception as exc:
        result = {"ok": False, "error": str(exc)}
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        else:
            print("FAIL report quality training final approval packet generation failed")
            print(f"ERROR {exc}")
        return 1

    if args.json:
        print(json.dumps(packet, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print("Report quality training final approval packet: PASS")
        print(f"approval_packet_only={str(packet['readiness']['approval_packet_only']).lower()}")
        print(f"packet_validation_ok={str(packet_validation['ok']).lower()}")
        print("training_boundary=not_authorized")
    return 0 if packet["readiness"]["ok"] and packet_validation["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
