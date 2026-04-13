#!/usr/bin/env python3
import json
import os
import sys
from datetime import datetime, timedelta
from typing import Any
from uuid import uuid4

import httpx

_DOCUMENT_UPLOAD_SAMPLE = (
    b"Project title: Smoke Upload\n"
    b"Goal: Validate uploaded document generation\n"
    b"Constraints: Keep auditability first.\n"
)


def _required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise SystemExit(f"Missing required environment variable: {name}")
    return value


def _json_body(response: httpx.Response) -> dict[str, Any]:
    try:
        data = response.json()
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def _assert_status(endpoint: str, response: httpx.Response, expected: int) -> dict[str, Any]:
    body = _json_body(response)
    if response.status_code != expected:
        code = body.get("code", "unknown")
        raise SystemExit(f"{endpoint} expected {expected}, got {response.status_code} (code={code})")
    return body


def _print_result(endpoint: str, status_code: int, request_id: str = "", bundle_id: str = "", extra: str = "") -> None:
    parts = [f"{endpoint} -> {status_code}"]
    if request_id:
        parts.append(f"request_id={request_id}")
    if bundle_id:
        parts.append(f"bundle_id={bundle_id}")
    if extra:
        parts.append(extra)
    print(" ".join(parts))


def _print_skip(reason: str) -> None:
    print(f"SKIP {reason}")


def _is_enabled(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _tenant_headers() -> dict[str, str]:
    tenant_id = os.getenv("SMOKE_TENANT_ID", "").strip()
    if not tenant_id or tenant_id == "system":
        return {}
    return {"X-Tenant-ID": tenant_id}


def _smoke_tenant_id() -> str:
    tenant_id = os.getenv("SMOKE_TENANT_ID", "").strip()
    return tenant_id or "system"


def _auth_headers(api_key: str, token: str) -> dict[str, str]:
    return {
        "X-DecisionDoc-Api-Key": api_key,
        "Authorization": f"Bearer {token}",
        **_tenant_headers(),
    }


def _register_or_login(client: httpx.Client, base_url: str) -> tuple[str, str]:
    username = os.getenv("PROCUREMENT_SMOKE_USERNAME", "").strip()
    password = os.getenv("PROCUREMENT_SMOKE_PASSWORD", "").strip()
    public_headers = _tenant_headers()

    if username and password:
        login = client.post(
            f"{base_url}/auth/login",
            headers=public_headers,
            json={"username": username, "password": password},
        )
        body = _assert_status("POST /auth/login", login, 200)
        token = str(body.get("access_token", "")).strip()
        if not token:
            raise SystemExit("POST /auth/login missing access_token")
        return token, username

    generated_username = f"proc_smoke_{uuid4().hex[:10]}"
    generated_password = f"ProcurementSmoke1!{uuid4().hex[:8]}"
    register = client.post(
        f"{base_url}/auth/register",
        headers=public_headers,
        json={
            "username": generated_username,
            "display_name": "Procurement Smoke",
            "email": f"{generated_username}@example.invalid",
            "password": generated_password,
        },
    )
    if register.status_code == 403:
        raise SystemExit(
            "Procurement smoke could not bootstrap a user because the tenant already has users. "
            "Set PROCUREMENT_SMOKE_USERNAME and PROCUREMENT_SMOKE_PASSWORD for this stage."
        )
    body = _assert_status("POST /auth/register", register, 200)
    token = str(body.get("access_token", "")).strip()
    if not token:
        raise SystemExit("POST /auth/register missing access_token")
    return token, generated_username


def _read_stream_complete(response: httpx.Response) -> dict[str, Any]:
    buffer = ""
    for chunk in response.iter_text():
        buffer += chunk
        while "\n\n" in buffer:
            part, buffer = buffer.split("\n\n", 1)
            event_type = ""
            payload_raw = ""
            for line in part.splitlines():
                if line.startswith("event: "):
                    event_type = line[7:].strip()
                elif line.startswith("data: "):
                    payload_raw += line[6:]
            if not payload_raw:
                continue
            try:
                payload = json.loads(payload_raw)
            except ValueError:
                continue
            if event_type == "complete":
                return payload if isinstance(payload, dict) else {}
            if event_type == "error":
                message = payload.get("message", "stream generation failed") if isinstance(payload, dict) else "stream generation failed"
                raise SystemExit(f"POST /generate/stream procurement smoke failed: {message}")
    raise SystemExit("POST /generate/stream procurement smoke ended without a complete event")


def _document_upload_files() -> list[tuple[str, tuple[str, bytes, str]]]:
    return [
        (
            "files",
            (
                "smoke-upload.txt",
                _DOCUMENT_UPLOAD_SAMPLE,
                "text/plain",
            ),
        )
    ]


def _run_document_upload_smoke(
    client: httpx.Client,
    *,
    base_url: str,
    api_key: str,
) -> None:
    data = {
        "doc_types": "adr,onepager",
        "goal": "Verify uploaded document generation",
    }

    no_auth = client.post(
        f"{base_url}/generate/from-documents",
        data=data,
        files=_document_upload_files(),
    )
    no_auth_body = _assert_status("POST /generate/from-documents (no key)", no_auth, 401)
    if no_auth_body.get("code") != "UNAUTHORIZED":
        raise SystemExit("POST /generate/from-documents (no key) did not return UNAUTHORIZED")
    _print_result(
        "POST /generate/from-documents (no key)",
        no_auth.status_code,
        request_id=str(no_auth_body.get("request_id", "")),
    )

    uploaded = client.post(
        f"{base_url}/generate/from-documents",
        headers={"X-DecisionDoc-Api-Key": api_key},
        data=data,
        files=_document_upload_files(),
    )
    uploaded_body = _assert_status("POST /generate/from-documents (auth)", uploaded, 200)
    uploaded_bundle_id = str(uploaded_body.get("bundle_id", ""))
    uploaded_request_id = str(uploaded_body.get("request_id", ""))
    docs = uploaded_body.get("docs")
    if not uploaded_bundle_id:
        raise SystemExit("POST /generate/from-documents (auth) missing bundle_id")
    if not isinstance(docs, list) or not docs:
        raise SystemExit("POST /generate/from-documents (auth) missing docs")
    actual_doc_types = [str(doc.get("doc_type", "")).strip() for doc in docs if isinstance(doc, dict)]
    if actual_doc_types != ["adr", "onepager"]:
        raise SystemExit(
            "POST /generate/from-documents (auth) returned unexpected doc_types: "
            f"{actual_doc_types!r}"
        )
    _print_result(
        "POST /generate/from-documents (auth)",
        uploaded.status_code,
        request_id=uploaded_request_id,
        bundle_id=uploaded_bundle_id,
        extra=f"files=1 docs={len(docs)}",
    )


_G2B_API_BASE = "https://apis.data.go.kr/1230000/ad/BidPublicInfoService"
_G2B_SEARCH_ENDPOINTS = (
    "getBidPblancListInfoServc",
    "getBidPblancListInfoThng",
    "getBidPblancListInfoCnstwk",
)


def _build_g2b_detail_url(bid_number: str) -> str:
    bid_number = bid_number.strip()
    if not bid_number:
        return ""
    return f"https://www.g2b.go.kr/pt/menu/selectSubFrame.do?bidNtceNo={bid_number}"


def _extract_g2b_items(payload: dict[str, Any]) -> list[dict[str, Any]]:
    items = (
        payload.get("response", {})
        .get("body", {})
        .get("items")
        or []
    )
    if isinstance(items, dict):
        return [items]
    return [item for item in items if isinstance(item, dict)]


def _discover_recent_g2b_bid_number(
    api_key: str,
    *,
    timeout_sec: float,
    now: datetime | None = None,
    client: httpx.Client | None = None,
) -> str | None:
    if not api_key:
        return None

    end_dt = now or datetime.now()
    start_dt = end_dt - timedelta(days=7)
    created_client = client is None
    active_client = client or httpx.Client(timeout=timeout_sec)

    try:
        for endpoint_name in _G2B_SEARCH_ENDPOINTS:
            params = {
                "serviceKey": api_key,
                "type": "json",
                "numOfRows": 10,
                "pageNo": 1,
                "inqryDiv": 1,
                "inqryBgnDt": start_dt.strftime("%Y%m%d0000"),
                "inqryEndDt": end_dt.strftime("%Y%m%d2359"),
            }
            response = active_client.get(f"{_G2B_API_BASE}/{endpoint_name}", params=params)
            response.raise_for_status()
            try:
                payload = response.json()
            except ValueError:
                continue
            for item in _extract_g2b_items(payload):
                bid_number = str(item.get("bidNtceNo", "")).strip()
                if bid_number:
                    return bid_number
    except Exception:
        return None
    finally:
        if created_client:
            active_client.close()

    return None


def _resolve_initial_procurement_import_target(
    *,
    configured_target: str,
    g2b_api_key: str,
    timeout_sec: float,
) -> str:
    normalized_target = str(configured_target or "").strip()
    if normalized_target:
        return normalized_target

    discovered_target = _discover_recent_g2b_bid_number(
        g2b_api_key,
        timeout_sec=timeout_sec,
    )
    if discovered_target:
        return discovered_target

    _print_skip(
        "procurement smoke could not discover a recent live G2B opportunity "
        "because no configured target was provided"
    )
    return ""


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
        _print_skip("procurement handoff summary validation requires an admin smoke user or SMOKE_OPS_KEY")
        return False
    summary_body = _assert_status(summary_endpoint, summary, 200)
    queue_item = _find_procurement_handoff_queue_item(summary_body, project_id=project_id)
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
    if not session_id or not isinstance(session_revision, int) or session_revision < 1 or not direction:
        raise SystemExit("Decision Council smoke expected a structured council session response")

    actual_session_id = str(document.get("source_decision_council_session_id", "")).strip()
    actual_session_revision = document.get("source_decision_council_session_revision")
    actual_direction = str(document.get("source_decision_council_direction", "")).strip()
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
    project_detail = client.get(f"{base_url}/projects/{project_id}", headers=auth_headers)
    return _assert_status("GET /projects/{id}", project_detail, 200)


def _run_procurement_smoke(
    client: httpx.Client,
    *,
    base_url: str,
    api_key: str,
    provider: str,
    url_or_number: str,
) -> None:
    token, username = _register_or_login(client, base_url)
    auth_headers = _auth_headers(api_key, token)
    g2b_api_key = os.getenv("G2B_API_KEY", "").strip()
    version = client.get(f"{base_url}/version")
    version_body = _assert_status("GET /version", version, 200)
    if not bool(version_body.get("features", {}).get("procurement_copilot")):
        raise SystemExit("Procurement smoke requested but /version.features.procurement_copilot is false")

    project = client.post(
        f"{base_url}/projects",
        headers=auth_headers,
        json={"name": "Procurement Smoke", "fiscal_year": 2026},
    )
    project_body = _assert_status("POST /projects", project, 200)
    project_id = str(project_body.get("project_id", ""))
    if not project_id:
        raise SystemExit("POST /projects missing project_id for procurement smoke")
    _print_result("POST /projects", project.status_code, extra=f"project_id={project_id}")

    client_timeout = float(client.timeout.connect or 30)
    import_target = _resolve_initial_procurement_import_target(
        configured_target=url_or_number,
        g2b_api_key=g2b_api_key,
        timeout_sec=client_timeout,
    )
    if not import_target:
        return

    imported = client.post(
        f"{base_url}/projects/{project_id}/imports/g2b-opportunity",
        headers=auth_headers,
        json={"url_or_number": import_target},
    )
    import_body = _json_body(imported)
    if imported.status_code == 404:
        retry_targets: list[str] = []

        detail_url_target = ""
        if not import_target.startswith("http"):
            detail_url_target = _build_g2b_detail_url(import_target)
            if detail_url_target:
                retry_targets.append(detail_url_target)

        discovered_target = _discover_recent_g2b_bid_number(
            g2b_api_key,
            timeout_sec=client_timeout,
        )
        if discovered_target and discovered_target != import_target:
            retry_targets.append(discovered_target)
            discovered_detail_url = _build_g2b_detail_url(discovered_target)
            if discovered_detail_url:
                retry_targets.append(discovered_detail_url)

        seen_targets: set[str] = {import_target}
        for candidate in retry_targets:
            if not candidate or candidate in seen_targets:
                continue
            seen_targets.add(candidate)
            import_target = candidate
            imported = client.post(
                f"{base_url}/projects/{project_id}/imports/g2b-opportunity",
                headers=auth_headers,
                json={"url_or_number": import_target},
            )
            import_body = _json_body(imported)
            if imported.status_code == 200:
                break
    if imported.status_code != 200:
        if imported.status_code == 404:
            _print_skip(
                "procurement smoke import could not resolve a live G2B opportunity "
                f"after fallback targets (target={import_target})"
            )
            return
        code = import_body.get("code", "unknown")
        raise SystemExit(
            f"POST /projects/{{id}}/imports/g2b-opportunity expected 200, "
            f"got {imported.status_code} (code={code})"
        )
    opportunity = import_body.get("opportunity") or {}
    _print_result(
        "POST /projects/{id}/imports/g2b-opportunity",
        imported.status_code,
        extra=f"title={opportunity.get('title', '')} target={import_target}",
    )

    evaluated = client.post(
        f"{base_url}/projects/{project_id}/procurement/evaluate",
        headers=auth_headers,
    )
    evaluated_body = _assert_status("POST /projects/{id}/procurement/evaluate", evaluated, 200)
    _print_result(
        "POST /projects/{id}/procurement/evaluate",
        evaluated.status_code,
        extra=f"soft_fit_score={evaluated_body.get('decision', {}).get('soft_fit_score', '')}",
    )

    recommended = client.post(
        f"{base_url}/projects/{project_id}/procurement/recommend",
        headers=auth_headers,
    )
    recommended_body = _assert_status("POST /projects/{id}/procurement/recommend", recommended, 200)
    recommendation = recommended_body.get("recommendation") or {}
    _print_result(
        "POST /projects/{id}/procurement/recommend",
        recommended.status_code,
        extra=f"recommendation={recommendation.get('value', '')}",
    )
    recommendation_value = str(recommendation.get("value", "")).strip()

    council = client.post(
        f"{base_url}/projects/{project_id}/decision-council/run",
        headers=auth_headers,
        json={
            "goal": "입찰 참여 여부 판단과 bid_decision_kr drafting 방향을 정리한다.",
            "context": f"provider={provider}; recommendation={recommendation_value or 'unknown'}",
            "constraints": "기존 approval/share/export 흐름은 그대로 유지한다.",
        },
    )
    council_body = _assert_status("POST /projects/{id}/decision-council/run", council, 200)
    council_session_id = str(council_body.get("session_id", "")).strip()
    council_revision = council_body.get("session_revision")
    council_direction = str(
        council_body.get("consensus", {}).get("recommended_direction", "")
    ).strip()
    if not council_session_id:
        raise SystemExit("POST /projects/{id}/decision-council/run missing session_id for procurement smoke")
    _print_result(
        "POST /projects/{id}/decision-council/run",
        council.status_code,
        extra=(
            f"session_id={council_session_id} "
            f"revision={council_revision!r} "
            f"direction={council_direction or 'unknown'}"
        ),
    )

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
    decision_doc = next((doc for doc in documents if doc.get("bundle_id") == "bid_decision_kr"), None)
    if decision_doc is None:
        raise SystemExit("Procurement smoke generated bid_decision_kr but project detail did not auto-link the document")
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
    try:
        approval_docs = json.loads(decision_doc.get("doc_snapshot") or "[]")
    except ValueError as exc:
        raise SystemExit("Procurement smoke could not parse project document snapshot for approval flow") from exc

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
        raise SystemExit("POST /share returned an invalid share_url for procurement smoke")
    _print_result(
        "POST /share",
        share.status_code,
        extra=f"share_id={share_body.get('share_id', '')}",
    )

    if recommendation_value != "NO_GO":
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
        proposal_doc = next((doc for doc in proposal_documents if doc.get("bundle_id") == "proposal_kr"), None)
        if proposal_doc is None:
            raise SystemExit("Procurement smoke generated proposal_kr but project detail did not auto-link the document")
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
    blocked_body = _assert_status("POST /generate/stream procurement downstream blocked", blocked, 409)
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
        json={"reason": "Procurement smoke override reason for NO_GO downstream retry."},
    )
    _assert_status("POST /projects/{id}/procurement/override-reason", override_saved, 200)
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
    proposal_doc = next((doc for doc in proposal_documents if doc.get("bundle_id") == "proposal_kr"), None)
    if proposal_doc is None:
        raise SystemExit("Procurement smoke retried proposal_kr but project detail did not auto-link the document")
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


def main() -> int:
    base_url = _required_env("SMOKE_BASE_URL").rstrip("/")
    api_key = _required_env("SMOKE_API_KEY")
    provider = os.getenv("SMOKE_PROVIDER", "mock").strip() or "mock"
    timeout_sec = float(os.getenv("SMOKE_TIMEOUT_SEC", "30"))
    include_procurement = _is_enabled(os.getenv("SMOKE_INCLUDE_PROCUREMENT", "0"))
    procurement_url_or_number = os.getenv("SMOKE_PROCUREMENT_URL_OR_NUMBER", "").strip()

    payload = {
        "title": "Smoke Check",
        "goal": "Verify deployed generate endpoints",
        "context": f"provider={provider}",
    }

    with httpx.Client(timeout=timeout_sec) as client:
        health = client.get(f"{base_url}/health")
        _assert_status("GET /health", health, 200)
        _print_result("GET /health", health.status_code, request_id=health.headers.get("X-Request-Id", ""))

        no_auth = client.post(f"{base_url}/generate", json=payload)
        no_auth_body = _assert_status("POST /generate (no key)", no_auth, 401)
        if no_auth_body.get("code") != "UNAUTHORIZED":
            raise SystemExit("POST /generate (no key) did not return UNAUTHORIZED")
        _print_result(
            "POST /generate (no key)",
            no_auth.status_code,
            request_id=str(no_auth_body.get("request_id", "")),
        )

        api_key_headers = {"X-DecisionDoc-Api-Key": api_key}
        generate = client.post(f"{base_url}/generate", headers=api_key_headers, json=payload)
        generate_body = _assert_status("POST /generate (auth)", generate, 200)
        generate_bundle_id = str(generate_body.get("bundle_id", ""))
        generate_request_id = str(generate_body.get("request_id", ""))
        if not generate_bundle_id:
            raise SystemExit("POST /generate (auth) missing bundle_id")
        _print_result(
            "POST /generate (auth)",
            generate.status_code,
            request_id=generate_request_id,
            bundle_id=generate_bundle_id,
        )

        export = client.post(f"{base_url}/generate/export", headers=api_key_headers, json=payload)
        export_body = _assert_status("POST /generate/export (auth)", export, 200)
        export_bundle_id = str(export_body.get("bundle_id", ""))
        export_request_id = str(export_body.get("request_id", ""))
        files = export_body.get("files")
        if not export_bundle_id:
            raise SystemExit("POST /generate/export (auth) missing bundle_id")
        if not isinstance(files, list) or not files:
            raise SystemExit("POST /generate/export (auth) missing export files")
        _print_result(
            "POST /generate/export (auth)",
            export.status_code,
            request_id=export_request_id,
            bundle_id=export_bundle_id,
            extra=f"files={len(files)}",
        )

        _run_document_upload_smoke(
            client,
            base_url=base_url,
            api_key=api_key,
        )

        if include_procurement:
            _run_procurement_smoke(
                client,
                base_url=base_url,
                api_key=api_key,
                provider=provider,
                url_or_number=procurement_url_or_number,
            )

    print("Smoke completed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
