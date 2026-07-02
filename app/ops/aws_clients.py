import json
import os
from datetime import UTC, datetime
from time import perf_counter
from typing import Any
from uuid import uuid4


class AwsClientsMixin:
    """AWS client access, S3 JSON persistence, and time/prefix helpers for OpsInvestigationService."""

    def _elapsed_ms(self, started: float) -> int:
        return max(0, int((perf_counter() - started) * 1000))

    def _default_lambda_log_group(self) -> str:
        function_name = os.getenv("AWS_LAMBDA_FUNCTION_NAME", "").strip()
        if not function_name:
            function_name = os.getenv("DECISIONDOC_LAMBDA_FUNCTION_NAME", "").strip()
        if not function_name:
            return ""
        return f"/aws/lambda/{function_name}"

    def _bucket(self) -> str:
        bucket = os.getenv("DECISIONDOC_S3_BUCKET", "").strip()
        if not bucket:
            raise RuntimeError("Ops investigation storage is not configured.")
        return bucket

    def _prefix(self) -> str:
        prefix = os.getenv("DECISIONDOC_S3_PREFIX", "decisiondoc-ai/").strip()
        if prefix and not prefix.endswith("/"):
            prefix = f"{prefix}/"
        return prefix

    def _index_key(self, incident_key: str) -> str:
        return f"{self._prefix()}reports/incidents/index/{incident_key}.json"

    def _report_prefix(self, *, incident_key: str, run_id: str) -> str:
        return f"{self._prefix()}reports/incidents/{incident_key}/{run_id}/"

    def _build_run_id(self, now: datetime) -> str:
        return f"{now.strftime('%Y%m%d-%H%M%S')}-{uuid4().hex[:4]}"

    def _read_s3_json(self, key: str) -> dict[str, Any] | None:
        try:
            obj = self._s3().get_object(Bucket=self._bucket(), Key=key)
            raw = obj["Body"].read().decode("utf-8")
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                return parsed
            return None
        except Exception:
            return None

    def _write_s3_json(self, key: str, payload: dict[str, Any]) -> None:
        data = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self._s3().put_object(Bucket=self._bucket(), Key=key, Body=data, ContentType="application/json")
        self._s3_put_count += 1

    def _cloudwatch(self):
        if self._cloudwatch_client is not None:
            return self._cloudwatch_client
        try:
            import boto3  # type: ignore
        except ImportError as exc:  # pragma: no cover - runtime dependent
            raise RuntimeError("AWS SDK unavailable.") from exc
        self._cloudwatch_client = boto3.client("cloudwatch")
        return self._cloudwatch_client

    def _logs(self):
        if self._logs_client is not None:
            return self._logs_client
        try:
            import boto3  # type: ignore
        except ImportError as exc:  # pragma: no cover - runtime dependent
            raise RuntimeError("AWS SDK unavailable.") from exc
        self._logs_client = boto3.client("logs")
        return self._logs_client

    def _s3(self):
        if self._s3_client is not None:
            return self._s3_client
        try:
            import boto3  # type: ignore
        except ImportError as exc:  # pragma: no cover - runtime dependent
            raise RuntimeError("AWS SDK unavailable.") from exc
        self._s3_client = boto3.client("s3")
        return self._s3_client

    def _now(self) -> datetime:
        if self.now_provider is not None:
            now = self.now_provider()
            if now.tzinfo is None:
                return now.replace(tzinfo=UTC)
            return now.astimezone(UTC)
        return datetime.now(UTC)
