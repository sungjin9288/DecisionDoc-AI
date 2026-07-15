"""Verify procurement document handoff, review, and remediation smoke paths."""

from __future__ import annotations

import json
import os
from typing import Any

import httpx

from scripts.smoke_support import (
    _assert_status,
    _json_body,
    _print_result,
    _print_skip,
    _read_stream_complete,
)


def _smoke_tenant_id() -> str:
    tenant_id = os.getenv("SMOKE_TENANT_ID", "").strip()
    return tenant_id or "system"


def _find_procurement_handoff_queue_item(
    summary_body: dict[str, Any],
    *,
    project_id: str,
) -> dict[str, Any] | None:
    procurement = summary_body.get("procurement")
    if not isinstance(procurement, dict):
        return None
    handoff = procurement.get("handoff")
    if not isinstance(handoff, dict):
        return None
    queue = handoff.get("remediation_queue")
    if not isinstance(queue, list):
        return None
    for item in queue:
        if not isinstance(item, dict):
            continue
        if str(item.get("project_id", "")).strip() == project_id:
            return item
    return None


def _validate_procurement_handoff_summary(
    client: httpx.Client,
    *,
    base_url: str,
    auth_headers: dict[str, str],
    project_id: str,
    expected_status: str,
) -> bool:
    tenant_id = _smoke_tenant_id()
    ops_key = os.getenv("SMOKE_OPS_KEY", "").strip()
    summary_endpoint = "/admin/locations/{tenant}/procurement-quality-summary"
    summary_headers = auth_headers
    if ops_key:
        summary_endpoint = "/admin/tenants/{tenant}/procurement-quality-summary"
        summary_headers = {"X-DecisionDoc-Ops-Key": ops_key}

    summary = client.get(
        f"{base_url}{summary_endpoint.format(tenant=tenant_id)}?focus_project_id={project_id}",
        headers=summary_headers,
    )
    if summary.status_code == 403 and not ops_key:
        _print_skip(
            "procurement handoff summary validation requires an admin smoke user or SMOKE_OPS_KEY"
        )
        return False
    summary_body = _assert_status(summary_endpoint, summary, 200)
    queue_item = _find_procurement_handoff_queue_item(
        summary_body, project_id=project_id
    )
    if queue_item is None:
        raise SystemExit(
            "Procurement handoff smoke could not find the project in "
            f"{summary_endpoint}"
        )
    actual_status = str(queue_item.get("handoff_status", "")).strip()
    if actual_status != expected_status:
        raise SystemExit(
            "Procurement handoff smoke expected "
            f"{expected_status}, got {actual_status or 'unknown'}"
        )
    _print_result(
        summary_endpoint,
        summary.status_code,
        extra=f"handoff_status={actual_status}",
    )
    return True


def _validate_decision_council_provenance(
    document: dict[str, Any],
    *,
    council_session: dict[str, Any],
    bundle_type: str,
) -> tuple[str, int, str]:
    session_id = str(council_session.get("session_id", "")).strip()
    session_revision = council_session.get("session_revision")
    direction = str(
        council_session.get("consensus", {}).get("recommended_direction", "")
    ).strip()
    if (
        not session_id
        or not isinstance(session_revision, int)
        or session_revision < 1
        or not direction
    ):
        raise SystemExit(
            "Decision Council smoke expected a structured council session response"
        )

    actual_session_id = str(
        document.get("source_decision_council_session_id", "")
    ).strip()
    actual_session_revision = document.get("source_decision_council_session_revision")
    actual_direction = str(
        document.get("source_decision_council_direction", "")
    ).strip()
    if actual_session_id != session_id:
        raise SystemExit(
            f"Procurement smoke expected project-linked {bundle_type} to keep "
            f"Decision Council session_id {session_id}, got {actual_session_id or 'unknown'}"
        )
    if actual_session_revision != session_revision:
        raise SystemExit(
            f"Procurement smoke expected project-linked {bundle_type} to keep "
            f"Decision Council revision {session_revision}, got {actual_session_revision!r}"
        )
    if actual_direction != direction:
        raise SystemExit(
            f"Procurement smoke expected project-linked {bundle_type} to keep "
            f"Decision Council direction {direction}, got {actual_direction or 'unknown'}"
        )
    return session_id, session_revision, direction


def _load_project_detail(
    client: httpx.Client,
    *,
    base_url: str,
    auth_headers: dict[str, str],
    project_id: str,
) -> dict[str, Any]:
    project_detail = client.get(
        f"{base_url}/projects/{project_id}", headers=auth_headers
    )
    return _assert_status("GET /projects/{id}", project_detail, 200)


def generate_bid_decision(
    client: httpx.Client,
    *,
    base_url: str,
    auth_headers: dict[str, str],
    project_id: str,
    provider: str,
    opportunity: dict[str, Any],
    council_body: dict[str, Any],
) -> tuple[dict[str, Any], str]:
    with client.stream(
        "POST",
        f"{base_url}/generate/stream",
        headers=auth_headers,
        json={
            "title": opportunity.get("title") or "Procurement Smoke",
            "goal": "입찰 참여 여부 판단 및 handoff 준비",
            "bundle_type": "bid_decision_kr",
            "project_id": project_id,
            "context": f"provider={provider}",
        },
    ) as streamed:
        if streamed.status_code != 200:
            body = _json_body(streamed)
            code = body.get("code", "unknown")
            raise SystemExit(
                f"POST /generate/stream procurement smoke expected 200, got {streamed.status_code} (code={code})"
            )
        completed = _read_stream_complete(streamed)
    _print_result(
        "POST /generate/stream procurement",
        200,
        request_id=str(completed.get("request_id", "")),
        bundle_id=str(completed.get("bundle_id", "")),
    )

    project_detail_body = _load_project_detail(
        client,
        base_url=base_url,
        auth_headers=auth_headers,
        project_id=project_id,
    )
    documents = project_detail_body.get("documents") or []
    decision_doc = next(
        (doc for doc in documents if doc.get("bundle_id") == "bid_decision_kr"), None
    )
    if decision_doc is None:
        raise SystemExit(
            "Procurement smoke generated bid_decision_kr but project detail did not auto-link the document"
        )
    _, _, provenance_direction = _validate_decision_council_provenance(
        decision_doc,
        council_session=council_body,
        bundle_type="bid_decision_kr",
    )
    _print_result(
        "GET /projects/{id}",
        200,
        extra=f"documents={len(documents)} council_direction={provenance_direction}",
    )
    return decision_doc, provenance_direction


def request_approval_and_share(
    client: httpx.Client,
    *,
    base_url: str,
    auth_headers: dict[str, str],
    username: str,
    decision_doc: dict[str, Any],
) -> None:
    try:
        approval_docs = json.loads(decision_doc.get("doc_snapshot") or "[]")
    except ValueError as exc:
        raise SystemExit(
            "Procurement smoke could not parse project document snapshot for approval flow"
        ) from exc

    approval = client.post(
        f"{base_url}/approvals",
        headers=auth_headers,
        json={
            "request_id": decision_doc.get("request_id", ""),
            "bundle_id": decision_doc.get("bundle_id", ""),
            "title": decision_doc.get("title", "") or "Procurement Smoke Approval",
            "drafter": username,
            "docs": approval_docs,
            "gov_options": decision_doc.get("gov_options"),
        },
    )
    approval_body = _assert_status("POST /approvals", approval, 200)
    _print_result(
        "POST /approvals",
        approval.status_code,
        extra=f"approval_id={approval_body.get('approval_id', '')}",
    )

    share = client.post(
        f"{base_url}/share",
        headers=auth_headers,
        json={
            "request_id": decision_doc.get("request_id", ""),
            "title": decision_doc.get("title", "") or "Procurement Smoke Share",
            "bundle_id": decision_doc.get("bundle_id", ""),
            "expires_days": 1,
        },
    )
    share_body = _assert_status("POST /share", share, 200)
    share_url = str(share_body.get("share_url", "")).strip()
    if not share_url.startswith("/shared/"):
        raise SystemExit(
            "POST /share returned an invalid share_url for procurement smoke"
        )
    _print_result(
        "POST /share",
        share.status_code,
        extra=f"share_id={share_body.get('share_id', '')}",
    )


def generate_proposal(
    client: httpx.Client,
    *,
    base_url: str,
    auth_headers: dict[str, str],
    project_id: str,
    provider: str,
    opportunity: dict[str, Any],
    council_body: dict[str, Any],
    provenance_direction: str,
    recommendation_value: str,
) -> None:
    with client.stream(
        "POST",
        f"{base_url}/generate/stream",
        headers=auth_headers,
        json={
            "title": opportunity.get("title") or "Procurement Smoke Proposal",
            "goal": "공공조달 제안서 drafting handoff smoke",
            "bundle_type": "proposal_kr",
            "project_id": project_id,
            "context": f"provider={provider}",
        },
    ) as proposal_streamed:
        if proposal_streamed.status_code != 200:
            body = _json_body(proposal_streamed)
            code = body.get("code", "unknown")
            raise SystemExit(
                "POST /generate/stream procurement proposal expected 200, "
                f"got {proposal_streamed.status_code} (code={code})"
            )
        proposal_completed = _read_stream_complete(proposal_streamed)
    _print_result(
        "POST /generate/stream procurement proposal",
        200,
        request_id=str(proposal_completed.get("request_id", "")),
        bundle_id=str(proposal_completed.get("bundle_id", "")),
    )
    proposal_project_detail = _load_project_detail(
        client,
        base_url=base_url,
        auth_headers=auth_headers,
        project_id=project_id,
    )
    proposal_documents = proposal_project_detail.get("documents") or []
    proposal_doc = next(
        (doc for doc in proposal_documents if doc.get("bundle_id") == "proposal_kr"),
        None,
    )
    if proposal_doc is None:
        raise SystemExit(
            "Procurement smoke generated proposal_kr but project detail did not auto-link the document"
        )
    _validate_decision_council_provenance(
        proposal_doc,
        council_session=council_body,
        bundle_type="proposal_kr",
    )
    _print_result(
        "GET /projects/{id} proposal",
        200,
        extra=f"proposal_docs={len(proposal_documents)} council_direction={provenance_direction}",
    )
    _print_skip(
        "procurement handoff smoke requires a NO_GO recommendation "
        f"(got {recommendation_value or 'unknown'})"
    )
    return


def run_no_go_remediation(
    client: httpx.Client,
    *,
    base_url: str,
    auth_headers: dict[str, str],
    project_id: str,
    provider: str,
    opportunity: dict[str, Any],
    council_body: dict[str, Any],
    council_direction: str,
    recommendation_value: str,
) -> None:
    downstream_payload = {
        "title": opportunity.get("title") or "Procurement Smoke",
        "goal": "NO_GO remediation handoff smoke",
        "bundle_type": "proposal_kr",
        "project_id": project_id,
        "context": f"provider={provider}",
    }
    blocked = client.post(
        f"{base_url}/generate/stream",
        headers=auth_headers,
        json=downstream_payload,
    )
    blocked_body = _assert_status(
        "POST /generate/stream procurement downstream blocked", blocked, 409
    )
    blocked_detail = blocked_body.get("detail")
    if not isinstance(blocked_detail, dict):
        raise SystemExit("Procurement handoff smoke expected structured blocked detail")
    blocked_code = str(blocked_detail.get("code", "")).strip()
    if blocked_code != "procurement_override_reason_required":
        raise SystemExit(
            "Procurement handoff smoke expected procurement_override_reason_required, "
            f"got {blocked_code or 'unknown'}"
        )
    _print_result(
        "POST /generate/stream procurement downstream blocked",
        blocked.status_code,
        extra=f"code={blocked_code}",
    )

    handoff_payload = {
        "source": "location_summary",
        "context_kind": "blocked_event",
        "bundle_type": "proposal_kr",
        "error_code": blocked_code,
        "recommendation": recommendation_value,
    }
    copied = client.post(
        f"{base_url}/projects/{project_id}/procurement/remediation-link-copy",
        headers=auth_headers,
        json=handoff_payload,
    )
    _assert_status("POST /projects/{id}/procurement/remediation-link-copy", copied, 200)
    _print_result(
        "POST /projects/{id}/procurement/remediation-link-copy",
        copied.status_code,
        extra="context=blocked_event",
    )

    handoff_summary_enabled = _validate_procurement_handoff_summary(
        client,
        base_url=base_url,
        auth_headers=auth_headers,
        project_id=project_id,
        expected_status="shared_not_opened",
    )

    opened = client.post(
        f"{base_url}/projects/{project_id}/procurement/remediation-link-open",
        headers=auth_headers,
        json={
            "source": "url_restore",
            "context_kind": "blocked_event",
            "bundle_type": "proposal_kr",
            "error_code": blocked_code,
            "recommendation": recommendation_value,
        },
    )
    _assert_status("POST /projects/{id}/procurement/remediation-link-open", opened, 200)
    _print_result(
        "POST /projects/{id}/procurement/remediation-link-open",
        opened.status_code,
        extra="context=blocked_event",
    )

    if handoff_summary_enabled:
        handoff_summary_enabled = _validate_procurement_handoff_summary(
            client,
            base_url=base_url,
            auth_headers=auth_headers,
            project_id=project_id,
            expected_status="opened_unresolved",
        )

    override_saved = client.post(
        f"{base_url}/projects/{project_id}/procurement/override-reason",
        headers=auth_headers,
        json={
            "reason": "Procurement smoke override reason for NO_GO downstream retry."
        },
    )
    _assert_status(
        "POST /projects/{id}/procurement/override-reason", override_saved, 200
    )
    _print_result(
        "POST /projects/{id}/procurement/override-reason",
        override_saved.status_code,
        extra="override_reason_saved=true",
    )

    with client.stream(
        "POST",
        f"{base_url}/generate/stream",
        headers=auth_headers,
        json=downstream_payload,
    ) as downstream_streamed:
        if downstream_streamed.status_code != 200:
            body = _json_body(downstream_streamed)
            code = body.get("code", "unknown")
            raise SystemExit(
                "POST /generate/stream procurement downstream retry expected 200, "
                f"got {downstream_streamed.status_code} (code={code})"
            )
        downstream_completed = _read_stream_complete(downstream_streamed)
    _print_result(
        "POST /generate/stream procurement downstream retry",
        200,
        request_id=str(downstream_completed.get("request_id", "")),
        bundle_id=str(downstream_completed.get("bundle_id", "")),
    )

    proposal_project_detail = _load_project_detail(
        client,
        base_url=base_url,
        auth_headers=auth_headers,
        project_id=project_id,
    )
    proposal_documents = proposal_project_detail.get("documents") or []
    proposal_doc = next(
        (doc for doc in proposal_documents if doc.get("bundle_id") == "proposal_kr"),
        None,
    )
    if proposal_doc is None:
        raise SystemExit(
            "Procurement smoke retried proposal_kr but project detail did not auto-link the document"
        )
    _validate_decision_council_provenance(
        proposal_doc,
        council_session=council_body,
        bundle_type="proposal_kr",
    )
    _print_result(
        "GET /projects/{id} proposal",
        200,
        extra=f"proposal_docs={len(proposal_documents)} council_direction={council_direction or 'unknown'}",
    )

    if handoff_summary_enabled:
        _validate_procurement_handoff_summary(
            client,
            base_url=base_url,
            auth_headers=auth_headers,
            project_id=project_id,
            expected_status="opened_resolved",
        )
