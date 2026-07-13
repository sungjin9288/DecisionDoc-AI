#!/usr/bin/env python3
"""Apply human review decisions to Report Quality pilot draft artifacts."""
from __future__ import annotations

import argparse
import hashlib
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
    REQUIRED_DIMENSIONS,
    validate_correction_artifact,
)
from scripts.report_quality_pilot_pack_provenance import (  # noqa: E402
    load_pilot_pack,
    require_current_pack_binding,
)


ALLOWED_DECISIONS = {"pending", "accepted", "changes_requested", "rejected"}
ALLOWED_SCAN_VALUES = {"not_run", "pass", "fail"}
APPLICATION_RECEIPT_SCHEMA = "decisiondoc_report_quality_review_decision_application_receipt.v1"


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


def _load_json_snapshot(path: Path) -> tuple[dict[str, Any], str]:
    content = path.read_bytes()
    payload = json.loads(content.decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path}: JSON root must be an object")
    return payload, hashlib.sha256(content).hexdigest()


def _resolve_receipt_path(pack_dir: Path, receipt_path: Path | None) -> Path | None:
    if receipt_path is None:
        return None
    expanded = receipt_path.expanduser()
    if expanded.is_symlink():
        raise ValueError("symlink receipt files are not allowed")
    resolved = expanded.resolve()
    if resolved.parent != pack_dir:
        raise ValueError("receipt must be written directly inside the pilot pack directory")
    if resolved.exists() or resolved.is_symlink():
        raise ValueError(f"refusing to overwrite existing receipt: {resolved}")
    return resolved


def _decision_items(payload: dict[str, Any]) -> list[dict[str, Any]]:
    raw = payload.get("decisions", payload.get("artifacts"))
    if raw is None and "artifact_id" in payload:
        raw = [payload]
    if not isinstance(raw, list):
        raise ValueError("decision file must contain a decisions array")
    decisions: list[dict[str, Any]] = []
    for index, item in enumerate(raw):
        if not isinstance(item, dict):
            raise ValueError(f"decisions[{index}] must be an object")
        decisions.append(item)
    if not decisions:
        raise ValueError("decision file contains no decisions")
    return decisions


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _validate_decision(item: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    artifact_id = str(item.get("artifact_id") or "").strip()
    decision = str(item.get("decision") or "").strip()
    if not artifact_id:
        errors.append("artifact_id must be non-empty")
    if decision not in ALLOWED_DECISIONS:
        errors.append(f"decision must be one of {sorted(ALLOWED_DECISIONS)}")

    if "overall_score" in item and item.get("overall_score") is not None and _score(item.get("overall_score")) is None:
        errors.append("overall_score must be a number between 0.0 and 1.0")
    dimension_scores = item.get("dimension_scores")
    if dimension_scores is not None:
        if not isinstance(dimension_scores, dict):
            errors.append("dimension_scores must be an object")
        else:
            for dimension, value in dimension_scores.items():
                if dimension not in REQUIRED_DIMENSIONS:
                    errors.append(f"unsupported dimension_scores key: {dimension}")
                elif value is None and decision != "accepted":
                    continue
                elif _score(value) is None:
                    errors.append(f"dimension_scores.{dimension} must be a number between 0.0 and 1.0")
    for scan_key in ("forbidden_terms_scan", "privacy_security_scan"):
        if scan_key in item:
            scan_value = str(item.get(scan_key) or "").strip()
            if scan_value not in ALLOWED_SCAN_VALUES:
                errors.append(f"{scan_key} must be one of {sorted(ALLOWED_SCAN_VALUES)}")

    if decision == "accepted":
        if not str(item.get("reviewer") or "").strip():
            errors.append("accepted decision requires reviewer")
        if not str(item.get("reviewed_at") or "").strip():
            errors.append("accepted decision requires reviewed_at")
        if item.get("forbidden_terms_scan") != "pass":
            errors.append("accepted decision requires forbidden_terms_scan=pass")
        if item.get("privacy_security_scan") != "pass":
            errors.append("accepted decision requires privacy_security_scan=pass")
        if _score(item.get("overall_score")) is None:
            errors.append("accepted decision requires overall_score")
        if not isinstance(dimension_scores, dict):
            errors.append("accepted decision requires dimension_scores")
        else:
            missing_dimensions = [dimension for dimension in REQUIRED_DIMENSIONS if dimension not in dimension_scores]
            if missing_dimensions:
                errors.append(f"accepted decision missing dimension_scores: {', '.join(missing_dimensions)}")
    return errors


def _apply_decision(payload: dict[str, Any], decision: dict[str, Any]) -> dict[str, Any]:
    human_decision = str(decision["decision"]).strip()
    correction = payload.setdefault("correction", {})
    quality = payload.setdefault("quality_baseline", {})
    labels = payload.setdefault("learning_labels", {})

    if decision.get("reviewer") is not None:
        correction["reviewer"] = str(decision.get("reviewer") or "").strip()
    if decision.get("reviewed_at") is not None:
        correction["reviewed_at"] = str(decision.get("reviewed_at") or "").strip()
    if decision.get("change_requests") is not None:
        correction["change_requests"] = list(_as_list(decision.get("change_requests")))
    if isinstance(decision.get("rationale_by_dimension"), dict):
        rationale = correction.setdefault("rationale_by_dimension", {})
        for dimension in REQUIRED_DIMENSIONS:
            if dimension in decision["rationale_by_dimension"]:
                rationale[dimension] = str(decision["rationale_by_dimension"][dimension])

    if decision.get("overall_score") is not None:
        quality["overall_score"] = float(decision["overall_score"])
    if decision.get("hard_failures") is not None:
        quality["hard_failures"] = list(_as_list(decision.get("hard_failures")))
    if isinstance(decision.get("dimension_scores"), dict):
        scores = quality.setdefault("dimension_scores", {})
        for dimension in REQUIRED_DIMENSIONS:
            if dimension in decision["dimension_scores"] and decision["dimension_scores"][dimension] is not None:
                scores[dimension] = float(decision["dimension_scores"][dimension])

    labels["accepted_for_learning"] = human_decision == "accepted"
    labels["human_review_status"] = human_decision
    if decision.get("forbidden_terms_scan") is not None:
        labels["forbidden_terms_scan"] = str(decision["forbidden_terms_scan"]).strip()
    if decision.get("privacy_security_scan") is not None:
        labels["privacy_security_scan"] = str(decision["privacy_security_scan"]).strip()
    for key in ("confirmed_claims", "assumed_claims", "todo_claims", "task_types", "skills"):
        if decision.get(key) is not None:
            labels[key] = _string_list(decision.get(key))
    return payload


def create_review_decision_template(*, pack_dir: Path, output_path: Path) -> dict[str, Any]:
    resolved_pack_dir = pack_dir.expanduser().resolve()
    resolved_output_path = output_path.expanduser().resolve()
    snapshot = load_pilot_pack(resolved_pack_dir)
    decisions: list[dict[str, Any]] = []
    for draft in snapshot.drafts:
        payload = draft.payload
        workflow = _as_dict(payload.get("workflow_reference"))
        profile = _as_dict(payload.get("document_profile"))
        quality = _as_dict(payload.get("quality_baseline"))
        correction = _as_dict(payload.get("correction"))
        labels = _as_dict(payload.get("learning_labels"))
        current_decision = str(labels.get("human_review_status") or "pending").strip()
        if current_decision not in ALLOWED_DECISIONS:
            current_decision = "pending"
        current_scores = _as_dict(quality.get("dimension_scores"))
        decisions.append({
            "artifact_id": draft.artifact_id,
            "report_workflow_id": workflow.get("report_workflow_id", ""),
            "domain": profile.get("domain", ""),
            "decision": current_decision,
            "reviewer": correction.get("reviewer", ""),
            "reviewed_at": correction.get("reviewed_at", ""),
            "overall_score": quality.get("overall_score"),
            "dimension_scores": {
                dimension: current_scores.get(dimension)
                for dimension in REQUIRED_DIMENSIONS
            },
            "hard_failures": list(_as_list(quality.get("hard_failures"))),
            "forbidden_terms_scan": labels.get("forbidden_terms_scan", "not_run"),
            "privacy_security_scan": labels.get("privacy_security_scan", "not_run"),
            "confirmed_claims": list(_as_list(labels.get("confirmed_claims"))),
            "assumed_claims": list(_as_list(labels.get("assumed_claims"))),
            "todo_claims": list(_as_list(labels.get("todo_claims"))),
            "change_requests": list(_as_list(correction.get("change_requests"))),
            "rationale_by_dimension": {
                dimension: _as_dict(correction.get("rationale_by_dimension")).get(dimension, "")
                for dimension in REQUIRED_DIMENSIONS
            },
        })
    template = {
        "report_type": "report_quality_human_review_decision_template",
        "schema_version": "decisiondoc_report_quality_human_review_decisions.v1",
        "created_at": _now_iso(),
        "pack_dir": str(resolved_pack_dir),
        "pack_binding": snapshot.binding(),
        "training_authorized": False,
        "instructions": [
            "accepted로 변경할 때만 accepted_for_learning=true가 적용됩니다.",
            "accepted decision은 reviewer, reviewed_at, overall_score, 모든 dimension_scores, scan pass가 필요합니다.",
            "changes_requested/rejected/pending은 accepted_for_learning=false를 유지합니다.",
            "training_boundary 값은 이 helper가 변경하지 않습니다.",
            "pack_binding이 현재 source manifest와 draft SHA-256에 맞아야 적용됩니다.",
        ],
        "decisions": decisions,
    }
    _write_text_atomic(
        resolved_output_path,
        json.dumps(template, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )
    return {
        "report_type": "report_quality_review_decision_template_created",
        "ok": True,
        "pack_dir": str(resolved_pack_dir),
        "output_path": str(resolved_output_path),
        "artifact_count": len(decisions),
        "source_bound": snapshot.source_order_applied,
        "side_effect_boundary": {
            "reads_local_draft_json": True,
            "writes_decision_template": True,
            "external_dataset_upload_started": False,
            "provider_fine_tune_api_called": False,
            "provider_job_created": False,
            "training_execution_started": False,
            "model_promotion_started": False,
        },
    }


def _write_application_receipt(
    *,
    receipt_path: Path,
    decisions_path: Path,
    decisions_sha256: str,
    decision_file: dict[str, Any],
    before_binding: dict[str, Any],
    after_binding: dict[str, Any],
    rows: list[dict[str, Any]],
    require_ready: bool,
) -> str:
    if receipt_path.exists() or receipt_path.is_symlink():
        raise ValueError(f"refusing to overwrite existing receipt: {receipt_path}")
    before_hashes = {
        item["artifact_id"]: item["draft_sha256"]
        for item in before_binding["artifacts"]
    }
    after_hashes = {
        item["artifact_id"]: item["draft_sha256"]
        for item in after_binding["artifacts"]
    }
    transitions = [
        {
            "artifact_id": row["artifact_id"],
            "decision": row["decision"],
            "ready_for_learning": row["ready_for_learning"],
            "before_draft_sha256": before_hashes[row["artifact_id"]],
            "after_draft_sha256": after_hashes[row["artifact_id"]],
            "changed": before_hashes[row["artifact_id"]] != after_hashes[row["artifact_id"]],
        }
        for row in rows
    ]
    receipt = {
        "report_type": "report_quality_review_decision_application_receipt",
        "schema_version": APPLICATION_RECEIPT_SCHEMA,
        "created_at": _now_iso(),
        "receipt_path": receipt_path.name,
        "pack_dir": str(receipt_path.parent),
        "decision_file": {
            "path": decisions_path.name,
            "sha256": decisions_sha256,
            "pack_binding_present": isinstance(decision_file.get("pack_binding"), dict),
        },
        "operation": {
            "ok": True,
            "dry_run": False,
            "require_ready": require_ready,
            "decision_count": len(rows),
            "applied_count": len(rows),
        },
        "pack_binding_before": before_binding,
        "pack_binding_after": after_binding,
        "artifacts": transitions,
        "side_effect_boundary": {
            "reads_local_draft_json": True,
            "reads_local_decision_json": True,
            "writes_local_draft_json": True,
            "writes_local_application_receipt": True,
            "external_dataset_upload_started": False,
            "provider_fine_tune_api_called": False,
            "provider_job_created": False,
            "training_execution_started": False,
            "model_promotion_started": False,
        },
    }
    _write_text_atomic(
        receipt_path,
        json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )
    return hashlib.sha256(receipt_path.read_bytes()).hexdigest()


def apply_review_decisions(
    *,
    pack_dir: Path,
    decisions_path: Path,
    dry_run: bool = False,
    require_ready: bool = False,
    receipt_path: Path | None = None,
) -> dict[str, Any]:
    resolved_pack_dir = pack_dir.expanduser().resolve()
    expanded_decisions_path = decisions_path.expanduser()
    if expanded_decisions_path.is_symlink():
        raise ValueError("symlink decision files are not allowed")
    resolved_decisions_path = expanded_decisions_path.resolve()
    resolved_receipt_path = _resolve_receipt_path(resolved_pack_dir, receipt_path)
    if resolved_receipt_path is not None:
        if dry_run:
            raise ValueError("receipt cannot be written during dry-run")
        if resolved_decisions_path.parent != resolved_pack_dir:
            raise ValueError("receipt-backed decision file must be inside the pilot pack directory")
        if resolved_decisions_path == resolved_receipt_path:
            raise ValueError("decision file and receipt path must be different")
    snapshot = load_pilot_pack(resolved_pack_dir)
    before_binding = snapshot.binding()
    draft_map = {draft.artifact_id: draft for draft in snapshot.drafts}
    decision_file, decisions_sha256 = _load_json_snapshot(resolved_decisions_path)
    pack_binding = decision_file.get("pack_binding")
    if snapshot.source_order_applied or pack_binding is not None:
        require_current_pack_binding(snapshot, pack_binding)
    raw_decisions = _decision_items(decision_file)

    rows: list[dict[str, Any]] = []
    errors: list[str] = []
    prepared: list[tuple[dict[str, Any], Path, dict[str, Any]]] = []
    seen_artifact_ids: set[str] = set()
    for index, decision in enumerate(raw_decisions):
        artifact_id = str(decision.get("artifact_id") or "").strip()
        decision_errors = _validate_decision(decision)
        if artifact_id and artifact_id not in draft_map:
            decision_errors.append(f"artifact_id not found in drafts: {artifact_id}")
        if artifact_id in seen_artifact_ids:
            decision_errors.append(f"duplicate artifact_id in decisions: {artifact_id}")
        if artifact_id:
            seen_artifact_ids.add(artifact_id)
        if decision_errors:
            errors.extend(f"decisions[{index}] {error}" for error in decision_errors)
            rows.append({
                "artifact_id": artifact_id,
                "applied": False,
                "ready_for_learning": False,
                "errors": decision_errors,
            })
            continue

        item = draft_map[artifact_id]
        next_payload = json.loads(json.dumps(item.payload, ensure_ascii=False))
        _apply_decision(next_payload, decision)
        validation = validate_correction_artifact(next_payload)
        validation_errors = list(validation.get("errors") or [])
        if validation_errors:
            errors.extend(f"{artifact_id}: {error}" for error in validation_errors)
        if require_ready and not validation.get("ready_for_learning"):
            errors.append(f"{artifact_id}: not ready_for_learning")
        row = {
            "artifact_id": artifact_id,
            "decision": decision["decision"],
            "path": str(item.path),
            "applied": False,
            "dry_run": dry_run,
            "validation_ok": bool(validation.get("ok")),
            "ready_for_learning": bool(validation.get("ready_for_learning")),
            "validation_errors": validation_errors,
            "validation_warnings": list(validation.get("warnings") or []),
        }
        rows.append(row)
        if not validation_errors and (not require_ready or validation.get("ready_for_learning")):
            prepared.append((row, item.path, next_payload))

    ok = not errors
    if ok and not dry_run:
        _, current_decisions_sha256 = _load_json_snapshot(resolved_decisions_path)
        if current_decisions_sha256 != decisions_sha256:
            raise ValueError("decision file changed during validation")
        if snapshot.source_order_applied or pack_binding is not None:
            current_snapshot = load_pilot_pack(resolved_pack_dir)
            require_current_pack_binding(current_snapshot, pack_binding)
        for row, path, next_payload in prepared:
            _write_text_atomic(
                path,
                json.dumps(next_payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            )
            row["applied"] = True

    applied_count = sum(1 for row in rows if row.get("applied"))
    ready_count = sum(1 for row in rows if row.get("ready_for_learning"))
    receipt_sha256: str | None = None
    if ok and not dry_run and resolved_receipt_path is not None:
        after_snapshot = load_pilot_pack(resolved_pack_dir)
        receipt_sha256 = _write_application_receipt(
            receipt_path=resolved_receipt_path,
            decisions_path=resolved_decisions_path,
            decisions_sha256=decisions_sha256,
            decision_file=decision_file,
            before_binding=before_binding,
            after_binding=after_snapshot.binding(),
            rows=rows,
            require_ready=require_ready,
        )
    return {
        "report_type": "report_quality_review_decisions_applied",
        "ok": ok,
        "pack_dir": str(resolved_pack_dir),
        "decisions_path": str(resolved_decisions_path),
        "dry_run": dry_run,
        "require_ready": require_ready,
        "pack_binding_verified": snapshot.source_order_applied or pack_binding is not None,
        "receipt_path": str(resolved_receipt_path) if receipt_sha256 is not None else None,
        "receipt_sha256": receipt_sha256,
        "decision_count": len(rows),
        "applied_count": applied_count,
        "ready_decisions": ready_count,
        "not_ready_decisions": len(rows) - ready_count,
        "errors": errors,
        "decisions": rows,
        "side_effect_boundary": {
            "reads_local_draft_json": True,
            "reads_local_decision_json": True,
            "writes_local_draft_json": not dry_run and applied_count > 0,
            "writes_local_application_receipt": receipt_sha256 is not None,
            "external_dataset_upload_started": False,
            "provider_fine_tune_api_called": False,
            "provider_job_created": False,
            "training_execution_started": False,
            "model_promotion_started": False,
        },
    }


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create or apply human review decisions for Report Quality pilot drafts.",
    )
    parser.add_argument("pack_dir", type=Path, help="Path to reports/report-quality/<batch-id>.")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--create-template", type=Path, help="Write a review decision template JSON.")
    mode.add_argument("--decisions", type=Path, help="Apply decisions from this JSON file.")
    parser.add_argument("--dry-run", action="store_true", help="Validate decisions without writing drafts.")
    parser.add_argument("--require-ready", action="store_true", help="Fail unless applied decisions become ready.")
    parser.add_argument("--receipt", type=Path, default=None, help="Write a pack-local application receipt JSON.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable result.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(list(argv) if argv is not None else None)
    try:
        if args.create_template is not None:
            if args.receipt is not None:
                raise ValueError("--receipt can only be used with --decisions")
            result = create_review_decision_template(pack_dir=args.pack_dir, output_path=args.create_template)
        else:
            result = apply_review_decisions(
                pack_dir=args.pack_dir,
                decisions_path=args.decisions,
                dry_run=args.dry_run,
                require_ready=args.require_ready,
                receipt_path=args.receipt,
            )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    elif result["report_type"].endswith("template_created"):
        print("PASS report quality review decision template created")
        print(f"output_path={result['output_path']}")
        print(f"artifact_count={result['artifact_count']}")
        print("training_boundary=not_authorized")
    else:
        print(f"{'PASS' if result['ok'] else 'FAIL'} report quality review decisions applied")
        print(f"decisions_path={result['decisions_path']}")
        print(f"decision_count={result['decision_count']}")
        print(f"applied_count={result['applied_count']}")
        print(f"ready_decisions={result['ready_decisions']}")
        print(f"dry_run={result['dry_run']}")
        if result["receipt_path"]:
            print(f"receipt_path={result['receipt_path']}")
            print(f"receipt_sha256={result['receipt_sha256']}")
        print("training_boundary=not_authorized")
        for error in result["errors"]:
            print(f"ERROR {error}")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
