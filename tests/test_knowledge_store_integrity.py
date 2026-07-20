from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.schemas import NormalizedProcurementOpportunity, ProcurementDecisionUpsert
from app.services.procurement_decision_service import ProcurementDecisionService
from app.services.report_workflow_service import ReportWorkflowService
from app.storage.knowledge_store import KnowledgeStore, KnowledgeStoreError
from app.storage.procurement_store import ProcurementDecisionStore
from app.storage.report_workflow_store import ReportWorkflowRecord, ReportWorkflowStore
from app.storage.state_backend import LocalStateBackend, S3StateBackend
from tests.conditional_state_support import (
    ConflictingLocalBackend,
    MemoryS3Client,
    s3_backend,
)


class _SlowLocalBackend(LocalStateBackend):
    def read_text(self, relative_path: str) -> str | None:
        value = super().read_text(relative_path)
        time.sleep(0.005)
        return value


def _s3_backend(
    client: MemoryS3Client | None = None,
) -> tuple[S3StateBackend, MemoryS3Client]:
    return s3_backend(client)


def _knowledge_prefix(
    project_id: str = "project-a",
    *,
    tenant_id: str = "tenant-a",
) -> str:
    return f"tenants/{tenant_id}/knowledge/{project_id}"


def _index_path(root: Path, project_id: str = "project-a") -> Path:
    return root / _knowledge_prefix(project_id) / "index.json"


def _s3_key(relative_path: str) -> tuple[str, str]:
    return "unit-bucket", f"decisiondoc-ai/state/{relative_path}"


def _s3_index_payload(
    client: MemoryS3Client,
    project_id: str = "project-a",
) -> dict[str, Any]:
    raw = client.objects[_s3_key(f"{_knowledge_prefix(project_id)}/index.json")]
    return json.loads(raw)


def _index_payload(root: Path, project_id: str = "project-a") -> Any:
    return json.loads(_index_path(root, project_id).read_text(encoding="utf-8"))


def _index_records(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return payload
    return payload["documents"]


def _persist_index(root: Path, payload: Any, project_id: str = "project-a") -> None:
    _index_path(root, project_id).write_text(
        json.dumps(payload),
        encoding="utf-8",
    )


def _object_path(
    root: Path,
    record: dict[str, Any],
    field: str,
) -> Path:
    return _index_path(root).parent / record[field]


def _local_store(tmp_path: Path, project_id: str = "project-a") -> KnowledgeStore:
    return KnowledgeStore(
        project_id,
        data_dir=str(tmp_path),
        tenant_id="tenant-a",
    )


def test_missing_reads_do_not_create_local_or_s3_state(tmp_path: Path) -> None:
    local = _local_store(tmp_path)
    backend, client = _s3_backend()
    remote = KnowledgeStore(
        "project-a",
        data_dir="/virtual/data",
        tenant_id="tenant-a",
        backend=backend,
    )

    assert local.list_documents() == []
    assert remote.list_documents() == []
    assert not (tmp_path / "tenants").exists()
    assert client.objects == {}


@pytest.mark.parametrize(
    "raw",
    [
        b"{not-json",
        b'{"unexpected":"object"}',
        b'[{"doc_id":"aaaaaaaaaaaa","doc_id":"bbbbbbbbbbbb"}]',
        b'["not-an-object"]',
    ],
)
def test_invalid_index_stops_reads_and_writes_without_replacement(
    tmp_path: Path,
    raw: bytes,
) -> None:
    path = _index_path(tmp_path)
    path.parent.mkdir(parents=True)
    path.write_bytes(raw)
    store = _local_store(tmp_path)

    with pytest.raises(KnowledgeStoreError):
        store.list_documents()
    with pytest.raises(KnowledgeStoreError):
        store.add_document("blocked.txt", "must not overwrite invalid state")

    assert path.read_bytes() == raw


def test_text_hash_mismatch_blocks_every_mutation(tmp_path: Path) -> None:
    store = _local_store(tmp_path)
    entry = store.add_document("trusted.txt", "alpha")
    record = _index_records(_index_payload(tmp_path))[0]
    text_path = _object_path(tmp_path, record, "_text_object")
    text_path.write_text("omega", encoding="utf-8")
    corrupted = text_path.read_bytes()

    with pytest.raises(KnowledgeStoreError, match="content binding mismatch"):
        store.list_documents()
    with pytest.raises(KnowledgeStoreError, match="content binding mismatch"):
        store.update_metadata(entry.doc_id, notes="blocked")
    with pytest.raises(KnowledgeStoreError, match="content binding mismatch"):
        store.delete_document(entry.doc_id)

    assert text_path.read_bytes() == corrupted


def test_style_corruption_and_partial_binding_fail_closed(tmp_path: Path) -> None:
    store = _local_store(tmp_path)
    entry = store.add_document(
        "styled.txt",
        "trusted",
        style_profile={"tone": "formal"},
    )
    payload = _index_payload(tmp_path)
    record = _index_records(payload)[0]
    style_path = _object_path(tmp_path, record, "_style_object")
    style_path.write_bytes(b'{"tone":"formal","tone":"forged"}')

    with pytest.raises(KnowledgeStoreError, match="Invalid knowledge style object"):
        store.get_document(entry.doc_id)

    records = _index_records(payload)
    style_path.write_text(json.dumps({"tone": "formal"}), encoding="utf-8")
    records[0].pop("style_sha256")
    partial = json.dumps(payload).encode()
    _index_path(tmp_path).write_bytes(partial)

    with pytest.raises(KnowledgeStoreError, match="Partial knowledge content binding"):
        store.list_documents()
    assert _index_path(tmp_path).read_bytes() == partial


def test_orphan_content_object_blocks_index_use(tmp_path: Path) -> None:
    store = _local_store(tmp_path)
    store.add_document("trusted.txt", "trusted")
    orphan = _index_path(tmp_path).parent / "aaaaaaaaaaaa.txt"
    orphan.write_text("unbound", encoding="utf-8")

    with pytest.raises(KnowledgeStoreError, match="Orphan knowledge content object"):
        store.list_documents()
    with pytest.raises(KnowledgeStoreError, match="Orphan knowledge content object"):
        store.add_document("blocked.txt", "blocked")

    assert orphan.read_text(encoding="utf-8") == "unbound"


def test_legacy_record_without_bindings_remains_readable(tmp_path: Path) -> None:
    directory = _index_path(tmp_path).parent
    directory.mkdir(parents=True)
    doc_id = "aaaaaaaaaaaa"
    text = "legacy knowledge"
    (directory / f"{doc_id}.txt").write_text(text, encoding="utf-8")
    _index_path(tmp_path).write_text(
        json.dumps(
            [
                {
                    "doc_id": doc_id,
                    "filename": "legacy.txt",
                    "text_len": len(text),
                    "has_style": False,
                    "created_at": 1_700_000_000.0,
                }
            ]
        ),
        encoding="utf-8",
    )
    store = _local_store(tmp_path)

    entry = store.get_document(doc_id)
    assert entry is not None
    assert entry.text == text
    assert store.update_metadata(doc_id, notes="migrated on mutation") is True

    payload = _index_payload(tmp_path)
    assert payload["schema_version"] == "knowledge_index.v2"
    persisted = _index_records(payload)[0]
    assert persisted["tenant_id"] == "tenant-a"
    assert persisted["project_id"] == "project-a"
    assert len(persisted["text_sha256"]) == 64
    assert persisted["text_size_bytes"] == len(text.encode("utf-8"))


def test_independent_local_and_s3_instances_preserve_concurrent_adds(
    tmp_path: Path,
) -> None:
    local_backend = _SlowLocalBackend(tmp_path)
    local_stores = [
        KnowledgeStore(
            "local-concurrency",
            data_dir=str(tmp_path),
            tenant_id="tenant-a",
            backend=local_backend,
        )
        for _ in range(20)
    ]
    shared_client = MemoryS3Client(read_delay=0.001)
    s3_stores = [
        KnowledgeStore(
            "s3-concurrency",
            data_dir="/virtual/data",
            tenant_id="tenant-a",
            backend=_s3_backend(shared_client)[0],
        )
        for _ in range(20)
    ]

    def add(store_and_index: tuple[KnowledgeStore, int]) -> str:
        store, index = store_and_index
        return store.add_document(f"doc-{index}.txt", f"content {index}").doc_id

    with ThreadPoolExecutor(max_workers=20) as executor:
        local_ids = set(executor.map(add, zip(local_stores, range(20))))
        s3_ids = set(executor.map(add, zip(s3_stores, range(20))))

    assert len(local_ids) == 20
    assert len(s3_ids) == 20
    assert len(local_stores[0].list_documents()) == 20
    assert len(s3_stores[0].list_documents()) == 20


@pytest.mark.parametrize("backend_kind", ["local", "s3"])
def test_delete_removes_index_content_and_style(
    tmp_path: Path,
    backend_kind: str,
) -> None:
    if backend_kind == "local":
        backend = LocalStateBackend(tmp_path)
        client = None
        data_dir = str(tmp_path)
    else:
        backend, client = _s3_backend()
        data_dir = "/virtual/data"
    store = KnowledgeStore(
        "delete-project",
        data_dir=data_dir,
        tenant_id="tenant-a",
        backend=backend,
    )
    entry = store.add_document(
        "delete.txt",
        "delete me",
        style_profile={"tone": "direct"},
    )
    if backend_kind == "local":
        payload = _index_payload(tmp_path, "delete-project")
    else:
        raw = backend.read_text(f"{_knowledge_prefix('delete-project')}/index.json")
        assert raw is not None
        payload = json.loads(raw)
    record = _index_records(payload)[0]
    content_paths = [
        f"{_knowledge_prefix('delete-project')}/{record['_text_object']}",
        f"{_knowledge_prefix('delete-project')}/{record['_style_object']}",
    ]

    assert store.delete_document(entry.doc_id) is True
    assert store.list_documents() == []
    relative_prefix = _knowledge_prefix("delete-project")
    assert all(backend.read_bytes(path) is None for path in content_paths)
    if client is not None:
        assert _s3_key(f"{relative_prefix}/index.json") in client.objects


def test_failed_index_write_rolls_back_new_content_objects() -> None:
    backend, client = _s3_backend()
    index_key = _s3_key(f"{_knowledge_prefix()}/index.json")[1]
    client.fail_before_next_write(key_fragment=index_key)
    store = KnowledgeStore(
        "project-a",
        data_dir="/virtual/data",
        tenant_id="tenant-a",
        backend=backend,
    )

    with pytest.raises(KnowledgeStoreError, match="could not be persisted"):
        store.add_document(
            "rollback.txt",
            "rollback",
            style_profile={"tone": "formal"},
        )

    assert client.objects == {}


def test_failed_style_index_write_restores_previous_object_state() -> None:
    backend, client = _s3_backend()
    store = KnowledgeStore(
        "project-a",
        data_dir="/virtual/data",
        tenant_id="tenant-a",
        backend=backend,
    )
    entry = store.add_document("style.txt", "style")
    index_relative = f"{_knowledge_prefix()}/index.json"
    original_index = client.objects[_s3_key(index_relative)]
    client.fail_before_next_write(
        key_fragment=_s3_key(index_relative)[1],
    )

    with pytest.raises(KnowledgeStoreError, match="could not be persisted"):
        store.update_style(entry.doc_id, {"tone": "formal"})

    assert client.objects[_s3_key(index_relative)] == original_index
    style_keys = [
        key
        for bucket, key in client.objects
        if bucket == "unit-bucket" and "/style-" in key
    ]
    assert style_keys == []
    assert store.get_document(entry.doc_id).style_profile == {}


def test_versioned_index_hides_internal_authority_metadata(
    tmp_path: Path,
) -> None:
    store = _local_store(tmp_path)
    entry = store.add_document(
        "authority.txt",
        "bound content",
        style_profile={"tone": "direct"},
    )

    payload = _index_payload(tmp_path)
    record = _index_records(payload)[0]
    public = store.list_documents()[0]

    assert set(payload) == {
        "schema_version",
        "documents",
        "_mutation_ids",
    }
    assert payload["schema_version"] == "knowledge_index.v2"
    assert payload["_mutation_ids"]
    assert record["_incarnation"]
    assert record["_text_object"].startswith(
        f"objects/{entry.doc_id}/{record['_incarnation']}/"
    )
    assert record["_style_object"].startswith(
        f"objects/{entry.doc_id}/{record['_incarnation']}/"
    )
    assert not {"_incarnation", "_text_object", "_style_object"} & set(public)


def test_lost_add_response_reconciles_after_successor_add() -> None:
    backend, client = _s3_backend()
    first = KnowledgeStore(
        "project-a",
        data_dir="/virtual/data",
        tenant_id="tenant-a",
        backend=backend,
    )
    successor = KnowledgeStore(
        "project-a",
        data_dir="/virtual/data",
        tenant_id="tenant-a",
        backend=_s3_backend(client)[0],
    )
    index_fragment = f"{_knowledge_prefix()}/index.json"
    client.fail_after_next_conditional_write(
        key_fragment=index_fragment,
        after_write=lambda: successor.add_document(
            "successor.txt",
            "successor content",
        ),
    )

    created = first.add_document("first.txt", "first content")
    documents = first.list_documents()

    assert {item["filename"] for item in documents} == {
        "first.txt",
        "successor.txt",
    }
    assert first.get_document(created.doc_id).text == "first content"
    assert len(_s3_index_payload(client)["_mutation_ids"]) == 2


def test_lost_style_response_reconciles_after_successor_metadata_update() -> None:
    backend, client = _s3_backend()
    first = KnowledgeStore(
        "project-a",
        data_dir="/virtual/data",
        tenant_id="tenant-a",
        backend=backend,
    )
    successor = KnowledgeStore(
        "project-a",
        data_dir="/virtual/data",
        tenant_id="tenant-a",
        backend=_s3_backend(client)[0],
    )
    entry = first.add_document("style.txt", "style content")
    client.fail_after_next_conditional_write(
        key_fragment=f"{_knowledge_prefix()}/index.json",
        after_write=lambda: successor.update_metadata(
            entry.doc_id,
            notes="successor metadata",
        ),
    )

    assert first.update_style(entry.doc_id, {"tone": "formal"}) is True
    observed = first.get_document(entry.doc_id)

    assert observed is not None
    assert observed.style_profile == {"tone": "formal"}
    assert observed.notes == "successor metadata"


def test_lost_delete_response_reconciles_after_successor_add() -> None:
    backend, client = _s3_backend()
    first = KnowledgeStore(
        "project-a",
        data_dir="/virtual/data",
        tenant_id="tenant-a",
        backend=backend,
    )
    successor = KnowledgeStore(
        "project-a",
        data_dir="/virtual/data",
        tenant_id="tenant-a",
        backend=_s3_backend(client)[0],
    )
    entry = first.add_document(
        "delete.txt",
        "delete content",
        style_profile={"tone": "direct"},
    )
    record = _index_records(_s3_index_payload(client))[0]
    retired_paths = [
        f"{_knowledge_prefix()}/{record['_text_object']}",
        f"{_knowledge_prefix()}/{record['_style_object']}",
    ]
    client.fail_after_next_conditional_write(
        key_fragment=f"{_knowledge_prefix()}/index.json",
        after_write=lambda: successor.add_document(
            "successor.txt",
            "successor content",
        ),
    )

    assert first.delete_document(entry.doc_id) is True
    assert [item["filename"] for item in first.list_documents()] == ["successor.txt"]
    assert all(backend.read_bytes(path) is None for path in retired_paths)


def test_cas_retry_preserves_successor_metadata_during_style_update() -> None:
    backend, client = _s3_backend()
    first = KnowledgeStore(
        "project-a",
        data_dir="/virtual/data",
        tenant_id="tenant-a",
        backend=backend,
    )
    successor = KnowledgeStore(
        "project-a",
        data_dir="/virtual/data",
        tenant_id="tenant-a",
        backend=_s3_backend(client)[0],
    )
    entry = first.add_document("shared.txt", "shared content")
    client.before_next_conditional_write(
        key_fragment=f"{_knowledge_prefix()}/index.json",
        callback=lambda: successor.update_metadata(
            entry.doc_id,
            notes="concurrent note",
        ),
    )

    assert first.update_style(entry.doc_id, {"tone": "concise"}) is True
    observed = first.get_document(entry.doc_id)

    assert observed is not None
    assert observed.notes == "concurrent note"
    assert observed.style_profile == {"tone": "concise"}


def test_replacement_identity_stops_stale_metadata_update(monkeypatch) -> None:
    backend, client = _s3_backend()
    first = KnowledgeStore(
        "project-a",
        data_dir="/virtual/data",
        tenant_id="tenant-a",
        backend=backend,
    )
    successor = KnowledgeStore(
        "project-a",
        data_dir="/virtual/data",
        tenant_id="tenant-a",
        backend=_s3_backend(client)[0],
    )
    original = first.add_document("original.txt", "original content")

    def replace_document() -> None:
        assert successor.delete_document(original.doc_id) is True
        monkeypatch.setattr(
            successor,
            "_new_doc_id",
            lambda _known_ids: original.doc_id,
        )
        successor.add_document("replacement.txt", "replacement content")

    client.before_next_conditional_write(
        key_fragment=f"{_knowledge_prefix()}/index.json",
        callback=replace_document,
    )

    with pytest.raises(KnowledgeStoreError, match="identity changed"):
        first.update_metadata(original.doc_id, notes="stale mutation")

    replacement = first.get_document(original.doc_id)
    assert replacement is not None
    assert replacement.filename == "replacement.txt"
    assert replacement.text == "replacement content"
    assert replacement.notes == ""


def test_knowledge_mutation_stops_after_bounded_conflicts(
    tmp_path: Path,
) -> None:
    backend = ConflictingLocalBackend(
        tmp_path,
        conflict_suffix="/index.json",
    )
    store = KnowledgeStore(
        "conflict-project",
        data_dir=str(tmp_path),
        tenant_id="tenant-a",
        backend=backend,
    )

    with pytest.raises(KnowledgeStoreError, match="changed too many times"):
        store.add_document("blocked.txt", "blocked content")

    assert backend.attempts == 32
    assert backend.list_prefix(_knowledge_prefix("conflict-project")) == []


def test_mutation_receipts_are_private_bounded_and_fail_closed(
    tmp_path: Path,
) -> None:
    store = _local_store(tmp_path)
    entry = store.add_document("history.txt", "history content")
    for index in range(70):
        assert store.update_metadata(
            entry.doc_id,
            notes=f"mutation {index}",
        )

    payload = _index_payload(tmp_path)
    assert len(payload["_mutation_ids"]) == 64
    assert "_mutation_ids" not in store.list_documents()[0]

    payload["_mutation_ids"][0] = payload["_mutation_ids"][1]
    _persist_index(tmp_path, payload)
    with pytest.raises(KnowledgeStoreError, match="mutation history"):
        store.list_documents()
    with pytest.raises(KnowledgeStoreError, match="mutation history"):
        store.update_metadata(entry.doc_id, notes="blocked")


def test_invalid_internal_object_binding_fails_closed(
    tmp_path: Path,
) -> None:
    store = _local_store(tmp_path)
    entry = store.add_document("trusted.txt", "trusted content")
    payload = _index_payload(tmp_path)
    payload["documents"][0]["_text_object"] = "../forged.txt"
    _persist_index(tmp_path, payload)

    with pytest.raises(KnowledgeStoreError, match="text object binding"):
        store.get_document(entry.doc_id)
    with pytest.raises(KnowledgeStoreError, match="text object binding"):
        store.delete_document(entry.doc_id)


def test_unreferenced_versioned_object_is_inert(
    tmp_path: Path,
) -> None:
    store = _local_store(tmp_path)
    entry = store.add_document(
        "trusted.txt",
        "trusted content",
        style_profile={"tone": "current"},
    )
    inert = (
        _index_path(tmp_path).parent
        / "objects"
        / "aaaaaaaaaaaa"
        / ("b" * 32)
        / "content.txt"
    )
    inert.parent.mkdir(parents=True)
    inert.write_text("never indexed", encoding="utf-8")

    observed = store.get_document(entry.doc_id)
    assert observed is not None
    assert observed.text == "trusted content"
    assert observed.style_profile == {"tone": "current"}
    assert "never indexed" not in store.build_context()

    unexpected_legacy = _index_path(tmp_path).parent / f"{entry.doc_id}_style.json"
    unexpected_legacy.write_text('{"tone":"stale"}', encoding="utf-8")
    with pytest.raises(KnowledgeStoreError, match="Orphan knowledge content object"):
        store.list_documents()


def _create_client(
    tmp_path: Path, monkeypatch, *, raise_server_exceptions: bool = True
):
    monkeypatch.setenv("DECISIONDOC_PROVIDER", "mock")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DECISIONDOC_ENV", "dev")
    monkeypatch.setenv("DECISIONDOC_MAINTENANCE", "0")
    monkeypatch.delenv("DECISIONDOC_API_KEY", raising=False)
    monkeypatch.delenv("DECISIONDOC_API_KEYS", raising=False)
    monkeypatch.setenv("DECISIONDOC_PROVIDER_GENERATION", "")
    monkeypatch.setenv("DECISIONDOC_PROVIDER_ATTACHMENT", "")
    monkeypatch.setenv("DECISIONDOC_PROVIDER_VISUAL", "")
    from app.main import create_app

    return TestClient(
        create_app(),
        raise_server_exceptions=raise_server_exceptions,
    )


def test_knowledge_api_uses_selected_s3_backend(tmp_path: Path, monkeypatch) -> None:
    client = _create_client(tmp_path, monkeypatch)
    backend, s3_client = _s3_backend()
    client.app.state.state_backend = backend

    uploaded = client.post(
        "/knowledge/project-a/documents",
        files={"file": ("reference.txt", b"trusted context", "text/plain")},
    )
    assert uploaded.status_code == 200
    doc_id = uploaded.json()["doc_id"]
    api_prefix = _knowledge_prefix(tenant_id="system")
    assert _s3_key(f"{api_prefix}/index.json") in s3_client.objects
    assert not (tmp_path / "tenants" / "system" / "knowledge").exists()

    listed = client.get("/knowledge/project-a/documents")
    detail = client.get(f"/knowledge/project-a/documents/{doc_id}")
    deleted = client.delete(f"/knowledge/project-a/documents/{doc_id}")
    assert listed.status_code == 200
    assert listed.json()["count"] == 1
    assert detail.status_code == 200
    assert detail.json()["text"] == "trusted context"
    assert deleted.status_code == 200


def test_corrupt_s3_knowledge_index_returns_internal_error_without_replacement(
    tmp_path: Path,
    monkeypatch,
) -> None:
    client = _create_client(tmp_path, monkeypatch, raise_server_exceptions=False)
    backend, s3_client = _s3_backend()
    client.app.state.state_backend = backend
    key = _s3_key(f"{_knowledge_prefix(tenant_id='system')}/index.json")
    s3_client.objects[key] = b"{not-json"

    response = client.get("/knowledge/project-a/documents")
    client.app.state.service.state_backend = backend
    generation = client.post(
        "/generate",
        json={
            "title": "Corrupt knowledge must block generation",
            "goal": "Do not silently omit untrusted context",
            "project_id": "project-a",
        },
    )

    assert response.status_code == 500
    assert response.json()["code"] == "INTERNAL_ERROR"
    assert generation.status_code == 500
    assert generation.json()["code"] == "INTERNAL_ERROR"
    assert s3_client.objects[key] == b"{not-json"


def test_generation_context_reads_knowledge_from_selected_backend(
    tmp_path: Path,
    monkeypatch,
) -> None:
    client = _create_client(tmp_path, monkeypatch)
    backend, s3_client = _s3_backend()
    KnowledgeStore(
        "generation-project",
        data_dir="/virtual/data",
        tenant_id="system",
        backend=backend,
    ).add_document(
        "selected-backend.txt",
        "selected backend generation context",
        applicable_bundles=["proposal_kr"],
    )
    client.app.state.service.state_backend = backend
    payload = {
        "project_id": "generation-project",
        "title": "Selected backend proposal",
        "goal": "Reuse backend-bound knowledge",
    }

    client.app.state.service._inject_project_contexts(
        payload,
        bundle_type="proposal_kr",
        tenant_id="system",
        request_id="backend-context-test",
    )

    assert "selected backend generation context" in payload["_knowledge_context"]
    assert (
        payload["_knowledge_ranked_documents"][0]["filename"] == "selected-backend.txt"
    )

    index_key = _s3_key(
        f"{_knowledge_prefix('generation-project', tenant_id='system')}/index.json"
    )
    s3_client.objects[index_key] = b"{not-json"
    with pytest.raises(KnowledgeStoreError, match="Invalid knowledge index"):
        client.app.state.service._inject_project_contexts(
            dict(payload),
            bundle_type="proposal_kr",
            tenant_id="system",
            request_id="corrupt-backend-context-test",
        )


def test_procurement_evaluator_reads_capability_from_selected_backend(
    tmp_path: Path,
) -> None:
    backend, _s3_client = _s3_backend()
    project_id = "procurement-project"
    KnowledgeStore(
        project_id,
        data_dir="/virtual/data",
        tenant_id="tenant-a",
        backend=backend,
    ).add_document(
        "capability.txt",
        "공공 AI 플랫폼 구축, 데이터 분석, 클라우드 전환 수행 경험",
    )
    procurement_store = ProcurementDecisionStore(base_dir=str(tmp_path))
    procurement_store.upsert(
        ProcurementDecisionUpsert(
            project_id=project_id,
            tenant_id="tenant-a",
            opportunity=NormalizedProcurementOpportunity(
                source_kind="g2b",
                source_id="2026-backend-test",
                title="공공 AI 플랫폼 구축",
                issuer="테스트기관",
                raw_text_preview="AI 플랫폼과 데이터 분석 수행실적 필요",
            ),
        )
    )
    service = ProcurementDecisionService(
        procurement_store=procurement_store,
        data_dir="/virtual/data",
        state_backend=backend,
    )

    evaluated = service.evaluate_project(
        project_id=project_id,
        tenant_id="tenant-a",
    )

    assert evaluated.capability_profile is not None
    assert evaluated.capability_profile.document_ids
    assert evaluated.capability_profile.title == "capability.txt"


def test_report_promotion_writes_and_reuses_selected_backend_knowledge(
    tmp_path: Path,
) -> None:
    backend, s3_client = _s3_backend()
    service = ReportWorkflowService(
        store=ReportWorkflowStore(base_dir=str(tmp_path)),
        provider_factory=lambda: object(),
        data_dir="/virtual/data",
        state_backend=backend,
    )
    record = ReportWorkflowRecord(
        report_workflow_id="rw_backend_test",
        tenant_id="tenant-a",
        title="승인 보고서",
        goal="선택 backend 승격 검증",
        client="테스트기관",
        report_type="proposal_deck",
        audience="executive",
        owner="owner",
        pm_reviewer="pm",
        executive_approver="ceo",
        status="final_approved",
        source_bundle_id="",
        source_request_id="",
        slide_count=1,
        attachments_context="",
        source_refs=[],
        learning_opt_in=True,
        created_at="2026-07-17T00:00:00Z",
        updated_at="2026-07-17T00:00:00Z",
        current_slide_version=1,
    )
    docs = [
        {
            "doc_type": "report_workflow_slides",
            "markdown": "# 승인된 장표\n\n근거와 결론",
        }
    ]

    created = service._promote_docs_to_knowledge(
        record,
        tenant_id="tenant-a",
        project_id="report-project",
        docs=docs,
        tags=["approved"],
        quality_tier="gold",
        success_state="approved",
        source_organization="테스트기관",
        reference_year=2026,
        notes="selected backend promotion",
    )
    repeated = service._promote_docs_to_knowledge(
        record,
        tenant_id="tenant-a",
        project_id="report-project",
        docs=docs,
        tags=["approved"],
        quality_tier="gold",
        success_state="approved",
        source_organization="테스트기관",
        reference_year=2026,
        notes="selected backend promotion",
    )

    prefix = _knowledge_prefix("report-project")
    assert _s3_key(f"{prefix}/index.json") in s3_client.objects
    assert created[0]["reused"] is False
    assert repeated[0]["doc_id"] == created[0]["doc_id"]
    assert repeated[0]["reused"] is True
