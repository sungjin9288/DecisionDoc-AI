from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4

import pytest

from app.schemas.decision_evidence import (
    DecisionEvidenceAuthority,
    GuidedDecisionReviewHandoffResponse,
    GuidedDecisionReviewNextCheck,
    GuidedDecisionReviewStage,
)
from app.services.guided_decision_review_service import GuidedDecisionReviewService
from app.storage.guided_decision_review_disposition_registry import (
    GuidedDecisionReviewDispositionRegistry,
    GuidedDecisionReviewDispositionRegistryConflictError,
    GuidedDecisionReviewDispositionRegistryError,
    canonical_guided_review_registry_json_bytes,
    guided_review_registry_sha256,
)
from app.storage.guided_decision_review_disposition_issuance_registry import (
    get_guided_decision_review_disposition_issuance_registry,
    guided_review_issuance_sha256,
)
from app.storage.state_backend import LocalStateBackend, S3StateBackend
from tests.conditional_state_support import MemoryS3Client


def _source_receipt(*, disposition: str = "acknowledged_unchanged") -> dict:
    service = GuidedDecisionReviewService()
    authority = DecisionEvidenceAuthority(
        mutation=False,
        approval=False,
        export_execution=False,
        provider_call=False,
        bid_submission=False,
        legal_contractual_commitment=False,
    )
    handoff = GuidedDecisionReviewHandoffResponse(
        contract_version="guided-decision-review-handoff.v1",
        source_contract_version="decision_evidence_map.v1",
        source_generated_at="2026-08-18T00:00:00+00:00",
        project_id="project-1",
        bundle_type="proposal_kr",
        projection_fingerprint="a" * 64,
        read_only=True,
        snapshot_atomic=False,
        requires_recheck_before_reliance=True,
        handoff_persisted=False,
        overall_state="Needs review",
        recommended_next_check=GuidedDecisionReviewNextCheck(
            stage="Decision",
            instruction="Inspect the decision evidence.",
        ),
        stages=[
            GuidedDecisionReviewStage(
                name=name,
                status="needs_attention",
                evidence=f"{name} evidence requires review.",
            )
            for name in ("Decision", "Evidence", "Review", "Documents")
        ],
        authority=authority,
    )
    handoff_hash = guided_review_registry_sha256(handoff.model_dump(mode="json"))
    recheck = service.recheck(
        source_handoff=handoff,
        source_handoff_sha256=handoff_hash,
        current_handoff=handoff,
        expected_project_id="project-1",
    )
    recheck_hash = guided_review_registry_sha256(recheck.model_dump(mode="json"))
    receipt = service.issue_disposition(
        source_recheck_receipt=recheck,
        source_recheck_receipt_sha256=recheck_hash,
        review_disposition=disposition,
        expected_project_id="project-1",
    )
    return receipt.model_dump(mode="json")


def _registry(backend) -> GuidedDecisionReviewDispositionRegistry:
    return GuidedDecisionReviewDispositionRegistry(
        tenant_id="alpha",
        project_id="project-1",
        bundle_type="proposal_kr",
        backend=backend,
    )


def _create(
    registry: GuidedDecisionReviewDispositionRegistry,
    *,
    operation_id: str,
    reviewer_user_id: str = "reviewer-1",
    reviewer_username: str = "first-name",
    reviewer_role: str = "member",
    source: dict | None = None,
):
    receipt = source or _source_receipt()
    return registry.create(
        operation_id=operation_id,
        reviewer_user_id=reviewer_user_id,
        reviewer_username=reviewer_username,
        reviewer_role=reviewer_role,
        source_disposition_receipt=receipt,
        source_disposition_receipt_sha256=guided_review_registry_sha256(receipt),
    )


@pytest.mark.parametrize("backend_kind", ["local", "s3"])
def test_registry_concurrent_exact_create_converges_to_one_record(
    tmp_path: Path,
    backend_kind: str,
) -> None:
    operation_id = str(uuid4())
    root = tmp_path / "state"
    client = MemoryS3Client(read_delay=0.001)

    def registry() -> GuidedDecisionReviewDispositionRegistry:
        backend = (
            LocalStateBackend(root)
            if backend_kind == "local"
            else S3StateBackend(
                bucket="unit-bucket",
                prefix="state/",
                s3_client=client,
            )
        )
        return _registry(backend)

    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(
            executor.map(
                lambda _: _create(registry(), operation_id=operation_id),
                range(8),
            )
        )

    records = [record for record, _ in results]
    assert len({canonical_guided_review_registry_json_bytes(record) for record in records}) == 1
    assert sum(created for _, created in results) == 1
    record = records[0]
    assert record["reviewer_identity_bound"] is True
    assert record["registry_record_persisted"] is True
    assert record["source_disposition_receipt"]["reviewer_identity_bound"] is False
    assert record["source_disposition_receipt"]["disposition_receipt_persisted"] is False
    assert record["authority"] == {
        "mutation": False,
        "approval": False,
        "export_execution": False,
        "provider_call": False,
        "bid_submission": False,
        "legal_contractual_commitment": False,
    }


def test_registry_replay_keeps_historical_identity_bytes_after_username_and_role_drift(
    tmp_path: Path,
) -> None:
    registry = _registry(LocalStateBackend(tmp_path / "state"))
    operation_id = str(uuid4())
    first, created = _create(
        registry,
        operation_id=operation_id,
        reviewer_username="before",
        reviewer_role="admin",
    )
    replay, replay_created = _create(
        registry,
        operation_id=operation_id,
        reviewer_username="after",
        reviewer_role="member",
    )

    assert created is True
    assert replay_created is False
    assert canonical_guided_review_registry_json_bytes(replay) == (
        canonical_guided_review_registry_json_bytes(first)
    )
    assert replay["reviewer_username"] == "before"
    assert replay["reviewer_role"] == "admin"
    assert replay["recorded_at"] == first["recorded_at"]
    assert replay["request_binding_sha256"] == guided_review_registry_sha256(
        {
            "tenant_id": "alpha",
            "project_id": "project-1",
            "bundle_type": "proposal_kr",
            "operation_id": operation_id,
            "reviewer_user_id": "reviewer-1",
            "source_disposition_receipt_sha256": guided_review_registry_sha256(
                _source_receipt()
            ),
        }
    )


def test_registry_rejects_changed_stable_reviewer_or_source_without_overwrite(
    tmp_path: Path,
) -> None:
    backend = LocalStateBackend(tmp_path / "state")
    registry = _registry(backend)
    operation_id = str(uuid4())
    first, _ = _create(registry, operation_id=operation_id)
    path = registry.record_path(operation_id)
    first_raw = backend.read_bytes(path)

    with pytest.raises(GuidedDecisionReviewDispositionRegistryConflictError):
        _create(
            registry,
            operation_id=operation_id,
            reviewer_user_id="reviewer-2",
        )
    with pytest.raises(GuidedDecisionReviewDispositionRegistryConflictError):
        _create(
            registry,
            operation_id=operation_id,
            source=_source_receipt(disposition="review_deferred"),
        )

    assert registry.read(operation_id) == first
    assert backend.read_bytes(path) == first_raw


def test_registry_reconciles_uncertain_conditional_create_only_after_exact_binding(
    tmp_path: Path,
) -> None:
    client = MemoryS3Client()
    backend = S3StateBackend(
        bucket="unit-bucket",
        prefix="state/",
        s3_client=client,
    )
    registry = _registry(backend)
    operation_id = str(uuid4())
    client.fail_after_next_conditional_write(
        key_fragment="guided_decision_review_dispositions",
    )

    record, created = _create(registry, operation_id=operation_id)

    assert created is False
    assert registry.read(operation_id) == record


def test_registry_v2_embeds_only_authoritative_same_backend_issuance_proof(
    tmp_path: Path,
) -> None:
    backend = LocalStateBackend(tmp_path / "state")
    registry = _registry(backend)
    source = _source_receipt()
    source_hash = guided_review_registry_sha256(source)
    issuance, _ = get_guided_decision_review_disposition_issuance_registry(
        tenant_id="alpha",
        project_id="project-1",
        bundle_type="proposal_kr",
        backend=backend,
    ).create(disposition_receipt_sha256=source_hash)

    record, created = registry.create(
        contract_version="guided-decision-review-disposition-record-request.v2",
        operation_id=str(uuid4()),
        reviewer_user_id="reviewer-1",
        reviewer_username="first-name",
        reviewer_role="member",
        source_disposition_receipt=source,
        source_disposition_receipt_sha256=source_hash,
    )

    assert created is True
    assert record["contract_version"] == "guided-decision-review-disposition-record.v2"
    assert record["issuance_provenance"] == "server_issued"
    assert record["source_issuance_metadata"] == issuance
    assert record["source_issuance_metadata_sha256"] == guided_review_issuance_sha256(
        issuance
    )
    assert "source_disposition_receipt" not in registry.list_summaries()[0]


def test_registry_path_is_scoped_and_uses_only_operation_hash(tmp_path: Path) -> None:
    registry = _registry(LocalStateBackend(tmp_path / "state"))
    operation_id = str(uuid4())
    path = registry.record_path(operation_id)

    assert path.startswith(
        "tenants/alpha/projects/project-1/"
        "guided_decision_review_dispositions/proposal_kr/"
    )
    assert operation_id not in path
    assert path.endswith(
        f"{__import__('hashlib').sha256(operation_id.encode()).hexdigest()}.json"
    )


def test_registry_list_is_sorted_redacted_and_owner_filtered(tmp_path: Path) -> None:
    backend = LocalStateBackend(tmp_path / "state")
    registry = _registry(backend)
    operation_ids = [
        "10000000-0000-4000-8000-000000000000",
        "20000000-0000-4000-8000-000000000000",
    ]
    for operation_id, reviewer_user_id in zip(
        operation_ids,
        ("reviewer-1", "reviewer-2"),
        strict=True,
    ):
        record, _ = _create(
            registry,
            operation_id=operation_id,
            reviewer_user_id=reviewer_user_id,
        )
        record["recorded_at"] = "2026-08-18T00:30:00+00:00"
        record["record_binding_sha256"] = guided_review_registry_sha256(
            {
                key: value
                for key, value in record.items()
                if key != "record_binding_sha256"
            }
        )
        backend.write_bytes(
            registry.record_path(operation_id),
            canonical_guided_review_registry_json_bytes(record),
        )

    summaries = registry.list_summaries()
    owned = registry.list_summaries(reviewer_user_id="reviewer-1")

    assert [item["operation_id"] for item in summaries] == list(
        reversed(operation_ids)
    )
    assert [item["operation_id"] for item in owned] == [operation_ids[0]]
    for summary in summaries:
        assert "source_disposition_receipt" not in summary
        assert "reviewer_user_id" not in summary
        assert "request_binding_sha256" not in summary
        assert "record_binding_sha256" not in summary


@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("reviewer_username", "tampered"),
        ("reviewer_role", "admin"),
        ("recorded_at", "2026-08-18T00:45:00+00:00"),
        ("review_only", False),
    ],
)
def test_registry_full_binding_rejects_historical_or_boundary_tampering(
    tmp_path: Path,
    field: str,
    replacement: object,
) -> None:
    backend = LocalStateBackend(tmp_path / "state")
    registry = _registry(backend)
    operation_id = str(uuid4())
    record, _ = _create(registry, operation_id=operation_id)
    tampered = {**record, field: replacement}
    path = registry.record_path(operation_id)
    raw = canonical_guided_review_registry_json_bytes(tampered)
    backend.write_bytes(path, raw)

    with pytest.raises(GuidedDecisionReviewDispositionRegistryError):
        registry.read(operation_id)
    assert backend.read_bytes(path) == raw


def test_registry_fails_closed_for_noncanonical_duplicate_and_vanishing_state(
    tmp_path: Path,
) -> None:
    backend = LocalStateBackend(tmp_path / "state")
    registry = _registry(backend)
    operation_id = str(uuid4())
    record, _ = _create(registry, operation_id=operation_id)
    path = registry.record_path(operation_id)
    backend.write_bytes(path, b' {"not":"canonical"}')
    with pytest.raises(GuidedDecisionReviewDispositionRegistryError):
        registry.read(operation_id)

    backend.write_bytes(path, canonical_guided_review_registry_json_bytes(record))
    backend.write_bytes(
        f"{registry.prefix}/unexpected.json",
        canonical_guided_review_registry_json_bytes(record),
    )
    with pytest.raises(GuidedDecisionReviewDispositionRegistryError):
        registry.list_summaries()

    class VanishingBackend(LocalStateBackend):
        def list_prefix(self, relative_prefix: str) -> list[str]:
            paths = super().list_prefix(relative_prefix)
            for listed_path in paths:
                self.delete(listed_path)
            return paths

    vanishing = _registry(VanishingBackend(tmp_path / "vanishing"))
    _create(vanishing, operation_id=str(uuid4()))
    with pytest.raises(
        GuidedDecisionReviewDispositionRegistryError,
        match="changed during list",
    ):
        vanishing.list_summaries()
