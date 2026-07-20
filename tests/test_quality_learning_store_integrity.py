from __future__ import annotations

import ast
import hashlib
import json
import threading
import time
from contextlib import nullcontext
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Callable

import pytest
from fastapi.testclient import TestClient

from app.eval.eval_store import EvalRecord, EvalStore, EvalStoreError, get_eval_store
from app.storage.feedback_store import (
    FeedbackStore,
    FeedbackStoreError,
    get_feedback_store,
)
from app.storage.prompt_override_store import (
    PromptOverrideStore,
    PromptOverrideStoreError,
    get_override_store,
)
from app.storage.state_backend import (
    LocalStateBackend,
    S3StateBackend,
    StateBackendError,
)


_NOW = "2026-07-17T00:00:00+00:00"


class _SlowLocalBackend(LocalStateBackend):
    def read_text(self, relative_path: str) -> str | None:
        raw = super().read_text(relative_path)
        time.sleep(0.003)
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

    def get_object(self, *, Bucket: str, Key: str) -> dict:
        time.sleep(self.read_delay)
        with self._lock:
            data = self.objects.get((Bucket, Key))
        if data is None:
            raise self._error("NoSuchKey")
        return {"Body": _Body(data), "ETag": self._etag(data)}


def _s3_backend(
    *,
    read_delay: float = 0.0,
    client: _MemoryS3Client | None = None,
) -> tuple[S3StateBackend, _MemoryS3Client]:
    selected_client = client or _MemoryS3Client(read_delay=read_delay)
    backend = S3StateBackend(
        bucket="unit-bucket",
        prefix="decisiondoc-ai/state/",
        s3_client=selected_client,
    )
    return backend, selected_client


def _eval_record(marker: str, *, tenant_id: str | None = None) -> EvalRecord:
    return EvalRecord(
        request_id=f"request-{marker}",
        bundle_id="tech_decision",
        timestamp=_NOW,
        heuristic_score=0.8,
        llm_score=None,
        issues=[],
        doc_scores={"adr": 0.8},
        tenant_id=tenant_id,
    )


def _override_record(
    bundle_id: str,
    *,
    tenant_id: str | None = "alpha",
) -> dict:
    record = {
        "bundle_id": bundle_id,
        "override_hint": f"Hint for {bundle_id}",
        "trigger_reason": "manual",
        "created_at": _NOW,
        "applied_count": 0,
        "avg_score_before": 0.5,
    }
    if tenant_id is not None:
        record["tenant_id"] = tenant_id
    return record


def _client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DECISIONDOC_PROVIDER", "mock")
    monkeypatch.setenv("DECISIONDOC_ENV", "dev")
    monkeypatch.setenv("JWT_SECRET_KEY", "quality-integrity-test-secret")
    monkeypatch.delenv("DECISIONDOC_API_KEY", raising=False)
    monkeypatch.delenv("DECISIONDOC_API_KEYS", raising=False)
    from app.main import create_app

    return TestClient(create_app(), raise_server_exceptions=False)


@pytest.mark.parametrize(
    "store_type",
    [FeedbackStore, EvalStore, PromptOverrideStore],
)
@pytest.mark.parametrize(
    "tenant_id",
    [" tenant", "tenant ", ".", "..", "tenant/a", "tenant\\a", "tenant\na"],
)
def test_quality_store_rejects_unsafe_tenant_before_state_access(
    tmp_path: Path,
    store_type: type,
    tenant_id: str,
) -> None:
    with pytest.raises(ValueError, match="Invalid tenant_id"):
        store_type(tmp_path, tenant_id=tenant_id)

    assert not (tmp_path / "tenants").exists()


def test_missing_quality_state_reads_have_no_side_effect(tmp_path: Path) -> None:
    feedback = FeedbackStore(tmp_path, tenant_id="alpha")
    evaluations = EvalStore(tmp_path, tenant_id="alpha")
    overrides = PromptOverrideStore(tmp_path, tenant_id="alpha")

    assert feedback.get_all() == []
    assert evaluations.load_all() == []
    assert overrides.list_overrides() == []
    assert not (tmp_path / "tenants").exists()


@pytest.mark.parametrize(
    ("relative_path", "store", "operation", "error_type", "message"),
    [
        (
            "tenants/alpha/feedback.jsonl",
            lambda root: FeedbackStore(root, tenant_id="alpha"),
            lambda store: store.save({"bundle_type": "tech_decision", "rating": 5}),
            FeedbackStoreError,
            "Invalid feedback state document",
        ),
        (
            "tenants/alpha/eval_results.jsonl",
            lambda root: EvalStore(root, tenant_id="alpha"),
            lambda store: store.append(_eval_record("new")),
            EvalStoreError,
            "Invalid evaluation state document",
        ),
        (
            "tenants/alpha/prompt_overrides.json",
            lambda root: PromptOverrideStore(root, tenant_id="alpha"),
            lambda store: store.save_override("new", "New hint", "manual"),
            PromptOverrideStoreError,
            "Invalid prompt override state document",
        ),
    ],
)
def test_untrusted_quality_state_stops_write_without_replacement(
    tmp_path: Path,
    relative_path: str,
    store,
    operation,
    error_type: type[Exception],
    message: str,
) -> None:
    path = tmp_path / relative_path
    path.parent.mkdir(parents=True)
    path.write_bytes(b"{not-json")

    with pytest.raises(error_type, match=message):
        operation(store(tmp_path))

    assert path.read_bytes() == b"{not-json"


@pytest.mark.parametrize(
    ("relative_path", "store", "operation", "error_type"),
    [
        (
            "tenants/alpha/feedback.jsonl",
            lambda root: FeedbackStore(root, tenant_id="alpha"),
            lambda store: store.get_all(),
            FeedbackStoreError,
        ),
        (
            "tenants/alpha/eval_results.jsonl",
            lambda root: EvalStore(root, tenant_id="alpha"),
            lambda store: store.load_all(),
            EvalStoreError,
        ),
        (
            "tenants/alpha/prompt_overrides.json",
            lambda root: PromptOverrideStore(root, tenant_id="alpha"),
            lambda store: store.list_overrides(),
            PromptOverrideStoreError,
        ),
    ],
)
def test_duplicate_json_keys_are_rejected(
    tmp_path: Path,
    relative_path: str,
    store,
    operation,
    error_type: type[Exception],
) -> None:
    path = tmp_path / relative_path
    path.parent.mkdir(parents=True)
    path.write_text('{"same":1,"same":2}\n', encoding="utf-8")

    with pytest.raises(error_type):
        operation(store(tmp_path))


def test_foreign_quality_records_remain_hidden_and_preserved(tmp_path: Path) -> None:
    feedback_path = tmp_path / "tenants/alpha/feedback.jsonl"
    feedback_path.parent.mkdir(parents=True)
    foreign_feedback = {"tenant_id": "beta", "opaque": {"keep": True}}
    feedback_path.write_text(json.dumps(foreign_feedback) + "\n", encoding="utf-8")
    feedback_store = FeedbackStore(tmp_path, tenant_id="alpha")
    feedback_store.save({"bundle_type": "tech_decision", "rating": 5})
    feedback_records = [
        json.loads(line) for line in feedback_path.read_text().splitlines()
    ]
    assert feedback_store.get_all()[0]["rating"] == 5
    assert feedback_records[0] == foreign_feedback

    eval_path = tmp_path / "tenants/alpha/eval_results.jsonl"
    foreign_eval = {"tenant_id": "beta", "opaque": {"keep": True}}
    eval_path.write_text(json.dumps(foreign_eval) + "\n", encoding="utf-8")
    eval_store = EvalStore(tmp_path, tenant_id="alpha")
    eval_store.append(_eval_record("owned"))
    eval_records = [json.loads(line) for line in eval_path.read_text().splitlines()]
    assert [record.request_id for record in eval_store.load_all()] == ["request-owned"]
    assert eval_records[0] == foreign_eval

    override_path = tmp_path / "tenants/alpha/prompt_overrides.json"
    foreign_override = {"tenant_id": "beta", "opaque": {"keep": True}}
    override_path.write_text(
        json.dumps({"foreign": foreign_override}),
        encoding="utf-8",
    )
    override_store = PromptOverrideStore(tmp_path, tenant_id="alpha")
    override_store.save_override("owned", "Owned hint", "manual")
    assert [item["bundle_id"] for item in override_store.list_overrides()] == ["owned"]
    assert json.loads(override_path.read_text())["foreign"] == foreign_override


def test_tenantless_legacy_quality_records_remain_readable(tmp_path: Path) -> None:
    tenant_dir = tmp_path / "tenants/alpha"
    tenant_dir.mkdir(parents=True)
    tenant_dir.joinpath("feedback.jsonl").write_text(
        json.dumps(
            {
                "feedback_id": "legacy-feedback",
                "timestamp": 1.0,
                "bundle_type": "tech_decision",
                "rating": 4,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    tenant_dir.joinpath("eval_results.jsonl").write_text(
        json.dumps(
            {
                "request_id": "legacy-eval",
                "bundle_id": "tech_decision",
                "timestamp": _NOW,
                "heuristic_score": 0.8,
                "llm_score": None,
                "issues": [],
                "doc_scores": {},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    tenant_dir.joinpath("prompt_overrides.json").write_text(
        json.dumps({"legacy": _override_record("legacy", tenant_id=None)}),
        encoding="utf-8",
    )

    assert (
        FeedbackStore(tmp_path, tenant_id="alpha").get_all()[0]["feedback_id"]
        == "legacy-feedback"
    )
    assert EvalStore(tmp_path, tenant_id="alpha").load_all()[0].request_id == (
        "legacy-eval"
    )
    assert (
        PromptOverrideStore(tmp_path, tenant_id="alpha").get_override("legacy")
        is not None
    )


def test_invalid_caller_state_is_rejected_before_write(tmp_path: Path) -> None:
    feedback = FeedbackStore(tmp_path, tenant_id="alpha")
    with pytest.raises(ValueError, match="Invalid feedback fields"):
        feedback.save({"bundle_type": "tech_decision", "rating": 5, "extra": True})
    assert not feedback._path.exists()

    evaluations = EvalStore(tmp_path, tenant_id="alpha")
    invalid_eval = _eval_record("invalid")
    invalid_eval.timestamp = "not-a-timestamp"
    with pytest.raises(ValueError, match="Invalid evaluation timestamp"):
        evaluations.append(invalid_eval)
    assert not evaluations._path.exists()

    overrides = PromptOverrideStore(tmp_path, tenant_id="alpha")
    with pytest.raises(ValueError, match="Invalid prompt override average score"):
        overrides.save_override("bundle", "Hint", "manual", avg_score_before=2.0)
    assert not overrides._path.exists()


def test_independent_local_quality_stores_preserve_concurrent_writes(
    tmp_path: Path,
) -> None:
    feedback_stores = [
        FeedbackStore(
            tmp_path,
            tenant_id="alpha",
            backend=_SlowLocalBackend(tmp_path),
        )
        for _ in range(20)
    ]
    eval_stores = [
        EvalStore(
            tmp_path,
            tenant_id="alpha",
            backend=_SlowLocalBackend(tmp_path),
        )
        for _ in range(20)
    ]
    override_stores = [
        PromptOverrideStore(
            tmp_path,
            tenant_id="alpha",
            backend=_SlowLocalBackend(tmp_path),
        )
        for _ in range(20)
    ]

    with ThreadPoolExecutor(max_workers=20) as executor:
        list(
            executor.map(
                lambda item: item[1].save(
                    {"bundle_type": f"bundle-{item[0]}", "rating": 5}
                ),
                enumerate(feedback_stores),
            )
        )
        list(
            executor.map(
                lambda item: item[1].append(_eval_record(str(item[0]))),
                enumerate(eval_stores),
            )
        )
        list(
            executor.map(
                lambda item: item[1].save_override(
                    f"bundle-{item[0]}",
                    f"Hint {item[0]}",
                    "manual",
                ),
                enumerate(override_stores),
            )
        )

    assert len(FeedbackStore(tmp_path, tenant_id="alpha").get_all()) == 20
    assert len(EvalStore(tmp_path, tenant_id="alpha").load_all()) == 20
    assert len(PromptOverrideStore(tmp_path, tenant_id="alpha").list_overrides()) == 20


def test_quality_state_round_trips_through_fake_s3() -> None:
    backend, client = _s3_backend()
    feedback = FeedbackStore("/virtual/data", tenant_id="alpha", backend=backend)
    evaluations = EvalStore("/virtual/data", tenant_id="alpha", backend=backend)
    overrides = PromptOverrideStore("/virtual/data", tenant_id="alpha", backend=backend)

    feedback.save({"bundle_type": "tech_decision", "rating": 5})
    evaluations.append(_eval_record("s3"))
    overrides.save_override("tech_decision", "Use evidence", "manual")

    assert (
        len(FeedbackStore("/other/root", tenant_id="alpha", backend=backend).get_all())
        == 1
    )
    assert (
        EvalStore("/other/root", tenant_id="alpha", backend=backend)
        .load_all()[0]
        .request_id
        == "request-s3"
    )
    assert (
        PromptOverrideStore(
            "/other/root", tenant_id="alpha", backend=backend
        ).get_override("tech_decision")["override_hint"]
        == "Use evidence"
    )
    assert {key for bucket, key in client.objects if bucket == "unit-bucket"} == {
        "decisiondoc-ai/state/tenants/alpha/feedback.jsonl",
        "decisiondoc-ai/state/tenants/alpha/eval_results.jsonl",
        "decisiondoc-ai/state/tenants/alpha/prompt_overrides.json",
    }


def test_independent_fake_s3_quality_stores_preserve_concurrent_writes() -> None:
    backend, _ = _s3_backend(read_delay=0.003)
    feedback_stores = [
        FeedbackStore("/virtual/data", tenant_id="alpha", backend=backend)
        for _ in range(20)
    ]
    eval_stores = [
        EvalStore("/virtual/data", tenant_id="alpha", backend=backend)
        for _ in range(20)
    ]
    override_stores = [
        PromptOverrideStore("/virtual/data", tenant_id="alpha", backend=backend)
        for _ in range(20)
    ]

    with ThreadPoolExecutor(max_workers=20) as executor:
        list(
            executor.map(
                lambda item: item[1].save(
                    {"bundle_type": f"bundle-{item[0]}", "rating": 4}
                ),
                enumerate(feedback_stores),
            )
        )
        list(
            executor.map(
                lambda item: item[1].append(_eval_record(str(item[0]))),
                enumerate(eval_stores),
            )
        )
        list(
            executor.map(
                lambda item: item[1].save_override(
                    f"bundle-{item[0]}",
                    f"Hint {item[0]}",
                    "manual",
                ),
                enumerate(override_stores),
            )
        )

    assert len(feedback_stores[0].get_all()) == 20
    assert len(eval_stores[0].load_all()) == 20
    assert len(override_stores[0].list_overrides()) == 20


def test_independent_prompt_override_workers_preserve_updates() -> None:
    client = _MemoryS3Client(read_delay=0.002)
    stores = [
        PromptOverrideStore(
            f"/virtual/worker-{index}",
            tenant_id="alpha",
            backend=_s3_backend(client=client)[0],
        )
        for index in range(20)
    ]
    for store in stores:
        store._lock = nullcontext()

    with ThreadPoolExecutor(max_workers=20) as executor:
        list(
            executor.map(
                lambda item: item[1].save_override(
                    f"bundle-{item[0]}",
                    f"Hint {item[0]}",
                    "manual",
                ),
                enumerate(stores),
            )
        )

    assert len(stores[0].list_overrides()) == 20

    stores[0].save_override("shared", "Shared hint", "manual")
    with ThreadPoolExecutor(max_workers=20) as executor:
        list(
            executor.map(
                lambda store: store.increment_applied("shared"),
                stores,
            )
        )
    assert stores[0].get_override("shared")["applied_count"] == 20


def test_prompt_override_public_records_hide_mutation_metadata(
    tmp_path: Path,
) -> None:
    store = PromptOverrideStore(tmp_path, tenant_id="alpha")
    store.save_override("proposal_kr", "Use evidence", "manual")

    records = [
        store.get_override("proposal_kr"),
        store.list_overrides()[0],
    ]
    assert all(
        not any(field.startswith("_") for field in record)
        for record in records
        if record is not None
    )

    persisted = json.loads(store._path.read_text(encoding="utf-8"))
    assert persisted["proposal_kr"]["_incarnation_id"]
    assert persisted["proposal_kr"]["_mutation_ids"]


def test_prompt_override_save_reconciles_commit_then_increment() -> None:
    client = _MemoryS3Client()
    primary = PromptOverrideStore(
        "/virtual/primary",
        tenant_id="alpha",
        backend=_s3_backend(client=client)[0],
    )
    successor = PromptOverrideStore(
        "/virtual/successor",
        tenant_id="alpha",
        backend=_s3_backend(client=client)[0],
    )
    primary._lock = nullcontext()
    successor._lock = nullcontext()

    client.fail_after_next_conditional_write(
        key_suffix="prompt_overrides.json",
        after_write=lambda: successor.increment_applied("proposal_kr"),
    )
    primary.save_override("proposal_kr", "Use evidence", "manual")

    record = primary.get_override("proposal_kr")
    assert record is not None
    assert record["override_hint"] == "Use evidence"
    assert record["applied_count"] == 1


def test_prompt_override_increment_reconciles_successor_increment() -> None:
    client = _MemoryS3Client()
    primary = PromptOverrideStore(
        "/virtual/primary",
        tenant_id="alpha",
        backend=_s3_backend(client=client)[0],
    )
    successor = PromptOverrideStore(
        "/virtual/successor",
        tenant_id="alpha",
        backend=_s3_backend(client=client)[0],
    )
    primary._lock = nullcontext()
    successor._lock = nullcontext()
    primary.save_override("proposal_kr", "Use evidence", "manual")

    client.fail_after_next_conditional_write(
        key_suffix="prompt_overrides.json",
        after_write=lambda: successor.increment_applied("proposal_kr"),
    )
    primary.increment_applied("proposal_kr")

    assert primary.get_override("proposal_kr")["applied_count"] == 2


@pytest.mark.parametrize("legacy", [False, True])
def test_prompt_override_increment_survives_concurrent_refresh(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    legacy: bool,
) -> None:
    backend = LocalStateBackend(tmp_path)
    primary = PromptOverrideStore(
        tmp_path,
        tenant_id="alpha",
        backend=backend,
    )
    successor = PromptOverrideStore(
        tmp_path,
        tenant_id="alpha",
        backend=backend,
    )
    primary._lock = nullcontext()
    successor._lock = nullcontext()
    if legacy:
        path = tmp_path / "tenants" / "alpha" / "prompt_overrides.json"
        path.parent.mkdir(parents=True)
        path.write_text(
            json.dumps({"proposal_kr": _override_record("proposal_kr")}),
            encoding="utf-8",
        )
    else:
        primary.save_override("proposal_kr", "Old hint", "manual")

    original_replace = backend.replace_text_if_equal

    def replace_after_refresh(*args, **kwargs):
        monkeypatch.setattr(backend, "replace_text_if_equal", original_replace)
        successor.save_override("proposal_kr", "New hint", "manual")
        return original_replace(*args, **kwargs)

    monkeypatch.setattr(backend, "replace_text_if_equal", replace_after_refresh)
    primary.increment_applied("proposal_kr")

    record = primary.get_override("proposal_kr")
    assert record is not None
    assert record["override_hint"] == "New hint"
    assert record["applied_count"] == 1


def test_prompt_override_legacy_delete_does_not_mask_failed_write(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backend = LocalStateBackend(tmp_path)
    store = PromptOverrideStore(
        tmp_path,
        tenant_id="alpha",
        backend=backend,
    )
    path = tmp_path / "tenants" / "alpha" / "prompt_overrides.json"
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps({"proposal_kr": _override_record("proposal_kr")}),
        encoding="utf-8",
    )

    def fail_before_write(*args, **kwargs):
        raise StateBackendError("simulated failed write")

    monkeypatch.setattr(backend, "replace_text_if_equal", fail_before_write)

    with pytest.raises(
        PromptOverrideStoreError,
        match="could not be written",
    ):
        store.delete_override("proposal_kr")

    assert store.get_override("proposal_kr") is not None


def test_prompt_override_operation_identity_is_bound_to_payload(
    tmp_path: Path,
) -> None:
    store = PromptOverrideStore(tmp_path, tenant_id="alpha")
    store.save_override(
        "proposal_kr",
        "Use evidence",
        "ab_test_winner",
        operation_id="winner-operation",
    )
    store.save_override(
        "proposal_kr",
        "Use evidence",
        "ab_test_winner",
        operation_id="winner-operation",
    )
    store.save_override(
        "proposal_kr",
        "Newer operator hint",
        "manual",
        operation_id="operator-operation",
    )
    store.save_override(
        "proposal_kr",
        "Use evidence",
        "ab_test_winner",
        operation_id="winner-operation",
    )
    assert store.get_override("proposal_kr")["override_hint"] == (
        "Newer operator hint"
    )

    with pytest.raises(
        PromptOverrideStoreError,
        match="reused with a different payload",
    ):
        store.save_override(
            "proposal_kr",
            "Ignore evidence",
            "ab_test_winner",
            operation_id="winner-operation",
        )


def test_prompt_override_delete_preserves_recreated_identity() -> None:
    client = _MemoryS3Client()
    primary = PromptOverrideStore(
        "/virtual/primary",
        tenant_id="alpha",
        backend=_s3_backend(client=client)[0],
    )
    successor = PromptOverrideStore(
        "/virtual/successor",
        tenant_id="alpha",
        backend=_s3_backend(client=client)[0],
    )
    primary._lock = nullcontext()
    successor._lock = nullcontext()
    primary.save_override("proposal_kr", "Old hint", "manual")

    client.fail_after_next_conditional_write(
        key_suffix="prompt_overrides.json",
        after_write=lambda: successor.save_override(
            "proposal_kr",
            "New hint",
            "manual",
        ),
    )
    primary.delete_override("proposal_kr")

    recreated = primary.get_override("proposal_kr")
    assert recreated is not None
    assert recreated["override_hint"] == "New hint"


def test_quality_store_factories_are_scoped_by_root_and_backend(
    tmp_path: Path,
) -> None:
    first_root = tmp_path / "first"
    second_root = tmp_path / "second"
    for factory in (get_feedback_store, get_eval_store, get_override_store):
        first = factory("alpha", data_dir=first_root)
        same = factory("alpha", data_dir=first_root)
        second = factory("alpha", data_dir=second_root)
        backend, _ = _s3_backend()
        remote = factory("alpha", data_dir=first_root, backend=backend)

        assert first is same
        assert first is not second
        assert first is not remote


def test_quality_routes_pass_application_state_backend() -> None:
    paths = [
        Path("app/routers/generate/ops.py"),
        Path("app/routers/eval.py"),
        Path("app/routers/dashboard.py"),
        Path("app/routers/admin/_bundles.py"),
        Path("app/routers/admin/_tenants.py"),
        Path("app/routers/admin/_locations.py"),
    ]
    factories = {"get_feedback_store", "get_eval_store", "get_override_store"}
    calls = []
    for path in paths:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        calls.extend(
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in factories
        )

    assert calls
    for call in calls:
        keyword_names = {keyword.arg for keyword in call.keywords}
        assert {"data_dir", "backend"}.issubset(keyword_names) or any(
            keyword.arg is None for keyword in call.keywords
        )


def test_feedback_api_uses_application_state_s3_backend(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _client(tmp_path, monkeypatch)
    backend, s3_client = _s3_backend()
    client.app.state.state_backend = backend

    response = client.post(
        "/feedback",
        json={
            "bundle_id": "bundle-1",
            "bundle_type": "tech_decision",
            "rating": 5,
            "comment": "Useful",
        },
    )

    assert response.status_code == 200
    key = (
        "unit-bucket",
        "decisiondoc-ai/state/tenants/system/feedback.jsonl",
    )
    assert key in s3_client.objects
    assert not (tmp_path / "tenants/system/feedback.jsonl").exists()


@pytest.mark.parametrize(
    ("relative_path", "method", "url", "body"),
    [
        (
            "tenants/system/feedback.jsonl",
            "post",
            "/feedback",
            {
                "bundle_id": "bundle-1",
                "bundle_type": "tech_decision",
                "rating": 5,
            },
        ),
        ("tenants/system/eval_results.jsonl", "get", "/dashboard/overview", None),
        (
            "tenants/system/prompt_overrides.json",
            "get",
            "/dashboard/improvement-history",
            None,
        ),
    ],
)
def test_quality_api_preserves_corrupt_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    relative_path: str,
    method: str,
    url: str,
    body: dict | None,
) -> None:
    path = tmp_path / relative_path
    path.parent.mkdir(parents=True)
    path.write_bytes(b"{not-json")
    client = _client(tmp_path, monkeypatch)

    response = client.request(method, url, json=body)

    assert response.status_code == 500
    assert response.json()["code"] == "INTERNAL_ERROR"
    assert path.read_bytes() == b"{not-json"


@pytest.mark.parametrize(
    ("relative_path", "error_type", "message"),
    [
        (
            "tenants/alpha/prompt_overrides.json",
            PromptOverrideStoreError,
            "Invalid prompt override state document",
        ),
        (
            "tenants/alpha/eval_results.jsonl",
            EvalStoreError,
            "Invalid evaluation state document",
        ),
    ],
)
def test_prompt_build_does_not_silently_omit_corrupt_quality_state(
    tmp_path: Path,
    relative_path: str,
    error_type: type[Exception],
    message: str,
) -> None:
    path = tmp_path / relative_path
    path.parent.mkdir(parents=True)
    path.write_bytes(b"{not-json")
    from app.bundle_catalog.registry import get_bundle_spec
    from app.domain.schema import (
        _current_generation_data_dir,
        _current_generation_state_backend,
        _current_tenant_id,
        build_bundle_prompt,
    )

    _current_tenant_id.value = "alpha"
    _current_generation_data_dir.value = tmp_path
    _current_generation_state_backend.value = LocalStateBackend(tmp_path)
    try:
        with pytest.raises(error_type, match=message):
            build_bundle_prompt(
                {"title": "Quality integrity"},
                "v1",
                get_bundle_spec("tech_decision"),
            )
    finally:
        for context in (
            _current_tenant_id,
            _current_generation_data_dir,
            _current_generation_state_backend,
        ):
            if hasattr(context, "value"):
                del context.value

    assert path.read_bytes() == b"{not-json"


def test_generation_feedback_context_does_not_silently_omit_corrupt_state(
    tmp_path: Path,
) -> None:
    path = tmp_path / "tenants/alpha/feedback.jsonl"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"{not-json")
    from app.services.generation.service_context_injection_mixin import (
        GenerationContextInjectionMixin,
    )

    service = GenerationContextInjectionMixin()
    service.data_dir = tmp_path
    service.state_backend = LocalStateBackend(tmp_path)

    with pytest.raises(FeedbackStoreError, match="Invalid feedback state document"):
        service._build_feedback_hints("tech_decision", tenant_id="alpha")

    assert path.read_bytes() == b"{not-json"
