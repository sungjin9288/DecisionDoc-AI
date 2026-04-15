"""app/routers/admin.py — Admin, tenant management, invite, and model registry endpoints.

Extracted from app/main.py to keep the main module lean.
"""
from __future__ import annotations

from collections import Counter
import dataclasses
from datetime import datetime
import json as _json
import os
import re
import secrets as _secrets
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse

from app.ai_profiles.catalog import (
    default_ai_profiles_for_role,
    list_ai_profiles,
    normalize_ai_profile_keys,
)
from app.auth.api_key import require_api_key
from app.auth.ops_key import require_ops_key
from app.dependencies import require_admin
from app.providers.factory import get_provider
from app.schemas import AcceptInviteRequest, InviteUserRequest

router = APIRouter(tags=["admin"])

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
_PROCUREMENT_STALE_SHARE_STATUSES = (
    "stale_procurement",
    "stale_revision",
)


# ---------------------------------------------------------------------------
# Helper: invite page HTML
# ---------------------------------------------------------------------------

def _render_invite_page(invite: dict, invite_id: str) -> str:
    role_labels = {"admin": "관리자", "member": "팀원", "viewer": "열람자"}
    role = role_labels.get(invite.get("role", "member"), "팀원")
    job_title = str(invite.get("job_title", "") or "").strip()
    assigned_profiles = list_ai_profiles(invite.get("assigned_ai_profiles") or [])
    profile_html = (
        "".join(
            f'<span class="badge" style="margin-right:6px;margin-bottom:6px;">{profile["label"]}</span>'
            for profile in assigned_profiles
        )
        if assigned_profiles
        else '<span style="color:#6b7280;font-size:.9rem;">관리자가 로그인 후 업무 AI를 배정할 예정입니다.</span>'
    )
    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>초대 — DecisionDoc AI</title>
<style>
  body{{font-family:'Malgun Gothic',sans-serif;display:flex;align-items:center;
       justify-content:center;min-height:100vh;margin:0;background:#f9fafb}}
  .box{{background:white;border-radius:16px;padding:40px;max-width:400px;
        width:90%;box-shadow:0 8px 32px rgba(0,0,0,0.1)}}
  h2{{color:#6366f1;margin-top:0}}
  .badge{{display:inline-block;background:#6366f120;color:#6366f1;
          padding:4px 12px;border-radius:99px;font-size:.85rem}}
  input{{width:100%;padding:10px;margin:6px 0 12px;border:1px solid #e5e7eb;
         border-radius:8px;box-sizing:border-box;font-size:1rem}}
  button{{width:100%;padding:12px;background:#6366f1;color:white;border:none;
          border-radius:8px;font-size:1rem;cursor:pointer}}
  label{{font-size:.85rem;color:#374151;font-weight:500}}
  #err{{color:#ef4444;margin-top:8px}}
</style>
</head>
<body>
<div class="box">
  <h2>🎉 팀 초대</h2>
  <p>DecisionDoc AI 팀에 초대되었습니다.</p>
  <p>역할: <span class="badge">{role}</span></p>
  <p>직위: <strong>{job_title or '미지정'}</strong></p>
  <div style="margin:12px 0 4px;">
    <div style="font-size:.85rem;color:#374151;font-weight:600;margin-bottom:6px;">배정된 업무 AI</div>
    <div style="display:flex;flex-wrap:wrap;">{profile_html}</div>
  </div>
  <hr style="border:none;border-top:1px solid #e5e7eb;margin:20px 0">
  <form onsubmit="accept(event)">
    <label>아이디</label>
    <input id="u" required minlength="3" placeholder="사용할 아이디">
    <label>이름</label>
    <input id="n" required placeholder="실명 또는 닉네임">
    <label>비밀번호</label>
    <input id="p" type="password" required minlength="8" placeholder="8자 이상">
    <button type="submit">계정 만들기 →</button>
  </form>
  <div id="err"></div>
</div>
<script>
async function accept(e){{
  e.preventDefault();
  const r=await fetch('/invite/{invite_id}/accept',{{method:'POST',
    headers:{{'Content-Type':'application/json'}},
    body:JSON.stringify({{username:document.getElementById('u').value,
      display_name:document.getElementById('n').value,
      password:document.getElementById('p').value}})
  }});
  if(r.ok){{const d=await r.json();
    localStorage.setItem('dd_access_token',d.access_token);
    localStorage.setItem('dd_refresh_token',d.refresh_token);
    location.href='/';
  }}else{{document.getElementById('err').textContent=(await r.json()).detail||'오류';}}
}}
</script>
</body>
</html>"""


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
    }


def _is_procurement_stale_share_activity(detail: object) -> bool:
    if not isinstance(detail, dict):
        return False
    if str(detail.get("bundle_type", "") or "").strip() not in {
        "bid_decision_kr",
        "proposal_kr",
    }:
        return False
    share_status = str(detail.get("share_decision_council_document_status", "") or "").strip()
    return bool(share_status) and share_status != "current"


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
    tenant_id: str,
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
            tenant_id,
            actions=actions,
            resource_ids=focus_resource_ids,
            result=result,
        ),
        audit_store.find_latest_entry(
            tenant_id,
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
    tenant_id: str,
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
            tenant_id,
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
            tenant_id,
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
            tenant_id,
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
        "stale_procurement": 0,
        "stale_revision": 1,
    }.get(str(item.get("decision_council_document_status", "")), 2)
    last_access_dt = _parse_iso_datetime(str(item.get("share_last_accessed_at") or ""))
    last_access_rank = -(last_access_dt.timestamp()) if last_access_dt is not None else float("inf")
    shared_dt = _parse_iso_datetime(str(item.get("latest_shared_at") or ""))
    shared_rank = -(shared_dt.timestamp()) if shared_dt is not None else float("inf")
    return (
        share_state_rank,
        last_access_rank,
        status_rank,
        shared_rank,
        str(item.get("project_name", "") or item.get("project_id", "")),
        str(item.get("project_document_title", "") or item.get("project_document_id", "")),
    )


def _build_procurement_stale_share_queue(
    stale_share_events_by_key: dict[tuple[str, str, str], dict[str, object]],
    *,
    project_map: dict[str, object],
    share_store,
) -> tuple[list[dict[str, object]], dict[str, int], dict[str, dict[str, object]]]:
    project_document_lookup: dict[tuple[str, str], object] = {}
    for project_id, project in project_map.items():
        for document in getattr(project, "documents", []):
            project_document_lookup[(project_id, str(getattr(document, "doc_id", "") or ""))] = document

    queue: list[dict[str, object]] = []
    status_counts: Counter[str] = Counter()
    latest_by_project: dict[str, dict[str, object]] = {}

    for key, payload in stale_share_events_by_key.items():
        project_id, project_document_id, bundle_type = key
        entry = payload.get("latest") if isinstance(payload, dict) else None
        if not isinstance(entry, dict):
            continue
        detail = entry.get("detail", {})
        share_status = (
            str(detail.get("share_decision_council_document_status", "") or "")
            if isinstance(detail, dict)
            else ""
        )
        share_id = str(entry.get("resource_id", "") or "").strip()
        if share_status not in _PROCUREMENT_STALE_SHARE_STATUSES:
            continue
        share_link = share_store.get(share_id) if share_id else None
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
            "decision_council_document_status": share_status,
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
            "latest_shared_at": str(entry.get("timestamp", "") or ""),
            "latest_shared_by_username": str(entry.get("username", "") or ""),
            "stale_share_count": int(payload.get("count", 0) or 0) if isinstance(payload, dict) else 0,
            "share_id": share_id or None,
            "share_url": f"/shared/{share_id}" if share_id else None,
            "share_record_found": isinstance(share_link, dict),
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
        }
        queue.append(queue_item)
        status_counts[share_status] += 1

        current_item = latest_by_project.get(project_id)
        if current_item is None or str(queue_item.get("latest_shared_at", "")) > str(
            current_item.get("latest_shared_at", "")
        ):
            latest_by_project[project_id] = queue_item

    queue.sort(key=_sort_procurement_stale_share_queue_item)
    return queue, _sorted_counts(status_counts), latest_by_project


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


# ---------------------------------------------------------------------------
# Bundle auto-expansion
# ---------------------------------------------------------------------------

@router.post("/admin/expand-bundles", dependencies=[Depends(require_ops_key)])
def expand_bundles(request: Request) -> dict:
    """Manually trigger bundle auto-expansion from unmatched request patterns."""
    from app.storage.request_pattern_store import RequestPatternStore
    from app.services.bundle_expander import BundleAutoExpander
    from app.config import get_auto_expand_threshold

    data_dir = request.app.state.data_dir
    prompt_override_store = request.app.state.prompt_override_store
    provider = get_provider()
    pattern_store = RequestPatternStore(data_dir)
    expander = BundleAutoExpander(
        provider=provider,
        override_store=prompt_override_store,
        pattern_store=pattern_store,
    )
    result = expander.analyze_and_expand()
    if result is None:
        unmatched_count = len(pattern_store.get_unmatched(limit=50))
        threshold = get_auto_expand_threshold()
        return {
            "expanded": False,
            "reason": (
                f"unmatched={unmatched_count} < threshold={threshold}"
                if unmatched_count < threshold
                else "패턴 미감지 또는 confidence 부족"
            ),
        }
    return {"expanded": True, "bundle": result}


@router.get("/admin/auto-bundles")
def list_auto_bundles(request: Request) -> list[dict]:
    """List all auto-generated bundles with their metadata."""
    data_dir = request.app.state.data_dir
    registry_path = data_dir / "auto_bundles" / "registry.json"
    if not registry_path.exists():
        return []
    try:
        data = _json.loads(registry_path.read_text(encoding="utf-8"))
    except Exception:
        return []
    return list(data.values())


@router.delete("/admin/auto-bundles/{bundle_id}", dependencies=[Depends(require_ops_key)])
def delete_auto_bundle(bundle_id: str, request: Request) -> dict:
    """Remove an auto-generated bundle from the registry and reload."""
    data_dir = request.app.state.data_dir
    registry_path = data_dir / "auto_bundles" / "registry.json"
    if not registry_path.exists():
        raise HTTPException(status_code=404, detail=f"Auto bundle '{bundle_id}' not found")

    try:
        data = _json.loads(registry_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"registry.json 읽기 실패: {exc}") from exc

    if bundle_id not in data:
        raise HTTPException(status_code=404, detail=f"Auto bundle '{bundle_id}' not found")

    del data[bundle_id]
    registry_path.write_text(_json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    py_path = data_dir / "auto_bundles" / f"{bundle_id}.py"
    if py_path.exists():
        py_path.unlink()

    try:
        from app.bundle_catalog.registry import reload_auto_bundles
        reload_auto_bundles()
    except Exception:
        pass

    return {"deleted": True, "bundle_id": bundle_id}


@router.get("/admin/request-patterns")
def get_request_patterns(request: Request) -> dict:
    """View the request pattern log."""
    from app.storage.request_pattern_store import RequestPatternStore
    from app.config import get_auto_expand_threshold

    data_dir = request.app.state.data_dir
    pattern_store = RequestPatternStore(data_dir)
    all_records = pattern_store.get_all(limit=200)
    unmatched = [r for r in all_records if not r.get("matched", True)]
    threshold = get_auto_expand_threshold()
    return {
        "total": len(all_records),
        "unmatched_count": len(unmatched),
        "threshold": threshold,
        "ready_to_expand": len(unmatched) >= threshold,
        "records": all_records,
    }


# ---------------------------------------------------------------------------
# Team Invitations
# ---------------------------------------------------------------------------

@router.post("/admin/invite")
async def admin_invite_user(body: InviteUserRequest, request: Request) -> dict:
    """Generate a 7-day invitation link for a new team member. Admin only."""
    require_admin(request)
    from app.storage.invite_store import InviteStore
    tenant_store = request.app.state.tenant_store
    tenant_id = (body.tenant_id or getattr(request.state, "tenant_id", "system") or "system").strip()
    if tenant_store.get_tenant(tenant_id) is None:
        raise HTTPException(404, f"Tenant '{tenant_id}' not found.")
    assigned_profiles = (
        normalize_ai_profile_keys(body.assigned_ai_profiles)
        if body.assigned_ai_profiles
        else default_ai_profiles_for_role(body.role)
    )
    invite_id = _secrets.token_urlsafe(20)
    store = InviteStore(tenant_id)
    store.create(
        invite_id=invite_id,
        tenant_id=tenant_id,
        email=body.email,
        role=body.role,
        created_by=getattr(request.state, "user_id", "admin"),
        expires_days=7,
        job_title=body.job_title.strip(),
        assigned_ai_profiles=assigned_profiles,
    )
    base_url = str(request.base_url).rstrip("/")
    invite_url = f"{base_url}/invite/{invite_id}"
    return {
        "invite_id": invite_id,
        "invite_url": invite_url,
        "email": body.email,
        "role": body.role,
        "job_title": body.job_title.strip(),
        "assigned_ai_profiles": assigned_profiles,
        "expires_days": 7,
    }


@router.get("/invite/{invite_id}")
async def view_invite(invite_id: str, request: Request):
    """Public invite acceptance page."""
    tenant_store = request.app.state.tenant_store
    from app.storage.invite_store import InviteStore
    for tenant in tenant_store.list_tenants():
        store = InviteStore(tenant.tenant_id)
        invite = store.get(invite_id)
        if invite:
            if not invite.get("is_active"):
                return HTMLResponse("<h2>초대 링크가 만료되었습니다.</h2>", status_code=410)
            return HTMLResponse(_render_invite_page(invite, invite_id))
    raise HTTPException(404, "초대 링크를 찾을 수 없습니다.")


@router.post("/invite/{invite_id}/accept")
async def accept_invite(invite_id: str, body: AcceptInviteRequest, request: Request) -> dict:
    """Accept invite and create account."""
    from app.storage.invite_store import InviteStore
    from app.storage.user_store import UserStore
    from app.services.auth_service import create_access_token, create_refresh_token
    tenant_store = request.app.state.tenant_store
    for tenant in tenant_store.list_tenants():
        store = InviteStore(tenant.tenant_id)
        invite = store.get(invite_id)
        if invite and invite.get("is_active"):
            data_dir = Path(os.getenv("DATA_DIR", "./data"))
            user_store = UserStore(
                data_dir / "tenants" / tenant.tenant_id,
                backend=request.app.state.state_backend,
            )
            existing = user_store.get_by_username(tenant.tenant_id, body.username)
            if existing:
                raise HTTPException(400, "이미 사용 중인 아이디입니다.")
            user = user_store.create(
                tenant_id=tenant.tenant_id,
                username=body.username,
                display_name=body.display_name,
                email=invite.get("email", ""),
                password=body.password,
                role=invite.get("role", "member"),
                job_title=invite.get("job_title", ""),
                assigned_ai_profiles=invite.get("assigned_ai_profiles") or [],
            )
            store.mark_used(invite_id)
            return {
                "message": "계정이 생성되었습니다.",
                "access_token": create_access_token(
                    user.user_id, tenant.tenant_id, user.role.value, user.username
                ),
                "refresh_token": create_refresh_token(user.user_id, tenant.tenant_id),
                "user": {
                    "user_id": user.user_id,
                    "username": user.username,
                    "role": user.role.value,
                    "job_title": user.job_title,
                    "assigned_ai_profiles": list(user.assigned_ai_profiles),
                },
            }
    raise HTTPException(404, "초대 링크를 찾을 수 없습니다.")


# ---------------------------------------------------------------------------
# Tenant Management
# ---------------------------------------------------------------------------

@router.post("/admin/tenants")
def admin_create_tenant(payload: dict, request: Request) -> dict:
    """Create a new tenant. Accepts admin JWT or OPS key."""
    require_admin(request)
    tenant_store = request.app.state.tenant_store
    tenant_id_val = payload.get("tenant_id", "").strip()
    display_name_val = payload.get("display_name", "").strip()
    if not tenant_id_val or not display_name_val:
        raise HTTPException(status_code=422, detail="tenant_id and display_name are required.")
    allowed = payload.get("allowed_bundles") or []
    try:
        tenant = tenant_store.create_tenant(
            tenant_id=tenant_id_val,
            display_name=display_name_val,
            allowed_bundles=allowed,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return dataclasses.asdict(tenant)


@router.get("/admin/tenants")
def admin_list_tenants(request: Request) -> list[dict]:
    """List all tenants. Accepts admin JWT or OPS key."""
    require_admin(request)
    return [dataclasses.asdict(t) for t in request.app.state.tenant_store.list_tenants()]


@router.get("/admin/tenants/{tenant_id_path}")
def admin_get_tenant(tenant_id_path: str, request: Request) -> dict:
    """Get a single tenant by ID. Accepts admin JWT or OPS key."""
    require_admin(request)
    tenant = request.app.state.tenant_store.get_tenant(tenant_id_path)
    if tenant is None:
        raise HTTPException(status_code=404, detail=f"Tenant '{tenant_id_path}' not found.")
    return dataclasses.asdict(tenant)


@router.patch("/admin/tenants/{tenant_id_path}")
def admin_update_tenant(tenant_id_path: str, payload: dict, request: Request) -> dict:
    """Update mutable fields of a tenant. Accepts admin JWT or OPS key."""
    require_admin(request)
    try:
        tenant = request.app.state.tenant_store.update_tenant(
            tenant_id_path,
            display_name=payload.get("display_name"),
            allowed_bundles=payload.get("allowed_bundles"),
            is_active=payload.get("is_active"),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return dataclasses.asdict(tenant)


@router.post("/admin/tenants/{tenant_id_path}/custom-hint")
def admin_set_custom_hint(tenant_id_path: str, payload: dict, request: Request) -> dict:
    """Set a bundle-specific custom prompt hint for a tenant. Accepts admin JWT or OPS key."""
    require_admin(request)
    bundle_id_val = payload.get("bundle_id", "").strip()
    hint_val = payload.get("hint", "").strip()
    if not bundle_id_val or not hint_val:
        raise HTTPException(status_code=422, detail="bundle_id and hint are required.")
    try:
        request.app.state.tenant_store.set_custom_hint(tenant_id_path, bundle_id_val, hint_val)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"tenant_id": tenant_id_path, "bundle_id": bundle_id_val, "hint": hint_val}


@router.delete("/admin/tenants/{tenant_id_path}/custom-hint/{bundle_id_path}")
def admin_delete_custom_hint(tenant_id_path: str, bundle_id_path: str, request: Request) -> dict:
    """Remove a bundle-specific custom prompt hint for a tenant. Accepts admin JWT or OPS key."""
    require_admin(request)
    try:
        request.app.state.tenant_store.delete_custom_hint(tenant_id_path, bundle_id_path)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"deleted": True, "tenant_id": tenant_id_path, "bundle_id": bundle_id_path}


@router.get("/admin/tenants/{tenant_id_path}/stats")
def admin_tenant_stats(tenant_id_path: str, request: Request) -> dict:
    """Tenant usage statistics. Accepts admin JWT or OPS key."""
    require_admin(request)
    tenant = request.app.state.tenant_store.get_tenant(tenant_id_path)
    if tenant is None:
        raise HTTPException(status_code=404, detail=f"Tenant '{tenant_id_path}' not found.")
    try:
        from app.eval.eval_store import get_eval_store
        eval_stats = get_eval_store(tenant_id_path).get_all_stats()
    except Exception:
        eval_stats = {}
    try:
        from app.storage.feedback_store import get_feedback_store
        all_fb = get_feedback_store(tenant_id_path).get_all()
        fb_count = len(all_fb)
        avg_rating: float | None = (
            round(sum(f.get("rating", 0) for f in all_fb) / fb_count, 2)
            if all_fb else None
        )
    except Exception:
        fb_count = 0
        avg_rating = None
    return {
        "tenant": dataclasses.asdict(tenant),
        "eval": eval_stats,
        "feedback_count": fb_count,
        "avg_rating": avg_rating,
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


# ---------------------------------------------------------------------------
# Per-Tenant API Key Management
# ---------------------------------------------------------------------------

@router.post("/admin/tenants/{tenant_id_path}/rotate-key", dependencies=[Depends(require_api_key)])
def admin_rotate_tenant_key(tenant_id_path: str, request: Request) -> dict:
    """Generate a new API key for the tenant. Key is shown ONLY in this response.
    Requires admin role."""
    require_admin(request)
    tenant_store = request.app.state.tenant_store
    if tenant_store.get_tenant(tenant_id_path) is None:
        raise HTTPException(status_code=404, detail=f"Tenant '{tenant_id_path}' not found.")
    key = tenant_store.rotate_api_key(tenant_id_path)
    return {
        "tenant_id": tenant_id_path,
        "api_key": key,
        "note": "이 키는 지금만 표시됩니다. 안전한 곳에 저장하세요.",
    }


# ---------------------------------------------------------------------------
# Location (Tenant) Overview with User Counts
# ---------------------------------------------------------------------------

@router.get("/admin/locations", dependencies=[Depends(require_api_key)])
def admin_list_locations(request: Request, include_procurement: bool = False) -> list[dict]:
    """List all tenants as 'locations' with user count + usage stats. Requires admin."""
    require_admin(request)
    from app.storage.user_store import UserStore
    tenant_store = request.app.state.tenant_store
    data_dir = request.app.state.data_dir

    result = []
    for tenant in tenant_store.list_tenants():
        try:
            user_store = UserStore(
                data_dir / "tenants" / tenant.tenant_id,
                backend=request.app.state.state_backend,
            )
            users = user_store.list_by_tenant(tenant.tenant_id)
            user_count = len(users)
        except Exception:
            user_count = 0

        try:
            from app.eval.eval_store import get_eval_store
            eval_stats = get_eval_store(tenant.tenant_id).get_all_stats()
            gen_count = eval_stats.get("total_count", 0)
        except Exception:
            gen_count = 0

        location_summary = {
            **dataclasses.asdict(tenant),
            "user_count": user_count,
            "generation_count": gen_count,
        }
        if include_procurement:
            try:
                location_summary["procurement"] = _build_procurement_location_overview(
                    tenant.tenant_id,
                    request,
                )
            except Exception:
                location_summary["procurement"] = _empty_procurement_location_overview()
        result.append(location_summary)
    return result


@router.get("/admin/locations/{tenant_id_path}/users", dependencies=[Depends(require_api_key)])
def admin_location_users(tenant_id_path: str, request: Request) -> list[dict]:
    """List users for a specific location/tenant. Requires admin."""
    require_admin(request)
    from app.storage.user_store import UserStore
    tenant_store = request.app.state.tenant_store
    if tenant_store.get_tenant(tenant_id_path) is None:
        raise HTTPException(status_code=404, detail=f"Tenant '{tenant_id_path}' not found.")
    data_dir = request.app.state.data_dir
    user_store = UserStore(
        data_dir / "tenants" / tenant_id_path,
        backend=request.app.state.state_backend,
    )
    users = user_store.list_by_tenant(tenant_id_path)
    return [
        {
            "user_id": u.user_id,
            "username": u.username,
            "display_name": u.display_name,
            "email": u.email,
            "role": u.role.value,
            "is_active": u.is_active,
            "created_at": u.created_at,
            "last_login": u.last_login,
            "avatar_color": u.avatar_color,
            "job_title": getattr(u, "job_title", ""),
            "assigned_ai_profiles": list(getattr(u, "assigned_ai_profiles", []) or []),
        }
        for u in users
    ]


@router.patch("/admin/locations/{tenant_id_path}/users/{user_id}", dependencies=[Depends(require_api_key)])
def admin_update_location_user(tenant_id_path: str, user_id: str, payload: dict, request: Request) -> dict:
    """Update a tenant user's role/profile assignment. Requires admin."""
    require_admin(request)
    from app.storage.user_store import UserStore

    tenant_store = request.app.state.tenant_store
    if tenant_store.get_tenant(tenant_id_path) is None:
        raise HTTPException(status_code=404, detail=f"Tenant '{tenant_id_path}' not found.")
    data_dir = request.app.state.data_dir
    user_store = UserStore(
        data_dir / "tenants" / tenant_id_path,
        backend=request.app.state.state_backend,
    )
    updates: dict = {}
    for key in ("display_name", "email", "role", "is_active", "job_title", "assigned_ai_profiles"):
        if key in payload:
            updates[key] = payload[key]
    try:
        user_store.update(user_id, **updates)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"message": "사용자 업무 AI 배정이 수정되었습니다."}


# ---------------------------------------------------------------------------
# Model Registry
# ---------------------------------------------------------------------------

@router.get("/models")
def list_models(
    request: Request,
    bundle_id: str | None = None,
    status: str | None = None,
) -> list[dict]:
    """List fine-tuned models for the current tenant."""
    from app.storage.model_registry import ModelRegistry
    tenant_id = getattr(request.state, "tenant_id", "system") or "system"
    registry = ModelRegistry(request.app.state.data_dir)
    return registry.list_models(tenant_id=tenant_id, bundle_id=bundle_id, status=status)


@router.get("/models/{model_id:path}")
def get_model(model_id: str, request: Request) -> dict:
    """Get details for a specific fine-tuned model."""
    from app.storage.model_registry import ModelRegistry
    tenant_id = getattr(request.state, "tenant_id", "system") or "system"
    registry = ModelRegistry(request.app.state.data_dir)
    model = registry.get_model(model_id, tenant_id)
    if model is None:
        raise HTTPException(status_code=404, detail=f"Model '{model_id}' not found.")
    return model


@router.post("/admin/models/trigger-training", dependencies=[Depends(require_ops_key)])
async def admin_trigger_training(request: Request, payload: dict) -> dict:
    """Manually trigger fine-tune check for a bundle+tenant. Requires OPS key."""
    from app.services.finetune_orchestrator import FineTuneOrchestrator
    tenant_id = getattr(request.state, "tenant_id", "system") or "system"
    bundle_id_val: str | None = payload.get("bundle_id") or None
    orch = FineTuneOrchestrator(request.app.state.data_dir)
    result = await orch.check_and_trigger(bundle_id_val, tenant_id)
    if result is None:
        return {"triggered": False, "message": "Not enough data or training already in progress."}
    return {"triggered": True, **result}


@router.post("/admin/models/{model_id:path}/promote", dependencies=[Depends(require_ops_key)])
def admin_promote_model(model_id: str, request: Request) -> dict:
    """Manually promote a model to 'ready' status. Requires OPS key."""
    from app.storage.model_registry import ModelRegistry
    tenant_id = getattr(request.state, "tenant_id", "system") or "system"
    registry = ModelRegistry(request.app.state.data_dir)
    model = registry.get_model(model_id, tenant_id)
    if model is None:
        raise HTTPException(status_code=404, detail=f"Model '{model_id}' not found.")
    job_id = model.get("openai_job_id", "")
    if not registry.update_status(job_id, "ready", tenant_id=tenant_id, model_id=model_id):
        raise HTTPException(status_code=500, detail="Failed to update model status.")
    return {"promoted": True, "model_id": model_id, "status": "ready"}


@router.post("/admin/models/{model_id:path}/deprecate", dependencies=[Depends(require_ops_key)])
def admin_deprecate_model(model_id: str, request: Request) -> dict:
    """Deprecate a model. Requires OPS key."""
    from app.storage.model_registry import ModelRegistry
    tenant_id = getattr(request.state, "tenant_id", "system") or "system"
    registry = ModelRegistry(request.app.state.data_dir)
    if not registry.deprecate_model(model_id, tenant_id):
        raise HTTPException(status_code=404, detail=f"Model '{model_id}' not found.")
    return {"deprecated": True, "model_id": model_id}


@router.get("/admin/models/jobs", dependencies=[Depends(require_ops_key)])
async def admin_list_jobs(request: Request) -> list[dict]:
    """List active OpenAI fine-tuning jobs with fresh status. Requires OPS key."""
    from app.services.finetune_orchestrator import FineTuneOrchestrator
    orch = FineTuneOrchestrator(request.app.state.data_dir)
    jobs = await orch.list_active_jobs()
    return [
        {
            "id": j.get("id"),
            "status": j.get("status"),
            "model": j.get("model"),
            "fine_tuned_model": j.get("fine_tuned_model"),
            "created_at": j.get("created_at"),
            "finished_at": j.get("finished_at"),
            "training_file": j.get("training_file"),
            "error": j.get("error"),
        }
        for j in jobs
    ]
