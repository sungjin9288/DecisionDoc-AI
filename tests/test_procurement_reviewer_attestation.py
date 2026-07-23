from __future__ import annotations

import hashlib
import io
import json
import zipfile
from dataclasses import asdict
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.services.procurement_decision_package.reviewer_attestation import (
    REVIEWER_ATTESTATION_FIELD_ORDER,
    attestation_sha256,
    build_procurement_reviewer_attestation,
    canonical_attestation_bytes,
    validate_procurement_reviewer_attestation,
)
from app.storage.procurement_review_store import ProcurementReviewStore
from app.storage.procurement_review_models import record_from_dict
from app.storage.audit_store import AuditStore
from app.main import create_app
from app.schemas import (
    NormalizedProcurementOpportunity,
    ProcurementChecklistItem,
    ProcurementDecisionUpsert,
    ProcurementHardFilterResult,
    ProcurementRecommendation,
    ProcurementScoreBreakdownItem,
)


TENANT_ID = "tenant-h120"
PROJECT_ID = "project-h120"
PACKET = b"packet evidence"
PACKET_SHA256 = hashlib.sha256(PACKET).hexdigest()


def _receipt(*, status: str = "pending") -> dict:
    return {
        "schema_version": "decisiondoc.procurement_review_receipt.v1",
        "status": status,
        "packet_sha256": PACKET_SHA256,
        "packet_size_bytes": len(PACKET),
        "packet_schema_version": "decisiondoc.procurement_review_packet.v1",
        "package_id": "pkg-h120",
        "recommendation": "CONDITIONAL_GO",
        "reviewer": "assigned-reviewer",
        "decision": "accepted" if status == "completed" else None,
        "rationale": "Evidence reviewed." if status == "completed" else None,
        "reviewed_at": "2026-07-23T00:01:00Z" if status == "completed" else None,
        "authorization_boundary": "explicit",
        "operational_approval": False,
    }


def test_reviewer_attestation_is_canonical_and_non_authorizing() -> None:
    attestation = build_procurement_reviewer_attestation(
        tenant_id=TENANT_ID,
        project_id=PROJECT_ID,
        packet_sha256=PACKET_SHA256,
        completed_receipt_sha256="a" * 64,
        decision="accepted",
        reviewed_at="2026-07-23T00:01:00Z",
        reviewer_user_id="stable-user-id",
        reviewer_username="renamed-reviewer",
        reviewer_role="member",
    )

    assert tuple(attestation) == REVIEWER_ATTESTATION_FIELD_ORDER
    assert attestation["reviewer"] == {
        "user_id": "stable-user-id",
        "username": "renamed-reviewer",
        "role": "member",
    }
    assert all(
        attestation[field] is False
        for field in (
            "approval_granted",
            "operational_approval",
            "bid_submission_authorized",
            "legal_commitment_authorized",
            "contractual_commitment_authorized",
        )
    )
    assert b"session" not in canonical_attestation_bytes(attestation)
    assert (
        attestation_sha256(attestation)
        == hashlib.sha256(canonical_attestation_bytes(attestation)).hexdigest()
    )


def test_identity_bound_store_requires_matching_attestation_and_keeps_v1_readable(
    tmp_path,
) -> None:
    store = ProcurementReviewStore(base_dir=str(tmp_path))
    legacy, _ = store.prepare(
        tenant_id=TENANT_ID,
        project_id="legacy-project",
        packet_content=PACKET,
        receipt=_receipt(),
        prepared_at="2026-07-23T00:00:00Z",
    )
    assert legacy.to_public_dict()["reviewer_identity_bound"] is False

    upgraded, created = store.prepare(
        tenant_id=TENANT_ID,
        project_id="legacy-project",
        packet_content=PACKET,
        receipt=_receipt(),
        prepared_at="2026-07-23T00:00:00Z",
        reviewer_assignment={
            "user_id": "stable-user-id",
            "username": "assigned-reviewer",
        },
    )
    assert created is False
    assert upgraded.reviewer_assignment == {
        "user_id": "stable-user-id",
        "username": "assigned-reviewer",
    }
    assert upgraded.reviewer_identity_bound is True
    assert upgraded.reviewer_session_bound is False

    record, created = store.prepare(
        tenant_id=TENANT_ID,
        project_id=PROJECT_ID,
        packet_content=PACKET,
        receipt=_receipt(),
        prepared_at="2026-07-23T00:00:00Z",
        reviewer_assignment={
            "user_id": "stable-user-id",
            "username": "assigned-reviewer",
        },
    )
    assert created is True
    assert record.reviewer_identity_bound is True
    completed = _receipt(status="completed")
    receipt_sha256 = hashlib.sha256(
        (json.dumps(completed, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    ).hexdigest()
    attestation = build_procurement_reviewer_attestation(
        tenant_id=TENANT_ID,
        project_id=PROJECT_ID,
        packet_sha256=PACKET_SHA256,
        completed_receipt_sha256=receipt_sha256,
        decision="accepted",
        reviewed_at=completed["reviewed_at"],
        reviewer_user_id="stable-user-id",
        reviewer_username="renamed-reviewer",
        reviewer_role="member",
    )
    completed_record = store.complete(
        tenant_id=TENANT_ID,
        project_id=PROJECT_ID,
        packet_sha256=PACKET_SHA256,
        current=record,
        completed_receipt=completed,
        reviewed_package_content=b"reviewed-package",
        reviewer_attestation=attestation,
    )
    assert (
        completed_record.reviewer_attestation["reviewer"]["username"]
        == "renamed-reviewer"
    )
    assert completed_record.reviewer_session_bound is True

    drifted = asdict(completed_record)
    drifted["receipt"] = {
        **completed_record.receipt,
        "rationale": "changed after attestation",
    }
    with pytest.raises(ValueError, match="binding is inconsistent"):
        record_from_dict(drifted)

    forged = {**attestation, "completed_receipt_sha256": "b" * 64}
    with pytest.raises(
        ValueError, match="requires reviewer attestation|binding is inconsistent"
    ):
        store.complete(
            tenant_id=TENANT_ID,
            project_id=PROJECT_ID,
            packet_sha256=PACKET_SHA256,
            current=record,
            completed_receipt=completed,
            reviewed_package_content=b"other-reviewed-package",
            reviewer_attestation=forged,
        )

    wrong_identity = {
        **asdict(completed_record),
        "reviewer_attestation": {
            **attestation,
            "reviewer": {
                **attestation["reviewer"],
                "user_id": "different-user-id",
            },
        },
    }
    wrong_identity["reviewer_attestation_sha256"] = attestation_sha256(
        wrong_identity["reviewer_attestation"]
    )
    with pytest.raises(ValueError, match="identity is inconsistent"):
        record_from_dict(wrong_identity)


def test_reviewer_attestation_rejects_sensitive_or_authorizing_contract_drift() -> None:
    attestation = build_procurement_reviewer_attestation(
        tenant_id=TENANT_ID,
        project_id=PROJECT_ID,
        packet_sha256=PACKET_SHA256,
        completed_receipt_sha256="a" * 64,
        decision="accepted",
        reviewed_at="2026-07-23T00:01:00Z",
        reviewer_user_id="stable-user-id",
        reviewer_username="assigned-reviewer",
        reviewer_role="admin",
    )
    with pytest.raises(ValueError, match="fields are invalid"):
        validate_procurement_reviewer_attestation(
            {**attestation, "session_id": "secret"}
        )
    with pytest.raises(ValueError, match="authority is invalid"):
        validate_procurement_reviewer_attestation(
            {**attestation, "approval_granted": True}
        )


@pytest.fixture
def client(tmp_path, monkeypatch) -> TestClient:
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DECISIONDOC_PROVIDER", "mock")
    monkeypatch.setenv("DECISIONDOC_API_KEY", "test-key")
    monkeypatch.setenv("DECISIONDOC_OPS_KEY", "test-ops-key")
    monkeypatch.setenv("DECISIONDOC_PROCUREMENT_COPILOT_ENABLED", "1")
    return TestClient(create_app())


def _login(
    client: TestClient,
    username: str,
    *,
    register_headers: dict[str, str] | None = None,
    role: str = "member",
) -> dict[str, str]:
    registered = client.post(
        "/auth/register",
        json={
            "username": username,
            "display_name": username,
            "email": f"{username}@example.com",
            "password": "Password123!",
            "role": role,
        },
        headers=register_headers,
    )
    assert registered.status_code == 200
    login = client.post(
        "/auth/login",
        json={"username": username, "password": "Password123!"},
    )
    assert login.status_code == 200
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


def _ready_project(client: TestClient, headers: dict[str, str]) -> str:
    created = client.post(
        "/projects",
        json={"name": "H120 review", "fiscal_year": 2026},
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
                source_id="H120-001",
                title="H120",
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


def test_project_completion_requires_assigned_session_principal_and_records_rename(
    client: TestClient,
) -> None:
    assigned_headers = _login(client, "assigned-reviewer", role="admin")
    created_other = client.post(
        "/admin/users",
        json={
            "username": "other-reviewer",
            "display_name": "other-reviewer",
            "email": "other-reviewer@example.com",
            "password": "Password123!",
            "role": "member",
        },
        headers=assigned_headers,
    )
    assert created_other.status_code == 200
    created_viewer = client.post(
        "/admin/users",
        json={
            "username": "viewer-reviewer",
            "display_name": "viewer-reviewer",
            "email": "viewer-reviewer@example.com",
            "password": "Password123!",
            "role": "viewer",
        },
        headers=assigned_headers,
    )
    assert created_viewer.status_code == 200
    other_login = client.post(
        "/auth/login",
        json={"username": "other-reviewer", "password": "Password123!"},
    )
    assert other_login.status_code == 200
    other_headers = {"Authorization": f"Bearer {other_login.json()['access_token']}"}
    viewer_login = client.post(
        "/auth/login",
        json={"username": "viewer-reviewer", "password": "Password123!"},
    )
    assert viewer_login.status_code == 200
    viewer_headers = {"Authorization": f"Bearer {viewer_login.json()['access_token']}"}
    project_id = _ready_project(client, assigned_headers)

    packet = client.post(
        f"/projects/{project_id}/procurement/review-packet",
        json={"reviewer": "assigned-reviewer"},
        headers=assigned_headers,
    )
    assert packet.status_code == 200
    assert packet.headers["x-decisiondoc-reviewer-identity-bound"] == "true"
    packet_sha256 = packet.headers["x-decisiondoc-packet-sha256"]

    api_key_only = client.post(
        f"/projects/{project_id}/procurement/reviews/not-a-sha/complete",
        json={"decision": "accepted", "rationale": "ignored"},
        headers={"X-DecisionDoc-Api-Key": "test-key"},
    )
    assert api_key_only.status_code == 401
    ops_key_only = client.post(
        f"/projects/{project_id}/procurement/reviews/not-a-sha/complete",
        json={"decision": "accepted", "rationale": "ignored"},
        headers={"X-DecisionDoc-Ops-Key": "test-ops-key"},
    )
    assert ops_key_only.status_code == 401
    from app.services.auth_service import create_access_token
    from app.storage.user_store import get_user_store

    user = get_user_store("system", data_dir=client.app.state.data_dir).get_by_username(
        "assigned-reviewer"
    )
    assert user is not None
    sessionless_headers = {
        "Authorization": "Bearer "
        + create_access_token(
            user.user_id,
            user.tenant_id,
            user.role.value,
            user.username,
            credential_version=user.credential_version,
        )
    }
    sessionless = client.post(
        f"/projects/{project_id}/procurement/reviews/not-a-sha/complete",
        json={"decision": "accepted", "rationale": "ignored"},
        headers=sessionless_headers,
    )
    assert sessionless.status_code == 401
    viewer = client.post(
        f"/projects/{project_id}/procurement/reviews/not-a-sha/complete",
        json={"decision": "accepted", "rationale": "ignored"},
        headers=viewer_headers,
    )
    assert viewer.status_code == 403
    mismatch = client.post(
        f"/projects/{project_id}/procurement/reviews/{packet_sha256}/complete",
        json={"decision": "accepted", "rationale": "other user"},
        headers=other_headers,
    )
    assert mismatch.status_code == 409
    assert mismatch.json()["detail"]["code"] == "procurement_reviewer_mismatch"

    users_path = client.app.state.data_dir / "tenants" / "system" / "users.json"
    users = json.loads(users_path.read_text(encoding="utf-8"))
    users[user.user_id]["username"] = "renamed-reviewer"
    users_path.write_text(
        json.dumps(users, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    completed = client.post(
        f"/projects/{project_id}/procurement/reviews/{packet_sha256}/complete",
        json={"decision": "accepted", "rationale": "packet evidence checked"},
        headers=assigned_headers,
    )
    assert completed.status_code == 200, completed.json()
    assert completed.headers["x-decisiondoc-reviewer-identity-bound"] == "true"
    from app.services.procurement_decision_package.reviewed_package import (
        verify_procurement_reviewed_package,
    )

    with pytest.raises(ValueError, match="trusted scope is required"):
        verify_procurement_reviewed_package(completed.content)
    for expected_scope in (
        {
            "expected_tenant_id": "different-tenant",
            "expected_project_id": project_id,
            "expected_reviewer_user_id": user.user_id,
        },
        {
            "expected_tenant_id": "system",
            "expected_project_id": "different-project",
            "expected_reviewer_user_id": user.user_id,
        },
        {
            "expected_tenant_id": "system",
            "expected_project_id": project_id,
            "expected_reviewer_user_id": "different-user",
        },
    ):
        with pytest.raises(ValueError, match="binding is inconsistent"):
            verify_procurement_reviewed_package(
                completed.content,
                **expected_scope,
            )
    assert verify_procurement_reviewed_package(
        completed.content,
        expected_tenant_id="system",
        expected_project_id=project_id,
        expected_reviewer_user_id=user.user_id,
    )["package_verified"] is True
    replayed = client.post(
        f"/projects/{project_id}/procurement/reviews/{packet_sha256}/complete",
        json={
            "decision": "accepted",
            "rationale": "packet evidence checked",
        },
        headers=assigned_headers,
    )
    assert replayed.status_code == 200
    assert replayed.content == completed.content
    changed_replay = client.post(
        f"/projects/{project_id}/procurement/reviews/{packet_sha256}/complete",
        json={
            "decision": "accepted",
            "rationale": "different rationale",
        },
        headers=assigned_headers,
    )
    assert changed_replay.status_code == 409
    assert (
        changed_replay.json()["detail"]["code"]
        == "procurement_review_already_completed"
    )
    from app.services.procurement_decision_package.reviewed_package import (
        REVIEWED_PACKAGE_V2_ENTRY_ORDER,
    )

    with zipfile.ZipFile(io.BytesIO(completed.content)) as archive:
        assert archive.namelist() == list(REVIEWED_PACKAGE_V2_ENTRY_ORDER)
        packaged_attestation = json.loads(
            archive.read("procurement_reviewer_attestation.json")
        )
        manifest = json.loads(
            archive.read("reviewed_package_manifest.json")
        )
    assert packaged_attestation["reviewer"]["username"] == "renamed-reviewer"
    assert "session_id" not in packaged_attestation
    attestation_content = canonical_attestation_bytes(packaged_attestation)
    assert (
        manifest["source"]["reviewer_attestation_sha256"]
        == hashlib.sha256(attestation_content).hexdigest()
    )
    assert manifest["source"]["reviewer_attestation_size_bytes"] == len(
        attestation_content
    )
    reviews = client.get(
        f"/projects/{project_id}/procurement/reviews",
        headers=assigned_headers,
    ).json()["reviews"]
    assert reviews[0]["reviewer_assignment"]["user_id"] == user.user_id
    assert reviews[0]["reviewer_attestation"]["reviewer"]["user_id"] == user.user_id
    assert (
        reviews[0]["reviewer_attestation"]["reviewer"]["username"] == "renamed-reviewer"
    )
    audit = AuditStore("system", data_dir=client.app.state.data_dir).find_latest_entry(
        actions=("procurement.review_completed",),
        result="success",
    )
    assert audit is not None
    assert audit["user_id"] == user.user_id
    assert audit["detail"]["procurement_review_packet_sha256"] == packet_sha256
    assert audit["detail"]["review_decision"] == "accepted"
    assert audit["detail"]["reviewer_identity_bound"] is True
    assert (
        audit["detail"]["reviewed_package_sha256"]
        == hashlib.sha256(completed.content).hexdigest()
    )
    serialized = json.dumps(audit, ensure_ascii=False)
    assert "packet evidence checked" not in serialized
    assert audit["session_id"] == ""
    assert audit["ip_address"] == ""
    assert audit["user_agent"] == ""


def test_completed_v1_review_remains_listable_and_downloadable(
    client: TestClient,
) -> None:
    reviewer_headers = _login(client, "legacy-review-admin", role="admin")
    project_id = _ready_project(client, reviewer_headers)
    decision_record = client.app.state.procurement_store.get(
        project_id,
        tenant_id="system",
    )
    assert decision_record is not None
    from app.services.procurement_decision_package.review_packet import (
        build_project_procurement_review_packet,
    )
    from app.services.procurement_decision_package.review_receipt import (
        build_pending_procurement_review_receipt,
        record_procurement_review_decision,
    )
    from app.services.procurement_decision_package.reviewed_package import (
        build_procurement_reviewed_package,
    )

    packet = build_project_procurement_review_packet(
        decision_record,
        reviewer_owner="legacy-review-admin",
    )
    pending_receipt = build_pending_procurement_review_receipt(packet.content)
    review_record, created = client.app.state.procurement_review_store.prepare(
        tenant_id="system",
        project_id=project_id,
        packet_content=packet.content,
        receipt=pending_receipt,
        prepared_at="2026-07-23T00:00:00Z",
    )
    assert created is True
    completed_receipt = record_procurement_review_decision(
        pending_receipt,
        packet.content,
        reviewer="legacy-review-admin",
        decision="accepted",
        rationale="Legacy review remains readable.",
        reviewed_at="2026-07-23T00:01:00Z",
    )
    receipt_content = (
        json.dumps(completed_receipt, ensure_ascii=False, indent=2) + "\n"
    ).encode("utf-8")
    reviewed_package, _manifest = build_procurement_reviewed_package(
        packet.content,
        completed_receipt,
        receipt_content=receipt_content,
    )
    completed_record = client.app.state.procurement_review_store.complete(
        tenant_id="system",
        project_id=project_id,
        packet_sha256=packet.sha256,
        current=review_record,
        completed_receipt=completed_receipt,
        reviewed_package_content=reviewed_package,
    )
    assert completed_record.schema_version.endswith(".v1")

    listed = client.get(
        f"/projects/{project_id}/procurement/reviews",
        headers=reviewer_headers,
    )
    assert listed.status_code == 200
    assert listed.json()["reviews"][0]["schema_version"].endswith(".v1")
    downloaded = client.get(
        (
            f"/projects/{project_id}/procurement/reviews/"
            f"{packet.sha256}/reviewed-package"
        ),
        headers=reviewer_headers,
    )
    assert downloaded.status_code == 200
    assert downloaded.content == reviewed_package


def test_procurement_review_ui_requires_assignee_and_omits_reviewer_payload() -> None:
    source = (Path(__file__).parents[1] / "app" / "static" / "index.html").read_text(
        encoding="utf-8"
    )

    assert "assignedUserId === currentUserId" in source
    assert "review?.reviewer_attestation?.reviewer?.username" in source
    assert "reviewer,\n            decision: decisionInput.value" not in source
