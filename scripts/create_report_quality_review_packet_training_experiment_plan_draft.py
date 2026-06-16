#!/usr/bin/env python3
"""Create a local report quality training experiment plan draft from a completed discussion decision."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
from typing import Any, Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
DECISION_VALIDATOR_PATH = REPO_ROOT / "scripts/validate_report_quality_review_packet_training_discussion_decision.py"
EXPECTED_SCHEMA = "decisiondoc_report_quality_training_experiment_plan_draft.v1"
REQUIRED_EVAL_METRICS = [
    "logic_quality",
    "evidence_grounding",
    "public_sector_tone",
    "slide_structure",
    "visual_design",
    "export_readiness",
]


def _load_decision_validator():
    spec = importlib.util.spec_from_file_location(
        "validate_report_quality_review_packet_training_discussion_decision",
        DECISION_VALIDATOR_PATH,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed to load decision validator: {DECISION_VALIDATOR_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_DECISION_VALIDATOR = _load_decision_validator()


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
    tmp = path.with_name(f"{path.name}.tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def _default_output_path(decision_record_path: Path, suffix: str) -> Path:
    name = decision_record_path.name
    if name.endswith("-training-discussion-decision.json"):
        base = name.removesuffix("-training-discussion-decision.json")
    else:
        base = decision_record_path.stem
    return decision_record_path.with_name(f"{base}{suffix}")


def _file_hash_from_handoff(handoff: dict[str, Any], key: str) -> dict[str, Any]:
    return _as_dict(_as_dict(handoff.get("handoff_files")).get(key))


def create_training_experiment_plan_draft(
    *,
    decision_record_path: Path,
    output_manifest: Path | None = None,
    output_markdown: Path | None = None,
    provider: str = "provider_agnostic",
    base_model: str | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    resolved_decision = decision_record_path.expanduser().resolve()
    decision_record = _load_json(resolved_decision)
    decision_validation = _DECISION_VALIDATOR.validate_training_discussion_decision(
        decision_record,
        require_complete=True,
    )
    if decision_validation.get("ok") is not True:
        errors = "; ".join(decision_validation.get("errors") or ["discussion decision validation failed"])
        raise ValueError(f"training discussion decision is not complete: {errors}")
    if decision_record.get("decision") != "plan_draft_requested":
        raise ValueError("training experiment plan draft requires decision=plan_draft_requested")
    if decision_record.get("requested_next_step") != "draft_training_experiment_plan":
        raise ValueError("training experiment plan draft requires requested_next_step=draft_training_experiment_plan")

    handoff_path = Path(str(decision_record["discussion_handoff_manifest_path"])).expanduser().resolve()
    handoff = _load_json(handoff_path)
    output_manifest = (
        output_manifest.expanduser().resolve()
        if output_manifest is not None
        else _default_output_path(resolved_decision, "-training-experiment-plan-draft-manifest.json")
    )
    output_markdown = (
        output_markdown.expanduser().resolve()
        if output_markdown is not None
        else _default_output_path(resolved_decision, "-training-experiment-plan-draft.md")
    )

    counts = _as_dict(handoff.get("counts"))
    readiness_manifest = _file_hash_from_handoff(handoff, "training_readiness_manifest")
    evidence_manifest = _file_hash_from_handoff(handoff, "evidence_pipeline_manifest")
    artifact_jsonl = _file_hash_from_handoff(handoff, "evidence_artifact_jsonl")
    signoff_summary = _file_hash_from_handoff(handoff, "signoff_summary")
    job_spec = {
        "provider": provider,
        "base_model": base_model or "to_be_selected_after_manual_approval",
        "dataset": {
            "source": "report_quality_review_packet_evidence",
            "artifact_jsonl_path": artifact_jsonl.get("path", ""),
            "artifact_jsonl_sha256": artifact_jsonl.get("sha256", ""),
            "evidence_manifest_path": evidence_manifest.get("path", ""),
            "evidence_manifest_sha256": evidence_manifest.get("sha256", ""),
            "ready_artifacts": counts.get("ready_artifacts", 0),
            "completed_signoff_count": counts.get("completed_signoff_count", 0),
        },
        "evaluation": {
            "suite": "report_quality_offline_eval",
            "required_metrics": REQUIRED_EVAL_METRICS,
            "minimum_expected_result": "no_regression_against_current_quality_rubric",
        },
        "parameters": {
            "training_method": "small_sft_experiment_candidate",
            "epochs": "manual_selection_required",
            "learning_rate": "manual_selection_required",
            "validation_split": "manual_selection_required",
        },
        "execution_steps": [
            {"step": "final_manual_training_approval", "status": "not_started"},
            {"step": "prepare_dataset_upload", "status": "not_started"},
            {"step": "call_provider_fine_tune_api", "status": "not_started"},
            {"step": "monitor_provider_job", "status": "not_started"},
            {"step": "run_offline_eval", "status": "not_started"},
            {"step": "model_promotion_review", "status": "not_started"},
        ],
    }
    plan = {
        "report_type": "report_quality_training_experiment_plan_draft",
        "schema_version": EXPECTED_SCHEMA,
        "generated_at": generated_at or _now_iso(),
        "plan_manifest_path": str(output_manifest),
        "plan_markdown_path": str(output_markdown),
        "decision_record_path": str(resolved_decision),
        "decision_record_sha256": _sha256(resolved_decision),
        "discussion_handoff_manifest_path": str(handoff_path),
        "discussion_handoff_manifest_sha256": _sha256(handoff_path),
        "decision_validation": decision_validation,
        "readiness": {
            "ok": True,
            "status": "draft_ready_for_manual_training_experiment_planning",
            "planning_only": True,
            "training_execution_allowed": False,
            "provider_api_calls_allowed": False,
            "external_upload_allowed": False,
            "provider_job_started": False,
            "model_promotion_allowed": False,
        },
        "source_files": {
            "training_readiness_manifest": readiness_manifest,
            "evidence_pipeline_manifest": evidence_manifest,
            "artifact_jsonl": artifact_jsonl,
            "signoff_summary": signoff_summary,
        },
        "counts": {
            "ready_artifacts": counts.get("ready_artifacts", 0),
            "completed_signoff_count": counts.get("completed_signoff_count", 0),
            "handoff_file_count": counts.get("handoff_file_count", 0),
        },
        "job_spec": job_spec,
        "operator_actions": [
            "Review this plan draft with ML/AI, Product/PM, Compliance/Security, and Release owner roles.",
            "Choose provider, base model, training parameters, and evaluation thresholds in a separate approval record.",
            "Do not upload datasets, call provider fine-tune APIs, create provider jobs, start training, or promote models from this draft.",
        ],
        "side_effect_boundary": {
            "reads_local_training_discussion_decision": True,
            "writes_local_plan_draft_files": True,
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
    _write_text_atomic(output_manifest, json.dumps(plan, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    _write_text_atomic(output_markdown, render_training_experiment_plan_draft_markdown(plan))
    return plan


def render_training_experiment_plan_draft_markdown(plan: dict[str, Any]) -> str:
    readiness = _as_dict(plan.get("readiness"))
    counts = _as_dict(plan.get("counts"))
    job_spec = _as_dict(plan.get("job_spec"))
    dataset = _as_dict(job_spec.get("dataset"))
    evaluation = _as_dict(job_spec.get("evaluation"))
    steps = "\n".join(
        f"- `{_as_dict(step).get('step', '-')}`: `{_as_dict(step).get('status', '-')}`"
        for step in job_spec.get("execution_steps", [])
    )
    return f"""# Report Quality Training Experiment Plan Draft

- generated_at: `{plan.get('generated_at', '-')}`
- status: `{readiness.get('status', '-')}`
- planning_only: `true`
- training_execution_allowed: `false`
- provider_api_calls_allowed: `false`
- external_upload_allowed: `false`
- provider_job_started: `false`
- model_promotion_allowed: `false`
- ready_artifacts: `{counts.get('ready_artifacts', 0)}`
- completed_signoff_count: `{counts.get('completed_signoff_count', 0)}`

## Dataset Reference

- artifact_jsonl_path: `{dataset.get('artifact_jsonl_path', '')}`
- artifact_jsonl_sha256: `{dataset.get('artifact_jsonl_sha256', '')}`
- evidence_manifest_path: `{dataset.get('evidence_manifest_path', '')}`

## Job Spec

- provider: `{job_spec.get('provider', '-')}`
- base_model: `{job_spec.get('base_model', '-')}`
- evaluation_suite: `{evaluation.get('suite', '-')}`
- required_metrics: `{', '.join(str(item) for item in evaluation.get('required_metrics', []))}`

## Execution Steps

{steps}

## Operator Actions

{chr(10).join(f"- {item}" for item in plan.get('operator_actions', []))}

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
    parser = argparse.ArgumentParser(description="Create a local report quality training experiment plan draft.")
    parser.add_argument("decision_record", type=Path, help="Path to completed training discussion decision JSON.")
    parser.add_argument("--output-manifest", type=Path, default=None)
    parser.add_argument("--output-markdown", type=Path, default=None)
    parser.add_argument("--provider", default="provider_agnostic")
    parser.add_argument("--base-model", default=None)
    parser.add_argument("--generated-at", help="Optional ISO timestamp for deterministic output.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable plan draft to stdout.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(list(argv) if argv is not None else None)
    try:
        plan = create_training_experiment_plan_draft(
            decision_record_path=args.decision_record,
            output_manifest=args.output_manifest,
            output_markdown=args.output_markdown,
            provider=args.provider,
            base_model=args.base_model,
            generated_at=args.generated_at,
        )
    except Exception as exc:
        result = {"ok": False, "error": str(exc)}
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        else:
            print("FAIL report quality training experiment plan draft generation failed")
            print(f"ERROR {exc}")
        return 1

    if args.json:
        print(json.dumps(plan, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print("Report quality training experiment plan draft: PASS")
        print(f"planning_only={str(plan['readiness']['planning_only']).lower()}")
        print(f"ready_artifacts={plan['counts']['ready_artifacts']}")
        print("training_boundary=not_authorized")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
