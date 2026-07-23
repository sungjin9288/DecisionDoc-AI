from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import pytest

from app.storage.auth_session_retention import (
    build_retention_recheck_receipt,
    build_retention_review_disposition_receipt,
    build_retention_review_handoff,
    canonical_retention_json_bytes,
    retention_sha256,
)
from app.storage.auth_session_retention_registry import (
    AuthSessionRetentionRegistry,
    AuthSessionRetentionRegistryConflictError,
    AuthSessionRetentionRegistryError,
)
from app.storage.state_backend import LocalStateBackend, S3StateBackend
from tests.conditional_state_support import MemoryS3Client


def _source_receipt(
    *,
    tenant_id: str = "alpha",
    review_disposition: str = "acknowledged_unchanged",
) -> dict:
    generated_at = datetime(2026, 7, 23, 2, 0, tzinfo=timezone.utc)
    comparison = {
        "contract_version": "auth-session-retention-comparison.v1",
        "generated_at": generated_at.isoformat(),
        "policy_days": [30, 90, 180, 365],
        "inspected_sessions": 0,
        "active_sessions": 0,
        "policies": [
            {
                "retention_days": days,
                "eligible_before": (generated_at - timedelta(days=days)).isoformat(),
                "eligible_sessions": 0,
                "eligible_by_reason": {"expired": 0, "revoked": 0},
                "retained_inactive_sessions": 0,
                "oldest_eligible_inactive_at": None,
            }
            for days in (30, 90, 180, 365)
        ],
        "read_only": True,
        "deletion_authorized": False,
        "snapshot_atomic": False,
        "requires_recheck_before_mutation": True,
    }
    handoff = build_retention_review_handoff(
        tenant_id=tenant_id,
        retention_days=90,
        comparison=comparison,
    )
    handoff_sha256 = retention_sha256(handoff)
    recheck = build_retention_recheck_receipt(
        source_handoff=handoff,
        source_handoff_sha256=handoff_sha256,
        current_handoff=handoff,
    )
    return build_retention_review_disposition_receipt(
        source_recheck_receipt=recheck,
        source_recheck_receipt_sha256=retention_sha256(recheck),
        expected_tenant_id=tenant_id,
        review_disposition=review_disposition,
    )


def _registry(tmp_path: Path, backend) -> AuthSessionRetentionRegistry:
    return AuthSessionRetentionRegistry(
        tenant_id="alpha",
        backend=backend,
    )


def _create(
    registry: AuthSessionRetentionRegistry,
    *,
    operation_id: str,
    reviewer_user_id: str = "reviewer-1",
    reviewer_username: str = "first-name",
    source: dict | None = None,
):
    receipt = source or _source_receipt()
    return registry.create(
        operation_id=operation_id,
        reviewer_user_id=reviewer_user_id,
        reviewer_username=reviewer_username,
        reviewer_role="admin",
        source_disposition_receipt=receipt,
        source_disposition_receipt_sha256=retention_sha256(receipt),
    )


@pytest.mark.parametrize("backend_kind", ["local", "s3"])
def test_registry_concurrent_exact_create_replays_one_canonical_record(
    tmp_path: Path,
    backend_kind: str,
) -> None:
    client = MemoryS3Client(read_delay=0.001)
    root = tmp_path / "state"
    operation_id = str(uuid4())

    def make_registry() -> AuthSessionRetentionRegistry:
        backend = (
            LocalStateBackend(root)
            if backend_kind == "local"
            else S3StateBackend(bucket="unit-bucket", prefix="state/", s3_client=client)
        )
        return _registry(tmp_path, backend)

    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(lambda _: _create(make_registry(), operation_id=operation_id), range(8)))

    records = [record for record, _ in results]
    assert len({canonical_retention_json_bytes(record) for record in records}) == 1
    assert sum(created for _, created in results) == 1
    record = records[0]
    assert record["reviewer_identity_bound"] is True
    assert record["registry_record_persisted"] is True
    assert record["reviewer_role"] == "admin"
    assert record["recorded_at"].endswith("+00:00")
    assert record["record_binding_sha256"] == retention_sha256(
        {
            key: value
            for key, value in record.items()
            if key != "record_binding_sha256"
        }
    )
    assert all(
        record[field] is False
        for field in (
            "approval_granted",
            "execution_authorized",
            "policy_change_authorized",
            "deletion_authorized",
            "scheduler_authorized",
            "mass_revoke_authorized",
        )
    )


def test_registry_replay_keeps_original_username_and_exact_bytes_after_rename(
    tmp_path: Path,
) -> None:
    backend = LocalStateBackend(tmp_path / "state")
    registry = _registry(tmp_path, backend)
    operation_id = str(uuid4())
    first, created = _create(registry, operation_id=operation_id, reviewer_username="before-rename")
    replay, replayed = _create(registry, operation_id=operation_id, reviewer_username="after-rename")

    assert created is True
    assert replayed is False
    assert canonical_retention_json_bytes(replay) == canonical_retention_json_bytes(first)
    assert replay["reviewer_username"] == "before-rename"
    raw = backend.read_text(registry.record_path(operation_id))
    assert raw is not None
    assert raw.encode("utf-8") == canonical_retention_json_bytes(first)
    assert replay["request_sha256"] == retention_sha256(
        {
            "tenant_id": "alpha",
            "operation_id": operation_id,
            "reviewer_user_id": "reviewer-1",
            "source_disposition_receipt_sha256": retention_sha256(_source_receipt()),
        }
    )


def test_registry_rejects_operation_reuse_with_changed_reviewer_or_source(tmp_path: Path) -> None:
    registry = _registry(tmp_path, LocalStateBackend(tmp_path / "state"))
    operation_id = str(uuid4())
    _create(registry, operation_id=operation_id)

    with pytest.raises(AuthSessionRetentionRegistryConflictError):
        _create(registry, operation_id=operation_id, reviewer_user_id="reviewer-2")
    with pytest.raises(AuthSessionRetentionRegistryConflictError):
        _create(
            registry,
            operation_id=operation_id,
            source=_source_receipt(review_disposition="review_deferred"),
        )


def test_registry_reconciles_lost_conditional_write_response(tmp_path: Path) -> None:
    client = MemoryS3Client()
    backend = S3StateBackend(bucket="unit-bucket", prefix="state/", s3_client=client)
    registry = _registry(tmp_path, backend)
    operation_id = str(uuid4())
    client.fail_after_next_conditional_write(
        key_fragment="auth_session_retention_review_dispositions",
    )

    record, created = _create(registry, operation_id=operation_id)

    assert created is False
    assert registry.read(operation_id) == record


def test_registry_lists_strict_summaries_in_recorded_at_and_operation_order(
    tmp_path: Path,
) -> None:
    backend = LocalStateBackend(tmp_path / "state")
    registry = _registry(tmp_path, backend)
    operation_ids = [
        "10000000-0000-4000-8000-000000000000",
        "20000000-0000-4000-8000-000000000000",
    ]
    recorded_at = "2026-07-23T02:30:00+00:00"
    records = []
    for operation_id in operation_ids:
        record, _ = _create(registry, operation_id=operation_id)
        record["recorded_at"] = recorded_at
        record["record_binding_sha256"] = retention_sha256(
            {
                key: value
                for key, value in record.items()
                if key != "record_binding_sha256"
            }
        )
        backend.write_text(
            registry.record_path(operation_id),
            canonical_retention_json_bytes(record).decode("utf-8"),
        )
        records.append(record)

    summaries = registry.list_summaries()

    assert [summary["operation_id"] for summary in summaries] == list(
        reversed(operation_ids)
    )
    assert all(
        set(summary)
        == {
            "operation_id",
            "tenant_id",
            "reviewer_user_id",
            "reviewer_username",
            "reviewer_role",
            "recorded_at",
            "record_sha256",
            "source_disposition_receipt_sha256",
            "selected_policy_days",
            "aggregate_status",
            "review_disposition",
            "record_status",
            "read_only",
            "snapshot_atomic",
        }
        for summary in summaries
    )
    assert summaries[0]["record_sha256"] == retention_sha256(records[1])


def test_registry_fails_closed_for_corrupt_foreign_and_path_drift_records(tmp_path: Path) -> None:
    backend = LocalStateBackend(tmp_path / "state")
    registry = _registry(tmp_path, backend)
    operation_id = str(uuid4())
    record, _ = _create(registry, operation_id=operation_id)
    path = registry.record_path(operation_id)

    backend.write_text(path, "{not-json")
    with pytest.raises(AuthSessionRetentionRegistryError):
        registry.read(operation_id)
    assert backend.read_text(path) == "{not-json"

    backend.write_text(path, canonical_retention_json_bytes(record).decode("utf-8"))
    foreign = dict(record)
    foreign["tenant_id"] = "other"
    backend.write_text(path, canonical_retention_json_bytes(foreign).decode("utf-8"))
    with pytest.raises(AuthSessionRetentionRegistryError):
        registry.list_summaries()
    backend.write_text(path, canonical_retention_json_bytes(record).decode("utf-8"))
    backend.write_text(
        "tenants/alpha/auth_session_retention_review_dispositions/unexpected.json",
        canonical_retention_json_bytes(record).decode("utf-8"),
    )
    with pytest.raises(AuthSessionRetentionRegistryError):
        registry.list_summaries()


@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("reviewer_username", "tampered-reviewer"),
        ("recorded_at", "2026-07-23T02:45:00+00:00"),
    ],
)
def test_registry_record_binding_rejects_historical_identity_or_time_tampering(
    tmp_path: Path,
    field: str,
    replacement: str,
) -> None:
    backend = LocalStateBackend(tmp_path / "state")
    registry = _registry(tmp_path, backend)
    operation_id = str(uuid4())
    record, _ = _create(registry, operation_id=operation_id)
    tampered = {**record, field: replacement}
    path = registry.record_path(operation_id)
    raw = canonical_retention_json_bytes(tampered).decode("utf-8")
    backend.write_text(path, raw)

    with pytest.raises(AuthSessionRetentionRegistryError):
        registry.read(operation_id)

    assert backend.read_text(path) == raw


def test_registry_list_fails_closed_when_a_listed_record_disappears(
    tmp_path: Path,
) -> None:
    class VanishingListBackend(LocalStateBackend):
        def list_prefix(self, relative_prefix: str) -> list[str]:
            paths = super().list_prefix(relative_prefix)
            for path in paths:
                self.delete(path)
            return paths

    backend = VanishingListBackend(tmp_path / "state")
    registry = _registry(tmp_path, backend)
    _create(registry, operation_id=str(uuid4()))

    with pytest.raises(
        AuthSessionRetentionRegistryError,
        match="changed during list",
    ):
        registry.list_summaries()


def test_registry_preserves_invalid_utf8_from_fake_s3(tmp_path: Path) -> None:
    client = MemoryS3Client()
    backend = S3StateBackend(bucket="unit-bucket", prefix="state/", s3_client=client)
    registry = _registry(tmp_path, backend)
    operation_id = str(uuid4())
    _create(registry, operation_id=operation_id)
    key = f"state/{registry.record_path(operation_id)}"
    client.objects[("unit-bucket", key)] = b"\xff"

    with pytest.raises(AuthSessionRetentionRegistryError):
        registry.read(operation_id)
    assert client.objects[("unit-bucket", key)] == b"\xff"
