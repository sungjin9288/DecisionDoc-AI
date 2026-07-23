"""Session-bound access rules for project procurement reviews."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.schemas import (
    NormalizedProcurementOpportunity,
    ProcurementChecklistItem,
    ProcurementDecisionUpsert,
    ProcurementHardFilterResult,
    ProcurementRecommendation,
    ProcurementScoreBreakdownItem,
)
from app.services.auth_service import create_access_token
from app.storage.audit_store import AuditStore
from app.storage.user_store import get_user_store


API_HEADERS = {"X-DecisionDoc-Api-Key": "test-key"}


@pytest.fixture
def client(tmp_path, monkeypatch) -> TestClient:
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DECISIONDOC_PROVIDER", "mock")
    monkeypatch.setenv("DECISIONDOC_API_KEY", "test-key")
    monkeypatch.setenv("DECISIONDOC_OPS_KEY", "test-ops-key")
    monkeypatch.setenv("DECISIONDOC_PROCUREMENT_COPILOT_ENABLED", "1")
    return TestClient(create_app())


def _login(client: TestClient, username: str, *, role: str = "member") -> dict[str, str]:
    registered = client.post(
        "/auth/register",
        json={
            "username": username,
            "display_name": username,
            "email": f"{username}@example.com",
            "password": "Password123!",
            "role": role,
        },
    )
    assert registered.status_code == 200
    return _login_existing(client, username)


def _login_existing(client: TestClient, username: str) -> dict[str, str]:
    response = client.post(
        "/auth/login",
        json={"username": username, "password": "Password123!"},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _create_user(
    client: TestClient,
    admin_headers: dict[str, str],
    username: str,
    *,
    role: str = "member",
) -> dict[str, str]:
    response = client.post(
        "/admin/users",
        json={
            "username": username,
            "display_name": username,
            "email": f"{username}@example.com",
            "password": "Password123!",
            "role": role,
        },
        headers=admin_headers,
    )
    assert response.status_code == 200
    return _login_existing(client, username)


def _ready_project(client: TestClient, headers: dict[str, str], *, name: str) -> str:
    created = client.post(
        "/projects",
        json={"name": name, "fiscal_year": 2026},
        headers=headers,
    )
    assert created.status_code == 200
    project_id = created.json()["project_id"]
    client.app.state.procurement_store.upsert(
        ProcurementDecisionUpsert(
            project_id=project_id,
            tenant_id="system",
            opportunity=NormalizedProcurementOpportunity(
                source_kind="g2b",
                source_id=f"H121-{project_id}",
                title="H121 local review",
                issuer="DecisionDoc",
            ),
            hard_filters=[
                ProcurementHardFilterResult(
                    code="security_plan",
                    label="Security plan",
                    status="unknown",
                    blocking=True,
                    reason="Reviewer confirmation is required.",
                )
            ],
            score_breakdown=[
                ProcurementScoreBreakdownItem(
                    key="readiness",
                    label="Readiness",
                    score=72.0,
                    weight=1.0,
                    weighted_score=72.0,
                    summary="Local evidence is reviewable.",
                )
            ],
            soft_fit_score=72.0,
            soft_fit_status="scored",
            missing_data=["Security owner"],
            checklist_items=[
                ProcurementChecklistItem(
                    category="security_plan",
                    title="Assign security owner",
                    status="action_needed",
                    severity="high",
                    remediation_note="Assign before submission.",
                )
            ],
            recommendation=ProcurementRecommendation(
                value="CONDITIONAL_GO",
                summary="Review evidence is required.",
                evidence=["Local evidence"],
                missing_data=["Security owner"],
                remediation_notes=["Assign security owner"],
            ),
        )
    )
    return project_id


def _prepare_packet(
    client: TestClient,
    project_id: str,
    headers: dict[str, str],
    reviewer: str,
):
    return client.post(
        f"/projects/{project_id}/procurement/review-packet",
        json={"reviewer": reviewer},
        headers=headers,
    )


def test_packet_preparation_requires_bound_session_and_authorized_assignment(
    client: TestClient,
) -> None:
    admin_headers = _login(client, "h121-admin", role="admin")
    member_headers = _create_user(client, admin_headers, "h121-member")
    _create_user(client, admin_headers, "h121-other")
    viewer_headers = _create_user(client, admin_headers, "h121-viewer", role="viewer")
    project_id = _ready_project(client, admin_headers, name="H121 access")
    member = get_user_store("system", data_dir=client.app.state.data_dir).get_by_username(
        "h121-member"
    )
    assert member is not None
    sessionless_headers = {
        "Authorization": "Bearer "
        + create_access_token(
            member.user_id,
            member.tenant_id,
            member.role.value,
            member.username,
            credential_version=member.credential_version,
        )
    }

    for headers, expected_status in (
        (API_HEADERS, 401),
        ({"X-DecisionDoc-Ops-Key": "test-ops-key"}, 401),
        (sessionless_headers, 401),
        (viewer_headers, 403),
    ):
        response = _prepare_packet(client, project_id, headers, "h121-member")
        assert response.status_code == expected_status
        assert client.app.state.procurement_review_store.list_by_project(
            tenant_id="system", project_id=project_id
        ) == []

    foreign = _prepare_packet(client, project_id, member_headers, "h121-other")
    assert foreign.status_code == 403
    assert client.app.state.procurement_review_store.list_by_project(
        tenant_id="system", project_id=project_id
    ) == []

    own = _prepare_packet(client, project_id, member_headers, "h121-member")
    assert own.status_code == 200
    assert own.headers["x-decisiondoc-reviewer-identity-bound"] == "true"


def test_review_read_routes_reject_non_session_reviewer_credentials(
    client: TestClient,
) -> None:
    admin_headers = _login(client, "h121-admin", role="admin")
    member_headers = _create_user(client, admin_headers, "h121-member")
    viewer_headers = _create_user(client, admin_headers, "h121-viewer", role="viewer")
    project_id = _ready_project(client, admin_headers, name="H121 read matrix")
    packet = _prepare_packet(client, project_id, admin_headers, "h121-member")
    assert packet.status_code == 200
    packet_sha256 = packet.headers["x-decisiondoc-packet-sha256"]
    member = get_user_store("system", data_dir=client.app.state.data_dir).get_by_username(
        "h121-member"
    )
    assert member is not None
    sessionless_headers = {
        "Authorization": "Bearer "
        + create_access_token(
            member.user_id,
            member.tenant_id,
            member.role.value,
            member.username,
            credential_version=member.credential_version,
        )
    }

    paths = (
        "/procurement/reviews",
        f"/projects/{project_id}/procurement/reviews",
        (
            f"/projects/{project_id}/procurement/reviews/"
            f"{packet_sha256}/reviewed-package"
        ),
    )
    for headers, expected_status in (
        (API_HEADERS, 401),
        ({"X-DecisionDoc-Ops-Key": "test-ops-key"}, 401),
        (sessionless_headers, 401),
        (viewer_headers, 403),
    ):
        for path in paths:
            assert client.get(path, headers=headers).status_code == expected_status

    assert client.get("/procurement/reviews", headers=member_headers).status_code == 200


def test_member_inbox_and_project_history_only_expose_assigned_safe_projection(
    client: TestClient,
) -> None:
    admin_headers = _login(client, "h121-admin", role="admin")
    member_headers = _create_user(client, admin_headers, "h121-member")
    _create_user(client, admin_headers, "h121-other")
    first_project = _ready_project(client, admin_headers, name="Assigned project")
    second_project = _ready_project(client, admin_headers, name="Foreign project")
    first = _prepare_packet(client, first_project, admin_headers, "h121-member")
    second = _prepare_packet(client, second_project, admin_headers, "h121-other")
    assert first.status_code == second.status_code == 200

    inbox = client.get("/procurement/reviews", headers=member_headers)
    assert inbox.status_code == 200
    payload = inbox.json()
    assert payload["summary"] == {"total": 1, "pending": 1, "completed": 0}
    assert payload["total"] == 1
    review = payload["reviews"][0]
    assert review["project_id"] == first_project
    assert review["assigned_reviewer"] == "h121-member"
    assert review["assigned_to_current_user"] is True
    assert review["access_scope"] == "assigned"
    member = get_user_store(
        "system", data_dir=client.app.state.data_dir
    ).get_by_username("h121-member")
    assert member is not None
    serialized = json.dumps(payload, ensure_ascii=False)
    for private_field in (
        "tenant_id",
        "receipt",
        "rationale",
        "reviewer_assignment",
        "reviewer_attestation",
        "reviewer_attestation_sha256",
        member.user_id,
    ):
        assert private_field not in serialized

    foreign_query = client.get(
        "/procurement/reviews?reviewer=h121-other", headers=member_headers
    )
    assert foreign_query.status_code == 403
    foreign_project = client.get(
        f"/projects/{second_project}/procurement/reviews", headers=member_headers
    )
    assert foreign_project.status_code == 403
    own_project = client.get(
        f"/projects/{first_project}/procurement/reviews", headers=member_headers
    )
    assert own_project.status_code == 200
    assert own_project.json()["reviews"][0]["access_scope"] == "assigned"


def test_reviewed_package_read_is_assignee_or_admin_only_before_artifact_access(
    client: TestClient,
    monkeypatch,
) -> None:
    admin_headers = _login(client, "h121-admin", role="admin")
    member_headers = _create_user(client, admin_headers, "h121-member")
    other_headers = _create_user(client, admin_headers, "h121-other")
    project_id = _ready_project(client, admin_headers, name="Completed review")
    packet = _prepare_packet(client, project_id, admin_headers, "h121-member")
    assert packet.status_code == 200
    packet_sha256 = packet.headers["x-decisiondoc-packet-sha256"]
    completed = client.post(
        f"/projects/{project_id}/procurement/reviews/{packet_sha256}/complete",
        json={"decision": "accepted", "rationale": "Evidence checked."},
        headers=member_headers,
    )
    assert completed.status_code == 200

    original_read = client.app.state.procurement_review_store.read_reviewed_package
    artifact_reads = 0

    def observe_read(*args, **kwargs):
        nonlocal artifact_reads
        artifact_reads += 1
        return original_read(*args, **kwargs)

    monkeypatch.setattr(
        client.app.state.procurement_review_store,
        "read_reviewed_package",
        observe_read,
    )
    foreign = client.get(
        f"/projects/{project_id}/procurement/reviews/{packet_sha256}/reviewed-package",
        headers=other_headers,
    )
    assert foreign.status_code == 403
    assert artifact_reads == 0
    assert client.get(
        f"/projects/{project_id}/procurement/reviews/{packet_sha256}/reviewed-package",
        headers=member_headers,
    ).status_code == 200
    assert artifact_reads == 1
    assert client.get(
        f"/projects/{project_id}/procurement/reviews/{packet_sha256}/reviewed-package",
        headers=admin_headers,
    ).status_code == 200
    assert artifact_reads == 2


def test_member_inbox_filters_foreign_record_before_artifact_validation(
    client: TestClient,
) -> None:
    admin_headers = _login(client, "h121-admin", role="admin")
    member_headers = _create_user(client, admin_headers, "h121-member")
    other_headers = _create_user(client, admin_headers, "h121-other")
    own_project = _ready_project(client, admin_headers, name="Own evidence")
    foreign_project = _ready_project(client, admin_headers, name="Foreign evidence")
    own = _prepare_packet(client, own_project, admin_headers, "h121-member")
    foreign = _prepare_packet(client, foreign_project, admin_headers, "h121-other")
    assert own.status_code == foreign.status_code == 200

    foreign_packet_sha256 = foreign.headers["x-decisiondoc-packet-sha256"]
    completed = client.post(
        (
            f"/projects/{foreign_project}/procurement/reviews/"
            f"{foreign_packet_sha256}/complete"
        ),
        json={"decision": "accepted", "rationale": "Foreign evidence checked."},
        headers=other_headers,
    )
    assert completed.status_code == 200
    foreign_review_dir = (
        Path(client.app.state.data_dir)
        / "tenants"
        / "system"
        / "procurement_reviews"
        / foreign_project
        / foreign_packet_sha256
    )
    foreign_record = json.loads(
        (foreign_review_dir / "record.json").read_text(encoding="utf-8")
    )
    foreign_package_path = (
        foreign_review_dir
        / "reviewed_packages"
        / f"{foreign_record['reviewed_package_sha256']}.zip"
    )
    foreign_package_path.write_bytes(b"foreign tampered reviewed package")

    member_inbox = client.get("/procurement/reviews", headers=member_headers)
    assert member_inbox.status_code == 200
    assert member_inbox.json()["summary"] == {
        "total": 1,
        "pending": 1,
        "completed": 0,
    }
    assert member_inbox.json()["reviews"][0]["project_id"] == own_project
    own_history = client.get(
        f"/projects/{own_project}/procurement/reviews",
        headers=member_headers,
    )
    assert own_history.status_code == 200
    foreign_history = client.get(
        f"/projects/{foreign_project}/procurement/reviews",
        headers=member_headers,
    )
    assert foreign_history.status_code == 403

    probe_client = TestClient(client.app, raise_server_exceptions=False)
    admin_inbox = probe_client.get("/procurement/reviews", headers=admin_headers)
    assert admin_inbox.status_code == 500


def test_review_access_audit_keeps_scope_and_counts_without_target_identity(
    client: TestClient,
) -> None:
    admin_headers = _login(client, "h121-admin", role="admin")
    member_headers = _create_user(client, admin_headers, "h121-member")
    _create_user(client, admin_headers, "h121-other")
    project_id = _ready_project(client, admin_headers, name="Audited access")
    assert _prepare_packet(client, project_id, admin_headers, "h121-member").status_code == 200
    assert client.get("/procurement/reviews", headers=member_headers).status_code == 200

    other = get_user_store("system", data_dir=client.app.state.data_dir).get_by_username(
        "h121-other"
    )
    assert other is not None
    audit = AuditStore("system", data_dir=client.app.state.data_dir).find_latest_entry(
        actions=("procurement.review_inbox_view",),
        result="success",
    )
    assert audit is not None
    assert audit["detail"]["access_scope"] == "assigned"
    assert audit["detail"]["authorized_review_count"] == 1
    serialized = json.dumps(audit, ensure_ascii=False)
    assert other.user_id not in serialized
    assert "reviewer_attestation" not in serialized
    assert "rationale" not in serialized
    assert audit["session_id"] == ""
    assert audit["ip_address"] == ""
    assert audit["user_agent"] == ""
