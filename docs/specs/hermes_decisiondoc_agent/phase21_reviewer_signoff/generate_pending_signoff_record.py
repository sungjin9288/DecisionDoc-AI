#!/usr/bin/env python3
"""Generate a pending DocumentOps reviewer sign-off record from the template.

This generator creates a local fillable JSON record only. It does not record
actual reviewer approval, start training, upload datasets, call provider APIs,
create provider jobs, or promote models.
"""
from __future__ import annotations

import argparse
import copy
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4


DEFAULT_TEMPLATE_PATH = Path(__file__).with_name("signoff_record_template.json")
PROTECTED_FALSE_BOUNDARY_KEYS = {
    "training_execution_authorized",
    "external_dataset_upload_authorized",
    "provider_fine_tune_api_call_authorized",
    "provider_job_creation_authorized",
    "provider_job_polling_authorized",
    "model_candidate_emission_authorized",
    "model_promotion_authorized",
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _safe_record_id(value: str) -> str:
    record_id = value.strip()
    if not re.fullmatch(r"dsr_[A-Za-z0-9_-]{8,80}", record_id):
        raise ValueError("record id must match dsr_[A-Za-z0-9_-]{8,80}")
    return record_id


def _load_template(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError("sign-off template must be a JSON object")
    return data


def _reset_reviewer_records(record: dict[str, Any]) -> None:
    reviewers = record.get("required_reviewers")
    if not isinstance(reviewers, list):
        raise ValueError("template required_reviewers must be a list")
    for reviewer in reviewers:
        if not isinstance(reviewer, dict):
            raise ValueError("template reviewer entries must be objects")
        reviewer["reviewer_name"] = ""
        reviewer["reviewer_title_or_team"] = ""
        reviewer["reviewed_at"] = ""
        reviewer["decision"] = "pending"
        reviewer["notes"] = ""
        acknowledgements = reviewer.get("required_acknowledgements")
        if not isinstance(acknowledgements, dict):
            raise ValueError("template required_acknowledgements must be objects")
        for key in acknowledgements:
            acknowledgements[key] = False


def _reset_completion_rule(record: dict[str, Any]) -> None:
    completion_rule = record.get("completion_rule")
    if not isinstance(completion_rule, dict):
        raise ValueError("template completion_rule must be an object")
    for key in completion_rule:
        completion_rule[key] = False


def _enforce_pending_boundary(record: dict[str, Any]) -> None:
    boundary = record.get("signoff_boundary")
    if not isinstance(boundary, dict):
        raise ValueError("template signoff_boundary must be an object")
    boundary["actual_reviewer_approval_recorded"] = False
    for key in PROTECTED_FALSE_BOUNDARY_KEYS:
        boundary[key] = False


def build_pending_record(
    template: dict[str, Any],
    *,
    record_id: str | None = None,
    created_at: str | None = None,
    template_path: Path = DEFAULT_TEMPLATE_PATH,
) -> dict[str, Any]:
    signoff_record_id = _safe_record_id(record_id) if record_id else f"dsr_{uuid4().hex}"
    timestamp = created_at or _utc_now()

    record = copy.deepcopy(template)
    record["report_type"] = "document_ops_phase23_pending_manual_reviewer_signoff_record"
    record["status"] = "pending_manual_signoff"
    record["signoff_record_id"] = signoff_record_id
    record["created_at"] = timestamp
    record["generated_from_template"] = {
        "template_path": str(template_path),
        "template_report_type": template.get("report_type"),
        "template_created_at": template.get("created_at"),
    }
    record["generation_boundary"] = {
        "actual_reviewer_approval_recorded": False,
        "training_execution_started": False,
        "external_dataset_uploaded": False,
        "provider_fine_tune_api_called": False,
        "provider_job_created": False,
        "model_promoted": False,
    }
    record["next_step_after_generation"] = (
        "Human reviewers fill reviewer fields and acknowledgements, then run "
        "validate_signoff_record.py before treating the record as completed governance evidence."
    )

    _reset_reviewer_records(record)
    _reset_completion_rule(record)
    _enforce_pending_boundary(record)
    return record


def write_pending_record(record: dict[str, Any], *, output: Path | None, output_dir: Path | None, overwrite: bool) -> Path:
    if output is None:
        directory = output_dir or Path.cwd()
        output = directory / f"{record['signoff_record_id']}_pending_signoff.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists() and not overwrite:
        raise FileExistsError(f"output already exists: {output}")
    output.write_text(json.dumps(record, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return output


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate a pending DocumentOps reviewer sign-off JSON record.")
    parser.add_argument("--template", type=Path, default=DEFAULT_TEMPLATE_PATH, help="Path to signoff_record_template.json.")
    parser.add_argument("--output", type=Path, help="Exact output JSON path.")
    parser.add_argument("--output-dir", type=Path, help="Directory for <record_id>_pending_signoff.json.")
    parser.add_argument("--record-id", help="Optional deterministic record id. Must match dsr_[A-Za-z0-9_-]{8,80}.")
    parser.add_argument("--created-at", help="Optional ISO timestamp for deterministic generation.")
    parser.add_argument("--overwrite", action="store_true", help="Allow overwriting the output path.")
    args = parser.parse_args(argv)

    try:
        template = _load_template(args.template)
        record = build_pending_record(
            template,
            record_id=args.record_id,
            created_at=args.created_at,
            template_path=args.template,
        )
        output_path = write_pending_record(
            record,
            output=args.output,
            output_dir=args.output_dir,
            overwrite=args.overwrite,
        )
    except Exception as exc:  # pragma: no cover - defensive CLI error path
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, sort_keys=True), file=sys.stderr)
        return 1

    print(
        json.dumps(
            {
                "ok": True,
                "record_id": record["signoff_record_id"],
                "created_at": record["created_at"],
                "output_path": str(output_path),
                "status": record["status"],
                "training_execution_authorized": record["signoff_boundary"]["training_execution_authorized"],
                "provider_fine_tune_api_call_authorized": record["signoff_boundary"][
                    "provider_fine_tune_api_call_authorized"
                ],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
