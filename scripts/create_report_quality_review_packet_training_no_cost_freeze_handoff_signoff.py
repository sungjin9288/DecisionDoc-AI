#!/usr/bin/env python3
"""Create a pending human sign-off record for a no-cost freeze handoff."""
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
DEFAULT_TEMPLATE_PATH = (
    REPO_ROOT / "docs/specs/report_quality_learning/training_no_cost_freeze_handoff_signoff_template.json"
)
HANDOFF_VALIDATOR_PATH = REPO_ROOT / "scripts/validate_report_quality_review_packet_training_no_cost_freeze_handoff.py"
SIGNOFF_VALIDATOR_PATH = (
    REPO_ROOT / "scripts/validate_report_quality_review_packet_training_no_cost_freeze_handoff_signoff.py"
)
SIGNOFF_ID_PATTERN = re.compile(r"rqp_training_no_cost_freeze_handoff_signoff_[A-Za-z0-9_-]{8,96}")
BOUNDARY_FALSE_KEYS = (
    "actual_operation_resume_approved",
    "service_operation_authorized",
    "server_file_written",
    "persisted_learning_artifact",
    "aws_deploy_authorized",
    "aws_resource_creation_authorized",
    "aws_runtime_authorized",
    "aws_cost_increase_authorized",
    "scheduled_job_authorized",
    "cloudwatch_polling_authorized",
    "external_dataset_upload_authorized",
    "provider_fine_tune_api_call_authorized",
    "provider_job_creation_authorized",
    "provider_job_polling_authorized",
    "training_execution_authorized",
    "model_promotion_authorized",
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
    "validate_report_quality_review_packet_training_no_cost_freeze_handoff",
)
_SIGNOFF_VALIDATOR = _load_module(
    SIGNOFF_VALIDATOR_PATH,
    "validate_report_quality_review_packet_training_no_cost_freeze_handoff_signoff",
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


def _safe_signoff_id(value: str | None) -> str:
    signoff_id = (
        value.strip()
        if isinstance(value, str) and value.strip()
        else f"rqp_training_no_cost_freeze_handoff_signoff_{uuid4().hex}"
    )
    if not SIGNOFF_ID_PATTERN.fullmatch(signoff_id):
        raise ValueError("signoff id must match rqp_training_no_cost_freeze_handoff_signoff_[A-Za-z0-9_-]{8,96}")
    return signoff_id


def _default_output_path(handoff_manifest_path: Path) -> Path:
    name = handoff_manifest_path.name
    if name.endswith("-training-no-cost-freeze-handoff-manifest.json"):
        base = name.removesuffix("-training-no-cost-freeze-handoff-manifest.json")
    else:
        base = handoff_manifest_path.stem
    return handoff_manifest_path.with_name(f"{base}-training-no-cost-freeze-handoff-signoff.json")


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
    for key in BOUNDARY_FALSE_KEYS:
        boundary[key] = False
    signoff["signoff_boundary"] = boundary


def _append_unique_path(paths: list[str], value: Any) -> None:
    if not isinstance(value, str) or not value.strip():
        return
    path = str(Path(value).expanduser().resolve())
    if path not in paths:
        paths.append(path)


def _evidence_to_review(handoff_manifest_path: Path, handoff_manifest: dict[str, Any]) -> list[str]:
    paths: list[str] = []
    _append_unique_path(paths, str(handoff_manifest_path))
    _append_unique_path(paths, handoff_manifest.get("handoff_markdown_path"))
    _append_unique_path(paths, handoff_manifest.get("freeze_summary_path"))
    for _, record in sorted(_as_dict(handoff_manifest.get("source_files")).items()):
        _append_unique_path(paths, _as_dict(record).get("path"))
    return paths


def build_pending_training_no_cost_freeze_handoff_signoff(
    *,
    handoff_manifest_path: Path,
    template_path: Path = DEFAULT_TEMPLATE_PATH,
    signoff_id: str | None = None,
    created_at: str | None = None,
    require_ready: bool = True,
) -> dict[str, Any]:
    resolved_handoff_manifest = handoff_manifest_path.expanduser().resolve()
    resolved_template = template_path.expanduser().resolve()
    handoff_validation = _HANDOFF_VALIDATOR.validate_training_no_cost_freeze_handoff(
        resolved_handoff_manifest,
        require_ready=require_ready,
    )
    if require_ready and handoff_validation.get("ok") is not True:
        errors = "; ".join(handoff_validation.get("errors") or ["no-cost freeze handoff validation failed"])
        raise ValueError(f"no-cost freeze handoff is not ready for sign-off generation: {errors}")

    template = _load_json(resolved_template)
    handoff_manifest = _load_json(resolved_handoff_manifest)
    signoff = dict(template)
    _reset_pending_fields(signoff)
    evidence_to_review = _evidence_to_review(resolved_handoff_manifest, handoff_manifest)

    signoff.update(
        {
            "signoff_id": _safe_signoff_id(signoff_id),
            "created_at": created_at or _now_iso(),
            "handoff_manifest_path": str(resolved_handoff_manifest),
            "handoff_manifest_sha256": _sha256(resolved_handoff_manifest),
            "generation_context": {
                "report_type": "report_quality_training_no_cost_freeze_handoff_pending_signoff_generation",
                "generated_from_template": str(resolved_template),
                "handoff_validation": handoff_validation,
                "handoff_readiness": _as_dict(handoff_manifest.get("readiness")),
                "handoff_counts": _as_dict(handoff_manifest.get("counts")),
                "evidence_to_review": evidence_to_review,
            },
            "generation_boundary": {
                "actual_operation_resume_approved": False,
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
            "next_step_after_generation": (
                "Human reviewer fills reviewer fields, decision, evidence_reviewed, findings, "
                "and acknowledgements, then runs "
                "validate_report_quality_review_packet_training_no_cost_freeze_handoff_signoff.py "
                "--require-complete. This sign-off records freeze handoff review only and does not resume "
                "service operation, AWS runtime, provider calls, training, or model promotion."
            ),
        }
    )
    return signoff


def write_pending_signoff(signoff: dict[str, Any], *, output_path: Path, overwrite: bool = False) -> Path:
    resolved_output = output_path.expanduser().resolve()
    resolved_output.parent.mkdir(parents=True, exist_ok=True)
    if resolved_output.exists() and not overwrite:
        raise FileExistsError(f"output already exists: {resolved_output}")
    tmp = resolved_output.with_name(f"{resolved_output.name}.tmp")
    tmp.write_text(json.dumps(signoff, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(resolved_output)
    return resolved_output


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Create a pending no-cost freeze handoff sign-off JSON record.")
    parser.add_argument("handoff_manifest", type=Path, help="Path to *-training-no-cost-freeze-handoff-manifest.json.")
    parser.add_argument("--template", type=Path, default=DEFAULT_TEMPLATE_PATH)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument(
        "--signoff-id",
        help="Optional deterministic id matching rqp_training_no_cost_freeze_handoff_signoff_[A-Za-z0-9_-]{8,96}.",
    )
    parser.add_argument("--created-at", help="Optional ISO timestamp for deterministic generation.")
    parser.add_argument("--allow-not-ready", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--json", action="store_true", help="Print generated sign-off JSON to stdout.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(list(argv) if argv is not None else None)
    try:
        resolved_handoff = args.handoff_manifest.expanduser().resolve()
        signoff = build_pending_training_no_cost_freeze_handoff_signoff(
            handoff_manifest_path=resolved_handoff,
            template_path=args.template,
            signoff_id=args.signoff_id,
            created_at=args.created_at,
            require_ready=not args.allow_not_ready,
        )
        output_path = (
            args.output.expanduser().resolve()
            if args.output is not None
            else _default_output_path(resolved_handoff)
        )
        written_path = write_pending_signoff(signoff, output_path=output_path, overwrite=args.overwrite)
        validation = _SIGNOFF_VALIDATOR.validate_training_no_cost_freeze_handoff_signoff(
            signoff,
            require_complete=False,
        )
    except Exception as exc:
        result = {"ok": False, "error": str(exc)}
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        else:
            print("FAIL report quality training no-cost freeze handoff pending signoff generation failed")
            print(f"ERROR {exc}")
        return 1

    if args.json:
        print(json.dumps(signoff, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print("Report quality training no-cost freeze handoff pending signoff: PASS")
        print(f"signoff_id={signoff['signoff_id']}")
        print(f"output_path={written_path}")
        print(f"pending_validation_ok={str(validation['ok']).lower()}")
        print("aws_cost_boundary=no_cost_increase")
        print("training_boundary=not_authorized")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
