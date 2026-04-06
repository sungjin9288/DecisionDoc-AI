#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import httpx

from scripts.seed_procurement_stale_share_demo import (
    DEFAULT_BASE_URL,
    DEMO_PASSWORD,
    DEMO_TENANT_ID,
    DEMO_USERNAME,
)


@dataclass
class DemoVerificationResult:
    tenant_id: str
    project_id: str
    share_id: str
    bundle_id: str
    public_share_url: str
    internal_tenant_review_url: str
    internal_focused_review_url: str
    stale_status_copy: str


def _build_url(base_url: str, path: str) -> str:
    normalized_base = str(base_url or "").strip().rstrip("/")
    if not normalized_base:
        return path
    return f"{normalized_base}{path}"


def _json_body(response: Any) -> dict[str, Any]:
    try:
        payload = response.json()
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _assert_status(endpoint: str, response: Any, expected: int) -> dict[str, Any]:
    body = _json_body(response)
    if int(getattr(response, "status_code", 0)) != expected:
        detail = body.get("detail") if isinstance(body.get("detail"), dict) else body
        raise SystemExit(f"{endpoint} expected {expected}, got {response.status_code}: {detail}")
    return body


def _login(
    client: Any,
    *,
    base_url: str,
    tenant_id: str,
    username: str,
    password: str,
) -> str:
    headers = {"X-Tenant-ID": tenant_id} if tenant_id and tenant_id != "system" else {}
    response = client.post(
        _build_url(base_url, "/auth/login"),
        json={"username": username, "password": password},
        headers=headers,
    )
    body = _assert_status("POST /auth/login", response, 200)
    token = str(body.get("access_token", "")).strip()
    if not token:
        raise SystemExit("POST /auth/login missing access_token")
    return token


def verify_procurement_stale_share_demo(
    *,
    base_url: str = DEFAULT_BASE_URL,
    tenant_id: str = DEMO_TENANT_ID,
    username: str = DEMO_USERNAME,
    password: str = DEMO_PASSWORD,
    client: Any | None = None,
) -> DemoVerificationResult:
    owned_client = client is None
    active_client = client or httpx.Client(timeout=20.0, follow_redirects=True)
    try:
        token = _login(
            active_client,
            base_url=base_url,
            tenant_id=tenant_id,
            username=username,
            password=password,
        )
        headers = {"Authorization": f"Bearer {token}"}
        if tenant_id and tenant_id != "system":
            headers["X-Tenant-ID"] = tenant_id

        overview_response = active_client.get(
            _build_url(base_url, "/admin/locations?include_procurement=1"),
            headers=headers,
        )
        _assert_status("GET /admin/locations?include_procurement=1", overview_response, 200)
        try:
            locations = overview_response.json()
        except Exception as exc:
            raise SystemExit(
                f"GET /admin/locations?include_procurement=1 returned invalid JSON: {exc}"
            ) from exc
        if not isinstance(locations, list):
            raise SystemExit("GET /admin/locations?include_procurement=1 returned non-list payload")
        target_location = next(
            (
                item for item in locations
                if isinstance(item, dict)
                and str(item.get("tenant_id", "")).strip() == tenant_id
            ),
            None,
        )
        if target_location is None:
            raise SystemExit(f"Tenant {tenant_id!r} not found in locations overview")

        procurement_overview = target_location.get("procurement") or {}
        top_item = procurement_overview.get("top_stale_external_share_item")
        if not isinstance(top_item, dict):
            raise SystemExit("Locations overview missing top_stale_external_share_item")
        if procurement_overview.get("has_active_stale_share_exposure") is not True:
            raise SystemExit("Locations overview did not report active stale share exposure")

        project_id = str(top_item.get("project_id", "")).strip()
        share_id = str(top_item.get("share_id", "")).strip()
        bundle_id = str(top_item.get("bundle_type", "")).strip()
        if not project_id or not share_id or not bundle_id:
            raise SystemExit("Top stale share item missing project_id, share_id, or bundle_type")
        if bundle_id != "proposal_kr":
            raise SystemExit(f"Expected top stale share to be proposal_kr, got {bundle_id!r}")

        summary_response = active_client.get(
            _build_url(
                base_url,
                f"/admin/locations/{tenant_id}/procurement-quality-summary"
                f"?focus_project_id={project_id}&activity_actions=share.create",
            ),
            headers=headers,
        )
        summary_body = _assert_status(
            "GET /admin/locations/{tenant}/procurement-quality-summary",
            summary_response,
            200,
        )
        procurement_summary = summary_body.get("procurement") or {}
        focused_project = procurement_summary.get("focused_project") or {}
        focused_share_item = focused_project.get("stale_external_share_item")
        if not isinstance(focused_share_item, dict):
            raise SystemExit("Focused procurement summary missing stale_external_share_item")
        if str(focused_share_item.get("share_id", "")).strip() != share_id:
            raise SystemExit("Focused stale share item does not match overview top share")
        if str(focused_share_item.get("bundle_type", "")).strip() != bundle_id:
            raise SystemExit("Focused stale share item bundle_type does not match overview top share")

        council_response = active_client.get(
            _build_url(base_url, f"/projects/{project_id}/decision-council"),
            headers=headers,
        )
        council_body = _assert_status("GET /projects/{project_id}/decision-council", council_response, 200)
        if str(council_body.get("current_procurement_binding_status", "")).strip() != "stale":
            raise SystemExit("Decision Council is not stale; expected stale procurement binding")

        shared_response = active_client.get(_build_url(base_url, f"/shared/{share_id}"))
        if int(getattr(shared_response, "status_code", 0)) != 200:
            raise SystemExit(f"GET /shared/{share_id} expected 200, got {shared_response.status_code}")
        shared_html = str(getattr(shared_response, "text", "") or "")
        stale_copy = str(top_item.get("decision_council_document_status_copy", "")).strip()
        if stale_copy and stale_copy not in shared_html:
            raise SystemExit("Shared page does not render the expected stale council warning copy")

        base = str(base_url or "").strip().rstrip("/")
        tenant_review_url = _build_url(
            base,
            f"/?location_procurement_tenant={tenant_id}&location_procurement_activity_actions=share.create",
        )
        focused_review_url = _build_url(
            base,
            f"/?location_procurement_tenant={tenant_id}&location_procurement_activity_actions=share.create"
            f"&location_procurement_focus_project={project_id}",
        )

        return DemoVerificationResult(
            tenant_id=tenant_id,
            project_id=project_id,
            share_id=share_id,
            bundle_id=bundle_id,
            public_share_url=_build_url(base, f"/shared/{share_id}"),
            internal_tenant_review_url=tenant_review_url,
            internal_focused_review_url=focused_review_url,
            stale_status_copy=stale_copy,
        )
    finally:
        if owned_client:
            active_client.close()


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify the seeded procurement stale-share local demo against a running app.",
    )
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--tenant-id", default=DEMO_TENANT_ID)
    parser.add_argument("--username", default=DEMO_USERNAME)
    parser.add_argument("--password", default=DEMO_PASSWORD)
    return parser.parse_args(argv)


def _print_result(result: DemoVerificationResult) -> None:
    print("Verified procurement stale-share demo.")
    print("")
    print(f"tenant_id: {result.tenant_id}")
    print(f"project_id: {result.project_id}")
    print(f"share_id: {result.share_id}")
    print(f"bundle_id: {result.bundle_id}")
    print(f"stale_status_copy: {result.stale_status_copy}")
    print("")
    print("Links")
    print(f"  tenant review: {result.internal_tenant_review_url}")
    print(f"  focused review: {result.internal_focused_review_url}")
    print(f"  public share: {result.public_share_url}")


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv or sys.argv[1:])
    result = verify_procurement_stale_share_demo(
        base_url=str(args.base_url).strip() or DEFAULT_BASE_URL,
        tenant_id=str(args.tenant_id).strip() or DEMO_TENANT_ID,
        username=str(args.username).strip() or DEMO_USERNAME,
        password=str(args.password),
    )
    _print_result(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
