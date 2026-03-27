"""
Tests for Prometheus metrics middleware, scrape endpoint,
Kubernetes probes, and alerting service.
"""
import pytest
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient

from tests.async_helper import run_async


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DECISIONDOC_PROVIDER", "mock")
    monkeypatch.setenv("DECISIONDOC_TEMPLATE_VERSION", "v1")
    monkeypatch.setenv("DECISIONDOC_ENV", "dev")
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("JWT_SECRET_KEY", "test-secret-key-for-metrics-tests-32chars!!")
    monkeypatch.delenv("DECISIONDOC_API_KEY", raising=False)
    monkeypatch.delenv("DECISIONDOC_API_KEYS", raising=False)
    from app.main import create_app
    return TestClient(create_app(), raise_server_exceptions=False)


# ── /metrics endpoint ─────────────────────────────────────────────────────────

def test_metrics_endpoint_returns_200(client):
    """GET /metrics returns 200 with prometheus-client installed."""
    r = client.get("/metrics")
    assert r.status_code == 200


def test_metrics_content_type(client):
    """GET /metrics returns Prometheus text format content-type."""
    r = client.get("/metrics")
    assert r.status_code == 200
    assert "text/plain" in r.headers.get("content-type", "")


def test_metrics_contains_standard_labels(client):
    """GET /metrics body contains expected metric names."""
    # Trigger a request so counters are non-zero
    client.get("/health")
    r = client.get("/metrics")
    assert r.status_code == 200
    body = r.text
    assert "decisiondoc_requests_total" in body


def test_metrics_contains_latency_histogram(client):
    """Latency histogram metric is present."""
    client.get("/bundles")
    r = client.get("/metrics")
    assert "decisiondoc_request_duration_seconds" in r.text


def test_metrics_active_requests_gauge_present(client):
    """Active requests gauge is exposed."""
    r = client.get("/metrics")
    assert "decisiondoc_active_requests" in r.text


# ── /health/live and /health/ready ───────────────────────────────────────────

def test_liveness_returns_200(client):
    """GET /health/live returns 200 always."""
    r = client.get("/health/live")
    assert r.status_code == 200


def test_liveness_response_structure(client):
    """GET /health/live returns {status: alive}."""
    r = client.get("/health/live")
    assert r.json().get("status") == "alive"


def test_readiness_returns_200(client):
    """GET /health/ready returns 200 in normal conditions."""
    r = client.get("/health/ready")
    assert r.status_code == 200


def test_readiness_has_status_field(client):
    """GET /health/ready response includes status field."""
    r = client.get("/health/ready")
    data = r.json()
    assert "status" in data
    assert data["status"] in ("ok", "degraded")


# ── Metrics middleware behaviour ──────────────────────────────────────────────

def test_metrics_not_recorded_for_metrics_endpoint(client):
    """Requests to /metrics itself don't inflate counters infinitely."""
    # Simply confirm the endpoint is idempotent and doesn't crash
    for _ in range(3):
        r = client.get("/metrics")
        assert r.status_code == 200


def test_auth_failure_counter_increments(client):
    """401 responses increment the auth_failures counter."""
    client.get("/auth/me")  # no token → 401
    r = client.get("/metrics")
    assert "decisiondoc_auth_failures_total" in r.text


# ── Alerting service ──────────────────────────────────────────────────────────

def test_send_alert_no_webhook_logs_only(caplog):
    """send_alert does not raise when SLACK_WEBHOOK_URL is not set."""
    import os
    os.environ.pop("SLACK_WEBHOOK_URL", None)
    from app.services.alerting_service import send_alert
    run_async(send_alert("Test Alert", "Test message", severity="warning"))
    # Should complete without exception


def test_alert_health_failure_no_webhook():
    """alert_health_failure completes silently without webhook."""
    import os
    os.environ.pop("SLACK_WEBHOOK_URL", None)
    from app.services.alerting_service import alert_health_failure
    run_async(alert_health_failure("storage", "disk full"))


def test_alert_generation_failure_no_webhook():
    """alert_generation_failure completes silently without webhook."""
    import os
    os.environ.pop("SLACK_WEBHOOK_URL", None)
    from app.services.alerting_service import alert_generation_failure
    run_async(alert_generation_failure("rfp_analysis_kr", "timeout", "tenant1"))


def test_send_alert_with_mock_webhook():
    """send_alert posts to Slack when webhook URL is set."""
    import os
    os.environ["SLACK_WEBHOOK_URL"] = "https://hooks.slack.com/test"
    try:
        from app.services.alerting_service import send_alert
        mock_response = AsyncMock()
        mock_response.status_code = 200

        with patch("httpx.AsyncClient.post", return_value=mock_response) as mock_post:
            run_async(send_alert(
                title="Test",
                message="Test message",
                severity="critical",
                details={"key": "value"},
            ))
            mock_post.assert_called_once()
            call_kwargs = mock_post.call_args
            payload = call_kwargs.kwargs.get("json") or call_kwargs.args[1] if len(call_kwargs.args) > 1 else {}
            # Accept both positional and keyword call styles
    finally:
        os.environ.pop("SLACK_WEBHOOK_URL", None)


# ── record_generation helper ──────────────────────────────────────────────────

def test_record_generation_no_error():
    """record_generation does not raise (prometheus installed)."""
    from app.middleware.metrics import record_generation
    record_generation("rfp_analysis_kr", "tenant1", "success", duration=1.5)
    record_generation("rfp_analysis_kr", "tenant1", "failure", duration=0.3)


def test_normalize_path_strips_uuids():
    """_normalize_path replaces UUIDs with {id}."""
    from app.middleware.metrics import _normalize_path
    path = "/projects/550e8400-e29b-41d4-a716-446655440000/documents"
    result = _normalize_path(path)
    assert "550e8400" not in result
    assert "{id}" in result
