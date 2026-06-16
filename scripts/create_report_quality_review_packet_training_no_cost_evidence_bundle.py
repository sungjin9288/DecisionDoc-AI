#!/usr/bin/env python3
"""Create a local no-cost evidence bundle from archive closure summaries."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
from typing import Any, Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
SUMMARY_SCRIPT_PATH = REPO_ROOT / "scripts/summarize_report_quality_review_packet_training_no_cost_archive_closures.py"
BUNDLE_VALIDATOR_PATH = REPO_ROOT / "scripts/validate_report_quality_review_packet_training_no_cost_evidence_bundle.py"
EXPECTED_SCHEMA = "decisiondoc_report_quality_training_no_cost_evidence_bundle.v1"


def _load_module(path: Path, module_name: str):
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed to load {module_name}: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_SUMMARY_SCRIPT = _load_module(
    SUMMARY_SCRIPT_PATH,
    "summarize_report_quality_review_packet_training_no_cost_archive_closures",
)
_BUNDLE_VALIDATOR = _load_module(
    BUNDLE_VALIDATOR_PATH,
    "validate_report_quality_review_packet_training_no_cost_evidence_bundle",
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
    if name.endswith("-training-no-cost-archive-closure-summary.json"):
        base = name.removesuffix("-training-no-cost-archive-closure-summary.json")
    else:
        base = summary_path.stem
    return summary_path.with_name(f"{base}{suffix}")


def _add_source_file(source_files: dict[str, dict[str, Any]], name: str, path_value: Any) -> None:
    record = _file_record(path_value)
    if record["path"] and all(existing.get("path") != record["path"] for existing in source_files.values()):
        source_files[name] = record


def _closure_paths(summary: dict[str, Any]) -> list[Path]:
    return [
        Path(str(closure.get("path"))).expanduser().resolve()
        for closure in _as_list(summary.get("closures"))
        if str(_as_dict(closure).get("path", "")).strip()
    ]


def _collect_source_files(summary_path: Path, closure_paths: Sequence[Path]) -> dict[str, dict[str, Any]]:
    source_files: dict[str, dict[str, Any]] = {
        "archive_closure_summary_json": _file_record(str(summary_path)),
    }
    for index, closure_path in enumerate(closure_paths, start=1):
        closure = _load_json(closure_path)
        _add_source_file(source_files, f"archive_closure_manifest_{index}", str(closure_path))
        _add_source_file(source_files, f"archive_closure_markdown_{index}", closure.get("archive_markdown_path"))
        _add_source_file(source_files, f"archive_closure_signoff_{index}", closure.get("signoff_path"))
        _add_source_file(source_files, f"archive_closure_handoff_{index}", closure.get("handoff_manifest_path"))
        for name, record in sorted(_as_dict(closure.get("source_files")).items()):
            _add_source_file(source_files, f"{name}_{index}", _as_dict(record).get("path"))
    return source_files


def create_training_no_cost_evidence_bundle(
    *,
    archive_closure_summary_path: Path,
    output_manifest: Path | None = None,
    output_markdown: Path | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    resolved_summary = archive_closure_summary_path.expanduser().resolve()
    summary = _load_json(resolved_summary)
    closure_paths = _closure_paths(summary)
    rebuilt_summary = _SUMMARY_SCRIPT.build_training_no_cost_archive_closure_summary(closure_paths)
    if rebuilt_summary.get("ok") is not True:
        blockers = ", ".join(_as_list(_as_dict(rebuilt_summary.get("readiness")).get("blocker_reasons")))
        raise ValueError(f"archive closure summary is not ready for bundle: {blockers or 'validation failed'}")
    if summary.get("ok") is not True:
        raise ValueError("archive closure summary must have ok=true before bundle generation")

    output_manifest = (
        output_manifest.expanduser().resolve()
        if output_manifest is not None
        else _default_output_path(resolved_summary, "-training-no-cost-evidence-bundle-manifest.json")
    )
    output_markdown = (
        output_markdown.expanduser().resolve()
        if output_markdown is not None
        else _default_output_path(resolved_summary, "-training-no-cost-evidence-bundle.md")
    )
    source_files = _collect_source_files(resolved_summary, closure_paths)
    missing_files = sorted(name for name, record in source_files.items() if record.get("exists") is not True)
    summary_counts = _as_dict(summary.get("counts"))

    bundle = {
        "report_type": "report_quality_training_no_cost_evidence_bundle",
        "schema_version": EXPECTED_SCHEMA,
        "generated_at": generated_at or _now_iso(),
        "bundle_manifest_path": str(output_manifest),
        "bundle_markdown_path": str(output_markdown),
        "archive_closure_summary_path": str(resolved_summary),
        "archive_closure_summary_sha256": _sha256(resolved_summary),
        "archive_closure_summary_validation": rebuilt_summary,
        "bundle_state": {
            "ok": True,
            "status": "no_cost_evidence_bundle_ready",
            "bundle_only": True,
            "archive_summary_ok": True,
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
            "archive_closure_count": summary_counts.get("archive_closure_count", 0),
            "valid_archive_closure_count": summary_counts.get("valid_archive_closure_count", 0),
            "archived_no_cost_hold_count": summary_counts.get("archived_no_cost_hold_count", 0),
            "source_file_count": len(source_files),
            "missing_file_count": len(missing_files),
        },
        "source_files": source_files,
        "operator_actions": [
            "Archive this bundle with the local no-cost evidence before pausing the project.",
            "Do not deploy AWS resources, enable runtime services, scheduled jobs, or CloudWatch polling from this bundle.",
            "Do not call provider APIs, upload datasets, create provider jobs, start training, or promote models from this bundle.",
            "Resume only after a separate human approval, AWS budget review, provider approval, offline eval plan, and rollback plan are complete.",
        ],
        "bundle_boundary": {
            "reads_local_archive_summary": True,
            "writes_local_bundle_files": True,
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
    _write_text_atomic(output_manifest, json.dumps(bundle, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    _write_text_atomic(output_markdown, render_training_no_cost_evidence_bundle_markdown(bundle))
    return bundle


def render_training_no_cost_evidence_bundle_markdown(bundle: dict[str, Any]) -> str:
    state = _as_dict(bundle.get("bundle_state"))
    counts = _as_dict(bundle.get("counts"))
    source_files = _as_dict(bundle.get("source_files"))
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
    return f"""# Report Quality Training No-Cost Evidence Bundle

- generated_at: `{bundle.get('generated_at', '-')}`
- status: `{state.get('status', '-')}`
- bundle_ready: `{str(state.get('ok') is True).lower()}`
- bundle_only: `true`
- archive_closure_count: `{counts.get('archive_closure_count', 0)}`
- valid_archive_closure_count: `{counts.get('valid_archive_closure_count', 0)}`
- archived_no_cost_hold_count: `{counts.get('archived_no_cost_hold_count', 0)}`
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

{chr(10).join(f"- {item}" for item in bundle.get('operator_actions', []))}

## Bundle Boundary

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
    parser = argparse.ArgumentParser(description="Create a local no-cost evidence bundle manifest.")
    parser.add_argument("archive_closure_summary", type=Path, help="Path to *-training-no-cost-archive-closure-summary.json.")
    parser.add_argument("--output-manifest", type=Path, default=None)
    parser.add_argument("--output-markdown", type=Path, default=None)
    parser.add_argument("--generated-at", help="Optional ISO timestamp for deterministic output.")
    parser.add_argument("--json", action="store_true", help="Print generated evidence bundle manifest JSON to stdout.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(list(argv) if argv is not None else None)
    try:
        bundle = create_training_no_cost_evidence_bundle(
            archive_closure_summary_path=args.archive_closure_summary,
            output_manifest=args.output_manifest,
            output_markdown=args.output_markdown,
            generated_at=args.generated_at,
        )
        validation = _BUNDLE_VALIDATOR.validate_training_no_cost_evidence_bundle(
            Path(bundle["bundle_manifest_path"]),
        )
    except Exception as exc:
        result = {"ok": False, "error": str(exc)}
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        else:
            print("FAIL report quality training no-cost evidence bundle generation failed")
            print(f"ERROR {exc}")
        return 1

    if args.json:
        print(json.dumps(bundle, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print("Report quality training no-cost evidence bundle: PASS")
        print(f"bundle_ready={str(bundle['bundle_state']['ok']).lower()}")
        print("aws_cost_boundary=no_cost_increase")
        print("training_boundary=not_authorized")
    return 0 if validation["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
