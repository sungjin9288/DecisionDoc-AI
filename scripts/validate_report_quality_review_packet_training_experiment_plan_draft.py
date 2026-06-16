#!/usr/bin/env python3
"""Validate a local report quality training experiment plan draft."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
from typing import Any, Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
DECISION_VALIDATOR_PATH = REPO_ROOT / "scripts/validate_report_quality_review_packet_training_discussion_decision.py"
EXPECTED_SCHEMA = "decisiondoc_report_quality_training_experiment_plan_draft.v1"
FORBIDDEN_TRUE_KEYS = {
    "actual_training_approval_recorded",
    "server_file_written",
    "persisted_learning_artifact",
    "external_dataset_upload_started",
    "external_upload_allowed",
    "provider_api_calls_allowed",
    "provider_fine_tune_api_called",
    "provider_job_created",
    "provider_job_polled",
    "provider_job_started",
    "training_execution_allowed",
    "training_execution_started",
    "model_promotion_allowed",
    "model_promotion_started",
}


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


def _resolve_path(path_value: Any, *, field: str, errors: list[str]) -> Path | None:
    if not isinstance(path_value, str) or not path_value.strip():
        errors.append(f"{field} must be a non-empty path")
        return None
    path = Path(path_value).expanduser().resolve()
    if not path.exists() or not path.is_file():
        errors.append(f"{field} does not exist: {path}")
        return None
    return path


def _scan_forbidden_true(value: Any, *, path: str = "$") -> list[str]:
    findings: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}"
            if key in FORBIDDEN_TRUE_KEYS and child is not False:
                findings.append(f"{child_path} must be false")
            findings.extend(_scan_forbidden_true(child, path=child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            findings.extend(_scan_forbidden_true(child, path=f"{path}[{index}]"))
    return findings


def _validate_hash(*, path: Path | None, expected_hash: Any, field: str, errors: list[str]) -> None:
    if path is None:
        return
    if not isinstance(expected_hash, str) or not expected_hash.strip():
        errors.append(f"{field} must be non-empty")
    elif expected_hash != _sha256(path):
        errors.append(f"{field} does not match referenced file")


def validate_training_experiment_plan_draft(
    plan_manifest_path: Path,
    *,
    require_ready: bool = True,
) -> dict[str, Any]:
    resolved_plan = plan_manifest_path.expanduser().resolve()
    errors: list[str] = []
    warnings: list[str] = []
    try:
        plan = _load_json(resolved_plan)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return {
            "report_type": "report_quality_training_experiment_plan_draft_validation",
            "ok": False,
            "require_ready": require_ready,
            "plan_manifest_path": str(resolved_plan),
            "errors": [str(exc)],
            "warnings": [],
        }

    if plan.get("schema_version") != EXPECTED_SCHEMA:
        errors.append(f"schema_version must be {EXPECTED_SCHEMA!r}")

    recorded_plan_path = _resolve_path(plan.get("plan_manifest_path"), field="plan_manifest_path", errors=errors)
    if recorded_plan_path is not None and recorded_plan_path != resolved_plan:
        warnings.append("plan_manifest_path points to a different path than the validated manifest")

    markdown_path = _resolve_path(plan.get("plan_markdown_path"), field="plan_markdown_path", errors=errors)
    if markdown_path is not None:
        markdown = markdown_path.read_text(encoding="utf-8")
        if "Report Quality Training Experiment Plan Draft" not in markdown:
            errors.append("plan markdown is missing title")
        if "training_execution_allowed: `false`" not in markdown:
            errors.append("plan markdown must show training_execution_allowed=false")

    decision_path = _resolve_path(plan.get("decision_record_path"), field="decision_record_path", errors=errors)
    _validate_hash(
        path=decision_path,
        expected_hash=plan.get("decision_record_sha256"),
        field="decision_record_sha256",
        errors=errors,
    )
    decision_validation: dict[str, Any] = {}
    if decision_path is not None:
        decision_record = _load_json(decision_path)
        decision_validation = _DECISION_VALIDATOR.validate_training_discussion_decision(
            decision_record,
            require_complete=True,
        )
        if require_ready and decision_validation.get("ok") is not True:
            errors.append("training discussion decision validation must pass")
        if decision_record.get("decision") != "plan_draft_requested":
            errors.append("decision_record.decision must be plan_draft_requested")
        if decision_record.get("requested_next_step") != "draft_training_experiment_plan":
            errors.append("decision_record.requested_next_step must be draft_training_experiment_plan")

    handoff_path = _resolve_path(
        plan.get("discussion_handoff_manifest_path"),
        field="discussion_handoff_manifest_path",
        errors=errors,
    )
    _validate_hash(
        path=handoff_path,
        expected_hash=plan.get("discussion_handoff_manifest_sha256"),
        field="discussion_handoff_manifest_sha256",
        errors=errors,
    )

    embedded_decision_validation = _as_dict(plan.get("decision_validation"))
    if require_ready and embedded_decision_validation.get("ok") is not True:
        errors.append("embedded decision_validation.ok must be true")

    readiness = _as_dict(plan.get("readiness"))
    if require_ready and readiness.get("ok") is not True:
        errors.append("readiness.ok must be true")
    if readiness.get("planning_only") is not True:
        errors.append("readiness.planning_only must be true")

    counts = _as_dict(plan.get("counts"))
    if require_ready and int(counts.get("ready_artifacts") or 0) < 1:
        errors.append("counts.ready_artifacts must be at least 1")
    if require_ready and int(counts.get("completed_signoff_count") or 0) < 1:
        errors.append("counts.completed_signoff_count must be at least 1")

    source_files = _as_dict(plan.get("source_files"))
    for name, record_value in source_files.items():
        record = _as_dict(record_value)
        if name in {"artifact_jsonl", "evidence_pipeline_manifest", "training_readiness_manifest", "signoff_summary"}:
            path = _resolve_path(record.get("path"), field=f"source_files.{name}.path", errors=errors)
            _validate_hash(
                path=path,
                expected_hash=record.get("sha256"),
                field=f"source_files.{name}.sha256",
                errors=errors,
            )

    job_spec = _as_dict(plan.get("job_spec"))
    if not str(job_spec.get("provider", "")).strip():
        errors.append("job_spec.provider must be non-empty")
    dataset = _as_dict(job_spec.get("dataset"))
    if not str(dataset.get("artifact_jsonl_path", "")).strip():
        errors.append("job_spec.dataset.artifact_jsonl_path must be non-empty")
    evaluation = _as_dict(job_spec.get("evaluation"))
    if evaluation.get("suite") != "report_quality_offline_eval":
        errors.append("job_spec.evaluation.suite must be report_quality_offline_eval")
    if len(_as_list(evaluation.get("required_metrics"))) < 6:
        errors.append("job_spec.evaluation.required_metrics must include at least six metrics")

    execution_steps = _as_list(job_spec.get("execution_steps"))
    if len(execution_steps) < 5:
        errors.append("job_spec.execution_steps must include at least five steps")
    for index, step_value in enumerate(execution_steps, start=1):
        step = _as_dict(step_value)
        if step.get("status") != "not_started":
            errors.append(f"job_spec.execution_steps[{index}].status must be not_started")

    operator_actions = plan.get("operator_actions")
    if not isinstance(operator_actions, list) or len(operator_actions) < 3:
        errors.append("operator_actions must include at least three actions")
    elif not any("Do not upload datasets" in str(item) for item in operator_actions):
        errors.append("operator_actions must explicitly prohibit dataset upload")

    for finding in _scan_forbidden_true(plan):
        errors.append(f"training_experiment_plan_draft: {finding}")

    return {
        "report_type": "report_quality_training_experiment_plan_draft_validation",
        "ok": not errors,
        "require_ready": require_ready,
        "plan_manifest_path": str(resolved_plan),
        "schema_version": plan.get("schema_version"),
        "planning_only": readiness.get("planning_only") is True,
        "decision_validation_ok": decision_validation.get("ok") if decision_validation else None,
        "ready_artifacts": counts.get("ready_artifacts", 0),
        "errors": errors,
        "warnings": warnings,
    }


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate a local report quality training experiment plan draft.")
    parser.add_argument("plan_manifest", type=Path, help="Path to *-training-experiment-plan-draft-manifest.json.")
    parser.add_argument("--allow-not-ready", action="store_true")
    parser.add_argument("--json", action="store_true", help="Print machine-readable validation result.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(list(argv) if argv is not None else None)
    result = validate_training_experiment_plan_draft(
        args.plan_manifest,
        require_ready=not args.allow_not_ready,
    )
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    elif result["ok"]:
        print("PASS report quality training experiment plan draft validated")
        print(f"planning_only={str(result['planning_only']).lower()}")
        print(f"ready_artifacts={result['ready_artifacts']}")
        print("training_boundary=not_authorized")
        for warning in result["warnings"]:
            print(f"WARN {warning}")
    else:
        print("FAIL report quality training experiment plan draft validation failed")
        for error in result["errors"]:
            print(f"ERROR {error}")
        for warning in result["warnings"]:
            print(f"WARN {warning}")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
