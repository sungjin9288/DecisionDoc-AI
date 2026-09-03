from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from app.storage.guided_decision_review_disposition_issuance_registry import (
    GuidedDecisionReviewDispositionIssuanceRegistry,
    GuidedDecisionReviewDispositionIssuanceRegistryError,
    canonical_guided_review_issuance_json_bytes,
    guided_review_issuance_sha256,
)
from app.storage.state_backend import LocalStateBackend, S3StateBackend
from tests.conditional_state_support import MemoryS3Client


RECEIPT_SHA256 = "a" * 64


def _registry(backend) -> GuidedDecisionReviewDispositionIssuanceRegistry:
    return GuidedDecisionReviewDispositionIssuanceRegistry(
        tenant_id="alpha",
        project_id="project-1",
        bundle_type="proposal_kr",
        backend=backend,
    )


@pytest.mark.parametrize("backend_kind", ["local", "s3"])
def test_issuance_concurrent_exact_create_replays_one_authoritative_record(
    tmp_path: Path,
    backend_kind: str,
) -> None:
    root = tmp_path / "state"
    client = MemoryS3Client(read_delay=0.001)

    def create() -> tuple[dict, bool]:
        backend = (
            LocalStateBackend(root)
            if backend_kind == "local"
            else S3StateBackend(
                bucket="unit-bucket",
                prefix="state/",
                s3_client=client,
            )
        )
        return _registry(backend).create(disposition_receipt_sha256=RECEIPT_SHA256)

    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(lambda _: create(), range(8)))

    records = [record for record, _ in results]
    assert len({canonical_guided_review_issuance_json_bytes(item) for item in records}) == 1
    assert sum(created for _, created in results) == 1
    record = records[0]
    assert record["disposition_receipt_sha256"] == RECEIPT_SHA256
    assert record["reviewer_identity_bound"] is False
    assert record["disposition_receipt_persisted"] is False
    assert record["authority"] == {
        "mutation": False,
        "approval": False,
        "export_execution": False,
        "provider_call": False,
        "bid_submission": False,
        "legal_contractual_commitment": False,
    }
    assert "receipt" not in record
    assert "session" not in canonical_guided_review_issuance_json_bytes(record).decode()


def test_issuance_reconciles_lost_conditional_write_only_after_exact_readback(
    tmp_path: Path,
) -> None:
    client = MemoryS3Client()
    backend = S3StateBackend(
        bucket="unit-bucket",
        prefix="state/",
        s3_client=client,
    )
    registry = _registry(backend)
    client.fail_after_next_conditional_write(
        key_fragment="guided_decision_review_disposition_issuances",
    )

    record, created = registry.create(disposition_receipt_sha256=RECEIPT_SHA256)

    assert created is False
    assert registry.read(RECEIPT_SHA256) == record


def test_issuance_post_write_disappearance_fails_closed_as_registry_error(
    tmp_path: Path,
) -> None:
    class DisappearingReadbackBackend(LocalStateBackend):
        def write_bytes_if_absent(
            self,
            relative_path: str,
            raw: bytes,
            *,
            content_type: str = "application/octet-stream",
        ) -> bool:
            created = super().write_bytes_if_absent(
                relative_path,
                raw,
                content_type=content_type,
            )
            self.delete(relative_path)
            return created

    backend = DisappearingReadbackBackend(tmp_path / "state")
    registry = _registry(backend)

    with pytest.raises(GuidedDecisionReviewDispositionIssuanceRegistryError):
        registry.create(disposition_receipt_sha256=RECEIPT_SHA256)
    assert backend.read_bytes(registry.record_path(RECEIPT_SHA256)) is None


def test_issuance_fails_closed_for_corrupt_or_foreign_scope_without_rewrite(
    tmp_path: Path,
) -> None:
    backend = LocalStateBackend(tmp_path / "state")
    registry = _registry(backend)
    record, _ = registry.create(disposition_receipt_sha256=RECEIPT_SHA256)
    path = registry.record_path(RECEIPT_SHA256)
    corrupt = b'{"corrupt":true}\n'
    backend.write_bytes(path, corrupt)

    with pytest.raises(GuidedDecisionReviewDispositionIssuanceRegistryError):
        registry.read(RECEIPT_SHA256)
    assert backend.read_bytes(path) == corrupt

    backend.write_bytes(path, canonical_guided_review_issuance_json_bytes(record))
    foreign = {**record, "tenant_id": "foreign"}
    foreign["issuance_record_binding_sha256"] = guided_review_issuance_sha256(
        {
            key: value
            for key, value in foreign.items()
            if key != "issuance_record_binding_sha256"
        }
    )
    foreign_raw = canonical_guided_review_issuance_json_bytes(foreign)
    backend.write_bytes(path, foreign_raw)
    with pytest.raises(GuidedDecisionReviewDispositionIssuanceRegistryError):
        registry.read(RECEIPT_SHA256)
    assert backend.read_bytes(path) == foreign_raw
