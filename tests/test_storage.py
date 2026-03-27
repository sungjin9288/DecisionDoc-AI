import json
from pathlib import Path

import pytest

from app.storage.base import StorageFailedError
from app.storage.local import LocalStorage
from app.storage.s3 import S3Storage


def test_local_storage_save_bundle_and_load(tmp_path):
    storage = LocalStorage(data_dir=tmp_path / "data", exports_dir=tmp_path / "exports")
    bundle_id = "bundle-1"
    payload = {"adr": {}, "onepager": {}, "eval_plan": {}, "ops_checklist": {}}

    storage.save_bundle(bundle_id, payload)
    loaded = storage.load_bundle(bundle_id)

    assert loaded == payload
    assert (tmp_path / "data" / f"{bundle_id}.json").exists()


def test_local_storage_save_export_atomic_and_exists(tmp_path):
    storage = LocalStorage(data_dir=tmp_path / "data", exports_dir=tmp_path / "exports")
    storage.save_export("bundle-2", "adr", "# ADR\ncontent\n")
    md_path = Path(storage.get_export_path("bundle-2", "adr"))
    assert md_path.exists()
    assert md_path.read_text(encoding="utf-8").startswith("# ADR")


def test_local_storage_corrupted_json_load_returns_none(tmp_path):
    storage = LocalStorage(data_dir=tmp_path / "data", exports_dir=tmp_path / "exports")
    broken = tmp_path / "data" / "bad.json"
    broken.parent.mkdir(parents=True, exist_ok=True)
    broken.write_text("{not-json", encoding="utf-8")
    assert storage.load_bundle("bad") is None


class FakeS3Client:
    def __init__(self) -> None:
        self.calls = []

    def put_object(self, **kwargs):
        self.calls.append(kwargs)

    def get_object(self, **kwargs):
        _ = kwargs
        return {"Body": FakeBody(json.dumps({"ok": True}).encode("utf-8"))}


class FakeBody:
    def __init__(self, body: bytes):
        self._body = body

    def read(self):
        return self._body


def test_s3_storage_put_object_key_scheme_and_bytes():
    fake = FakeS3Client()
    storage = S3Storage(bucket="unit-bucket", prefix="decisiondoc-ai/", s3_client=fake)

    storage.save_bundle("abc123", {"x": 1})
    storage.save_export("abc123", "adr", "# ADR")

    assert len(fake.calls) == 2
    first = fake.calls[0]
    second = fake.calls[1]
    assert first["Bucket"] == "unit-bucket"
    assert first["Key"] == "decisiondoc-ai/bundles/abc123.json"
    assert isinstance(first["Body"], bytes)
    assert second["Key"] == "decisiondoc-ai/exports/abc123/adr.md"
    assert isinstance(second["Body"], bytes)


class FakeS3ClientNotFound:
    """S3 client that raises a NoSuchKey ClientError on get_object."""

    def get_object(self, **kwargs):
        exc = Exception("NoSuchKey")
        exc.response = {"Error": {"Code": "NoSuchKey", "Message": "The specified key does not exist."}}
        raise exc


class FakeS3ClientNetworkError:
    """S3 client that raises a non-NotFound error on get_object."""

    def get_object(self, **kwargs):
        exc = Exception("Connection reset")
        exc.response = {"Error": {"Code": "InternalError", "Message": "We encountered an internal error."}}
        raise exc


def test_s3_load_bundle_returns_none_on_no_such_key():
    """NoSuchKey → bundle not found → return None (cache miss)."""
    storage = S3Storage(bucket="unit-bucket", prefix="decisiondoc-ai/", s3_client=FakeS3ClientNotFound())
    assert storage.load_bundle("missing-bundle") is None


def test_s3_load_bundle_raises_storage_failed_on_other_errors():
    """Non-NoSuchKey errors → StorageFailedError (real failure, not cache miss)."""
    storage = S3Storage(bucket="unit-bucket", prefix="decisiondoc-ai/", s3_client=FakeS3ClientNetworkError())
    with pytest.raises(StorageFailedError):
        storage.load_bundle("some-bundle")


def test_atomic_write_json_raises_storage_failed_on_non_serializable(tmp_path):
    storage = LocalStorage(data_dir=tmp_path / "data", exports_dir=tmp_path / "exports")
    path = tmp_path / "data" / "test.json"

    # datetime objects are not JSON-serializable — _atomic_write_json must convert
    # the TypeError into StorageFailedError rather than letting it propagate raw.
    from datetime import datetime

    with pytest.raises(StorageFailedError):
        storage._atomic_write_json(path, {"ts": datetime(2026, 1, 1)})
