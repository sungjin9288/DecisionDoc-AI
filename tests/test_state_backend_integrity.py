from __future__ import annotations

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
