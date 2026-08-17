from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

import app.storage.generation_export_source_store as source_module
from app.storage.generation_export_source_store import (
    MAX_REFERENCED_SOURCES,
    MAX_REFERENCED_TENANT_BYTES,
    MAX_SOURCE_BYTES,
    SOURCE_TTL_SECONDS,
    GenerationExportSourceConflictError,
    GenerationExportSourceStore,
    GenerationExportSourceUnavailableError,
)
from app.storage.state_backend import LocalStateBackend, S3StateBackend, StateBackendError
from tests.conditional_state_support import MemoryS3Client


def _backend(
    tmp_path: Path,
    backend_kind: str,
    client: MemoryS3Client,
) -> LocalStateBackend | S3StateBackend:
    if backend_kind == "local":
        return LocalStateBackend(tmp_path / "state")
    return S3StateBackend(
        bucket="generation-export-sources",
        prefix="state/",
        s3_client=client,
    )


def _docs(body: str = "rendered source") -> list[dict[str, str]]:
    return [{"doc_type": "adr", "markdown": body}]


@pytest.mark.parametrize("backend_kind", ["local", "s3"])
def test_independent_store_instances_preserve_disjoint_writes(
    tmp_path: Path,
    backend_kind: str,
) -> None:
    client = MemoryS3Client(read_delay=0.001)

    def write(index: int) -> None:
        store = GenerationExportSourceStore(
            backend=_backend(tmp_path, backend_kind, client),
        )
        store.store(
            tenant_id="alpha",
            request_id=f"request-{index:02d}",
            docs=_docs(f"document {index}"),
            title=f"Title {index}",
        )

    with ThreadPoolExecutor(max_workers=12) as executor:
        list(executor.map(write, range(24)))

    reader = GenerationExportSourceStore(backend=_backend(tmp_path, backend_kind, client))
    assert [
        reader.get(tenant_id="alpha", request_id=f"request-{index:02d}")
        for index in range(24)
    ] == [(_docs(f"document {index}"), f"Title {index}") for index in range(24)]


@pytest.mark.parametrize("backend_kind", ["local", "s3"])
def test_store_is_durable_across_independent_instances(
    tmp_path: Path,
    backend_kind: str,
) -> None:
    client = MemoryS3Client()
    first = GenerationExportSourceStore(backend=_backend(tmp_path, backend_kind, client))
    first.store(
        tenant_id="alpha",
        request_id="restart-proof",
        docs=_docs("survives restart"),
        title="Durable source",
    )

    independent = GenerationExportSourceStore(
        backend=_backend(tmp_path, backend_kind, client),
    )
    assert independent.get(tenant_id="alpha", request_id="restart-proof") == (
        _docs("survives restart"),
        "Durable source",
    )


def test_s3_lost_conditional_write_responses_reconcile_exact_source() -> None:
    client = MemoryS3Client()
    backend = S3StateBackend(
        bucket="generation-export-sources",
        prefix="state/",
        s3_client=client,
    )
    store = GenerationExportSourceStore(backend=backend)
    client.fail_after_next_conditional_write(
        key_fragment="generation_export_sources/objects/"
    )
    store.store(
        tenant_id="alpha",
        request_id="lost-object-response",
        docs=_docs("exact source"),
        title="Exact title",
    )
    client.fail_after_next_conditional_write(
        key_fragment="generation_export_sources/index.json"
    )
    store.store(
        tenant_id="alpha",
        request_id="lost-index-response",
        docs=_docs("exact index source"),
        title="Exact index title",
    )
    assert store.get(tenant_id="alpha", request_id="lost-object-response") == (
        _docs("exact source"),
        "Exact title",
    )
    assert store.get(tenant_id="alpha", request_id="lost-index-response") == (
        _docs("exact index source"),
        "Exact index title",
    )


def test_fixed_limits_expiry_and_deterministic_oldest_first_eviction(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert SOURCE_TTL_SECONDS == 60 * 60
    assert MAX_REFERENCED_SOURCES == 500
    assert MAX_SOURCE_BYTES == 8 * 1024 * 1024
    assert MAX_REFERENCED_TENANT_BYTES == 64 * 1024 * 1024
    now = [1000.0]
    backend = LocalStateBackend(tmp_path / "state")
    store = GenerationExportSourceStore(backend=backend, clock=lambda: now[0])

    for index in range(MAX_REFERENCED_SOURCES + 1):
        now[0] += 0.001
        store.store(
            tenant_id="alpha",
            request_id=f"entry-{index:03d}",
            docs=_docs(str(index)),
            title=f"source {index}",
        )
    assert store.get(tenant_id="alpha", request_id="entry-000") is None
    assert store.get(tenant_id="alpha", request_id="entry-001") is not None

    now[0] += SOURCE_TTL_SECONDS
    assert store.get(tenant_id="alpha", request_id="entry-001") is None
    store.store(
        tenant_id="alpha",
        request_id="fresh",
        docs=_docs("fresh"),
        title="fresh",
    )
    index = json.loads(backend.read_text(store.index_path(tenant_id="alpha")) or "{}")
    assert [item["request_id"] for item in index["sources"]] == ["fresh"]

    monkeypatch.setattr(source_module, "MAX_REFERENCED_TENANT_BYTES", 1_300)
    byte_store = GenerationExportSourceStore(
        backend=LocalStateBackend(tmp_path / "byte-state"),
        clock=lambda: now[0],
    )
    for request_id in ("old", "middle", "new"):
        now[0] += 1
        byte_store.store(
            tenant_id="alpha",
            request_id=request_id,
            docs=_docs("x" * 400),
            title=request_id,
        )
    assert byte_store.get(tenant_id="alpha", request_id="old") is None
    assert byte_store.get(tenant_id="alpha", request_id="middle") is not None
    assert byte_store.get(tenant_id="alpha", request_id="new") is not None


def test_source_size_cap_idempotency_and_content_conflict_preserve_original_bytes(
    tmp_path: Path,
) -> None:
    backend = LocalStateBackend(tmp_path / "state")
    store = GenerationExportSourceStore(backend=backend)
    with pytest.raises(GenerationExportSourceUnavailableError):
        store.store(
            tenant_id="alpha",
            request_id="too-large",
            docs=_docs("x" * MAX_SOURCE_BYTES),
            title="large",
        )

    store.store(
        tenant_id="alpha",
        request_id="bound-request",
        docs=_docs("original"),
        title="Original title",
    )
    index_path = store.index_path(tenant_id="alpha")
    original_index = backend.read_text(index_path)
    index = json.loads(original_index or "{}")
    object_path = store.object_path(
        tenant_id="alpha",
        object_sha256=index["sources"][0]["object_sha256"],
    )
    original_object = backend.read_bytes(object_path)

    store.store(
        tenant_id="alpha",
        request_id="bound-request",
        docs=_docs("original"),
        title="Original title",
    )
    assert backend.read_text(index_path) == original_index
    assert backend.read_bytes(object_path) == original_object

    with pytest.raises(GenerationExportSourceConflictError):
        store.store(
            tenant_id="alpha",
            request_id="bound-request",
            docs=_docs("different"),
            title="Original title",
        )
    assert backend.read_text(index_path) == original_index
    assert backend.read_bytes(object_path) == original_object


@pytest.mark.parametrize("backend_kind", ["local", "s3"])
def test_expired_request_id_rebinds_without_rewriting_immutable_objects(
    tmp_path: Path,
    backend_kind: str,
) -> None:
    now = [100.0]
    client = MemoryS3Client()
    backend = _backend(tmp_path, backend_kind, client)
    store = GenerationExportSourceStore(backend=backend, clock=lambda: now[0])
    store.store(
        tenant_id="alpha",
        request_id="reusable-request",
        docs=_docs("original"),
        title="Original title",
    )
    index_path = store.index_path(tenant_id="alpha")
    first_index = json.loads(backend.read_text(index_path) or "{}")
    first_reference = first_index["sources"][0]
    first_path = store.object_path(
        tenant_id="alpha", object_sha256=first_reference["object_sha256"]
    )
    first_object = backend.read_bytes(first_path)

    now[0] += SOURCE_TTL_SECONDS
    store.store(
        tenant_id="alpha",
        request_id="reusable-request",
        docs=_docs("original"),
        title="Original title",
    )
    renewed_index = json.loads(backend.read_text(index_path) or "{}")
    assert renewed_index["sources"] == [
        {
            **first_reference,
            "stored_at_unix_ns": int(now[0] * 1_000_000_000),
        }
    ]
    assert backend.read_bytes(first_path) == first_object
    assert store.get(tenant_id="alpha", request_id="reusable-request") == (
        _docs("original"),
        "Original title",
    )

    now[0] += SOURCE_TTL_SECONDS
    store.store(
        tenant_id="alpha",
        request_id="reusable-request",
        docs=_docs("replacement"),
        title="Replacement title",
    )
    replacement_index = json.loads(backend.read_text(index_path) or "{}")
    replacement_reference = replacement_index["sources"][0]
    replacement_path = store.object_path(
        tenant_id="alpha", object_sha256=replacement_reference["object_sha256"]
    )
    replacement_object = backend.read_bytes(replacement_path)
    assert replacement_reference["object_sha256"] != first_reference["object_sha256"]
    assert backend.read_bytes(first_path) == first_object
    assert store.get(tenant_id="alpha", request_id="reusable-request") == (
        _docs("replacement"),
        "Replacement title",
    )

    replacement_raw_index = backend.read_text(index_path)
    with pytest.raises(GenerationExportSourceConflictError):
        store.store(
            tenant_id="alpha",
            request_id="reusable-request",
            docs=_docs("active conflict"),
            title="Replacement title",
        )
    assert backend.read_text(index_path) == replacement_raw_index
    assert backend.read_bytes(replacement_path) == replacement_object


@pytest.mark.parametrize("backend_kind", ["local", "s3"])
def test_store_uses_one_clock_sample_at_each_exact_ttl_boundary(
    tmp_path: Path,
    backend_kind: str,
) -> None:
    start = 100.0
    exact_expiry = start + SOURCE_TTL_SECONDS
    replacement_expiry = exact_expiry + SOURCE_TTL_SECONDS
    values = iter([start, exact_expiry, replacement_expiry, replacement_expiry])
    samples: list[float] = []

    def stepping_clock() -> float:
        value = next(values)
        samples.append(value)
        return value

    client = MemoryS3Client()
    backend = _backend(tmp_path, backend_kind, client)
    store = GenerationExportSourceStore(backend=backend, clock=stepping_clock)
    store.store(
        tenant_id="alpha",
        request_id="reusable-request",
        docs=_docs("original"),
        title="Original title",
    )
    index_path = store.index_path(tenant_id="alpha")
    first_reference = json.loads(backend.read_text(index_path) or "{}")["sources"][0]
    first_path = store.object_path(
        tenant_id="alpha", object_sha256=first_reference["object_sha256"]
    )
    first_object = backend.read_bytes(first_path)

    store.store(
        tenant_id="alpha",
        request_id="reusable-request",
        docs=_docs("original"),
        title="Original title",
    )
    renewed_reference = json.loads(backend.read_text(index_path) or "{}")["sources"][0]
    assert renewed_reference == {
        **first_reference,
        "stored_at_unix_ns": int(exact_expiry * 1_000_000_000),
    }
    assert backend.read_bytes(first_path) == first_object

    store.store(
        tenant_id="alpha",
        request_id="reusable-request",
        docs=_docs("replacement"),
        title="Replacement title",
    )
    replacement_reference = json.loads(backend.read_text(index_path) or "{}")["sources"][0]
    replacement_path = store.object_path(
        tenant_id="alpha", object_sha256=replacement_reference["object_sha256"]
    )
    replacement_object = backend.read_bytes(replacement_path)
    assert replacement_reference["stored_at_unix_ns"] == int(
        replacement_expiry * 1_000_000_000
    )
    assert backend.read_bytes(first_path) == first_object

    with pytest.raises(GenerationExportSourceConflictError):
        store.store(
            tenant_id="alpha",
            request_id="reusable-request",
            docs=_docs("active drift"),
            title="Replacement title",
        )
    assert samples == [start, exact_expiry, replacement_expiry, replacement_expiry]
    assert backend.read_bytes(replacement_path) == replacement_object


def test_expired_lost_index_write_does_not_reconcile_as_success() -> None:
    now = [100.0]
    client = MemoryS3Client()
    backend = S3StateBackend(
        bucket="generation-export-sources",
        prefix="state/",
        s3_client=client,
    )
    store = GenerationExportSourceStore(backend=backend, clock=lambda: now[0])
    store.store(
        tenant_id="alpha",
        request_id="expired-request",
        docs=_docs("original"),
        title="Original title",
    )
    index_path = store.index_path(tenant_id="alpha")
    original_index = backend.read_text(index_path)
    original_reference = json.loads(original_index or "{}")["sources"][0]
    original_path = store.object_path(
        tenant_id="alpha", object_sha256=original_reference["object_sha256"]
    )
    original_object = backend.read_bytes(original_path)

    values = iter(
        [
            now[0] + SOURCE_TTL_SECONDS,
            now[0] + SOURCE_TTL_SECONDS - 1,
            now[0] + SOURCE_TTL_SECONDS - 1,
        ]
    )
    samples: list[float] = []

    def stepping_clock() -> float:
        value = next(values)
        samples.append(value)
        return value

    retrying_store = GenerationExportSourceStore(backend=backend, clock=stepping_clock)
    client.fail_before_next_write(key_fragment="generation_export_sources/index.json")
    with pytest.raises(GenerationExportSourceUnavailableError):
        retrying_store.store(
            tenant_id="alpha",
            request_id="expired-request",
            docs=_docs("original"),
            title="Original title",
        )

    assert samples == [now[0] + SOURCE_TTL_SECONDS]
    assert backend.read_text(index_path) == original_index
    assert backend.read_bytes(original_path) == original_object
    assert (
        GenerationExportSourceStore(
            backend=backend,
            clock=lambda: now[0] + SOURCE_TTL_SECONDS,
        ).get(tenant_id="alpha", request_id="expired-request")
        is None
    )


def test_missing_expired_and_foreign_sources_are_indistinguishable(
    tmp_path: Path,
) -> None:
    now = [100.0]
    store = GenerationExportSourceStore(
        backend=LocalStateBackend(tmp_path / "state"),
        clock=lambda: now[0],
    )
    store.store(
        tenant_id="alpha",
        request_id="same-request",
        docs=_docs(),
        title="Private title",
    )
    assert store.get(tenant_id="alpha", request_id="missing") is None
    assert store.get(tenant_id="beta", request_id="same-request") is None
    now[0] += SOURCE_TTL_SECONDS
    assert store.get(tenant_id="alpha", request_id="same-request") is None


@pytest.mark.parametrize("mutation", ["corrupt-index", "missing-object", "tampered-object"])
def test_corruption_and_missing_or_tampered_objects_fail_closed_without_rewrite(
    tmp_path: Path,
    mutation: str,
) -> None:
    backend = LocalStateBackend(tmp_path / "state")
    store = GenerationExportSourceStore(backend=backend)
    store.store(
        tenant_id="alpha",
        request_id="source",
        docs=_docs("secret rendered body"),
        title="secret title",
    )
    index_path = store.index_path(tenant_id="alpha")
    index_raw = backend.read_text(index_path) or ""
    digest = json.loads(index_raw)["sources"][0]["object_sha256"]
    object_path = store.object_path(tenant_id="alpha", object_sha256=digest)

    if mutation == "corrupt-index":
        backend.write_text(index_path, "{not-json")
        original = backend.read_text(index_path)
    elif mutation == "missing-object":
        backend.delete(object_path)
        original = backend.read_text(index_path)
    else:
        backend.write_bytes(object_path, b'{"tampered":true}')
        original = backend.read_bytes(object_path)

    with pytest.raises(GenerationExportSourceUnavailableError):
        store.get(tenant_id="alpha", request_id="source")

    if mutation == "corrupt-index":
        assert backend.read_text(index_path) == original
    elif mutation == "missing-object":
        assert backend.read_text(index_path) == original
        assert backend.read_bytes(object_path) is None
    else:
        assert backend.read_bytes(object_path) == original


def test_backend_unavailability_is_normalized_without_source_details(tmp_path: Path) -> None:
    class UnavailableBackend(LocalStateBackend):
        def read_text(self, relative_path: str) -> str | None:
            raise StateBackendError("backend endpoint and secret title are unavailable")

    store = GenerationExportSourceStore(backend=UnavailableBackend(tmp_path / "state"))
    with pytest.raises(GenerationExportSourceUnavailableError) as exc_info:
        store.get(tenant_id="alpha", request_id="source")
    assert "secret title" not in str(exc_info.value)
