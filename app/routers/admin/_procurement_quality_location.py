"""app/routers/admin/_procurement_quality_location.py — Location-level stale-share overview.

Extracted from app/routers/admin.py (moved verbatim; no behavior changes).
Split out of _procurement_quality.py to keep each module under 800 lines.
Used by app/routers/admin/_locations.py for the /admin/locations list endpoint
(include_procurement=True).
"""
from __future__ import annotations

from fastapi import Request

from app.routers.admin._procurement_quality_helpers import (
    _build_procurement_stale_share_queue_key,
    _is_procurement_stale_share_activity,
    _pick_newer_audit_entry,
)
from app.routers.admin._procurement_quality_queues import _build_procurement_stale_share_queue


def _empty_procurement_location_overview() -> dict[str, object]:
    return {
        "stale_external_share_queue_count": 0,
        "active_stale_external_share_queue_count": 0,
        "active_accessed_stale_external_share_queue_count": 0,
        "active_unaccessed_stale_external_share_queue_count": 0,
        "inactive_stale_external_share_queue_count": 0,
        "missing_stale_external_share_record_count": 0,
        "has_active_stale_share_exposure": False,
        "top_stale_external_share_item": None,
    }


def _build_procurement_location_overview(tenant_id: str, request: Request) -> dict[str, object]:
    procurement_store = request.app.state.procurement_store
    project_store = request.app.state.project_store
    from app.storage.audit_store import AuditStore
    from app.storage.share_store import ShareStore

    decisions = procurement_store.list_by_tenant(tenant_id)
    if not decisions:
        return _empty_procurement_location_overview()

    decision_project_ids = {decision.project_id for decision in decisions}
    project_map = {
        project.project_id: project
        for project in project_store.list_by_tenant(tenant_id)
        if project.project_id in decision_project_ids
    }
    audit_store = AuditStore(tenant_id)
    share_store = ShareStore(
        tenant_id,
        data_dir=request.app.state.data_dir,
        backend=request.app.state.state_backend,
    )
    stale_share_events_by_key: dict[tuple[str, str, str], dict[str, object]] = {}
    for entry in audit_store.query_all(tenant_id):
        if str(entry.get("action", "")) != "share.create":
            continue
        detail = entry.get("detail", {})
        if not _is_procurement_stale_share_activity(detail):
            continue
        linked_project_id = ""
        if isinstance(detail, dict):
            linked_project_id = str(detail.get("project_id", "") or "").strip()
        if not linked_project_id or linked_project_id not in decision_project_ids:
            continue
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

    stale_external_share_queue, _, _ = _build_procurement_stale_share_queue(
        stale_share_events_by_key,
        project_map=project_map,
        share_store=share_store,
    )
    active_stale_external_share_queue_count = sum(
        1 for item in stale_external_share_queue if item.get("share_is_active") is True
    )
    return {
        "stale_external_share_queue_count": len(stale_external_share_queue),
        "active_stale_external_share_queue_count": int(active_stale_external_share_queue_count),
        "active_accessed_stale_external_share_queue_count": int(
            sum(
                1
                for item in stale_external_share_queue
                if item.get("share_is_active") is True and int(item.get("share_access_count", 0) or 0) > 0
            )
        ),
        "active_unaccessed_stale_external_share_queue_count": int(
            sum(
                1
                for item in stale_external_share_queue
                if item.get("share_is_active") is True and int(item.get("share_access_count", 0) or 0) <= 0
            )
        ),
        "inactive_stale_external_share_queue_count": int(
            sum(1 for item in stale_external_share_queue if item.get("share_is_active") is False)
        ),
        "missing_stale_external_share_record_count": int(
            sum(1 for item in stale_external_share_queue if item.get("share_record_found") is False)
        ),
        "has_active_stale_share_exposure": active_stale_external_share_queue_count > 0,
        "top_stale_external_share_item": stale_external_share_queue[0] if stale_external_share_queue else None,
    }
