import hashlib
import io
import json
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from app.ops.service import OpsInvestigationService


def _create_client(tmp_path, monkeypatch, ops_service):
    monkeypatch.setenv("DECISIONDOC_PROVIDER", "mock")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DECISIONDOC_TEMPLATE_VERSION", "v1")
    monkeypatch.setenv("DECISIONDOC_ENV", "dev")
    monkeypatch.setenv("DECISIONDOC_MAINTENANCE", "0")
    monkeypatch.setenv("DECISIONDOC_OPS_KEY", "ops-secret")
    monkeypatch.delenv("DECISIONDOC_API_KEY", raising=False)
    monkeypatch.delenv("DECISIONDOC_API_KEYS", raising=False)

    import app.main as main_module

    monkeypatch.setattr(main_module, "get_ops_service", lambda: ops_service)
    return TestClient(main_module.create_app())


class _FakeOpsService:
    def __init__(self):
        self.calls: list[dict] = []

    def investigate(self, *, window_minutes, reason, stage, request_id, force=False):  # noqa: ANN001
        self.calls.append(
            {
                "window_minutes": window_minutes,
                "reason": reason,
                "stage": stage,
                "request_id": request_id,
                "force": force,
            }
        )
        return {
            "incident_id": "incident-123",
            "incident_key": "inc-abc123def456",
            "deduped": False,
            "summary": {"counts": {"lambda_errors": 2}},
            "statuspage_incident_url": "https://status.example/incidents/123",
            "report_s3_key": "decisiondoc-ai/reports/incidents/incident-123/report.json",
            "statuspage_posted": True,
            "statuspage_error": None,
        }


def test_ops_investigate_auth_401_and_200(tmp_path, monkeypatch):
    service = _FakeOpsService()
    client = _create_client(tmp_path, monkeypatch, service)

    missing = client.post("/ops/investigate", json={})
    assert missing.status_code == 401
    assert missing.json()["code"] == "UNAUTHORIZED"

    wrong = client.post(
        "/ops/investigate",
        headers={"X-DecisionDoc-Ops-Key": "wrong"},
        json={"window_minutes": 15},
    )
    assert wrong.status_code == 401
    assert wrong.json()["code"] == "UNAUTHORIZED"

    ok = client.post(
        "/ops/investigate",
        headers={"X-DecisionDoc-Ops-Key": "ops-secret"},
        json={"window_minutes": 15, "reason": "latency spike", "stage": "prod", "force": True},
    )
    assert ok.status_code == 200
    body = ok.json()
    assert body["incident_id"] == "incident-123"
    assert body["report_s3_key"].endswith("report.json")
    assert service.calls
    assert service.calls[-1]["window_minutes"] == 15
    assert service.calls[-1]["stage"] == "prod"
    assert service.calls[-1]["force"] is True


class _FakeCloudWatchClient:
    def __init__(self):
        self.calls = 0

    def get_metric_data(self, **kwargs):  # noqa: ANN003
        self.calls += 1
        assert "MetricDataQueries" in kwargs
        return {
            "MetricDataResults": [
                {"Id": "lambda_invocations", "Values": [12]},
                {"Id": "lambda_errors", "Values": [3]},
                {"Id": "lambda_throttles", "Values": [1]},
                {"Id": "lambda_duration_p95", "Values": [245.4]},
                {"Id": "api_count", "Values": [20]},
                {"Id": "api_4xx", "Values": [5]},
                {"Id": "api_5xx", "Values": [2]},
                {"Id": "api_integration_latency_p95", "Values": [180.0]},
            ]
        }


class _FakeLogsClient:
    def __init__(self):
        self.calls = 0

    def filter_log_events(self, **kwargs):  # noqa: ANN003
        self.calls += 1
        _ = kwargs
        sentinel = "SUPER_SECRET_DO_NOT_STORE"
        return {
            "events": [
                {
                    "message": json.dumps(
                        {
                            "event": "request.failed",
                            "error_code": "PROVIDER_FAILED",
                            "request_id": "req-1",
                            "raw": sentinel,
                            "llm_prompt_tokens": 100,
                            "llm_output_tokens": 50,
                            "llm_total_tokens": 150,
                        }
                    )
                },
                {
                    "message": json.dumps(
                        {
                            "event": "request.completed",
                            "request_id": "req-2",
                            "llm_prompt_tokens": 80,
                            "llm_output_tokens": 40,
                            "llm_total_tokens": 120,
                        }
                    )
                },
            ]
        }


class _FakeS3Client:
    def __init__(self):
        self.objects: dict[str, str] = {}

    def put_object(self, *, Bucket, Key, Body, ContentType):  # noqa: N803
        _ = Bucket, ContentType
        self.objects[Key] = Body.decode("utf-8")

    def get_object(self, *, Bucket, Key):  # noqa: N803
        _ = Bucket
        if Key not in self.objects:
            raise KeyError(Key)
        return {"Body": io.BytesIO(self.objects[Key].encode("utf-8"))}


class _FakeStatuspageClient:
    def __init__(self, should_fail=False):
        self.should_fail = should_fail
        self.create_calls = 0
        self.update_calls = 0

    def create_investigating_incident(self, *, stage, incident_key):  # noqa: ANN001
        self.create_calls += 1
        _ = stage, incident_key
        if self.should_fail:
            raise RuntimeError("statuspage failed")
        return {
            "incident_id": "status-inc-123",
            "incident_url": "https://status.example/incidents/abc",
        }

    def post_investigating_update(self, *, incident_id):  # noqa: ANN001
        self.update_calls += 1
        _ = incident_id
        if self.should_fail:
            raise RuntimeError("statuspage failed")


def _iso_utc(dt: datetime) -> str:
    return dt.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _incident_key(*, stage: str, window_minutes: int, bucket_seconds: int, now: datetime, reason: str) -> str:
    reason_norm = reason.replace("\r", " ").replace("\n", " ").strip().lower()
    reason_norm = " ".join(reason_norm.split())[:80]
    bucket = int(now.timestamp()) // bucket_seconds
    material = f"{stage}|{window_minutes}|{bucket}|{reason_norm}"
    digest = hashlib.sha256(material.encode("utf-8")).hexdigest()[:12]
    return f"inc-{digest}"


def _ops_service(monkeypatch, *, now, fake_s3, fake_cw, fake_logs, fake_statuspage):
    monkeypatch.setenv("DECISIONDOC_S3_BUCKET", "ops-bucket")
    monkeypatch.setenv("DECISIONDOC_S3_PREFIX", "decisiondoc-ai/")
    monkeypatch.setenv("DECISIONDOC_HTTP_API_ID", "api-123")
    monkeypatch.setenv("DECISIONDOC_LAMBDA_FUNCTION_NAME", "decisiondoc-ai-prod")
    monkeypatch.setenv("DECISIONDOC_INVESTIGATE_DEDUP_TTL_SECONDS", "300")
    monkeypatch.setenv("DECISIONDOC_INVESTIGATE_BUCKET_SECONDS", "300")
    monkeypatch.setenv("DECISIONDOC_INVESTIGATE_STATUSPAGE_UPDATE_MIN_SECONDS", "600")
    monkeypatch.delenv("DECISIONDOC_OPS_STATUSPAGE_STRICT", raising=False)
    return OpsInvestigationService(
        cloudwatch_client=fake_cw,
        logs_client=fake_logs,
        s3_client=fake_s3,
        statuspage_client=fake_statuspage,
        now_provider=lambda: now,
    )


def test_investigate_deduped_returns_cached_without_collectors(monkeypatch):
    now = datetime(2026, 2, 20, 12, 34, 56, tzinfo=UTC)
    fake_s3 = _FakeS3Client()
    fake_cw = _FakeCloudWatchClient()
    fake_logs = _FakeLogsClient()
    fake_status = _FakeStatuspageClient()
    service = _ops_service(
        monkeypatch,
        now=now,
        fake_s3=fake_s3,
        fake_cw=fake_cw,
        fake_logs=fake_logs,
        fake_statuspage=fake_status,
    )

    incident_key = _incident_key(stage="prod", window_minutes=30, bucket_seconds=300, now=now, reason="Elevated 5xx")
    index_key = f"decisiondoc-ai/reports/incidents/index/{incident_key}.json"
    latest_report_prefix = f"decisiondoc-ai/reports/incidents/{incident_key}/20260220-120000-abcd/"
    fake_s3.objects[index_key] = json.dumps(
        {
            "incident_key": incident_key,
            "stage": "prod",
            "window_minutes": 30,
            "reason": "elevated 5xx",
            "updated_at": _iso_utc(now - timedelta(seconds=60)),
            "ttl_seconds": 300,
            "latest_report_prefix": latest_report_prefix,
            "summary": {"counts": {"lambda_errors": 99}},
            "statuspage": {
                "incident_id": "status-inc-1",
                "incident_url": "https://status.example/incidents/1",
                "last_state": "investigating",
                "last_update_at": _iso_utc(now - timedelta(seconds=60)),
            },
        }
    )

    result = service.investigate(
        window_minutes=30,
        reason="Elevated 5xx",
        stage="prod",
        request_id="ops-req-1",
        force=False,
    )

    assert result["deduped"] is True
    assert result["incident_key"] == incident_key
    assert result["summary"]["counts"]["lambda_errors"] == 99
    assert result["report_s3_key"] == f"{latest_report_prefix}report.json"
    assert fake_cw.calls == 0
    assert fake_logs.calls == 0
    assert fake_status.create_calls == 0
    assert fake_status.update_calls == 0


def test_investigate_force_bypasses_dedupe_and_writes_new_report(monkeypatch):
    now = datetime(2026, 2, 20, 12, 34, 56, tzinfo=UTC)
    fake_s3 = _FakeS3Client()
    fake_cw = _FakeCloudWatchClient()
    fake_logs = _FakeLogsClient()
    fake_status = _FakeStatuspageClient()
    service = _ops_service(
        monkeypatch,
        now=now,
        fake_s3=fake_s3,
        fake_cw=fake_cw,
        fake_logs=fake_logs,
        fake_statuspage=fake_status,
    )

    incident_key = _incident_key(stage="prod", window_minutes=30, bucket_seconds=300, now=now, reason="Elevated 5xx")
    index_key = f"decisiondoc-ai/reports/incidents/index/{incident_key}.json"
    fake_s3.objects[index_key] = json.dumps(
        {
            "incident_key": incident_key,
            "stage": "prod",
            "window_minutes": 30,
            "reason": "elevated 5xx",
            "updated_at": _iso_utc(now - timedelta(seconds=60)),
            "ttl_seconds": 300,
            "latest_report_prefix": f"decisiondoc-ai/reports/incidents/{incident_key}/20260220-120000-abcd/",
            "statuspage": {
                "incident_id": "status-inc-1",
                "incident_url": "https://status.example/incidents/1",
                "last_state": "investigating",
            },
        }
    )

    result = service.investigate(
        window_minutes=30,
        reason="Elevated 5xx",
        stage="prod",
        request_id="ops-req-1",
        force=True,
    )

    assert result["deduped"] is False
    assert result["incident_key"] == incident_key
    assert result["report_s3_key"] in fake_s3.objects
    assert fake_cw.calls == 1
    assert fake_logs.calls == 1
    assert fake_status.create_calls == 0
    assert fake_status.update_calls == 1


def test_statuspage_incident_reused_not_recreated(monkeypatch):
    now = datetime(2026, 2, 20, 12, 34, 56, tzinfo=UTC)
    fake_s3 = _FakeS3Client()
    fake_cw = _FakeCloudWatchClient()
    fake_logs = _FakeLogsClient()
    fake_status = _FakeStatuspageClient()
    service = _ops_service(
        monkeypatch,
        now=now,
        fake_s3=fake_s3,
        fake_cw=fake_cw,
        fake_logs=fake_logs,
        fake_statuspage=fake_status,
    )

    incident_key = _incident_key(stage="prod", window_minutes=30, bucket_seconds=300, now=now, reason="Elevated 5xx")
    index_key = f"decisiondoc-ai/reports/incidents/index/{incident_key}.json"
    fake_s3.objects[index_key] = json.dumps(
        {
            "incident_key": incident_key,
            "stage": "prod",
            "window_minutes": 30,
            "reason": "elevated 5xx",
            "updated_at": _iso_utc(now - timedelta(seconds=301)),
            "ttl_seconds": 300,
            "latest_report_prefix": f"decisiondoc-ai/reports/incidents/{incident_key}/20260220-120000-abcd/",
            "statuspage": {
                "incident_id": "status-inc-1",
                "incident_url": "https://status.example/incidents/1",
                "last_state": "investigating",
            },
        }
    )

    result = service.investigate(
        window_minutes=30,
        reason="Elevated 5xx",
        stage="prod",
        request_id="ops-req-1",
        force=False,
    )

    assert result["deduped"] is False
    assert fake_status.create_calls == 0
    assert fake_status.update_calls == 1
    assert result["statuspage_incident_url"] == "https://status.example/incidents/1"


def test_statuspage_failure_soft_does_not_fail_investigation_by_default(monkeypatch):
    now = datetime(2026, 2, 20, 12, 34, 56, tzinfo=UTC)
    fake_s3 = _FakeS3Client()
    fake_cw = _FakeCloudWatchClient()
    fake_logs = _FakeLogsClient()
    fake_status = _FakeStatuspageClient(should_fail=True)
    service = _ops_service(
        monkeypatch,
        now=now,
        fake_s3=fake_s3,
        fake_cw=fake_cw,
        fake_logs=fake_logs,
        fake_statuspage=fake_status,
    )

    result = service.investigate(
        window_minutes=30,
        reason="Elevated 5xx",
        stage="prod",
        request_id="ops-req-1",
        force=False,
    )

    assert result["deduped"] is False
    assert result["statuspage_posted"] is False
    assert result["statuspage_error"] == "Status page notification failed."
    assert result["report_s3_key"] in fake_s3.objects
    assert fake_cw.calls == 1
    assert fake_logs.calls == 1


def test_ops_report_contains_no_sensitive_strings(monkeypatch):
    now = datetime(2026, 2, 20, 12, 34, 56, tzinfo=UTC)
    sentinel = "SUPER_SECRET_DO_NOT_STORE"
    sentinel_api_key = "VERY_SECRET_OPS_KEY_VALUE"
    monkeypatch.setenv("DECISIONDOC_OPS_KEY", sentinel_api_key)

    fake_s3 = _FakeS3Client()
    fake_cw = _FakeCloudWatchClient()
    fake_logs = _FakeLogsClient()
    fake_status = _FakeStatuspageClient()
    service = _ops_service(
        monkeypatch,
        now=now,
        fake_s3=fake_s3,
        fake_cw=fake_cw,
        fake_logs=fake_logs,
        fake_statuspage=fake_status,
    )

    result = service.investigate(
        window_minutes=30,
        reason=sentinel,
        stage="prod",
        request_id="ops-req-1",
        force=False,
    )

    assert result["report_s3_key"].endswith("/report.json")
    assert result["statuspage_incident_url"] == "https://status.example/incidents/abc"

    stored_blob = "\n".join(fake_s3.objects.values())
    assert sentinel not in stored_blob
    assert sentinel_api_key not in stored_blob
    assert "requirements=" not in stored_blob
    assert "output_text" not in stored_blob
