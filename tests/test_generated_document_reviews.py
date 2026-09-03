from __future__ import annotations

import json
import logging

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.services.auth_service import create_access_token
from app.services.generation_export_packet import (
    AUTHORITY_FALSE,
    PERSISTED_PACKET_SCHEMA,
    verify_generation_export_packet,
)
from app.storage.user_store import get_user_store
from app.storage.audit_store import AuditStore


API_HEADERS = {"X-DecisionDoc-Api-Key": "test-key"}
OPS_HEADERS = {"X-DecisionDoc-Ops-Key": "test-ops-key"}
DOCS = [{"doc_type": "adr", "markdown": "# 검토 문서\n\n결정 근거"}]


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DECISIONDOC_PROVIDER", "mock")
    monkeypatch.setenv("DECISIONDOC_ENV", "dev")
    monkeypatch.setenv("DECISIONDOC_STORAGE", "local")
    monkeypatch.setenv("DECISIONDOC_STATE_STORAGE", "local")
    monkeypatch.setenv("DECISIONDOC_API_KEY", "test-key")
    monkeypatch.setenv("DECISIONDOC_OPS_KEY", "test-ops-key")
    monkeypatch.setenv("JWT_SECRET_KEY", "generated-review-test-secret-key")
    with TestClient(create_app()) as test_client:
        yield test_client


def _login_existing(client: TestClient, username: str) -> dict[str, str]:
    response = client.post(
        "/auth/login",
        json={"username": username, "password": "Password123!"},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


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


def _project_document(
    client: TestClient,
    *,
    title: str = "검토 문서",
    docs: list[dict] | None = None,
):
    project = client.app.state.project_store.create(
        "system",
        name="Generated review project",
    )
    document = client.app.state.project_store.add_document(
        project.project_id,
        "request-generated-review",
        "bundle-generated-review",
        title,
        DOCS if docs is None else docs,
        tenant_id="system",
    )
    return project, document


def _create_review(
    client: TestClient,
    *,
    project_id: str,
    document_id: str,
    headers: dict[str, str],
    reviewer: str,
    formats: list[str] | None = None,
):
    return client.post(
        f"/projects/{project_id}/documents/{document_id}/generated-reviews",
        headers=headers,
        json={
            "reviewer": reviewer,
            "formats": formats or ["docx", "pdf"],
        },
    )


def test_admin_creates_persisted_review_packet_with_closed_authority_headers(client):
    admin_headers = _login(client, "review-admin", role="admin")
    _create_user(client, admin_headers, "review-member")
    project, document = _project_document(client)

    response = _create_review(
        client,
        project_id=project.project_id,
        document_id=document.doc_id,
        headers=admin_headers,
        reviewer="review-member",
    )

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-decisiondoc-review-status"] == "pending"
    assert response.headers["x-decisiondoc-reviewer-identity-bound"] == "true"
    assert response.headers["x-decisiondoc-review-only"] == "true"
    assert response.headers["x-decisiondoc-packet-persisted"] == "true"
    assert response.headers["x-decisiondoc-human-review-completed"] == "false"
    assert response.headers["x-decisiondoc-operational-approval"] == "false"
    assert response.headers["x-decisiondoc-replay"] == "false"
    for key in AUTHORITY_FALSE:
        header = "x-decisiondoc-authority-" + key.replace("_", "-")
        assert response.headers[header] == "false"

    evidence = verify_generation_export_packet(response.content)
    assert evidence["schema"] == PERSISTED_PACKET_SCHEMA
    assert response.headers["x-decisiondoc-packet-sha256"] == evidence["packet_sha256"]
    assert response.headers["x-decisiondoc-manifest-sha256"] == evidence["manifest_sha256"]
    assert response.headers["x-decisiondoc-artifact-count"] == "2"
    assert evidence["source"]["project_id"] == project.project_id
    assert evidence["source"]["project_document_id"] == document.doc_id

    records = client.app.state.generated_document_review_store.list_by_project(
        tenant_id="system", project_id=project.project_id
    )
    assert len(records) == 1
    assert records[0].reviewer_assignment["username"] == "review-member"
    assert records[0].creator_assignment["username"] == "review-admin"

    replay = _create_review(
        client,
        project_id=project.project_id,
        document_id=document.doc_id,
        headers=admin_headers,
        reviewer="review-member",
        formats=["pdf", "docx", "docx"],
    )
    assert replay.status_code == 200
    assert replay.content == response.content
    assert replay.headers["x-decisiondoc-replay"] == "true"


def test_creation_requires_current_session_role_and_authorized_assignment(client):
    admin_headers = _login(client, "access-admin", role="admin")
    member_headers = _create_user(client, admin_headers, "access-member")
    _create_user(client, admin_headers, "access-other")
    viewer_headers = _create_user(
        client, admin_headers, "access-viewer", role="viewer"
    )
    project, document = _project_document(client)
    member = get_user_store(
        "system",
        data_dir=client.app.state.data_dir,
        backend=client.app.state.state_backend,
    ).get_by_username("access-member")
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
        (OPS_HEADERS, 401),
        (sessionless_headers, 401),
        (viewer_headers, 403),
    ):
        response = _create_review(
            client,
            project_id=project.project_id,
            document_id=document.doc_id,
            headers=headers,
            reviewer="access-member",
        )
        assert response.status_code == expected_status

    foreign_assignment = _create_review(
        client,
        project_id=project.project_id,
        document_id=document.doc_id,
        headers=member_headers,
        reviewer="access-other",
    )
    assert foreign_assignment.status_code == 403
    assert client.app.state.generated_document_review_store.list_by_project(
        tenant_id="system", project_id=project.project_id
    ) == []

    own = _create_review(
        client,
        project_id=project.project_id,
        document_id=document.doc_id,
        headers=member_headers,
        reviewer="access-member",
    )
    assert own.status_code == 200


def test_creation_rejects_missing_inactive_or_unexportable_identity(client):
    admin_headers = _login(client, "failure-admin", role="admin")
    _create_user(client, admin_headers, "failure-member")
    _create_user(client, admin_headers, "failure-inactive")
    user_store = get_user_store(
        "system",
        data_dir=client.app.state.data_dir,
        backend=client.app.state.state_backend,
    )
    inactive = user_store.get_by_username("failure-inactive")
    assert inactive is not None
    user_store.update(inactive.user_id, is_active=False)
    project, document = _project_document(client)

    for reviewer in ("missing-reviewer", "failure-inactive"):
        response = _create_review(
            client,
            project_id=project.project_id,
            document_id=document.doc_id,
            headers=admin_headers,
            reviewer=reviewer,
        )
        assert response.status_code == 404

    invalid_format = _create_review(
        client,
        project_id=project.project_id,
        document_id=document.doc_id,
        headers=admin_headers,
        reviewer="failure-member",
        formats=["docx", "unknown"],
    )
    assert invalid_format.status_code == 400

    missing_document = _create_review(
        client,
        project_id=project.project_id,
        document_id="missing-document",
        headers=admin_headers,
        reviewer="failure-member",
    )
    assert missing_document.status_code == 404

    invalid_document = client.app.state.project_store.add_document(
        project.project_id,
        "request-invalid",
        "bundle-invalid",
        "Invalid document",
        [],
        tenant_id="system",
    )
    unexportable = _create_review(
        client,
        project_id=project.project_id,
        document_id=invalid_document.doc_id,
        headers=admin_headers,
        reviewer="failure-member",
    )
    assert unexportable.status_code == 409

    assert "document_snapshot" not in json.dumps(
        unexportable.json(), ensure_ascii=False
    )


def test_member_inbox_and_project_history_expose_only_safe_assigned_records(client):
    admin_headers = _login(client, "inbox-admin", role="admin")
    member_headers = _create_user(client, admin_headers, "inbox-member")
    _create_user(client, admin_headers, "inbox-other")
    assigned_project, assigned_document = _project_document(
        client, title="Assigned document"
    )
    foreign_project, foreign_document = _project_document(
        client, title="Foreign document"
    )
    assigned = _create_review(
        client,
        project_id=assigned_project.project_id,
        document_id=assigned_document.doc_id,
        headers=admin_headers,
        reviewer="inbox-member",
        formats=["docx"],
    )
    foreign = _create_review(
        client,
        project_id=foreign_project.project_id,
        document_id=foreign_document.doc_id,
        headers=admin_headers,
        reviewer="inbox-other",
        formats=["pdf"],
    )
    assert assigned.status_code == foreign.status_code == 200

    inbox = client.get("/generated-document-reviews", headers=member_headers)
    assert inbox.status_code == 200
    payload = inbox.json()
    assert payload["total"] == 1
    assert payload["limit"] == 50
    assert payload["offset"] == 0
    assert payload["has_more"] is False
    assert payload["access_scope"] == "assigned"
    assert payload["operational_approval"] is False
    review = payload["reviews"][0]
    assert review["project_id"] == assigned_project.project_id
    assert review["project_document_id"] == assigned_document.doc_id
    assert review["reviewer"] == {"username": "inbox-member", "role": "member"}
    assert review["assigned_to_current_user"] is True
    assert review["source_status"] == "current"
    serialized = json.dumps(payload, ensure_ascii=False)
    member = get_user_store(
        "system",
        data_dir=client.app.state.data_dir,
        backend=client.app.state.state_backend,
    ).get_by_username("inbox-member")
    assert member is not None
    for private_value in (
        "tenant_id",
        "creator_assignment",
        "reviewer_assignment",
        "doc_snapshot",
        member.user_id,
    ):
        assert private_value not in serialized

    own_history = client.get(
        f"/projects/{assigned_project.project_id}/generated-document-reviews",
        headers=member_headers,
    )
    assert own_history.status_code == 200
    assert own_history.json()["reviews"][0]["access_scope"] == "assigned"
    hidden_history = client.get(
        f"/projects/{foreign_project.project_id}/generated-document-reviews",
        headers=member_headers,
    )
    assert hidden_history.status_code == 404

    admin_inbox = client.get(
        "/generated-document-reviews?review_status=pending&limit=1&offset=1",
        headers=admin_headers,
    )
    assert admin_inbox.status_code == 200
    assert admin_inbox.json()["total"] == 2
    assert admin_inbox.json()["limit"] == 1
    assert admin_inbox.json()["offset"] == 1
    assert len(admin_inbox.json()["reviews"]) == 1

    for query in (
        "review_status=completed",
        "limit=0",
        "limit=51",
        "limit=not-a-number",
        "offset=-1",
    ):
        invalid = client.get(
            f"/generated-document-reviews?{query}", headers=admin_headers
        )
        assert invalid.status_code == 400


def test_download_authorizes_before_read_and_returns_exact_historical_packet(client, monkeypatch):
    admin_headers = _login(client, "download-admin", role="admin")
    member_headers = _create_user(client, admin_headers, "download-member")
    other_headers = _create_user(client, admin_headers, "download-other")
    project, document = _project_document(client, title="Historical review")
    created = _create_review(
        client,
        project_id=project.project_id,
        document_id=document.doc_id,
        headers=admin_headers,
        reviewer="download-member",
        formats=["docx"],
    )
    assert created.status_code == 200
    packet_sha256 = created.headers["x-decisiondoc-packet-sha256"]
    path = (
        f"/projects/{project.project_id}/generated-document-reviews/"
        f"{packet_sha256}/packet"
    )
    store = client.app.state.generated_document_review_store
    original_read = store.read_packet
    reads = 0

    def observe_read(*args, **kwargs):
        nonlocal reads
        reads += 1
        return original_read(*args, **kwargs)

    monkeypatch.setattr(store, "read_packet", observe_read)
    hidden = client.get(path, headers=other_headers)
    assert hidden.status_code == 404
    assert reads == 0

    current = client.get(path, headers=member_headers)
    assert current.status_code == 200
    assert current.content == created.content
    assert current.headers["x-decisiondoc-source-status"] == "current"
    assert current.headers["x-decisiondoc-replay"] == "true"
    assert reads == 1

    projects_path = "tenants/system/projects.json"
    projects = json.loads(client.app.state.state_backend.read_text(projects_path) or "[]")
    stored_document = next(
        item
        for item in projects[0]["documents"]
        if item["doc_id"] == document.doc_id
    )
    stored_document["title"] = "Changed after handoff"
    client.app.state.state_backend.write_text(
        projects_path, json.dumps(projects, ensure_ascii=False)
    )

    changed_history = client.get(
        f"/projects/{project.project_id}/generated-document-reviews",
        headers=member_headers,
    )
    assert changed_history.status_code == 200
    assert changed_history.json()["reviews"][0]["source_status"] == "changed"
    changed = client.get(path, headers=member_headers)
    assert changed.status_code == 200
    assert changed.content == created.content
    assert changed.headers["x-decisiondoc-source-status"] == "changed"

    client.app.state.project_store.remove_document(
        project.project_id,
        document.doc_id,
        tenant_id="system",
    )
    missing_history = client.get(
        f"/projects/{project.project_id}/generated-document-reviews",
        headers=member_headers,
    )
    assert missing_history.status_code == 200
    assert missing_history.json()["reviews"][0]["source_status"] == "missing"
    missing = client.get(path, headers=member_headers)
    assert missing.status_code == 200
    assert missing.content == created.content
    assert missing.headers["x-decisiondoc-source-status"] == "missing"


def test_read_routes_require_session_and_hide_foreign_or_missing_records(client):
    admin_headers = _login(client, "read-admin", role="admin")
    member_headers = _create_user(client, admin_headers, "read-member")
    viewer_headers = _create_user(client, admin_headers, "read-viewer", role="viewer")
    project, document = _project_document(client)
    created = _create_review(
        client,
        project_id=project.project_id,
        document_id=document.doc_id,
        headers=admin_headers,
        reviewer="read-member",
        formats=["docx"],
    )
    assert created.status_code == 200
    packet_sha256 = created.headers["x-decisiondoc-packet-sha256"]
    paths = (
        "/generated-document-reviews",
        f"/projects/{project.project_id}/generated-document-reviews",
        (
            f"/projects/{project.project_id}/generated-document-reviews/"
            f"{packet_sha256}/packet"
        ),
    )

    for headers, expected_status in (
        (API_HEADERS, 401),
        (OPS_HEADERS, 401),
        (viewer_headers, 403),
    ):
        for path in paths:
            assert client.get(path, headers=headers).status_code == expected_status

    missing = client.get(
        f"/projects/{project.project_id}/generated-document-reviews/"
        f"{'f' * 64}/packet",
        headers=member_headers,
    )
    assert missing.status_code == 404
    unsafe = client.get(
        f"/projects/{project.project_id}/generated-document-reviews/not-a-hash/packet",
        headers=member_headers,
    )
    assert unsafe.status_code == 404


def test_generated_review_emits_redacted_observability_and_audit_evidence(
    client, caplog
):
    admin_headers = _login(client, "audit-admin", role="admin")
    _create_user(client, admin_headers, "audit-member")
    project, document = _project_document(client)
    caplog.clear()
    caplog.set_level(logging.INFO)

    created = _create_review(
        client,
        project_id=project.project_id,
        document_id=document.doc_id,
        headers=admin_headers,
        reviewer="audit-member",
        formats=["docx"],
    )

    assert created.status_code == 200
    packet_sha256 = created.headers["x-decisiondoc-packet-sha256"]
    events = [record.msg for record in caplog.records if isinstance(record.msg, dict)]
    completed = next(
        event
        for event in events
        if event.get("event") == "request.completed"
        and event.get("path", "").endswith("/generated-reviews")
    )
    assert completed["generated_document_review_action"] == "prepared"
    assert completed["generated_document_review_project_id"] == project.project_id
    assert completed["generated_document_review_document_id"] == document.doc_id
    assert completed["generated_document_review_packet_sha256"] == packet_sha256
    assert completed["generated_document_review_status"] == "pending"
    assert completed["generated_document_review_access_scope"] == "tenant"
    assert completed["generated_document_review_replay"] is False

    audit = AuditStore(
        "system",
        data_dir=client.app.state.data_dir,
        backend=client.app.state.state_backend,
    ).query(filters={"action": "generated_document_review.prepare"})[-1]
    assert audit["user_id"] == ""
    assert audit["session_id"] == ""
    assert audit["ip_address"] == ""
    assert audit["user_agent"] == ""
    expected_detail = {
        "access_scope": "tenant",
        "document_id": document.doc_id,
        "operational_approval": False,
        "packet_sha256": packet_sha256,
        "project_id": project.project_id,
        "replay": False,
        "review_status": "pending",
        "source_status": "current",
    }
    for key, value in expected_detail.items():
        assert audit["detail"][key] == value
    serialized_audit = json.dumps(audit, ensure_ascii=False)
    assert "creator_assignment" not in serialized_audit
    assert "reviewer_assignment" not in serialized_audit
    assert "doc_snapshot" not in serialized_audit
