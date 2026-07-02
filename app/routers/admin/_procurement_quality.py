"""app/routers/admin/_procurement_quality.py — Procurement decision quality/handoff summary.

Extracted from app/routers/admin.py (moved verbatim; no behavior changes).
Provides the tenant- and location-scoped "procurement-quality-summary" endpoints
plus `_build_procurement_quality_summary`, the top-level aggregation function
they depend on. To keep every module under 800 lines, related logic is split
across sibling files:
- _procurement_quality_helpers.py: pure/utility helpers (parsing, filtering,
  sorting, link resolution).
- _procurement_quality_queues.py: remediation handoff + stale-share queue
  builders.
- _procurement_quality_location.py: the location-level stale-share overview
  used by _locations.py's /admin/locations endpoint.
"""
from __future__ import annotations

from collections import Counter
import dataclasses

from fastapi import APIRouter, Depends, HTTPException, Request

from app.auth.api_key import require_api_key
from app.dependencies import require_admin

from app.routers.admin._procurement_quality_helpers import (
    _PROCUREMENT_ACTIVITY_ACTIONS,
    _PROCUREMENT_DOWNSTREAM_BUNDLE_IDS,
    _PROCUREMENT_HANDOFF_BUNDLE_IDS,
    _build_procurement_handoff_queue_key,
    _build_procurement_recent_event,
    _build_procurement_stale_share_queue_key,
    _extract_latest_override_reason,
    _find_latest_procurement_project_entry,
    _hydrate_procurement_followup_state,
    _is_procurement_candidate_visible_for_scope,
    _is_procurement_candidate_visible_for_statuses,
    _is_procurement_recent_event_visible_for_actions,
    _is_procurement_stale_share_activity,
    _limit_procurement_recent_activity,
    _normalize_procurement_activity_actions,
    _normalize_procurement_override_candidate_scope,
    _normalize_procurement_override_candidate_statuses,
    _normalize_procurement_override_candidate_view,
    _pick_newer_audit_entry,
    _resolve_procurement_activity_link,
    _resolve_procurement_followup_reference,
    _resolve_procurement_remediation_status,
    _select_oldest_unresolved_procurement_candidate,
    _sort_procurement_override_candidate,
    _sort_procurement_override_candidate_stale_first,
    _sorted_counts,
)
from app.routers.admin._procurement_quality_queues import (
    _build_procurement_handoff_queue,
    _build_procurement_stale_share_queue,
)

router = APIRouter()


def _build_procurement_quality_summary(
    tenant_id: str,
    request: Request,
    *,
    focus_project_id: str = "",
    candidate_view: str = "latest_followup",
    candidate_scope: str = "all",
    candidate_statuses: str | list[str] | tuple[str, ...] | set[str] | None = None,
    activity_actions: str | list[str] | tuple[str, ...] | set[str] | None = None,
) -> dict:
    candidate_view = _normalize_procurement_override_candidate_view(candidate_view)
    candidate_scope = _normalize_procurement_override_candidate_scope(candidate_scope)
    candidate_statuses = _normalize_procurement_override_candidate_statuses(candidate_statuses)
    activity_actions = _normalize_procurement_activity_actions(activity_actions)
    procurement_store = request.app.state.procurement_store
    project_store = request.app.state.project_store
    approval_store = request.app.state.approval_store

    decisions = procurement_store.list_by_tenant(tenant_id)
    projects = project_store.list_by_tenant(tenant_id)
    approvals = approval_store.list_by_tenant(tenant_id)
    decision_map = {decision.project_id: decision for decision in decisions}

    recommendation_counts: Counter[str] = Counter()
    score_status_counts: Counter[str] = Counter()
    blocking_hard_filter_counts: Counter[str] = Counter()
    handoff_document_counts: Counter[str] = Counter()
    project_document_status_counts: Counter[str] = Counter()
    approval_status_counts: Counter[str] = Counter()

    decision_project_ids: set[str] = set()
    procurement_request_ids: set[str] = set()
    procurement_approval_ids: set[str] = set()
    approval_to_project_id: dict[str, str] = {}
    soft_fit_scores: list[float] = []
    records_with_missing_data = 0
    records_with_blocking_failures = 0
    action_needed_total = 0
    bid_decision_project_ids: set[str] = set()
    downstream_bundles_by_project: dict[str, set[str]] = {}

    for decision in decisions:
        decision_project_ids.add(decision.project_id)
        if decision.recommendation is None:
            recommendation_counts["PENDING"] += 1
        else:
            recommendation_counts[decision.recommendation.value] += 1
        score_status_counts[decision.soft_fit_status] += 1
        if decision.soft_fit_score is not None:
            soft_fit_scores.append(decision.soft_fit_score)
        if decision.missing_data:
            records_with_missing_data += 1
        has_blocking_failure = False
        for hard_filter in decision.hard_filters:
            if hard_filter.blocking and hard_filter.status == "fail":
                has_blocking_failure = True
                blocking_hard_filter_counts[hard_filter.code] += 1
        if has_blocking_failure:
            records_with_blocking_failures += 1
        action_needed_total += sum(
            1
            for item in decision.checklist_items
            if item.status in {"action_needed", "blocked"}
        )

    procurement_documents = []
    project_map = {
        project.project_id: project
        for project in projects
        if project.project_id in decision_project_ids
    }
    for project in projects:
        if project.project_id not in decision_project_ids:
            continue
        for document in project.documents:
            if document.bundle_id not in _PROCUREMENT_HANDOFF_BUNDLE_IDS:
                continue
            procurement_documents.append(document)
            handoff_document_counts[document.bundle_id] += 1
            if document.bundle_id == "bid_decision_kr":
                bid_decision_project_ids.add(project.project_id)
            if document.bundle_id in _PROCUREMENT_DOWNSTREAM_BUNDLE_IDS:
                downstream_bundles_by_project.setdefault(project.project_id, set()).add(document.bundle_id)
            if document.approval_status:
                project_document_status_counts[document.approval_status] += 1
            if document.request_id:
                procurement_request_ids.add(document.request_id)
            if document.approval_id:
                procurement_approval_ids.add(document.approval_id)
                approval_to_project_id[document.approval_id] = project.project_id

    procurement_approvals = [
        approval
        for approval in approvals
        if approval.approval_id in procurement_approval_ids
        or approval.request_id in procurement_request_ids
    ]
    for approval in procurement_approvals:
        approval_status_counts[approval.status] += 1

    avg_soft_fit_score = (
        round(sum(soft_fit_scores) / len(soft_fit_scores), 2)
        if soft_fit_scores
        else None
    )
    recommendation_followthrough = {
        key: {"projects": 0, "with_downstream": 0, "without_downstream": 0}
        for key in ("GO", "CONDITIONAL_GO", "NO_GO", "PENDING")
    }
    from app.storage.audit_store import AuditStore
    from app.storage.share_store import ShareStore

    audit_store = AuditStore(tenant_id)
    share_store = ShareStore(
        tenant_id,
        data_dir=request.app.state.data_dir,
        backend=request.app.state.state_backend,
    )
    audit_entries = audit_store.query_all(tenant_id)
    activity_counts: Counter[str] = Counter()
    recent_activity: list[dict[str, object]] = []
    project_activity_actions: dict[str, list[str]] = {}
    project_followup_state: dict[str, dict[str, str]] = {}
    handoff_events_by_key: dict[tuple[str, str, str, str, str], dict[str, object]] = {}
    stale_share_events_by_key: dict[tuple[str, str, str], dict[str, object]] = {}
    for entry in audit_entries:
        action = str(entry.get("action", ""))
        if action not in _PROCUREMENT_ACTIVITY_ACTIONS:
            continue
        detail = entry.get("detail", {})
        if action == "share.create" and not _is_procurement_stale_share_activity(detail):
            continue
        linked_project_id, linked_approval_id = _resolve_procurement_activity_link(
            entry,
            decision_project_ids=decision_project_ids,
            procurement_approval_ids=procurement_approval_ids,
            approval_to_project_id=approval_to_project_id,
        )
        if not linked_project_id and not linked_approval_id:
            continue
        activity_counts[action] += 1
        if linked_project_id:
            project_activity_actions.setdefault(linked_project_id, []).append(action)
            followup_state = project_followup_state.setdefault(
                linked_project_id,
                {
                    "latest_blocked_at": "",
                    "latest_blocked_bundle_type": "",
                    "latest_blocked_error_code": "",
                    "latest_override_reason_at": "",
                    "latest_resolved_at": "",
                    "latest_resolved_bundle_type": "",
                },
            )
            if action == "procurement.downstream_blocked" and not followup_state["latest_blocked_at"]:
                followup_state["latest_blocked_at"] = str(entry.get("timestamp", ""))
                followup_state["latest_blocked_bundle_type"] = (
                    str(detail.get("bundle_type", "")) if isinstance(detail, dict) else ""
                )
                followup_state["latest_blocked_error_code"] = (
                    str(detail.get("error_code", "")) if isinstance(detail, dict) else ""
                )
            if action == "procurement.downstream_resolved" and not followup_state["latest_resolved_at"]:
                followup_state["latest_resolved_at"] = str(entry.get("timestamp", ""))
                followup_state["latest_resolved_bundle_type"] = (
                    str(detail.get("bundle_type", "")) if isinstance(detail, dict) else ""
                )
            if action == "procurement.override_reason" and not followup_state["latest_override_reason_at"]:
                followup_state["latest_override_reason_at"] = str(entry.get("timestamp", ""))
            if action in {
                "procurement.remediation_link_copied",
                "procurement.remediation_link_opened",
            }:
                handoff_key = _build_procurement_handoff_queue_key(
                    linked_project_id=linked_project_id,
                    detail=detail,
                )
                handoff_event_state = handoff_events_by_key.setdefault(handoff_key, {})
                if action == "procurement.remediation_link_copied" and "copied" not in handoff_event_state:
                    handoff_event_state["copied"] = entry
                if action == "procurement.remediation_link_opened" and "opened" not in handoff_event_state:
                    handoff_event_state["opened"] = entry
            if action == "share.create":
                stale_share_key = _build_procurement_stale_share_queue_key(
                    linked_project_id=linked_project_id,
                    detail=detail,
                )
                stale_share_state = stale_share_events_by_key.setdefault(
                    stale_share_key,
                    {"latest": None, "count": 0},
                )
                stale_share_state["latest"] = _pick_newer_audit_entry(
                    stale_share_state.get("latest"),
                    entry,
                ) or entry
                stale_share_state["count"] = int(stale_share_state.get("count", 0) or 0) + 1
        recent_activity.append(
            _build_procurement_recent_event(
                entry,
                linked_project_id=linked_project_id,
                linked_approval_id=linked_approval_id,
                project_map=project_map,
            )
        )

    override_candidates: list[dict[str, object]] = []
    handoff_project_context_map: dict[str, dict[str, object]] = {}
    override_candidate_status_counts: Counter[str] = Counter()
    unresolved_override_candidates = 0
    for decision in decisions:
        recommendation_key = (
            decision.recommendation.value if decision.recommendation is not None else "PENDING"
        )
        followthrough = recommendation_followthrough[recommendation_key]
        followthrough["projects"] += 1
        downstream_bundles = sorted(downstream_bundles_by_project.get(decision.project_id, set()))
        if downstream_bundles:
            followthrough["with_downstream"] += 1
        else:
            followthrough["without_downstream"] += 1
        if recommendation_key == "NO_GO":
            project = project_map.get(decision.project_id)
            blocking_codes = sorted(
                hard_filter.code
                for hard_filter in decision.hard_filters
                if hard_filter.blocking and hard_filter.status == "fail"
            )
            action_needed_count = sum(
                1
                for item in decision.checklist_items
                if item.status in {"action_needed", "blocked"}
            )
            latest_override_reason = _extract_latest_override_reason(decision.notes)
            followup_state = _hydrate_procurement_followup_state(
                audit_store,
                tenant_id,
                project_id=decision.project_id,
                current_state=project_followup_state.get(decision.project_id, {}),
                decision_project_ids=decision_project_ids,
                procurement_approval_ids=procurement_approval_ids,
                approval_to_project_id=approval_to_project_id,
            )
            latest_blocked_at = str(followup_state.get("latest_blocked_at", ""))
            latest_blocked_bundle_type = str(
                followup_state.get("latest_blocked_bundle_type", "")
            )
            latest_blocked_error_code = str(
                followup_state.get("latest_blocked_error_code", "")
            )
            latest_resolved_at = str(followup_state.get("latest_resolved_at", ""))
            latest_resolved_bundle_type = str(
                followup_state.get("latest_resolved_bundle_type", "")
            )
            remediation_status = _resolve_procurement_remediation_status(
                followup_state=followup_state,
                latest_override_reason=latest_override_reason,
            )
            followup_updated_at, followup_reference_kind = _resolve_procurement_followup_reference(
                remediation_status=remediation_status,
                followup_state=followup_state,
                latest_override_reason=latest_override_reason,
            )
            handoff_project_context = {
                "project_id": decision.project_id,
                "project_name": project.name if project is not None else "",
                "recommendation": recommendation_key,
                "downstream_bundles": downstream_bundles,
                "blocking_hard_filter_codes": blocking_codes,
                "missing_data_count": len(decision.missing_data),
                "action_needed_count": action_needed_count,
                "latest_activity": project_activity_actions.get(decision.project_id, [])[:3],
                "latest_override_reason": latest_override_reason,
                "remediation_status": remediation_status,
                "latest_blocked_at": latest_blocked_at or None,
                "latest_blocked_bundle_type": latest_blocked_bundle_type or None,
                "latest_blocked_error_code": latest_blocked_error_code or None,
                "latest_resolved_at": latest_resolved_at or None,
                "latest_resolved_bundle_type": latest_resolved_bundle_type or None,
                "followup_updated_at": followup_updated_at,
                "followup_reference_kind": followup_reference_kind,
            }
            handoff_project_context_map[decision.project_id] = handoff_project_context
            if downstream_bundles:
                override_candidate_status_counts[remediation_status] += 1
                if remediation_status in {"needs_override_reason", "ready_to_retry"}:
                    unresolved_override_candidates += 1
                override_candidates.append(handoff_project_context)
    if candidate_view == "stale_unresolved":
        override_candidates.sort(key=_sort_procurement_override_candidate_stale_first)
    else:
        override_candidates.sort(key=_sort_procurement_override_candidate)
    override_candidate_map = {
        str(candidate.get("project_id", "")): candidate
        for candidate in override_candidates
        if str(candidate.get("project_id", "")).strip()
    }
    remediation_handoff_queue, remediation_handoff_status_counts, remediation_handoff_by_project = (
        _build_procurement_handoff_queue(
            handoff_events_by_key,
            project_map=project_map,
            override_candidate_map={**handoff_project_context_map, **override_candidate_map},
        )
    )
    stale_external_share_queue, stale_external_share_status_counts, stale_external_share_by_project = (
        _build_procurement_stale_share_queue(
            stale_share_events_by_key,
            project_map=project_map,
            share_store=share_store,
        )
    )
    active_stale_external_share_queue_count = sum(
        1 for item in stale_external_share_queue if item.get("share_is_active") is True
    )
    active_accessed_stale_external_share_queue_count = sum(
        1
        for item in stale_external_share_queue
        if item.get("share_is_active") is True and int(item.get("share_access_count", 0) or 0) > 0
    )
    active_unaccessed_stale_external_share_queue_count = sum(
        1
        for item in stale_external_share_queue
        if item.get("share_is_active") is True and int(item.get("share_access_count", 0) or 0) <= 0
    )
    inactive_stale_external_share_queue_count = sum(
        1 for item in stale_external_share_queue if item.get("share_is_active") is False
    )
    missing_stale_external_share_record_count = sum(
        1 for item in stale_external_share_queue if item.get("share_record_found") is False
    )
    oldest_unresolved_followup = _select_oldest_unresolved_procurement_candidate(override_candidates)
    visible_override_candidates = (
        [
            candidate
            for candidate in override_candidates
            if _is_procurement_candidate_visible_for_scope(candidate, candidate_scope)
            and _is_procurement_candidate_visible_for_statuses(candidate, candidate_statuses)
        ]
        if candidate_scope != "all" or candidate_statuses
        else list(override_candidates)
    )
    scope_override_candidates = (
        [
            candidate
            for candidate in override_candidates
            if _is_procurement_candidate_visible_for_scope(candidate, candidate_scope)
        ]
        if candidate_scope != "all"
        else list(override_candidates)
    )
    scope_override_candidate_status_counts: Counter[str] = Counter(
        str(candidate.get("remediation_status", "") or "monitor")
        for candidate in scope_override_candidates
    )
    visible_override_project_ids = {
        str(candidate.get("project_id", "")).strip()
        for candidate in visible_override_candidates
        if str(candidate.get("project_id", "")).strip()
    }

    focused_project_summary: dict[str, object] | None = None
    focused_recent_event: dict[str, object] | None = None
    if focus_project_id:
        focused_project = project_map.get(focus_project_id)
        focused_decision = decision_map.get(focus_project_id)
        focused_candidate = next(
            (
                candidate
                for candidate in override_candidates
                if str(candidate.get("project_id", "")) == focus_project_id
            ),
            None,
        )
        focused_recent_event = next(
            (
                event
                for event in recent_activity
                if str(event.get("linked_project_id", "")) == focus_project_id
            ),
            None,
        )
        if focused_recent_event is None:
            latest_focus_entry, fallback_project_id, fallback_approval_id = (
                _find_latest_procurement_project_entry(
                    audit_store,
                    tenant_id,
                    project_id=focus_project_id,
                    actions=_PROCUREMENT_ACTIVITY_ACTIONS,
                    decision_project_ids=decision_project_ids,
                    procurement_approval_ids=procurement_approval_ids,
                    approval_to_project_id=approval_to_project_id,
                )
            )
            if latest_focus_entry is not None:
                focused_recent_event = _build_procurement_recent_event(
                    latest_focus_entry,
                    linked_project_id=fallback_project_id,
                    linked_approval_id=fallback_approval_id,
                    project_map=project_map,
                )

    visible_recent_activity_source = (
        [
            event
            for event in recent_activity
            if str(event.get("linked_project_id", "")).strip() in visible_override_project_ids
        ]
        if candidate_scope != "all" or candidate_statuses
        else list(recent_activity)
    )
    if focus_project_id and focused_recent_event is not None and not any(
        str(event.get("linked_project_id", "")) == focus_project_id
        for event in visible_recent_activity_source
    ):
        visible_recent_activity_source.append(focused_recent_event)

    scope_activity_counts: Counter[str] = Counter(
        str(event.get("action", "")).strip()
        for event in visible_recent_activity_source
        if str(event.get("action", "")).strip()
    )
    filtered_recent_activity_source = (
        [
            event
            for event in visible_recent_activity_source
            if _is_procurement_recent_event_visible_for_actions(event, activity_actions)
        ]
        if activity_actions
        else list(visible_recent_activity_source)
    )
    if focus_project_id and focused_recent_event is not None and not any(
        str(event.get("linked_project_id", "")) == focus_project_id
        for event in filtered_recent_activity_source
    ):
        filtered_recent_activity_source.append(focused_recent_event)
    visible_action_counts: Counter[str] = Counter(
        str(event.get("action", "")).strip()
        for event in filtered_recent_activity_source
        if str(event.get("action", "")).strip()
    )
    visible_recent_activity = _limit_procurement_recent_activity(
        filtered_recent_activity_source,
        focus_project_id=focus_project_id,
        limit=10,
    )

    if focus_project_id:
        focused_project = project_map.get(focus_project_id)
        focused_decision = decision_map.get(focus_project_id)
        focused_candidate = next(
            (
                candidate
                for candidate in override_candidates
                if str(candidate.get("project_id", "")) == focus_project_id
            ),
            None,
        )
        if focused_project is not None or focused_decision is not None or focused_candidate is not None:
            focused_latest_activity = project_activity_actions.get(focus_project_id, [])[:3]
            if not focused_latest_activity and focused_recent_event is not None:
                latest_action = str(focused_recent_event.get("action", "")).strip()
                if latest_action:
                    focused_latest_activity = [latest_action]

            focused_latest_override_reason = (
                focused_candidate.get("latest_override_reason")
                if focused_candidate is not None
                else _extract_latest_override_reason(focused_decision.notes if focused_decision is not None else "")
            )
            focused_followup_state = _hydrate_procurement_followup_state(
                audit_store,
                tenant_id,
                project_id=focus_project_id,
                current_state={
                    "latest_blocked_at": (
                        str(focused_candidate.get("latest_blocked_at") or "")
                        if focused_candidate is not None
                        else ""
                    ),
                    "latest_blocked_bundle_type": (
                        str(focused_candidate.get("latest_blocked_bundle_type") or "")
                        if focused_candidate is not None
                        else ""
                    ),
                    "latest_blocked_error_code": (
                        str(focused_candidate.get("latest_blocked_error_code") or "")
                        if focused_candidate is not None
                        else ""
                    ),
                    "latest_override_reason_at": "",
                    "latest_resolved_at": (
                        str(focused_candidate.get("latest_resolved_at") or "")
                        if focused_candidate is not None
                        else ""
                    ),
                    "latest_resolved_bundle_type": (
                        str(focused_candidate.get("latest_resolved_bundle_type") or "")
                        if focused_candidate is not None
                        else ""
                    ),
                },
                decision_project_ids=decision_project_ids,
                procurement_approval_ids=procurement_approval_ids,
                approval_to_project_id=approval_to_project_id,
            )
            focused_remediation_status = _resolve_procurement_remediation_status(
                followup_state=focused_followup_state,
                latest_override_reason=focused_latest_override_reason,
                default_status=(
                    str(focused_candidate.get("remediation_status", "monitor"))
                    if focused_candidate is not None
                    else "monitor"
                ),
            )
            focused_followup_updated_at, focused_followup_reference_kind = (
                _resolve_procurement_followup_reference(
                    remediation_status=focused_remediation_status,
                    followup_state=focused_followup_state,
                    latest_override_reason=focused_latest_override_reason,
                    latest_event_timestamp=(
                        str(focused_recent_event.get("timestamp", "")) if focused_recent_event else ""
                    ),
                )
            )

            recommendation = "PENDING"
            if focused_candidate is not None:
                recommendation = str(focused_candidate.get("recommendation", "PENDING"))
            elif focused_decision is not None and focused_decision.recommendation is not None:
                recommendation = focused_decision.recommendation.value
            focused_handoff_queue_item = remediation_handoff_by_project.get(focus_project_id)
            focused_stale_external_share_item = stale_external_share_by_project.get(focus_project_id)
            focused_project_summary = {
                "project_id": focus_project_id,
                "project_name": focused_project.name if focused_project is not None else "",
                "recommendation": recommendation,
                "remediation_status": focused_remediation_status,
                "downstream_bundles": (
                    list(focused_candidate.get("downstream_bundles", []))
                    if focused_candidate is not None
                    else sorted(downstream_bundles_by_project.get(focus_project_id, set()))
                ),
                "latest_activity": focused_latest_activity,
                "latest_override_reason": focused_latest_override_reason,
                "latest_event": focused_recent_event,
                "latest_blocked_at": focused_followup_state["latest_blocked_at"] or None,
                "latest_blocked_bundle_type": (
                    focused_followup_state["latest_blocked_bundle_type"] or None
                ),
                "latest_blocked_error_code": (
                    focused_followup_state["latest_blocked_error_code"] or None
                ),
                "latest_resolved_at": focused_followup_state["latest_resolved_at"] or None,
                "latest_resolved_bundle_type": (
                    focused_followup_state["latest_resolved_bundle_type"] or None
                ),
                "followup_updated_at": focused_followup_updated_at,
                "followup_reference_kind": focused_followup_reference_kind,
                "handoff_queue_item": focused_handoff_queue_item,
                "stale_external_share_item": focused_stale_external_share_item,
                "visible_in_override_candidates": any(
                    str(candidate.get("project_id", "")) == focus_project_id
                    for candidate in visible_override_candidates[:4]
                ),
                "visible_in_recent_events": any(
                    str(event.get("linked_project_id", "")) == focus_project_id
                    for event in visible_recent_activity
                ),
            }

    return {
        "focused_project": focused_project_summary,
        "decision": {
            "total_records": len(decisions),
            "projects_with_procurement_state": len(decision_project_ids),
            "records_with_recommendation": len(decisions) - recommendation_counts.get("PENDING", 0),
            "records_missing_recommendation": recommendation_counts.get("PENDING", 0),
            "recommendation_counts": _sorted_counts(recommendation_counts),
            "score_status_counts": _sorted_counts(score_status_counts),
            "avg_soft_fit_score": avg_soft_fit_score,
            "records_with_missing_data": records_with_missing_data,
            "records_with_blocking_failures": records_with_blocking_failures,
            "blocking_hard_filter_counts": _sorted_counts(blocking_hard_filter_counts),
            "action_needed_total": action_needed_total,
        },
        "handoff": {
            "documents_total": len(procurement_documents),
            "document_counts": _sorted_counts(handoff_document_counts),
            "documents_with_approval_link": len(procurement_approval_ids),
            "project_document_status_counts": _sorted_counts(project_document_status_counts),
            "approval_status_counts": _sorted_counts(approval_status_counts),
            "remediation_queue_count": len(remediation_handoff_queue),
            "remediation_queue_status_counts": remediation_handoff_status_counts,
            "remediation_queue": remediation_handoff_queue,
        },
        "sharing": {
            "stale_external_share_queue_count": len(stale_external_share_queue),
            "active_stale_external_share_queue_count": active_stale_external_share_queue_count,
            "active_accessed_stale_external_share_queue_count": active_accessed_stale_external_share_queue_count,
            "active_unaccessed_stale_external_share_queue_count": active_unaccessed_stale_external_share_queue_count,
            "inactive_stale_external_share_queue_count": inactive_stale_external_share_queue_count,
            "missing_stale_external_share_record_count": missing_stale_external_share_record_count,
            "stale_external_share_status_counts": stale_external_share_status_counts,
            "stale_external_share_queue": stale_external_share_queue,
        },
        "outcomes": {
            "override_candidate_view": candidate_view,
            "override_candidate_scope": candidate_scope,
            "override_candidate_status_filters": list(candidate_statuses),
            "projects_with_bid_decision_doc": len(bid_decision_project_ids),
            "projects_with_downstream_handoff": len(downstream_bundles_by_project),
            "recommendation_followthrough": recommendation_followthrough,
            "override_candidate_count": len(override_candidates),
            "visible_override_candidate_count": len(visible_override_candidates),
            "override_candidates_needing_followup": unresolved_override_candidates,
            "override_candidate_status_counts": _sorted_counts(override_candidate_status_counts),
            "scope_override_candidate_status_counts": _sorted_counts(scope_override_candidate_status_counts),
            "oldest_unresolved_followup": oldest_unresolved_followup,
            "override_candidates": visible_override_candidates,
        },
        "activity": {
            "action_counts": _sorted_counts(activity_counts),
            "activity_action_filters": list(activity_actions),
            "scope_action_counts": _sorted_counts(scope_activity_counts),
            "scope_recent_event_count": len(visible_recent_activity_source),
            "visible_action_counts": _sorted_counts(visible_action_counts),
            "filtered_recent_event_count": len(filtered_recent_activity_source),
            "visible_recent_event_count": len(visible_recent_activity),
            "recent_events": visible_recent_activity,
        },
    }


@router.get(
    "/admin/tenants/{tenant_id_path}/procurement-quality-summary",
)
def admin_tenant_procurement_quality_summary(tenant_id_path: str, request: Request) -> dict:
    """Tenant-scoped procurement decision and handoff summary. Accepts admin JWT or OPS key."""
    require_admin(request)
    tenant = request.app.state.tenant_store.get_tenant(tenant_id_path)
    if tenant is None:
        raise HTTPException(status_code=404, detail=f"Tenant '{tenant_id_path}' not found.")
    focus_project_id = str(request.query_params.get("focus_project_id", "")).strip()
    candidate_view = str(request.query_params.get("candidate_view", "")).strip()
    candidate_scope = str(request.query_params.get("candidate_scope", "")).strip()
    candidate_statuses = str(request.query_params.get("candidate_statuses", "")).strip()
    activity_actions = str(request.query_params.get("activity_actions", "")).strip()
    return {
        "tenant": dataclasses.asdict(tenant),
        "procurement": _build_procurement_quality_summary(
            tenant_id_path,
            request,
            focus_project_id=focus_project_id,
            candidate_view=candidate_view,
            candidate_scope=candidate_scope,
            candidate_statuses=candidate_statuses,
            activity_actions=activity_actions,
        ),
    }


@router.get(
    "/admin/locations/{tenant_id_path}/procurement-quality-summary",
    dependencies=[Depends(require_api_key)],
)
def admin_location_procurement_quality_summary(tenant_id_path: str, request: Request) -> dict:
    """Location-scoped procurement decision and handoff summary for admin UI."""
    require_admin(request)
    tenant = request.app.state.tenant_store.get_tenant(tenant_id_path)
    if tenant is None:
        raise HTTPException(status_code=404, detail=f"Tenant '{tenant_id_path}' not found.")
    focus_project_id = str(request.query_params.get("focus_project_id", "")).strip()
    candidate_view = str(request.query_params.get("candidate_view", "")).strip()
    candidate_scope = str(request.query_params.get("candidate_scope", "")).strip()
    candidate_statuses = str(request.query_params.get("candidate_statuses", "")).strip()
    activity_actions = str(request.query_params.get("activity_actions", "")).strip()
    return {
        "tenant": dataclasses.asdict(tenant),
        "procurement": _build_procurement_quality_summary(
            tenant_id_path,
            request,
            focus_project_id=focus_project_id,
            candidate_view=candidate_view,
            candidate_scope=candidate_scope,
            candidate_statuses=candidate_statuses,
            activity_actions=activity_actions,
        ),
    }
