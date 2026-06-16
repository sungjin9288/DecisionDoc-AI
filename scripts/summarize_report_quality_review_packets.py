#!/usr/bin/env python3
"""Create a local batch manifest from Report Workflow review packet JSON files."""
from __future__ import annotations

import argparse
from collections import Counter
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


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _score(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    return None


def _counter_payload(counter: Counter[str]) -> dict[str, int]:
    return dict(sorted(counter.items(), key=lambda item: (-item[1], item[0])))


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


def _packet_summary(
    *,
    path: Path,
    packet: dict[str, Any],
    validation: dict[str, Any],
) -> dict[str, Any]:
    workflow = _as_dict(packet.get("report_workflow"))
    quality_payload = _as_dict(packet.get("quality_payload"))
    develop_preview = _as_dict(packet.get("develop_preview"))
    preview_artifact = _as_dict(packet.get("preview_artifact"))
    preview_artifact_validation = _as_dict(validation.get("preview_artifact_validation"))
    return {
        "path": str(path),
        "sha256": _sha256(path),
        "packet_version": packet.get("packet_version", ""),
        "report_workflow_id": workflow.get("report_workflow_id", ""),
        "workflow_title": workflow.get("title", ""),
        "workflow_status": workflow.get("status", ""),
        "learning_opt_in": workflow.get("learning_opt_in") is True,
        "reviewer": quality_payload.get("reviewer", ""),
        "reviewed_at": quality_payload.get("reviewed_at", ""),
        "overall_score": quality_payload.get("overall_score"),
        "accepted_for_learning": quality_payload.get("accepted_for_learning") is True,
        "human_review_status": quality_payload.get("human_review_status", ""),
        "preview_artifact_id": packet.get("preview_artifact_id", ""),
        "preview_artifact_schema": preview_artifact.get("schema_version", ""),
        "preview_artifact_ok": validation.get("preview_artifact_ok") is True,
        "preview_artifact_ready_for_learning": validation.get("preview_artifact_ready_for_learning") is True,
        "preview_artifact_validation_errors": list(preview_artifact_validation.get("errors") or []),
        "checklist_count": int(validation.get("checklist_count") or 0),
        "checklist_passed": int(validation.get("checklist_passed") or 0),
        "checklist_pending": int(validation.get("checklist_pending") or 0),
        "develop_task_type": develop_preview.get("task_type", ""),
        "develop_skill_name": develop_preview.get("skill_name", ""),
        "validation_ok": validation.get("ok") is True,
        "ready_for_learning": validation.get("ready_for_learning") is True,
        "validation_errors": list(validation.get("errors") or []),
        "validation_warnings": list(validation.get("warnings") or []),
    }


def create_review_packet_batch_manifest(
    *,
    packet_paths: Sequence[Path],
    batch_id: str = "",
    min_packets: int = 3,
    require_ready: bool = False,
) -> dict[str, Any]:
    resolved_paths = _expand_packet_paths(packet_paths)
    min_packets = max(1, int(min_packets or 1))

    rows: list[dict[str, Any]] = []
    parse_errors: list[dict[str, Any]] = []
    reviewers: Counter[str] = Counter()
    workflow_statuses: Counter[str] = Counter()
    develop_tasks: Counter[str] = Counter()
    develop_skills: Counter[str] = Counter()
    overall_scores: list[float] = []

    for path in resolved_paths:
        try:
            packet = _load_packet(path)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            parse_errors.append({"path": str(path), "error": str(exc)})
            continue

        validation = _PACKET_VALIDATOR.validate_review_packet(packet, require_ready=require_ready)
        row = _packet_summary(path=path, packet=packet, validation=validation)
        rows.append(row)

        if row["reviewer"]:
            reviewers[str(row["reviewer"])] += 1
        if row["workflow_status"]:
            workflow_statuses[str(row["workflow_status"])] += 1
        if row["develop_task_type"]:
            develop_tasks[str(row["develop_task_type"])] += 1
        if row["develop_skill_name"]:
            develop_skills[str(row["develop_skill_name"])] += 1
        score = _score(row.get("overall_score"))
        if score is not None:
            overall_scores.append(score)

    packet_count = len(rows)
    valid_packets = sum(1 for row in rows if row["validation_ok"])
    ready_packets = sum(1 for row in rows if row["ready_for_learning"])
    blocker_reasons: list[str] = []
    if parse_errors:
        blocker_reasons.append("packet_parse_errors")
    if packet_count < min_packets:
        blocker_reasons.append("minimum_packet_count_not_met")
    if valid_packets != packet_count:
        blocker_reasons.append("invalid_packets_present")
    if require_ready and ready_packets != packet_count:
        blocker_reasons.append("not_ready_packets_present")

    ok = not blocker_reasons and packet_count >= min_packets
    manifest = {
        "report_type": "report_quality_review_packet_batch_manifest",
        "schema_version": "decisiondoc_report_quality_review_packet_batch_manifest.v1",
        "batch_id": batch_id.strip() or f"rqp_batch_{uuid.uuid4().hex[:12]}",
        "generated_at": _now_iso(),
        "require_ready": require_ready,
        "readiness": {
            "ok": ok,
            "status": "ready_for_human_review" if ok else "follow_up_required",
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
            "not_ready_packets": packet_count - ready_packets,
            "parse_errors": len(parse_errors),
            "reviewer_count": len(reviewers),
        },
        "quality": {
            "overall_score": {
                "count": len(overall_scores),
                "avg": round(sum(overall_scores) / len(overall_scores), 4) if overall_scores else None,
                "min": round(min(overall_scores), 4) if overall_scores else None,
                "max": round(max(overall_scores), 4) if overall_scores else None,
            },
        },
        "distribution": {
            "reviewers": _counter_payload(reviewers),
            "workflow_statuses": _counter_payload(workflow_statuses),
            "develop_task_types": _counter_payload(develop_tasks),
            "develop_skills": _counter_payload(develop_skills),
        },
        "parse_errors": parse_errors,
        "packets": rows,
        "side_effect_boundary": {
            "reads_local_review_packet_json": True,
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
    return manifest


def render_review_packet_batch_markdown(manifest: dict[str, Any]) -> str:
    readiness = _as_dict(manifest.get("readiness"))
    counts = _as_dict(manifest.get("counts"))
    quality = _as_dict(manifest.get("quality"))
    overall = _as_dict(quality.get("overall_score"))
    distribution = _as_dict(manifest.get("distribution"))
    blockers = _as_list(readiness.get("blocker_reasons"))
    packet_rows = _as_list(manifest.get("packets"))
    packet_table = "\n".join(
        "| {workflow_id} | {reviewer} | {score} | {checklist} | {artifact_ready} | {packet_ready} |".format(
            workflow_id=str(row.get("report_workflow_id") or "-"),
            reviewer=str(row.get("reviewer") or "-"),
            score=str(row.get("overall_score") if row.get("overall_score") is not None else "-"),
            checklist=f"{row.get('checklist_passed', 0)}/{row.get('checklist_count', 0)}",
            artifact_ready="yes" if row.get("preview_artifact_ready_for_learning") else "no",
            packet_ready="yes" if row.get("ready_for_learning") else "no",
        )
        for row in packet_rows[:25]
        if isinstance(row, dict)
    )
    if not packet_table:
        packet_table = "| - | - | - | - | - | - |"

    return f"""# Report Quality Review Packet Batch Summary

- batch_id: `{manifest.get('batch_id', '-')}`
- generated_at: `{manifest.get('generated_at', '-')}`
- readiness: `{readiness.get('status', 'follow_up_required')}`
- require_ready: `{str(manifest.get('require_ready', False)).lower()}`
- training_authorized: `false`
- packet_count: `{counts.get('packet_count', 0)}`
- ready_packets: `{counts.get('ready_packets', 0)}`
- min_packets: `{readiness.get('min_packets', 0)}`
- reviewer_count: `{counts.get('reviewer_count', 0)}`
- overall_score_avg: `{overall.get('avg', '-')}`

## Blockers

{chr(10).join(f'- `{item}`' for item in blockers) if blockers else '- none'}

## Distribution

- reviewers: `{json.dumps(distribution.get('reviewers') or {}, ensure_ascii=False, sort_keys=True)}`
- workflow_statuses: `{json.dumps(distribution.get('workflow_statuses') or {}, ensure_ascii=False, sort_keys=True)}`
- develop_task_types: `{json.dumps(distribution.get('develop_task_types') or {}, ensure_ascii=False, sort_keys=True)}`
- develop_skills: `{json.dumps(distribution.get('develop_skills') or {}, ensure_ascii=False, sort_keys=True)}`

## Packet Sample

| workflow_id | reviewer | overall_score | checklist | preview_artifact_ready | packet_ready |
| --- | --- | --- | --- | --- | --- |
{packet_table}

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
    parser = argparse.ArgumentParser(
        description="Summarize Report Workflow review packet JSON files into a local batch manifest.",
    )
    parser.add_argument("packets", type=Path, nargs="+", help="Review packet JSON files or directories.")
    parser.add_argument("--batch-id", default="")
    parser.add_argument("--min-packets", type=int, default=3)
    parser.add_argument("--require-ready", action="store_true")
    parser.add_argument("--output", type=Path, default=Path("reports/report-quality/review_packet_manifest.json"))
    parser.add_argument("--markdown", type=Path, default=Path("reports/report-quality/review_packet_summary.md"))
    parser.add_argument("--json", action="store_true", help="Print manifest JSON to stdout.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(list(argv) if argv is not None else None)
    manifest = create_review_packet_batch_manifest(
        packet_paths=args.packets,
        batch_id=args.batch_id,
        min_packets=args.min_packets,
        require_ready=args.require_ready,
    )
    manifest_text = json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output:
        _write_text_atomic(args.output, manifest_text)
    if args.markdown:
        _write_text_atomic(args.markdown, render_review_packet_batch_markdown(manifest))
    if args.json:
        print(manifest_text, end="")
    else:
        print(f"Report quality review packet readiness: {'PASS' if manifest['readiness']['ok'] else 'FAIL'}")
        print(f"Batch id: {manifest['batch_id']}")
        print(f"Packet count: {manifest['counts']['packet_count']}")
        print(f"Ready packets: {manifest['counts']['ready_packets']}")
        print(f"Manifest: {args.output}")
        print(f"Markdown: {args.markdown}")
        print("training_boundary=not_authorized")
    return 0 if manifest["readiness"]["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
