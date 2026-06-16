#!/usr/bin/env python3
"""Create a pending DocumentOps Phase 130 validated handoff sign-off record."""
from __future__ import annotations

import argparse
import copy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sys
from typing import Any, Sequence
from uuid import uuid4


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.validate_documentops_phase129_validated_closure_receipt_summary_handoff_signoff_closure_receipt_summary_handoff_signoff_closure_receipt_summary_handoff_signoff_closure_receipt_summary_handoff_signoff import (  # noqa: E402
    validate_documentops_phase129_validated_closure_receipt_summary_handoff_signoff,
)


DEFAULT_TEMPLATE_PATH = (
    REPO_ROOT
    / "docs/specs/hermes_decisiondoc_agent/"
    "phase130_local_feature_completion_validated_closure_receipt_summary_handoff_signoff_"
    "closure_receipt_summary_handoff_signoff_closure_receipt_summary_handoff_signoff_"
    "closure_receipt_summary_handoff_signoff/"
    "validated_closure_receipt_summary_handoff_signoff_closure_receipt_summary_handoff_signoff_"
    "closure_receipt_summary_handoff_signoff_closure_receipt_summary_handoff_signoff_template.json"
)
SIGNOFF_ID_PREFIX = "documentops_local_feature_completion_phase129_validated_closure_receipt_summary_handoff_signoff_"
SIGNOFF_ID_PATTERN = re.compile(rf"{SIGNOFF_ID_PREFIX}[A-Za-z0-9_-]{{8,96}}")
BOUNDARY_FALSE_KEYS = (
    "actual_reviewer_approval_recorded_by_template",
    "service_resume_authorized",
    "production_ui_called",
    "production_uat_reexecuted",
    "production_download_open_verification_authorized",
    "aws_runtime_called",
    "aws_cost_increase_allowed",
    "aws_deploy_authorized",
    "aws_resource_creation_authorized",
    "scheduled_job_authorized",
    "cloudwatch_polling_authorized",
    "provider_api_calls_authorized",
    "provider_fine_tune_api_called",
    "provider_job_creation_authorized",
    "provider_job_polling_authorized",
    "external_dataset_upload_authorized",
    "training_execution_authorized",
    "model_candidate_emission_authorized",
    "model_promotion_authorized",
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path}: JSON root must be an object")
    return payload


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_signoff_id(value: str | None) -> str:
    signoff_id = (
        value.strip()
        if isinstance(value, str) and value.strip()
        else f"{SIGNOFF_ID_PREFIX}{uuid4().hex}"
    )
    if not SIGNOFF_ID_PATTERN.fullmatch(signoff_id):
        raise ValueError(f"signoff id must match {SIGNOFF_ID_PREFIX}[A-Za-z0-9_-]{{8,96}}")
    if signoff_id.endswith("_TEMPLATE"):
        raise ValueError("pending signoff id must not use the template id")
    return signoff_id


def _reset_pending_fields(signoff: dict[str, Any]) -> None:
    signoff["decision"] = "pending"
    signoff["reviewer"] = {
        "name": "",
        "title_or_team": "",
        "reviewed_at": "",
    }
    signoff["evidence_reviewed"] = []
    signoff["findings"] = {
        "summary": "",
        "changes_requested": [],
        "residual_risks": [],
    }
    acknowledgements = _as_dict(signoff.get("acknowledgements"))
    for key in acknowledgements:
        acknowledgements[key] = False
    signoff["acknowledgements"] = acknowledgements

    boundary = _as_dict(signoff.get("signoff_boundary"))
    boundary["evidence_only_signoff"] = True
    boundary["service_freeze_preserved"] = True
    boundary["resume_requires_separate_approval"] = True
    for key in BOUNDARY_FALSE_KEYS:
        boundary[key] = False
    boundary["aws_cost_boundary"] = "no_cost_increase"
    boundary["training_boundary"] = "not_authorized"
    signoff["signoff_boundary"] = boundary


def _append_unique_path(paths: list[str], value: Any) -> None:
    if not isinstance(value, str) or not value.strip():
        return
    path = str((REPO_ROOT / value).resolve()) if not Path(value).is_absolute() else str(Path(value).resolve())
    if path not in paths:
        paths.append(path)


def _evidence_to_review(signoff: dict[str, Any], template_path: Path) -> list[str]:
    paths: list[str] = []
    _append_unique_path(paths, str(template_path))
    source_handoff = _as_dict(signoff.get("source_handoff"))
    _append_unique_path(paths, source_handoff.get("path"))
    _append_unique_path(paths, source_handoff.get("validator"))
    return paths


def build_pending_documentops_phase130_validated_closure_receipt_summary_handoff_signoff(
    *,
    template_path: Path = DEFAULT_TEMPLATE_PATH,
    signoff_id: str | None = None,
    created_at: str | None = None,
) -> dict[str, Any]:
    resolved_template = template_path.expanduser().resolve()
    safe_signoff_id = _safe_signoff_id(signoff_id)
    template = _load_json(resolved_template)
    source_template_validation = validate_documentops_phase129_validated_closure_receipt_summary_handoff_signoff(
        template
    )
    if source_template_validation.get("ok") is not True:
        errors = "; ".join(source_template_validation.get("errors") or ["source template validation failed"])
        raise ValueError(f"source template is invalid: {errors}")

    signoff = copy.deepcopy(template)
    _reset_pending_fields(signoff)

    signoff["signoff_id"] = safe_signoff_id
    signoff["created_at"] = created_at or _now_iso()
    signoff["generation_context"] = {
        "report_type": (
            "document_ops_phase131_local_feature_completion_validated_closure_receipt_summary_"
            "handoff_signoff_pending_signoff_generation"
        ),
        "generated_from_template": str(resolved_template),
        "generated_from_template_sha256": _sha256_file(resolved_template),
        "source_template_validation": source_template_validation,
        "evidence_to_review": _evidence_to_review(signoff, resolved_template),
    }
    signoff["generation_boundary"] = {
        "local_pending_record_generation": True,
        "evidence_only_signoff": True,
        "service_freeze_preserved": True,
        "resume_requires_separate_approval": True,
        "actual_reviewer_approval_recorded": False,
        "service_resume_authorized": False,
        "production_ui_called": False,
        "production_uat_reexecuted": False,
        "production_download_open_verification_authorized": False,
        "aws_runtime_called": False,
        "aws_cost_increase_allowed": False,
        "aws_deploy_started": False,
        "aws_resource_created": False,
        "scheduled_job_enabled": False,
        "cloudwatch_polling_started": False,
        "provider_api_calls_authorized": False,
        "provider_fine_tune_api_called": False,
        "provider_job_created": False,
        "provider_job_polled": False,
        "external_dataset_uploaded": False,
        "training_execution_started": False,
        "model_candidate_emitted": False,
        "model_promoted": False,
        "aws_cost_boundary": "no_cost_increase",
        "training_boundary": "not_authorized",
    }
    signoff["next_step_after_generation"] = (
        "Human reviewer fills reviewer fields, decision, evidence_reviewed, findings, "
        "and acknowledgements, then runs the Phase 130 validator with --require-complete. "
        "This sign-off records local evidence review only and does not resume service "
        "operation, AWS runtime, provider calls, training, or model promotion."
    )

    validation = validate_documentops_phase129_validated_closure_receipt_summary_handoff_signoff(signoff)
    if validation.get("ok") is not True:
        errors = "; ".join(validation.get("errors") or ["pending sign-off validation failed"])
        raise ValueError(f"generated pending sign-off is invalid: {errors}")
    signoff["generation_context"]["generated_record_validation"] = validation
    return signoff


def write_pending_signoff(signoff: dict[str, Any], *, output_path: Path, overwrite: bool = False) -> Path:
    resolved_output = output_path.expanduser().resolve()
    resolved_output.parent.mkdir(parents=True, exist_ok=True)
    if resolved_output.exists() and not overwrite:
        raise FileExistsError(f"output already exists: {resolved_output}")
    tmp = resolved_output.with_name(f"{resolved_output.name}.tmp.{uuid4().hex}")
    with tmp.open("w", encoding="utf-8") as handle:
        handle.write(json.dumps(signoff, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, resolved_output)
    return resolved_output


def _default_output_path(signoff: dict[str, Any], output_dir: Path | None) -> Path:
    directory = output_dir.expanduser().resolve() if output_dir is not None else Path.cwd()
    return directory / f"{signoff['signoff_id']}_pending_signoff.json"


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create a pending DocumentOps Phase 130 validated handoff sign-off JSON record."
    )
    parser.add_argument("--template", type=Path, default=DEFAULT_TEMPLATE_PATH)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument(
        "--signoff-id",
        help=f"Optional deterministic id matching {SIGNOFF_ID_PREFIX}[A-Za-z0-9_-]{{8,96}}.",
    )
    parser.add_argument("--created-at", help="Optional ISO timestamp for deterministic generation.")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--json", action="store_true", help="Print generated sign-off JSON to stdout instead of writing.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(list(argv) if argv is not None else None)
    try:
        if not args.json and args.output is not None:
            resolved_output = args.output.expanduser().resolve()
            if resolved_output.exists() and not args.overwrite:
                raise FileExistsError(f"output already exists: {resolved_output}")
        signoff = build_pending_documentops_phase130_validated_closure_receipt_summary_handoff_signoff(
            template_path=args.template,
            signoff_id=args.signoff_id,
            created_at=args.created_at,
        )
        if args.json:
            print(json.dumps(signoff, ensure_ascii=False, indent=2, sort_keys=True))
        else:
            output_path = args.output.expanduser().resolve() if args.output else _default_output_path(signoff, args.output_dir)
            output_path = write_pending_signoff(signoff, output_path=output_path, overwrite=args.overwrite)
            print(
                json.dumps(
                    {
                        "ok": True,
                        "signoff_id": signoff["signoff_id"],
                        "created_at": signoff["created_at"],
                        "output_path": str(output_path),
                        "decision": signoff["decision"],
                        "completed": False,
                        "service_resume_authorized": signoff["signoff_boundary"]["service_resume_authorized"],
                        "training_execution_authorized": signoff["signoff_boundary"]["training_execution_authorized"],
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                )
            )
    except Exception as exc:  # pragma: no cover - defensive CLI error path
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, sort_keys=True), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
