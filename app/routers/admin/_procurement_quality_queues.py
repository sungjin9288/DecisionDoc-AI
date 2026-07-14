"""Procurement remediation and external-share queue builders."""
from __future__ import annotations

from collections import Counter

from app.routers.admin._procurement_quality_helpers import (
    _resolve_procurement_stale_share_evidence,
    _sort_procurement_handoff_queue_item,
    _sort_procurement_stale_share_queue_item,
    _sorted_counts,
)


def _build_procurement_stale_share_queue(
    stale_share_events_by_key: dict[tuple[str, str, str], dict[str, object]],
    *,
    project_map: dict[str, object],
    share_store,
) -> tuple[
    list[dict[str, object]],
    dict[str, int],
    dict[str, dict[str, object]],
    int,
]:
    project_document_lookup: dict[tuple[str, str], object] = {}
    for project_id, project in project_map.items():
        for document in getattr(project, "documents", []):
            project_document_lookup[(project_id, str(getattr(document, "doc_id", "") or ""))] = document

    queue: list[dict[str, object]] = []
    status_counts: Counter[str] = Counter()
    latest_by_project: dict[str, dict[str, object]] = {}
    recovered_share_count = 0

    for key, payload in stale_share_events_by_key.items():
        project_id, project_document_id, bundle_type = key
        latest_by_share_id = payload.get("latest_by_share_id") if isinstance(payload, dict) else None
        risk_seen_share_ids = payload.get("risk_seen_share_ids") if isinstance(payload, dict) else None
        if isinstance(latest_by_share_id, dict):
            risky_shares: list[
                tuple[dict[str, object], dict[str, object], dict[str, object] | None]
            ] = []
            for candidate_share_id, candidate_entry in latest_by_share_id.items():
                if not isinstance(candidate_entry, dict):
                    continue
                candidate_risk = _resolve_procurement_stale_share_evidence(
                    candidate_entry.get("detail", {})
                )
                if candidate_risk:
                    candidate_link = share_store.get(candidate_share_id)
                    risky_shares.append((candidate_entry, candidate_risk, candidate_link))
                elif isinstance(risk_seen_share_ids, set) and candidate_share_id in risk_seen_share_ids:
                    recovered_share_count += 1
            if not risky_shares:
                continue
            risky_shares.sort(
                key=lambda item: (
                    isinstance(item[2], dict) and item[2].get("is_active") is True,
                    isinstance(item[2], dict)
                    and int(item[2].get("access_count", 0) or 0) > 0,
                    str(item[0].get("timestamp", "")),
                ),
                reverse=True,
            )
            entry, risk, share_link = risky_shares[0]
            stale_share_count = len(risky_shares)
            risky_share_links = [link for _, _, link in risky_shares]
            share_lifecycle_status_counts: Counter[str] = Counter(
                str(link.get("lifecycle_status", "inactive") or "inactive")
                if isinstance(link, dict)
                else "missing"
                for _, _, link in risky_shares
            )
        else:
            entry = payload.get("latest") if isinstance(payload, dict) else None
            if not isinstance(entry, dict):
                continue
            risk = _resolve_procurement_stale_share_evidence(entry.get("detail", {}))
            if not risk:
                continue
            stale_share_count = (
                int(payload.get("count", 0) or 0) if isinstance(payload, dict) else 0
            )
            share_id = str(entry.get("resource_id", "") or "").strip()
            share_link = share_store.get(share_id) if share_id else None
            share_lifecycle_status_counts = Counter(
                {
                    (
                        str(share_link.get("lifecycle_status", "inactive") or "inactive")
                        if isinstance(share_link, dict)
                        else "missing"
                    ): 1
                }
            )
            risky_share_links = [share_link]

        detail = entry.get("detail", {})
        risk_status = str(risk.get("status", "") or "")
        share_id = str(entry.get("resource_id", "") or "").strip()
        share_lifecycle_status = (
            str(share_link.get("lifecycle_status", "") or "inactive")
            if isinstance(share_link, dict)
            else "missing"
        )
        create_by_share_id = payload.get("create_by_share_id") if isinstance(payload, dict) else None
        latest_create = (
            create_by_share_id.get(share_id)
            if share_id and isinstance(create_by_share_id, dict)
            else None
        )
        if (
            not isinstance(latest_create, dict)
            and not isinstance(create_by_share_id, dict)
            and isinstance(payload, dict)
        ):
            latest_create = payload.get("latest_create")
        latest_shared_at = (
            str(latest_create.get("timestamp", "") or "")
            if isinstance(latest_create, dict)
            else str((share_link or {}).get("created_at", "") or "")
        )
        latest_shared_by_username = (
            str(latest_create.get("username", "") or "")
            if isinstance(latest_create, dict)
            else str((share_link or {}).get("created_by", "") or "")
        )
        project = project_map.get(project_id)
        document = project_document_lookup.get((project_id, project_document_id))
        queue_item = {
            "project_id": project_id,
            "project_name": str(getattr(project, "name", "") or "") if project is not None else "",
            "project_document_id": project_document_id or None,
            "project_document_title": (
                str(getattr(document, "title", "") or "") if document is not None else ""
            ),
            "bundle_type": bundle_type or (
                str(getattr(document, "bundle_id", "") or "") if document is not None else ""
            ),
            "bundle_label": {
                "bid_decision_kr": "의사결정 문서",
                "proposal_kr": "제안서",
            }.get(
                bundle_type or str(getattr(document, "bundle_id", "") or ""),
                bundle_type or str(getattr(document, "bundle_id", "") or "") or "downstream",
            ),
            "share_risk_status": risk_status,
            "share_risk_status_tone": str(risk.get("tone", "") or ""),
            "share_risk_status_copy": str(risk.get("copy", "") or ""),
            "share_risk_status_summary": str(risk.get("summary", "") or ""),
            "decision_council_document_status": (
                str(detail.get("share_decision_council_document_status", "") or "")
                if isinstance(detail, dict)
                else ""
            ),
            "decision_council_document_status_tone": (
                str(detail.get("share_decision_council_document_status_tone", "") or "")
                if isinstance(detail, dict)
                else ""
            ),
            "decision_council_document_status_copy": (
                str(detail.get("share_decision_council_document_status_copy", "") or "")
                if isinstance(detail, dict)
                else ""
            ),
            "decision_council_document_status_summary": (
                str(detail.get("share_decision_council_document_status_summary", "") or "")
                if isinstance(detail, dict)
                else ""
            ),
            "procurement_review_document_status": (
                str(detail.get("share_procurement_review_document_status", "") or "")
                if isinstance(detail, dict)
                else ""
            ),
            "procurement_review_document_status_tone": (
                str(detail.get("share_procurement_review_document_status_tone", "") or "")
                if isinstance(detail, dict)
                else ""
            ),
            "procurement_review_document_status_copy": (
                str(detail.get("share_procurement_review_document_status_copy", "") or "")
                if isinstance(detail, dict)
                else ""
            ),
            "procurement_review_document_status_summary": (
                str(detail.get("share_procurement_review_document_status_summary", "") or "")
                if isinstance(detail, dict)
                else ""
            ),
            "source_binding_status": (
                str(detail.get("share_source_binding_status", "") or "")
                if isinstance(detail, dict)
                else ""
            ),
            "post_share_source_changed": (
                detail.get("share_post_share_source_changed") is True
                if isinstance(detail, dict)
                else False
            ),
            "latest_shared_at": latest_shared_at,
            "latest_shared_by_username": latest_shared_by_username,
            "latest_risk_observed_at": str(entry.get("timestamp", "") or ""),
            "latest_risk_observed_by_username": str(entry.get("username", "") or ""),
            "latest_risk_action": str(entry.get("action", "") or ""),
            "stale_share_count": stale_share_count,
            "active_stale_share_count": share_lifecycle_status_counts.get("active", 0),
            "active_accessed_stale_share_count": sum(
                1
                for link in risky_share_links
                if isinstance(link, dict)
                and link.get("is_active") is True
                and int(link.get("access_count", 0) or 0) > 0
            ),
            "active_unaccessed_stale_share_count": sum(
                1
                for link in risky_share_links
                if isinstance(link, dict)
                and link.get("is_active") is True
                and int(link.get("access_count", 0) or 0) <= 0
            ),
            "revoked_stale_share_count": share_lifecycle_status_counts.get("revoked", 0),
            "expired_stale_share_count": share_lifecycle_status_counts.get("expired", 0),
            "inactive_stale_share_count": share_lifecycle_status_counts.get("inactive", 0),
            "missing_stale_share_count": share_lifecycle_status_counts.get("missing", 0),
            "share_lifecycle_status_counts": _sorted_counts(share_lifecycle_status_counts),
            "share_id": share_id or None,
            "share_url": f"/shared/{share_id}" if share_id else None,
            "share_record_found": isinstance(share_link, dict),
            "share_lifecycle_status": share_lifecycle_status,
            "share_is_active": (
                bool(share_link.get("is_active"))
                if isinstance(share_link, dict)
                else None
            ),
            "share_access_count": (
                int(share_link.get("access_count", 0) or 0)
                if isinstance(share_link, dict)
                else 0
            ),
            "share_last_accessed_at": (
                str(share_link.get("last_accessed_at", "") or "") or None
                if isinstance(share_link, dict)
                else None
            ),
            "share_expires_at": (
                str(share_link.get("expires_at", "") or "") or None
                if isinstance(share_link, dict)
                else None
            ),
            "share_revoked_at": (
                str(share_link.get("revoked_at", "") or "") or None
                if isinstance(share_link, dict)
                else None
            ),
            "share_revoked_by": (
                str(share_link.get("revoked_by", "") or "") or None
                if isinstance(share_link, dict)
                else None
            ),
            "share_revoked_by_username": (
                str(share_link.get("revoked_by_username", "") or "") or None
                if isinstance(share_link, dict)
                else None
            ),
        }
        queue.append(queue_item)
        status_counts[risk_status] += 1

        current_item = latest_by_project.get(project_id)
        if current_item is None or str(queue_item.get("latest_risk_observed_at", "")) > str(
            current_item.get("latest_risk_observed_at", "")
        ):
            latest_by_project[project_id] = queue_item

    queue.sort(key=_sort_procurement_stale_share_queue_item)
    return queue, _sorted_counts(status_counts), latest_by_project, recovered_share_count


def _build_procurement_handoff_queue(
    handoff_events_by_key: dict[tuple[str, str, str, str, str], dict[str, object]],
    *,
    project_map: dict[str, object],
    override_candidate_map: dict[str, dict[str, object]],
) -> tuple[list[dict[str, object]], dict[str, int], dict[str, dict[str, object]]]:
    handoff_queue: list[dict[str, object]] = []
    handoff_queue_status_counts: Counter[str] = Counter()
    latest_handoff_by_project: dict[str, dict[str, object]] = {}

    for key, payload in handoff_events_by_key.items():
        project_id, context_kind, bundle_type, error_code, recommendation = key
        candidate = override_candidate_map.get(project_id)
        remediation_status = str((candidate or {}).get("remediation_status", "monitor") or "monitor")
        if remediation_status == "monitor":
            continue

        latest_copied_entry = payload.get("copied")
        latest_opened_entry = payload.get("opened")
        latest_copied_at = (
            str(latest_copied_entry.get("timestamp", "")) if isinstance(latest_copied_entry, dict) else ""
        )
        latest_opened_at = (
            str(latest_opened_entry.get("timestamp", "")) if isinstance(latest_opened_entry, dict) else ""
        )
        if latest_opened_at and latest_opened_at >= latest_copied_at:
            if remediation_status in {"needs_override_reason", "ready_to_retry"}:
                handoff_status = "opened_unresolved"
            elif remediation_status == "resolved":
                handoff_status = "opened_resolved"
            else:
                continue
            latest_handoff_entry = latest_opened_entry
            latest_handoff_at = latest_opened_at
        elif latest_copied_at:
            handoff_status = "shared_not_opened"
            latest_handoff_entry = latest_copied_entry
            latest_handoff_at = latest_copied_at
        else:
            continue

        latest_detail = latest_handoff_entry.get("detail", {}) if isinstance(latest_handoff_entry, dict) else {}
        project = project_map.get(project_id)
        project_name = str(getattr(project, "name", "") or "") if project is not None else ""
        queue_item = {
            "project_id": project_id,
            "project_name": project_name,
            "handoff_status": handoff_status,
            "remediation_status": remediation_status,
            "recommendation": recommendation or str((candidate or {}).get("recommendation", "") or ""),
            "procurement_context_kind": context_kind,
            "procurement_operation": (
                str(latest_detail.get("procurement_operation", "") or "")
                if isinstance(latest_detail, dict)
                else ""
            ),
            "bundle_type": bundle_type or (
                str(latest_detail.get("bundle_type", "") or "")
                if isinstance(latest_detail, dict)
                else ""
            ),
            "error_code": error_code or (
                str(latest_detail.get("error_code", "") or "")
                if isinstance(latest_detail, dict)
                else ""
            ),
            "latest_handoff_at": latest_handoff_at,
            "latest_copied_at": latest_copied_at or None,
            "latest_opened_at": latest_opened_at or None,
            "downstream_bundles": list((candidate or {}).get("downstream_bundles", [])),
            "latest_activity": list((candidate or {}).get("latest_activity", [])),
            "latest_override_reason": (candidate or {}).get("latest_override_reason"),
            "followup_updated_at": (candidate or {}).get("followup_updated_at"),
            "followup_reference_kind": (candidate or {}).get("followup_reference_kind"),
        }
        handoff_queue.append(queue_item)
        handoff_queue_status_counts[handoff_status] += 1

        current_project_item = latest_handoff_by_project.get(project_id)
        if current_project_item is None or str(queue_item.get("latest_handoff_at", "")) > str(
            current_project_item.get("latest_handoff_at", "")
        ):
            latest_handoff_by_project[project_id] = queue_item

    handoff_queue.sort(key=_sort_procurement_handoff_queue_item)
    return handoff_queue, _sorted_counts(handoff_queue_status_counts), latest_handoff_by_project
