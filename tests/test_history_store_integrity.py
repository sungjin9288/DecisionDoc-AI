from __future__ import annotations

import ast
import json
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.storage.history_store import HistoryEntry, HistoryStore, HistoryStoreError
from app.storage.state_backend import LocalStateBackend, S3StateBackend


class _SlowLocalBackend(LocalStateBackend):
    """Expose lost updates when independent stores do not share a lock."""

    def read_text(self, relative_path: str) -> str | None:
        raw = super().read_text(relative_path)
        time.sleep(0.005)
        return raw


class _Body:
    def __init__(self, data: bytes) -> None:
        self._data = data

    def read(self) -> bytes:
        return self._data


class _MemoryS3Client:
    def __init__(self, *, read_delay: float = 0.0) -> None:
        self.objects: dict[tuple[str, str], bytes] = {}
        self.read_delay = read_delay

    def put_object(
        self,
        *,
        Bucket: str,
        Key: str,
        Body: bytes,
        ContentType: str,
    ) -> None:
        _ = ContentType
        self.objects[(Bucket, Key)] = Body

    def get_object(self, *, Bucket: str, Key: str) -> dict:
        time.sleep(self.read_delay)
        data = self.objects.get((Bucket, Key))
        if data is None:
            error = Exception("NoSuchKey")
            error.response = {"Error": {"Code": "NoSuchKey"}}
            raise error
        return {"Body": _Body(data)}


def _s3_backend(
    *,
    read_delay: float = 0.0,
) -> tuple[S3StateBackend, _MemoryS3Client]:
    client = _MemoryS3Client(read_delay=read_delay)
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

    with pytest.raises(HistoryStoreError, match=error):
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
    with pytest.raises(HistoryStoreError, match="Invalid history identity"):
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
    backend, _ = _s3_backend(read_delay=0.005)
    stores = [
        HistoryStore("alpha", base_dir="/virtual/data", backend=backend)
        for _ in range(20)
    ]

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

    reloaded = HistoryStore("alpha", base_dir="/virtual/data", backend=backend)
    entries = reloaded.get_for_user("user-1")
    assert {entry["entry_id"] for entry in entries} == {
        f"entry-{index}" for index in range(20)
    }
    assert reloaded.get_entry("entry-0", "user-1")["starred"] is False


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
