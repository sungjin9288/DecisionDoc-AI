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

from app.storage.state_backend import (
    LocalStateBackend,
    S3StateBackend,
    StateBackendError,
)
from app.storage.template_store import (
    TemplateEntry,
    TemplateStore,
    TemplateStoreError,
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
    template_id: str,
    *,
    tenant_id: str = "alpha",
    user_id: str = "user-1",
) -> TemplateEntry:
    return TemplateEntry(
        template_id=template_id,
        tenant_id=tenant_id,
        user_id=user_id,
        name=f"Template {template_id}",
        bundle_id="tech_decision",
        bundle_name="기술 결정",
        form_data={"title": template_id},
        created_at="2026-07-16T00:00:00+00:00",
        updated_at="2026-07-16T00:00:00+00:00",
    )


def _record(
    template_id: str,
    *,
    tenant_id: str | None = "alpha",
    user_id: str = "user-1",
) -> dict:
    record = {
        "template_id": template_id,
        "user_id": user_id,
        "name": f"Template {template_id}",
        "bundle_id": "tech_decision",
        "bundle_name": "기술 결정",
        "form_data": {"title": template_id},
        "created_at": "2026-07-16T00:00:00+00:00",
        "updated_at": "2026-07-16T00:00:00+00:00",
        "use_count": 0,
    }
    if tenant_id is not None:
        record["tenant_id"] = tenant_id
    return record


@pytest.mark.parametrize(
    "tenant_id",
    [" tenant", "tenant ", ".", "..", "tenant/a", "tenant\\a", "tenant\na"],
)
def test_template_store_rejects_unsafe_tenant_before_state_access(
    tmp_path: Path,
    tenant_id: str,
) -> None:
    with pytest.raises(ValueError, match="Invalid tenant_id"):
        TemplateStore(tenant_id, data_dir=tmp_path)

    assert not (tmp_path / "tenants").exists()


def test_missing_template_state_read_has_no_side_effect(tmp_path: Path) -> None:
    store = TemplateStore("alpha", data_dir=tmp_path)

    assert store.list_for_user("user-1") == []
    assert not store._path.exists()


def test_empty_jsonl_is_a_valid_empty_template_state(tmp_path: Path) -> None:
    path = tmp_path / "tenants/alpha/templates.jsonl"
    path.parent.mkdir(parents=True)
    path.write_text("", encoding="utf-8")

    assert TemplateStore("alpha", data_dir=tmp_path).list_for_user("user-1") == []
    assert path.read_bytes() == b""


@pytest.mark.parametrize(
    ("raw", "error"),
    [
        ("{not-json\n", "Invalid template state at line 1"),
        ("[]\n", "Invalid template state at line 1"),
        (
            '{"template_id":"first","template_id":"second"}\n',
            "Invalid template state at line 1",
        ),
        (
            json.dumps({**_record("invalid"), "form_data": []}) + "\n",
            "Invalid template state at line 1",
        ),
        (
            json.dumps({**_record("invalid"), "use_count": -1}) + "\n",
            "Invalid template state at line 1",
        ),
        (
            json.dumps(_record("duplicate"))
            + "\n"
            + json.dumps(_record("duplicate"))
            + "\n",
            "Duplicate template identity",
        ),
    ],
)
def test_untrusted_template_state_stops_read_and_write_without_replacement(
    tmp_path: Path,
    raw: str,
    error: str,
) -> None:
    path = tmp_path / "tenants/alpha/templates.jsonl"
    path.parent.mkdir(parents=True)
    path.write_text(raw, encoding="utf-8")
    original_bytes = path.read_bytes()
    store = TemplateStore("alpha", data_dir=tmp_path)

    with pytest.raises(TemplateStoreError, match=error):
        store.list_for_user("user-1")
    with pytest.raises(TemplateStoreError, match=error):
        store.add(_entry("new-template"))

    assert path.read_bytes() == original_bytes


def test_foreign_template_remains_hidden_and_preserved(tmp_path: Path) -> None:
    path = tmp_path / "tenants/alpha/templates.jsonl"
    path.parent.mkdir(parents=True)
    foreign = {"tenant_id": "beta", "opaque": {"keep": True}}
    path.write_text(json.dumps(foreign) + "\n", encoding="utf-8")
    store = TemplateStore("alpha", data_dir=tmp_path)

    store.add(_entry("owned"))
    assert [item["template_id"] for item in store.list_for_user("user-1")] == ["owned"]
    persisted = [json.loads(line) for line in path.read_text().splitlines()]
    assert persisted[0] == foreign


def test_legacy_template_without_tenant_remains_owned(tmp_path: Path) -> None:
    path = tmp_path / "tenants/alpha/templates.jsonl"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(_record("legacy", tenant_id=None)) + "\n")
    store = TemplateStore("alpha", data_dir=tmp_path)

    store.increment_use_count("legacy", "user-1")
    legacy = store.get("legacy", "user-1")

    assert legacy is not None
    assert legacy.get("tenant_id") is None
    assert legacy["use_count"] == 1


@pytest.mark.parametrize(
    ("field", "value", "error"),
    [
        ("template_id", "", "Invalid template identity"),
        ("form_data", [], "Invalid template form data"),
        ("use_count", -1, "Invalid template use count"),
    ],
)
def test_invalid_caller_template_is_rejected_before_write(
    tmp_path: Path,
    field: str,
    value: object,
    error: str,
) -> None:
    entry = replace(_entry("invalid"), **{field: value})
    store = TemplateStore("alpha", data_dir=tmp_path)

    with pytest.raises(ValueError, match=error):
        store.add(entry)

    assert not store._path.exists()


def test_template_store_rejects_reused_identity(tmp_path: Path) -> None:
    store = TemplateStore("alpha", data_dir=tmp_path)
    store.add(_entry("same-id"))
    original_bytes = store._path.read_bytes()

    with pytest.raises(TemplateStoreError, match="Duplicate template identity"):
        store.add(_entry("same-id", user_id="user-2"))

    assert store._path.read_bytes() == original_bytes


def test_missing_increment_does_not_rewrite_template_state(tmp_path: Path) -> None:
    store = TemplateStore("alpha", data_dir=tmp_path)
    store.add(_entry("template-1"))
    original_bytes = store._path.read_bytes()

    store.increment_use_count("missing", "user-1")

    assert store._path.read_bytes() == original_bytes


def test_independent_local_template_stores_preserve_concurrent_adds(
    tmp_path: Path,
) -> None:
    stores = [
        TemplateStore(
            "alpha",
            data_dir=tmp_path,
            backend=_SlowLocalBackend(tmp_path),
        )
        for _ in range(20)
    ]
    for store in stores:
        store._lock = nullcontext()

    def add(index: int) -> None:
        stores[index].add(_entry(f"template-{index}"))

    with ThreadPoolExecutor(max_workers=20) as executor:
        list(executor.map(add, range(20)))

    templates = TemplateStore("alpha", data_dir=tmp_path).list_for_user("user-1")
    assert {item["template_id"] for item in templates} == {
        f"template-{index}" for index in range(20)
    }


def test_independent_local_template_stores_preserve_concurrent_use_counts(
    tmp_path: Path,
) -> None:
    creator = TemplateStore("alpha", data_dir=tmp_path)
    creator.add(_entry("shared"))
    stores = [
        TemplateStore(
            "alpha",
            data_dir=tmp_path,
            backend=_SlowLocalBackend(tmp_path),
        )
        for _ in range(20)
    ]
    for store in stores:
        store._lock = nullcontext()

    with ThreadPoolExecutor(max_workers=20) as executor:
        list(
            executor.map(
                lambda store: store.increment_use_count("shared", "user-1"),
                stores,
            )
        )

    assert creator.get("shared", "user-1")["use_count"] == 20


def test_template_round_trip_through_fake_s3() -> None:
    backend, client = _s3_backend()
    store = TemplateStore("alpha", data_dir="/virtual/data", backend=backend)
    store.add(_entry("template-1"))
    key = (
        "unit-bucket",
        "decisiondoc-ai/state/tenants/alpha/templates.jsonl",
    )

    assert key in client.objects
    reloaded = TemplateStore("alpha", data_dir="/virtual/data", backend=backend).get(
        "template-1", "user-1"
    )
    assert reloaded is not None
    assert reloaded["name"] == "Template template-1"


def test_untrusted_fake_s3_template_state_is_preserved() -> None:
    backend, client = _s3_backend()
    key = (
        "unit-bucket",
        "decisiondoc-ai/state/tenants/alpha/templates.jsonl",
    )
    client.objects[key] = b"{not-json\n"
    store = TemplateStore("alpha", data_dir="/virtual/data", backend=backend)

    with pytest.raises(TemplateStoreError, match="Invalid template state at line 1"):
        store.add(_entry("new-template"))

    assert client.objects[key] == b"{not-json\n"


def test_independent_fake_s3_template_stores_preserve_concurrent_mutations() -> None:
    client = _MemoryS3Client(read_delay=0.005)
    stores = [
        TemplateStore(
            "alpha",
            data_dir=f"/virtual/worker-{index}",
            backend=_s3_backend(client=client)[0],
        )
        for index in range(20)
    ]
    for store in stores:
        store._lock = nullcontext()

    def add(index: int) -> None:
        stores[index].add(_entry(f"template-{index}"))

    with ThreadPoolExecutor(max_workers=20) as executor:
        list(executor.map(add, range(20)))
    with ThreadPoolExecutor(max_workers=20) as executor:
        list(
            executor.map(
                lambda store: store.increment_use_count("template-0", "user-1"),
                stores,
            )
        )

    reloaded = TemplateStore(
        "alpha",
        data_dir="/virtual/reload",
        backend=_s3_backend(client=client)[0],
    )
    templates = reloaded.list_for_user("user-1")
    assert {item["template_id"] for item in templates} == {
        f"template-{index}" for index in range(20)
    }
    assert reloaded.get("template-0", "user-1")["use_count"] == 20


def test_template_mutation_reconciles_commit_then_successor_create() -> None:
    client = _MemoryS3Client()
    bootstrap = TemplateStore(
        "alpha",
        data_dir="/virtual/bootstrap",
        backend=_s3_backend(client=client)[0],
    )
    bootstrap.add(_entry("shared"))
    primary = TemplateStore(
        "alpha",
        data_dir="/virtual/primary",
        backend=_s3_backend(client=client)[0],
    )
    successor = TemplateStore(
        "alpha",
        data_dir="/virtual/successor",
        backend=_s3_backend(client=client)[0],
    )
    primary._lock = nullcontext()
    successor._lock = nullcontext()
    client.fail_after_next_conditional_write(
        after_write=lambda: successor.add(_entry("successor"))
    )

    primary.increment_use_count("shared", "user-1")

    assert bootstrap.get("shared", "user-1")["use_count"] == 1
    assert bootstrap.get("successor", "user-1") is not None


def test_template_mutation_does_not_apply_to_recreated_identity() -> None:
    client = _MemoryS3Client()
    bootstrap = TemplateStore(
        "alpha",
        data_dir="/virtual/bootstrap",
        backend=_s3_backend(client=client)[0],
    )
    bootstrap.add(_entry("shared"))
    primary = TemplateStore(
        "alpha",
        data_dir="/virtual/primary",
        backend=_s3_backend(client=client)[0],
    )
    successor = TemplateStore(
        "alpha",
        data_dir="/virtual/successor",
        backend=_s3_backend(client=client)[0],
    )
    primary._lock = nullcontext()
    successor._lock = nullcontext()

    def recreate() -> None:
        assert successor.delete("shared", "user-1") is True
        successor.add(replace(_entry("shared"), name="Replacement"))

    client.fail_after_next_conditional_write(after_write=recreate)

    with pytest.raises(
        TemplateStoreError,
        match="Failed to persist template state",
    ):
        primary.increment_use_count("shared", "user-1")

    replacement = bootstrap.get("shared", "user-1")
    assert replacement is not None
    assert replacement["name"] == "Replacement"
    assert replacement["use_count"] == 0


def test_template_delete_reconciliation_preserves_recreated_identity() -> None:
    client = _MemoryS3Client()
    bootstrap = TemplateStore(
        "alpha",
        data_dir="/virtual/bootstrap",
        backend=_s3_backend(client=client)[0],
    )
    bootstrap.add(_entry("shared"))
    primary = TemplateStore(
        "alpha",
        data_dir="/virtual/primary",
        backend=_s3_backend(client=client)[0],
    )
    successor = TemplateStore(
        "alpha",
        data_dir="/virtual/successor",
        backend=_s3_backend(client=client)[0],
    )
    primary._lock = nullcontext()
    successor._lock = nullcontext()
    replacement = replace(
        _entry("shared"),
        name="Replacement",
    )
    client.fail_after_next_conditional_write(
        after_write=lambda: successor.add(replacement)
    )

    assert primary.delete("shared", "user-1") is True

    recreated = bootstrap.get("shared", "user-1")
    assert recreated is not None
    assert recreated["name"] == "Replacement"


def test_template_mutation_stops_after_bounded_conflicts(tmp_path: Path) -> None:
    backend = _ConflictingLocalBackend(tmp_path)
    store = TemplateStore("alpha", data_dir=tmp_path, backend=backend)

    with pytest.raises(
        TemplateStoreError,
        match="Template state changed too many times to persist safely",
    ):
        store.add(_entry("template-1"))

    assert backend.attempts == 32


def test_template_mutation_wraps_backend_failure(tmp_path: Path) -> None:
    store = TemplateStore(
        "alpha",
        data_dir=tmp_path,
        backend=_FailingConditionalBackend(tmp_path),
    )

    with pytest.raises(
        TemplateStoreError,
        match="Failed to persist template state",
    ):
        store.add(_entry("template-1"))


def test_template_mutation_receipts_are_private_bounded_and_fail_closed(
    tmp_path: Path,
) -> None:
    store = TemplateStore("alpha", data_dir=tmp_path)
    store.add(_entry("template-1"))
    for _ in range(70):
        store.increment_use_count("template-1", "user-1")

    public = store.get("template-1", "user-1")
    persisted = json.loads(store._path.read_text(encoding="utf-8").splitlines()[0])
    assert public is not None
    assert "_mutation_ids" not in public
    assert "_incarnation_id" not in public
    assert isinstance(persisted["_incarnation_id"], str)
    assert len(persisted["_mutation_ids"]) == 64

    persisted["_mutation_ids"] = [f"mutation-{index}" for index in range(65)]
    store._path.write_text(json.dumps(persisted) + "\n", encoding="utf-8")
    original_bytes = store._path.read_bytes()

    with pytest.raises(TemplateStoreError):
        store.list_for_user("user-1")
    with pytest.raises(TemplateStoreError):
        store.increment_use_count("template-1", "user-1")
    assert store._path.read_bytes() == original_bytes


def test_template_routes_pass_the_application_state_backend() -> None:
    source_path = Path("app/routers/templates.py")
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "TemplateStore"
    ]

    assert len(calls) == 4
    for call in calls:
        keywords = {keyword.arg for keyword in call.keywords}
        assert {"data_dir", "backend"} <= keywords


def test_template_api_rejects_non_object_form_data(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _client(tmp_path, monkeypatch)

    response = client.post(
        "/templates",
        json={"name": "Invalid", "bundle_id": "tech_decision", "form_data": []},
    )

    assert response.status_code == 422
    assert response.json()["detail"]["errors"] == [
        {"field": "form_data", "message": "입력값은 객체여야 합니다."}
    ]
    assert not (tmp_path / "tenants/system/templates.jsonl").exists()


def test_template_api_reports_corrupt_state_as_internal_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "tenants/system/templates.jsonl"
    path.parent.mkdir(parents=True)
    path.write_text("{not-json\n", encoding="utf-8")
    client = _client(tmp_path, monkeypatch)

    list_response = client.get("/templates")
    create_response = client.post(
        "/templates",
        json={"name": "New", "bundle_id": "tech_decision", "form_data": {}},
    )

    assert list_response.status_code == 500
    assert list_response.json()["code"] == "INTERNAL_ERROR"
    assert create_response.status_code == 500
    assert create_response.json()["code"] == "INTERNAL_ERROR"
    assert path.read_bytes() == b"{not-json\n"


def _client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DECISIONDOC_PROVIDER", "mock")
    monkeypatch.setenv("DECISIONDOC_ENV", "dev")
    monkeypatch.setenv("JWT_SECRET_KEY", "template-integrity-test-secret-key")
    monkeypatch.delenv("DECISIONDOC_API_KEY", raising=False)
    monkeypatch.delenv("DECISIONDOC_API_KEYS", raising=False)
    from app.main import create_app

    return TestClient(create_app(), raise_server_exceptions=False)
