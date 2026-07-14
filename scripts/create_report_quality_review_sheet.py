#!/usr/bin/env python3
"""Create a human review worksheet for Report Quality pilot artifacts."""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence
from uuid import uuid4


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.services.report_quality_learning import (  # noqa: E402
    MIN_EXPORT_READINESS_SCORE,
    MIN_OVERALL_SCORE,
    MIN_REQUIRED_DIMENSION_SCORE,
    MIN_VISUAL_DESIGN_SCORE,
    REQUIRED_DIMENSIONS,
    validate_correction_artifact,
)
from scripts.report_quality_pilot_pack_provenance import load_pilot_pack  # noqa: E402


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_text_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.tmp.{uuid4().hex}")
    with tmp.open("w", encoding="utf-8") as handle:
        handle.write(text)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _score(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        score = float(value)
        if 0.0 <= score <= 1.0:
            return score
    return None


def _dimension_threshold(dimension: str) -> float:
    if dimension == "visual_design":
        return MIN_VISUAL_DESIGN_SCORE
    if dimension == "export_readiness":
        return MIN_EXPORT_READINESS_SCORE
    return MIN_REQUIRED_DIMENSION_SCORE


def _default_output_path(pack_dir: Path) -> Path:
    return pack_dir / "HUMAN_REVIEW_WORKSHEET.md"


def _default_manifest_path(pack_dir: Path) -> Path:
    return pack_dir / "human_review_manifest.json"


def _contains_placeholder(value: Any) -> bool:
    if isinstance(value, dict):
        return any(_contains_placeholder(child) for child in value.values())
    if isinstance(value, list):
        return any(_contains_placeholder(child) for child in value)
    if isinstance(value, str):
        upper_value = value.upper()
        return "TODO_" in upper_value or "TODO:" in upper_value or "TODO " in upper_value
    return False


def artifact_required_actions(payload: dict[str, Any], validation: dict[str, Any]) -> list[str]:
    workflow = _as_dict(payload.get("workflow_reference"))
    quality = _as_dict(payload.get("quality_baseline"))
    correction = _as_dict(payload.get("correction"))
    labels = _as_dict(payload.get("learning_labels"))
    dimension_scores = _as_dict(quality.get("dimension_scores"))
    actions: list[str] = []

    if validation.get("errors"):
        actions.append("fix_validation_errors")
    if labels.get("accepted_for_learning") is not True:
        actions.append("human_decision_pending")
    if workflow.get("workflow_status") != "final_approved":
        actions.append("confirm_final_approval")
    if workflow.get("learning_opt_in") is not True:
        actions.append("confirm_learning_opt_in")
    if not str(correction.get("reviewer") or "").strip():
        actions.append("fill_reviewer")
    if not str(correction.get("reviewed_at") or "").strip():
        actions.append("fill_reviewed_at")
    if labels.get("forbidden_terms_scan") != "pass":
        actions.append("run_forbidden_terms_scan")
    if labels.get("privacy_security_scan") != "pass":
        actions.append("run_privacy_security_scan")
    overall_score = _score(quality.get("overall_score"))
    if overall_score is None or overall_score < MIN_OVERALL_SCORE:
        actions.append("score_overall_quality")
    for dimension in REQUIRED_DIMENSIONS:
        score = _score(dimension_scores.get(dimension))
        if score is None or score < _dimension_threshold(dimension):
            actions.append(f"score_{dimension}")
    if _as_list(quality.get("hard_failures")):
        actions.append("resolve_hard_failures")
    if _as_list(labels.get("todo_claims")):
        actions.append("resolve_or_document_todo_claims")
    if _contains_placeholder(payload):
        actions.append("remove_placeholders")
    return sorted(dict.fromkeys(actions))


def _artifact_row(
    path: Path,
    payload: dict[str, Any],
    validation: dict[str, Any],
    *,
    draft_sha256: str,
) -> dict[str, Any]:
    workflow = _as_dict(payload.get("workflow_reference"))
    profile = _as_dict(payload.get("document_profile"))
    quality = _as_dict(payload.get("quality_baseline"))
    correction = _as_dict(payload.get("correction"))
    labels = _as_dict(payload.get("learning_labels"))
    actions = artifact_required_actions(payload, validation)
    return {
        "path": str(path),
        "draft_sha256": draft_sha256,
        "artifact_id": str(payload.get("artifact_id") or ""),
        "report_workflow_id": str(workflow.get("report_workflow_id") or ""),
        "workflow_status": str(workflow.get("workflow_status") or ""),
        "learning_opt_in": bool(workflow.get("learning_opt_in")),
        "document_type": str(profile.get("document_type") or ""),
        "domain": str(profile.get("domain") or ""),
        "slide_count": profile.get("slide_count"),
        "reviewer": str(correction.get("reviewer") or ""),
        "reviewed_at": str(correction.get("reviewed_at") or ""),
        "overall_score": quality.get("overall_score"),
        "human_review_status": str(labels.get("human_review_status") or ""),
        "accepted_for_learning": labels.get("accepted_for_learning") is True,
        "validation_ok": bool(validation.get("ok")),
        "ready_for_learning": bool(validation.get("ready_for_learning")),
        "required_actions": actions,
        "validation_errors": list(validation.get("errors") or []),
        "validation_warnings": list(validation.get("warnings") or []),
    }


def create_report_quality_review_sheet(
    *,
    pack_dir: Path,
    output_path: Path | None = None,
    manifest_path: Path | None = None,
) -> dict[str, Any]:
    resolved_pack_dir = pack_dir.expanduser().resolve()
    resolved_output_path = (
        output_path.expanduser().resolve()
        if output_path is not None
        else _default_output_path(resolved_pack_dir).resolve()
    )
    resolved_manifest_path = (
        manifest_path.expanduser().resolve()
        if manifest_path is not None
        else _default_manifest_path(resolved_pack_dir).resolve()
    )
    snapshot = load_pilot_pack(resolved_pack_dir)
    rows: list[dict[str, Any]] = []
    for draft in snapshot.drafts:
        payload = draft.payload
        validation = validate_correction_artifact(payload)
        rows.append(
            _artifact_row(
                draft.path,
                payload,
                validation,
                draft_sha256=draft.sha256,
            )
        )

    artifact_count = len(rows)
    ready_artifacts = sum(1 for row in rows if row["ready_for_learning"])
    accepted_artifacts = sum(1 for row in rows if row["accepted_for_learning"])
    pending_artifacts = sum(1 for row in rows if row["human_review_status"] == "pending")
    changes_requested_artifacts = sum(
        1 for row in rows if row["human_review_status"] == "changes_requested"
    )
    invalid_artifacts = sum(1 for row in rows if not row["validation_ok"])
    manifest = {
        "report_type": "report_quality_human_review_sheet_manifest",
        "schema_version": "decisiondoc_report_quality_human_review_sheet_manifest.v1",
        "generated_at": _now_iso(),
        "pack_dir": str(resolved_pack_dir),
        "output_path": str(resolved_output_path),
        "manifest_path": str(resolved_manifest_path),
        "pack_binding": snapshot.binding(),
        "counts": {
            "artifact_count": artifact_count,
            "validation_ok_artifacts": artifact_count - invalid_artifacts,
            "invalid_artifacts": invalid_artifacts,
            "accepted_artifacts": accepted_artifacts,
            "ready_artifacts": ready_artifacts,
            "not_ready_artifacts": artifact_count - ready_artifacts,
            "pending_artifacts": pending_artifacts,
            "changes_requested_artifacts": changes_requested_artifacts,
        },
        "artifacts": rows,
        "side_effect_boundary": {
            "reads_local_draft_json": True,
            "reads_source_manifest": snapshot.source_order_applied,
            "writes_review_sheet": True,
            "writes_manifest": True,
            "external_dataset_upload_started": False,
            "provider_fine_tune_api_called": False,
            "provider_job_created": False,
            "training_execution_started": False,
            "model_promotion_started": False,
        },
    }
    _write_text_atomic(resolved_output_path, render_review_sheet_markdown(manifest))
    _write_text_atomic(
        resolved_manifest_path,
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )
    return manifest


def _action_text(actions: list[str]) -> str:
    if not actions:
        return "none"
    return ", ".join(f"`{item}`" for item in actions[:8])


def render_review_sheet_markdown(manifest: dict[str, Any]) -> str:
    counts = _as_dict(manifest.get("counts"))
    pack_binding = _as_dict(manifest.get("pack_binding"))
    source_manifest = _as_dict(pack_binding.get("source_manifest"))
    rows = [row for row in _as_list(manifest.get("artifacts")) if isinstance(row, dict)]
    table = "\n".join(
        "| {artifact_id} | {workflow_id} | {domain} | {score} | {status} | {ready} | {actions} |".format(
            artifact_id=row.get("artifact_id") or "-",
            workflow_id=row.get("report_workflow_id") or "-",
            domain=row.get("domain") or "-",
            score=row.get("overall_score"),
            status=row.get("human_review_status") or "-",
            ready="yes" if row.get("ready_for_learning") else "no",
            actions=_action_text(list(row.get("required_actions") or [])),
        )
        for row in rows
    )
    if not table:
        table = "| - | - | - | - | - | - | - |"

    detail_sections = "\n\n".join(
        """### {artifact_id}

- draft_file: `{path}`
- workflow_id: `{workflow_id}`
- document_type: `{document_type}`
- slide_count: `{slide_count}`
- current_status: `{status}`
- ready_for_learning: `{ready}`
- required_actions: {actions}

검수자가 채워야 할 핵심 필드:

- `correction.reviewer`
- `correction.reviewed_at`
- `quality_baseline.overall_score`
- `quality_baseline.dimension_scores.*`
- `learning_labels.forbidden_terms_scan`
- `learning_labels.privacy_security_scan`
- `learning_labels.human_review_status`
- `learning_labels.accepted_for_learning`

승인할 때만 `accepted_for_learning=true`로 변경한다. 반려 또는 보완 필요이면 `accepted_for_learning=false`를 유지한다.""".format(
            artifact_id=row.get("artifact_id") or "-",
            path=row.get("path") or "-",
            workflow_id=row.get("report_workflow_id") or "-",
            document_type=row.get("document_type") or "-",
            slide_count=row.get("slide_count") if row.get("slide_count") is not None else "-",
            status=row.get("human_review_status") or "-",
            ready="yes" if row.get("ready_for_learning") else "no",
            actions=_action_text(list(row.get("required_actions") or [])),
        )
        for row in rows
    )

    return f"""# Report Quality Human Review Worksheet

- generated_at: `{manifest.get('generated_at', '-')}`
- pack_dir: `{manifest.get('pack_dir', '-')}`
- manifest_path: `{manifest.get('manifest_path', '-')}`
- source_bound: `{'yes' if source_manifest else 'no'}`
- source_manifest_sha256: `{source_manifest.get('sha256', '-')}`
- training_authorized: `false`
- artifact_count: `{counts.get('artifact_count', 0)}`
- ready_artifacts: `{counts.get('ready_artifacts', 0)}`
- pending_artifacts: `{counts.get('pending_artifacts', 0)}`

## Review Table

| artifact_id | workflow_id | domain | overall_score | review_status | ready | required_actions |
| --- | --- | --- | --- | --- | --- | --- |
{table}

## Review Rules

- 원본 첨부파일, base64, raw file bytes, secret, API key 값은 넣지 않는다.
- 학습 후보 승인 전까지 모든 `training_boundary.*` 값은 `false`로 유지한다.
- `overall_score`는 `{MIN_OVERALL_SCORE:.2f}` 이상이어야 한다.
- `export_readiness`는 `{MIN_EXPORT_READINESS_SCORE:.2f}` 이상이어야 한다.
- `visual_design`은 `{MIN_VISUAL_DESIGN_SCORE:.2f}` 이상이어야 한다.
- 다른 dimension score는 `{MIN_REQUIRED_DIMENSION_SCORE:.2f}` 이상이어야 한다.

## Per-Artifact Forms

{detail_sections}

## Validation Commands

```bash
python3 scripts/sync_report_quality_pilot_pack.py \\
  {manifest.get('pack_dir', '-')} \\
  --min-records {counts.get('artifact_count', 0)}

python3 scripts/sync_report_quality_pilot_pack.py \\
  {manifest.get('pack_dir', '-')} \\
  --min-records {counts.get('artifact_count', 0)} \\
  --require-ready
```

`--require-ready`는 사람이 승인 필드를 모두 채우기 전에는 실패하는 것이 정상이다.

## Side-Effect Boundary

- external_dataset_upload_started: `false`
- provider_fine_tune_api_called: `false`
- provider_job_created: `false`
- training_execution_started: `false`
- model_promotion_started: `false`
"""


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create a markdown worksheet for human review of Report Quality pilot drafts.",
    )
    parser.add_argument("pack_dir", type=Path, help="Path to reports/report-quality/<batch-id>.")
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--manifest", type=Path, default=None)
    parser.add_argument("--json", action="store_true", help="Print manifest JSON to stdout.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(list(argv) if argv is not None else None)
    try:
        manifest = create_report_quality_review_sheet(
            pack_dir=args.pack_dir,
            output_path=args.output,
            manifest_path=args.manifest,
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        counts = manifest["counts"]
        print("PASS report quality human review worksheet created")
        print(f"output_path={manifest['output_path']}")
        print(f"manifest_path={manifest['manifest_path']}")
        print(f"artifact_count={counts['artifact_count']}")
        print(f"ready_artifacts={counts['ready_artifacts']}")
        print(f"pending_artifacts={counts['pending_artifacts']}")
        print("training_boundary=not_authorized")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
