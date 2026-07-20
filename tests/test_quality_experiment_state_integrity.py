from __future__ import annotations

import hashlib
import json
import threading
from contextlib import nullcontext
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Callable, get_type_hints

import pytest
from fastapi.testclient import TestClient

from app.storage.ab_test_store import ABTestStore, ABTestStoreError
from app.storage.prompt_override_store import (
    PromptOverrideStore,
    PromptOverrideStoreError,
)
from app.storage.request_pattern_store import (
    RequestPatternStore,
    RequestPatternStoreError,
)
from app.storage.state_backend import LocalStateBackend, S3StateBackend


class _Body:
    def __init__(self, data: bytes) -> None:
        self._data = data

    def read(self) -> bytes:
        return self._data


class _MemoryS3Client:
    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], bytes] = {}
        self._lock = threading.Lock()
        self._fail_after_key_suffix: str | None = None
        self._after_failed_write: Callable[[], None] | None = None

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
        key_suffix: str,
        after_write: Callable[[], None] | None = None,
    ) -> None:
        self._fail_after_key_suffix = key_suffix
        self._after_failed_write = after_write

    def get_object(self, *, Bucket: str, Key: str) -> dict[str, _Body]:
        with self._lock:
            data = self.objects.get((Bucket, Key))
        if data is None:
            raise self._error("NoSuchKey")
        return {"Body": _Body(data), "ETag": self._etag(data)}

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
                (IfNoneMatch is not None or IfMatch is not None)
                and self._fail_after_key_suffix is not None
                and Key.endswith(self._fail_after_key_suffix)
            )
            if fail_after_write:
                self._fail_after_key_suffix = None
                after_write = self._after_failed_write
                self._after_failed_write = None
            else:
                after_write = None

        if not fail_after_write:
            return
        if after_write is not None:
            after_write()
        raise self._error("InternalError")


class _AlwaysConflictingBackend(LocalStateBackend):
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

    def replace_text_if_equal(
        self,
        relative_path: str,
        *,
        expected: str,
        replacement: str,
        content_type: str = "application/json; charset=utf-8",
    ) -> bool:
        _ = relative_path, expected, replacement, content_type
        self.attempts += 1
        return False


def _s3_backend(
    client: _MemoryS3Client | None = None,
) -> tuple[S3StateBackend, _MemoryS3Client]:
    selected_client = client or _MemoryS3Client()
    backend = S3StateBackend(
        bucket="state-bucket",
        prefix="decisiondoc/state/",
        s3_client=selected_client,
    )
    return backend, selected_client


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
    stores = [
        ABTestStore(
            tmp_path,
            tenant_id="tenant_a",
            backend=LocalStateBackend(tmp_path),
        )
        for _ in range(20)
    ]
    for store in stores:
        store._lock = nullcontext()
    with ThreadPoolExecutor(max_workers=20) as executor:
        list(
            executor.map(
                lambda item: item[1].create_test(
                    f"bundle_{item[0]}",
                    "hint a",
                    "hint b",
                ),
                enumerate(stores),
            )
        )

    reader = ABTestStore(tmp_path, tenant_id="tenant_a")
    assert len(reader.list_active_tests()) == 20

    reader.create_test("round_robin", "hint a", "hint b")
    with ThreadPoolExecutor(max_workers=20) as executor:
        variants = list(
            executor.map(
                lambda store: store.get_next_variant("round_robin"),
                stores,
            )
        )

    assert variants.count("variant_a") == 10
    assert variants.count("variant_b") == 10
    assert reader.get_active_test("round_robin")["generation_count"] == 20


def test_ab_store_round_trips_and_serializes_through_fake_s3(tmp_path: Path) -> None:
    _backend, client = _s3_backend()
    stores = [
        ABTestStore(
            tmp_path,
            tenant_id="tenant_a",
            backend=_s3_backend(client)[0],
        )
        for _ in range(20)
    ]
    for store in stores:
        store._lock = nullcontext()
    with ThreadPoolExecutor(max_workers=20) as executor:
        list(
            executor.map(
                lambda item: item[1].create_test(
                    f"bundle_{item[0]}",
                    "hint a",
                    "hint b",
                ),
                enumerate(stores),
            )
        )

    reloaded = ABTestStore(
        tmp_path,
        tenant_id="tenant_a",
        backend=_s3_backend(client)[0],
    )
    assert len(reloaded.list_active_tests()) == 20
    reloaded.create_test("round_robin", "hint a", "hint b")
    with ThreadPoolExecutor(max_workers=20) as executor:
        variants = list(
            executor.map(
                lambda store: store.get_next_variant("round_robin"),
                stores,
            )
        )
    assert variants.count("variant_a") == 10
    assert variants.count("variant_b") == 10
    assert reloaded.get_active_test("round_robin")["generation_count"] == 20
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
    client = _MemoryS3Client() if use_s3 else None
    stores = [
        RequestPatternStore(
            tmp_path,
            tenant_id="tenant_a",
            backend=(
                _s3_backend(client)[0]
                if client is not None
                else LocalStateBackend(tmp_path)
            ),
        )
        for _ in range(20)
    ]
    for store in stores:
        store._lock = nullcontext()
    with ThreadPoolExecutor(max_workers=20) as executor:
        list(
            executor.map(
                lambda item: item[1].record_request(
                    f"request {item[0]}",
                    None,
                    False,
                ),
                enumerate(stores),
            )
        )

    reloaded = RequestPatternStore(
        tmp_path,
        tenant_id="tenant_a",
        backend=(
            _s3_backend(client)[0]
            if client is not None
            else LocalStateBackend(tmp_path)
        ),
    )
    assert {record["raw_input"] for record in reloaded.get_all()} == {
        f"request {index}" for index in range(20)
    }
    if use_s3:
        assert not (tmp_path / "tenants").exists()


def test_quality_experiment_public_records_hide_mutation_metadata(
    tmp_path: Path,
) -> None:
    ab_store = ABTestStore(tmp_path, tenant_id="tenant_a")
    ab_store.create_test("proposal_kr", "hint a", "hint b")

    public_records = [
        ab_store.get_active_test("proposal_kr"),
        ab_store.list_active_tests()[0],
        ab_store.list_tests()[0],
    ]
    assert all(
        not any(field.startswith("_") for field in record)
        for record in public_records
        if record is not None
    )

    persisted = json.loads(ab_store._path.read_text(encoding="utf-8"))
    assert persisted["proposal_kr"]["_incarnation_id"]
    assert persisted["proposal_kr"]["_mutation_ids"]


def test_ab_conclusion_resumes_after_override_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = ABTestStore(tmp_path, tenant_id="tenant_a")
    store.create_test("proposal_kr", "winner hint", "loser hint", min_samples=1)
    store.record_result("proposal_kr", "variant_a", 0.9)
    store.record_result("proposal_kr", "variant_b", 0.2)

    original_save = PromptOverrideStore.save_override
    attempts = 0

    def fail_once(self, *args, **kwargs):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("simulated override outage")
        return original_save(self, *args, **kwargs)

    monkeypatch.setattr(PromptOverrideStore, "save_override", fail_once)
    with pytest.raises(RuntimeError, match="simulated override outage"):
        store.evaluate_and_conclude("proposal_kr")

    active = store.get_active_test("proposal_kr")
    assert active is not None
    assert not any(field.startswith("_") for field in active)
    assert store.get_next_variant("proposal_kr") == "variant_a"

    assert store.evaluate_and_conclude("proposal_kr") == "variant_a"
    assert store.get_active_test("proposal_kr") is None
    override = PromptOverrideStore(
        tmp_path,
        tenant_id="tenant_a",
    ).get_override("proposal_kr")
    assert override is not None
    assert override["override_hint"] == "winner hint"


def test_ab_pending_conclusion_must_match_persisted_results(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = ABTestStore(tmp_path, tenant_id="tenant_a")
    store.create_test("proposal_kr", "winner hint", "loser hint", min_samples=1)
    store.record_result("proposal_kr", "variant_a", 0.9)
    store.record_result("proposal_kr", "variant_b", 0.2)

    def fail_override(*args, **kwargs):
        raise RuntimeError("simulated override outage")

    monkeypatch.setattr(PromptOverrideStore, "save_override", fail_override)
    with pytest.raises(RuntimeError, match="simulated override outage"):
        store.evaluate_and_conclude("proposal_kr")

    payload = json.loads(store._path.read_text(encoding="utf-8"))
    payload["proposal_kr"]["_pending_conclusion"]["override_hint"] = "forged hint"
    store._path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(
        ABTestStoreError,
        match="does not match persisted results",
    ):
        store.get_active_test("proposal_kr")


def test_ab_assignment_does_not_mix_replaced_experiment_hint(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backend = LocalStateBackend(tmp_path)
    primary = ABTestStore(tmp_path, tenant_id="tenant_a", backend=backend)
    successor = ABTestStore(tmp_path, tenant_id="tenant_a", backend=backend)
    primary._lock = nullcontext()
    successor._lock = nullcontext()
    primary.create_test("proposal_kr", "old a", "old b")

    original_replace = backend.replace_text_if_equal

    def replace_after_recreate(*args, **kwargs):
        monkeypatch.setattr(backend, "replace_text_if_equal", original_replace)
        successor.create_test("proposal_kr", "new a", "new b")
        return original_replace(*args, **kwargs)

    monkeypatch.setattr(backend, "replace_text_if_equal", replace_after_recreate)
    assert primary.get_next_assignment("proposal_kr") is None

    current = primary.get_active_test("proposal_kr")
    assert current is not None
    assert current["variant_a_hint"] == "new a"
    assert current["generation_count"] == 0


def test_ab_result_is_bound_to_assigned_experiment(tmp_path: Path) -> None:
    store = ABTestStore(tmp_path, tenant_id="tenant_a")
    store.create_test("proposal_kr", "old a", "old b", min_samples=1)
    assignment = store.get_next_assignment("proposal_kr")
    assert assignment is not None
    variant, hint, experiment_id = assignment
    assert hint == "old a"
    assert experiment_id is not None
    assert store.record_result(
        "proposal_kr",
        variant,
        0.8,
        experiment_id=experiment_id,
    ) is True

    store.create_test("proposal_kr", "new a", "new b", min_samples=1)
    assert store.record_result(
        "proposal_kr",
        variant,
        0.9,
        experiment_id=experiment_id,
    ) is False
    assert (
        store.evaluate_and_conclude(
            "proposal_kr",
            experiment_id=experiment_id,
        )
        is None
    )
    current = store.get_active_test("proposal_kr")
    assert current is not None
    assert current["results"] == {"variant_a": [], "variant_b": []}


def test_independent_workers_conclude_one_ab_experiment_once() -> None:
    _backend, client = _s3_backend()
    seed = ABTestStore(
        "/virtual/seed",
        tenant_id="tenant_a",
        backend=_s3_backend(client)[0],
    )
    seed.create_test("proposal_kr", "winner hint", "loser hint", min_samples=1)
    seed.record_result("proposal_kr", "variant_a", 0.9)
    seed.record_result("proposal_kr", "variant_b", 0.2)

    workers = [
        ABTestStore(
            f"/virtual/worker-{index}",
            tenant_id="tenant_a",
            backend=_s3_backend(client)[0],
        )
        for index in range(8)
    ]
    for worker in workers:
        worker._lock = nullcontext()

    with ThreadPoolExecutor(max_workers=8) as executor:
        winners = list(
            executor.map(
                lambda worker: worker.evaluate_and_conclude("proposal_kr"),
                workers,
            )
        )

    assert {winner for winner in winners if winner is not None} == {"variant_a"}
    assert winners.count("variant_a") >= 1
    concluded = seed.list_concluded_tests()
    assert len(concluded) == 1
    assert concluded[0]["winner"] == "variant_a"
    override = PromptOverrideStore(
        "/virtual/override-reader",
        tenant_id="tenant_a",
        backend=_s3_backend(client)[0],
    ).get_override("proposal_kr")
    assert override is not None
    assert override["override_hint"] == "winner hint"


def test_ab_assignment_reconciles_commit_then_successor_assignment() -> None:
    _backend, client = _s3_backend()
    primary = ABTestStore(
        "/virtual/primary",
        tenant_id="tenant_a",
        backend=_s3_backend(client)[0],
    )
    successor = ABTestStore(
        "/virtual/successor",
        tenant_id="tenant_a",
        backend=_s3_backend(client)[0],
    )
    primary._lock = nullcontext()
    successor._lock = nullcontext()
    primary.create_test("proposal_kr", "hint a", "hint b")

    successor_variant: list[str | None] = []
    client.fail_after_next_conditional_write(
        key_suffix="ab_tests.json",
        after_write=lambda: successor_variant.append(
            successor.get_next_variant("proposal_kr")
        ),
    )

    assert primary.get_next_variant("proposal_kr") == "variant_a"
    assert successor_variant == ["variant_b"]
    assert primary.get_active_test("proposal_kr")["generation_count"] == 2


def test_ab_conclusion_reconciles_when_successor_finishes_claim() -> None:
    _backend, client = _s3_backend()
    primary = ABTestStore(
        "/virtual/primary",
        tenant_id="tenant_a",
        backend=_s3_backend(client)[0],
    )
    successor = ABTestStore(
        "/virtual/successor",
        tenant_id="tenant_a",
        backend=_s3_backend(client)[0],
    )
    primary._lock = nullcontext()
    successor._lock = nullcontext()
    primary.create_test("proposal_kr", "winner hint", "loser hint", min_samples=1)
    primary.record_result("proposal_kr", "variant_a", 0.9)
    primary.record_result("proposal_kr", "variant_b", 0.2)

    successor_winner: list[str | None] = []
    client.fail_after_next_conditional_write(
        key_suffix="ab_tests.json",
        after_write=lambda: successor_winner.append(
            successor.evaluate_and_conclude("proposal_kr")
        ),
    )

    assert primary.evaluate_and_conclude("proposal_kr") == "variant_a"
    assert successor_winner == ["variant_a"]
    concluded = primary.list_concluded_tests()
    assert len(concluded) == 1
    assert concluded[0]["winner"] == "variant_a"


def test_ab_create_reconciles_commit_then_successor_replacement() -> None:
    _backend, client = _s3_backend()
    primary = ABTestStore(
        "/virtual/primary",
        tenant_id="tenant_a",
        backend=_s3_backend(client)[0],
    )
    successor = ABTestStore(
        "/virtual/successor",
        tenant_id="tenant_a",
        backend=_s3_backend(client)[0],
    )
    primary._lock = nullcontext()
    successor._lock = nullcontext()

    client.fail_after_next_conditional_write(
        key_suffix="ab_tests.json",
        after_write=lambda: successor.create_test(
            "proposal_kr",
            "successor a",
            "successor b",
        ),
    )
    primary.create_test("proposal_kr", "primary a", "primary b")

    current = primary.get_active_test("proposal_kr")
    assert current is not None
    assert current["variant_a_hint"] == "successor a"


def test_ab_delete_preserves_recreated_identity() -> None:
    _backend, client = _s3_backend()
    primary = ABTestStore(
        "/virtual/primary",
        tenant_id="tenant_a",
        backend=_s3_backend(client)[0],
    )
    successor = ABTestStore(
        "/virtual/successor",
        tenant_id="tenant_a",
        backend=_s3_backend(client)[0],
    )
    primary._lock = nullcontext()
    successor._lock = nullcontext()
    primary.create_test("proposal_kr", "old a", "old b")

    client.fail_after_next_conditional_write(
        key_suffix="ab_tests.json",
        after_write=lambda: successor.create_test(
            "proposal_kr",
            "new a",
            "new b",
        ),
    )
    primary.delete_test("proposal_kr")

    recreated = primary.get_active_test("proposal_kr")
    assert recreated is not None
    assert recreated["variant_a_hint"] == "new a"


def test_request_append_reconciles_commit_then_successor_append() -> None:
    _backend, client = _s3_backend()
    primary = RequestPatternStore(
        "/virtual/primary",
        tenant_id="tenant_a",
        backend=_s3_backend(client)[0],
    )
    successor = RequestPatternStore(
        "/virtual/successor",
        tenant_id="tenant_a",
        backend=_s3_backend(client)[0],
    )
    primary._lock = nullcontext()
    successor._lock = nullcontext()

    client.fail_after_next_conditional_write(
        key_suffix="request_patterns.jsonl",
        after_write=lambda: successor.record_request(
            "successor request",
            None,
            False,
        ),
    )
    primary_id = primary.record_request("primary request", None, False)

    records = primary.get_all()
    assert {record["raw_input"] for record in records} == {
        "primary request",
        "successor request",
    }
    assert primary_id in {record["record_id"] for record in records}


def test_request_clear_preserves_successor_append_after_commit() -> None:
    _backend, client = _s3_backend()
    primary = RequestPatternStore(
        "/virtual/primary",
        tenant_id="tenant_a",
        backend=_s3_backend(client)[0],
    )
    successor = RequestPatternStore(
        "/virtual/successor",
        tenant_id="tenant_a",
        backend=_s3_backend(client)[0],
    )
    primary._lock = nullcontext()
    successor._lock = nullcontext()
    primary.record_request("old request one", None, False)
    primary.record_request("old request two", None, False)

    client.fail_after_next_conditional_write(
        key_suffix="request_patterns.jsonl",
        after_write=lambda: successor.record_request(
            "new request",
            None,
            False,
        ),
    )

    assert primary.clear_unmatched() == 2
    assert [record["raw_input"] for record in primary.get_all()] == [
        "new request"
    ]


def test_quality_state_mutations_stop_after_bounded_conflicts(
    tmp_path: Path,
) -> None:
    cases = [
        (
            ABTestStore,
            ABTestStoreError,
            lambda store: store.create_test("proposal_kr", "hint a", "hint b"),
        ),
        (
            PromptOverrideStore,
            PromptOverrideStoreError,
            lambda store: store.save_override(
                "proposal_kr",
                "Use evidence",
                "manual",
            ),
        ),
        (
            RequestPatternStore,
            RequestPatternStoreError,
            lambda store: store.record_request("new request", None, False),
        ),
    ]

    for index, (store_type, error_type, mutate) in enumerate(cases):
        root = tmp_path / str(index)
        backend = _AlwaysConflictingBackend(root)
        store = store_type(root, tenant_id="tenant_a", backend=backend)
        store._lock = nullcontext()

        with pytest.raises(error_type, match="changed too many times"):
            mutate(store)

        assert backend.attempts == 32
        assert not (root / "tenants").exists()


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


def test_ab_reset_reports_conflict_while_conclusion_is_pending(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DECISIONDOC_PROVIDER", "mock")
    monkeypatch.setenv("DECISIONDOC_API_KEY", "quality-api-key")
    monkeypatch.setenv("DECISIONDOC_OPS_KEY", "quality-ops-key")

    from app.main import create_app

    app = create_app()
    store = ABTestStore(
        tmp_path,
        tenant_id="system",
        backend=app.state.state_backend,
    )
    store.create_test("proposal_kr", "winner hint", "loser hint", min_samples=1)
    store.record_result("proposal_kr", "variant_a", 0.9)
    store.record_result("proposal_kr", "variant_b", 0.2)

    def fail_override(*args, **kwargs):
        raise RuntimeError("simulated override outage")

    monkeypatch.setattr(PromptOverrideStore, "save_override", fail_override)
    with pytest.raises(RuntimeError, match="simulated override outage"):
        store.evaluate_and_conclude("proposal_kr")

    client = TestClient(app, raise_server_exceptions=False)
    response = client.post(
        "/ab-tests/proposal_kr/reset",
        headers={
            "X-DecisionDoc-Api-Key": "quality-api-key",
            "X-DecisionDoc-Ops-Key": "quality-ops-key",
        },
    )

    assert response.status_code == 409
    assert response.json()["detail"] == (
        "A/B test conclusion is in progress and cannot be reset"
    )
    assert store.get_active_test("proposal_kr") is not None


def test_ab_factory_type_hints_are_runtime_resolvable() -> None:
    from app.storage.ab_test_conclusion import evaluate_and_conclude
    from app.storage.ab_test_store_factory import get_cached_ab_test_store

    factory_hints = get_type_hints(get_cached_ab_test_store)
    conclusion_hints = get_type_hints(evaluate_and_conclude)
    assert factory_hints["tenant_id"] is str
    assert factory_hints["return"] is ABTestStore
    assert conclusion_hints["store"] is ABTestStore


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
