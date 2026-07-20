from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from contextlib import nullcontext
from pathlib import Path, PurePosixPath

import pytest

from app.storage.state_backend import LocalStateBackend, S3StateBackend
from app.storage.trajectory_store import TrajectoryStore, TrajectoryStoreError
from tests.conditional_state_support import (
    ConflictingLocalBackend,
    MemoryS3Client,
)


def _trajectory(trajectory_id: str) -> dict:
    return {
        "trajectory_id": trajectory_id,
        "task_type": "policy_planning_brief",
        "skill": {"name": "policy-planning", "version": "0.1.0"},
        "provider": "mock",
        "input": {
            "requirements": {"title": trajectory_id},
            "source_references": [{"id": "source-1"}],
        },
        "plan": ["승인 질문 분리", "근거 상태 정리"],
        "critique": ["승인 질문을 앞부분에 배치"],
        "revision_tasks": ["근거 상태와 운영 리스크 분리"],
        "draft_output": f"Decision brief for {trajectory_id}",
        "evidence_status": {
            "confirmed": ["source-1"],
            "assumptions": [],
            "gaps": [],
            "source_references": ["source-1"],
        },
        "qa": {"hard_gate_pass": True, "warnings": []},
    }


def _s3_backend(client: MemoryS3Client) -> S3StateBackend:
    return S3StateBackend(
        bucket="trajectory-artifacts",
        prefix="state/",
        s3_client=client,
    )


def _store(
    tmp_path: Path,
    backend: LocalStateBackend | S3StateBackend,
) -> TrajectoryStore:
    store = TrajectoryStore(tmp_path / "runtime", backend=backend)
    store._lock = nullcontext()
    return store


def _reviewed_export(store: TrajectoryStore, trajectory_id: str = "trj_ready") -> str:
    store.save(_trajectory(trajectory_id), tenant_id="alpha")
    store.mark_reviewed(
        trajectory_id,
        tenant_id="alpha",
        accepted=True,
        reviewer="product-owner",
        quality_score=0.95,
    )
    export_reference = store.export_sft_messages(tenant_id="alpha")
    assert export_reference is not None
    return PurePosixPath(export_reference).name


def _approved_chain(
    store: TrajectoryStore,
    *,
    trajectory_id: str = "trj_ready",
) -> tuple[str, dict, dict]:
    filename = _reviewed_export(store, trajectory_id)
    manifest = store.freeze_sft_export(
        filename,
        tenant_id="alpha",
        reviewer="dataset-owner",
    )
    assert manifest is not None
    approval = store.approve_training_from_freeze(
        manifest["manifest_id"],
        tenant_id="alpha",
        approver="ml-owner",
        eval_plan={
            "suite": "document_ops_offline_eval",
            "required_metrics": {"schema_valid_rate": 1.0},
        },
    )
    assert approval is not None
    return filename, manifest, approval


def test_selected_backend_owns_complete_governance_chain(tmp_path: Path) -> None:
    client = MemoryS3Client()
    backend = _s3_backend(client)
    store = _store(tmp_path, backend)

    filename, manifest, approval = _approved_chain(store)
    request = store.request_training_execution_from_plan(
        tenant_id="alpha",
        requester="ops-owner",
        provider="openai",
        base_model="gpt-test-base",
    )
    audit = store.export_training_pre_execution_audit(
        tenant_id="alpha",
        auditor="compliance-owner",
        provider="openai",
        base_model="gpt-test-base",
    )

    metadata_raw = backend.read_text("tenants/alpha/trajectory_metadata.json")
    assert metadata_raw is not None
    metadata = json.loads(metadata_raw)
    assert metadata["exports"][0]["size_bytes"] > 0
    assert metadata["freezes"][0]["manifest_size_bytes"] > 0
    assert metadata["training_approvals"][0]["approval_size_bytes"] > 0
    assert metadata["training_execution_requests"][0]["request_size_bytes"] > 0
    assert (
        metadata["training_pre_execution_audits"][0]["audit_size_bytes"]
        > 0
    )
    assert backend.read_bytes(f"tenants/alpha/trajectory_exports/{filename}") is not None
    assert store.get_sft_export_bytes(filename, tenant_id="alpha") is not None
    assert store.get_reviewed_sft_export_bytes(filename, tenant_id="alpha") is not None

    freezes = store.list_dataset_freezes(tenant_id="alpha")
    approvals = store.list_training_approvals(tenant_id="alpha")
    requests = store.list_training_execution_requests(tenant_id="alpha")
    audits = store.list_training_pre_execution_audits(tenant_id="alpha")
    assert freezes[0]["manifest_id"] == manifest["manifest_id"]
    assert approvals[0]["approval_id"] == approval["approval_id"]
    assert requests[0]["request_id"] == request["request_id"]
    assert audits[0]["audit_id"] == audit["audit_id"]
    assert all(
        item["integrity_verified"] is True
        for item in (freezes[0], approvals[0], requests[0], audits[0])
    )
    assert all(
        item["size_binding_verified"] is True
        for item in (freezes[0], approvals[0], requests[0], audits[0])
    )
    assert store.get_training_pre_execution_audit_bytes(
        audits[0]["audit_file"],
        tenant_id="alpha",
    ) is not None
    audit_path = (
        f"tenants/alpha/trajectory_training_audits/"
        f"{audits[0]['audit_file']}"
    )
    audit_bytes = backend.read_bytes(audit_path)
    assert audit_bytes is not None
    backend.write_bytes(
        audit_path,
        audit_bytes + b"\n",
        content_type="application/json; charset=utf-8",
    )
    assert store.get_training_pre_execution_audit_bytes(
        audits[0]["audit_file"],
        tenant_id="alpha",
    ) is None
    assert not (tmp_path / "runtime" / "tenants" / "alpha").exists()


@pytest.mark.parametrize("backend_kind", ["local", "s3"])
def test_concurrent_freezes_preserve_every_metadata_entry(
    tmp_path: Path,
    backend_kind: str,
) -> None:
    client = MemoryS3Client(read_delay=0.001)
    local_root = tmp_path / "state"

    def backend() -> LocalStateBackend | S3StateBackend:
        if backend_kind == "local":
            return LocalStateBackend(local_root)
        return _s3_backend(client)

    filename = _reviewed_export(_store(tmp_path, backend()))

    def freeze(index: int) -> str:
        manifest = _store(tmp_path, backend()).freeze_sft_export(
            filename,
            tenant_id="alpha",
            reviewer=f"dataset-owner-{index}",
        )
        assert manifest is not None
        return manifest["manifest_id"]

    with ThreadPoolExecutor(max_workers=12) as executor:
        manifest_ids = list(executor.map(freeze, range(12)))

    reader = _store(tmp_path, backend())
    freezes = reader.list_dataset_freezes(tenant_id="alpha", limit=20)
    assert {item["manifest_id"] for item in freezes} == set(manifest_ids)
    assert len(freezes) == 12
    assert all(item["integrity_verified"] is True for item in freezes)


def test_lost_metadata_response_reconciles_after_successor_freeze(
    tmp_path: Path,
) -> None:
    client = MemoryS3Client()
    first = _store(tmp_path, _s3_backend(client))
    successor = _store(tmp_path, _s3_backend(client))
    filename = _reviewed_export(first)
    successor_manifest: dict = {}

    def append_successor() -> None:
        created = successor.freeze_sft_export(
            filename,
            tenant_id="alpha",
            reviewer="successor-owner",
        )
        assert created is not None
        successor_manifest.update(created)

    client.fail_after_next_conditional_write(
        key_fragment="trajectory_metadata.json",
        after_write=append_successor,
    )
    original = first.freeze_sft_export(
        filename,
        tenant_id="alpha",
        reviewer="original-owner",
    )

    assert original is not None
    freezes = first.list_dataset_freezes(tenant_id="alpha")
    assert {item["manifest_id"] for item in freezes} == {
        original["manifest_id"],
        successor_manifest["manifest_id"],
    }


def test_lost_immutable_export_response_is_reconciled(tmp_path: Path) -> None:
    client = MemoryS3Client()
    store = _store(tmp_path, _s3_backend(client))
    store.save(_trajectory("trj_export_loss"), tenant_id="alpha")
    store.mark_reviewed(
        "trj_export_loss",
        tenant_id="alpha",
        accepted=True,
        reviewer="product-owner",
        quality_score=0.95,
    )
    client.fail_after_next_conditional_write(
        key_fragment="trajectory_exports/",
    )

    export_reference = store.export_sft_messages(tenant_id="alpha")

    assert export_reference is not None
    filename = PurePosixPath(export_reference).name
    assert store.get_sft_export_bytes(filename, tenant_id="alpha") is not None
    assert store.list_sft_exports(tenant_id="alpha")[0]["integrity_verified"] is True


def test_tampered_export_remains_inspectable_but_cannot_be_downloaded(
    tmp_path: Path,
) -> None:
    client = MemoryS3Client()
    backend = _s3_backend(client)
    store = _store(tmp_path, backend)
    filename = _reviewed_export(store, "trj_tampered")
    relative_path = f"tenants/alpha/trajectory_exports/{filename}"
    original = backend.read_bytes(relative_path)
    assert original is not None
    backend.write_bytes(
        relative_path,
        original + b"\n",
        content_type="application/x-ndjson; charset=utf-8",
    )

    report = store.inspect_sft_export_quality(
        filename,
        tenant_id="alpha",
    )

    assert report is not None
    assert report["content_sha256_matches_metadata"] is False
    assert store.get_sft_export_bytes(filename, tenant_id="alpha") is None
    assert (
        store.get_reviewed_sft_export_bytes(
            filename,
            tenant_id="alpha",
        )
        is None
    )


def test_legacy_hash_only_export_remains_readable_without_size_claim(
    tmp_path: Path,
) -> None:
    backend = LocalStateBackend(tmp_path / "state")
    store = _store(tmp_path, backend)
    filename = _reviewed_export(store, "trj_legacy_size")
    metadata_path = "tenants/alpha/trajectory_metadata.json"
    metadata_raw = backend.read_text(metadata_path)
    assert metadata_raw is not None
    metadata = json.loads(metadata_raw)
    metadata["exports"][0].pop("size_bytes")
    backend.write_text(metadata_path, json.dumps(metadata))

    assert store.get_sft_export_bytes(filename, tenant_id="alpha") is not None
    listed = store.list_sft_exports(tenant_id="alpha")
    assert listed[0]["integrity_verified"] is True
    assert listed[0]["size_binding_verified"] is False


@pytest.mark.parametrize(
    "corrupt",
    [
        '{"tenant_id":"alpha","exports":[],"exports":[]}',
        json.dumps(
            {
                "tenant_id": "alpha",
                "export_count": 2,
                "exports": [
                    {
                        "tenant_id": "alpha",
                        "filename": "sft_first.jsonl",
                        "export_fingerprint": "same-fingerprint",
                        "size_bytes": 1,
                        "content_sha256": "a" * 64,
                    },
                    {
                        "tenant_id": "alpha",
                        "filename": "sft_second.jsonl",
                        "export_fingerprint": "same-fingerprint",
                        "size_bytes": 1,
                        "content_sha256": "b" * 64,
                    },
                ],
            }
        ),
        json.dumps(
            {
                "tenant_id": "alpha",
                "freeze_count": 1,
            }
        ),
    ],
)
def test_corrupt_metadata_fails_closed_without_overwrite(
    tmp_path: Path,
    corrupt: str,
) -> None:
    backend = LocalStateBackend(tmp_path / "state")
    store = _store(tmp_path, backend)
    relative_path = "tenants/alpha/trajectory_metadata.json"
    backend.write_text(relative_path, corrupt)

    with pytest.raises(TrajectoryStoreError, match="metadata"):
        store.list_sft_exports(tenant_id="alpha")

    assert backend.read_text(relative_path) == corrupt


def test_metadata_conflict_cap_leaves_export_outside_authority(tmp_path: Path) -> None:
    backend = ConflictingLocalBackend(
        tmp_path / "state",
        conflict_suffix="trajectory_metadata.json",
    )
    store = _store(tmp_path, backend)
    store.save(_trajectory("trj_conflict"), tenant_id="alpha")
    store.mark_reviewed(
        "trj_conflict",
        tenant_id="alpha",
        accepted=True,
        reviewer="product-owner",
        quality_score=0.95,
    )

    with pytest.raises(TrajectoryStoreError, match="changed too many times"):
        store.export_sft_messages(tenant_id="alpha")

    assert backend.attempts == 32
    assert store.list_sft_exports(tenant_id="alpha") == []
    assert backend.list_prefix("tenants/alpha/trajectory_exports")


def test_reviewer_signoff_summary_reads_selected_backend(tmp_path: Path) -> None:
    client = MemoryS3Client()
    backend = _s3_backend(client)
    store = _store(tmp_path, backend)
    record = {
        "tenant_id": "alpha",
        "report_type": "document_ops_reviewer_signoff",
        "signoff_record_id": "signoff-1",
        "created_at": "2026-07-20T00:00:00+00:00",
        "required_reviewers": [],
        "signoff_boundary": {},
        "generation_boundary": {},
    }
    backend.write_text(
        "tenants/alpha/trajectory_reviewer_signoffs/signoff.json",
        json.dumps(record),
    )

    summary = store.reviewer_signoff_summary(tenant_id="alpha")

    assert summary["record_directory_exists"] is True
    assert summary["record_count"] == 1
    assert summary["records"][0]["signoff_record_id"] == "signoff-1"
    assert not (tmp_path / "runtime" / "tenants" / "alpha").exists()
