#!/usr/bin/env python3
"""Create a local handoff from report quality training no-cost freeze summaries."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
from typing import Any, Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
SUMMARY_SCRIPT_PATH = REPO_ROOT / "scripts/summarize_report_quality_review_packet_training_no_cost_freezes.py"
HANDOFF_VALIDATOR_PATH = REPO_ROOT / "scripts/validate_report_quality_review_packet_training_no_cost_freeze_handoff.py"
EXPECTED_SCHEMA = "decisiondoc_report_quality_training_no_cost_freeze_handoff.v1"


def _load_module(path: Path, module_name: str):
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed to load {module_name}: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_SUMMARY_SCRIPT = _load_module(
    SUMMARY_SCRIPT_PATH,
    "summarize_report_quality_review_packet_training_no_cost_freezes",
)
_HANDOFF_VALIDATOR = _load_module(
    HANDOFF_VALIDATOR_PATH,
    "validate_report_quality_review_packet_training_no_cost_freeze_handoff",
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


def _default_output_path(summary_path: Path, suffix: str) -> Path:
    name = summary_path.name
    if name.endswith("-training-no-cost-freeze-summary.json"):
        base = name.removesuffix("-training-no-cost-freeze-summary.json")
    else:
        base = summary_path.stem
    return summary_path.with_name(f"{base}{suffix}")


def _summary_freeze_paths(summary: dict[str, Any]) -> list[Path]:
    return [
        Path(str(freeze.get("path"))).expanduser().resolve()
        for freeze in _as_list(summary.get("freezes"))
        if str(_as_dict(freeze).get("path", "")).strip()
    ]


def create_training_no_cost_freeze_handoff(
    *,
    freeze_summary_path: Path,
    output_manifest: Path | None = None,
    output_markdown: Path | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    resolved_summary = freeze_summary_path.expanduser().resolve()
    summary = _load_json(resolved_summary)
    freeze_paths = _summary_freeze_paths(summary)
    summary_validation = _SUMMARY_SCRIPT.build_training_no_cost_freeze_summary(freeze_paths)
    if summary_validation.get("ok") is not True:
        blockers = ", ".join(_as_list(_as_dict(summary_validation.get("readiness")).get("blocker_reasons")))
        raise ValueError(f"no-cost freeze summary is not ready for handoff: {blockers or 'validation failed'}")
    if summary.get("ok") is not True:
        raise ValueError("no-cost freeze summary must have ok=true before handoff")

    output_manifest = (
        output_manifest.expanduser().resolve()
        if output_manifest is not None
        else _default_output_path(resolved_summary, "-training-no-cost-freeze-handoff-manifest.json")
    )
    output_markdown = (
        output_markdown.expanduser().resolve()
        if output_markdown is not None
        else _default_output_path(resolved_summary, "-training-no-cost-freeze-handoff.md")
    )

    source_files = {
        "freeze_summary_json": _file_record(str(resolved_summary)),
    }
    for index, freeze_path in enumerate(freeze_paths, start=1):
        source_files[f"freeze_manifest_{index}"] = _file_record(str(freeze_path))
    missing_files = sorted(name for name, record in source_files.items() if record.get("exists") is not True)
    counts = _as_dict(summary.get("counts"))
    handoff = {
        "report_type": "report_quality_training_no_cost_freeze_handoff",
        "schema_version": EXPECTED_SCHEMA,
        "generated_at": generated_at or _now_iso(),
        "handoff_manifest_path": str(output_manifest),
        "handoff_markdown_path": str(output_markdown),
        "freeze_summary_path": str(resolved_summary),
        "freeze_summary_sha256": _sha256(resolved_summary),
        "freeze_summary_validation": summary_validation,
        "readiness": {
            "ok": True,
            "status": "no_cost_freeze_handoff_ready",
            "freeze_only": True,
            "aws_cost_increase_allowed": False,
            "service_operation_allowed": False,
            "external_dataset_upload_authorized": False,
            "provider_fine_tune_api_call_authorized": False,
            "provider_job_creation_authorized": False,
            "training_execution_authorized": False,
            "model_promotion_authorized": False,
        },
        "counts": {
            "freeze_count": counts.get("freeze_count", 0),
            "valid_freeze_count": counts.get("valid_freeze_count", 0),
            "no_cost_hold_count": counts.get("no_cost_hold_count", 0),
            "source_file_count": len(source_files),
            "missing_file_count": len(missing_files),
        },
        "source_files": source_files,
        "operator_actions": [
            "Archive this handoff with the local no-cost freeze evidence before pausing the project.",
            "Do not deploy AWS resources, enable runtime services, scheduled jobs, or CloudWatch polling from this handoff.",
            "Do not call provider APIs, upload datasets, create provider jobs, start training, or promote models from this handoff.",
            "Resume only after a separate human approval, AWS budget review, provider approval, offline eval plan, and rollback plan are complete.",
        ],
        "handoff_boundary": {
            "reads_local_freeze_summary": True,
            "writes_local_handoff_files": True,
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
    }
    _write_text_atomic(output_manifest, json.dumps(handoff, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    _write_text_atomic(output_markdown, render_training_no_cost_freeze_handoff_markdown(handoff))
    return handoff


def render_training_no_cost_freeze_handoff_markdown(handoff: dict[str, Any]) -> str:
    readiness = _as_dict(handoff.get("readiness"))
    counts = _as_dict(handoff.get("counts"))
    source_files = _as_dict(handoff.get("source_files"))
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
    return f"""# Report Quality Training No-Cost Freeze Handoff

- generated_at: `{handoff.get('generated_at', '-')}`
- status: `{readiness.get('status', '-')}`
- handoff_ready: `{str(readiness.get('ok') is True).lower()}`
- freeze_only: `true`
- freeze_count: `{counts.get('freeze_count', 0)}`
- valid_freeze_count: `{counts.get('valid_freeze_count', 0)}`
- no_cost_hold_count: `{counts.get('no_cost_hold_count', 0)}`
- aws_cost_increase_allowed: `false`
- service_operation_allowed: `false`
- provider_fine_tune_api_call_authorized: `false`
- external_dataset_upload_authorized: `false`
- training_execution_authorized: `false`
- model_promotion_authorized: `false`

## Source Files

| file | exists | path |
| --- | --- | --- |
{rows}

## Operator Actions

{chr(10).join(f"- {item}" for item in handoff.get('operator_actions', []))}

## Handoff Boundary

- server_file_written: `false`
- persisted_learning_artifact: `false`
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
    parser = argparse.ArgumentParser(description="Create a local no-cost freeze handoff manifest.")
    parser.add_argument("freeze_summary", type=Path, help="Path to *-training-no-cost-freeze-summary.json.")
    parser.add_argument("--output-manifest", type=Path, default=None)
    parser.add_argument("--output-markdown", type=Path, default=None)
    parser.add_argument("--generated-at", help="Optional ISO timestamp for deterministic output.")
    parser.add_argument("--json", action="store_true", help="Print generated handoff manifest JSON to stdout.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(list(argv) if argv is not None else None)
    try:
        handoff = create_training_no_cost_freeze_handoff(
            freeze_summary_path=args.freeze_summary,
            output_manifest=args.output_manifest,
            output_markdown=args.output_markdown,
            generated_at=args.generated_at,
        )
        validation = _HANDOFF_VALIDATOR.validate_training_no_cost_freeze_handoff(
            Path(handoff["handoff_manifest_path"]),
        )
    except Exception as exc:
        result = {"ok": False, "error": str(exc)}
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        else:
            print("FAIL report quality training no-cost freeze handoff generation failed")
            print(f"ERROR {exc}")
        return 1

    if args.json:
        print(json.dumps(handoff, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print("Report quality training no-cost freeze handoff: PASS")
        print(f"handoff_ready={str(handoff['readiness']['ok']).lower()}")
        print("aws_cost_boundary=no_cost_increase")
        print("training_boundary=not_authorized")
    return 0 if validation["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
