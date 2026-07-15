"""Run the deployed public-procurement smoke workflow."""

from __future__ import annotations

import os
from datetime import datetime, timedelta
from typing import Any
from uuid import uuid4

import httpx

from scripts.procurement_smoke_handoff import (
    generate_bid_decision,
    generate_proposal,
    request_approval_and_share,
    run_no_go_remediation,
)
from scripts.smoke_support import (
    _assert_status,
    _json_body,
    _print_result,
    _print_skip,
    _tenant_headers,
)


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
    items = payload.get("response", {}).get("body", {}).get("items") or []
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
            response = active_client.get(
                f"{_G2B_API_BASE}/{endpoint_name}", params=params
            )
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


def _create_procurement_project(
    client: httpx.Client,
    *,
    base_url: str,
    auth_headers: dict[str, str],
) -> str:
    project = client.post(
        f"{base_url}/projects",
        headers=auth_headers,
        json={"name": "Procurement Smoke", "fiscal_year": 2026},
    )
    project_body = _assert_status("POST /projects", project, 200)
    project_id = str(project_body.get("project_id", ""))
    if not project_id:
        raise SystemExit("POST /projects missing project_id for procurement smoke")
    _print_result(
        "POST /projects", project.status_code, extra=f"project_id={project_id}"
    )
    return project_id


def _import_procurement_opportunity(
    client: httpx.Client,
    *,
    base_url: str,
    auth_headers: dict[str, str],
    project_id: str,
    configured_target: str,
    g2b_api_key: str,
) -> dict[str, Any] | None:
    client_timeout = float(client.timeout.connect or 30)
    import_target = _resolve_initial_procurement_import_target(
        configured_target=configured_target,
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
    return opportunity


def _evaluate_procurement(
    client: httpx.Client,
    *,
    base_url: str,
    auth_headers: dict[str, str],
    project_id: str,
) -> str:
    evaluated = client.post(
        f"{base_url}/projects/{project_id}/procurement/evaluate",
        headers=auth_headers,
    )
    evaluated_body = _assert_status(
        "POST /projects/{id}/procurement/evaluate", evaluated, 200
    )
    _print_result(
        "POST /projects/{id}/procurement/evaluate",
        evaluated.status_code,
        extra=f"soft_fit_score={evaluated_body.get('decision', {}).get('soft_fit_score', '')}",
    )

    recommended = client.post(
        f"{base_url}/projects/{project_id}/procurement/recommend",
        headers=auth_headers,
    )
    recommended_body = _assert_status(
        "POST /projects/{id}/procurement/recommend", recommended, 200
    )
    recommendation = recommended_body.get("recommendation") or {}
    _print_result(
        "POST /projects/{id}/procurement/recommend",
        recommended.status_code,
        extra=f"recommendation={recommendation.get('value', '')}",
    )
    recommendation_value = str(recommendation.get("value", "")).strip()
    return recommendation_value


def _run_decision_council(
    client: httpx.Client,
    *,
    base_url: str,
    auth_headers: dict[str, str],
    project_id: str,
    provider: str,
    recommendation_value: str,
) -> tuple[dict[str, Any], str]:
    council = client.post(
        f"{base_url}/projects/{project_id}/decision-council/run",
        headers=auth_headers,
        json={
            "goal": "입찰 참여 여부 판단과 bid_decision_kr drafting 방향을 정리한다.",
            "context": f"provider={provider}; recommendation={recommendation_value or 'unknown'}",
            "constraints": "기존 approval/share/export 흐름은 그대로 유지한다.",
        },
    )
    council_body = _assert_status(
        "POST /projects/{id}/decision-council/run", council, 200
    )
    council_session_id = str(council_body.get("session_id", "")).strip()
    council_revision = council_body.get("session_revision")
    council_direction = str(
        council_body.get("consensus", {}).get("recommended_direction", "")
    ).strip()
    if not council_session_id:
        raise SystemExit(
            "POST /projects/{id}/decision-council/run missing session_id for procurement smoke"
        )
    _print_result(
        "POST /projects/{id}/decision-council/run",
        council.status_code,
        extra=(
            f"session_id={council_session_id} "
            f"revision={council_revision!r} "
            f"direction={council_direction or 'unknown'}"
        ),
    )
    return council_body, council_direction


def run_procurement_smoke(
    client: httpx.Client,
    *,
    base_url: str,
    api_key: str,
    provider: str,
    url_or_number: str,
) -> None:
    token, username = _register_or_login(client, base_url)
    auth_headers = _auth_headers(api_key, token)

    version = client.get(f"{base_url}/version")
    version_body = _assert_status("GET /version", version, 200)
    if not bool(version_body.get("features", {}).get("procurement_copilot")):
        raise SystemExit(
            "Procurement smoke requested but /version.features.procurement_copilot is false"
        )

    project_id = _create_procurement_project(
        client,
        base_url=base_url,
        auth_headers=auth_headers,
    )
    opportunity = _import_procurement_opportunity(
        client,
        base_url=base_url,
        auth_headers=auth_headers,
        project_id=project_id,
        configured_target=url_or_number,
        g2b_api_key=os.getenv("G2B_API_KEY", "").strip(),
    )
    if opportunity is None:
        return

    recommendation_value = _evaluate_procurement(
        client,
        base_url=base_url,
        auth_headers=auth_headers,
        project_id=project_id,
    )
    council_body, council_direction = _run_decision_council(
        client,
        base_url=base_url,
        auth_headers=auth_headers,
        project_id=project_id,
        provider=provider,
        recommendation_value=recommendation_value,
    )
    decision_doc, provenance_direction = generate_bid_decision(
        client,
        base_url=base_url,
        auth_headers=auth_headers,
        project_id=project_id,
        provider=provider,
        opportunity=opportunity,
        council_body=council_body,
    )
    request_approval_and_share(
        client,
        base_url=base_url,
        auth_headers=auth_headers,
        username=username,
        decision_doc=decision_doc,
    )

    if recommendation_value != "NO_GO":
        generate_proposal(
            client,
            base_url=base_url,
            auth_headers=auth_headers,
            project_id=project_id,
            provider=provider,
            opportunity=opportunity,
            council_body=council_body,
            provenance_direction=provenance_direction,
            recommendation_value=recommendation_value,
        )
        return

    run_no_go_remediation(
        client,
        base_url=base_url,
        auth_headers=auth_headers,
        project_id=project_id,
        provider=provider,
        opportunity=opportunity,
        council_body=council_body,
        council_direction=council_direction,
        recommendation_value=recommendation_value,
    )
