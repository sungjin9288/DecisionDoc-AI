#!/usr/bin/env python3
"""Extract correction artifact JSONL from local Report Workflow review packets."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import uuid
from typing import Any, Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
VALIDATOR_PATH = REPO_ROOT / "docs/specs/report_quality_learning/validate_review_packet.py"
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.services.report_quality_learning import validate_correction_artifact  # noqa: E402


def _load_packet_validator():
    spec = importlib.util.spec_from_file_location("validate_review_packet", VALIDATOR_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed to load review packet validator: {VALIDATOR_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_PACKET_VALIDATOR = _load_packet_validator()


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


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _expand_packet_paths(paths: Sequence[Path]) -> list[Path]:
    expanded: list[Path] = []
    for path in paths:
        resolved = path.expanduser().resolve()
        if resolved.is_dir():
            expanded.extend(sorted(resolved.glob("*.json")))
        else:
            expanded.append(resolved)
    return sorted(dict.fromkeys(expanded))


def _load_packet(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("review packet root must be an object")
    return payload


def export_artifacts_from_review_packets(
    *,
    packet_paths: Sequence[Path],
    output_path: Path,
    batch_id: str = "",
    min_packets: int = 1,
    require_ready: bool = True,
) -> dict[str, Any]:
    resolved_paths = _expand_packet_paths(packet_paths)
    resolved_output = output_path.expanduser().resolve()
    min_packets = max(1, int(min_packets or 1))

    exported_artifacts: list[dict[str, Any]] = []
    packet_rows: list[dict[str, Any]] = []
    parse_errors: list[dict[str, Any]] = []

    for path in resolved_paths:
        try:
            packet = _load_packet(path)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            parse_errors.append({"path": str(path), "error": str(exc)})
            continue

        packet_validation = _PACKET_VALIDATOR.validate_review_packet(packet, require_ready=require_ready)
        preview_artifact = packet.get("preview_artifact")
        artifact_validation = (
            validate_correction_artifact(preview_artifact)
            if isinstance(preview_artifact, dict)
            else {
                "ok": False,
                "ready_for_learning": False,
                "errors": ["preview_artifact must be an object"],
                "warnings": [],
                "artifact_id": None,
                "schema_version": None,
            }
        )
        exportable = (
            packet_validation.get("ok") is True
            and isinstance(preview_artifact, dict)
            and artifact_validation.get("ok") is True
            and (not require_ready or artifact_validation.get("ready_for_learning") is True)
        )
        row = {
            "path": str(path),
            "sha256": _sha256(path),
            "report_workflow_id": _as_dict(packet.get("report_workflow")).get("report_workflow_id", ""),
            "preview_artifact_id": artifact_validation.get("artifact_id"),
            "packet_ok": packet_validation.get("ok") is True,
            "packet_ready_for_learning": packet_validation.get("ready_for_learning") is True,
            "artifact_ok": artifact_validation.get("ok") is True,
            "artifact_ready_for_learning": artifact_validation.get("ready_for_learning") is True,
            "exported": exportable,
            "errors": list(packet_validation.get("errors") or [])
            + [f"preview_artifact: {error}" for error in artifact_validation.get("errors") or []],
            "warnings": list(packet_validation.get("warnings") or [])
            + [f"preview_artifact: {warning}" for warning in artifact_validation.get("warnings") or []],
        }
        packet_rows.append(row)
        if exportable:
            exported_artifacts.append(preview_artifact)

    artifact_count = len(exported_artifacts)
    packet_count = len(packet_rows)
    valid_packets = sum(1 for row in packet_rows if row["packet_ok"])
    ready_packets = sum(1 for row in packet_rows if row["packet_ready_for_learning"])
    blocker_reasons: list[str] = []
    if parse_errors:
        blocker_reasons.append("packet_parse_errors")
    if packet_count < min_packets:
        blocker_reasons.append("minimum_packet_count_not_met")
    if valid_packets != packet_count:
        blocker_reasons.append("invalid_packets_present")
    if require_ready and ready_packets != packet_count:
        blocker_reasons.append("not_ready_packets_present")
    if artifact_count < min_packets:
        blocker_reasons.append("minimum_exported_artifact_count_not_met")

    ok = not blocker_reasons
    jsonl_text = "\n".join(
        json.dumps(artifact, ensure_ascii=False, sort_keys=True)
        for artifact in exported_artifacts
    )
    if jsonl_text:
        jsonl_text += "\n"
    _write_text_atomic(resolved_output, jsonl_text)

    return {
        "report_type": "report_quality_review_packet_artifact_export",
        "schema_version": "decisiondoc_report_quality_review_packet_artifact_export.v1",
        "batch_id": batch_id.strip() or f"rqp_artifact_export_{uuid.uuid4().hex[:12]}",
        "generated_at": _now_iso(),
        "require_ready": require_ready,
        "source": {
            "packet_count": len(resolved_paths),
            "paths": [str(path) for path in resolved_paths],
        },
        "output": {
            "jsonl_path": str(resolved_output),
            "artifact_count": artifact_count,
            "jsonl_sha256": _sha256(resolved_output),
        },
        "readiness": {
            "ok": ok,
            "status": "ready_for_artifact_validation" if ok else "follow_up_required",
            "min_packets": min_packets,
            "blocker_reasons": blocker_reasons,
            "training_execution_authorized": False,
            "external_dataset_upload_authorized": False,
            "provider_fine_tune_api_call_authorized": False,
            "provider_job_creation_authorized": False,
            "model_promotion_authorized": False,
        },
        "counts": {
            "packet_count": packet_count,
            "valid_packets": valid_packets,
            "ready_packets": ready_packets,
            "exported_artifacts": artifact_count,
            "parse_errors": len(parse_errors),
        },
        "parse_errors": parse_errors,
        "packets": packet_rows,
        "side_effect_boundary": {
            "reads_local_review_packet_json": True,
            "writes_local_jsonl": True,
            "writes_manifest_only": True,
            "server_file_written": False,
            "persisted_learning_artifact": False,
            "external_dataset_upload_started": False,
            "provider_fine_tune_api_called": False,
            "provider_job_created": False,
            "training_execution_started": False,
            "model_promotion_started": False,
        },
    }


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Extract correction artifact JSONL from local Report Workflow review packet JSON files.",
    )
    parser.add_argument("packets", type=Path, nargs="+", help="Review packet JSON files or directories.")
    parser.add_argument("--batch-id", default="")
    parser.add_argument("--min-packets", type=int, default=1)
    parser.add_argument("--allow-pending", action="store_true", help="Allow valid non-ready packet artifacts.")
    parser.add_argument("--output", type=Path, default=Path("reports/report-quality/review_packet_artifacts.jsonl"))
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("reports/report-quality/review_packet_artifact_export_manifest.json"),
    )
    parser.add_argument("--json", action="store_true", help="Print manifest JSON to stdout.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(list(argv) if argv is not None else None)
    manifest = export_artifacts_from_review_packets(
        packet_paths=args.packets,
        output_path=args.output,
        batch_id=args.batch_id,
        min_packets=args.min_packets,
        require_ready=not args.allow_pending,
    )
    manifest_text = json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.manifest:
        _write_text_atomic(args.manifest, manifest_text)
    if args.json:
        print(manifest_text, end="")
    else:
        print(f"Report quality artifact export: {'PASS' if manifest['readiness']['ok'] else 'FAIL'}")
        print(f"Batch id: {manifest['batch_id']}")
        print(f"Packet count: {manifest['counts']['packet_count']}")
        print(f"Exported artifacts: {manifest['counts']['exported_artifacts']}")
        print(f"JSONL: {manifest['output']['jsonl_path']}")
        print(f"Manifest: {args.manifest}")
        print("training_boundary=not_authorized")
    return 0 if manifest["readiness"]["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
