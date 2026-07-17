from __future__ import annotations

import hashlib
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import pytest

from app.storage.state_backend import (
    LocalStateBackend,
    S3StateBackend,
    StateBackendError,
)


class _RecordingS3Client:
    def __init__(self, pages: dict[str | None, dict[str, Any]] | None = None) -> None:
        self.calls: list[dict[str, Any]] = []
        self.pages = pages or {}

    def head_object(self, **request: Any) -> dict[str, Any]:
        self.calls.append(request)
        return {}

    def get_object(self, **request: Any) -> dict[str, Any]:
        self.calls.append(request)
        return {}

    def put_object(self, **request: Any) -> None:
        self.calls.append(request)

    def list_objects_v2(self, **request: Any) -> dict[str, Any]:
        self.calls.append(request)
        token = request.get("ContinuationToken")
        return self.pages[token]


def _s3_backend(client: _RecordingS3Client) -> S3StateBackend:
    return S3StateBackend(
        bucket="unit-bucket",
        prefix="decisiondoc-ai/state/",
        s3_client=client,
    )


def test_local_state_backend_round_trips_canonical_paths(tmp_path: Path):
    backend = LocalStateBackend(tmp_path)

    backend.write_text("tenants/alpha/profile.json", '{"name":"Alpha"}')
    backend.write_bytes("tenants/alpha/logo.bin", b"logo")

    assert backend.exists("tenants/alpha/profile.json") is True
    assert backend.read_text("tenants/alpha/profile.json") == '{"name":"Alpha"}'
    assert backend.read_bytes("tenants/alpha/logo.bin") == b"logo"
    assert backend.list_prefix("tenants/alpha") == [
        "tenants/alpha/logo.bin",
        "tenants/alpha/profile.json",
    ]
    backend.delete("tenants/alpha/logo.bin")
    backend.delete("tenants/alpha/logo.bin")
    assert backend.read_bytes("tenants/alpha/logo.bin") is None


def test_local_state_backend_conditional_writes_preserve_winner(
    tmp_path: Path,
) -> None:
    first = LocalStateBackend(tmp_path)
    second = LocalStateBackend(tmp_path)

    assert first.write_text_if_absent("reviews/record.json", "pending") is True
    assert second.write_text_if_absent("reviews/record.json", "other") is False
    assert second.replace_text_if_equal(
        "reviews/record.json",
        expected="other",
        replacement="rejected",
    ) is False
    assert second.replace_text_if_equal(
        "reviews/record.json",
        expected="pending",
        replacement="completed",
    ) is True
    assert first.read_text("reviews/record.json") == "completed"


def test_local_conditional_lock_initialization_is_thread_safe(tmp_path: Path) -> None:
    relative_path = "tenants/alpha/concurrent-state.json"
    backends = [LocalStateBackend(tmp_path) for _ in range(20)]

    def create(index: int) -> bool:
        return backends[index].write_text_if_absent(
            relative_path,
            json.dumps({"worker": index}),
        )

    with ThreadPoolExecutor(max_workers=20) as executor:
        outcomes = list(executor.map(create, range(20)))

    assert outcomes.count(True) == 1
    assert outcomes.count(False) == 19
    persisted = json.loads((tmp_path / relative_path).read_text(encoding="utf-8"))
    assert persisted["worker"] in range(20)


def test_local_state_backend_plain_write_uses_conditional_lock(
    tmp_path: Path,
) -> None:
    backend = LocalStateBackend(tmp_path)
    relative_path = "reviews/record.json"
    path = backend._path(relative_path)
    started = threading.Event()
    finished = threading.Event()

    def write() -> None:
        started.set()
        backend.write_text(relative_path, "completed")
        finished.set()

    with backend._conditional_write_lock(path):
        worker = threading.Thread(target=write)
        worker.start()
        assert started.wait(timeout=1)
        time.sleep(0.05)
        assert finished.is_set() is False

    worker.join(timeout=1)
    assert finished.is_set() is True
    assert backend.read_text(relative_path) == "completed"


def test_local_state_backend_rejects_conditional_lock_symlink(
    tmp_path: Path,
) -> None:
    root = tmp_path / "state"
    lock_root = root / ".decisiondoc-state-locks"
    lock_root.mkdir(parents=True)
    relative_path = "reviews/record.json"
    lock_name = hashlib.sha256(relative_path.encode("utf-8")).hexdigest()
    outside = tmp_path / "outside.lock"
    outside.write_text("outside", encoding="utf-8")
    (lock_root / f"{lock_name}.lock").symlink_to(outside)
    backend = LocalStateBackend(root)

    with pytest.raises(StateBackendError, match="conditional write"):
        backend.write_text_if_absent(relative_path, "pending")

    assert outside.read_text(encoding="utf-8") == "outside"
    assert not (root / relative_path).exists()


def test_local_state_backend_normalizes_atomic_write_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backend = LocalStateBackend(tmp_path)

    def fail_write(_path: Path, _text: str) -> None:
        raise OSError("simulated disk failure")

    monkeypatch.setattr("app.storage.base.atomic_write_text", fail_write)

    with pytest.raises(StateBackendError, match="Failed to write state file"):
        backend.write_text("reviews/record.json", "pending")
    with pytest.raises(
        StateBackendError,
        match="Failed to conditionally write state file",
    ):
        backend.write_text_if_absent("reviews/conditional.json", "pending")


@pytest.mark.parametrize(
    "unsafe_path",
    [
        "",
        " ",
        "/absolute.json",
        "../outside.json",
        "safe/../outside.json",
        "./state.json",
        "safe//state.json",
        "safe/",
        "safe\\state.json",
        "safe\x00state.json",
        "safe/control\nstate.json",
    ],
)
def test_local_state_backend_rejects_noncanonical_paths(
    tmp_path: Path,
    unsafe_path: str,
):
    backend = LocalStateBackend(tmp_path / "state")
    operations = (
        lambda: backend.exists(unsafe_path),
        lambda: backend.read_text(unsafe_path),
        lambda: backend.read_bytes(unsafe_path),
        lambda: backend.write_text(unsafe_path, "unsafe"),
        lambda: backend.write_bytes(unsafe_path, b"unsafe"),
        lambda: backend.write_text_if_absent(unsafe_path, "unsafe"),
        lambda: backend.write_bytes_if_absent(unsafe_path, b"unsafe"),
        lambda: backend.replace_text_if_equal(
            unsafe_path,
            expected="before",
            replacement="after",
        ),
        lambda: backend.delete(unsafe_path),
        lambda: backend.list_prefix(unsafe_path),
    )

    for operation in operations:
        with pytest.raises(StateBackendError):
            operation()

    assert not (tmp_path / "outside.json").exists()


def test_local_state_backend_rejects_file_symlink_escape(tmp_path: Path):
    root = tmp_path / "state"
    root.mkdir()
    outside = tmp_path / "outside.json"
    outside.write_text("outside", encoding="utf-8")
    (root / "linked.json").symlink_to(outside)
    backend = LocalStateBackend(root)

    with pytest.raises(StateBackendError, match="symbolic link"):
        backend.read_text("linked.json")
    with pytest.raises(StateBackendError, match="symbolic link"):
        backend.delete("linked.json")


def test_local_state_backend_rejects_directory_symlink_write_escape(tmp_path: Path):
    root = tmp_path / "state"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (root / "linked").symlink_to(outside, target_is_directory=True)
    backend = LocalStateBackend(root)

    with pytest.raises(StateBackendError, match="symbolic link"):
        backend.write_text("linked/escaped.json", "unsafe")

    assert not (outside / "escaped.json").exists()


def test_local_state_backend_rejects_nested_symlink_during_listing(tmp_path: Path):
    root = tmp_path / "state"
    (root / "tenants/alpha").mkdir(parents=True)
    (root / "tenants/alpha/profile.json").write_text("{}", encoding="utf-8")
    outside = tmp_path / "outside.json"
    outside.write_text("outside", encoding="utf-8")
    (root / "tenants/alpha/linked.json").symlink_to(outside)
    backend = LocalStateBackend(root)

    with pytest.raises(StateBackendError, match="symbolic link"):
        backend.list_prefix("tenants/alpha")


@pytest.mark.parametrize(
    "unsafe_path",
    [
        "",
        " ",
        "/absolute.json",
        "../outside.json",
        "safe/../outside.json",
        "./state.json",
        "safe//state.json",
        "safe/",
        "safe\\state.json",
        "safe\x00state.json",
        "safe/control\nstate.json",
    ],
)
def test_s3_state_backend_rejects_noncanonical_paths_before_client_call(
    unsafe_path: str,
):
    client = _RecordingS3Client()
    backend = _s3_backend(client)
    operations = (
        lambda: backend.exists(unsafe_path),
        lambda: backend.read_text(unsafe_path),
        lambda: backend.read_bytes(unsafe_path),
        lambda: backend.write_text(unsafe_path, "unsafe"),
        lambda: backend.write_bytes(unsafe_path, b"unsafe"),
        lambda: backend.write_text_if_absent(unsafe_path, "unsafe"),
        lambda: backend.write_bytes_if_absent(unsafe_path, b"unsafe"),
        lambda: backend.replace_text_if_equal(
            unsafe_path,
            expected="before",
            replacement="after",
        ),
        lambda: backend.delete(unsafe_path),
        lambda: backend.list_prefix(unsafe_path),
    )

    for operation in operations:
        with pytest.raises(StateBackendError):
            operation()

    assert client.calls == []


def test_s3_state_backend_paginates_and_excludes_adjacent_prefixes():
    client = _RecordingS3Client(
        {
            None: {
                "Contents": [
                    {"Key": "decisiondoc-ai/state/tenants/a/profile.json"},
                    {"Key": "decisiondoc-ai/state/tenants/alpha/profile.json"},
                    {"Key": "decisiondoc-ai/state/tenants/a/"},
                ],
                "IsTruncated": True,
                "NextContinuationToken": "page-2",
            },
            "page-2": {
                "Contents": [
                    {"Key": "decisiondoc-ai/state/tenants/a/settings.json"},
                    {"Key": "decisiondoc-ai/state/tenants/a/profile.json"},
                ],
                "IsTruncated": False,
            },
        }
    )
    backend = _s3_backend(client)

    assert backend.list_prefix("tenants/a") == [
        "tenants/a/profile.json",
        "tenants/a/settings.json",
    ]
    assert client.calls == [
        {
            "Bucket": "unit-bucket",
            "Prefix": "decisiondoc-ai/state/tenants/a",
        },
        {
            "Bucket": "unit-bucket",
            "Prefix": "decisiondoc-ai/state/tenants/a",
            "ContinuationToken": "page-2",
        },
    ]


def test_s3_state_backend_rejects_invalid_continuation_token():
    missing_token_client = _RecordingS3Client(
        {
            None: {
                "Contents": [],
                "IsTruncated": True,
            }
        }
    )

    with pytest.raises(StateBackendError, match="continuation token"):
        _s3_backend(missing_token_client).list_prefix("tenants/a")

    repeated_token_client = _RecordingS3Client(
        {
            None: {
                "Contents": [],
                "IsTruncated": True,
                "NextContinuationToken": "repeated",
            },
            "repeated": {
                "Contents": [],
                "IsTruncated": True,
                "NextContinuationToken": "repeated",
            },
        }
    )

    with pytest.raises(StateBackendError, match="continuation token"):
        _s3_backend(repeated_token_client).list_prefix("tenants/a")


def test_s3_state_backend_rejects_noncanonical_returned_key():
    client = _RecordingS3Client(
        {
            None: {
                "Contents": [
                    {"Key": "decisiondoc-ai/state/tenants/a/../escape.json"},
                ],
                "IsTruncated": False,
            }
        }
    )

    with pytest.raises(StateBackendError, match="canonical relative path"):
        _s3_backend(client).list_prefix("tenants/a")
