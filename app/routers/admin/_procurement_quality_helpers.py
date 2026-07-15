"""app/routers/admin/_procurement_quality_helpers.py — Procurement quality aggregation helpers.

Extracted from app/routers/admin.py (moved verbatim; no behavior changes).
Pure/utility helpers used by _procurement_quality.py's
`_build_procurement_quality_summary` and `_build_procurement_location_overview`.
Split out of _procurement_quality.py to keep each module under 800 lines.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime
import re

_PROCUREMENT_HANDOFF_BUNDLE_IDS = (
    "bid_decision_kr",
    "rfp_analysis_kr",
    "proposal_kr",
    "performance_plan_kr",
)
_PROCUREMENT_DOWNSTREAM_BUNDLE_IDS = (
    "rfp_analysis_kr",
    "proposal_kr",
    "performance_plan_kr",
)
_PROCUREMENT_ACTIVITY_ACTIONS = (
    "procurement.import",
    "procurement.evaluate",
    "procurement.recommend",
    "procurement.override_reason",
    "share.create",
    "share.view",
    "procurement.remediation_link_copied",
    "procurement.remediation_link_opened",
    "procurement.downstream_blocked",
    "procurement.downstream_resolved",
    "approval.create",
    "approval.submit",
    "approval.review",
    "approval.approve",
    "approval.reject",
)
_PROCUREMENT_OVERRIDE_CANDIDATE_VIEWS = {
    "latest_followup",
    "stale_unresolved",
}
_PROCUREMENT_OVERRIDE_CANDIDATE_SCOPES = {
    "all",
    "unresolved_only",
    "resolved_only",
    "monitor_only",
    "review_only",
}
_PROCUREMENT_OVERRIDE_CANDIDATE_STATUSES = (
    "needs_override_reason",
    "ready_to_retry",
    "resolved",
    "monitor",
)
_PROCUREMENT_HANDOFF_QUEUE_STATUSES = (
    "shared_not_opened",
    "opened_unresolved",
    "opened_resolved",
)
def _sorted_counts(counter: Counter[str]) -> dict[str, int]:
    return {
        key: value
        for key, value in sorted(counter.items(), key=lambda item: (-item[1], item[0]))
    }


def _extract_latest_override_reason(notes: str) -> dict[str, str] | None:
    if not notes.strip():
        return None
    matches = list(
        re.finditer(
            r"\[override_reason ts=(?P<timestamp>[^\s]+) actor=(?P<actor>[^\]]+)\]\n(?P<reason>.*?)\n\[/override_reason\]",
            notes,
            flags=re.DOTALL,
        )
    )
    if not matches:
        return None
    match = matches[-1]
    return {
        "timestamp": match.group("timestamp").strip(),
        "actor": match.group("actor").strip(),
        "reason": match.group("reason").strip(),
    }


def _parse_iso_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    normalized = str(value).strip()
    if not normalized:
        return None
    try:
        return datetime.fromisoformat(normalized.replace("Z", "+00:00"))
    except ValueError:
        return None


def _limit_procurement_recent_activity(
    recent_activity: list[dict[str, object]],
    *,
    focus_project_id: str = "",
    limit: int = 10,
) -> list[dict[str, object]]:
    if limit <= 0:
        return []
    limited = recent_activity[:limit]
    if (
        not focus_project_id
        or any(str(event.get("linked_project_id", "")) == focus_project_id for event in limited)
    ):
        return limited
    focused_event = next(
        (
            event
            for event in recent_activity
            if str(event.get("linked_project_id", "")) == focus_project_id
        ),
        None,
    )
    if focused_event is None:
        return limited
    return [
        *limited[: max(limit - 1, 0)],
        focused_event,
    ]


def _resolve_procurement_activity_link(
    entry: dict[str, object],
    *,
    decision_project_ids: set[str],
    procurement_approval_ids: set[str],
    approval_to_project_id: dict[str, str],
) -> tuple[str, str]:
    detail = entry.get("detail", {})
    resource_id = str(entry.get("resource_id", ""))
    detail_project_id = ""
    if isinstance(detail, dict):
        detail_project_id = str(detail.get("project_id", ""))

    linked_project_id = ""
    linked_approval_id = ""
    if resource_id in decision_project_ids:
        linked_project_id = resource_id
    elif detail_project_id in decision_project_ids:
        linked_project_id = detail_project_id
    elif resource_id in procurement_approval_ids:
        linked_approval_id = resource_id
        linked_project_id = approval_to_project_id.get(resource_id, "")
    return linked_project_id, linked_approval_id


def _build_procurement_recent_event(
    entry: dict[str, object],
    *,
    linked_project_id: str,
    linked_approval_id: str,
    project_map: dict[str, object],
) -> dict[str, object]:
    detail = entry.get("detail", {})
    linked_project = project_map.get(linked_project_id)
    linked_project_name = ""
    if linked_project is not None:
        linked_project_name = str(getattr(linked_project, "name", "") or "")
    return {
        "timestamp": entry.get("timestamp", ""),
        "action": str(entry.get("action", "")),
        "result": entry.get("result", ""),
        "resource_type": entry.get("resource_type", ""),
        "linked_project_id": linked_project_id,
        "linked_project_name": linked_project_name,
        "linked_approval_id": linked_approval_id or None,
        "error_code": detail.get("error_code") if isinstance(detail, dict) else None,
        "bundle_type": detail.get("bundle_type") if isinstance(detail, dict) else None,
        "recommendation": detail.get("recommendation") if isinstance(detail, dict) else None,
        "procurement_operation": (
            detail.get("procurement_operation") if isinstance(detail, dict) else None
        ),
        "procurement_context_kind": (
            detail.get("procurement_context_kind") if isinstance(detail, dict) else None
        ),
        "share_decision_council_document_status": (
            detail.get("share_decision_council_document_status") if isinstance(detail, dict) else None
        ),
        "share_decision_council_document_status_copy": (
            detail.get("share_decision_council_document_status_copy") if isinstance(detail, dict) else None
        ),
        "share_decision_council_document_status_summary": (
            detail.get("share_decision_council_document_status_summary") if isinstance(detail, dict) else None
        ),
        "share_project_document_id": (
            detail.get("share_project_document_id") if isinstance(detail, dict) else None
        ),
        "share_procurement_review_document_status": (
            detail.get("share_procurement_review_document_status")
            if isinstance(detail, dict)
            else None
        ),
        "share_procurement_review_document_status_copy": (
            detail.get("share_procurement_review_document_status_copy")
            if isinstance(detail, dict)
            else None
        ),
        "share_source_binding_status": (
            detail.get("share_source_binding_status") if isinstance(detail, dict) else None
        ),
        "share_post_share_source_changed": (
            detail.get("share_post_share_source_changed") if isinstance(detail, dict) else None
        ),
    }


def _resolve_procurement_stale_share_evidence(detail: object) -> dict[str, object]:
    if not isinstance(detail, dict):
        return {}
    if str(detail.get("bundle_type", "") or "").strip() not in {
        "bid_decision_kr",
        "proposal_kr",
    }:
        return {}

    binding_status = str(detail.get("share_source_binding_status", "") or "").strip()
    if binding_status in {"missing", "mismatch"}:
        return {
            "status": f"source_{binding_status}",
            "tone": "danger",
            "copy": (
                "공유 원본 문서 없음"
                if binding_status == "missing"
                else "공유 원본 연결 불일치"
            ),
            "summary": (
                "공유 링크가 참조한 프로젝트 문서를 현재 tenant에서 찾을 수 없습니다."
                if binding_status == "missing"
                else "공유 링크의 project, document, request, bundle 연결을 다시 확인해야 합니다."
            ),
        }

    council_status = str(
        detail.get("share_decision_council_document_status", "") or ""
    ).strip()
    if council_status and council_status != "current":
        return {
            "status": council_status,
            "tone": str(
                detail.get("share_decision_council_document_status_tone", "") or ""
            ).strip(),
            "copy": str(
                detail.get("share_decision_council_document_status_copy", "") or ""
            ).strip(),
            "summary": str(
                detail.get("share_decision_council_document_status_summary", "") or ""
            ).strip(),
        }

    review_status = str(
        detail.get("share_procurement_review_document_status", "") or ""
    ).strip()
    if review_status and review_status != "current":
        return {
            "status": review_status,
            "tone": str(
                detail.get("share_procurement_review_document_status_tone", "") or ""
            ).strip(),
            "copy": str(
                detail.get("share_procurement_review_document_status_copy", "") or ""
            ).strip(),
            "summary": str(
                detail.get("share_procurement_review_document_status_summary", "") or ""
            ).strip(),
        }

    if detail.get("share_post_share_source_changed") is True:
        return {
            "status": "source_changed",
            "tone": "danger",
            "copy": "공유 이후 원본 상태 변경",
            "summary": "공유 링크 생성 이후 현재 원본 기준이 달라졌습니다.",
        }
    return {}


def _is_procurement_stale_share_activity(detail: object) -> bool:
    return bool(_resolve_procurement_stale_share_evidence(detail))


def _record_procurement_share_activity(
    events_by_key: dict[tuple[str, str, str], dict[str, object]],
    *,
    linked_project_id: str,
    entry: dict[str, object],
) -> None:
    detail = entry.get("detail", {})
    key = _build_procurement_stale_share_queue_key(
        linked_project_id=linked_project_id,
        detail=detail,
    )
    state = events_by_key.setdefault(
        key,
        {
            "latest": None,
            "latest_create": None,
            "latest_by_share_id": {},
            "create_by_share_id": {},
            "risk_seen_share_ids": set(),
        },
    )
    state["latest"] = _pick_newer_audit_entry(
        state.get("latest"),
        entry,
    ) or entry
    if str(entry.get("action", "")) == "share.create":
        state["latest_create"] = _pick_newer_audit_entry(
            state.get("latest_create"),
            entry,
        ) or entry
    share_id = str(entry.get("resource_id", "") or "").strip()
    if share_id:
        latest_by_share_id = state.setdefault("latest_by_share_id", {})
        if isinstance(latest_by_share_id, dict):
            latest_by_share_id[share_id] = _pick_newer_audit_entry(
                latest_by_share_id.get(share_id),
                entry,
            ) or entry
        if _is_procurement_stale_share_activity(detail):
            risk_seen_share_ids = state.setdefault("risk_seen_share_ids", set())
            if isinstance(risk_seen_share_ids, set):
                risk_seen_share_ids.add(share_id)
        if str(entry.get("action", "")) == "share.create":
            create_by_share_id = state.setdefault("create_by_share_id", {})
            if isinstance(create_by_share_id, dict):
                create_by_share_id[share_id] = _pick_newer_audit_entry(
                    create_by_share_id.get(share_id),
                    entry,
                ) or entry


def _pick_newer_audit_entry(
    left: dict[str, object] | None,
    right: dict[str, object] | None,
) -> dict[str, object] | None:
    if left is None:
        return right
    if right is None:
        return left
    if str(right.get("timestamp", "")) > str(left.get("timestamp", "")):
        return right
    return left


def _find_latest_procurement_project_entry(
    audit_store,
    *,
    project_id: str,
    actions: tuple[str, ...] | list[str] | set[str],
    decision_project_ids: set[str],
    procurement_approval_ids: set[str],
    approval_to_project_id: dict[str, str],
    result: str | None = None,
) -> tuple[dict[str, object] | None, str, str]:
    focus_resource_ids = {project_id}
    focus_resource_ids.update(
        approval_id
        for approval_id, linked_project_id in approval_to_project_id.items()
        if linked_project_id == project_id
    )
    latest_entry = _pick_newer_audit_entry(
        audit_store.find_latest_entry(
            actions=actions,
            resource_ids=focus_resource_ids,
            result=result,
        ),
        audit_store.find_latest_entry(
            actions=actions,
            detail_filters={"project_id": project_id},
            result=result,
        ),
    )
    if latest_entry is None:
        return None, "", ""
    linked_project_id, linked_approval_id = _resolve_procurement_activity_link(
        latest_entry,
        decision_project_ids=decision_project_ids,
        procurement_approval_ids=procurement_approval_ids,
        approval_to_project_id=approval_to_project_id,
    )
    if linked_project_id != project_id:
        return None, "", ""
    return latest_entry, linked_project_id, linked_approval_id


def _hydrate_procurement_followup_state(
    audit_store,
    *,
    project_id: str,
    current_state: dict[str, str] | None,
    decision_project_ids: set[str],
    procurement_approval_ids: set[str],
    approval_to_project_id: dict[str, str],
) -> dict[str, str]:
    followup_state = {
        "latest_blocked_at": str((current_state or {}).get("latest_blocked_at", "") or ""),
        "latest_blocked_bundle_type": str(
            (current_state or {}).get("latest_blocked_bundle_type", "") or ""
        ),
        "latest_blocked_error_code": str(
            (current_state or {}).get("latest_blocked_error_code", "") or ""
        ),
        "latest_override_reason_at": str(
            (current_state or {}).get("latest_override_reason_at", "") or ""
        ),
        "latest_resolved_at": str((current_state or {}).get("latest_resolved_at", "") or ""),
        "latest_resolved_bundle_type": str(
            (current_state or {}).get("latest_resolved_bundle_type", "") or ""
        ),
    }
    if not followup_state["latest_blocked_at"]:
        blocked_entry, _, _ = _find_latest_procurement_project_entry(
            audit_store,
            project_id=project_id,
            actions={"procurement.downstream_blocked"},
            decision_project_ids=decision_project_ids,
            procurement_approval_ids=procurement_approval_ids,
            approval_to_project_id=approval_to_project_id,
        )
        if blocked_entry is not None:
            blocked_detail = blocked_entry.get("detail", {})
            followup_state["latest_blocked_at"] = str(blocked_entry.get("timestamp", ""))
            if isinstance(blocked_detail, dict):
                followup_state["latest_blocked_bundle_type"] = str(
                    blocked_detail.get("bundle_type", "")
                )
                followup_state["latest_blocked_error_code"] = str(
                    blocked_detail.get("error_code", "")
                )
    if not followup_state["latest_resolved_at"]:
        resolved_entry, _, _ = _find_latest_procurement_project_entry(
            audit_store,
            project_id=project_id,
            actions={"procurement.downstream_resolved"},
            decision_project_ids=decision_project_ids,
            procurement_approval_ids=procurement_approval_ids,
            approval_to_project_id=approval_to_project_id,
        )
        if resolved_entry is not None:
            resolved_detail = resolved_entry.get("detail", {})
            followup_state["latest_resolved_at"] = str(resolved_entry.get("timestamp", ""))
            if isinstance(resolved_detail, dict):
                followup_state["latest_resolved_bundle_type"] = str(
                    resolved_detail.get("bundle_type", "")
                )
    if not followup_state["latest_override_reason_at"]:
        override_entry, _, _ = _find_latest_procurement_project_entry(
            audit_store,
            project_id=project_id,
            actions={"procurement.override_reason"},
            decision_project_ids=decision_project_ids,
            procurement_approval_ids=procurement_approval_ids,
            approval_to_project_id=approval_to_project_id,
        )
        if override_entry is not None:
            followup_state["latest_override_reason_at"] = str(override_entry.get("timestamp", ""))
    return followup_state


def _resolve_procurement_remediation_status(
    *,
    followup_state: dict[str, str],
    latest_override_reason: dict[str, str] | None,
    default_status: str = "monitor",
) -> str:
    blocked_dt = _parse_iso_datetime(followup_state.get("latest_blocked_at"))
    resolved_dt = _parse_iso_datetime(followup_state.get("latest_resolved_at"))
    override_note_dt = _parse_iso_datetime(
        latest_override_reason.get("timestamp") if latest_override_reason else None
    )
    override_audit_dt = _parse_iso_datetime(followup_state.get("latest_override_reason_at"))
    override_dt = override_audit_dt or override_note_dt

    remediation_status = default_status
    if resolved_dt is not None and (blocked_dt is None or resolved_dt >= blocked_dt):
        remediation_status = "resolved"
    elif blocked_dt is not None and override_dt is not None and override_dt >= blocked_dt:
        remediation_status = "ready_to_retry"
    elif blocked_dt is not None:
        remediation_status = "needs_override_reason"
    return remediation_status


def _resolve_procurement_followup_reference(
    *,
    remediation_status: str,
    followup_state: dict[str, str],
    latest_override_reason: dict[str, str] | None,
    latest_event_timestamp: str = "",
) -> tuple[str | None, str]:
    latest_override_at = (
        str(followup_state.get("latest_override_reason_at", "") or "")
        or str(latest_override_reason.get("timestamp", "") if latest_override_reason else "")
    )
    latest_blocked_at = str(followup_state.get("latest_blocked_at", "") or "")
    latest_resolved_at = str(followup_state.get("latest_resolved_at", "") or "")

    if remediation_status == "needs_override_reason":
        return latest_blocked_at or None, "blocked"
    if remediation_status == "ready_to_retry":
        return latest_override_at or latest_blocked_at or None, "override_saved"
    if remediation_status == "resolved":
        return latest_resolved_at or latest_blocked_at or latest_override_at or None, "resolved"
    return (
        latest_resolved_at or latest_blocked_at or latest_override_at or latest_event_timestamp or None,
        "activity",
    )


def _sort_procurement_override_candidate(candidate: dict[str, object]) -> tuple[object, ...]:
    status_rank = {
        "needs_override_reason": 0,
        "ready_to_retry": 1,
        "resolved": 2,
        "monitor": 3,
    }.get(str(candidate.get("remediation_status", "")), 4)
    followup_dt = _parse_iso_datetime(str(candidate.get("followup_updated_at") or ""))
    followup_rank = -(followup_dt.timestamp()) if followup_dt is not None else float("inf")
    return (
        status_rank,
        followup_rank,
        str(candidate.get("project_name", "") or candidate.get("project_id", "")),
    )


def _normalize_procurement_override_candidate_view(view: str | None) -> str:
    normalized = str(view or "").strip()
    if normalized in _PROCUREMENT_OVERRIDE_CANDIDATE_VIEWS:
        return normalized
    return "latest_followup"


def _normalize_procurement_override_candidate_scope(scope: str | None) -> str:
    normalized = str(scope or "").strip()
    if normalized in _PROCUREMENT_OVERRIDE_CANDIDATE_SCOPES:
        return normalized
    return "all"


def _normalize_procurement_override_candidate_statuses(
    statuses: str | list[str] | tuple[str, ...] | set[str] | None,
) -> tuple[str, ...]:
    if statuses is None:
        return ()
    if isinstance(statuses, str):
        requested = {part.strip() for part in statuses.split(",") if part.strip()}
    else:
        requested = {str(part).strip() for part in statuses if str(part).strip()}
    return tuple(
        status for status in _PROCUREMENT_OVERRIDE_CANDIDATE_STATUSES if status in requested
    )


def _normalize_procurement_activity_actions(
    actions: str | list[str] | tuple[str, ...] | set[str] | None,
) -> tuple[str, ...]:
    if actions is None:
        return ()
    if isinstance(actions, str):
        requested = {part.strip() for part in actions.split(",") if part.strip()}
    else:
        requested = {str(part).strip() for part in actions if str(part).strip()}
    return tuple(action for action in _PROCUREMENT_ACTIVITY_ACTIONS if action in requested)


def _is_procurement_unresolved_candidate(candidate: dict[str, object]) -> bool:
    return str(candidate.get("remediation_status", "")) in {
        "needs_override_reason",
        "ready_to_retry",
    }


def _is_procurement_resolved_candidate(candidate: dict[str, object]) -> bool:
    return str(candidate.get("remediation_status", "")) == "resolved"


def _is_procurement_monitor_candidate(candidate: dict[str, object]) -> bool:
    return str(candidate.get("remediation_status", "")) == "monitor"


def _is_procurement_review_candidate(candidate: dict[str, object]) -> bool:
    return _is_procurement_resolved_candidate(candidate) or _is_procurement_monitor_candidate(candidate)


def _is_procurement_candidate_visible_for_scope(
    candidate: dict[str, object],
    scope: str,
) -> bool:
    if scope == "unresolved_only":
        return _is_procurement_unresolved_candidate(candidate)
    if scope == "resolved_only":
        return _is_procurement_resolved_candidate(candidate)
    if scope == "monitor_only":
        return _is_procurement_monitor_candidate(candidate)
    if scope == "review_only":
        return _is_procurement_review_candidate(candidate)
    return True


def _is_procurement_candidate_visible_for_statuses(
    candidate: dict[str, object],
    statuses: tuple[str, ...],
) -> bool:
    if not statuses:
        return True
    return str(candidate.get("remediation_status", "")) in set(statuses)


def _is_procurement_recent_event_visible_for_actions(
    event: dict[str, object],
    actions: tuple[str, ...],
) -> bool:
    if not actions:
        return True
    return str(event.get("action", "")).strip() in set(actions)


def _sort_procurement_override_candidate_stale_first(
    candidate: dict[str, object],
) -> tuple[object, ...]:
    remediation_status = str(candidate.get("remediation_status", ""))
    unresolved_rank = 0 if _is_procurement_unresolved_candidate(candidate) else 1
    followup_dt = _parse_iso_datetime(str(candidate.get("followup_updated_at") or ""))
    followup_timestamp = followup_dt.timestamp() if followup_dt is not None else float("inf")
    status_rank = {
        "needs_override_reason": 0,
        "ready_to_retry": 1,
        "monitor": 2,
        "resolved": 3,
    }.get(remediation_status, 4)
    fallback_recency_rank = -followup_timestamp if followup_timestamp != float("inf") else float("inf")
    return (
        unresolved_rank,
        followup_timestamp if unresolved_rank == 0 else fallback_recency_rank,
        status_rank,
        str(candidate.get("project_name", "") or candidate.get("project_id", "")),
    )


def _select_oldest_unresolved_procurement_candidate(
    candidates: list[dict[str, object]],
) -> dict[str, object] | None:
    unresolved_candidates = [
        candidate
        for candidate in candidates
        if str(candidate.get("remediation_status", "")) in {"needs_override_reason", "ready_to_retry"}
    ]
    if not unresolved_candidates:
        return None

    def _key(candidate: dict[str, object]) -> tuple[float, str]:
        followup_dt = _parse_iso_datetime(str(candidate.get("followup_updated_at") or ""))
        return (
            followup_dt.timestamp() if followup_dt is not None else float("inf"),
            str(candidate.get("project_name", "") or candidate.get("project_id", "")),
        )

    oldest = min(unresolved_candidates, key=_key)
    return {
        "project_id": oldest.get("project_id"),
        "project_name": oldest.get("project_name"),
        "recommendation": oldest.get("recommendation"),
        "remediation_status": oldest.get("remediation_status"),
        "downstream_bundles": oldest.get("downstream_bundles"),
        "latest_blocked_bundle_type": oldest.get("latest_blocked_bundle_type"),
        "latest_blocked_error_code": oldest.get("latest_blocked_error_code"),
        "followup_updated_at": oldest.get("followup_updated_at"),
        "followup_reference_kind": oldest.get("followup_reference_kind"),
    }


def _build_procurement_handoff_queue_key(
    *,
    linked_project_id: str,
    detail: dict[str, object] | object,
) -> tuple[str, str, str, str, str]:
    if not isinstance(detail, dict):
        return (linked_project_id, "", "", "", "")
    return (
        linked_project_id,
        str(detail.get("procurement_context_kind", "") or ""),
        str(detail.get("bundle_type", "") or ""),
        str(detail.get("error_code", "") or ""),
        str(detail.get("recommendation", "") or ""),
    )


def _sort_procurement_handoff_queue_item(item: dict[str, object]) -> tuple[object, ...]:
    status_rank = {
        "shared_not_opened": 0,
        "opened_unresolved": 1,
        "opened_resolved": 2,
    }.get(str(item.get("handoff_status", "")), 3)
    handoff_dt = _parse_iso_datetime(str(item.get("latest_handoff_at") or ""))
    handoff_rank = -(handoff_dt.timestamp()) if handoff_dt is not None else float("inf")
    return (
        status_rank,
        handoff_rank,
        str(item.get("project_name", "") or item.get("project_id", "")),
        str(item.get("bundle_type", "")),
    )


def _build_procurement_stale_share_queue_key(
    *,
    linked_project_id: str,
    detail: dict[str, object] | object,
) -> tuple[str, str, str]:
    if not isinstance(detail, dict):
        return (linked_project_id, "", "")
    return (
        linked_project_id,
        str(detail.get("share_project_document_id", "") or ""),
        str(detail.get("bundle_type", "") or ""),
    )


def _sort_procurement_stale_share_queue_item(item: dict[str, object]) -> tuple[object, ...]:
    share_state_rank = 2
    if item.get("share_record_found") is False:
        share_state_rank = 3
    elif item.get("share_is_active") is True:
        share_state_rank = 0 if int(item.get("share_access_count", 0) or 0) > 0 else 1
    status_rank = {
        "source_missing": 0,
        "source_mismatch": 0,
        "stale_procurement": 0,
        "stale_revision": 1,
        "stale_procurement_review": 1,
        "source_changed": 2,
    }.get(str(item.get("share_risk_status", "")), 3)
    last_access_dt = _parse_iso_datetime(str(item.get("share_last_accessed_at") or ""))
    last_access_rank = -(last_access_dt.timestamp()) if last_access_dt is not None else float("inf")
    observed_dt = _parse_iso_datetime(str(item.get("latest_risk_observed_at") or ""))
    observed_rank = -(observed_dt.timestamp()) if observed_dt is not None else float("inf")
    return (
        share_state_rank,
        last_access_rank,
        status_rank,
        observed_rank,
        str(item.get("project_name", "") or item.get("project_id", "")),
        str(item.get("project_document_title", "") or item.get("project_document_id", "")),
    )
