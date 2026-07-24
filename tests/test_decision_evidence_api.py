from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.schemas import (
    GenerateRequest,
    NormalizedProcurementOpportunity,
    ProcurementChecklistItem,
    ProcurementDecisionUpsert,
    ProcurementHardFilterResult,
    ProcurementRecommendation,
    ProcurementScoreBreakdownItem,
)
from app.services.decision_evidence_service import procurement_requirement_node_ids
from app.storage.audit_store import AuditStore


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


def _ready_project(
    client: TestClient,
    headers: dict[str, str],
    *,
    name: str,
) -> str:
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
                source_id=f"EVIDENCE-{project_id}",
                title="Decision Evidence Map project",
                issuer="DecisionDoc",
            ),
            hard_filters=[
                ProcurementHardFilterResult(
                    code="security_plan",
                    label="Security plan",
                    status="unknown",
                    blocking=True,
                    reason="Reviewer evidence is required.",
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
                summary="Proceed only after evidence review.",
                evidence=["Local deterministic evidence"],
                missing_data=["Security owner"],
                remediation_notes=["Assign security owner"],
            ),
        )
    )
    return project_id


def _prepare_review(
    client: TestClient,
    project_id: str,
    admin_headers: dict[str, str],
    *,
    reviewer: str,
) -> str:
    response = client.post(
        f"/projects/{project_id}/procurement/review-packet",
        json={"reviewer": reviewer},
        headers=admin_headers,
    )
    assert response.status_code == 200
    return response.headers["x-decisiondoc-packet-sha256"]


def test_decision_evidence_map_requires_bound_reviewer_and_redacts_reviews(
    client: TestClient,
) -> None:
    admin_headers = _login(client, "evidence-admin", role="admin")
    assigned_headers = _create_user(client, admin_headers, "evidence-member")
    other_headers = _create_user(client, admin_headers, "evidence-other")
    viewer_headers = _create_user(
        client,
        admin_headers,
        "evidence-viewer",
        role="viewer",
    )
    project_id = _ready_project(
        client,
        admin_headers,
        name="Evidence authorization",
    )
    packet_sha256 = _prepare_review(
        client,
        project_id,
        admin_headers,
        reviewer="evidence-member",
    )
    path = f"/projects/{project_id}/decision-evidence-map"

    assert client.get(path, headers=API_HEADERS).status_code == 401
    assert client.get(path, headers=viewer_headers).status_code == 403
    assert client.get(path, headers=other_headers).status_code == 404
    assert client.get(
        "/projects/not-a-project/decision-evidence-map",
        headers=other_headers,
    ).status_code == 404

    unassigned_project_id = _ready_project(
        client,
        admin_headers,
        name="Unassigned evidence authorization",
    )
    assert client.get(
        f"/projects/{unassigned_project_id}/decision-evidence-map",
        headers=other_headers,
    ).status_code == 404
    assert client.get(
        f"/projects/{unassigned_project_id}/decision-evidence-map",
        headers=admin_headers,
    ).status_code == 200

    response = client.get(path, headers=assigned_headers)
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-decisiondoc-operational-approval"] == "false"

    payload = response.json()
    assert payload["contract_version"] == "decision_evidence_map.v1"
    assert payload["project_id"] == project_id
    assert payload["read_only"] is True
    assert payload["snapshot_atomic"] is False
    assert payload["authority"] == {
        "mutation": False,
        "approval": False,
        "export_execution": False,
        "provider_call": False,
        "bid_submission": False,
        "legal_contractual_commitment": False,
    }
    assert any(
        node["node_id"] == f"review:{packet_sha256}"
        for node in payload["nodes"]
    )
    serialized = json.dumps(payload, ensure_ascii=False)
    for forbidden in (
        "tenant_id",
        "receipt",
        "rationale",
        "reviewer_assignment",
        "reviewer_attestation",
        "assigned_reviewer",
        "completed_by",
        "reviewer_session_bound",
    ):
        assert forbidden not in serialized


def test_decision_evidence_map_is_tenant_bound_and_bundle_limited(
    client: TestClient,
) -> None:
    admin_headers = _login(client, "tenant-admin", role="admin")
    foreign_project = client.app.state.project_store.create(
        "foreign-tenant",
        "Foreign evidence",
        fiscal_year=2026,
    )

    hidden = client.get(
        f"/projects/{foreign_project.project_id}/decision-evidence-map",
        headers=admin_headers,
    )
    assert hidden.status_code == 404

    project_id = _ready_project(client, admin_headers, name="Bundle contract")
    invalid = client.get(
        f"/projects/{project_id}/decision-evidence-map?bundle_type=unknown_bundle",
        headers=admin_headers,
    )
    assert invalid.status_code == 422


def test_decision_evidence_map_audit_keeps_review_network_and_session_redacted(
    client: TestClient,
) -> None:
    admin_headers = _login(client, "audit-admin", role="admin")
    project_id = _ready_project(client, admin_headers, name="Audit projection")

    response = client.get(
        f"/projects/{project_id}/decision-evidence-map",
        headers={**admin_headers, "User-Agent": "private-client"},
    )
    assert response.status_code == 200

    records = AuditStore(
        "system",
        data_dir=client.app.state.data_dir,
        backend=client.app.state.state_backend,
    ).query(filters={"action": "procurement.review_evidence_map_view"})
    assert len(records) == 1
    record = records[0]
    assert record["resource_id"] == project_id
    assert record["session_id"] == ""
    assert record["ip_address"] == ""
    assert record["user_agent"] == ""
    assert record["detail"]["access_scope"] == "tenant"
    assert record["detail"]["procurement_review_operational_approval"] is False


def test_generation_persists_canonical_requirement_references_for_projection(
    client: TestClient,
) -> None:
    admin_headers = _login(client, "generation-admin", role="admin")
    project_id = _ready_project(
        client,
        admin_headers,
        name="Generation evidence lineage",
    )
    procurement = client.app.state.procurement_store.get(
        project_id,
        tenant_id="system",
    )
    expected_refs = procurement_requirement_node_ids(procurement)

    result = client.app.state.service.generate_documents(
        GenerateRequest(
            title="Evidence-bound proposal",
            goal="Persist exact procurement requirement references.",
            bundle_type="proposal_kr",
            project_id=project_id,
        ),
        request_id="req-evidence-lineage",
        tenant_id="system",
    )
    assert result["metadata"]["decision_evidence_refs"] == expected_refs

    document = client.app.state.project_store.add_document(
        project_id=project_id,
        request_id="req-evidence-lineage",
        bundle_id="proposal_kr",
        title="Evidence-bound proposal",
        docs=result["docs"],
        tenant_id="system",
        source_evidence_refs=result["metadata"]["decision_evidence_refs"],
    )
    reloaded = client.app.state.project_store.get(
        project_id,
        tenant_id="system",
    )
    assert reloaded is not None
    assert reloaded.documents[-1].doc_id == document.doc_id
    assert reloaded.documents[-1].source_evidence_refs == expected_refs

    map_response = client.get(
        f"/projects/{project_id}/decision-evidence-map",
        headers=admin_headers,
    )
    assert map_response.status_code == 200
    coverage = map_response.json()["coverage"]
    assert coverage["explicit"] == len(expected_refs)
    assert coverage["missing"] == 0
