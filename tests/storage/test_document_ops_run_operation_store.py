from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from app.storage.document_ops_run_operation_store import (
    DocumentOpsRunOperationConflictError,
    DocumentOpsRunOperationStore,
    DocumentOpsRunOperationStoreError,
    DocumentOpsRunOperationUnavailableError,
)
from app.storage.state_backend import LocalStateBackend, S3StateBackend
from tests.conditional_state_support import MemoryS3Client


def _backend(
    tmp_path: Path,
    backend_kind: str,
    client: MemoryS3Client,
) -> LocalStateBackend | S3StateBackend:
    if backend_kind == "local":
        return LocalStateBackend(tmp_path / "state")
    return S3StateBackend(
        bucket="document-ops-run-operations",
        prefix="state/",
        s3_client=client,
    )


def _request_payload(title: str = "중복 실행 차단") -> dict:
    return {
        "task_type": "decision_brief",
        "requirements": {"title": title},
        "project_context": {},
        "source_summaries": [],
        "source_references": [],
        "skill_name": None,
        "capture_trajectory": True,
    }


def _result() -> dict:
    return {
        "task_type": "decision_brief",
        "skill_name": "decision-brief",
        "skill_version": "0.1.0",
        "provider_name": "mock",
        "plan": ["요구사항을 확인합니다."],
        "critique": [],
        "revision_tasks": [],
        "draft": "# 중복 실행 차단",
        "evidence_status": {
            "confirmed": [],
            "assumptions": [],
            "gaps": [],
            "source_references": [],
        },
        "qa": {"hard_gate_pass": True},
        "quality_warnings": [],
        "trajectory": {"trajectory_id": "trj_operation"},
        "trajectory_id": "trj_operation",
        "trajectory_saved": True,
    }


@pytest.mark.parametrize("backend_kind", ["local", "s3"])
def test_agent_run_operation_claim_allows_one_shared_backend_owner(
    tmp_path: Path,
    backend_kind: str,
) -> None:
    client = MemoryS3Client(read_delay=0.001)

    def claim() -> object:
        store = DocumentOpsRunOperationStore(
            backend=_backend(tmp_path, backend_kind, client),
        )
        try:
            return store.claim(
                tenant_id="alpha",
                operation_id="agent-run:shared",
                request_payload=_request_payload(),
            )
        except DocumentOpsRunOperationUnavailableError:
            return "pending"

    with ThreadPoolExecutor(max_workers=8) as executor:
        claims = list(executor.map(lambda _: claim(), range(8)))

    owners = [item for item in claims if item != "pending"]
    assert len(owners) == 1
    assert owners[0].should_execute is True
    assert sum(item == "pending" for item in claims) == 7


@pytest.mark.parametrize("backend_kind", ["local", "s3"])
def test_agent_run_operation_replays_the_verified_original_result(
    tmp_path: Path,
    backend_kind: str,
) -> None:
    client = MemoryS3Client()
    first_store = DocumentOpsRunOperationStore(
        backend=_backend(tmp_path, backend_kind, client),
    )
    claim = first_store.claim(
        tenant_id="alpha",
        operation_id="agent-run:replay",
        request_payload=_request_payload(),
    )
    first_store.complete(claim, result=_result())

    replay = DocumentOpsRunOperationStore(
        backend=_backend(tmp_path, backend_kind, client),
    ).claim(
        tenant_id="alpha",
        operation_id="agent-run:replay",
        request_payload=_request_payload(),
    )

    assert replay.should_execute is False
    assert replay.result == _result()


def test_agent_run_operation_rejects_changed_payload_and_failed_retry(
    tmp_path: Path,
) -> None:
    store = DocumentOpsRunOperationStore(
        backend=LocalStateBackend(tmp_path / "state"),
    )
    claim = store.claim(
        tenant_id="alpha",
        operation_id="agent-run:bound",
        request_payload=_request_payload(),
    )

    with pytest.raises(DocumentOpsRunOperationConflictError):
        store.claim(
            tenant_id="alpha",
            operation_id="agent-run:bound",
            request_payload=_request_payload("다른 요청"),
        )

    store.fail(claim)
    with pytest.raises(DocumentOpsRunOperationUnavailableError, match="did not complete"):
        store.claim(
            tenant_id="alpha",
            operation_id="agent-run:bound",
            request_payload=_request_payload(),
        )


def test_agent_run_operation_fails_closed_on_corrupt_receipt(
    tmp_path: Path,
) -> None:
    backend = LocalStateBackend(tmp_path / "state")
    store = DocumentOpsRunOperationStore(backend=backend)
    relative_path = store.operation_path(
        tenant_id="alpha",
        operation_id="agent-run:corrupt",
    )
    raw = '{"schema_version":"document_ops_agent_operation_v1","status":"running"}'
    backend.write_text(relative_path, raw)

    with pytest.raises(DocumentOpsRunOperationStoreError):
        store.claim(
            tenant_id="alpha",
            operation_id="agent-run:corrupt",
            request_payload=_request_payload(),
        )

    assert backend.read_text(relative_path) == raw

    claim = store.claim(
        tenant_id="alpha",
        operation_id="agent-run:tampered-result",
        request_payload=_request_payload(),
    )
    store.complete(claim, result=_result())
    result_path = store.operation_path(
        tenant_id="alpha",
        operation_id="agent-run:tampered-result",
    )
    receipt = json.loads(backend.read_text(result_path) or "{}")
    receipt["result"]["draft"] = "tampered"
    tampered = json.dumps(receipt, ensure_ascii=False, sort_keys=True)
    backend.write_text(result_path, tampered)

    with pytest.raises(DocumentOpsRunOperationStoreError):
        store.claim(
            tenant_id="alpha",
            operation_id="agent-run:tampered-result",
            request_payload=_request_payload(),
        )

    assert backend.read_text(result_path) == tampered


def test_agent_run_operation_reconciles_lost_conditional_write_responses(
    tmp_path: Path,
) -> None:
    client = MemoryS3Client()
    backend = _backend(tmp_path, "s3", client)
    store = DocumentOpsRunOperationStore(backend=backend)
    client.fail_after_next_conditional_write(
        key_fragment="document_ops_agent_operations/"
    )

    claim = store.claim(
        tenant_id="alpha",
        operation_id="agent-run:lost-response",
        request_payload=_request_payload(),
    )

    assert claim.should_execute is True
    client.fail_after_next_conditional_write(
        key_fragment="document_ops_agent_operations/"
    )
    assert store.complete(claim, result=_result()) == _result()
    replay = store.claim(
        tenant_id="alpha",
        operation_id="agent-run:lost-response",
        request_payload=_request_payload(),
    )
    assert replay.should_execute is False
    assert replay.result == _result()
