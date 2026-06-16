#!/usr/bin/env python3
"""Create a reviewer handoff index from a local review packet evidence pipeline."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
from typing import Any, Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
VALIDATOR_PATH = REPO_ROOT / "scripts/validate_report_quality_review_packet_evidence.py"


def _load_validator():
    spec = importlib.util.spec_from_file_location("validate_report_quality_review_packet_evidence", VALIDATOR_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed to load evidence validator: {VALIDATOR_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_EVIDENCE_VALIDATOR = _load_validator()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


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


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path}: JSON root must be an object")
    return payload


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _default_output_path(pipeline_manifest_path: Path, suffix: str) -> Path:
    name = pipeline_manifest_path.name
    if name.endswith("-evidence-pipeline-manifest.json"):
        base = name.removesuffix("-evidence-pipeline-manifest.json")
    else:
        base = pipeline_manifest_path.stem
    return pipeline_manifest_path.with_name(f"{base}{suffix}")


def _output_file_record(path_value: Any) -> dict[str, Any]:
    if not isinstance(path_value, str) or not path_value.strip():
        return {"path": "", "exists": False, "sha256": ""}
    path = Path(path_value).expanduser().resolve()
    return {
        "path": str(path),
        "exists": path.exists(),
        "sha256": _sha256(path) if path.exists() and path.is_file() else "",
    }


def create_review_packet_handoff(
    *,
    pipeline_manifest_path: Path,
    output_markdown: Path | None = None,
    output_manifest: Path | None = None,
    require_ready: bool = True,
) -> dict[str, Any]:
    resolved_pipeline_manifest = pipeline_manifest_path.expanduser().resolve()
    validation = _EVIDENCE_VALIDATOR.validate_review_packet_evidence_manifest(
        resolved_pipeline_manifest,
        require_ready=require_ready,
    )
    pipeline_manifest = _load_json(resolved_pipeline_manifest)
    output_markdown = (
        output_markdown.expanduser().resolve()
        if output_markdown is not None
        else _default_output_path(resolved_pipeline_manifest, "-handoff-index.md")
    )
    output_manifest = (
        output_manifest.expanduser().resolve()
        if output_manifest is not None
        else _default_output_path(resolved_pipeline_manifest, "-handoff-manifest.json")
    )

    outputs = _as_dict(pipeline_manifest.get("outputs"))
    output_files = {
        key: _output_file_record(value)
        for key, value in sorted(outputs.items())
    }
    readiness = _as_dict(pipeline_manifest.get("readiness"))
    counts = _as_dict(pipeline_manifest.get("counts"))
    handoff_manifest = {
        "report_type": "report_quality_review_packet_handoff",
        "schema_version": "decisiondoc_report_quality_review_packet_handoff.v1",
        "generated_at": _now_iso(),
        "pipeline_manifest_path": str(resolved_pipeline_manifest),
        "pipeline_manifest_sha256": _sha256(resolved_pipeline_manifest),
        "handoff_index_path": str(output_markdown),
        "handoff_manifest_path": str(output_manifest),
        "require_ready": require_ready,
        "validation": validation,
        "readiness": {
            "ok": validation.get("ok") is True and readiness.get("ok") is True,
            "status": readiness.get("status", "follow_up_required"),
            "blocker_reasons": list(readiness.get("blocker_reasons") or []),
            "training_execution_authorized": False,
            "external_dataset_upload_authorized": False,
            "provider_fine_tune_api_call_authorized": False,
            "provider_job_creation_authorized": False,
            "model_promotion_authorized": False,
        },
        "counts": {
            "packet_count": counts.get("packet_count", 0),
            "ready_packets": counts.get("ready_packets", 0),
            "exported_artifacts": counts.get("exported_artifacts", 0),
            "ready_artifacts": counts.get("ready_artifacts", 0),
        },
        "handoff_files": output_files,
        "reviewer_actions": [
            "Open the review packet summary and artifact batch summary.",
            "Confirm packet_count, ready_packets, exported_artifacts, and ready_artifacts match the planned sample count.",
            "Inspect reviewer, reviewed_at, score, scan, and blocker fields.",
            "Confirm every no-side-effect boundary flag remains false.",
            "Do not start provider fine-tune, dataset upload, training execution, provider jobs, or model promotion from this handoff.",
        ],
        "side_effect_boundary": {
            "reads_local_pipeline_manifest": True,
            "writes_local_handoff_files": True,
            "server_file_written": False,
            "persisted_learning_artifact": False,
            "external_dataset_upload_started": False,
            "provider_fine_tune_api_called": False,
            "provider_job_created": False,
            "training_execution_started": False,
            "model_promotion_started": False,
        },
    }
    _write_text_atomic(output_manifest, json.dumps(handoff_manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    _write_text_atomic(output_markdown, render_handoff_markdown(handoff_manifest))
    return handoff_manifest


def render_handoff_markdown(handoff_manifest: dict[str, Any]) -> str:
    readiness = _as_dict(handoff_manifest.get("readiness"))
    counts = _as_dict(handoff_manifest.get("counts"))
    validation = _as_dict(handoff_manifest.get("validation"))
    handoff_files = _as_dict(handoff_manifest.get("handoff_files"))
    file_rows = "\n".join(
        "| {name} | {exists} | `{path}` |".format(
            name=name,
            exists="yes" if _as_dict(record).get("exists") else "no",
            path=_as_dict(record).get("path", ""),
        )
        for name, record in handoff_files.items()
    )
    if not file_rows:
        file_rows = "| - | - | - |"
    blockers = readiness.get("blocker_reasons") or validation.get("errors") or []
    return f"""# Report Quality Review Packet Handoff

- generated_at: `{handoff_manifest.get('generated_at', '-')}`
- pipeline_manifest: `{handoff_manifest.get('pipeline_manifest_path', '-')}`
- readiness: `{readiness.get('status', 'follow_up_required')}`
- validation_ok: `{str(validation.get('ok') is True).lower()}`
- training_authorized: `false`
- packet_count: `{counts.get('packet_count', 0)}`
- ready_packets: `{counts.get('ready_packets', 0)}`
- exported_artifacts: `{counts.get('exported_artifacts', 0)}`
- ready_artifacts: `{counts.get('ready_artifacts', 0)}`

## Files

| file | exists | path |
| --- | --- | --- |
{file_rows}

## Reviewer Actions

{chr(10).join(f"- {item}" for item in handoff_manifest.get('reviewer_actions', []))}

## Blockers

{chr(10).join(f"- `{item}`" for item in blockers) if blockers else "- none"}

## Side-Effect Boundary

- server_file_written: `false`
- persisted_learning_artifact: `false`
- external_dataset_upload_started: `false`
- provider_fine_tune_api_called: `false`
- provider_job_created: `false`
- training_execution_started: `false`
- model_promotion_started: `false`
"""


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Create a local review packet evidence handoff index.")
    parser.add_argument("pipeline_manifest", type=Path, help="Path to *-evidence-pipeline-manifest.json")
    parser.add_argument("--output-markdown", type=Path, default=None)
    parser.add_argument("--output-manifest", type=Path, default=None)
    parser.add_argument("--allow-not-ready", action="store_true")
    parser.add_argument("--json", action="store_true", help="Print handoff manifest JSON to stdout.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(list(argv) if argv is not None else None)
    manifest = create_review_packet_handoff(
        pipeline_manifest_path=args.pipeline_manifest,
        output_markdown=args.output_markdown,
        output_manifest=args.output_manifest,
        require_ready=not args.allow_not_ready,
    )
    if args.json:
        print(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"Report quality review packet handoff: {'PASS' if manifest['readiness']['ok'] else 'FAIL'}")
        print(f"Packet count: {manifest['counts']['packet_count']}")
        print(f"Ready artifacts: {manifest['counts']['ready_artifacts']}")
        print("training_boundary=not_authorized")
    return 0 if manifest["readiness"]["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
