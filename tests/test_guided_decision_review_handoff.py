from __future__ import annotations

import hashlib
import json

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
from app.schemas.decision_evidence import (
    DecisionEvidenceCoverageSummary,
    DecisionEvidenceDiagnostic,
    DecisionEvidenceMapResponse,
    DecisionEvidenceNode,
    DecisionEvidenceProposalBlueprint,
    GuidedDecisionReviewRecheckReceipt,
)
from app.services.guided_decision_review_service import (
    GuidedDecisionReviewService,
)
from app.storage.audit_store import AuditStore
from app.storage.guided_decision_review_disposition_issuance_registry import (
    get_guided_decision_review_disposition_issuance_registry,
)
from app.storage.state_backend import StateBackendError


def _canonical_json_bytes(payload: dict) -> bytes:
    return (
        json.dumps(
            payload,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        + b"\n"
    )


def _review_state_fingerprint(handoff: dict) -> str:
    payload = json.loads(json.dumps(handoff))
    payload.pop("source_generated_at")
    return hashlib.sha256(_canonical_json_bytes(payload)[:-1]).hexdigest()


def _projection(
    *,
    diagnostics: list[DecisionEvidenceDiagnostic] | None = None,
) -> DecisionEvidenceMapResponse:
    return DecisionEvidenceMapResponse(
        generated_at="2026-07-28T00:00:00Z",
        project_id="project-1",
        bundle_type="proposal_kr",
        projection_fingerprint="a" * 64,
        nodes=[
            DecisionEvidenceNode(
                node_id="recommendation:decision-1",
                node_type="recommendation",
                label="Recommendation",
                status="GO",
                evidence_level="authoritative",
            )
        ],
        coverage=DecisionEvidenceCoverageSummary(
            total=0,
            explicit=0,
            candidate=0,
            missing=0,
            unverifiable=0,
        ),
        diagnostics=diagnostics or [],
        proposal_blueprint=DecisionEvidenceProposalBlueprint(
            status="not_observed",
        ),
    )


def _decision() -> dict:
    return {
        "opportunity": {"title": "Local review"},
        "hard_filters": [],
        "missing_data": [],
        "recommendation": {"value": "GO"},
        "notes": "",
    }


def _accepted_review() -> dict:
    return {
        "packet_sha256": "b" * 64,
        "review_status": "completed",
        "decision": "accepted",
        "prepared_at": "2026-07-28T00:01:00Z",
    }


def _current_document() -> dict:
    return {
        "doc_id": "doc-1",
        "bundle_id": "proposal_kr",
        "title": "Proposal",
        "generated_at": "2026-07-28T00:02:00Z",
        "procurement_review_document_status": "current",
        "decision_council_document_status": "current",
    }


def test_guided_review_handoff_uses_conservative_stage_precedence() -> None:
    service = GuidedDecisionReviewService()
    decision = _decision()
    decision["missing_data"] = ["Security owner"]
    handoff = service.build(
        projection=_projection(
            diagnostics=[
                DecisionEvidenceDiagnostic(
                    code="projection_error",
                    severity="error",
                    message="Projection requires review.",
                    next_action="Inspect evidence.",
                )
            ]
        ),
        procurement_record=decision,
        review_summaries=[_accepted_review()],
        council_session=None,
        project_documents=[_current_document()],
    )

    assert handoff.recommended_next_check.stage == "Evidence"
    assert handoff.overall_state == "Needs review"
    assert [stage.name for stage in handoff.stages] == [
        "Decision",
        "Evidence",
        "Review",
        "Documents",
    ]
    assert handoff.stages[0].status == "needs_attention"
    assert handoff.stages[1].status == "needs_attention"


def test_guided_review_handoff_distinguishes_pending_and_stale_documents() -> None:
    service = GuidedDecisionReviewService()
    pending = _accepted_review()
    pending.update({"review_status": "pending", "decision": ""})

    pending_handoff = service.build(
        projection=_projection(),
        procurement_record=_decision(),
        review_summaries=[pending],
        council_session=None,
        project_documents=[_current_document()],
    )
    assert pending_handoff.overall_state == "Review in progress"
    assert pending_handoff.recommended_next_check.stage == "Review"

    stale_document = _current_document()
    stale_document["procurement_review_document_status"] = "stale_source"
    stale_handoff = service.build(
        projection=_projection(),
        procurement_record=_decision(),
        review_summaries=[_accepted_review()],
        council_session=None,
        project_documents=[stale_document],
    )
    assert stale_handoff.recommended_next_check.stage == "Documents"
    assert stale_handoff.stages[-1].status == "needs_attention"


def test_guided_review_handoff_keeps_authority_false_and_serializes_canonically() -> None:
    service = GuidedDecisionReviewService()
    handoff = service.build(
        projection=_projection(),
        procurement_record=_decision(),
        review_summaries=[_accepted_review()],
        council_session=None,
        project_documents=[_current_document()],
    )

    assert handoff.overall_state == "No blocking signal observed"
    assert handoff.read_only is True
    assert handoff.snapshot_atomic is False
    assert handoff.handoff_persisted is False
    assert handoff.requires_recheck_before_reliance is True
    assert handoff.authority.model_dump() == {
        "mutation": False,
        "approval": False,
        "export_execution": False,
        "provider_call": False,
        "bid_submission": False,
        "legal_contractual_commitment": False,
    }
    body = service.serialize(handoff)
    assert body.endswith(b"\n")
    assert body == (
        json.dumps(
            handoff.model_dump(mode="json"),
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        + b"\n"
    )


def test_guided_review_recheck_ignores_only_source_timestamp() -> None:
    service = GuidedDecisionReviewService()
    source = service.build(
        projection=_projection(),
        procurement_record=_decision(),
        review_summaries=[_accepted_review()],
        council_session=None,
        project_documents=[_current_document()],
    )
    current_projection = _projection().model_copy(
        update={"generated_at": "2026-07-28T01:00:00Z"},
    )
    current = service.build(
        projection=current_projection,
        procurement_record=_decision(),
        review_summaries=[_accepted_review()],
        council_session=None,
        project_documents=[_current_document()],
    )
    source_sha256 = hashlib.sha256(service.serialize(source)).hexdigest()

    receipt = service.recheck(
        source_handoff=source,
        source_handoff_sha256=source_sha256,
        current_handoff=current,
        expected_project_id="project-1",
    )

    assert source.source_generated_at != current.source_generated_at
    assert receipt.contract_version == "guided-decision-review-recheck-receipt.v1"
    assert receipt.source_handoff_sha256 == source_sha256
    assert receipt.review_state_status == "unchanged"
    assert receipt.source_review_state_fingerprint_sha256 == (
        receipt.current_review_state_fingerprint_sha256
    )
    assert receipt.volatile_fields_excluded == ["source_generated_at"]
    assert receipt.review_state_only is True
    assert receipt.review_only is True
    assert receipt.read_only is True
    assert receipt.snapshot_atomic is False
    assert receipt.requires_recheck_before_reliance is True
    assert receipt.recheck_persisted is False
    assert receipt.authority.model_dump() == source.authority.model_dump()


def test_guided_review_recheck_detects_semantic_drift_and_rejects_bad_source() -> None:
    service = GuidedDecisionReviewService()
    source = service.build(
        projection=_projection(),
        procurement_record=_decision(),
        review_summaries=[_accepted_review()],
        council_session=None,
        project_documents=[_current_document()],
    )
    source_sha256 = hashlib.sha256(service.serialize(source)).hexdigest()
    current = source.model_copy(update={"projection_fingerprint": "b" * 64})

    receipt = service.recheck(
        source_handoff=source,
        source_handoff_sha256=source_sha256,
        current_handoff=current,
        expected_project_id="project-1",
    )

    assert receipt.review_state_status == "changed"
    assert receipt.source_review_state_fingerprint_sha256 != (
        receipt.current_review_state_fingerprint_sha256
    )
    with pytest.raises(ValueError, match="source_handoff_sha256"):
        service.recheck(
            source_handoff=source,
            source_handoff_sha256="0" * 64,
            current_handoff=current,
            expected_project_id="project-1",
        )
    with pytest.raises(ValueError, match="project"):
        service.recheck(
            source_handoff=source,
            source_handoff_sha256=source_sha256,
            current_handoff=current,
            expected_project_id="project-2",
        )


def test_guided_review_disposition_binds_verified_recheck_and_status_matrix() -> None:
    service = GuidedDecisionReviewService()
    source = service.build(
        projection=_projection(),
        procurement_record=_decision(),
        review_summaries=[_accepted_review()],
        council_session=None,
        project_documents=[_current_document()],
    )
    source_sha256 = hashlib.sha256(service.serialize(source)).hexdigest()
    current = source.model_copy(
        update={"source_generated_at": "2026-07-28T01:00:00Z"},
    )
    recheck = service.recheck(
        source_handoff=source,
        source_handoff_sha256=source_sha256,
        current_handoff=current,
        expected_project_id="project-1",
    )
    recheck_sha256 = hashlib.sha256(
        service.serialize_recheck(recheck)
    ).hexdigest()

    disposition = service.issue_disposition(
        source_recheck_receipt=recheck,
        source_recheck_receipt_sha256=recheck_sha256,
        review_disposition="acknowledged_unchanged",
        expected_project_id="project-1",
    )

    assert disposition.contract_version == (
        "guided-decision-review-disposition-receipt.v1"
    )
    assert disposition.project_id == "project-1"
    assert disposition.bundle_type == "proposal_kr"
    assert disposition.source_recheck_receipt == recheck
    assert disposition.source_recheck_receipt_sha256 == recheck_sha256
    assert disposition.current_handoff_sha256 == recheck.current_handoff_sha256
    assert disposition.current_review_state_fingerprint_sha256 == (
        recheck.current_review_state_fingerprint_sha256
    )
    assert disposition.review_state_status == "unchanged"
    assert disposition.review_disposition == "acknowledged_unchanged"
    assert disposition.receipt_status == "issued"
    assert disposition.reviewer_identity_bound is False
    assert disposition.review_only is True
    assert disposition.read_only is True
    assert disposition.snapshot_atomic is False
    assert disposition.requires_recheck_before_reliance is True
    assert disposition.disposition_receipt_persisted is False
    assert disposition.authority.model_dump() == source.authority.model_dump()
    binding = {
        "project_id": "project-1",
        "bundle_type": "proposal_kr",
        "source_recheck_receipt_sha256": recheck_sha256,
        "current_handoff_sha256": recheck.current_handoff_sha256,
        "current_review_state_fingerprint_sha256": (
            recheck.current_review_state_fingerprint_sha256
        ),
        "review_state_status": "unchanged",
        "review_disposition": "acknowledged_unchanged",
    }
    assert disposition.disposition_binding_sha256 == hashlib.sha256(
        json.dumps(
            binding,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    assert service.serialize_disposition(disposition) == (
        json.dumps(
            disposition.model_dump(mode="json"),
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        + b"\n"
    )

    with pytest.raises(ValueError, match="review disposition"):
        service.issue_disposition(
            source_recheck_receipt=recheck,
            source_recheck_receipt_sha256=recheck_sha256,
            review_disposition="new_handoff_required",
            expected_project_id="project-1",
        )

    changed = service.recheck(
        source_handoff=source,
        source_handoff_sha256=source_sha256,
        current_handoff=current.model_copy(
            update={"projection_fingerprint": "b" * 64},
        ),
        expected_project_id="project-1",
    )
    changed_sha256 = hashlib.sha256(
        service.serialize_recheck(changed)
    ).hexdigest()
    changed_disposition = service.issue_disposition(
        source_recheck_receipt=changed,
        source_recheck_receipt_sha256=changed_sha256,
        review_disposition="new_handoff_required",
        expected_project_id="project-1",
    )
    assert changed_disposition.review_state_status == "changed"
    assert changed_disposition.review_disposition == "new_handoff_required"


def test_guided_review_disposition_rejects_outer_and_embedded_hash_drift() -> None:
    service = GuidedDecisionReviewService()
    source = service.build(
        projection=_projection(),
        procurement_record=_decision(),
        review_summaries=[_accepted_review()],
        council_session=None,
        project_documents=[_current_document()],
    )
    source_sha256 = hashlib.sha256(service.serialize(source)).hexdigest()
    recheck = service.recheck(
        source_handoff=source,
        source_handoff_sha256=source_sha256,
        current_handoff=source,
        expected_project_id="project-1",
    )
    with pytest.raises(ValueError, match="source_recheck_receipt_sha256"):
        service.issue_disposition(
            source_recheck_receipt=recheck,
            source_recheck_receipt_sha256="0" * 64,
            review_disposition="acknowledged_unchanged",
            expected_project_id="project-1",
        )

    tampered = recheck.model_copy(
        update={"current_review_state_fingerprint_sha256": "0" * 64},
    )
    tampered_sha256 = hashlib.sha256(
        service.serialize_recheck(tampered)
    ).hexdigest()
    with pytest.raises(ValueError, match="current review state fingerprint"):
        service.issue_disposition(
            source_recheck_receipt=tampered,
            source_recheck_receipt_sha256=tampered_sha256,
            review_disposition="acknowledged_unchanged",
            expected_project_id="project-1",
        )


def test_guided_review_disposition_rejects_preparsed_incomplete_recheck_receipt() -> None:
    service = GuidedDecisionReviewService()
    source = service.build(
        projection=_projection(),
        procurement_record=_decision(),
        review_summaries=[_accepted_review()],
        council_session=None,
        project_documents=[_current_document()],
    )
    source_sha256 = hashlib.sha256(service.serialize(source)).hexdigest()
    recheck = service.recheck(
        source_handoff=source,
        source_handoff_sha256=source_sha256,
        current_handoff=source,
        expected_project_id="project-1",
    )
    incomplete_payload = recheck.model_dump(mode="json")
    incomplete_payload["source_handoff"].pop("authority")
    pre_parsed = GuidedDecisionReviewRecheckReceipt.model_validate(
        incomplete_payload,
        strict=True,
    )
    recheck_sha256 = hashlib.sha256(
        service.serialize_recheck(pre_parsed)
    ).hexdigest()

    with pytest.raises(ValueError, match="missing required contract fields"):
        service.issue_disposition(
            source_recheck_receipt=pre_parsed,
            source_recheck_receipt_sha256=recheck_sha256,
            review_disposition="acknowledged_unchanged",
            expected_project_id="project-1",
        )


API_HEADERS = {"X-DecisionDoc-Api-Key": "test-key"}


@pytest.fixture
def client(tmp_path, monkeypatch) -> TestClient:
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DECISIONDOC_PROVIDER", "mock")
    monkeypatch.setenv("DECISIONDOC_API_KEY", "test-key")
    monkeypatch.setenv("DECISIONDOC_PROCUREMENT_COPILOT_ENABLED", "1")
    return TestClient(create_app())


def _login(client: TestClient, username: str, *, role: str) -> dict[str, str]:
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
    return {"Authorization": f"Bearer {registered.json()['access_token']}"}


def _create_user(
    client: TestClient,
    admin_headers: dict[str, str],
    username: str,
    *,
    role: str,
) -> dict[str, str]:
    created = client.post(
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
    assert created.status_code == 200
    response = client.post(
        "/auth/login",
        json={"username": username, "password": "Password123!"},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _ready_project(client: TestClient, headers: dict[str, str]) -> str:
    created = client.post(
        "/projects",
        json={"name": "Guided review handoff", "fiscal_year": 2026},
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
                source_id="HANDOFF-1",
                title="Guided review handoff",
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


def _guided_review_disposition_request(
    client: TestClient,
    headers: dict[str, str],
    project_id: str,
) -> tuple[str, dict]:
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
    return (
        f"/projects/{project_id}/guided-decision-review-handoff/"
        "review-disposition",
        {
            "contract_version": "guided-decision-review-disposition-request.v1",
            "source_recheck_receipt": recheck.json(),
            "source_recheck_receipt_sha256": hashlib.sha256(
                recheck.content
            ).hexdigest(),
            "review_disposition": "acknowledged_unchanged",
        },
    )


def test_guided_review_handoff_route_is_session_bound_and_hash_verified(
    client: TestClient,
) -> None:
    admin_headers = _login(client, "handoff-admin", role="admin")
    viewer_headers = _create_user(
        client,
        admin_headers,
        "handoff-viewer",
        role="viewer",
    )
    assigned_headers = _create_user(
        client,
        admin_headers,
        "handoff-member",
        role="member",
    )
    other_headers = _create_user(
        client,
        admin_headers,
        "handoff-other",
        role="member",
    )
    project_id = _ready_project(client, admin_headers)
    path = f"/projects/{project_id}/guided-decision-review-handoff"

    assert client.get(path, headers=API_HEADERS).status_code == 401
    assert client.get(path, headers=viewer_headers).status_code == 403
    assert client.get(path, headers=other_headers).status_code == 404
    prepared = client.post(
        f"/projects/{project_id}/procurement/review-packet",
        json={"reviewer": "handoff-member"},
        headers=admin_headers,
    )
    assert prepared.status_code == 200
    assert client.get(path, headers=assigned_headers).status_code == 200

    response = client.get(path, headers=admin_headers)
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-decisiondoc-operational-approval"] == "false"
    assert response.headers["x-decisiondoc-projection-fingerprint"] == (
        response.json()["projection_fingerprint"]
    )
    assert response.headers[
        "x-decisiondoc-guided-review-handoff-sha256"
    ] == hashlib.sha256(response.content).hexdigest()
    assert response.headers["content-disposition"].startswith(
        'attachment; filename="guided-decision-review-handoff-'
    )

    payload = response.json()
    assert payload["contract_version"] == "guided-decision-review-handoff.v1"
    assert payload["source_contract_version"] == "decision_evidence_map.v1"
    assert payload["project_id"] == project_id
    assert payload["read_only"] is True
    assert payload["handoff_persisted"] is False
    assert payload["authority"]["export_execution"] is False
    assert response.content == (
        json.dumps(
            payload,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        + b"\n"
    )


def test_guided_review_handoff_audit_is_redacted(client: TestClient) -> None:
    admin_headers = _login(client, "handoff-audit-admin", role="admin")
    project_id = _ready_project(client, admin_headers)

    response = client.get(
        f"/projects/{project_id}/guided-decision-review-handoff",
        headers={**admin_headers, "User-Agent": "private-client"},
    )
    assert response.status_code == 200

    records = AuditStore(
        "system",
        data_dir=client.app.state.data_dir,
        backend=client.app.state.state_backend,
    ).query(filters={"action": "procurement.guided_review_handoff_download"})
    assert len(records) == 1
    record = records[0]
    assert record["resource_id"] == project_id
    assert record["session_id"] == ""
    assert record["ip_address"] == ""
    assert record["user_agent"] == ""
    assert record["detail"]["read_only"] is True
    assert record["detail"]["snapshot_atomic"] is False
    assert record["detail"]["handoff_persisted"] is False


def test_guided_review_recheck_route_is_hash_bound_and_session_scoped(
    client: TestClient,
) -> None:
    admin_headers = _login(client, "recheck-admin", role="admin")
    viewer_headers = _create_user(
        client,
        admin_headers,
        "recheck-viewer",
        role="viewer",
    )
    project_id = _ready_project(client, admin_headers)
    source_response = client.get(
        f"/projects/{project_id}/guided-decision-review-handoff",
        headers=admin_headers,
    )
    source = source_response.json()
    source_sha256 = hashlib.sha256(source_response.content).hexdigest()
    path = f"/projects/{project_id}/guided-decision-review-handoff/recheck"
    request_payload = {
        "contract_version": "guided-decision-review-recheck-request.v1",
        "source_handoff": source,
        "source_handoff_sha256": source_sha256,
    }

    assert client.post(path, json=request_payload, headers=API_HEADERS).status_code == 401
    assert client.post(path, json=request_payload, headers=viewer_headers).status_code == 403
    response = client.post(path, json=request_payload, headers=admin_headers)

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-decisiondoc-operational-approval"] == "false"
    assert response.headers["x-decisiondoc-review-state-status"] == "unchanged"
    assert response.headers[
        "x-decisiondoc-guided-review-recheck-receipt-sha256"
    ] == hashlib.sha256(response.content).hexdigest()
    assert response.headers["content-disposition"].startswith(
        'attachment; filename="guided-decision-review-recheck-receipt-'
    )
    receipt = response.json()
    assert receipt["contract_version"] == (
        "guided-decision-review-recheck-receipt.v1"
    )
    assert receipt["source_handoff"] == source
    assert receipt["source_handoff_sha256"] == source_sha256
    assert receipt["current_handoff"]["project_id"] == project_id
    assert receipt["review_state_status"] == "unchanged"
    assert receipt["volatile_fields_excluded"] == ["source_generated_at"]
    assert receipt["recheck_persisted"] is False
    assert response.content == (
        json.dumps(
            receipt,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        + b"\n"
    )

    bad_hash = client.post(
        path,
        json={**request_payload, "source_handoff_sha256": "0" * 64},
        headers=admin_headers,
    )
    assert bad_hash.status_code == 422
    foreign_source = json.loads(json.dumps(source))
    foreign_source["project_id"] = "foreign-project"
    foreign_body = (
        json.dumps(
            foreign_source,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        + b"\n"
    )
    project_drift = client.post(
        path,
        json={
            **request_payload,
            "source_handoff": foreign_source,
            "source_handoff_sha256": hashlib.sha256(foreign_body).hexdigest(),
        },
        headers=admin_headers,
    )
    assert project_drift.status_code == 422


def test_guided_review_recheck_rejects_incomplete_or_unknown_handoff_contract(
    client: TestClient,
) -> None:
    headers = _login(client, "recheck-contract-admin", role="admin")
    project_id = _ready_project(client, headers)
    handoff_response = client.get(
        f"/projects/{project_id}/guided-decision-review-handoff",
        headers=headers,
    )
    assert handoff_response.status_code == 200
    source = handoff_response.json()
    source_sha256 = hashlib.sha256(handoff_response.content).hexdigest()
    path = f"/projects/{project_id}/guided-decision-review-handoff/recheck"

    unknown_handoff = client.get(
        f"/projects/{project_id}/guided-decision-review-handoff"
        "?bundle_type=unknown_bundle",
        headers=headers,
    )
    assert unknown_handoff.status_code == 422

    incomplete_source = json.loads(json.dumps(source))
    incomplete_source.pop("authority")
    incomplete = client.post(
        path,
        headers=headers,
        json={
            "contract_version": "guided-decision-review-recheck-request.v1",
            "source_handoff": incomplete_source,
            "source_handoff_sha256": source_sha256,
        },
    )
    assert incomplete.status_code == 422

    unknown_source = json.loads(json.dumps(source))
    unknown_source["bundle_type"] = "unknown_bundle"
    unknown = client.post(
        path,
        headers=headers,
        json={
            "contract_version": "guided-decision-review-recheck-request.v1",
            "source_handoff": unknown_source,
            "source_handoff_sha256": hashlib.sha256(
                _canonical_json_bytes(unknown_source)
            ).hexdigest(),
        },
    )
    assert unknown.status_code == 422


def test_guided_review_recheck_audit_is_redacted(client: TestClient) -> None:
    admin_headers = _login(client, "recheck-audit-admin", role="admin")
    project_id = _ready_project(client, admin_headers)
    source_response = client.get(
        f"/projects/{project_id}/guided-decision-review-handoff",
        headers=admin_headers,
    )
    response = client.post(
        f"/projects/{project_id}/guided-decision-review-handoff/recheck",
        headers={**admin_headers, "User-Agent": "private-recheck-client"},
        json={
            "contract_version": "guided-decision-review-recheck-request.v1",
            "source_handoff": source_response.json(),
            "source_handoff_sha256": hashlib.sha256(
                source_response.content
            ).hexdigest(),
        },
    )
    assert response.status_code == 200

    records = AuditStore(
        "system",
        data_dir=client.app.state.data_dir,
        backend=client.app.state.state_backend,
    ).query(filters={"action": "procurement.guided_review_handoff_recheck"})
    assert len(records) == 1
    record = records[0]
    assert record["resource_id"] == project_id
    assert record["session_id"] == ""
    assert record["ip_address"] == ""
    assert record["user_agent"] == ""
    assert record["detail"]["read_only"] is True
    assert record["detail"]["snapshot_atomic"] is False
    assert record["detail"]["recheck_persisted"] is False
    assert record["detail"]["review_state_status"] == "unchanged"
    assert "source_handoff" not in record["detail"]


def test_guided_review_disposition_route_is_bound_and_session_scoped(
    client: TestClient,
) -> None:
    admin_headers = _login(client, "disposition-admin", role="admin")
    viewer_headers = _create_user(
        client,
        admin_headers,
        "disposition-viewer",
        role="viewer",
    )
    other_headers = _create_user(
        client,
        admin_headers,
        "disposition-other",
        role="member",
    )
    project_id = _ready_project(client, admin_headers)
    handoff = client.get(
        f"/projects/{project_id}/guided-decision-review-handoff",
        headers=admin_headers,
    )
    recheck = client.post(
        f"/projects/{project_id}/guided-decision-review-handoff/recheck",
        headers=admin_headers,
        json={
            "contract_version": "guided-decision-review-recheck-request.v1",
            "source_handoff": handoff.json(),
            "source_handoff_sha256": hashlib.sha256(handoff.content).hexdigest(),
        },
    )
    assert recheck.status_code == 200
    path = (
        f"/projects/{project_id}/guided-decision-review-handoff/"
        "review-disposition"
    )
    payload = {
        "contract_version": "guided-decision-review-disposition-request.v1",
        "source_recheck_receipt": recheck.json(),
        "source_recheck_receipt_sha256": hashlib.sha256(
            recheck.content
        ).hexdigest(),
        "review_disposition": "acknowledged_unchanged",
    }

    assert client.post(path, json=payload, headers=API_HEADERS).status_code == 401
    assert client.post(path, json=payload, headers=viewer_headers).status_code == 403
    assert client.post(path, json=payload, headers=other_headers).status_code == 404
    response = client.post(path, json=payload, headers=admin_headers)

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-decisiondoc-operational-approval"] == "false"
    assert response.headers["x-decisiondoc-review-state-status"] == "unchanged"
    assert response.headers[
        "x-decisiondoc-guided-review-disposition-receipt-sha256"
    ] == hashlib.sha256(response.content).hexdigest()
    assert len(
        response.headers[
            "x-decisiondoc-guided-review-disposition-issuance-record-sha256"
        ]
    ) == 64
    receipt = response.json()
    assert receipt["contract_version"] == (
        "guided-decision-review-disposition-receipt.v1"
    )
    assert receipt["project_id"] == project_id
    assert receipt["source_recheck_receipt"] == recheck.json()
    assert receipt["source_recheck_receipt_sha256"] == hashlib.sha256(
        recheck.content
    ).hexdigest()
    assert receipt["review_state_status"] == "unchanged"
    assert receipt["review_disposition"] == "acknowledged_unchanged"
    assert receipt["reviewer_identity_bound"] is False
    assert receipt["disposition_receipt_persisted"] is False
    assert receipt["authority"]["approval"] is False

    invalid_matrix = client.post(
        path,
        json={**payload, "review_disposition": "new_handoff_required"},
        headers=admin_headers,
    )
    assert invalid_matrix.status_code == 422
    tampered_receipt = json.loads(json.dumps(recheck.json()))
    tampered_receipt["current_review_state_fingerprint_sha256"] = "0" * 64
    tampered_body = (
        json.dumps(
            tampered_receipt,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        + b"\n"
    )
    tampered = client.post(
        path,
        json={
            **payload,
            "source_recheck_receipt": tampered_receipt,
            "source_recheck_receipt_sha256": hashlib.sha256(
                tampered_body
            ).hexdigest(),
        },
        headers=admin_headers,
    )
    assert tampered.status_code == 422


def test_guided_review_disposition_issuance_unavailable_returns_generic_503(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    headers = _login(client, "disposition-issuance-unavailable", role="admin")
    project_id = _ready_project(client, headers)
    path, payload = _guided_review_disposition_request(client, headers, project_id)
    backend = client.app.state.state_backend
    original_read = backend.read_bytes

    def unavailable_read(relative_path: str) -> bytes | None:
        if "guided_decision_review_disposition_issuances/" in relative_path:
            raise StateBackendError("issuance backend unavailable")
        return original_read(relative_path)

    monkeypatch.setattr(backend, "read_bytes", unavailable_read)
    response = client.post(path, headers=headers, json=payload)

    assert response.status_code == 503
    assert "source_recheck_receipt" not in response.text
    assert (
        "x-decisiondoc-guided-review-disposition-receipt-sha256"
        not in response.headers
    )


def test_guided_review_disposition_issuance_disappearance_returns_generic_503(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    headers = _login(client, "disposition-issuance-disappearing", role="admin")
    project_id = _ready_project(client, headers)
    path, payload = _guided_review_disposition_request(client, headers, project_id)
    backend = client.app.state.state_backend
    original_write = backend.write_bytes_if_absent

    def disappearing_write(
        relative_path: str,
        raw: bytes,
        *,
        content_type: str = "application/octet-stream",
    ) -> bool:
        created = original_write(
            relative_path,
            raw,
            content_type=content_type,
        )
        if "guided_decision_review_disposition_issuances/" in relative_path:
            backend.delete(relative_path)
        return created

    monkeypatch.setattr(backend, "write_bytes_if_absent", disappearing_write)
    response = client.post(path, headers=headers, json=payload)

    assert response.status_code == 503
    assert "source_recheck_receipt" not in response.text
    assert (
        "x-decisiondoc-guided-review-disposition-receipt-sha256"
        not in response.headers
    )


def test_guided_review_disposition_corrupt_issuance_returns_generic_503(
    client: TestClient,
) -> None:
    headers = _login(client, "disposition-issuance-corrupt", role="admin")
    project_id = _ready_project(client, headers)
    path, payload = _guided_review_disposition_request(client, headers, project_id)
    issued = client.post(path, headers=headers, json=payload)
    assert issued.status_code == 200
    issuance = get_guided_decision_review_disposition_issuance_registry(
        tenant_id="system",
        project_id=project_id,
        bundle_type="proposal_kr",
        backend=client.app.state.state_backend,
    )
    issuance_path = issuance.record_path(hashlib.sha256(issued.content).hexdigest())
    corrupt = b'{"corrupt":true}\n'
    client.app.state.state_backend.write_bytes(issuance_path, corrupt)

    response = client.post(path, headers=headers, json=payload)

    assert response.status_code == 503
    assert response.content != issued.content
    assert "source_recheck_receipt" not in response.text
    assert client.app.state.state_backend.read_bytes(issuance_path) == corrupt


def test_guided_review_disposition_rejects_incomplete_or_unknown_receipt_contract(
    client: TestClient,
) -> None:
    headers = _login(client, "disposition-contract-admin", role="admin")
    project_id = _ready_project(client, headers)
    handoff = client.get(
        f"/projects/{project_id}/guided-decision-review-handoff",
        headers=headers,
    )
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
    receipt = recheck.json()
    receipt_sha256 = hashlib.sha256(recheck.content).hexdigest()
    path = (
        f"/projects/{project_id}/guided-decision-review-handoff/"
        "review-disposition"
    )

    incomplete_receipt = json.loads(json.dumps(receipt))
    incomplete_receipt["source_handoff"].pop("authority")
    incomplete_receipt["current_handoff"].pop("authority")
    incomplete = client.post(
        path,
        headers=headers,
        json={
            "contract_version": "guided-decision-review-disposition-request.v1",
            "source_recheck_receipt": incomplete_receipt,
            "source_recheck_receipt_sha256": receipt_sha256,
            "review_disposition": "acknowledged_unchanged",
        },
    )
    assert incomplete.status_code == 422

    unknown_receipt = json.loads(json.dumps(receipt))
    for name in ("source_handoff", "current_handoff"):
        unknown_receipt[name]["bundle_type"] = "unknown_bundle"
        handoff_body = _canonical_json_bytes(unknown_receipt[name])
        unknown_receipt[f"{name}_sha256"] = hashlib.sha256(
            handoff_body
        ).hexdigest()
        unknown_receipt[
            f"{name.replace('_handoff', '')}_review_state_fingerprint_sha256"
        ] = _review_state_fingerprint(unknown_receipt[name])
    unknown_receipt["review_state_status"] = "unchanged"
    unknown = client.post(
        path,
        headers=headers,
        json={
            "contract_version": "guided-decision-review-disposition-request.v1",
            "source_recheck_receipt": unknown_receipt,
            "source_recheck_receipt_sha256": hashlib.sha256(
                _canonical_json_bytes(unknown_receipt)
            ).hexdigest(),
            "review_disposition": "acknowledged_unchanged",
        },
    )
    assert unknown.status_code == 422


def test_guided_review_disposition_audit_is_redacted(client: TestClient) -> None:
    admin_headers = _login(client, "disposition-audit-admin", role="admin")
    project_id = _ready_project(client, admin_headers)
    handoff = client.get(
        f"/projects/{project_id}/guided-decision-review-handoff",
        headers=admin_headers,
    )
    recheck = client.post(
        f"/projects/{project_id}/guided-decision-review-handoff/recheck",
        headers=admin_headers,
        json={
            "contract_version": "guided-decision-review-recheck-request.v1",
            "source_handoff": handoff.json(),
            "source_handoff_sha256": hashlib.sha256(handoff.content).hexdigest(),
        },
    )
    response = client.post(
        (
            f"/projects/{project_id}/guided-decision-review-handoff/"
            "review-disposition"
        ),
        headers={**admin_headers, "User-Agent": "private-disposition-client"},
        json={
            "contract_version": "guided-decision-review-disposition-request.v1",
            "source_recheck_receipt": recheck.json(),
            "source_recheck_receipt_sha256": hashlib.sha256(
                recheck.content
            ).hexdigest(),
            "review_disposition": "acknowledged_unchanged",
        },
    )
    assert response.status_code == 200

    records = AuditStore(
        "system",
        data_dir=client.app.state.data_dir,
        backend=client.app.state.state_backend,
    ).query(filters={"action": "procurement.guided_review_disposition"})
    assert len(records) == 1
    record = records[0]
    assert record["resource_id"] == project_id
    assert record["session_id"] == ""
    assert record["ip_address"] == ""
    assert record["user_agent"] == ""
    assert record["detail"]["review_state_status"] == "unchanged"
    assert record["detail"]["review_disposition"] == "acknowledged_unchanged"
    assert record["detail"]["reviewer_identity_bound"] is False
    assert record["detail"]["disposition_receipt_persisted"] is False
    assert "source_recheck_receipt" not in record["detail"]
    assert "source_handoff" not in record["detail"]
