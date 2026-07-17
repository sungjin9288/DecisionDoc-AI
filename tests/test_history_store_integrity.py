from __future__ import annotations

import ast
import hashlib
import json
import threading
import time
from contextlib import nullcontext
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from typing import Callable

import pytest
from fastapi.testclient import TestClient

from app.storage.history_store import (
    MAX_HISTORY_PER_USER,
    HistoryEntry,
    HistoryStore,
    HistoryStoreError,
)
from app.storage.state_backend import (
    LocalStateBackend,
    S3StateBackend,
    StateBackendError,
)


class _SlowLocalBackend(LocalStateBackend):
    """Expose lost updates when independent stores do not share a lock."""

    def read_text(self, relative_path: str) -> str | None:
        raw = super().read_text(relative_path)
        time.sleep(0.005)
        return raw


class _ConflictingLocalBackend(LocalStateBackend):
    def __init__(self, root: Path) -> None:
        super().__init__(root)
        self.attempts = 0

    def write_text_if_absent(
        self,
        relative_path: str,
        text: str,
        *,
        content_type: str = "application/json; charset=utf-8",
    ) -> bool:
        _ = relative_path, text, content_type
        self.attempts += 1
        return False


class _FailingConditionalBackend(LocalStateBackend):
    def write_text_if_absent(
        self,
        relative_path: str,
        text: str,
        *,
        content_type: str = "application/json; charset=utf-8",
    ) -> bool:
        _ = relative_path, text, content_type
        raise StateBackendError("simulated conditional write failure")


class _Body:
    def __init__(self, data: bytes) -> None:
        self._data = data

    def read(self) -> bytes:
        return self._data


class _MemoryS3Client:
    def __init__(self, *, read_delay: float = 0.0) -> None:
        self.objects: dict[tuple[str, str], bytes] = {}
        self.read_delay = read_delay
        self._lock = threading.Lock()
        self._fail_after_conditional_write = False
        self._after_failed_conditional_write: Callable[[], None] | None = None

    @staticmethod
    def _etag(data: bytes) -> str:
        return f'"{hashlib.sha256(data).hexdigest()}"'

    @staticmethod
    def _error(code: str) -> Exception:
        error = Exception(code)
        error.response = {"Error": {"Code": code}}
        return error

    def fail_after_next_conditional_write(
        self,
        *,
        after_write: Callable[[], None] | None = None,
    ) -> None:
        self._fail_after_conditional_write = True
        self._after_failed_conditional_write = after_write

    def put_object(
        self,
        *,
        Bucket: str,
        Key: str,
        Body: bytes,
        ContentType: str,
        IfNoneMatch: str | None = None,
        IfMatch: str | None = None,
    ) -> None:
        _ = ContentType
        with self._lock:
            current = self.objects.get((Bucket, Key))
            if IfNoneMatch == "*" and current is not None:
                raise self._error("PreconditionFailed")
            if IfMatch is not None and (
                current is None or self._etag(current) != IfMatch
            ):
                raise self._error("PreconditionFailed")
            self.objects[(Bucket, Key)] = Body
            fail_after_write = (
                self._fail_after_conditional_write
                and (IfNoneMatch is not None or IfMatch is not None)
            )
            if fail_after_write:
                self._fail_after_conditional_write = False
                after_failed_write = self._after_failed_conditional_write
                self._after_failed_conditional_write = None
            else:
                after_failed_write = None
        if fail_after_write:
            if after_failed_write is not None:
                after_failed_write()
            raise self._error("InternalError")

    def get_object(self, *, Bucket: str, Key: str) -> dict:
        with self._lock:
            data = self.objects.get((Bucket, Key))
        if data is None:
            raise self._error("NoSuchKey")
        time.sleep(self.read_delay)
        return {"Body": _Body(data), "ETag": self._etag(data)}


def _s3_backend(
    *,
    read_delay: float = 0.0,
    client: _MemoryS3Client | None = None,
) -> tuple[S3StateBackend, _MemoryS3Client]:
    client = client or _MemoryS3Client(read_delay=read_delay)
    backend = S3StateBackend(
        bucket="unit-bucket",
        prefix="decisiondoc-ai/state/",
        s3_client=client,
    )
    return backend, client


def _entry(
    entry_id: str,
    *,
    tenant_id: str = "alpha",
    user_id: str = "user-1",
) -> HistoryEntry:
    return HistoryEntry(
        entry_id=entry_id,
        tenant_id=tenant_id,
        user_id=user_id,
        bundle_id="tech_decision",
        bundle_name="기술 결정",
        title=f"History {entry_id}",
        request_id=f"request-{entry_id}",
        created_at="2026-07-16T00:00:00+00:00",
        bundle_type="tech_decision",
        project_id="project-1",
        score=0.8,
        tags=["architecture"],
        applied_references=[{"reference_id": "ref-1"}],
        docs=[{"doc_type": "adr", "content": "Decision"}],
        visual_assets=[{"asset_id": "asset-1", "doc_type": "adr"}],
    )


def _record(
    entry_id: str,
    *,
    tenant_id: str | None = "alpha",
    user_id: str = "user-1",
) -> dict:
    record = {
        "entry_id": entry_id,
        "user_id": user_id,
        "bundle_id": "tech_decision",
        "bundle_name": "기술 결정",
        "title": f"History {entry_id}",
        "request_id": f"request-{entry_id}",
        "created_at": "2026-07-16T00:00:00+00:00",
        "bundle_type": "tech_decision",
        "project_id": "project-1",
        "score": 0.8,
        "tags": ["architecture"],
        "applied_references": [{"reference_id": "ref-1"}],
        "docs": [{"doc_type": "adr", "content": "Decision"}],
        "visual_assets": [],
        "knowledge_promoted": False,
        "knowledge_project_id": "",
        "knowledge_promoted_at": "",
        "knowledge_document_count": 0,
        "knowledge_quality_tier": "",
        "knowledge_success_state": "",
        "knowledge_documents": [],
    }
    if tenant_id is not None:
        record["tenant_id"] = tenant_id
    return record


@pytest.mark.parametrize(
    "tenant_id",
    [" tenant", "tenant ", ".", "..", "tenant/a", "tenant\\a", "tenant\na"],
)
def test_history_store_rejects_unsafe_tenant_before_state_access(
    tmp_path: Path,
    tenant_id: str,
) -> None:
    with pytest.raises(ValueError, match="Invalid tenant_id"):
        HistoryStore(tenant_id, base_dir=tmp_path)

    assert not (tmp_path / "tenants").exists()


def test_history_store_uses_data_dir_without_creating_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    store = HistoryStore("alpha")

    assert store.get_for_user("user-1") == []
    assert store._base == tmp_path
    assert not store._path.exists()


def test_empty_jsonl_is_a_valid_empty_history_state(tmp_path: Path) -> None:
    path = tmp_path / "tenants/alpha/history.jsonl"
    path.parent.mkdir(parents=True)
    path.write_text("", encoding="utf-8")

    assert HistoryStore("alpha", base_dir=tmp_path).get_for_user("user-1") == []
    assert path.read_bytes() == b""


@pytest.mark.parametrize(
    ("raw", "error"),
    [
        ("{not-json\n", "Invalid history state at line 1"),
        ("[]\n", "Invalid history state at line 1"),
        (
            '{"entry_id":"first","entry_id":"second"}\n',
            "Invalid history state at line 1",
        ),
        (
            json.dumps({**_record("invalid"), "tags": [1]}) + "\n",
            "Invalid history state at line 1",
        ),
        (
            json.dumps({**_record("invalid"), "docs": ["bad"]}) + "\n",
            "Invalid history state at line 1",
        ),
        (
            json.dumps({**_record("invalid"), "score": float("nan")}) + "\n",
            "Invalid history state at line 1",
        ),
        (
            json.dumps({**_record("invalid"), "starred": "yes"}) + "\n",
            "Invalid history state at line 1",
        ),
        (
            json.dumps({**_record("invalid"), "created_at": "later"}) + "\n",
            "Invalid history state at line 1",
        ),
        (
            json.dumps(_record("duplicate"))
            + "\n"
            + json.dumps(_record("duplicate"))
            + "\n",
            "Duplicate history identity",
        ),
    ],
)
def test_untrusted_history_state_stops_reads_and_writes_without_replacement(
    tmp_path: Path,
    raw: str,
    error: str,
) -> None:
    path = tmp_path / "tenants/alpha/history.jsonl"
    path.parent.mkdir(parents=True)
    path.write_text(raw, encoding="utf-8")
    original_bytes = path.read_bytes()
    store = HistoryStore("alpha", base_dir=tmp_path)

    operations = (
        lambda: store.get_for_user("user-1"),
        lambda: store.get_entry("entry-1", "user-1"),
        lambda: store.get_favorites("user-1"),
        lambda: store.search("user-1", "history"),
        lambda: store.add(_entry("new-entry")),
        lambda: store.toggle_favorite("entry-1", "user-1"),
        lambda: store.delete("entry-1", "user-1"),
        lambda: store.update_visual_assets("entry-1", "user-1", []),
        lambda: store.mark_promoted(
            "request-entry-1",
            project_id="project-1",
            document_count=1,
            quality_tier="reviewed",
            success_state="promoted",
            promoted_at="2026-07-16T01:00:00+00:00",
        ),
    )
    for operation in operations:
        with pytest.raises(HistoryStoreError, match=error):
            operation()

    assert path.read_bytes() == original_bytes


def test_foreign_history_remains_hidden_and_preserved(tmp_path: Path) -> None:
    path = tmp_path / "tenants/alpha/history.jsonl"
    path.parent.mkdir(parents=True)
    foreign = {"tenant_id": "beta", "opaque": {"keep": True}}
    path.write_text(json.dumps(foreign) + "\n", encoding="utf-8")
    store = HistoryStore("alpha", base_dir=tmp_path)

    store.add(_entry("owned"))

    assert [item["entry_id"] for item in store.get_for_user("user-1")] == ["owned"]
    persisted = [json.loads(line) for line in path.read_text().splitlines()]
    assert persisted[0] == foreign


def test_legacy_history_without_tenant_remains_path_owned(tmp_path: Path) -> None:
    path = tmp_path / "tenants/alpha/history.jsonl"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(_record("legacy", tenant_id=None)) + "\n")
    store = HistoryStore("alpha", base_dir=tmp_path)

    assert store.toggle_favorite("legacy", "user-1") is True
    legacy = store.get_entry("legacy", "user-1")

    assert legacy is not None
    assert legacy.get("tenant_id") is None
    assert legacy["starred"] is True


@pytest.mark.parametrize(
    ("field", "value", "error"),
    [
        ("entry_id", "", "Invalid history identity"),
        ("tags", [1], "Invalid history tags"),
        ("docs", ["bad"], "Invalid history document list"),
        ("score", float("inf"), "Invalid history score"),
        ("knowledge_document_count", -1, "Invalid history document count"),
        ("knowledge_document_count", True, "Invalid history document count"),
    ],
)
def test_invalid_caller_history_is_rejected_before_write(
    tmp_path: Path,
    field: str,
    value: object,
    error: str,
) -> None:
    entry = replace(_entry("invalid"), **{field: value})
    store = HistoryStore("alpha", base_dir=tmp_path)

    with pytest.raises(ValueError, match=error):
        store.add(entry)

    assert not store._path.exists()


def test_history_store_rejects_reused_identity(tmp_path: Path) -> None:
    store = HistoryStore("alpha", base_dir=tmp_path)
    store.add(_entry("same-id"))
    original_bytes = store._path.read_bytes()

    with pytest.raises(HistoryStoreError, match="Duplicate history identity"):
        store.add(_entry("same-id", user_id="user-2"))

    assert store._path.read_bytes() == original_bytes


def test_missing_and_invalid_history_mutations_do_not_rewrite_state(
    tmp_path: Path,
) -> None:
    store = HistoryStore("alpha", base_dir=tmp_path)
    store.add(_entry("entry-1"))
    original_bytes = store._path.read_bytes()

    store.delete("missing", "user-1")
    assert store.toggle_favorite("missing", "user-1") is False
    assert store.update_visual_assets("missing", "user-1", []) is False
    assert (
        store.mark_promoted(
            "missing-request",
            project_id="project-1",
            document_count=1,
            quality_tier="reviewed",
            success_state="promoted",
            promoted_at="2026-07-16T01:00:00+00:00",
        )
        == 0
    )
    with pytest.raises(ValueError, match="Invalid history identity"):
        store.mark_promoted(
            "request-entry-1",
            project_id="project-1",
            document_count=1,
            quality_tier="reviewed",
            success_state="promoted",
            promoted_at="2026-07-16T01:00:00+00:00",
            user_id="",
        )

    assert store._path.read_bytes() == original_bytes


def test_independent_local_history_stores_preserve_concurrent_adds(
    tmp_path: Path,
) -> None:
    stores = [
        HistoryStore(
            "alpha",
            base_dir=tmp_path,
            backend=_SlowLocalBackend(tmp_path),
        )
        for _ in range(20)
    ]
    for store in stores:
        store._lock = nullcontext()

    def add(index: int) -> None:
        stores[index].add(_entry(f"entry-{index}"))

    with ThreadPoolExecutor(max_workers=20) as executor:
        list(executor.map(add, range(20)))

    entries = HistoryStore("alpha", base_dir=tmp_path).get_for_user("user-1")
    assert {entry["entry_id"] for entry in entries} == {
        f"entry-{index}" for index in range(20)
    }


def test_independent_local_history_stores_preserve_favorite_toggles(
    tmp_path: Path,
) -> None:
    creator = HistoryStore("alpha", base_dir=tmp_path)
    creator.add(_entry("shared"))
    stores = [
        HistoryStore(
            "alpha",
            base_dir=tmp_path,
            backend=_SlowLocalBackend(tmp_path),
        )
        for _ in range(20)
    ]
    for store in stores:
        store._lock = nullcontext()

    with ThreadPoolExecutor(max_workers=20) as executor:
        list(
            executor.map(
                lambda store: store.toggle_favorite("shared", "user-1"),
                stores,
            )
        )

    assert creator.get_entry("shared", "user-1")["starred"] is False


def test_history_round_trip_through_fake_s3() -> None:
    backend, client = _s3_backend()
    store = HistoryStore("alpha", base_dir="/virtual/data", backend=backend)
    store.add(_entry("entry-1"))
    key = ("unit-bucket", "decisiondoc-ai/state/tenants/alpha/history.jsonl")

    assert key in client.objects
    reloaded = HistoryStore(
        "alpha",
        base_dir="/virtual/data",
        backend=backend,
    ).get_entry("entry-1", "user-1")
    assert reloaded is not None
    assert reloaded["docs"] == [{"doc_type": "adr", "content": "Decision"}]
    assert reloaded["visual_assets"][0]["asset_id"] == "asset-1"


def test_untrusted_fake_s3_history_state_is_preserved() -> None:
    backend, client = _s3_backend()
    key = ("unit-bucket", "decisiondoc-ai/state/tenants/alpha/history.jsonl")
    client.objects[key] = b"{not-json\n"
    store = HistoryStore("alpha", base_dir="/virtual/data", backend=backend)

    with pytest.raises(HistoryStoreError, match="Invalid history state at line 1"):
        store.add(_entry("new-entry"))

    assert client.objects[key] == b"{not-json\n"


def test_independent_fake_s3_history_stores_preserve_concurrent_mutations() -> None:
    client = _MemoryS3Client(read_delay=0.005)
    stores = [
        HistoryStore(
            "alpha",
            base_dir=f"/virtual/worker-{index}",
            backend=_s3_backend(client=client)[0],
        )
        for index in range(20)
    ]
    for store in stores:
        store._lock = nullcontext()

    def add(index: int) -> None:
        stores[index].add(_entry(f"entry-{index}"))

    with ThreadPoolExecutor(max_workers=20) as executor:
        list(executor.map(add, range(20)))
    with ThreadPoolExecutor(max_workers=20) as executor:
        list(
            executor.map(
                lambda store: store.toggle_favorite("entry-0", "user-1"),
                stores,
            )
        )

    reloaded = HistoryStore(
        "alpha",
        base_dir="/virtual/reload",
        backend=_s3_backend(client=client)[0],
    )
    entries = reloaded.get_for_user("user-1")
    assert {entry["entry_id"] for entry in entries} == {
        f"entry-{index}" for index in range(20)
    }
    assert reloaded.get_entry("entry-0", "user-1")["starred"] is False


def test_history_mutation_reconciles_commit_then_successor_add() -> None:
    client = _MemoryS3Client()
    bootstrap = HistoryStore(
        "alpha",
        base_dir="/virtual/bootstrap",
        backend=_s3_backend(client=client)[0],
    )
    bootstrap.add(_entry("shared"))
    primary = HistoryStore(
        "alpha",
        base_dir="/virtual/primary",
        backend=_s3_backend(client=client)[0],
    )
    successor = HistoryStore(
        "alpha",
        base_dir="/virtual/successor",
        backend=_s3_backend(client=client)[0],
    )
    primary._lock = nullcontext()
    successor._lock = nullcontext()
    client.fail_after_next_conditional_write(
        after_write=lambda: successor.add(_entry("successor"))
    )

    assert primary.toggle_favorite("shared", "user-1") is True

    assert bootstrap.get_entry("shared", "user-1")["starred"] is True
    assert bootstrap.get_entry("successor", "user-1") is not None


def test_history_mutation_does_not_apply_to_recreated_identity() -> None:
    client = _MemoryS3Client()
    bootstrap = HistoryStore(
        "alpha",
        base_dir="/virtual/bootstrap",
        backend=_s3_backend(client=client)[0],
    )
    bootstrap.add(_entry("shared"))
    primary = HistoryStore(
        "alpha",
        base_dir="/virtual/primary",
        backend=_s3_backend(client=client)[0],
    )
    successor = HistoryStore(
        "alpha",
        base_dir="/virtual/successor",
        backend=_s3_backend(client=client)[0],
    )
    primary._lock = nullcontext()
    successor._lock = nullcontext()

    def recreate() -> None:
        successor.delete("shared", "user-1")
        successor.add(replace(_entry("shared"), title="Replacement"))

    client.fail_after_next_conditional_write(after_write=recreate)

    with pytest.raises(
        HistoryStoreError,
        match="Failed to persist history state",
    ):
        primary.toggle_favorite("shared", "user-1")

    replacement = bootstrap.get_entry("shared", "user-1")
    assert replacement is not None
    assert replacement["title"] == "Replacement"
    assert replacement.get("starred", False) is False


def test_history_add_reconciles_after_retention_removes_original_entry() -> None:
    client = _MemoryS3Client()
    primary = HistoryStore(
        "alpha",
        base_dir="/virtual/primary",
        backend=_s3_backend(client=client)[0],
    )
    successor = HistoryStore(
        "alpha",
        base_dir="/virtual/successor",
        backend=_s3_backend(client=client)[0],
    )
    primary._lock = nullcontext()
    successor._lock = nullcontext()

    def add_successors() -> None:
        for index in range(MAX_HISTORY_PER_USER):
            successor.add(_entry(f"successor-{index}"))

    client.fail_after_next_conditional_write(after_write=add_successors)

    primary.add(_entry("original"))

    entries = primary.get_for_user("user-1", limit=100)
    assert len(entries) == MAX_HISTORY_PER_USER
    assert all(entry["entry_id"] != "original" for entry in entries)


def test_history_delete_reconciliation_preserves_recreated_identity() -> None:
    client = _MemoryS3Client()
    bootstrap = HistoryStore(
        "alpha",
        base_dir="/virtual/bootstrap",
        backend=_s3_backend(client=client)[0],
    )
    bootstrap.add(_entry("shared"))
    primary = HistoryStore(
        "alpha",
        base_dir="/virtual/primary",
        backend=_s3_backend(client=client)[0],
    )
    successor = HistoryStore(
        "alpha",
        base_dir="/virtual/successor",
        backend=_s3_backend(client=client)[0],
    )
    primary._lock = nullcontext()
    successor._lock = nullcontext()
    replacement = replace(
        _entry("shared"),
        title="Replacement",
    )
    client.fail_after_next_conditional_write(
        after_write=lambda: successor.add(replacement)
    )

    primary.delete("shared", "user-1")

    recreated = bootstrap.get_entry("shared", "user-1")
    assert recreated is not None
    assert recreated["title"] == "Replacement"


def test_history_disjoint_visual_asset_and_favorite_updates_are_preserved() -> None:
    client = _MemoryS3Client(read_delay=0.005)
    bootstrap = HistoryStore(
        "alpha",
        base_dir="/virtual/bootstrap",
        backend=_s3_backend(client=client)[0],
    )
    bootstrap.add(_entry("shared"))
    visual_store = HistoryStore(
        "alpha",
        base_dir="/virtual/visual",
        backend=_s3_backend(client=client)[0],
    )
    favorite_store = HistoryStore(
        "alpha",
        base_dir="/virtual/favorite",
        backend=_s3_backend(client=client)[0],
    )
    visual_store._lock = nullcontext()
    favorite_store._lock = nullcontext()

    with ThreadPoolExecutor(max_workers=2) as executor:
        visual_result, favorite_result = executor.map(
            lambda action: action(),
            (
                lambda: visual_store.update_visual_assets(
                    "shared",
                    "user-1",
                    [{"asset_id": "asset-2", "doc_type": "adr"}],
                ),
                lambda: favorite_store.toggle_favorite("shared", "user-1"),
            ),
        )

    reloaded = bootstrap.get_entry("shared", "user-1")
    assert visual_result is True
    assert favorite_result is True
    assert reloaded is not None
    assert reloaded["starred"] is True
    assert reloaded["visual_assets"][0]["asset_id"] == "asset-2"


def test_history_disjoint_promotion_and_visual_asset_updates_are_preserved() -> None:
    client = _MemoryS3Client(read_delay=0.005)
    bootstrap = HistoryStore(
        "alpha",
        base_dir="/virtual/bootstrap",
        backend=_s3_backend(client=client)[0],
    )
    bootstrap.add(_entry("shared"))
    promotion_store = HistoryStore(
        "alpha",
        base_dir="/virtual/promotion",
        backend=_s3_backend(client=client)[0],
    )
    visual_store = HistoryStore(
        "alpha",
        base_dir="/virtual/visual",
        backend=_s3_backend(client=client)[0],
    )
    promotion_store._lock = nullcontext()
    visual_store._lock = nullcontext()

    with ThreadPoolExecutor(max_workers=2) as executor:
        promoted_count, visual_result = executor.map(
            lambda action: action(),
            (
                lambda: promotion_store.mark_promoted(
                    "request-shared",
                    project_id="project-2",
                    document_count=1,
                    quality_tier="reviewed",
                    success_state="promoted",
                    promoted_at="2026-07-17T01:00:00+00:00",
                    knowledge_documents=[
                        {
                            "doc_id": "knowledge-1",
                            "doc_type": "adr",
                            "filename": "decision.md",
                        }
                    ],
                    user_id="user-1",
                ),
                lambda: visual_store.update_visual_assets(
                    "shared",
                    "user-1",
                    [{"asset_id": "asset-2", "doc_type": "adr"}],
                ),
            ),
        )

    reloaded = bootstrap.get_entry("shared", "user-1")
    assert promoted_count == 1
    assert visual_result is True
    assert reloaded is not None
    assert reloaded["knowledge_promoted"] is True
    assert reloaded["knowledge_project_id"] == "project-2"
    assert reloaded["visual_assets"][0]["asset_id"] == "asset-2"


def test_history_mutation_stops_after_bounded_conflicts(tmp_path: Path) -> None:
    backend = _ConflictingLocalBackend(tmp_path)
    store = HistoryStore("alpha", base_dir=tmp_path, backend=backend)

    with pytest.raises(
        HistoryStoreError,
        match="History state changed too many times to persist safely",
    ):
        store.add(_entry("entry-1"))

    assert backend.attempts == 32


def test_history_mutation_wraps_backend_failure(tmp_path: Path) -> None:
    store = HistoryStore(
        "alpha",
        base_dir=tmp_path,
        backend=_FailingConditionalBackend(tmp_path),
    )

    with pytest.raises(HistoryStoreError, match="Failed to persist history state"):
        store.add(_entry("entry-1"))


def test_history_mutation_receipts_are_private_bounded_and_fail_closed(
    tmp_path: Path,
) -> None:
    store = HistoryStore("alpha", base_dir=tmp_path)
    store.add(_entry("entry-1"))
    for _ in range(70):
        store.toggle_favorite("entry-1", "user-1")

    public = store.get_entry("entry-1", "user-1")
    listed = store.get_for_user("user-1")
    persisted = json.loads(store._path.read_text(encoding="utf-8").splitlines()[0])
    assert public is not None
    assert "_mutation_ids" not in public
    assert "_incarnation_id" not in public
    assert all("_mutation_ids" not in entry for entry in listed)
    assert all("_incarnation_id" not in entry for entry in listed)
    assert isinstance(persisted["_incarnation_id"], str)
    assert len(persisted["_mutation_ids"]) == 64

    persisted["_mutation_ids"] = [f"mutation-{index}" for index in range(65)]
    store._path.write_text(json.dumps(persisted) + "\n", encoding="utf-8")
    original_bytes = store._path.read_bytes()

    with pytest.raises(HistoryStoreError):
        store.get_for_user("user-1")
    with pytest.raises(HistoryStoreError):
        store.toggle_favorite("entry-1", "user-1")
    assert store._path.read_bytes() == original_bytes


def test_history_callers_pass_the_application_state_backend() -> None:
    source_paths = (
        Path("app/routers/history.py"),
        Path("app/routers/knowledge.py"),
        Path("app/routers/generate/_shared.py"),
    )
    calls = []
    for source_path in source_paths:
        tree = ast.parse(source_path.read_text(encoding="utf-8"))
        calls.extend(
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "HistoryStore"
        )

    assert len(calls) == 8
    for call in calls:
        keywords = {keyword.arg for keyword in call.keywords}
        assert {"base_dir", "backend"} <= keywords


def test_history_api_reports_corrupt_state_without_replacement(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "tenants/system/history.jsonl"
    path.parent.mkdir(parents=True)
    path.write_text("{not-json\n", encoding="utf-8")
    client = _client(tmp_path, monkeypatch)
    headers = {"Authorization": f"Bearer {_token('user-1')}"}

    responses = (
        client.get("/history", headers=headers),
        client.get("/history/entry-1", headers=headers),
        client.post("/history/entry-1/star", headers=headers),
        client.delete("/history/entry-1", headers=headers),
        client.put(
            "/history/entry-1/visual-assets",
            json={"visual_assets": []},
            headers=headers,
        ),
    )

    assert all(response.status_code == 500 for response in responses)
    assert all(response.json()["code"] == "INTERNAL_ERROR" for response in responses)
    assert path.read_bytes() == b"{not-json\n"


def test_generate_does_not_replace_corrupt_history_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "tenants/system/history.jsonl"
    path.parent.mkdir(parents=True)
    path.write_text("{not-json\n", encoding="utf-8")
    client = _client(tmp_path, monkeypatch)

    response = client.post(
        "/generate",
        json={"title": "History isolation", "goal": "Keep corrupt state intact"},
    )

    assert response.status_code == 200
    assert path.read_bytes() == b"{not-json\n"


def _client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DECISIONDOC_PROVIDER", "mock")
    monkeypatch.setenv("DECISIONDOC_ENV", "dev")
    monkeypatch.setenv("DECISIONDOC_STORAGE", "local")
    monkeypatch.setenv("DECISIONDOC_STATE_STORAGE", "local")
    monkeypatch.setenv("JWT_SECRET_KEY", "history-integrity-test-secret-key-32")
    monkeypatch.delenv("DECISIONDOC_API_KEY", raising=False)
    monkeypatch.delenv("DECISIONDOC_API_KEYS", raising=False)
    from app.main import create_app

    return TestClient(create_app(), raise_server_exceptions=False)


def _token(user_id: str) -> str:
    from app.services.auth_service import create_access_token

    return create_access_token(user_id, "system", "member", user_id)
