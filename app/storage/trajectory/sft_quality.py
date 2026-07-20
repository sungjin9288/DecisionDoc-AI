"""SFT export selection, record validation, and quality-report helpers."""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from app.storage.trajectory.redaction import _string_list


def _is_accepted(record: dict[str, Any]) -> bool:
    feedback = record.get("human_feedback") if isinstance(record.get("human_feedback"), dict) else {}
    return bool(feedback.get("accepted")) or record.get("human_review_status") in {"accepted", "approved"}


def _sft_export_blockers(record: dict[str, Any], *, accepted_only: bool) -> list[str]:
    blockers: list[str] = []
    if accepted_only and not _is_accepted(record):
        blockers.append("not_accepted")
    feedback = record.get("human_feedback") if isinstance(record.get("human_feedback"), dict) else {}
    reviewer = str(feedback.get("reviewer") or "").strip()
    if accepted_only and _is_accepted(record) and (not reviewer or reviewer.casefold() == "anonymous"):
        blockers.append("missing_reviewer")
    if not str(record.get("task_type") or "").strip():
        blockers.append("missing_task_type")
    skill = record.get("skill") if isinstance(record.get("skill"), dict) else {}
    if not str(skill.get("name") or "").strip() or str(skill.get("name")) == "unknown":
        blockers.append("missing_skill")
    if not record.get("plan"):
        blockers.append("missing_plan")
    if not (record.get("final_output") or record.get("draft_output") or record.get("draft")):
        blockers.append("missing_assistant_output")
    qa = record.get("qa") if isinstance(record.get("qa"), dict) else {}
    if qa.get("hard_gate_pass") is False:
        blockers.append("qa_hard_gate_failed")
    return blockers


def _record_preview(record: dict[str, Any], *, blockers: list[str]) -> dict[str, Any]:
    skill = record.get("skill") if isinstance(record.get("skill"), dict) else {}
    feedback = record.get("human_feedback") if isinstance(record.get("human_feedback"), dict) else {}
    qa = record.get("qa") if isinstance(record.get("qa"), dict) else {}
    return {
        "trajectory_id": record.get("trajectory_id"),
        "task_type": record.get("task_type"),
        "skill": skill.get("name"),
        "skill_version": skill.get("version"),
        "human_review_status": record.get("human_review_status"),
        "accepted": _is_accepted(record),
        "quality_score": feedback.get("quality_score"),
        "qa_hard_gate_pass": qa.get("hard_gate_pass"),
        "blockers": blockers,
    }


def _build_sft_quality_report(
    sft_records: list[dict[str, Any]],
    *,
    blocked_samples: list[dict[str, Any]],
    jsonl_parse_errors: list[dict[str, Any]] | None = None,
    sample_limit: int = 5,
) -> dict[str, Any]:
    parse_errors = jsonl_parse_errors or []
    invalid_samples: list[dict[str, Any]] = list(parse_errors[: max(0, sample_limit)])
    valid_count = 0
    role_sequences: dict[str, int] = {}
    qa_hard_pass = 0
    qa_hard_fail = 0
    qa_warning_count = 0
    qa_gate_issue_count = 0
    quality_scores: list[float] = []
    evidence = {
        "records_with_confirmed": 0,
        "records_with_assumptions": 0,
        "records_with_gaps": 0,
        "records_with_source_references": 0,
        "unsupported_confirmed_records": 0,
    }
    provenance = {
        "records_with_trajectory_id": 0,
        "records_with_skill_version": 0,
        "records_with_reviewer": 0,
        "records_with_review_version": 0,
        "records_with_reviewed_at": 0,
        "records_with_accepted_review": 0,
        "records_with_quality_score": 0,
        "complete_records": 0,
    }
    sample_records: list[dict[str, Any]] = []

    for index, record in enumerate(sft_records):
        provenance_flags = _provenance_flags(record.get("metadata"))
        for key, present in provenance_flags.items():
            if present:
                provenance[key] += 1
        if all(provenance_flags.values()):
            provenance["complete_records"] += 1

        validation = _validate_sft_record(record)
        role_key = ",".join(validation["roles"]) if validation["roles"] else "missing"
        role_sequences[role_key] = role_sequences.get(role_key, 0) + 1
        if validation["issues"]:
            if len(invalid_samples) < sample_limit:
                invalid_samples.append(
                    {
                        "index": index,
                        "issues": validation["issues"],
                        "metadata": record.get("metadata") if isinstance(record.get("metadata"), dict) else {},
                    }
                )
            continue

        valid_count += 1
        metadata = record["metadata"]
        assistant_payload = validation["assistant_payload"]
        qa = assistant_payload.get("qa") if isinstance(assistant_payload.get("qa"), dict) else {}
        if qa.get("hard_gate_pass") is False:
            qa_hard_fail += 1
        else:
            qa_hard_pass += 1
        qa_warning_count += len(_string_list(qa.get("warnings")))
        gate_issues = qa.get("gate_issues")
        if isinstance(gate_issues, list):
            qa_gate_issue_count += len(gate_issues)
        score = _metadata_quality_score(metadata)
        if score is not None:
            quality_scores.append(score)

        evidence_status = assistant_payload.get("evidence_status")
        evidence_status = evidence_status if isinstance(evidence_status, dict) else {}
        confirmed = _string_list(evidence_status.get("confirmed"))
        assumptions = _string_list(evidence_status.get("assumptions") or evidence_status.get("assumed"))
        gaps = _string_list(evidence_status.get("gaps") or evidence_status.get("todo") or evidence_status.get("open_questions"))
        sources = _string_list(evidence_status.get("source_references") or evidence_status.get("sources"))
        if confirmed:
            evidence["records_with_confirmed"] += 1
        if assumptions:
            evidence["records_with_assumptions"] += 1
        if gaps:
            evidence["records_with_gaps"] += 1
        if sources:
            evidence["records_with_source_references"] += 1
        if confirmed and not sources:
            evidence["unsupported_confirmed_records"] += 1
        if len(sample_records) < sample_limit:
            sample_records.append(
                {
                    "index": index,
                    "trajectory_id": metadata.get("trajectory_id"),
                    "task_type": metadata.get("task_type"),
                    "reviewer": metadata.get("reviewer"),
                    "review_version": metadata.get("review_version"),
                    "roles": validation["roles"],
                    "assistant_keys": sorted(assistant_payload.keys()),
                    "has_source_references": bool(sources),
                    "qa_hard_gate_pass": qa.get("hard_gate_pass"),
                }
            )

    invalid_count = len(sft_records) - valid_count + len(parse_errors)
    return {
        "jsonl_record_count": len(sft_records),
        "schema_valid_count": valid_count,
        "schema_invalid_count": invalid_count,
        "role_sequence_summary": role_sequences,
        "qa_summary": {
            "hard_gate_pass_count": qa_hard_pass,
            "hard_gate_fail_count": qa_hard_fail,
            "warning_count": qa_warning_count,
            "gate_issue_count": qa_gate_issue_count,
            "quality_score_summary": _score_summary(quality_scores),
        },
        "evidence_coverage": {
            **evidence,
            "source_reference_coverage": _coverage_ratio(evidence["records_with_source_references"], valid_count),
            "confirmed_coverage": _coverage_ratio(evidence["records_with_confirmed"], valid_count),
        },
        "provenance_coverage": {
            **provenance,
            "complete_rate": _coverage_ratio(provenance["complete_records"], len(sft_records)),
        },
        "invalid_samples": invalid_samples,
        "blocked_samples": blocked_samples[: max(0, sample_limit)],
        "sample_records": sample_records,
    }


def _validate_sft_record(record: dict[str, Any]) -> dict[str, Any]:
    issues: list[str] = []
    messages = record.get("messages")
    roles: list[str] = []
    user_payload: dict[str, Any] = {}
    assistant_payload: dict[str, Any] = {}
    if not isinstance(messages, list):
        return {
            "issues": ["missing_messages"],
            "roles": roles,
            "user_payload": user_payload,
            "assistant_payload": assistant_payload,
        }
    for message in messages:
        role = message.get("role") if isinstance(message, dict) else None
        roles.append(str(role or "missing"))
    if roles != ["system", "user", "assistant"]:
        issues.append("invalid_role_sequence")
    if len(messages) != 3:
        issues.append("invalid_message_count")
    for index, message in enumerate(messages):
        if not isinstance(message, dict):
            issues.append(f"message_{index}_not_object")
            continue
        if not str(message.get("content") or "").strip():
            issues.append(f"message_{index}_missing_content")

    user = messages[1] if len(messages) >= 2 and isinstance(messages[1], dict) else {}
    try:
        parsed_user = json.loads(str(user.get("content") or ""))
    except json.JSONDecodeError:
        issues.append("user_content_not_json")
        parsed_user = {}
    if isinstance(parsed_user, dict):
        user_payload = parsed_user
    else:
        issues.append("user_content_not_object")
    if not str(user_payload.get("task_type") or "").strip():
        issues.append("user_missing_task_type")
    if not isinstance(user_payload.get("input"), dict):
        issues.append("user_missing_input")
    if not isinstance(user_payload.get("source_references"), list):
        issues.append("user_missing_source_references")

    assistant = messages[2] if len(messages) >= 3 and isinstance(messages[2], dict) else {}
    try:
        parsed = json.loads(str(assistant.get("content") or ""))
    except json.JSONDecodeError:
        issues.append("assistant_content_not_json")
        parsed = {}
    if isinstance(parsed, dict):
        assistant_payload = parsed
    else:
        issues.append("assistant_content_not_object")
    if not _string_list(assistant_payload.get("plan")):
        issues.append("assistant_missing_plan")
    if not str(assistant_payload.get("draft") or "").strip():
        issues.append("assistant_missing_draft")
    if not isinstance(assistant_payload.get("evidence_status"), dict):
        issues.append("assistant_missing_evidence_status")
    if not isinstance(assistant_payload.get("qa"), dict):
        issues.append("assistant_missing_qa")
    elif assistant_payload["qa"].get("hard_gate_pass") is not True:
        issues.append("assistant_qa_hard_gate_not_passed")

    metadata = record.get("metadata")
    if not isinstance(metadata, dict):
        issues.append("missing_metadata")
    else:
        if not str(metadata.get("trajectory_id") or "").strip():
            issues.append("metadata_missing_trajectory_id")
        if not str(metadata.get("skill_version") or "").strip() or metadata.get("skill_version") == "unknown":
            issues.append("metadata_missing_skill_version")
        reviewer = str(metadata.get("reviewer") or "").strip()
        if not reviewer or reviewer.casefold() == "anonymous":
            issues.append("metadata_missing_reviewer")
        review_version = metadata.get("review_version")
        if isinstance(review_version, bool) or not isinstance(review_version, int) or review_version < 1:
            issues.append("metadata_invalid_review_version")
        if not _is_iso_datetime(metadata.get("reviewed_at")):
            issues.append("metadata_invalid_reviewed_at")
        if metadata.get("human_review_status") not in {"accepted", "approved"}:
            issues.append("metadata_review_not_accepted")
        if str(metadata.get("task_type") or "") != str(user_payload.get("task_type") or ""):
            issues.append("metadata_task_type_mismatch")
        quality_score = _metadata_quality_score(metadata)
        if quality_score is None or not 0.0 <= quality_score <= 1.0:
            issues.append("metadata_invalid_quality_score")
    return {
        "issues": issues,
        "roles": roles,
        "user_payload": user_payload,
        "assistant_payload": assistant_payload,
    }


def _metadata_quality_score(metadata: Any) -> float | None:
    if not isinstance(metadata, dict):
        return None
    raw = metadata.get("quality_score")
    if raw is None or isinstance(raw, bool):
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _blocker_summary(blocked: list[dict[str, Any]]) -> dict[str, int]:
    summary: dict[str, int] = {}
    for item in blocked:
        for blocker in item.get("blockers", []):
            label = str(blocker)
            summary[label] = summary.get(label, 0) + 1
    return summary


def _coverage_ratio(count: int, total: int) -> float:
    if total <= 0:
        return 0.0
    return round(count / total, 3)


def _quality_recommendations(report: dict[str, Any]) -> list[str]:
    recommendations: list[str] = []
    if report.get("schema_invalid_count"):
        recommendations.append("fix_invalid_sft_schema_before_training")
    if report.get("blocked_count"):
        recommendations.append("review_or_reject_blocked_trajectories_before_dataset_freeze")
    evidence = report.get("evidence_coverage") if isinstance(report.get("evidence_coverage"), dict) else {}
    if evidence.get("unsupported_confirmed_records"):
        recommendations.append("add_source_references_for_confirmed_claims")
    provenance = report.get("provenance_coverage") if isinstance(report.get("provenance_coverage"), dict) else {}
    if provenance.get("complete_records", 0) < report.get("jsonl_record_count", 0):
        recommendations.append("restore_review_provenance_before_training")
    if (
        report.get("content_sha256_matches_metadata") is False
        or report.get("size_bytes_matches_metadata") is False
    ):
        recommendations.append("regenerate_export_after_integrity_check")
    if report.get("eligible_count") == 0 or report.get("jsonl_record_count") == 0:
        recommendations.append("collect_reviewed_accepted_trajectories")
    return recommendations


def _provenance_flags(metadata: Any) -> dict[str, bool]:
    metadata = metadata if isinstance(metadata, dict) else {}
    reviewer = str(metadata.get("reviewer") or "").strip()
    review_version = metadata.get("review_version")
    quality_score = _metadata_quality_score(metadata)
    return {
        "records_with_trajectory_id": bool(str(metadata.get("trajectory_id") or "").strip()),
        "records_with_skill_version": bool(
            str(metadata.get("skill_version") or "").strip() and metadata.get("skill_version") != "unknown"
        ),
        "records_with_reviewer": bool(reviewer and reviewer.casefold() != "anonymous"),
        "records_with_review_version": bool(
            not isinstance(review_version, bool) and isinstance(review_version, int) and review_version >= 1
        ),
        "records_with_reviewed_at": _is_iso_datetime(metadata.get("reviewed_at")),
        "records_with_accepted_review": metadata.get("human_review_status") in {"accepted", "approved"},
        "records_with_quality_score": bool(quality_score is not None and 0.0 <= quality_score <= 1.0),
    }


def _is_iso_datetime(value: Any) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None


def _source_references(record: dict[str, Any]) -> list[Any]:
    direct = record.get("source_references")
    if isinstance(direct, list):
        return direct
    input_payload = record.get("input") if isinstance(record.get("input"), dict) else {}
    nested = input_payload.get("source_references")
    return nested if isinstance(nested, list) else []


def _quality_score(record: dict[str, Any]) -> float | None:
    feedback = record.get("human_feedback") if isinstance(record.get("human_feedback"), dict) else {}
    raw = feedback.get("quality_score")
    if raw is None:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _score_summary(scores: list[float]) -> dict[str, Any]:
    if not scores:
        return {"count": 0, "min": None, "max": None, "avg": None}
    return {
        "count": len(scores),
        "min": round(min(scores), 3),
        "max": round(max(scores), 3),
        "avg": round(sum(scores) / len(scores), 3),
    }


def _count_by(records: list[dict[str, Any]], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for record in records:
        label = str(record.get(key) or "unknown")
        counts[label] = counts.get(label, 0) + 1
    return counts


def _skill_counts(records: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for record in records:
        skill = record.get("skill") if isinstance(record.get("skill"), dict) else {}
        label = str(skill.get("name") or "unknown")
        counts[label] = counts.get(label, 0) + 1
    return counts
