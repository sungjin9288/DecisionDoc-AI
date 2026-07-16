from __future__ import annotations

import json
import threading
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.storage.ab_test_store import ABTestStore, ABTestStoreError
from app.storage.request_pattern_store import (
    RequestPatternStore,
    RequestPatternStoreError,
)
from app.storage.state_backend import S3StateBackend


class _Body:
    def __init__(self, data: bytes) -> None:
        self._data = data

    def read(self) -> bytes:
        return self._data


class _MemoryS3Client:
    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], bytes] = {}

    def get_object(self, *, Bucket: str, Key: str) -> dict[str, _Body]:
        data = self.objects.get((Bucket, Key))
        if data is None:
            error = Exception("NoSuchKey")
            error.response = {"Error": {"Code": "NoSuchKey"}}
            raise error
        return {"Body": _Body(data)}

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


def _s3_backend() -> tuple[S3StateBackend, _MemoryS3Client]:
    client = _MemoryS3Client()
    backend = S3StateBackend(
        bucket="state-bucket",
        prefix="decisiondoc/state/",
        s3_client=client,
    )
    return backend, client


def _active_ab_record(
    bundle_id: str = "proposal_kr",
    *,
    tenant_id: str | None = "tenant_a",
) -> dict:
    record = {
        "bundle_id": bundle_id,
        "tenant_id": tenant_id,
        "status": "active",
        "variant_a_hint": "Use concise evidence.",
        "variant_b_hint": "State assumptions explicitly.",
        "min_samples": 2,
        "generation_count": 0,
        "created_at": "2026-07-17T00:00:00+00:00",
        "concluded_at": None,
        "winner": None,
        "winner_avg_score": None,
        "results": {"variant_a": [], "variant_b": []},
    }
    if tenant_id is None:
        record.pop("tenant_id")
    return record


def _pattern_record(
    record_id: str,
    *,
    tenant_id: str | None = "tenant_a",
    matched: bool = False,
) -> dict:
    record = {
        "record_id": record_id,
        "tenant_id": tenant_id,
        "timestamp": "2026-07-17T00:00:00+00:00",
        "raw_input": f"request {record_id}",
        "bundle_id": "proposal_kr" if matched else None,
        "matched": matched,
    }
    if tenant_id is None:
        record.pop("tenant_id")
    return record


def test_missing_quality_experiment_state_has_no_read_side_effect(tmp_path: Path) -> None:
    ab_store = ABTestStore(tmp_path, tenant_id="tenant_a")
    pattern_store = RequestPatternStore(tmp_path, tenant_id="tenant_a")

    assert ab_store.list_tests() == []
    assert pattern_store.get_all() == []
    assert not ab_store._path.exists()
    assert not pattern_store._path.exists()


@pytest.mark.parametrize(
    "raw",
    [
        b"",
        b"{broken",
        b"[]",
        b'{"proposal_kr":1}',
        (
            b'{"proposal_kr":'
            + json.dumps(_active_ab_record()).encode()
            + b',"proposal_kr":'
            + json.dumps(_active_ab_record()).encode()
            + b"}"
        ),
        b"\xff\xfe",
    ],
)
def test_ab_state_corruption_fails_closed_and_preserves_source(
    tmp_path: Path,
    raw: bytes,
) -> None:
    path = tmp_path / "tenants" / "tenant_a" / "ab_tests.json"
    path.parent.mkdir(parents=True)
    path.write_bytes(raw)
    store = ABTestStore(tmp_path, tenant_id="tenant_a")

    with pytest.raises(ABTestStoreError):
        store.list_tests()
    with pytest.raises(ABTestStoreError):
        store.create_test("new_bundle", "hint a", "hint b")

    assert path.read_bytes() == raw


def test_ab_owned_schema_drift_and_storage_identity_fail_closed(tmp_path: Path) -> None:
    path = tmp_path / "tenants" / "tenant_a" / "ab_tests.json"
    path.parent.mkdir(parents=True)
    record = _active_ab_record("other_bundle")
    raw = json.dumps({"proposal_kr": record}).encode()
    path.write_bytes(raw)

    with pytest.raises(ABTestStoreError, match="storage identity mismatch"):
        ABTestStore(tmp_path, tenant_id="tenant_a").list_tests()
    assert path.read_bytes() == raw

    record = _active_ab_record()
    record["generation_count"] = True
    raw = json.dumps({"proposal_kr": record}).encode()
    path.write_bytes(raw)
    with pytest.raises(ABTestStoreError, match="generation count"):
        ABTestStore(tmp_path, tenant_id="tenant_a").list_tests()
    assert path.read_bytes() == raw


def test_ab_legacy_and_foreign_records_remain_isolated(tmp_path: Path) -> None:
    path = tmp_path / "tenants" / "tenant_a" / "ab_tests.json"
    path.parent.mkdir(parents=True)
    foreign = _active_ab_record("foreign", tenant_id="tenant_b")
    source = {
        "legacy": _active_ab_record("legacy", tenant_id=None),
        "foreign": foreign,
    }
    path.write_text(json.dumps(source), encoding="utf-8")
    store = ABTestStore(tmp_path, tenant_id="tenant_a")

    assert [record["bundle_id"] for record in store.list_active_tests()] == ["legacy"]
    store.create_test("owned", "owned a", "owned b")
    store.delete_test("foreign")

    persisted = json.loads(path.read_text(encoding="utf-8"))
    assert persisted["foreign"] == foreign
    assert persisted["owned"]["tenant_id"] == "tenant_a"


def test_independent_ab_stores_preserve_concurrent_updates(tmp_path: Path) -> None:
    stores = [ABTestStore(tmp_path, tenant_id="tenant_a") for _ in range(20)]
    create_threads = [
        threading.Thread(
            target=store.create_test,
            args=(f"bundle_{index}", "hint a", "hint b"),
        )
        for index, store in enumerate(stores)
    ]
    for thread in create_threads:
        thread.start()
    for thread in create_threads:
        thread.join()

    reader = ABTestStore(tmp_path, tenant_id="tenant_a")
    assert len(reader.list_active_tests()) == 20

    reader.create_test("round_robin", "hint a", "hint b")
    variants: list[str | None] = []
    result_lock = threading.Lock()

    def assign(store: ABTestStore) -> None:
        variant = store.get_next_variant("round_robin")
        with result_lock:
            variants.append(variant)

    assignment_threads = [threading.Thread(target=assign, args=(store,)) for store in stores]
    for thread in assignment_threads:
        thread.start()
    for thread in assignment_threads:
        thread.join()

    assert variants.count("variant_a") == 10
    assert variants.count("variant_b") == 10
    assert reader.get_active_test("round_robin")["generation_count"] == 20


def test_ab_store_round_trips_and_serializes_through_fake_s3(tmp_path: Path) -> None:
    backend, _client = _s3_backend()
    stores = [
        ABTestStore(tmp_path, tenant_id="tenant_a", backend=backend)
        for _ in range(20)
    ]
    threads = [
        threading.Thread(
            target=store.create_test,
            args=(f"bundle_{index}", "hint a", "hint b"),
        )
        for index, store in enumerate(stores)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    reloaded = ABTestStore(tmp_path, tenant_id="tenant_a", backend=backend)
    assert len(reloaded.list_active_tests()) == 20
    assert not (tmp_path / "tenants").exists()


@pytest.mark.parametrize(
    "raw",
    [
        b"{broken\n",
        b"[]\n",
        b'{"record_id":"duplicate","record_id":"again"}\n',
        b'"not-an-object"\n',
        b"\xff\xfe",
    ],
)
def test_request_pattern_corruption_fails_closed_and_preserves_source(
    tmp_path: Path,
    raw: bytes,
) -> None:
    path = tmp_path / "tenants" / "tenant_a" / "request_patterns.jsonl"
    path.parent.mkdir(parents=True)
    path.write_bytes(raw)
    store = RequestPatternStore(tmp_path, tenant_id="tenant_a")

    with pytest.raises(RequestPatternStoreError):
        store.get_all()
    with pytest.raises(RequestPatternStoreError):
        store.record_request("new request", None, False)

    assert path.read_bytes() == raw


def test_request_pattern_blank_line_and_duplicate_identity_fail_closed(
    tmp_path: Path,
) -> None:
    path = tmp_path / "tenants" / "tenant_a" / "request_patterns.jsonl"
    path.parent.mkdir(parents=True)
    line = json.dumps(_pattern_record("same"))

    for raw in (f"{line}\n\n", f"{line}\n{line}\n"):
        path.write_text(raw, encoding="utf-8")
        store = RequestPatternStore(tmp_path, tenant_id="tenant_a")
        with pytest.raises(RequestPatternStoreError):
            store.clear_unmatched()
        assert path.read_text(encoding="utf-8") == raw


def test_request_pattern_legacy_and_foreign_records_remain_isolated(
    tmp_path: Path,
) -> None:
    path = tmp_path / "tenants" / "tenant_a" / "request_patterns.jsonl"
    path.parent.mkdir(parents=True)
    own = _pattern_record("own", matched=True)
    legacy = _pattern_record("legacy", tenant_id=None)
    foreign = _pattern_record("foreign", tenant_id="tenant_b")
    path.write_text(
        "".join(f"{json.dumps(record)}\n" for record in (own, legacy, foreign)),
        encoding="utf-8",
    )
    store = RequestPatternStore(tmp_path, tenant_id="tenant_a")

    assert [record["record_id"] for record in store.get_all()] == ["own", "legacy"]
    assert store.clear_unmatched() == 1
    store.record_request("new request", None, False)

    persisted = [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
    ]
    assert foreign in persisted
    assert all(record["record_id"] != "legacy" for record in persisted)


@pytest.mark.parametrize("use_s3", [False, True])
def test_independent_request_pattern_stores_preserve_concurrent_appends(
    tmp_path: Path,
    use_s3: bool,
) -> None:
    backend = _s3_backend()[0] if use_s3 else None
    stores = [
        RequestPatternStore(
            tmp_path,
            tenant_id="tenant_a",
            backend=backend,
        )
        for _ in range(20)
    ]
    threads = [
        threading.Thread(
            target=store.record_request,
            args=(f"request {index}", None, False),
        )
        for index, store in enumerate(stores)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    reloaded = RequestPatternStore(
        tmp_path,
        tenant_id="tenant_a",
        backend=backend,
    )
    assert {record["raw_input"] for record in reloaded.get_all()} == {
        f"request {index}" for index in range(20)
    }
    if use_s3:
        assert not (tmp_path / "tenants").exists()


def test_quality_experiment_routes_use_application_s3_backend(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DECISIONDOC_PROVIDER", "mock")
    monkeypatch.setenv("DECISIONDOC_API_KEY", "quality-api-key")
    monkeypatch.setenv("DECISIONDOC_OPS_KEY", "quality-ops-key")

    from app.main import create_app

    app = create_app()
    backend, _client = _s3_backend()
    app.state.state_backend = backend
    client = TestClient(app, raise_server_exceptions=False)
    headers = {
        "X-DecisionDoc-Api-Key": "quality-api-key",
        "X-DecisionDoc-Ops-Key": "quality-ops-key",
    }

    ABTestStore(
        tmp_path,
        tenant_id="system",
        backend=backend,
    ).create_test("proposal_kr", "hint a", "hint b")
    active = client.get("/ab-tests/active", headers=headers)
    assert active.status_code == 200
    assert active.json()[0]["bundle_id"] == "proposal_kr"

    recorded = client.post(
        "/generate/freeform",
        headers=headers,
        json={"title": "New report", "goal": "Track this request"},
    )
    assert recorded.status_code == 200
    patterns = RequestPatternStore(
        tmp_path,
        tenant_id="system",
        backend=backend,
    ).get_all()
    assert patterns[0]["raw_input"] == "New report Track this request"
    assert not (tmp_path / "tenants" / "system" / "request_patterns.jsonl").exists()


def test_quality_experiment_api_does_not_hide_corrupt_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DECISIONDOC_PROVIDER", "mock")
    monkeypatch.setenv("DECISIONDOC_API_KEY", "quality-api-key")
    monkeypatch.setenv("DECISIONDOC_OPS_KEY", "quality-ops-key")

    from app.main import create_app

    app = create_app()
    backend, _client = _s3_backend()
    app.state.state_backend = backend
    client = TestClient(app, raise_server_exceptions=False)
    headers = {
        "X-DecisionDoc-Api-Key": "quality-api-key",
        "X-DecisionDoc-Ops-Key": "quality-ops-key",
    }

    backend.write_bytes("tenants/system/ab_tests.json", b"{broken")
    response = client.get("/ab-tests/active", headers=headers)
    assert response.status_code == 500
    assert response.json()["code"] == "INTERNAL_ERROR"
    assert backend.read_bytes("tenants/system/ab_tests.json") == b"{broken"

    backend.write_bytes("tenants/system/request_patterns.jsonl", b"{broken\n")
    response = client.post(
        "/generate/freeform",
        headers=headers,
        json={"title": "New report", "goal": "Track this request"},
    )
    assert response.status_code == 500
    assert response.json()["code"] == "INTERNAL_ERROR"
    assert backend.read_bytes("tenants/system/request_patterns.jsonl") == b"{broken\n"
