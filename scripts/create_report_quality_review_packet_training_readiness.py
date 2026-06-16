#!/usr/bin/env python3
"""Create a local training-discussion readiness manifest from review packet evidence."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
from typing import Any, Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_VALIDATOR_PATH = REPO_ROOT / "scripts/validate_report_quality_review_packet_evidence.py"
EXPECTED_SIGNOFF_SUMMARY_SCHEMA = "decisiondoc_report_quality_review_packet_signoff_summary.v1"
EXPECTED_SCHEMA = "decisiondoc_report_quality_review_packet_training_readiness.v1"
FORBIDDEN_TRUE_KEYS = {
    "actual_reviewer_approval_recorded_by_summary",
    "server_file_written",
    "persisted_learning_artifact",
    "external_dataset_upload_started",
    "external_dataset_upload_authorized",
    "provider_fine_tune_api_called",
    "provider_fine_tune_api_call_authorized",
    "provider_job_created",
    "provider_job_creation_authorized",
    "training_execution_started",
    "training_execution_authorized",
    "model_promotion_started",
    "model_promotion_authorized",
}


def _load_evidence_validator():
    spec = importlib.util.spec_from_file_location(
        "validate_report_quality_review_packet_evidence",
        EVIDENCE_VALIDATOR_PATH,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed to load evidence validator: {EVIDENCE_VALIDATOR_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_EVIDENCE_VALIDATOR = _load_evidence_validator()


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


def _scan_forbidden_true(value: Any, *, path: str = "$") -> list[str]:
    findings: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}"
            if key in FORBIDDEN_TRUE_KEYS and child is not False:
                findings.append(f"{child_path} must be false")
            findings.extend(_scan_forbidden_true(child, path=child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            findings.extend(_scan_forbidden_true(child, path=f"{path}[{index}]"))
    return findings


def _default_output_path(evidence_manifest_path: Path, suffix: str) -> Path:
    name = evidence_manifest_path.name
    if name.endswith("-evidence-pipeline-manifest.json"):
        base = name.removesuffix("-evidence-pipeline-manifest.json")
    else:
        base = evidence_manifest_path.stem
    return evidence_manifest_path.with_name(f"{base}{suffix}")


def _validate_signoff_summary(
    summary: dict[str, Any],
    *,
    require_complete: bool,
    errors: list[str],
) -> None:
    if summary.get("schema_version") != EXPECTED_SIGNOFF_SUMMARY_SCHEMA:
        errors.append(f"signoff_summary.schema_version must be {EXPECTED_SIGNOFF_SUMMARY_SCHEMA!r}")
    if summary.get("read_only") is not True:
        errors.append("signoff_summary.read_only must be true")
    if summary.get("ok") is not True:
        errors.append("signoff_summary.ok must be true")

    counts = _as_dict(summary.get("counts"))
    readiness = _as_dict(summary.get("readiness"))
    if counts.get("record_count", 0) < 1:
        errors.append("signoff_summary.counts.record_count must be at least 1")
    if counts.get("invalid_record_count", 0) != 0:
        errors.append("signoff_summary.counts.invalid_record_count must be 0")
    if require_complete:
        if readiness.get("require_complete_ok") is not True:
            errors.append("signoff_summary.readiness.require_complete_ok must be true")
        if counts.get("completed_record_count") != counts.get("record_count"):
            errors.append("signoff_summary completed_record_count must equal record_count")

    for record in _as_list(summary.get("records")):
        record_dict = _as_dict(record)
        if require_complete and record_dict.get("completed") is not True:
            errors.append(f"signoff record {record_dict.get('signoff_id', '-')} must be completed")
        if record_dict.get("boundary_ok") is not True:
            errors.append(f"signoff record {record_dict.get('signoff_id', '-')} boundary_ok must be true")
        if require_complete and record_dict.get("handoff_validation_ok") is not True:
            errors.append(f"signoff record {record_dict.get('signoff_id', '-')} handoff_validation_ok must be true")

    for finding in _scan_forbidden_true(summary):
        errors.append(f"signoff_summary: {finding}")


def build_training_readiness_manifest(
    *,
    evidence_manifest_path: Path,
    signoff_summary_path: Path,
    min_ready_artifacts: int = 1,
    require_completed_signoffs: bool = True,
    generated_at: str | None = None,
) -> dict[str, Any]:
    resolved_evidence = evidence_manifest_path.expanduser().resolve()
    resolved_signoff_summary = signoff_summary_path.expanduser().resolve()
    errors: list[str] = []
    warnings: list[str] = []

    evidence_validation = _EVIDENCE_VALIDATOR.validate_review_packet_evidence_manifest(
        resolved_evidence,
        require_ready=True,
    )
    if evidence_validation.get("ok") is not True:
        errors.append("evidence pipeline validation must pass")
        errors.extend(str(item) for item in evidence_validation.get("errors", []))

    try:
        evidence_manifest = _load_json(resolved_evidence)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        evidence_manifest = {}
        errors.append(f"failed to load evidence manifest: {exc}")

    try:
        signoff_summary = _load_json(resolved_signoff_summary)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        signoff_summary = {}
        errors.append(f"failed to load signoff summary: {exc}")

    _validate_signoff_summary(
        signoff_summary,
        require_complete=require_completed_signoffs,
        errors=errors,
    )

    evidence_counts = _as_dict(evidence_manifest.get("counts"))
    signoff_counts = _as_dict(signoff_summary.get("counts"))
    ready_artifacts = int(evidence_counts.get("ready_artifacts") or 0)
    if ready_artifacts < min_ready_artifacts:
        errors.append(f"ready_artifacts {ready_artifacts} is below min_ready_artifacts {min_ready_artifacts}")

    if _as_dict(evidence_manifest.get("readiness")).get("ok") is not True:
        errors.append("evidence_manifest.readiness.ok must be true")

    for finding in _scan_forbidden_true(evidence_manifest):
        errors.append(f"evidence_manifest: {finding}")

    ready = not errors
    return {
        "report_type": "report_quality_review_packet_training_readiness",
        "schema_version": EXPECTED_SCHEMA,
        "generated_at": generated_at or _now_iso(),
        "readiness": {
            "ok": ready,
            "status": "ready_for_human_training_discussion" if ready else "follow_up_required",
            "ready_for_training_discussion": ready,
            "training_execution_authorized": False,
            "external_dataset_upload_authorized": False,
            "provider_fine_tune_api_call_authorized": False,
            "provider_job_creation_authorized": False,
            "model_promotion_authorized": False,
        },
        "requirements": {
            "min_ready_artifacts": min_ready_artifacts,
            "require_completed_signoffs": require_completed_signoffs,
        },
        "inputs": {
            "evidence_manifest_path": str(resolved_evidence),
            "evidence_manifest_sha256": _sha256(resolved_evidence) if resolved_evidence.exists() else "",
            "signoff_summary_path": str(resolved_signoff_summary),
            "signoff_summary_sha256": _sha256(resolved_signoff_summary) if resolved_signoff_summary.exists() else "",
        },
        "validations": {
            "evidence_pipeline": evidence_validation,
            "signoff_summary_ok": signoff_summary.get("ok") is True,
            "signoff_summary_require_complete_ok": _as_dict(signoff_summary.get("readiness")).get(
                "require_complete_ok"
            ),
        },
        "counts": {
            "packet_count": evidence_counts.get("packet_count", 0),
            "ready_packets": evidence_counts.get("ready_packets", 0),
            "exported_artifacts": evidence_counts.get("exported_artifacts", 0),
            "ready_artifacts": ready_artifacts,
            "signoff_record_count": signoff_counts.get("record_count", 0),
            "completed_signoff_count": signoff_counts.get("completed_record_count", 0),
            "pending_signoff_count": signoff_counts.get("pending_record_count", 0),
            "invalid_signoff_count": signoff_counts.get("invalid_record_count", 0),
        },
        "errors": errors,
        "warnings": warnings,
        "side_effect_boundary": {
            "reads_local_evidence_manifest": True,
            "reads_local_signoff_summary": True,
            "writes_readiness_manifest_only": True,
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


def render_readiness_markdown(manifest: dict[str, Any]) -> str:
    readiness = _as_dict(manifest.get("readiness"))
    counts = _as_dict(manifest.get("counts"))
    inputs = _as_dict(manifest.get("inputs"))
    errors = _as_list(manifest.get("errors"))
    return f"""# Report Quality Review Packet Training Readiness

- generated_at: `{manifest.get('generated_at', '-')}`
- status: `{readiness.get('status', '-')}`
- ready_for_training_discussion: `{str(readiness.get('ready_for_training_discussion') is True).lower()}`
- training_authorized: `false`
- evidence_manifest: `{inputs.get('evidence_manifest_path', '')}`
- signoff_summary: `{inputs.get('signoff_summary_path', '')}`
- ready_artifacts: `{counts.get('ready_artifacts', 0)}`
- completed_signoff_count: `{counts.get('completed_signoff_count', 0)}`
- invalid_signoff_count: `{counts.get('invalid_signoff_count', 0)}`

## Blockers

{chr(10).join(f"- `{item}`" for item in errors) if errors else "- none"}

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


def _write_text_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Create a local report quality training-discussion readiness manifest.")
    parser.add_argument("evidence_manifest", type=Path, help="Path to *-evidence-pipeline-manifest.json.")
    parser.add_argument("signoff_summary", type=Path, help="Path to *-signoff-summary.json.")
    parser.add_argument("--min-ready-artifacts", type=int, default=1)
    parser.add_argument("--allow-pending-signoffs", action="store_true")
    parser.add_argument("--generated-at", help="Optional ISO timestamp for deterministic output.")
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--markdown", type=Path, default=None)
    parser.add_argument("--json", action="store_true", help="Print machine-readable readiness JSON to stdout.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(list(argv) if argv is not None else None)
    evidence_path = args.evidence_manifest.expanduser().resolve()
    output_path = (
        args.output.expanduser().resolve()
        if args.output is not None
        else _default_output_path(evidence_path, "-training-readiness-manifest.json")
    )
    markdown_path = args.markdown.expanduser().resolve() if args.markdown is not None else None
    manifest = build_training_readiness_manifest(
        evidence_manifest_path=evidence_path,
        signoff_summary_path=args.signoff_summary,
        min_ready_artifacts=args.min_ready_artifacts,
        require_completed_signoffs=not args.allow_pending_signoffs,
        generated_at=args.generated_at,
    )
    manifest_text = json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    _write_text_atomic(output_path, manifest_text)
    if markdown_path is not None:
        _write_text_atomic(markdown_path, render_readiness_markdown(manifest))

    if args.json:
        print(manifest_text, end="")
    else:
        print(f"Report quality review packet training readiness: {'PASS' if manifest['readiness']['ok'] else 'FAIL'}")
        print(f"ready_for_training_discussion={str(manifest['readiness']['ready_for_training_discussion']).lower()}")
        print(f"ready_artifacts={manifest['counts']['ready_artifacts']}")
        print("training_boundary=not_authorized")
    return 0 if manifest["readiness"]["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
