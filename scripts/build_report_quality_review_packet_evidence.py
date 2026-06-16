#!/usr/bin/env python3
"""Build local evidence artifacts from Report Workflow review packet JSON files."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import sys
import uuid
from typing import Any, Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

PACKET_SUMMARY_PATH = REPO_ROOT / "scripts/summarize_report_quality_review_packets.py"
PACKET_ARTIFACT_EXPORT_PATH = REPO_ROOT / "scripts/export_report_quality_artifacts_from_review_packets.py"
ARTIFACT_SUMMARY_PATH = REPO_ROOT / "scripts/summarize_report_quality_artifacts.py"


def _load_script(path: Path, module_name: str):
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed to load script module: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_PACKET_SUMMARY = _load_script(PACKET_SUMMARY_PATH, "summarize_report_quality_review_packets")
_PACKET_ARTIFACT_EXPORT = _load_script(
    PACKET_ARTIFACT_EXPORT_PATH,
    "export_report_quality_artifacts_from_review_packets",
)
_ARTIFACT_SUMMARY = _load_script(ARTIFACT_SUMMARY_PATH, "summarize_report_quality_artifacts")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_text_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _stage_blockers(stage_name: str, manifest: dict[str, Any]) -> list[str]:
    readiness = _as_dict(manifest.get("readiness"))
    return [f"{stage_name}:{reason}" for reason in readiness.get("blocker_reasons") or []]


def _default_batch_id() -> str:
    return f"rqp_evidence_{uuid.uuid4().hex[:12]}"


def build_review_packet_evidence_pipeline(
    *,
    packet_paths: Sequence[Path],
    batch_id: str = "",
    output_root: Path = Path("reports/report-quality"),
    min_packets: int = 3,
    require_ready: bool = True,
) -> dict[str, Any]:
    batch_id = batch_id.strip() or _default_batch_id()
    min_packets = max(1, int(min_packets or 1))
    resolved_output_root = output_root.expanduser().resolve()

    packet_manifest_path = resolved_output_root / f"{batch_id}-review-packet-manifest.json"
    packet_summary_path = resolved_output_root / f"{batch_id}-review-packet-summary.md"
    artifact_jsonl_path = resolved_output_root / f"{batch_id}-from-review-packets.jsonl"
    artifact_export_manifest_path = resolved_output_root / f"{batch_id}-artifact-export-manifest.json"
    artifact_batch_manifest_path = resolved_output_root / f"{batch_id}-artifact-batch-manifest.json"
    artifact_batch_summary_path = resolved_output_root / f"{batch_id}-artifact-batch-summary.md"
    pipeline_manifest_path = resolved_output_root / f"{batch_id}-evidence-pipeline-manifest.json"

    packet_manifest = _PACKET_SUMMARY.create_review_packet_batch_manifest(
        packet_paths=packet_paths,
        batch_id=batch_id,
        min_packets=min_packets,
        require_ready=require_ready,
    )
    _write_text_atomic(
        packet_manifest_path,
        json.dumps(packet_manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )
    _write_text_atomic(packet_summary_path, _PACKET_SUMMARY.render_review_packet_batch_markdown(packet_manifest))

    artifact_export_manifest = _PACKET_ARTIFACT_EXPORT.export_artifacts_from_review_packets(
        packet_paths=packet_paths,
        output_path=artifact_jsonl_path,
        batch_id=batch_id,
        min_packets=min_packets,
        require_ready=require_ready,
    )
    _write_text_atomic(
        artifact_export_manifest_path,
        json.dumps(artifact_export_manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )

    artifact_batch_manifest = _ARTIFACT_SUMMARY.create_report_quality_batch_manifest(
        jsonl_path=artifact_jsonl_path,
        batch_id=batch_id,
        min_records=min_packets,
    )
    _write_text_atomic(
        artifact_batch_manifest_path,
        json.dumps(artifact_batch_manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )
    _write_text_atomic(artifact_batch_summary_path, _ARTIFACT_SUMMARY.render_batch_markdown(artifact_batch_manifest))

    blocker_reasons = (
        _stage_blockers("review_packet_summary", packet_manifest)
        + _stage_blockers("artifact_export", artifact_export_manifest)
        + _stage_blockers("artifact_batch_summary", artifact_batch_manifest)
    )
    ok = (
        packet_manifest.get("readiness", {}).get("ok") is True
        and artifact_export_manifest.get("readiness", {}).get("ok") is True
        and artifact_batch_manifest.get("readiness", {}).get("ok") is True
        and not blocker_reasons
    )

    pipeline_manifest = {
        "report_type": "report_quality_review_packet_evidence_pipeline",
        "schema_version": "decisiondoc_report_quality_review_packet_evidence_pipeline.v1",
        "batch_id": batch_id,
        "generated_at": _now_iso(),
        "require_ready": require_ready,
        "source": {
            "packet_paths": [str(path.expanduser().resolve()) for path in packet_paths],
        },
        "outputs": {
            "review_packet_manifest": str(packet_manifest_path),
            "review_packet_summary": str(packet_summary_path),
            "artifact_jsonl": str(artifact_jsonl_path),
            "artifact_export_manifest": str(artifact_export_manifest_path),
            "artifact_batch_manifest": str(artifact_batch_manifest_path),
            "artifact_batch_summary": str(artifact_batch_summary_path),
            "pipeline_manifest": str(pipeline_manifest_path),
        },
        "readiness": {
            "ok": ok,
            "status": "ready_for_human_training_review" if ok else "follow_up_required",
            "min_packets": min_packets,
            "blocker_reasons": blocker_reasons,
            "training_execution_authorized": False,
            "external_dataset_upload_authorized": False,
            "provider_fine_tune_api_call_authorized": False,
            "provider_job_creation_authorized": False,
            "model_promotion_authorized": False,
        },
        "counts": {
            "packet_count": packet_manifest.get("counts", {}).get("packet_count", 0),
            "ready_packets": packet_manifest.get("counts", {}).get("ready_packets", 0),
            "exported_artifacts": artifact_export_manifest.get("counts", {}).get("exported_artifacts", 0),
            "ready_artifacts": artifact_batch_manifest.get("counts", {}).get("ready_artifacts", 0),
        },
        "stage_readiness": {
            "review_packet_summary": packet_manifest.get("readiness", {}),
            "artifact_export": artifact_export_manifest.get("readiness", {}),
            "artifact_batch_summary": artifact_batch_manifest.get("readiness", {}),
        },
        "side_effect_boundary": {
            "reads_local_review_packet_json": True,
            "writes_local_evidence_files": True,
            "server_file_written": False,
            "persisted_learning_artifact": False,
            "external_dataset_upload_started": False,
            "provider_fine_tune_api_called": False,
            "provider_job_created": False,
            "training_execution_started": False,
            "model_promotion_started": False,
        },
    }
    _write_text_atomic(
        pipeline_manifest_path,
        json.dumps(pipeline_manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )
    return pipeline_manifest


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build local review-packet, correction-artifact, and pipeline evidence manifests.",
    )
    parser.add_argument("packets", type=Path, nargs="+", help="Review packet JSON files or directories.")
    parser.add_argument("--batch-id", default="")
    parser.add_argument("--output-root", type=Path, default=Path("reports/report-quality"))
    parser.add_argument("--min-packets", type=int, default=3)
    parser.add_argument("--allow-pending", action="store_true", help="Allow valid non-ready packet artifacts.")
    parser.add_argument("--json", action="store_true", help="Print pipeline manifest JSON to stdout.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(list(argv) if argv is not None else None)
    manifest = build_review_packet_evidence_pipeline(
        packet_paths=args.packets,
        batch_id=args.batch_id,
        output_root=args.output_root,
        min_packets=args.min_packets,
        require_ready=not args.allow_pending,
    )
    if args.json:
        print(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"Report quality review packet evidence pipeline: {'PASS' if manifest['readiness']['ok'] else 'FAIL'}")
        print(f"Batch id: {manifest['batch_id']}")
        print(f"Packet count: {manifest['counts']['packet_count']}")
        print(f"Exported artifacts: {manifest['counts']['exported_artifacts']}")
        print(f"Pipeline manifest: {manifest['outputs']['pipeline_manifest']}")
        print("training_boundary=not_authorized")
    return 0 if manifest["readiness"]["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
