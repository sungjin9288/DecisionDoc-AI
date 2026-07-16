from __future__ import annotations

import asyncio
import ast
import hashlib
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.storage.finetune_store import (
    FineTuneStore,
    FineTuneStoreError,
    get_finetune_store,
)
from app.storage.model_registry import (
    ModelRegistry,
    ModelRegistryError,
    clear_model_registry_cache,
    get_model_registry,
)
from app.storage.state_backend import S3StateBackend


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

    def get_object(self, *, Bucket: str, Key: str) -> dict[str, _Body]:
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


def _messages(marker: str = "sample") -> list[dict[str, str]]:
    return [
        {"role": "system", "content": "Write a decision document."},
        {"role": "user", "content": f"Input {marker}"},
        {"role": "assistant", "content": f"Output {marker}"},
    ]


def _metadata(marker: str = "sample") -> dict[str, Any]:
    return {
        "request_id": f"request-{marker}",
        "bundle_id": "tech_decision",
        "heuristic_score": 0.8,
        "llm_score": None,
        "user_rating": None,
        "source": "high_eval_score",
    }


def _register(registry: ModelRegistry, marker: str = "sample") -> dict[str, Any]:
    return registry.register_model(
        model_id=f"ft:model:{marker}",
        base_model="base-model",
        bundle_id="tech_decision",
        training_file_id=f"file-{marker}",
        record_count=10,
        avg_score_before=0.7,
        openai_job_id=f"job-{marker}",
    )


def _client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DECISIONDOC_PROVIDER", "mock")
    monkeypatch.setenv("DECISIONDOC_ENV", "dev")
    monkeypatch.setenv("DECISIONDOC_OPS_KEY", "ops-secret")
    monkeypatch.setenv("JWT_SECRET_KEY", "finetune-integrity-test-secret")
    monkeypatch.delenv("DECISIONDOC_API_KEY", raising=False)
    monkeypatch.delenv("DECISIONDOC_API_KEYS", raising=False)
    from app.main import create_app

    return TestClient(create_app(), raise_server_exceptions=False)


def _run_async(coroutine: Any) -> Any:
    """Run a coroutine in an isolated thread even if the suite leaked a loop."""
    result: list[Any] = []
    errors: list[BaseException] = []

    def _target() -> None:
        try:
            result.append(asyncio.run(coroutine))
        except BaseException as exc:
            errors.append(exc)

    thread = threading.Thread(target=_target)
    thread.start()
    thread.join()
    if errors:
        raise errors[0]
    return result[0] if result else None


@pytest.mark.parametrize("store_type", [FineTuneStore, ModelRegistry])
@pytest.mark.parametrize(
    "tenant_id",
    [" tenant", "tenant ", ".", "..", "tenant/a", "tenant\\a", "tenant\na"],
)
def test_training_state_rejects_unsafe_tenant_before_access(
    tmp_path: Path,
    store_type: type,
    tenant_id: str,
) -> None:
    with pytest.raises(ValueError, match="Invalid tenant_id"):
        store_type(tmp_path, tenant_id=tenant_id)
    assert not (tmp_path / "tenants").exists()


def test_missing_training_state_reads_have_no_side_effect(tmp_path: Path) -> None:
    fine_tune = FineTuneStore(tmp_path, tenant_id="alpha")
    registry = ModelRegistry(tmp_path, tenant_id="alpha")

    assert fine_tune.get_records() == []
    assert fine_tune.get_stats()["total_records"] == 0
    assert registry.list_models() == []
    assert registry.get_active_model("tech_decision") is None
    assert not (tmp_path / "tenants").exists()


@pytest.mark.parametrize(
    "raw",
    [
        b"{not-json\n",
        (
            b'{"messages":[{"role":"user","content":"x"}],'
            b'"metadata":{"request_id":"one","request_id":"two"}}\n'
        ),
        json.dumps(
            {
                "messages": _messages(),
                "metadata": {
                    **_metadata(),
                    "tenant_id": "alpha",
                    "collected_at": "not-a-timestamp",
                },
            }
        ).encode()
        + b"\n",
    ],
)
def test_finetune_store_fails_closed_and_preserves_corrupt_state(
    tmp_path: Path,
    raw: bytes,
) -> None:
    path = tmp_path / "tenants/alpha/finetune/dataset.jsonl"
    path.parent.mkdir(parents=True)
    path.write_bytes(raw)
    store = FineTuneStore(tmp_path, tenant_id="alpha")

    with pytest.raises(FineTuneStoreError):
        store.get_records()
    with pytest.raises(FineTuneStoreError):
        store.save_record(_messages("new"), _metadata("new"))
    assert path.read_bytes() == raw


@pytest.mark.parametrize(
    "raw",
    [
        b"{not-json",
        b'{"not":"a-list"}',
        json.dumps(
            [
                {
                    "model_id": "ft:model:bad",
                    "base_model": "base-model",
                    "bundle_id": "tech_decision",
                    "tenant_id": "alpha",
                    "status": "ready",
                }
            ]
        ).encode(),
    ],
)
def test_model_registry_fails_closed_and_preserves_corrupt_state(
    tmp_path: Path,
    raw: bytes,
) -> None:
    path = tmp_path / "tenants/alpha/model_registry.json"
    path.parent.mkdir(parents=True)
    path.write_bytes(raw)
    registry = ModelRegistry(tmp_path, tenant_id="alpha")

    with pytest.raises(ModelRegistryError):
        registry.list_models()
    with pytest.raises(ModelRegistryError):
        _register(registry, "new")
    assert path.read_bytes() == raw


def test_finetune_export_detects_tampering_without_overwrite(tmp_path: Path) -> None:
    store = FineTuneStore(tmp_path, tenant_id="alpha")
    store.save_record(_messages(), _metadata())
    export = store.export_for_training(min_records=1)
    assert export is not None
    path = tmp_path / "tenants/alpha/finetune" / export.filename
    tampered = path.read_bytes() + b"{}\n"
    path.write_bytes(tampered)

    with pytest.raises(FineTuneStoreError, match="integrity mismatch"):
        store.get_export_bytes(export.filename)
    assert path.read_bytes() == tampered

    metadata_path = tmp_path / "tenants/alpha/finetune/metadata.json"
    metadata_path.write_bytes(b"{not-json")
    files_before = {item.name for item in metadata_path.parent.iterdir()}
    with pytest.raises(FineTuneStoreError):
        store.save_record(_messages("blocked"), _metadata("blocked"))
    with pytest.raises(FineTuneStoreError):
        store.export_for_training(min_records=1)
    with pytest.raises(FineTuneStoreError):
        store.clear_dataset()
    assert metadata_path.read_bytes() == b"{not-json"
    assert {item.name for item in metadata_path.parent.iterdir()} == files_before


def test_training_state_round_trips_through_fake_s3() -> None:
    backend, client = _s3_backend()
    fine_tune = FineTuneStore("/virtual/one", tenant_id="alpha", backend=backend)
    registry = ModelRegistry("/virtual/one", tenant_id="alpha", backend=backend)

    fine_tune.save_record(_messages(), _metadata())
    export = fine_tune.export_for_training(min_records=1)
    assert export is not None
    raw = FineTuneStore(
        "/virtual/two", tenant_id="alpha", backend=backend
    ).get_export_bytes(export.filename)
    assert raw is not None
    assert hashlib.sha256(raw).hexdigest() == export.sha256

    model = _register(registry)
    registry.update_status(model["openai_job_id"], "ready")
    active = ModelRegistry(
        "/virtual/two", tenant_id="alpha", backend=backend
    ).get_active_model("tech_decision")
    assert active is not None
    assert active["model_id"] == model["model_id"]
    assert not Path("/virtual/one/tenants").exists()
    assert {key for bucket, key in client.objects if bucket == "unit-bucket"} == {
        "decisiondoc-ai/state/tenants/alpha/finetune/dataset.jsonl",
        "decisiondoc-ai/state/tenants/alpha/finetune/metadata.json",
        f"decisiondoc-ai/state/tenants/alpha/finetune/{export.filename}",
        "decisiondoc-ai/state/tenants/alpha/model_registry.json",
    }


def test_independent_fake_s3_training_stores_preserve_concurrent_writes() -> None:
    backend, _ = _s3_backend(read_delay=0.002)
    fine_tune_stores = [
        FineTuneStore("/virtual/data", tenant_id="alpha", backend=backend)
        for _ in range(20)
    ]
    registries = [
        ModelRegistry("/virtual/data", tenant_id="alpha", backend=backend)
        for _ in range(20)
    ]

    with ThreadPoolExecutor(max_workers=20) as executor:
        list(
            executor.map(
                lambda item: item[1].save_record(
                    _messages(str(item[0])),
                    _metadata(str(item[0])),
                ),
                enumerate(fine_tune_stores),
            )
        )
        list(
            executor.map(
                lambda item: _register(item[1], str(item[0])),
                enumerate(registries),
            )
        )

    assert len(fine_tune_stores[0].get_records()) == 20
    assert len(registries[0].list_models()) == 20


def test_training_state_factories_are_scoped_by_root_and_backend(
    tmp_path: Path,
) -> None:
    first_root = tmp_path / "first"
    second_root = tmp_path / "second"
    backend, _ = _s3_backend()
    for factory in (get_finetune_store, get_model_registry):
        first = factory("alpha", data_dir=first_root)
        same = factory("alpha", data_dir=first_root)
        second = factory("alpha", data_dir=second_root)
        remote = factory("alpha", data_dir=first_root, backend=backend)

        assert first is same
        assert first is not second
        assert first is not remote


def test_finetune_and_model_routes_use_application_s3_backend(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _client(tmp_path, monkeypatch)
    backend, s3_client = _s3_backend()
    client.app.state.state_backend = backend
    fine_tune = FineTuneStore(tmp_path, tenant_id="system", backend=backend)
    fine_tune.save_record(_messages(), _metadata())

    stats = client.get("/finetune/stats")
    exported = client.post(
        "/finetune/export",
        json={"min_records": 1},
        headers={"X-DecisionDoc-Ops-Key": "ops-secret"},
    )

    assert stats.status_code == 200
    assert stats.json()["total_records"] == 1
    assert exported.status_code == 200
    filename = exported.json()["filename"]
    downloaded = client.get(
        f"/finetune/export/{filename}",
        headers={"X-DecisionDoc-Ops-Key": "ops-secret"},
    )
    assert downloaded.status_code == 200
    assert hashlib.sha256(downloaded.content).hexdigest() == exported.json()["sha256"]

    registry = ModelRegistry(tmp_path, tenant_id="system", backend=backend)
    _register(registry)
    models = client.get("/models")
    assert models.status_code == 200
    assert [model["model_id"] for model in models.json()] == ["ft:model:sample"]
    assert not (tmp_path / "tenants/system/finetune/dataset.jsonl").exists()
    assert not (tmp_path / "tenants/system/model_registry.json").exists()
    assert any("/finetune/" in key for _bucket, key in s3_client.objects)


@pytest.mark.parametrize(
    ("relative_path", "url"),
    [
        ("tenants/system/finetune/dataset.jsonl", "/finetune/stats"),
        ("tenants/system/model_registry.json", "/models"),
    ],
)
def test_training_authority_api_preserves_corrupt_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    relative_path: str,
    url: str,
) -> None:
    path = tmp_path / relative_path
    path.parent.mkdir(parents=True)
    path.write_bytes(b"{not-json")
    client = _client(tmp_path, monkeypatch)

    response = client.get(url)

    assert response.status_code == 500
    assert response.json()["code"] == "INTERNAL_ERROR"
    assert path.read_bytes() == b"{not-json"


def test_provider_selection_fails_closed_on_corrupt_registry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "tenants/alpha/model_registry.json"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"{not-json")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DECISIONDOC_PROVIDER", "mock")
    clear_model_registry_cache()
    from app.providers.factory import get_provider_for_bundle

    with pytest.raises(ModelRegistryError):
        get_provider_for_bundle("tech_decision", "alpha")


def test_generation_fails_closed_before_provider_on_corrupt_registry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "tenants/system/model_registry.json"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"{not-json")
    client = _client(tmp_path, monkeypatch)

    response = client.post(
        "/generate",
        json={"title": "Authority check", "goal": "Do not bypass model state"},
    )

    assert response.status_code == 500
    assert response.json()["code"] == "INTERNAL_ERROR"
    assert path.read_bytes() == b"{not-json"


def test_finetune_auto_execution_is_disabled_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.config import is_finetune_auto_enabled
    from app.services.finetune_orchestrator import FineTuneOrchestrator

    monkeypatch.delenv("FINETUNE_AUTO_ENABLED", raising=False)
    assert is_finetune_auto_enabled() is False
    monkeypatch.setenv("FINETUNE_AUTO_ENABLED", "1")
    assert is_finetune_auto_enabled() is True

    monkeypatch.setenv("DECISIONDOC_PROVIDER", "notopenai")
    monkeypatch.setenv("DECISIONDOC_PROVIDER_GENERATION", "mock")
    monkeypatch.setenv("DECISIONDOC_PROVIDER_ATTACHMENT", "mock")
    monkeypatch.setenv("DECISIONDOC_PROVIDER_VISUAL", "mock")
    orchestrator = FineTuneOrchestrator()
    assert orchestrator._is_openai_provider() is False
    monkeypatch.setenv("DECISIONDOC_PROVIDER_GENERATION", "openai")
    assert orchestrator._is_openai_provider() is True


def test_eval_collection_does_not_start_training_without_opt_in(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.eval.eval_store import EvalStore
    from app.eval.pipeline import run_eval_pipeline

    monkeypatch.delenv("FINETUNE_AUTO_ENABLED", raising=False)
    monkeypatch.setenv("FINETUNE_AUTO_THRESHOLD", "1")
    monkeypatch.setenv("FINETUNE_MIN_SCORE", "0")

    def _unexpected_thread(*args: Any, **kwargs: Any) -> threading.Thread:
        _ = args, kwargs
        raise AssertionError("training thread must remain disabled")

    monkeypatch.setattr(threading, "Thread", _unexpected_thread)
    run_eval_pipeline(
        request_id="request-auto-disabled",
        bundle_id="tech_decision",
        docs=[{"doc_type": "adr", "markdown": "# Decision\n\nEvidence."}],
        eval_store=EvalStore(tmp_path, tenant_id="alpha"),
        run_llm_judge=False,
        finetune_store=FineTuneStore(tmp_path, tenant_id="alpha"),
        ft_system_prompt="Write a decision document.",
        ft_output="# Decision\n\nEvidence.",
        tenant_id="alpha",
    )


def test_eval_collection_schedules_training_only_after_opt_in(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.eval.eval_store import EvalStore
    from app.eval.pipeline import run_eval_pipeline

    monkeypatch.setenv("FINETUNE_AUTO_ENABLED", "1")
    monkeypatch.setenv("FINETUNE_AUTO_THRESHOLD", "1")
    monkeypatch.setenv("FINETUNE_MIN_SCORE", "0")
    scheduled: list[tuple[Any, tuple[Any, ...]]] = []

    class _Thread:
        def __init__(
            self,
            *,
            target: Any,
            args: tuple[Any, ...],
            daemon: bool,
            name: str,
        ) -> None:
            assert daemon is True
            assert name.startswith("finetune-")
            self.target = target
            self.args = args

        def start(self) -> None:
            scheduled.append((self.target, self.args))

    monkeypatch.setattr(threading, "Thread", _Thread)
    fine_tune = FineTuneStore(tmp_path, tenant_id="alpha")
    run_eval_pipeline(
        request_id="request-auto-enabled",
        bundle_id="tech_decision",
        docs=[{"doc_type": "adr", "markdown": "# Decision\n\nEvidence."}],
        eval_store=EvalStore(tmp_path, tenant_id="alpha"),
        run_llm_judge=False,
        finetune_store=fine_tune,
        ft_system_prompt="Write a decision document.",
        ft_output="# Decision\n\nEvidence.",
        tenant_id="alpha",
    )

    assert len(scheduled) == 1
    _target, args = scheduled[0]
    assert args == (
        "tech_decision",
        "alpha",
        fine_tune.data_dir,
        fine_tune.backend,
    )


def test_orchestrator_requires_explicit_execution_authority(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services.finetune_orchestrator import FineTuneOrchestrator

    orchestrator = FineTuneOrchestrator(tmp_path)
    monkeypatch.setattr(orchestrator, "_is_openai_provider", lambda: True)
    monkeypatch.setattr(orchestrator, "_get_api_key", lambda: "test-key")

    async def _unexpected_upload(*args: Any, **kwargs: Any) -> str:
        _ = args, kwargs
        raise AssertionError("provider upload must not run")

    monkeypatch.setattr(orchestrator, "_upload_training_file", _unexpected_upload)
    result = _run_async(orchestrator.check_and_trigger("tech_decision", "alpha"))
    assert result is None


def test_mocked_orchestrator_binds_s3_export_and_registry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services.finetune_orchestrator import FineTuneOrchestrator

    backend, _ = _s3_backend()
    store = FineTuneStore("/virtual/data", tenant_id="alpha", backend=backend)
    store.save_record(_messages(), _metadata())
    monkeypatch.setenv("FINETUNE_AUTO_THRESHOLD", "1")
    orchestrator = FineTuneOrchestrator(
        "/virtual/data",
        state_backend=backend,
    )
    monkeypatch.setattr(orchestrator, "_is_openai_provider", lambda: True)
    monkeypatch.setattr(orchestrator, "_get_api_key", lambda: "test-key")

    async def _upload(filename: str, content: bytes, api_key: str) -> str:
        assert filename.endswith(".jsonl")
        assert content
        assert api_key == "test-key"
        return "file-mocked"

    async def _create(
        file_id: str,
        base_model: str,
        bundle_id: str | None,
        api_key: str,
    ) -> str:
        assert (file_id, bundle_id, api_key) == (
            "file-mocked",
            "tech_decision",
            "test-key",
        )
        assert base_model
        return "job-mocked"

    def _discard_poll(coroutine: Any) -> None:
        coroutine.close()

    monkeypatch.setattr(orchestrator, "_upload_training_file", _upload)
    monkeypatch.setattr(orchestrator, "_create_finetune_job", _create)
    monkeypatch.setattr(asyncio, "ensure_future", _discard_poll)

    result = _run_async(
        orchestrator.check_and_trigger(
            "tech_decision",
            "alpha",
            execution_authorized=True,
        )
    )

    assert result is not None
    assert result["openai_job_id"] == "job-mocked"
    registry = ModelRegistry("/other/root", tenant_id="alpha", backend=backend)
    model = registry.get_model_by_job("job-mocked")
    assert model is not None
    assert model["status"] == "training"


def test_polling_keeps_completed_model_inactive_until_evaluation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services.finetune_orchestrator import FineTuneOrchestrator

    backend, _ = _s3_backend()
    registry = ModelRegistry("/virtual/data", tenant_id="alpha", backend=backend)
    registry.register_model(
        model_id="pending:job-eval",
        base_model="base-model",
        bundle_id="tech_decision",
        training_file_id="file-eval",
        record_count=10,
        avg_score_before=0.7,
        openai_job_id="job-eval",
    )
    orchestrator = FineTuneOrchestrator(
        "/virtual/data",
        state_backend=backend,
    )
    orchestrator.POLL_INTERVAL_SECONDS = 0
    orchestrator.MAX_POLL_ATTEMPTS = 1
    monkeypatch.setattr(orchestrator, "_get_api_key", lambda: "test-key")

    async def _status(job_id: str, api_key: str) -> dict[str, str]:
        assert (job_id, api_key) == ("job-eval", "test-key")
        return {"status": "succeeded", "fine_tuned_model": "ft:model:evaluated"}

    observed_statuses: list[str] = []

    async def _evaluate(model_id: str, bundle_id: str, tenant_id: str) -> None:
        current = registry.get_model(model_id)
        assert current is not None
        observed_statuses.append(current["status"])
        assert (bundle_id, tenant_id) == ("tech_decision", "alpha")
        registry.update_status("job-eval", "ready")

    monkeypatch.setattr(orchestrator, "_get_job_status", _status)
    monkeypatch.setattr(orchestrator, "_evaluate_and_promote", _evaluate)

    _run_async(
        orchestrator.poll_job_status(
            "job-eval",
            tenant_id="alpha",
            bundle_id="tech_decision",
        )
    )

    assert observed_statuses == ["training"]
    active = registry.get_active_model("tech_decision")
    assert active is not None
    assert active["model_id"] == "ft:model:evaluated"


def test_registry_rejects_duplicate_model_and_job_authority(tmp_path: Path) -> None:
    registry = ModelRegistry(tmp_path, tenant_id="alpha")
    _register(registry, "first")

    with pytest.raises(ModelRegistryError, match="Model identity"):
        registry.register_model(
            model_id="ft:model:first",
            base_model="base-model",
            bundle_id="tech_decision",
            training_file_id="file-second",
            record_count=10,
            avg_score_before=0.7,
            openai_job_id="job-second",
        )
    with pytest.raises(ModelRegistryError, match="Provider job identity"):
        registry.register_model(
            model_id="ft:model:second",
            base_model="base-model",
            bundle_id="tech_decision",
            training_file_id="file-second",
            record_count=10,
            avg_score_before=0.7,
            openai_job_id="job-first",
        )
    assert len(registry.list_models()) == 1


def test_finetune_requests_reject_unexpected_fields(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _client(tmp_path, monkeypatch)
    headers = {"X-DecisionDoc-Ops-Key": "ops-secret"}

    export = client.post(
        "/finetune/export",
        json={"min_records": 1, "unexpected": True},
        headers=headers,
    )
    training = client.post(
        "/admin/models/trigger-training",
        json={"bundle_id": "tech_decision", "unexpected": True},
        headers=headers,
    )

    assert export.status_code == 422
    assert training.status_code == 422


def test_training_authority_callers_bind_application_backend() -> None:
    required_calls = {
        Path("app/routers/finetune.py"): {"get_finetune_store"},
        Path("app/routers/generate/ops.py"): {"get_finetune_store"},
        Path("app/routers/admin/_models.py"): {"get_model_registry"},
        Path("app/services/generation/service_core_mixin.py"): {"get_finetune_store"},
        Path("app/services/generation/service_provider_mixin.py"): {"get_model_registry"},
        Path("app/services/finetune_orchestrator.py"): {
            "get_finetune_store",
            "get_model_registry",
        },
    }

    for path, names in required_calls.items():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        calls = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in names
        ]
        assert calls, path
        for call in calls:
            keywords = {keyword.arg for keyword in call.keywords}
            assert {"data_dir", "backend"}.issubset(keywords) or any(
                keyword.arg is None for keyword in call.keywords
            ), f"{path}:{call.lineno}"
