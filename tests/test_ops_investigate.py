import json

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

    def investigate(self, *, window_minutes, reason, stage, request_id):  # noqa: ANN001
        self.calls.append(
            {
                "window_minutes": window_minutes,
                "reason": reason,
                "stage": stage,
                "request_id": request_id,
            }
        )
        return {
            "incident_id": "incident-123",
            "summary": {"counts": {"lambda_errors": 2}},
            "statuspage_incident_url": "https://status.example/incidents/123",
            "report_s3_key": "decisiondoc-ai/reports/incidents/incident-123/report.json",
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
        json={"window_minutes": 15, "reason": "latency spike", "stage": "prod"},
    )
    assert ok.status_code == 200
    body = ok.json()
    assert body["incident_id"] == "incident-123"
    assert body["report_s3_key"].endswith("report.json")
    assert service.calls
    assert service.calls[-1]["window_minutes"] == 15
    assert service.calls[-1]["stage"] == "prod"


class _FakeCloudWatchClient:
    def get_metric_data(self, **kwargs):  # noqa: ANN003
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
    def filter_log_events(self, **kwargs):  # noqa: ANN003
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


class _FakeStatuspageClient:
    def create_investigating_incident(self, *, stage, incident_id):  # noqa: ANN001
        _ = stage, incident_id
        return "https://status.example/incidents/abc"


def test_ops_report_contains_no_sensitive_strings(monkeypatch):
    sentinel = "SUPER_SECRET_DO_NOT_STORE"
    sentinel_api_key = "VERY_SECRET_OPS_KEY_VALUE"
    monkeypatch.setenv("DECISIONDOC_S3_BUCKET", "ops-bucket")
    monkeypatch.setenv("DECISIONDOC_S3_PREFIX", "decisiondoc-ai/")
    monkeypatch.setenv("DECISIONDOC_HTTP_API_ID", "api-123")
    monkeypatch.setenv("DECISIONDOC_LAMBDA_FUNCTION_NAME", "decisiondoc-ai-prod")
    monkeypatch.setenv("DECISIONDOC_OPS_KEY", sentinel_api_key)

    fake_s3 = _FakeS3Client()
    service = OpsInvestigationService(
        cloudwatch_client=_FakeCloudWatchClient(),
        logs_client=_FakeLogsClient(),
        s3_client=fake_s3,
        statuspage_client=_FakeStatuspageClient(),
    )
    result = service.investigate(
        window_minutes=30,
        reason=sentinel,
        stage="prod",
        request_id="ops-req-1",
    )

    assert result["report_s3_key"].endswith("/report.json")
    assert result["statuspage_incident_url"] == "https://status.example/incidents/abc"

    stored_blob = "\n".join(fake_s3.objects.values())
    assert sentinel not in stored_blob
    assert sentinel_api_key not in stored_blob
    assert "requirements=" not in stored_blob
    assert "output_text" not in stored_blob
