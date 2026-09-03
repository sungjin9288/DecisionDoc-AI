from __future__ import annotations

import hashlib
import json
from uuid import uuid4

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
from app.storage.guided_decision_review_disposition_registry import (
    canonical_guided_review_registry_json_bytes,
    get_guided_decision_review_disposition_registry,
)
from app.storage.guided_decision_review_disposition_issuance_registry import (
    get_guided_decision_review_disposition_issuance_registry,
)
from app.storage.user_store import get_user_store


API_HEADERS = {"X-DecisionDoc-Api-Key": "test-key"}
BUNDLE_QUERY = "?bundle_type=proposal_kr"


@pytest.fixture
def client(tmp_path, monkeypatch) -> TestClient:
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DECISIONDOC_PROVIDER", "mock")
    monkeypatch.setenv("DECISIONDOC_API_KEY", "test-key")
    monkeypatch.setenv("DECISIONDOC_OPS_KEY", "ops-secret")
    monkeypatch.setenv("DECISIONDOC_PROCUREMENT_COPILOT_ENABLED", "1")
    return TestClient(create_app())


def _login(
    client: TestClient,
    username: str,
    *,
    tenant_id: str = "system",
) -> dict[str, str]:
    tenant_headers = {} if tenant_id == "system" else {"X-Tenant-ID": tenant_id}
    registered = client.post(
        "/auth/register",
        headers=tenant_headers,
        json={
            "username": username,
            "display_name": username,
            "email": f"{username}@example.com",
            "password": "Password123!",
            "role": "admin",
        },
    )
    assert registered.status_code == 200
    return {
        **tenant_headers,
        "Authorization": f"Bearer {registered.json()['access_token']}",
    }


def _create_user(
    client: TestClient,
    admin_headers: dict[str, str],
    username: str,
    *,
    role: str,
) -> dict[str, str]:
    created = client.post(
        "/admin/users",
        headers=admin_headers,
        json={
            "username": username,
            "display_name": username,
            "email": f"{username}@example.com",
            "password": "Password123!",
            "role": role,
        },
    )
    assert created.status_code == 200
    logged_in = client.post(
        "/auth/login",
        json={"username": username, "password": "Password123!"},
    )
    assert logged_in.status_code == 200
    return {"Authorization": f"Bearer {logged_in.json()['access_token']}"}


def _ready_project(client: TestClient, headers: dict[str, str]) -> str:
    created = client.post(
        "/projects",
        headers=headers,
        json={"name": "H129 registry", "fiscal_year": 2026},
    )
    assert created.status_code == 200
    project_id = created.json()["project_id"]
    client.app.state.procurement_store.upsert(
        ProcurementDecisionUpsert(
            project_id=project_id,
            tenant_id="system",
            opportunity=NormalizedProcurementOpportunity(
                source_kind="g2b",
                source_id=f"H129-{project_id}",
                title="H129 local review",
                issuer="DecisionDoc",
            ),
            hard_filters=[
                ProcurementHardFilterResult(
                    code="eligibility",
                    label="Eligibility",
                    status="pass",
                    blocking=True,
                    reason="Observed locally.",
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
                value="GO",
                summary="Proceed to human review.",
                evidence=["Local deterministic evidence"],
                missing_data=["Security owner"],
                remediation_notes=["Assign security owner"],
            ),
        )
    )
    return project_id


def _h128_receipt(
    client: TestClient,
    headers: dict[str, str],
    project_id: str,
    *,
    disposition: str = "acknowledged_unchanged",
) -> tuple[dict, str]:
    handoff = client.get(
        f"/projects/{project_id}/guided-decision-review-handoff",
        headers=headers,
    )
    assert handoff.status_code == 200
    recheck = client.post(
        f"/projects/{project_id}/guided-decision-review-handoff/recheck",
        headers=headers,
        json={
            "contract_version": "guided-decision-review-recheck-request.v1",
            "source_handoff": handoff.json(),
            "source_handoff_sha256": hashlib.sha256(handoff.content).hexdigest(),
        },
    )
    assert recheck.status_code == 200
    receipt = client.post(
        (
            f"/projects/{project_id}/guided-decision-review-handoff/"
            "review-disposition"
        ),
        headers=headers,
        json={
            "contract_version": "guided-decision-review-disposition-request.v1",
            "source_recheck_receipt": recheck.json(),
            "source_recheck_receipt_sha256": hashlib.sha256(
                recheck.content
            ).hexdigest(),
            "review_disposition": disposition,
        },
    )
    assert receipt.status_code == 200
    return receipt.json(), hashlib.sha256(receipt.content).hexdigest()


def _create_payload(
    receipt: dict,
    receipt_hash: str,
    operation_id: str,
    *,
    contract_version: str = "guided-decision-review-disposition-record-request.v2",
) -> dict:
    return {
        "contract_version": contract_version,
        "operation_id": operation_id,
        "source_disposition_receipt": receipt,
        "source_disposition_receipt_sha256": receipt_hash,
    }


def test_h129_create_replay_list_read_and_download_are_canonical(
    client: TestClient,
) -> None:
    admin = _login(client, "h129-admin")
    project_id = _ready_project(client, admin)
    receipt, receipt_hash = _h128_receipt(client, admin, project_id)
    operation_id = str(uuid4())
    path = f"/projects/{project_id}/guided-decision-review-dispositions"
    payload = _create_payload(receipt, receipt_hash, operation_id)

    first = client.post(path + BUNDLE_QUERY, headers=admin, json=payload)
    replay = client.post(path + BUNDLE_QUERY, headers=admin, json=payload)

    assert first.status_code == 201
    assert replay.status_code == 200
    assert replay.content == first.content
    record = first.json()
    assert record["contract_version"] == (
        "guided-decision-review-disposition-record.v2"
    )
    assert record["tenant_id"] == "system"
    assert record["project_id"] == project_id
    assert record["bundle_type"] == "proposal_kr"
    assert record["reviewer_identity_bound"] is True
    assert record["registry_record_persisted"] is True
    assert record["source_disposition_receipt"] == receipt
    assert record["issuance_provenance"] == "server_issued"
    assert receipt["reviewer_identity_bound"] is False
    assert receipt["disposition_receipt_persisted"] is False
    assert first.headers["cache-control"] == "no-store"
    assert first.headers["x-content-type-options"] == "nosniff"
    assert first.headers[
        "x-decisiondoc-guided-review-disposition-record-sha256"
    ] == hashlib.sha256(first.content).hexdigest()

    listing = client.get(path + BUNDLE_QUERY, headers=admin)
    read = client.get(f"{path}/{operation_id}{BUNDLE_QUERY}", headers=admin)
    downloaded = client.get(
        f"{path}/{operation_id}/download{BUNDLE_QUERY}",
        headers=admin,
    )

    assert listing.status_code == 200
    assert listing.headers[
        "x-decisiondoc-guided-review-disposition-registry-sha256"
    ] == hashlib.sha256(listing.content).hexdigest()
    summary = listing.json()["records"][0]
    assert summary["operation_id"] == operation_id
    assert "source_disposition_receipt" not in summary
    assert "reviewer_user_id" not in summary
    assert "request_binding_sha256" not in summary
    assert "record_binding_sha256" not in summary
    assert read.status_code == downloaded.status_code == 200
    assert read.content == downloaded.content == first.content
    assert downloaded.headers["content-disposition"] == (
        'attachment; filename="guided-decision-review-disposition-record-'
        f'{operation_id}.json"'
    )

    changed_receipt, changed_hash = _h128_receipt(
        client,
        admin,
        project_id,
        disposition="review_deferred",
    )
    conflict = client.post(
        path + BUNDLE_QUERY,
        headers=admin,
        json=_create_payload(changed_receipt, changed_hash, operation_id),
    )
    assert conflict.status_code == 409
    assert client.get(f"{path}/{operation_id}{BUNDLE_QUERY}", headers=admin).content == first.content


def test_h129_v1_missing_operation_is_rejected_without_write(
    client: TestClient,
) -> None:
    admin = _login(client, "h129-v1-missing-admin")
    project_id = _ready_project(client, admin)
    receipt, receipt_hash = _h128_receipt(client, admin, project_id)
    operation_id = str(uuid4())
    path = f"/projects/{project_id}/guided-decision-review-dispositions"
    registry = get_guided_decision_review_disposition_registry(
        tenant_id="system",
        project_id=project_id,
        bundle_type="proposal_kr",
        backend=client.app.state.state_backend,
    )

    response = client.post(
        path + BUNDLE_QUERY,
        headers=admin,
        json=_create_payload(
            receipt,
            receipt_hash,
            operation_id,
            contract_version="guided-decision-review-disposition-record-request.v1",
        ),
    )

    assert response.status_code == 422
    assert "source_disposition_receipt" not in response.text
    assert client.app.state.state_backend.read_bytes(registry.record_path(operation_id)) is None


def test_h129_v1_public_post_replays_existing_legacy_record_exactly(
    client: TestClient,
) -> None:
    admin = _login(client, "h129-v1-replay-admin")
    project_id = _ready_project(client, admin)
    receipt, receipt_hash = _h128_receipt(client, admin, project_id)
    operation_id = str(uuid4())
    path = f"/projects/{project_id}/guided-decision-review-dispositions"
    user = get_user_store(
        "system",
        data_dir=client.app.state.data_dir,
        backend=client.app.state.state_backend,
    ).get_by_username("h129-v1-replay-admin")
    assert user is not None
    registry = get_guided_decision_review_disposition_registry(
        tenant_id="system",
        project_id=project_id,
        bundle_type="proposal_kr",
        backend=client.app.state.state_backend,
    )
    legacy, created = registry.create(
        operation_id=operation_id,
        reviewer_user_id=user.user_id,
        reviewer_username="historical-name",
        reviewer_role="member",
        source_disposition_receipt=receipt,
        source_disposition_receipt_sha256=receipt_hash,
    )
    assert created is True
    expected = canonical_guided_review_registry_json_bytes(legacy)
    payload = _create_payload(
        receipt,
        receipt_hash,
        operation_id,
        contract_version="guided-decision-review-disposition-record-request.v1",
    )

    replay = client.post(path + BUNDLE_QUERY, headers=admin, json=payload)
    listing = client.get(path + BUNDLE_QUERY, headers=admin)
    read = client.get(f"{path}/{operation_id}{BUNDLE_QUERY}", headers=admin)
    downloaded = client.get(
        f"{path}/{operation_id}/download{BUNDLE_QUERY}",
        headers=admin,
    )

    assert replay.status_code == 200
    assert replay.content == expected
    assert replay.json()["reviewer_username"] == "historical-name"
    assert replay.json()["reviewer_role"] == "member"
    assert replay.headers[
        "x-decisiondoc-guided-review-disposition-issuance-provenance"
    ] == "legacy-unrecorded"
    assert listing.status_code == read.status_code == downloaded.status_code == 200
    assert listing.json()["records"][0]["issuance_provenance"] == (
        "legacy_issuance_unrecorded"
    )
    assert read.content == downloaded.content == expected


@pytest.mark.parametrize(
    ("issuance_state", "expected_status"),
    [("missing", 422), ("corrupt", 503)],
)
def test_h129_v2_fails_closed_when_issuance_is_missing_or_corrupt(
    client: TestClient,
    issuance_state: str,
    expected_status: int,
) -> None:
    admin = _login(client, f"h129-v2-{issuance_state}-admin")
    project_id = _ready_project(client, admin)
    receipt, receipt_hash = _h128_receipt(client, admin, project_id)
    operation_id = str(uuid4())
    path = f"/projects/{project_id}/guided-decision-review-dispositions"
    issuance = get_guided_decision_review_disposition_issuance_registry(
        tenant_id="system",
        project_id=project_id,
        bundle_type="proposal_kr",
        backend=client.app.state.state_backend,
    )
    issuance_path = issuance.record_path(receipt_hash)
    if issuance_state == "missing":
        client.app.state.state_backend.delete(issuance_path)
        expected_raw = None
    else:
        expected_raw = b'{"corrupt":true}\n'
        client.app.state.state_backend.write_bytes(issuance_path, expected_raw)
    registry = get_guided_decision_review_disposition_registry(
        tenant_id="system",
        project_id=project_id,
        bundle_type="proposal_kr",
        backend=client.app.state.state_backend,
    )

    response = client.post(
        path + BUNDLE_QUERY,
        headers=admin,
        json=_create_payload(receipt, receipt_hash, operation_id),
    )

    assert response.status_code == expected_status
    assert "source_disposition_receipt" not in response.text
    assert client.app.state.state_backend.read_bytes(registry.record_path(operation_id)) is None
    assert client.app.state.state_backend.read_bytes(issuance_path) == expected_raw


def test_h129_v2_requires_and_embeds_same_backend_h128_issuance(
    client: TestClient,
) -> None:
    admin = _login(client, "h129-v2-admin")
    project_id = _ready_project(client, admin)
    receipt, receipt_hash = _h128_receipt(client, admin, project_id)
    path = f"/projects/{project_id}/guided-decision-review-dispositions"
    response = client.post(
        path + BUNDLE_QUERY,
        headers=admin,
        json=_create_payload(
            receipt,
            receipt_hash,
            str(uuid4()),
            contract_version="guided-decision-review-disposition-record-request.v2",
        ),
    )

    assert response.status_code == 201
    record = response.json()
    assert record["contract_version"] == "guided-decision-review-disposition-record.v2"
    assert record["issuance_provenance"] == "server_issued"
    assert record["source_issuance_metadata"]["disposition_receipt_sha256"] == receipt_hash
    assert response.headers[
        "x-decisiondoc-guided-review-disposition-issuance-provenance"
    ] == "server-issued"
    assert response.headers[
        "x-decisiondoc-guided-review-disposition-issuance-record-sha256"
    ] == record["source_issuance_metadata_sha256"]


def test_h129_authorization_and_non_disclosing_owner_boundary(
    client: TestClient,
) -> None:
    admin = _login(client, "h129-access-admin")
    member = _create_user(client, admin, "h129-member", role="member")
    other = _create_user(client, admin, "h129-other", role="member")
    viewer = _create_user(client, admin, "h129-viewer", role="viewer")
    project_id = _ready_project(client, admin)
    receipt, receipt_hash = _h128_receipt(client, admin, project_id)
    operation_id = str(uuid4())
    path = f"/projects/{project_id}/guided-decision-review-dispositions"
    payload = _create_payload(receipt, receipt_hash, operation_id)
    user = get_user_store(
        "system",
        data_dir=client.app.state.data_dir,
        backend=client.app.state.state_backend,
    ).get_by_username("h129-member")
    assert user is not None
    sessionless = {
        "Authorization": "Bearer "
        + create_access_token(
            user.user_id,
            user.tenant_id,
            user.role.value,
            user.username,
            credential_version=user.credential_version,
        )
    }

    for headers, expected in (
        (API_HEADERS, 401),
        ({"X-DecisionDoc-Ops-Key": "ops-secret"}, 401),
        (sessionless, 401),
        (viewer, 403),
        (member, 404),
        (other, 404),
    ):
        assert client.post(path + BUNDLE_QUERY, headers=headers, json=payload).status_code == expected

    assert client.post(
        f"/projects/{uuid4()}/guided-decision-review-dispositions{BUNDLE_QUERY}",
        headers=admin,
        json=payload,
    ).status_code == 404

    client.app.state.tenant_store.create_tenant("foreign", "Foreign")
    foreign = _login(client, "foreign-admin", tenant_id="foreign")
    assert client.post(path + BUNDLE_QUERY, headers=foreign, json=payload).status_code == 404

    prepared = client.post(
        f"/projects/{project_id}/procurement/review-packet",
        headers=admin,
        json={"reviewer": "h129-member"},
    )
    assert prepared.status_code == 200
    created = client.post(path + BUNDLE_QUERY, headers=admin, json=payload)
    assert created.status_code == 201
    assert client.get(path + BUNDLE_QUERY, headers=member).json()["records"] == []
    for suffix in ("", "/download"):
        assert client.get(
            f"{path}/{operation_id}{suffix}{BUNDLE_QUERY}",
            headers=member,
        ).status_code == 404


def test_h129_member_create_visibility_and_audit_are_stable_identity_redacted(
    client: TestClient,
) -> None:
    admin = _login(client, "h129-audit-admin")
    member = _create_user(client, admin, "h129-audit-member", role="member")
    project_id = _ready_project(client, admin)
    assert client.post(
        f"/projects/{project_id}/procurement/review-packet",
        headers=admin,
        json={"reviewer": "h129-audit-member"},
    ).status_code == 200
    receipt, receipt_hash = _h128_receipt(client, member, project_id)
    operation_id = str(uuid4())
    path = f"/projects/{project_id}/guided-decision-review-dispositions"
    created = client.post(
        path + BUNDLE_QUERY,
        headers={**member, "User-Agent": "private-h129-client"},
        json=_create_payload(receipt, receipt_hash, operation_id),
    )
    assert created.status_code == 201
    assert client.get(path + BUNDLE_QUERY, headers=member).json()["records"][0][
        "operation_id"
    ] == operation_id
    assert client.get(path + BUNDLE_QUERY, headers=admin).json()["records"][0][
        "operation_id"
    ] == operation_id

    audits = AuditStore(
        "system",
        data_dir=client.app.state.data_dir,
        backend=client.app.state.state_backend,
    ).query(filters={"action": "procurement.guided_review_registry_create"})
    assert len(audits) == 1
    audit = audits[0]
    assert audit["session_id"] == ""
    assert audit["ip_address"] == ""
    assert audit["user_agent"] == ""
    assert audit["user_id"] == created.json()["reviewer_user_id"]
    assert audit["detail"]["operation_id"] == operation_id
    assert audit["detail"]["reviewer_identity_bound"] is True
    assert audit["detail"]["registry_record_persisted"] is True
    assert audit["detail"]["approval"] is False
    detail_text = json.dumps(audit["detail"])
    assert "source_disposition_receipt" not in audit["detail"]
    assert "source_recheck_receipt" not in audit["detail"]
    assert created.json()["reviewer_user_id"] not in detail_text
    assert "private-h129-client" not in json.dumps(audit)


def test_h129_corruption_fails_closed_without_rewriting_bytes(
    client: TestClient,
) -> None:
    admin = _login(client, "h129-corrupt-admin")
    project_id = _ready_project(client, admin)
    receipt, receipt_hash = _h128_receipt(client, admin, project_id)
    operation_id = str(uuid4())
    path = f"/projects/{project_id}/guided-decision-review-dispositions"
    assert client.post(
        path + BUNDLE_QUERY,
        headers=admin,
        json=_create_payload(receipt, receipt_hash, operation_id),
    ).status_code == 201
    registry = get_guided_decision_review_disposition_registry(
        tenant_id="system",
        project_id=project_id,
        bundle_type="proposal_kr",
        backend=client.app.state.state_backend,
    )
    record_path = registry.record_path(operation_id)
    corrupt = b'{"corrupt":true}\n'
    client.app.state.state_backend.write_bytes(record_path, corrupt)

    assert client.get(f"{path}/{operation_id}{BUNDLE_QUERY}", headers=admin).status_code == 503
    assert client.get(path + BUNDLE_QUERY, headers=admin).status_code == 503
    assert client.app.state.state_backend.read_bytes(record_path) == corrupt
