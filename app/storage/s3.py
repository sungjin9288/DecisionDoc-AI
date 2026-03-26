import json
import logging
import os
from typing import Any

from app.storage.base import Storage, StorageFailedError

_log = logging.getLogger("decisiondoc.storage.s3")


class S3Storage(Storage):
    def __init__(
        self,
        bucket: str,
        prefix: str = "decisiondoc-ai/",
        s3_client: Any | None = None,
    ) -> None:
        self.bucket = bucket
        self.prefix = prefix if prefix.endswith("/") else f"{prefix}/"
        self._s3_client = s3_client

    @property
    def kind(self) -> str:
        return "s3"

    @property
    def client(self) -> Any:
        if self._s3_client is not None:
            return self._s3_client
        try:
            import boto3  # type: ignore
        except ImportError as exc:
            raise StorageFailedError("Storage operation failed.") from exc
        self._s3_client = boto3.client("s3")
        return self._s3_client

    def _bundle_key(self, bundle_id: str) -> str:
        return f"{self.prefix}bundles/{bundle_id}.json"

    def _export_key(self, bundle_id: str, doc_type: str) -> str:
        return f"{self.prefix}exports/{bundle_id}/{doc_type}.md"

    def save_bundle(self, bundle_id: str, bundle: dict[str, Any]) -> None:
        body = json.dumps(bundle, ensure_ascii=False, indent=2).encode("utf-8")
        self._put(self._bundle_key(bundle_id), body, "application/json")

    def load_bundle(self, bundle_id: str) -> dict[str, Any] | None:
        try:
            obj = self.client.get_object(Bucket=self.bucket, Key=self._bundle_key(bundle_id))
            raw = obj["Body"].read().decode("utf-8")
            return json.loads(raw)
        except Exception as exc:
            # boto3 ClientError: NoSuchKey means the bundle doesn't exist yet (cache miss).
            # Any other error (network, permissions, malformed JSON, …) is a real failure.
            error_code = ""
            response = getattr(exc, "response", None)
            if isinstance(response, dict):
                error_code = response.get("Error", {}).get("Code", "")
            if error_code == "NoSuchKey":
                return None
            raise StorageFailedError("Storage operation failed.") from exc

    def save_export(self, bundle_id: str, doc_type: str, markdown: str) -> None:
        body = markdown.encode("utf-8")
        self._put(self._export_key(bundle_id, doc_type), body, "text/markdown; charset=utf-8")

    def get_export_path(self, bundle_id: str, doc_type: str) -> str:
        return f"s3://{self.bucket}/{self._export_key(bundle_id, doc_type)}"

    def get_export_dir(self, bundle_id: str) -> str:
        return f"s3://{self.bucket}/{self.prefix}exports/{bundle_id}/"

    def health_check(self) -> dict:
        """Return {"ok": True} if the bucket is reachable, raise StorageFailedError otherwise."""
        try:
            self.client.head_bucket(Bucket=self.bucket)
            return {"ok": True}
        except Exception as exc:
            _log.warning("S3 health check failed for bucket=%s: %s", self.bucket, exc)
            raise StorageFailedError("Storage operation failed.") from exc

    def _put(self, key: str, body: bytes, content_type: str) -> None:
        try:
            if not self.bucket:
                raise StorageFailedError("Storage operation failed.")
            self.client.put_object(Bucket=self.bucket, Key=key, Body=body, ContentType=content_type)
        except Exception as exc:
            _log.warning("S3 put failed for key=%s: %s", key, exc)
            raise StorageFailedError("Storage operation failed.") from exc


def s3_from_env() -> "S3Storage":
    bucket = os.getenv("DECISIONDOC_S3_BUCKET", "")
    prefix = os.getenv("DECISIONDOC_S3_PREFIX", "decisiondoc-ai/")
    return S3Storage(bucket=bucket, prefix=prefix)
