"""Tests for local LLM endpoints (L-3).

These endpoints degrade gracefully when no local LLM is configured,
returning either 200 (with status=unavailable) or 503.
"""
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_local_llm_health_endpoint_exists():
    """GET /local-llm/health is reachable and returns a status field."""
    res = client.get("/local-llm/health")
    assert res.status_code in (200, 503), (
        f"Unexpected status {res.status_code}: {res.text[:200]}"
    )
    if res.status_code == 200:
        data = res.json()
        assert "status" in data, "Response must include 'status' field"


def test_local_llm_health_not_configured():
    """When LOCAL_LLM_BASE_URL is unset, /local-llm/health returns graceful response."""
    import os
    saved = os.environ.pop("LOCAL_LLM_BASE_URL", None)
    try:
        res = client.get("/local-llm/health")
        # Must not crash — either 200 (with unavailable status) or 503
        assert res.status_code in (200, 503)
        if res.status_code == 200:
            data = res.json()
            assert data.get("status") in (
                "unavailable", "healthy", "ok", "degraded", "not_configured", None
            )
    finally:
        if saved is not None:
            os.environ["LOCAL_LLM_BASE_URL"] = saved


def test_local_llm_models_endpoint_exists():
    """GET /local-llm/models is reachable (200, 401, or 503)."""
    res = client.get("/local-llm/models")
    # 401 = requires auth (valid), 200 = ok, 503 = LLM unavailable
    assert res.status_code in (200, 401, 503), (
        f"Unexpected status {res.status_code}: {res.text[:200]}"
    )
    if res.status_code == 200:
        data = res.json()
        assert isinstance(data, dict), "Response must be a JSON object"


def test_local_llm_models_not_configured():
    """When LOCAL_LLM_BASE_URL is unset, /local-llm/models returns graceful response."""
    import os
    saved = os.environ.pop("LOCAL_LLM_BASE_URL", None)
    try:
        res = client.get("/local-llm/models")
        assert res.status_code in (200, 401, 503)
    finally:
        if saved is not None:
            os.environ["LOCAL_LLM_BASE_URL"] = saved
