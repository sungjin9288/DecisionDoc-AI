#!/usr/bin/env python3
"""Create a local handoff package for report quality training-discussion readiness."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
from typing import Any, Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
READINESS_VALIDATOR_PATH = REPO_ROOT / "scripts/validate_report_quality_review_packet_training_readiness.py"
EXPECTED_SCHEMA = "decisiondoc_report_quality_review_packet_training_discussion_handoff.v1"


def _load_readiness_validator():
    spec = importlib.util.spec_from_file_location(
        "validate_report_quality_review_packet_training_readiness",
        READINESS_VALIDATOR_PATH,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed to load readiness validator: {READINESS_VALIDATOR_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_READINESS_VALIDATOR = _load_readiness_validator()


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


def _default_output_path(readiness_manifest_path: Path, suffix: str) -> Path:
    name = readiness_manifest_path.name
    if name.endswith("-training-readiness-manifest.json"):
        base = name.removesuffix("-training-readiness-manifest.json")
    else:
        base = readiness_manifest_path.stem
    return readiness_manifest_path.with_name(f"{base}{suffix}")


def _file_record(path_value: Any) -> dict[str, Any]:
    if not isinstance(path_value, str) or not path_value.strip():
        return {"path": "", "exists": False, "sha256": ""}
    path = Path(path_value).expanduser().resolve()
    return {
        "path": str(path),
        "exists": path.exists() and path.is_file(),
        "sha256": _sha256(path) if path.exists() and path.is_file() else "",
    }


def _safe_label(value: Any, fallback: str) -> str:
    text = str(value).strip() if value is not None else ""
    if not text:
        text = fallback
    return "".join(ch if ch.isalnum() or ch in {"_", "-"} else "_" for ch in text)


def _collect_handoff_files(
    *,
    readiness_manifest_path: Path,
    readiness_manifest: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    files: dict[str, dict[str, Any]] = {
        "training_readiness_manifest": _file_record(str(readiness_manifest_path)),
    }
    inputs = _as_dict(readiness_manifest.get("inputs"))
    evidence_path_value = inputs.get("evidence_manifest_path")
    signoff_summary_path_value = inputs.get("signoff_summary_path")
    files["evidence_pipeline_manifest"] = _file_record(evidence_path_value)
    files["signoff_summary"] = _file_record(signoff_summary_path_value)

    evidence_record = files["evidence_pipeline_manifest"]
    if evidence_record["exists"]:
        evidence_manifest = _load_json(Path(evidence_record["path"]))
        for key, path_value in sorted(_as_dict(evidence_manifest.get("outputs")).items()):
            files[f"evidence_{key}"] = _file_record(path_value)

    signoff_record = files["signoff_summary"]
    if signoff_record["exists"]:
        signoff_summary = _load_json(Path(signoff_record["path"]))
        for index, record in enumerate(_as_list(signoff_summary.get("records")), start=1):
            record_dict = _as_dict(record)
            label = _safe_label(record_dict.get("signoff_id"), f"signoff_{index}")
            files[f"signoff_record_{label}"] = _file_record(record_dict.get("path"))

    return files


def create_training_discussion_handoff(
    *,
    readiness_manifest_path: Path,
    output_manifest: Path | None = None,
    output_markdown: Path | None = None,
    require_ready: bool = True,
    generated_at: str | None = None,
) -> dict[str, Any]:
    resolved_readiness = readiness_manifest_path.expanduser().resolve()
    readiness_validation = _READINESS_VALIDATOR.validate_training_readiness_manifest(
        resolved_readiness,
        require_ready=require_ready,
    )
    readiness_manifest = _load_json(resolved_readiness)
    output_manifest = (
        output_manifest.expanduser().resolve()
        if output_manifest is not None
        else _default_output_path(resolved_readiness, "-training-discussion-handoff-manifest.json")
    )
    output_markdown = (
        output_markdown.expanduser().resolve()
        if output_markdown is not None
        else _default_output_path(resolved_readiness, "-training-discussion-handoff.md")
    )
    readiness = _as_dict(readiness_manifest.get("readiness"))
    counts = _as_dict(readiness_manifest.get("counts"))
    handoff_files = _collect_handoff_files(
        readiness_manifest_path=resolved_readiness,
        readiness_manifest=readiness_manifest,
    )
    missing_files = sorted(name for name, record in handoff_files.items() if record.get("exists") is not True)
    ok = readiness_validation.get("ok") is True and not missing_files
    manifest = {
        "report_type": "report_quality_review_packet_training_discussion_handoff",
        "schema_version": EXPECTED_SCHEMA,
        "generated_at": generated_at or _now_iso(),
        "readiness_manifest_path": str(resolved_readiness),
        "readiness_manifest_sha256": _sha256(resolved_readiness),
        "handoff_manifest_path": str(output_manifest),
        "handoff_index_path": str(output_markdown),
        "readiness_validation": readiness_validation,
        "readiness": {
            "ok": ok,
            "status": "ready_for_human_training_discussion_handoff" if ok else "follow_up_required",
            "ready_for_training_discussion": readiness.get("ready_for_training_discussion") is True and ok,
            "missing_files": missing_files,
            "training_execution_authorized": False,
            "external_dataset_upload_authorized": False,
            "provider_fine_tune_api_call_authorized": False,
            "provider_job_creation_authorized": False,
            "model_promotion_authorized": False,
        },
        "counts": {
            "ready_artifacts": counts.get("ready_artifacts", 0),
            "completed_signoff_count": counts.get("completed_signoff_count", 0),
            "invalid_signoff_count": counts.get("invalid_signoff_count", 0),
            "handoff_file_count": len(handoff_files),
            "missing_file_count": len(missing_files),
        },
        "handoff_files": handoff_files,
        "operator_actions": [
            "Open the training readiness Markdown and this handoff manifest.",
            "Confirm evidence pipeline, sign-off summary, and readiness validation all pass.",
            "Use this handoff only to discuss whether a future training experiment should be planned.",
            "Do not upload datasets, call provider fine-tune APIs, create provider jobs, start training, or promote models from this handoff.",
        ],
        "side_effect_boundary": {
            "reads_local_training_readiness_manifest": True,
            "writes_local_handoff_files": True,
            "actual_reviewer_approval_recorded": False,
            "server_file_written": False,
            "persisted_learning_artifact": False,
            "external_dataset_upload_started": False,
            "provider_fine_tune_api_called": False,
            "provider_job_created": False,
            "training_execution_started": False,
            "model_promotion_started": False,
        },
    }
    _write_text_atomic(output_manifest, json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    _write_text_atomic(output_markdown, render_training_discussion_handoff_markdown(manifest))
    return manifest


def render_training_discussion_handoff_markdown(manifest: dict[str, Any]) -> str:
    readiness = _as_dict(manifest.get("readiness"))
    counts = _as_dict(manifest.get("counts"))
    files = _as_dict(manifest.get("handoff_files"))
    file_rows = "\n".join(
        "| {name} | {exists} | `{path}` |".format(
            name=name,
            exists="yes" if _as_dict(record).get("exists") else "no",
            path=_as_dict(record).get("path", ""),
        )
        for name, record in files.items()
    )
    if not file_rows:
        file_rows = "| - | - | - |"
    missing = readiness.get("missing_files") or []
    return f"""# Report Quality Training Discussion Handoff

- generated_at: `{manifest.get('generated_at', '-')}`
- readiness: `{readiness.get('status', '-')}`
- ready_for_training_discussion: `{str(readiness.get('ready_for_training_discussion') is True).lower()}`
- training_authorized: `false`
- ready_artifacts: `{counts.get('ready_artifacts', 0)}`
- completed_signoff_count: `{counts.get('completed_signoff_count', 0)}`
- handoff_file_count: `{counts.get('handoff_file_count', 0)}`

## Files

| file | exists | path |
| --- | --- | --- |
{file_rows}

## Operator Actions

{chr(10).join(f"- {item}" for item in manifest.get('operator_actions', []))}

## Blockers

{chr(10).join(f"- `{item}`" for item in missing) if missing else "- none"}

## Side-Effect Boundary

- actual_reviewer_approval_recorded: `false`
- server_file_written: `false`
- persisted_learning_artifact: `false`
- external_dataset_upload_started: `false`
- provider_fine_tune_api_called: `false`
- provider_job_created: `false`
- training_execution_started: `false`
- model_promotion_started: `false`
"""


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Create a local training-discussion handoff from readiness evidence.")
    parser.add_argument("readiness_manifest", type=Path, help="Path to *-training-readiness-manifest.json.")
    parser.add_argument("--output-manifest", type=Path, default=None)
    parser.add_argument("--output-markdown", type=Path, default=None)
    parser.add_argument("--allow-not-ready", action="store_true")
    parser.add_argument("--generated-at", help="Optional ISO timestamp for deterministic output.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable handoff manifest to stdout.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(list(argv) if argv is not None else None)
    manifest = create_training_discussion_handoff(
        readiness_manifest_path=args.readiness_manifest,
        output_manifest=args.output_manifest,
        output_markdown=args.output_markdown,
        require_ready=not args.allow_not_ready,
        generated_at=args.generated_at,
    )
    if args.json:
        print(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"Report quality training discussion handoff: {'PASS' if manifest['readiness']['ok'] else 'FAIL'}")
        print(
            "ready_for_training_discussion="
            f"{str(manifest['readiness']['ready_for_training_discussion']).lower()}"
        )
        print(f"handoff_file_count={manifest['counts']['handoff_file_count']}")
        print("training_boundary=not_authorized")
    return 0 if manifest["readiness"]["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
