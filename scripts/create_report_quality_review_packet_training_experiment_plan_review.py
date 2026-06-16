#!/usr/bin/env python3
"""Create a pending human review record for a report quality training experiment plan draft."""
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
DEFAULT_TEMPLATE_PATH = REPO_ROOT / "docs/specs/report_quality_learning/training_experiment_plan_review_template.json"
PLAN_VALIDATOR_PATH = REPO_ROOT / "scripts/validate_report_quality_review_packet_training_experiment_plan_draft.py"
REVIEW_VALIDATOR_PATH = REPO_ROOT / "scripts/validate_report_quality_review_packet_training_experiment_plan_review.py"
REVIEW_ID_PATTERN = re.compile(r"rqp_training_experiment_plan_review_[A-Za-z0-9_-]{8,96}")
BOUNDARY_FALSE_KEYS = (
    "actual_training_approval_recorded",
    "server_file_written",
    "persisted_learning_artifact",
    "external_dataset_upload_authorized",
    "provider_fine_tune_api_call_authorized",
    "provider_job_creation_authorized",
    "provider_job_polling_authorized",
    "training_execution_authorized",
    "model_promotion_authorized",
)
GENERATION_BOUNDARY_FALSE_KEYS = (
    "actual_training_approval_recorded",
    "server_file_written",
    "persisted_learning_artifact",
    "external_dataset_upload_started",
    "provider_fine_tune_api_called",
    "provider_job_created",
    "provider_job_polled",
    "training_execution_started",
    "model_promotion_started",
)


def _load_module(path: Path, module_name: str):
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed to load {module_name}: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_PLAN_VALIDATOR = _load_module(
    PLAN_VALIDATOR_PATH,
    "validate_report_quality_review_packet_training_experiment_plan_draft",
)
_REVIEW_VALIDATOR = _load_module(
    REVIEW_VALIDATOR_PATH,
    "validate_report_quality_review_packet_training_experiment_plan_review",
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path}: JSON root must be an object")
    return payload


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_review_id(value: str | None) -> str:
    review_id = (
        value.strip()
        if isinstance(value, str) and value.strip()
        else f"rqp_training_experiment_plan_review_{uuid4().hex}"
    )
    if not REVIEW_ID_PATTERN.fullmatch(review_id):
        raise ValueError("review id must match rqp_training_experiment_plan_review_[A-Za-z0-9_-]{8,96}")
    return review_id


def _default_output_path(plan_manifest_path: Path) -> Path:
    name = plan_manifest_path.name
    if name.endswith("-training-experiment-plan-draft-manifest.json"):
        base = name.removesuffix("-training-experiment-plan-draft-manifest.json")
    else:
        base = plan_manifest_path.stem
    return plan_manifest_path.with_name(f"{base}-training-experiment-plan-review.json")


def _reset_pending_fields(review: dict[str, Any]) -> None:
    review["decision"] = "pending"
    review["requested_next_step"] = "none"
    review["reviewers"] = [
        {
            "name": "",
            "role_or_team": "",
            "reviewed_at": "",
        }
    ]
    review["review_summary"] = ""
    review["decision_rationale"] = ""
    review["conditions"] = []
    review["evidence_reviewed"] = []

    acknowledgements = _as_dict(review.get("acknowledgements"))
    for key in acknowledgements:
        acknowledgements[key] = False
    review["acknowledgements"] = acknowledgements

    boundary = _as_dict(review.get("review_boundary"))
    for key in BOUNDARY_FALSE_KEYS:
        boundary[key] = False
    review["review_boundary"] = boundary

    generation_boundary = _as_dict(review.get("generation_boundary"))
    for key in GENERATION_BOUNDARY_FALSE_KEYS:
        generation_boundary[key] = False
    review["generation_boundary"] = generation_boundary


def build_pending_training_experiment_plan_review(
    *,
    plan_manifest_path: Path,
    template_path: Path = DEFAULT_TEMPLATE_PATH,
    review_id: str | None = None,
    created_at: str | None = None,
    require_ready: bool = True,
) -> dict[str, Any]:
    resolved_plan = plan_manifest_path.expanduser().resolve()
    resolved_template = template_path.expanduser().resolve()
    plan_validation = _PLAN_VALIDATOR.validate_training_experiment_plan_draft(
        resolved_plan,
        require_ready=require_ready,
    )
    if require_ready and plan_validation.get("ok") is not True:
        errors = "; ".join(plan_validation.get("errors") or ["training experiment plan draft validation failed"])
        raise ValueError(f"training experiment plan draft is not ready for review generation: {errors}")

    template = _load_json(resolved_template)
    plan = _load_json(resolved_plan)
    review = dict(template)
    _reset_pending_fields(review)

    source_files = _as_dict(plan.get("source_files"))
    evidence_to_review = [
        str(resolved_plan),
        str(plan.get("plan_markdown_path", "")),
        str(plan.get("decision_record_path", "")),
        str(plan.get("discussion_handoff_manifest_path", "")),
    ]
    for record in source_files.values():
        path_value = _as_dict(record).get("path")
        if str(path_value or "").strip():
            evidence_to_review.append(str(path_value))

    review.update(
        {
            "review_id": _safe_review_id(review_id),
            "created_at": created_at or _now_iso(),
            "plan_manifest_path": str(resolved_plan),
            "plan_manifest_sha256": _sha256(resolved_plan),
            "generation_context": {
                "report_type": "report_quality_training_experiment_plan_pending_review_generation",
                "generated_from_template": str(resolved_template),
                "plan_validation": plan_validation,
                "plan_readiness": _as_dict(plan.get("readiness")),
                "plan_counts": _as_dict(plan.get("counts")),
                "evidence_to_review": evidence_to_review,
                "review_scope": (
                    "This record reviews whether the plan draft is ready for a separate final "
                    "approval packet. It cannot authorize dataset upload, provider fine-tune API "
                    "calls, provider jobs, training execution, or model promotion."
                ),
            },
            "next_step_after_generation": (
                "Human reviewers fill reviewers, decision, requested_next_step, evidence_reviewed, "
                "review_summary, decision_rationale, conditions if needed, and acknowledgements, then "
                "run validate_report_quality_review_packet_training_experiment_plan_review.py --require-complete."
            ),
        }
    )
    return review


def write_pending_review(review: dict[str, Any], *, output_path: Path, overwrite: bool = False) -> Path:
    resolved_output = output_path.expanduser().resolve()
    resolved_output.parent.mkdir(parents=True, exist_ok=True)
    if resolved_output.exists() and not overwrite:
        raise FileExistsError(f"output already exists: {resolved_output}")
    tmp = resolved_output.with_name(f"{resolved_output.name}.tmp")
    tmp.write_text(json.dumps(review, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(resolved_output)
    return resolved_output


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Create a pending training experiment plan review record.")
    parser.add_argument("plan_manifest", type=Path, help="Path to *-training-experiment-plan-draft-manifest.json.")
    parser.add_argument("--template", type=Path, default=DEFAULT_TEMPLATE_PATH)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument(
        "--review-id",
        help="Optional deterministic id matching rqp_training_experiment_plan_review_[A-Za-z0-9_-]{8,96}.",
    )
    parser.add_argument("--created-at", help="Optional ISO timestamp for deterministic generation.")
    parser.add_argument("--allow-not-ready", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--json", action="store_true", help="Print generated review JSON to stdout.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(list(argv) if argv is not None else None)
    try:
        resolved_plan = args.plan_manifest.expanduser().resolve()
        review = build_pending_training_experiment_plan_review(
            plan_manifest_path=resolved_plan,
            template_path=args.template,
            review_id=args.review_id,
            created_at=args.created_at,
            require_ready=not args.allow_not_ready,
        )
        output_path = (
            args.output.expanduser().resolve()
            if args.output is not None
            else _default_output_path(resolved_plan)
        )
        written_path = write_pending_review(review, output_path=output_path, overwrite=args.overwrite)
        validation = _REVIEW_VALIDATOR.validate_training_experiment_plan_review(review, require_complete=False)
    except Exception as exc:
        result = {"ok": False, "error": str(exc)}
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        else:
            print("FAIL report quality training experiment plan pending review generation failed")
            print(f"ERROR {exc}")
        return 1

    if args.json:
        print(json.dumps(review, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print("Report quality training experiment plan pending review: PASS")
        print(f"review_id={review['review_id']}")
        print(f"output_path={written_path}")
        print(f"pending_validation_ok={str(validation['ok']).lower()}")
        print("training_boundary=not_authorized")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
