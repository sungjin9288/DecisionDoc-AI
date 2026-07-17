from __future__ import annotations

import ast
import asyncio
import hashlib
import json
import threading
import time
from contextlib import nullcontext
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable
from unittest.mock import MagicMock

import httpx
import pytest
from fastapi.testclient import TestClient
from starlette.requests import Request

from app.services.auth_service import create_access_token
from app.middleware.billing import _acquire_thread_lock, is_metered_endpoint
from app.services.attachment_service import extract_multiple
from app.services.meeting_recording_service import (
    MeetingRecordingService,
    TRANSCRIPTION_FAILED_MESSAGE,
)
from app.storage.billing_store import PREDEFINED_PLANS
from app.storage.state_backend import LocalStateBackend, S3StateBackend, StateBackendError
from app.storage.usage_store import UsageEvent, UsageStore, UsageStoreError
from tests.async_helper import run_async


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
        self._failed_key_suffix: str | None = None

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
        key_suffix: str | None = None,
    ) -> None:
        self._fail_after_conditional_write = True
        self._after_failed_conditional_write = after_write
        self._failed_key_suffix = key_suffix

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
                and (
                    self._failed_key_suffix is None
                    or Key.endswith(self._failed_key_suffix)
                )
            )
            if fail_after_write:
                self._fail_after_conditional_write = False
                after_failed_write = self._after_failed_conditional_write
                self._after_failed_conditional_write = None
                self._failed_key_suffix = None
            else:
                after_failed_write = None

        if not fail_after_write:
            return
        if after_failed_write is not None:
            after_failed_write()
        raise self._error("InternalError")

    def get_object(self, *, Bucket: str, Key: str) -> dict[str, _Body]:
        time.sleep(self.read_delay)
        with self._lock:
            data = self.objects.get((Bucket, Key))
        if data is None:
            raise self._error("NoSuchKey")
        return {"Body": _Body(data), "ETag": self._etag(data)}


class _FailingSummaryBackend(LocalStateBackend):
    def write_text_if_absent(
        self,
        relative_path: str,
        text: str,
        *,
        content_type: str = "application/json; charset=utf-8",
    ) -> bool:
        if relative_path.endswith("usage_summary.json"):
            raise StateBackendError("simulated summary write failure")
        return super().write_text_if_absent(
            relative_path,
            text,
            content_type=content_type,
        )

    def replace_text_if_equal(
        self,
        relative_path: str,
        *,
        expected: str,
        replacement: str,
        content_type: str = "application/json; charset=utf-8",
    ) -> bool:
        if relative_path.endswith("usage_summary.json"):
            raise StateBackendError("simulated summary write failure")
        return super().replace_text_if_equal(
            relative_path,
            expected=expected,
            replacement=replacement,
            content_type=content_type,
        )


class _ConflictingEventBackend(LocalStateBackend):
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
        _ = text, content_type
        if relative_path.endswith("usage.jsonl"):
            self.attempts += 1
            return False
        return super().write_text_if_absent(
            relative_path,
            text,
            content_type=content_type,
        )


class _ConflictingSummaryBackend(LocalStateBackend):
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
        if relative_path.endswith("usage_summary.json"):
            self.attempts += 1
            return False
        return super().write_text_if_absent(
            relative_path,
            text,
            content_type=content_type,
        )


class _FailingEventBackend(LocalStateBackend):
    def write_text_if_absent(
        self,
        relative_path: str,
        text: str,
        *,
        content_type: str = "application/json; charset=utf-8",
    ) -> bool:
        _ = text, content_type
        if relative_path.endswith("usage.jsonl"):
            raise StateBackendError("simulated event write failure")
        return super().write_text_if_absent(
            relative_path,
            text,
            content_type=content_type,
        )


class _UsageReportingAttachmentProvider:
    name = "usage-reporting-attachment"

    def __init__(self) -> None:
        self.calls = 0
        self.pending_usage: dict[str, int] | None = None

    def extract_attachment_text(
        self,
        filename: str,
        raw: bytes,
        *,
        request_id: str,
    ) -> str:
        _ = raw, request_id
        self.calls += 1
        self.pending_usage = {
            "prompt_tokens": self.calls,
            "output_tokens": self.calls + 1,
            "total_tokens": (self.calls * 2) + 1,
        }
        return f"provider text for {filename}"

    def consume_usage_tokens(self) -> dict[str, int] | None:
        usage = self.pending_usage
        self.pending_usage = None
        return usage


class _FailingUsageAttachmentProvider(_UsageReportingAttachmentProvider):
    name = "failing-usage-attachment"

    def extract_attachment_text(
        self,
        filename: str,
        raw: bytes,
        *,
        request_id: str,
    ) -> str:
        super().extract_attachment_text(
            filename,
            raw,
            request_id=request_id,
        )
        raise RuntimeError("provider response parsing failed")


class _SensitiveFailingProvider:
    name = "sensitive-failure"

    def __init__(self) -> None:
        self.pending_usage: dict[str, int] | None = None

    def generate_raw(
        self,
        prompt: str,
        *,
        request_id: str,
        max_output_tokens: int | None = None,
    ) -> str:
        _ = prompt, request_id, max_output_tokens
        self.pending_usage = {
            "prompt_tokens": 7,
            "output_tokens": 4,
            "total_tokens": 11,
        }
        raise RuntimeError(
            "upstream http://127.0.0.1:11434 returned secret response body"
        )

    def consume_usage_tokens(self) -> dict[str, int] | None:
        usage = self.pending_usage
        self.pending_usage = None
        return usage


class _BrokenBundleProvider:
    name = "broken-bundle"

    def __init__(self) -> None:
        self.pending_usage: dict[str, int] | None = None

    def generate_bundle(self, *args, **kwargs):
        _ = args, kwargs
        self.pending_usage = {
            "prompt_tokens": 5,
            "output_tokens": 3,
            "total_tokens": 8,
        }
        return "not-a-bundle"

    def consume_usage_tokens(self) -> dict[str, int] | None:
        usage = self.pending_usage
        self.pending_usage = None
        return usage


class _RetryUsageProvider:
    def __init__(self) -> None:
        self.calls = 0
        self.pending_usage: dict[str, int] | None = None

    def generate_bundle(self, *args, **kwargs):
        _ = args, kwargs
        self.calls += 1
        self.pending_usage = {
            "prompt_tokens": self.calls,
            "output_tokens": self.calls + 1,
        }
        if self.calls == 1:
            raise RuntimeError("retry this attempt")
        return {"result": "ok"}

    def consume_usage_tokens(self) -> dict[str, int] | None:
        usage = self.pending_usage
        self.pending_usage = None
        return usage


def _s3_backend(
    *,
    client: _MemoryS3Client | None = None,
    read_delay: float = 0.0,
) -> tuple[S3StateBackend, _MemoryS3Client]:
    selected_client = client or _MemoryS3Client(read_delay=read_delay)
    backend = S3StateBackend(
        bucket="unit-bucket",
        prefix="decisiondoc-ai/state/",
        s3_client=selected_client,
    )
    return backend, selected_client


def _event(
    marker: str = "sample",
    *,
    tenant_id: str = "alpha",
    timestamp: str | None = None,
) -> UsageEvent:
    return UsageEvent(
        event_id=f"event-{marker}",
        tenant_id=tenant_id,
        user_id="user-1",
        timestamp=timestamp or datetime.now(timezone.utc).isoformat(),
        event_type="doc.generate",
        bundle_id="tech_decision",
        tokens_input=2,
        tokens_output=3,
        tokens_total=5,
        cost_usd=0.001,
        model="mock",
        request_id=f"request-{marker}",
    )


def _client(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    backend: S3StateBackend | None = None,
) -> TestClient:
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DECISIONDOC_PROVIDER", "mock")
    monkeypatch.setenv("DECISIONDOC_PROVIDER_GENERATION", "mock")
    monkeypatch.setenv("DECISIONDOC_PROVIDER_ATTACHMENT", "mock")
    monkeypatch.setenv("DECISIONDOC_PROVIDER_VISUAL", "mock")
    monkeypatch.setenv("DECISIONDOC_ENV", "dev")
    monkeypatch.setenv(
        "JWT_SECRET_KEY",
        "usage-integrity-test-secret-at-least-32-bytes",
    )
    monkeypatch.delenv("DECISIONDOC_API_KEY", raising=False)
    monkeypatch.delenv("DECISIONDOC_API_KEYS", raising=False)

    import app.main as main_module

    if backend is not None:
        monkeypatch.setattr(
            main_module,
            "get_state_backend",
            lambda *, data_dir: backend,
        )
    return TestClient(main_module.create_app(), raise_server_exceptions=False)


def _headers() -> dict[str, str]:
    token = create_access_token(
        user_id="usage-admin",
        tenant_id="system",
        role="admin",
        username="usage-admin",
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.parametrize(
    "tenant_id",
    [" tenant", "tenant ", ".", "..", "tenant/a", "tenant\\a", "tenant\na"],
)
def test_usage_store_rejects_unsafe_tenant_before_state_access(
    tmp_path: Path,
    tenant_id: str,
) -> None:
    with pytest.raises(ValueError, match="Invalid tenant_id"):
        UsageStore(tmp_path, tenant_id=tenant_id)
    assert not (tmp_path / "tenants").exists()


def test_missing_usage_state_reads_have_no_side_effect(tmp_path: Path) -> None:
    store = UsageStore(tmp_path, tenant_id="alpha")

    assert store.get_current_month() is None
    assert store.get_daily_usage() == []
    assert store.check_limit(PREDEFINED_PLANS["free"])["generations_used"] == 0
    assert not (tmp_path / "tenants").exists()


@pytest.mark.parametrize(
    "raw",
    [
        b"{not-json\n",
        b"\xff\xfeinvalid-utf8",
        b"\n",
        (
            b'{"event_id":"one","event_id":"two",'
            b'"tenant_id":"alpha"}\n'
        ),
        json.dumps(
            {
                **_event().__dict__,
                "tokens_total": 999,
            }
        ).encode()
        + b"\n",
        json.dumps(
            {
                **_event().__dict__,
                "timestamp": "20260717T120000+00:00",
            }
        ).encode()
        + b"\n",
        (
            json.dumps(_event("duplicate").__dict__)
            + "\n"
            + json.dumps(_event("duplicate").__dict__)
            + "\n"
        ).encode(),
    ],
)
def test_usage_event_corruption_fails_closed_and_preserves_source(
    tmp_path: Path,
    raw: bytes,
) -> None:
    path = tmp_path / "tenants/alpha/usage.jsonl"
    path.parent.mkdir(parents=True)
    path.write_bytes(raw)
    store = UsageStore(tmp_path, tenant_id="alpha")

    with pytest.raises(UsageStoreError):
        store.get_daily_usage()
    with pytest.raises(UsageStoreError):
        store.check_limit(PREDEFINED_PLANS["free"])
    with pytest.raises(UsageStoreError):
        store.record(_event("new"))
    assert path.read_bytes() == raw


@pytest.mark.parametrize(
    "raw",
    [
        b"{not-json",
        b"[]",
        (
            "{"
            f'"{datetime.now(timezone.utc).strftime("%Y-%m")}":{{}},'
            f'"{datetime.now(timezone.utc).strftime("%Y-%m")}":{{}}'
            "}"
        ).encode(),
        json.dumps(
            {
                datetime.now(timezone.utc).strftime("%Y-%m"): {
                    "tenant_id": "alpha",
                    "year_month": datetime.now(timezone.utc).strftime("%Y-%m"),
                    "total_generations": 99,
                    "total_tokens": 5,
                    "total_cost_usd": 0.001,
                    "by_bundle": {},
                    "by_user": {},
                    "by_model": {},
                    "last_updated": datetime.now(timezone.utc).isoformat(),
                }
            }
        ).encode(),
    ],
)
def test_usage_summary_corruption_fails_closed_and_preserves_source(
    tmp_path: Path,
    raw: bytes,
) -> None:
    store = UsageStore(tmp_path, tenant_id="alpha")
    store.record(_event())
    path = tmp_path / "tenants/alpha/usage_summary.json"
    path.write_bytes(raw)

    with pytest.raises(UsageStoreError):
        store.get_current_month()
    with pytest.raises(UsageStoreError):
        store.record(_event("new"))
    assert path.read_bytes() == raw


def test_usage_summary_missing_for_multiple_events_fails_closed(
    tmp_path: Path,
) -> None:
    store = UsageStore(tmp_path, tenant_id="alpha")
    store.record(_event("first"))
    store.record(_event("second"))
    summary_path = tmp_path / "tenants/alpha/usage_summary.json"
    summary_path.unlink()
    event_bytes = (tmp_path / "tenants/alpha/usage.jsonl").read_bytes()

    with pytest.raises(UsageStoreError, match="summary is missing"):
        store.check_limit(PREDEFINED_PLANS["free"])
    assert (tmp_path / "tenants/alpha/usage.jsonl").read_bytes() == event_bytes
    assert not summary_path.exists()


def test_usage_record_is_idempotent_by_event_identity(tmp_path: Path) -> None:
    store = UsageStore(tmp_path, tenant_id="alpha")
    event = _event()

    assert store.record(event) is True
    assert store.record(event) is False
    repeated_request = _event("other")
    repeated_request.request_id = event.request_id
    assert store.record(repeated_request) is True
    assert store.get_current_month().total_generations == 2


def test_explicit_foreign_usage_state_stays_hidden_and_preserved(
    tmp_path: Path,
) -> None:
    event_path = tmp_path / "tenants/alpha/usage.jsonl"
    summary_path = tmp_path / "tenants/alpha/usage_summary.json"
    event_path.parent.mkdir(parents=True)
    foreign_line = json.dumps({"tenant_id": "beta", "opaque": True}) + "\n"
    event_path.write_text(foreign_line, encoding="utf-8")
    foreign_summary = {
        "2025-01": {
            "tenant_id": "beta",
            "opaque": True,
        }
    }
    summary_path.write_text(json.dumps(foreign_summary), encoding="utf-8")
    store = UsageStore(tmp_path, tenant_id="alpha")

    assert store.get_current_month() is None
    assert store.record(_event()) is True
    assert event_path.read_text(encoding="utf-8").startswith(foreign_line)
    persisted_summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert persisted_summary["2025-01"] == foreign_summary["2025-01"]
    assert store.get_current_month().total_generations == 1


def test_foreign_summary_collision_blocks_record_without_mutation(tmp_path: Path) -> None:
    year_month = datetime.now(timezone.utc).strftime("%Y-%m")
    path = tmp_path / "tenants/alpha/usage_summary.json"
    path.parent.mkdir(parents=True)
    raw = json.dumps(
        {year_month: {"tenant_id": "beta", "opaque": True}}
    ).encode()
    path.write_bytes(raw)
    store = UsageStore(tmp_path, tenant_id="alpha")

    with pytest.raises(UsageStoreError, match="owned by another tenant"):
        store.get_current_month()
    with pytest.raises(UsageStoreError, match="owned by another tenant"):
        store.record(_event())
    assert path.read_bytes() == raw
    assert not (path.parent / "usage.jsonl").exists()


def test_summary_write_failure_remains_visible_until_verified_repair(
    tmp_path: Path,
) -> None:
    backend = _FailingSummaryBackend(tmp_path)
    store = UsageStore(tmp_path, tenant_id="alpha", backend=backend)

    with pytest.raises(UsageStoreError, match="could not be written"):
        store.record(_event())
    event_path = tmp_path / "tenants/alpha/usage.jsonl"
    assert event_path.exists()
    assert not (tmp_path / "tenants/alpha/usage_summary.json").exists()
    with pytest.raises(UsageStoreError, match="could not be written"):
        store.get_current_month()

    recovered = UsageStore(tmp_path, tenant_id="alpha")
    summary = recovered.get_current_month()
    assert summary is not None
    assert summary.total_generations == 1


def test_read_repairs_exact_one_event_summary_gap(tmp_path: Path) -> None:
    failed = UsageStore(
        tmp_path,
        tenant_id="alpha",
        backend=_FailingSummaryBackend(tmp_path),
    )
    with pytest.raises(UsageStoreError, match="could not be written"):
        failed.record(_event("first"))

    recovered = UsageStore(tmp_path, tenant_id="alpha")
    first_summary = recovered.get_current_month()
    assert first_summary is not None
    assert first_summary.total_generations == 1
    assert recovered.record(_event("second")) is True

    summary = recovered.get_current_month()
    assert summary is not None
    assert summary.total_generations == 2
    assert summary.total_tokens == 10


def test_usage_record_stops_after_bounded_event_conflicts(tmp_path: Path) -> None:
    backend = _ConflictingEventBackend(tmp_path)
    store = UsageStore(tmp_path, tenant_id="alpha", backend=backend)

    with pytest.raises(
        UsageStoreError,
        match="Usage state changed too many times to persist safely",
    ):
        store.record(_event())

    assert backend.attempts == 32


def test_usage_record_stops_after_bounded_summary_conflicts(
    tmp_path: Path,
) -> None:
    backend = _ConflictingSummaryBackend(tmp_path)
    store = UsageStore(tmp_path, tenant_id="alpha", backend=backend)

    with pytest.raises(
        UsageStoreError,
        match="Usage state changed too many times to read safely",
    ):
        store.record(_event())

    assert backend.attempts == 32
    assert (tmp_path / "tenants/alpha/usage.jsonl").exists()
    assert not (tmp_path / "tenants/alpha/usage_summary.json").exists()


def test_usage_record_wraps_conditional_event_failure(tmp_path: Path) -> None:
    store = UsageStore(
        tmp_path,
        tenant_id="alpha",
        backend=_FailingEventBackend(tmp_path),
    )

    with pytest.raises(UsageStoreError, match="could not be written"):
        store.record(_event())


def test_usage_state_round_trips_through_fake_s3() -> None:
    backend, client = _s3_backend()
    store = UsageStore("/virtual/one", tenant_id="alpha", backend=backend)

    store.record(_event())

    reloaded = UsageStore("/virtual/two", tenant_id="alpha", backend=backend)
    summary = reloaded.get_current_month()
    assert summary is not None
    assert summary.total_generations == 1
    assert summary.total_tokens == 5
    assert {key for bucket, key in client.objects if bucket == "unit-bucket"} >= {
        "decisiondoc-ai/state/tenants/alpha/usage.jsonl",
        "decisiondoc-ai/state/tenants/alpha/usage_summary.json",
    }
    assert not Path("/virtual/one/tenants").exists()


def test_usage_read_retries_event_and_summary_snapshot_skew(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = UsageStore(tmp_path, tenant_id="alpha")
    assert store.record(_event("first")) is True
    stale_event_raw, stale_events, _stale_summary_raw = (
        store._read_state_documents()
    )

    assert store.record(_event("second")) is True
    _current_event_raw, _current_events, current_summary_raw = (
        store._read_state_documents()
    )
    read_state_documents = store._read_state_documents
    first_read = True

    def read_with_snapshot_skew() -> tuple[
        str | None,
        list[dict[str, object]],
        str | None,
    ]:
        nonlocal first_read
        if first_read:
            first_read = False
            return stale_event_raw, stale_events, current_summary_raw
        return read_state_documents()

    monkeypatch.setattr(store, "_read_state_documents", read_with_snapshot_skew)

    summary = store.get_current_month()

    assert summary is not None
    assert summary.total_generations == 2
    assert summary.total_tokens == 10


def test_independent_local_workers_preserve_concurrent_events(
    tmp_path: Path,
) -> None:
    stores = [
        UsageStore(tmp_path, tenant_id="alpha")
        for _ in range(20)
    ]
    for store in stores:
        store._lock = nullcontext()

    with ThreadPoolExecutor(max_workers=20) as executor:
        results = list(
            executor.map(
                lambda item: item[1].record(_event(str(item[0]))),
                enumerate(stores),
            )
        )

    assert results == [True] * 20
    summary = stores[0].get_current_month()
    assert summary is not None
    assert summary.total_generations == 20
    assert summary.total_tokens == 100


def test_independent_fake_s3_usage_stores_preserve_concurrent_events() -> None:
    client = _MemoryS3Client(read_delay=0.002)
    stores = [
        UsageStore(
            f"/virtual/data-{index}",
            tenant_id="alpha",
            backend=_s3_backend(client=client)[0],
        )
        for index in range(20)
    ]
    for store in stores:
        store._lock = nullcontext()

    with ThreadPoolExecutor(max_workers=20) as executor:
        results = list(
            executor.map(
                lambda item: item[1].record(_event(str(item[0]))),
                enumerate(stores),
            )
        )

    assert results == [True] * 20
    summary = stores[0].get_current_month()
    assert summary is not None
    assert summary.total_generations == 20
    assert summary.total_tokens == 100
    assert len(stores[0].get_daily_usage()) == 1


def test_usage_record_reconciles_commit_then_successor_append() -> None:
    client = _MemoryS3Client()
    primary = UsageStore(
        "/virtual/primary",
        tenant_id="alpha",
        backend=_s3_backend(client=client)[0],
    )
    successor = UsageStore(
        "/virtual/successor",
        tenant_id="alpha",
        backend=_s3_backend(client=client)[0],
    )
    primary._lock = nullcontext()
    successor._lock = nullcontext()
    successor_event = _event("successor")
    client.fail_after_next_conditional_write(
        after_write=lambda: successor.record(successor_event)
    )

    assert primary.record(_event("primary")) is True

    summary = primary.get_current_month()
    assert summary is not None
    assert summary.total_generations == 2
    assert summary.total_tokens == 10
    event_ids = {
        event["event_id"]
        for event in primary._parse_events(
            primary._read_text(primary._event_relative_path)
        )
        if event.get("tenant_id") == "alpha"
    }
    assert event_ids == {"event-primary", "event-successor"}


def test_usage_summary_reconciles_commit_then_successor_append() -> None:
    client = _MemoryS3Client()
    primary = UsageStore(
        "/virtual/primary",
        tenant_id="alpha",
        backend=_s3_backend(client=client)[0],
    )
    successor = UsageStore(
        "/virtual/successor",
        tenant_id="alpha",
        backend=_s3_backend(client=client)[0],
    )
    primary._lock = nullcontext()
    successor._lock = nullcontext()
    successor_event = _event("successor")
    client.fail_after_next_conditional_write(
        after_write=lambda: successor.record(successor_event),
        key_suffix="usage_summary.json",
    )

    assert primary.record(_event("primary")) is True

    summary = primary.get_current_month()
    assert summary is not None
    assert summary.total_generations == 2
    assert summary.total_tokens == 10


def test_same_event_from_independent_workers_is_recorded_once() -> None:
    client = _MemoryS3Client(read_delay=0.001)
    stores = [
        UsageStore(
            f"/virtual/data-{index}",
            tenant_id="alpha",
            backend=_s3_backend(client=client)[0],
        )
        for index in range(20)
    ]
    for store in stores:
        store._lock = nullcontext()
    event = _event("shared")

    with ThreadPoolExecutor(max_workers=20) as executor:
        results = list(
            executor.map(lambda store: store.record(event), stores)
        )

    assert results.count(True) == 1
    assert results.count(False) == 19
    summary = stores[0].get_current_month()
    assert summary is not None
    assert summary.total_generations == 1
    assert summary.total_tokens == 5


def test_billing_api_reads_usage_from_application_s3_backend(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backend, _ = _s3_backend()
    UsageStore(tmp_path, tenant_id="system", backend=backend).record(_event(tenant_id="system"))
    client = _client(tmp_path, monkeypatch, backend=backend)

    response = client.get("/billing/status", headers=_headers())

    assert response.status_code == 200
    assert response.json()["usage"]["generations_used"] == 1
    assert not (tmp_path / "tenants/system/usage.jsonl").exists()


def test_metered_request_rejects_corrupt_s3_usage_before_generation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backend, client_data = _s3_backend()
    key = ("unit-bucket", "decisiondoc-ai/state/tenants/system/usage.jsonl")
    client_data.objects[key] = b"{not-json\n"
    client = _client(tmp_path, monkeypatch, backend=backend)

    response = client.post(
        "/generate/stream",
        json={"title": "Usage authority", "goal": "Reject corrupt metering state"},
        headers=_headers(),
    )

    assert response.status_code == 503
    assert response.json()["code"] == "BILLING_STATE_UNAVAILABLE"
    assert client_data.objects[key] == b"{not-json\n"


def test_generation_rejects_corrupt_usage_during_billing_preflight(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backend, client_data = _s3_backend()
    key = ("unit-bucket", "decisiondoc-ai/state/tenants/system/usage.jsonl")
    client_data.objects[key] = b"{not-json\n"
    client = _client(tmp_path, monkeypatch, backend=backend)

    response = client.post(
        "/generate",
        json={"title": "Usage evidence", "goal": "Do not omit metering failure"},
        headers=_headers(),
    )

    assert response.status_code == 503
    assert response.json()["code"] == "BILLING_STATE_UNAVAILABLE"
    assert client_data.objects[key] == b"{not-json\n"


def test_generation_usage_recording_uses_application_s3_backend(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backend, _ = _s3_backend()
    client = _client(tmp_path, monkeypatch, backend=backend)

    response = client.post(
        "/generate",
        json={"title": "Usage evidence", "goal": "Persist metering state"},
        headers=_headers(),
    )

    assert response.status_code == 200
    summary = UsageStore(
        "/other/root",
        tenant_id="system",
        backend=backend,
    ).get_current_month()
    assert summary is not None
    assert summary.total_generations == 1
    assert not (tmp_path / "tenants/system/usage.jsonl").exists()


def test_generation_metering_failure_precedes_bundle_side_effects(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backend = _FailingSummaryBackend(tmp_path)
    client = _client(tmp_path, monkeypatch, backend=backend)

    response = client.post(
        "/generate",
        json={"title": "Usage ordering", "goal": "Do not persist an unmetered bundle"},
        headers=_headers(),
    )

    assert response.status_code == 503
    assert response.json()["code"] == "USAGE_STATE_UNAVAILABLE"
    assert [path.name for path in tmp_path.glob("*.json")] == ["tenants.json"]
    assert not list((tmp_path / "cache").glob("*.json"))
    assert (tmp_path / "tenants/system/usage.jsonl").exists()
    assert not (tmp_path / "tenants/system/usage_summary.json").exists()


def test_billing_usage_days_are_bounded_by_request_schema(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _client(tmp_path, monkeypatch)

    assert client.get("/billing/usage?days=0", headers=_headers()).status_code == 422
    assert client.get("/billing/usage?days=367", headers=_headers()).status_code == 422


def test_billing_usage_requires_authenticated_user(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _client(tmp_path, monkeypatch)

    response = client.get("/billing/usage")

    assert response.status_code == 401


def test_invalid_utf8_usage_state_maps_to_public_error_contracts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "tenants/system/usage.jsonl"
    path.parent.mkdir(parents=True)
    raw = b"\xff\xfeinvalid-utf8"
    path.write_bytes(raw)
    client = _client(tmp_path, monkeypatch)

    billing_response = client.get("/billing/status", headers=_headers())
    generation_response = client.post(
        "/generate",
        json={"title": "Invalid state", "goal": "Reject before provider execution"},
        headers=_headers(),
    )

    assert billing_response.status_code == 503
    assert billing_response.json()["code"] == "USAGE_STATE_UNAVAILABLE"
    assert generation_response.status_code == 503
    assert generation_response.json()["code"] == "BILLING_STATE_UNAVAILABLE"
    assert path.read_bytes() == raw


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("POST", "/attachments/parse-rfp"),
        ("POST", "/api/agent/document-ops/run"),
        ("POST", "/admin/expand-bundles"),
        ("POST", "/generate"),
        ("POST", "/generate/docx"),
        ("POST", "/generate/excel"),
        ("POST", "/generate/export"),
        ("POST", "/generate/from-documents"),
        ("POST", "/generate/from-pdf"),
        ("POST", "/generate/hwp"),
        ("POST", "/generate/pdf"),
        ("POST", "/generate/pptx"),
        ("POST", "/generate/refine"),
        ("POST", "/generate/review"),
        ("POST", "/generate/rewrite-section"),
        ("POST", "/generate/sketch"),
        ("POST", "/generate/stream"),
        ("POST", "/generate/summary"),
        ("POST", "/generate/translate"),
        ("POST", "/generate/visual-assets"),
        ("POST", "/generate/with-attachments"),
        ("POST", "/projects/project-1/recordings/recording-1/transcribe"),
        ("POST", "/projects/project-1/recordings/recording-1/generate-documents"),
        ("POST", "/report-workflows/report-1/develop-quality/preview"),
        ("POST", "/report-workflows/report-1/planning/generate"),
        ("POST", "/report-workflows/report-1/slides/generate"),
        ("POST", "/report-workflows/report-1/visual-assets/generate"),
        ("POST", "/styles/profile-1/analyze"),
    ],
)
def test_provider_backed_routes_are_metered(method: str, path: str) -> None:
    assert is_metered_endpoint(method, path) is True


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/billing/status"),
        ("POST", "/generate/freeform"),
        ("POST", "/generate/export-edited"),
        ("POST", "/generate/related"),
        ("POST", "/generate/validate"),
        ("POST", "/g2b/fetch"),
        ("POST", "/knowledge/project-1/documents"),
        ("POST", "/projects/project-1/imports/g2b-opportunity"),
    ],
)
def test_routes_without_unconditional_provider_calls_are_not_globally_metered(
    method: str,
    path: str,
) -> None:
    assert is_metered_endpoint(method, path) is False


def test_direct_ai_route_records_usage(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _client(tmp_path, monkeypatch)

    response = client.post(
        "/generate/summary",
        json={"content": "A decision document with enough content to summarize."},
        headers=_headers(),
    )

    assert response.status_code == 200
    summary = UsageStore(tmp_path, tenant_id="system").get_current_month()
    assert summary is not None
    assert summary.total_generations == 1
    assert summary.by_bundle["ai.summary"]["count"] == 1


def test_direct_ai_failure_records_tokens_without_exposing_provider_details(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _client(tmp_path, monkeypatch)
    provider = _SensitiveFailingProvider()
    monkeypatch.setattr(
        "app.routers.generate.ai_features.get_provider_for_capability",
        lambda capability: provider,
    )

    response = client.post(
        "/generate/summary",
        json={"content": "A document long enough to reach the provider."},
        headers=_headers(),
    )

    assert response.status_code == 503
    assert response.json()["detail"] == "AI provider 요청에 실패했습니다."
    assert "127.0.0.1" not in response.text
    assert "secret response body" not in response.text
    summary = UsageStore(tmp_path, tenant_id="system").get_current_month()
    assert summary is not None
    assert summary.total_generations == 1
    assert summary.total_tokens == 11


def test_core_generation_records_tokens_before_bundle_post_processing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _client(tmp_path, monkeypatch)
    client.app.state.service.provider_factory = _BrokenBundleProvider

    response = client.post(
        "/generate",
        json={"title": "Broken bundle usage", "goal": "Persist provider tokens first"},
        headers=_headers(),
    )

    assert response.status_code == 500
    summary = UsageStore(tmp_path, tenant_id="system").get_current_month()
    assert summary is not None
    assert summary.total_generations == 1
    assert summary.total_tokens == 8


def test_provider_retry_accumulates_usage_from_each_attempt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.bundle_catalog.spec import BundleSpec
    from app.services.generation_service import GenerationService

    monkeypatch.setenv("LLM_RETRY_ATTEMPTS", "2")
    monkeypatch.setenv("LLM_RETRY_BACKOFF_SECONDS", "0")
    provider = _RetryUsageProvider()
    service = GenerationService(
        provider_factory=lambda: provider,
        template_dir=tmp_path,
        data_dir=tmp_path,
    )
    bundle_spec = MagicMock(spec=BundleSpec)
    bundle_spec.id = "tech_decision"
    usage_totals: dict[str, int] = {}

    result = service._call_provider_with_retry(
        provider,
        {},
        "request-retry-usage",
        bundle_spec,
        tenant_id="system",
        usage_totals=usage_totals,
    )

    assert result == {"result": "ok"}
    assert provider.calls == 2
    assert usage_totals == {"prompt_tokens": 3, "output_tokens": 5}


def test_document_ops_route_records_usage(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _client(tmp_path, monkeypatch)

    response = client.post(
        "/api/agent/document-ops/run",
        json={
            "task_type": "decision_brief",
            "requirements": {"title": "Metered DocumentOps decision"},
        },
        headers=_headers(),
    )

    assert response.status_code == 200
    summary = UsageStore(tmp_path, tenant_id="system").get_current_month()
    assert summary is not None
    assert summary.total_generations == 1
    assert summary.by_bundle["document-ops.agent-run"]["count"] == 1


def test_document_ops_metering_failure_precedes_trajectory_persistence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backend = _FailingSummaryBackend(tmp_path)
    client = _client(tmp_path, monkeypatch, backend=backend)

    response = client.post(
        "/api/agent/document-ops/run",
        json={
            "task_type": "decision_brief",
            "requirements": {"title": "Fail closed before trajectory save"},
            "capture_trajectory": True,
        },
        headers=_headers(),
    )

    assert response.status_code == 503
    assert response.json()["code"] == "USAGE_STATE_UNAVAILABLE"
    assert not (tmp_path / "tenants/system/trajectories.jsonl").exists()


def test_attachment_usage_is_auxiliary_to_generation_count(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _client(tmp_path, monkeypatch)

    response = client.post(
        "/generate/with-attachments",
        data={
            "payload": json.dumps(
                {"title": "Attachment usage", "goal": "Track composite provider usage"}
            )
        },
        files={"attachments": ("context.png", b"fake-image", "image/png")},
        headers=_headers(),
    )

    assert response.status_code == 200
    summary = UsageStore(tmp_path, tenant_id="system").get_current_month()
    assert summary is not None
    assert summary.total_generations == 1
    assert summary.by_bundle["generation.attachment"]["count"] == 1


def test_attachment_extraction_accumulates_each_provider_call() -> None:
    provider = _UsageReportingAttachmentProvider()
    usage_totals: dict[str, int] = {}

    result = extract_multiple(
        [("one.png", b"one"), ("two.png", b"two")],
        provider=provider,
        request_id="request-attachment-usage",
        usage_totals=usage_totals,
    )

    assert provider.calls == 2
    assert "provider text for one.png" in result
    assert "provider text for two.png" in result
    assert usage_totals == {
        "provider_calls": 2,
        "prompt_tokens": 3,
        "output_tokens": 5,
        "total_tokens": 8,
    }


def test_attachment_failure_still_accumulates_provider_usage() -> None:
    provider = _FailingUsageAttachmentProvider()
    usage_totals: dict[str, int] = {}

    result = extract_multiple(
        [("failed.png", b"image")],
        provider=provider,
        request_id="request-attachment-failure",
        usage_totals=usage_totals,
    )

    assert "OCR·비전 추출 실패" in result
    assert "provider response parsing failed" not in result
    assert usage_totals == {
        "provider_calls": 1,
        "prompt_tokens": 1,
        "output_tokens": 2,
        "total_tokens": 3,
    }


def test_process_local_admission_serializes_requests_at_limit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = UsageStore(tmp_path, tenant_id="system")
    for index in range(19):
        store.record(_event(f"seed-{index}", tenant_id="system"))
    client = _client(tmp_path, monkeypatch)

    def _request() -> tuple[int, str | None]:
        response = client.post(
            "/generate/summary",
            json={"content": "Concurrent request admission must be serialized."},
            headers=_headers(),
        )
        return response.status_code, response.json().get("code")

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: _request(), range(2)))

    assert sorted(results) == [(200, None), (402, "LIMIT_EXCEEDED")]
    assert store.get_current_month().total_generations == 20


def test_cancelled_admission_waiter_does_not_orphan_thread_lock() -> None:
    lock = threading.Lock()
    lock.acquire()

    async def _exercise_cancellation() -> None:
        waiter = asyncio.create_task(_acquire_thread_lock(lock))
        await asyncio.sleep(0.01)
        waiter.cancel()
        with pytest.raises(asyncio.CancelledError):
            await waiter

        lock.release()
        for _ in range(100):
            if lock.acquire(blocking=False):
                lock.release()
                return
            await asyncio.sleep(0.01)
        pytest.fail("cancelled billing admission left the tenant lock acquired")

    run_async(_exercise_cancellation())


def test_cancelled_provider_worker_holds_admission_until_usage_is_recorded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app.middleware.billing as billing_module

    lock = threading.Lock()
    lock.acquire()
    worker_done = threading.Event()
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/generate/rewrite-section",
            "raw_path": b"/generate/rewrite-section",
            "query_string": b"",
            "headers": [],
            "scheme": "http",
            "server": ("testserver", 80),
            "client": ("testclient", 50000),
        }
    )

    async def _acquire(_request: Request):
        return lock, None

    async def _cancel_after_worker_starts(active_request: Request):
        active_request.state.billing_provider_worker_done = worker_done
        raise asyncio.CancelledError

    monkeypatch.setattr(billing_module, "acquire_billing_admission", _acquire)

    async def _exercise_cancellation() -> None:
        with pytest.raises(asyncio.CancelledError):
            await billing_module.billing_middleware(
                request,
                _cancel_after_worker_starts,
            )

        assert lock.acquire(blocking=False) is False
        worker_done.set()
        for _ in range(100):
            if lock.acquire(blocking=False):
                lock.release()
                return
            await asyncio.sleep(0.01)
        pytest.fail("provider worker completion did not release billing admission")

    run_async(_exercise_cancellation())


def test_meeting_transcription_limit_blocks_provider_transport(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = UsageStore(tmp_path, tenant_id="system")
    for index in range(20):
        store.record(_event(f"transcription-limit-{index}", tenant_id="system"))

    monkeypatch.setenv("OPENAI_API_KEY", "local-test-key")
    client = _client(tmp_path, monkeypatch)
    project = client.post(
        "/projects",
        json={"name": "Transcription admission"},
        headers=_headers(),
    )
    assert project.status_code == 200
    project_id = project.json()["project_id"]
    upload = client.post(
        f"/projects/{project_id}/recordings",
        files={"file": ("meeting.wav", b"fake-audio", "audio/wav")},
        headers=_headers(),
    )
    assert upload.status_code == 200
    recording_id = upload.json()["recording"]["recording_id"]
    provider_called = threading.Event()

    def _provider_transport(_request: httpx.Request) -> httpx.Response:
        provider_called.set()
        return httpx.Response(200, json={"text": "must not run"})

    client.app.state.meeting_recording_service = MeetingRecordingService(
        recording_store=client.app.state.meeting_recording_store,
        project_store=client.app.state.project_store,
        generation_service=client.app.state.service,
        transport=httpx.MockTransport(_provider_transport),
    )

    response = client.post(
        f"/projects/{project_id}/recordings/{recording_id}/transcribe",
        json={},
        headers=_headers(),
    )

    assert response.status_code == 402
    assert response.json()["code"] == "LIMIT_EXCEEDED"
    assert provider_called.is_set() is False
    assert store.get_current_month().total_generations == 20


def test_meeting_transcription_usage_failure_marks_recording_failed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backend = _FailingSummaryBackend(tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "local-test-key")
    client = _client(tmp_path, monkeypatch, backend=backend)
    project = client.post(
        "/projects",
        json={"name": "Transcription usage failure"},
        headers=_headers(),
    )
    project_id = project.json()["project_id"]
    upload = client.post(
        f"/projects/{project_id}/recordings",
        files={"file": ("meeting.wav", b"fake-audio", "audio/wav")},
        headers=_headers(),
    )
    recording_id = upload.json()["recording"]["recording_id"]

    client.app.state.meeting_recording_service = MeetingRecordingService(
        recording_store=client.app.state.meeting_recording_store,
        project_store=client.app.state.project_store,
        generation_service=client.app.state.service,
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(200, json={"text": "transcript"})
        ),
    )

    response = client.post(
        f"/projects/{project_id}/recordings/{recording_id}/transcribe",
        json={},
        headers=_headers(),
    )

    assert response.status_code == 503
    assert response.json()["code"] == "USAGE_STATE_UNAVAILABLE"
    recording = client.app.state.meeting_recording_store.get(
        tenant_id="system",
        project_id=project_id,
        recording_id=recording_id,
    )
    assert recording is not None
    assert recording.transcription_status == "failed"
    assert recording.transcript_error == TRANSCRIPTION_FAILED_MESSAGE
    assert recording.transcript_text == ""


def test_edited_export_only_requires_admission_for_provider_visuals(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = UsageStore(tmp_path, tenant_id="system")
    for index in range(20):
        store.record(_event(f"limit-{index}", tenant_id="system"))
    client = _client(tmp_path, monkeypatch)
    monkeypatch.setenv("DECISIONDOC_PROVIDER_VISUAL", "invalid-local-visual-provider")

    local_response = client.post(
        "/generate/export-edited",
        json={
            "format": "excel",
            "title": "Local export",
            "docs": [{"doc_type": "adr", "markdown": "# Local"}],
        },
        headers=_headers(),
    )
    local_visual_response = client.post(
        "/generate/export-edited",
        json={
            "format": "docx",
            "title": "Local visual export",
            "docs": [
                {
                    "doc_type": "proposal_kr",
                    "markdown": "# Timeline",
                    "slide_outline": [
                        {"title": "Timeline", "visual_type": "타임라인"}
                    ],
                }
            ],
        },
        headers=_headers(),
    )
    visual_response = client.post(
        "/generate/export-edited",
        json={
            "format": "docx",
            "title": "Visual export",
            "docs": [
                {
                    "doc_type": "proposal_kr",
                    "markdown": "# Visual",
                    "slide_outline": [
                        {"title": "Visual slide", "visual_type": "현장 사진"}
                    ],
                }
            ],
        },
        headers=_headers(),
    )

    assert local_response.status_code == 200
    assert local_visual_response.status_code == 200
    assert visual_response.status_code == 402
    assert visual_response.json()["code"] == "LIMIT_EXCEEDED"


def test_local_knowledge_upload_does_not_consume_generation_admission(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = UsageStore(tmp_path, tenant_id="system")
    for index in range(20):
        store.record(_event(f"knowledge-limit-{index}", tenant_id="system"))
    client = _client(tmp_path, monkeypatch)

    response = client.post(
        "/knowledge/project-1/documents",
        data={"learning_mode": "reference"},
        files={"file": ("local.txt", b"local parser content", "text/plain")},
        headers=_headers(),
    )

    assert response.status_code == 200
    assert store.get_current_month().total_generations == 20


def test_stream_normalizes_usage_recording_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _client(tmp_path, monkeypatch)

    def _fail_usage(*args, **kwargs):
        _ = args, kwargs
        raise UsageStoreError("internal usage state detail")

    monkeypatch.setattr(client.app.state.service, "generate_documents", _fail_usage)
    response = client.post(
        "/generate/stream",
        json={"title": "Stream error", "goal": "Normalize metering error"},
        headers=_headers(),
    )

    assert response.status_code == 200
    assert '"code": "USAGE_STATE_UNAVAILABLE"' in response.text
    assert "internal usage state detail" not in response.text


def test_usage_callers_bind_application_backend() -> None:
    paths = [
        Path("app/middleware/billing.py"),
        Path("app/routers/billing.py"),
        Path("app/storage/billing_store.py"),
        Path("app/services/generation/context_store.py"),
    ]
    calls: list[tuple[Path, ast.Call]] = []
    for path in paths:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        calls.extend(
            (path, node)
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "UsageStore"
        )

    assert calls
    for path, call in calls:
        assert "backend" in {keyword.arg for keyword in call.keywords}, (
            f"{path}:{call.lineno}"
        )
