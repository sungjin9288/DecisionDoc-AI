#!/usr/bin/env python3
"""Create a local archive closure from a completed no-cost freeze handoff sign-off."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
from typing import Any, Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
SIGNOFF_VALIDATOR_PATH = (
    REPO_ROOT / "scripts/validate_report_quality_review_packet_training_no_cost_freeze_handoff_signoff.py"
)
ARCHIVE_VALIDATOR_PATH = REPO_ROOT / "scripts/validate_report_quality_review_packet_training_no_cost_archive_closure.py"
EXPECTED_SCHEMA = "decisiondoc_report_quality_training_no_cost_archive_closure.v1"


def _load_module(path: Path, module_name: str):
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed to load {module_name}: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_SIGNOFF_VALIDATOR = _load_module(
    SIGNOFF_VALIDATOR_PATH,
    "validate_report_quality_review_packet_training_no_cost_freeze_handoff_signoff",
)
_ARCHIVE_VALIDATOR = _load_module(
    ARCHIVE_VALIDATOR_PATH,
    "validate_report_quality_review_packet_training_no_cost_archive_closure",
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


def _write_text_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


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


def _default_output_path(signoff_path: Path, suffix: str) -> Path:
    name = signoff_path.name
    if name.endswith("-training-no-cost-freeze-handoff-signoff.json"):
        base = name.removesuffix("-training-no-cost-freeze-handoff-signoff.json")
    else:
        base = signoff_path.stem
    return signoff_path.with_name(f"{base}{suffix}")


def _add_source_file(source_files: dict[str, dict[str, Any]], name: str, path_value: Any) -> None:
    record = _file_record(path_value)
    if record["path"] and all(existing.get("path") != record["path"] for existing in source_files.values()):
        source_files[name] = record


def create_training_no_cost_archive_closure(
    *,
    signoff_path: Path,
    output_manifest: Path | None = None,
    output_markdown: Path | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    resolved_signoff = signoff_path.expanduser().resolve()
    signoff = _load_json(resolved_signoff)
    signoff_validation = _SIGNOFF_VALIDATOR.validate_training_no_cost_freeze_handoff_signoff(
        signoff,
        require_complete=True,
    )
    if signoff_validation.get("ok") is not True:
        errors = "; ".join(signoff_validation.get("errors") or ["sign-off validation failed"])
        raise ValueError(f"no-cost freeze handoff sign-off is not complete: {errors}")

    handoff_path = Path(str(signoff["handoff_manifest_path"])).expanduser().resolve()
    handoff = _load_json(handoff_path)
    output_manifest = (
        output_manifest.expanduser().resolve()
        if output_manifest is not None
        else _default_output_path(resolved_signoff, "-training-no-cost-archive-closure-manifest.json")
    )
    output_markdown = (
        output_markdown.expanduser().resolve()
        if output_markdown is not None
        else _default_output_path(resolved_signoff, "-training-no-cost-archive-closure.md")
    )

    source_files: dict[str, dict[str, Any]] = {
        "freeze_handoff_signoff": _file_record(str(resolved_signoff)),
        "freeze_handoff_manifest": _file_record(str(handoff_path)),
    }
    _add_source_file(source_files, "freeze_handoff_markdown", handoff.get("handoff_markdown_path"))
    _add_source_file(source_files, "freeze_summary_json", handoff.get("freeze_summary_path"))
    for name, record in sorted(_as_dict(handoff.get("source_files")).items()):
        _add_source_file(source_files, name, _as_dict(record).get("path"))
    missing_files = sorted(name for name, record in source_files.items() if record.get("exists") is not True)
    handoff_counts = _as_dict(handoff.get("counts"))

    closure = {
        "report_type": "report_quality_training_no_cost_archive_closure",
        "schema_version": EXPECTED_SCHEMA,
        "generated_at": generated_at or _now_iso(),
        "archive_manifest_path": str(output_manifest),
        "archive_markdown_path": str(output_markdown),
        "signoff_path": str(resolved_signoff),
        "signoff_sha256": _sha256(resolved_signoff),
        "signoff_validation": signoff_validation,
        "handoff_manifest_path": str(handoff_path),
        "handoff_manifest_sha256": _sha256(handoff_path),
        "closure_state": {
            "ok": True,
            "status": "archived_no_cost_hold",
            "archive_only": True,
            "freeze_handoff_signoff_completed": True,
            "operation_resume_approved": False,
            "service_operation_allowed": False,
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
        "counts": {
            "freeze_count": handoff_counts.get("freeze_count", 0),
            "valid_freeze_count": handoff_counts.get("valid_freeze_count", 0),
            "no_cost_hold_count": handoff_counts.get("no_cost_hold_count", 0),
            "source_file_count": len(source_files),
            "missing_file_count": len(missing_files),
        },
        "source_files": source_files,
        "operator_actions": [
            "Archive this closure with the local no-cost freeze handoff and sign-off evidence.",
            "Do not deploy AWS resources, enable runtime services, scheduled jobs, or CloudWatch polling from this closure.",
            "Do not call provider APIs, upload datasets, create provider jobs, start training, or promote models from this closure.",
            "Resume only after a separate human approval, AWS budget review, provider approval, offline eval plan, and rollback plan are complete.",
        ],
        "closure_boundary": {
            "reads_local_signoff": True,
            "writes_local_archive_files": True,
            "server_file_written": False,
            "persisted_learning_artifact": False,
            "operation_resume_approved": False,
            "service_operation_allowed": False,
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
    }
    _write_text_atomic(output_manifest, json.dumps(closure, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    _write_text_atomic(output_markdown, render_training_no_cost_archive_closure_markdown(closure))
    return closure


def render_training_no_cost_archive_closure_markdown(closure: dict[str, Any]) -> str:
    state = _as_dict(closure.get("closure_state"))
    counts = _as_dict(closure.get("counts"))
    source_files = _as_dict(closure.get("source_files"))
    rows = "\n".join(
        "| {name} | {exists} | `{path}` |".format(
            name=name,
            exists="yes" if _as_dict(record).get("exists") else "no",
            path=_as_dict(record).get("path", ""),
        )
        for name, record in source_files.items()
    )
    if not rows:
        rows = "| - | - | - |"
    return f"""# Report Quality Training No-Cost Archive Closure

- generated_at: `{closure.get('generated_at', '-')}`
- status: `{state.get('status', '-')}`
- archive_ready: `{str(state.get('ok') is True).lower()}`
- archive_only: `true`
- freeze_handoff_signoff_completed: `true`
- freeze_count: `{counts.get('freeze_count', 0)}`
- valid_freeze_count: `{counts.get('valid_freeze_count', 0)}`
- no_cost_hold_count: `{counts.get('no_cost_hold_count', 0)}`
- operation_resume_approved: `false`
- service_operation_allowed: `false`
- aws_cost_increase_allowed: `false`
- provider_fine_tune_api_called: `false`
- external_dataset_upload_started: `false`
- training_execution_started: `false`
- model_promotion_started: `false`

## Source Files

| file | exists | path |
| --- | --- | --- |
{rows}

## Operator Actions

{chr(10).join(f"- {item}" for item in closure.get('operator_actions', []))}

## Closure Boundary

- server_file_written: `false`
- persisted_learning_artifact: `false`
- operation_resume_approved: `false`
- service_operation_allowed: `false`
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
    parser = argparse.ArgumentParser(description="Create a local no-cost archive closure manifest.")
    parser.add_argument("signoff", type=Path, help="Path to *-training-no-cost-freeze-handoff-signoff.json.")
    parser.add_argument("--output-manifest", type=Path, default=None)
    parser.add_argument("--output-markdown", type=Path, default=None)
    parser.add_argument("--generated-at", help="Optional ISO timestamp for deterministic output.")
    parser.add_argument("--json", action="store_true", help="Print generated archive closure manifest JSON to stdout.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(list(argv) if argv is not None else None)
    try:
        closure = create_training_no_cost_archive_closure(
            signoff_path=args.signoff,
            output_manifest=args.output_manifest,
            output_markdown=args.output_markdown,
            generated_at=args.generated_at,
        )
        validation = _ARCHIVE_VALIDATOR.validate_training_no_cost_archive_closure(
            Path(closure["archive_manifest_path"]),
        )
    except Exception as exc:
        result = {"ok": False, "error": str(exc)}
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        else:
            print("FAIL report quality training no-cost archive closure generation failed")
            print(f"ERROR {exc}")
        return 1

    if args.json:
        print(json.dumps(closure, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print("Report quality training no-cost archive closure: PASS")
        print(f"archive_ready={str(closure['closure_state']['ok']).lower()}")
        print("aws_cost_boundary=no_cost_increase")
        print("training_boundary=not_authorized")
    return 0 if validation["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
