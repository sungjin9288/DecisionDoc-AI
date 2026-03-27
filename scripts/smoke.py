#!/usr/bin/env python3
import json
import os
import sys
from datetime import datetime, timedelta
from typing import Any
from uuid import uuid4

import httpx


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


def _is_enabled(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _tenant_headers() -> dict[str, str]:
    tenant_id = os.getenv("SMOKE_TENANT_ID", "").strip()
    if not tenant_id or tenant_id == "system":
        return {}
    return {"X-Tenant-ID": tenant_id}


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


_G2B_API_BASE = "https://apis.data.go.kr/1230000/ad/BidPublicInfoService"
_G2B_SEARCH_ENDPOINTS = (
    "getBidPblancListInfoServc",
    "getBidPblancListInfoThng",
    "getBidPblancListInfoCnstwk",
)


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

    import_target = url_or_number
    imported = client.post(
        f"{base_url}/projects/{project_id}/imports/g2b-opportunity",
        headers=auth_headers,
        json={"url_or_number": import_target},
    )
    import_body = _json_body(imported)
    if imported.status_code == 404:
        discovered_target = _discover_recent_g2b_bid_number(
            g2b_api_key,
            timeout_sec=float(client.timeout.connect or 30),
        )
        if discovered_target and discovered_target != import_target:
            import_target = discovered_target
            imported = client.post(
                f"{base_url}/projects/{project_id}/imports/g2b-opportunity",
                headers=auth_headers,
                json={"url_or_number": import_target},
            )
            import_body = _json_body(imported)
    if imported.status_code != 200:
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

    project_detail = client.get(f"{base_url}/projects/{project_id}", headers=auth_headers)
    project_detail_body = _assert_status("GET /projects/{id}", project_detail, 200)
    documents = project_detail_body.get("documents") or []
    decision_doc = next((doc for doc in documents if doc.get("bundle_id") == "bid_decision_kr"), None)
    if decision_doc is None:
        raise SystemExit("Procurement smoke generated bid_decision_kr but project detail did not auto-link the document")
    _print_result(
        "GET /projects/{id}",
        project_detail.status_code,
        extra=f"documents={len(documents)}",
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

        if include_procurement:
            if not procurement_url_or_number:
                raise SystemExit("Missing required environment variable: SMOKE_PROCUREMENT_URL_OR_NUMBER")
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
