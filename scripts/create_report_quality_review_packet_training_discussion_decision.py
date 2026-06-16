#!/usr/bin/env python3
"""Create a pending training discussion decision record for report quality evidence."""
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
DEFAULT_TEMPLATE_PATH = REPO_ROOT / "docs/specs/report_quality_learning/training_discussion_decision_template.json"
HANDOFF_VALIDATOR_PATH = REPO_ROOT / "scripts/validate_report_quality_review_packet_training_discussion_handoff.py"
DECISION_VALIDATOR_PATH = REPO_ROOT / "scripts/validate_report_quality_review_packet_training_discussion_decision.py"
DECISION_ID_PATTERN = re.compile(r"rqp_training_discussion_decision_[A-Za-z0-9_-]{8,96}")
BOUNDARY_FALSE_KEYS = (
    "actual_training_approval_recorded",
    "server_file_written",
    "persisted_learning_artifact",
    "external_dataset_upload_authorized",
    "provider_fine_tune_api_call_authorized",
    "provider_job_creation_authorized",
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


_HANDOFF_VALIDATOR = _load_module(
    HANDOFF_VALIDATOR_PATH,
    "validate_report_quality_review_packet_training_discussion_handoff",
)
_DECISION_VALIDATOR = _load_module(
    DECISION_VALIDATOR_PATH,
    "validate_report_quality_review_packet_training_discussion_decision",
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


def _safe_decision_id(value: str | None) -> str:
    decision_id = (
        value.strip()
        if isinstance(value, str) and value.strip()
        else f"rqp_training_discussion_decision_{uuid4().hex}"
    )
    if not DECISION_ID_PATTERN.fullmatch(decision_id):
        raise ValueError("decision id must match rqp_training_discussion_decision_[A-Za-z0-9_-]{8,96}")
    return decision_id


def _default_output_path(handoff_manifest_path: Path) -> Path:
    name = handoff_manifest_path.name
    if name.endswith("-training-discussion-handoff-manifest.json"):
        base = name.removesuffix("-training-discussion-handoff-manifest.json")
    else:
        base = handoff_manifest_path.stem
    return handoff_manifest_path.with_name(f"{base}-training-discussion-decision.json")


def _reset_pending_fields(decision_record: dict[str, Any]) -> None:
    decision_record["decision"] = "pending"
    decision_record["participants"] = [
        {
            "name": "",
            "role_or_team": "",
            "reviewed_at": "",
        }
    ]
    decision_record["discussion_summary"] = ""
    decision_record["decision_rationale"] = ""
    decision_record["requested_next_step"] = "none"
    decision_record["conditions"] = []
    decision_record["evidence_reviewed"] = []

    acknowledgements = _as_dict(decision_record.get("acknowledgements"))
    for key in acknowledgements:
        acknowledgements[key] = False
    decision_record["acknowledgements"] = acknowledgements

    boundary = _as_dict(decision_record.get("decision_boundary"))
    for key in BOUNDARY_FALSE_KEYS:
        boundary[key] = False
    decision_record["decision_boundary"] = boundary

    generation_boundary = _as_dict(decision_record.get("generation_boundary"))
    for key in GENERATION_BOUNDARY_FALSE_KEYS:
        generation_boundary[key] = False
    decision_record["generation_boundary"] = generation_boundary


def build_pending_training_discussion_decision(
    *,
    discussion_handoff_manifest_path: Path,
    template_path: Path = DEFAULT_TEMPLATE_PATH,
    decision_id: str | None = None,
    created_at: str | None = None,
    require_ready: bool = True,
) -> dict[str, Any]:
    resolved_handoff_manifest = discussion_handoff_manifest_path.expanduser().resolve()
    resolved_template = template_path.expanduser().resolve()
    handoff_validation = _HANDOFF_VALIDATOR.validate_training_discussion_handoff_manifest(
        resolved_handoff_manifest,
        require_ready=require_ready,
    )
    if require_ready and handoff_validation.get("ok") is not True:
        errors = "; ".join(handoff_validation.get("errors") or ["training discussion handoff validation failed"])
        raise ValueError(f"training discussion handoff is not ready for decision generation: {errors}")

    template = _load_json(resolved_template)
    handoff_manifest = _load_json(resolved_handoff_manifest)
    decision_record = dict(template)
    _reset_pending_fields(decision_record)

    handoff_files = _as_dict(handoff_manifest.get("handoff_files"))
    evidence_to_review = [
        str(_as_dict(record).get("path"))
        for _, record in sorted(handoff_files.items())
        if str(_as_dict(record).get("path", "")).strip()
    ]

    decision_record.update(
        {
            "decision_id": _safe_decision_id(decision_id),
            "created_at": created_at or _now_iso(),
            "discussion_handoff_manifest_path": str(resolved_handoff_manifest),
            "discussion_handoff_manifest_sha256": _sha256(resolved_handoff_manifest),
            "generation_context": {
                "report_type": "report_quality_training_discussion_pending_decision_generation",
                "generated_from_template": str(resolved_template),
                "handoff_validation": handoff_validation,
                "handoff_readiness": _as_dict(handoff_manifest.get("readiness")),
                "handoff_counts": _as_dict(handoff_manifest.get("counts")),
                "evidence_to_review": evidence_to_review,
                "decision_scope": (
                    "This record can request a future training experiment plan draft, but it cannot "
                    "authorize dataset upload, provider fine-tune API calls, training execution, "
                    "provider job creation, or model promotion."
                ),
            },
            "next_step_after_generation": (
                "Human participants fill participants, decision, requested_next_step, evidence_reviewed, "
                "discussion_summary, decision_rationale, conditions if needed, and acknowledgements, then "
                "run validate_report_quality_review_packet_training_discussion_decision.py --require-complete."
            ),
        }
    )
    return decision_record


def write_pending_decision(decision_record: dict[str, Any], *, output_path: Path, overwrite: bool = False) -> Path:
    resolved_output = output_path.expanduser().resolve()
    resolved_output.parent.mkdir(parents=True, exist_ok=True)
    if resolved_output.exists() and not overwrite:
        raise FileExistsError(f"output already exists: {resolved_output}")
    tmp = resolved_output.with_name(f"{resolved_output.name}.tmp")
    tmp.write_text(json.dumps(decision_record, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(resolved_output)
    return resolved_output


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Create a pending report quality training discussion decision record.")
    parser.add_argument("discussion_handoff_manifest", type=Path, help="Path to *-training-discussion-handoff-manifest.json.")
    parser.add_argument("--template", type=Path, default=DEFAULT_TEMPLATE_PATH)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument(
        "--decision-id",
        help="Optional deterministic id matching rqp_training_discussion_decision_[A-Za-z0-9_-]{8,96}.",
    )
    parser.add_argument("--created-at", help="Optional ISO timestamp for deterministic generation.")
    parser.add_argument("--allow-not-ready", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--json", action="store_true", help="Print generated decision JSON to stdout.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(list(argv) if argv is not None else None)
    try:
        resolved_handoff = args.discussion_handoff_manifest.expanduser().resolve()
        decision_record = build_pending_training_discussion_decision(
            discussion_handoff_manifest_path=resolved_handoff,
            template_path=args.template,
            decision_id=args.decision_id,
            created_at=args.created_at,
            require_ready=not args.allow_not_ready,
        )
        output_path = (
            args.output.expanduser().resolve()
            if args.output is not None
            else _default_output_path(resolved_handoff)
        )
        written_path = write_pending_decision(decision_record, output_path=output_path, overwrite=args.overwrite)
        validation = _DECISION_VALIDATOR.validate_training_discussion_decision(
            decision_record,
            require_complete=False,
        )
    except Exception as exc:
        result = {"ok": False, "error": str(exc)}
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        else:
            print("FAIL report quality training discussion pending decision generation failed")
            print(f"ERROR {exc}")
        return 1

    if args.json:
        print(json.dumps(decision_record, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print("Report quality training discussion pending decision: PASS")
        print(f"decision_id={decision_record['decision_id']}")
        print(f"output_path={written_path}")
        print(f"pending_validation_ok={str(validation['ok']).lower()}")
        print("training_boundary=not_authorized")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
