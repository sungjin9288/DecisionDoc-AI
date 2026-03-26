"""Tests for POST /generate/rewrite-section endpoint.

The endpoint accepts a bundle_id, section_title, current_content, and instruction,
then calls the LLM to rewrite just that one section (no full regeneration).
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


def _create_client(tmp_path, monkeypatch):
    monkeypatch.setenv("DECISIONDOC_PROVIDER", "mock")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DECISIONDOC_ENV", "dev")
    monkeypatch.setenv("DECISIONDOC_MAINTENANCE", "0")
    monkeypatch.delenv("DECISIONDOC_API_KEY",  raising=False)
    monkeypatch.delenv("DECISIONDOC_API_KEYS", raising=False)
    from app.main import create_app
    return TestClient(create_app())


_VALID_BODY = {
    "bundle_id": "tech_decision",
    "section_title": "## 배경",
    "current_content": "현재 시스템은 모놀리식 아키텍처로 구성되어 있습니다.",
    "instruction": "마이크로서비스 전환 필요성을 강조하여 더 설득력 있게 작성해 주세요.",
}


# ── 1. success ────────────────────────────────────────────────────────────────

def test_rewrite_section_returns_200(tmp_path, monkeypatch):
    """Happy path: valid payload returns 200 with 'rewritten' field."""
    client = _create_client(tmp_path, monkeypatch)
    res = client.post("/generate/rewrite-section", json=_VALID_BODY)
    assert res.status_code == 200


def test_rewrite_section_returns_rewritten_field(tmp_path, monkeypatch):
    """Response JSON must contain the 'rewritten' key with a non-empty string."""
    client = _create_client(tmp_path, monkeypatch)
    data = client.post("/generate/rewrite-section", json=_VALID_BODY).json()
    assert "rewritten" in data
    assert isinstance(data["rewritten"], str)
    assert len(data["rewritten"]) > 0


# ── 2. empty instruction ──────────────────────────────────────────────────────

def test_rewrite_section_empty_instruction_returns_200(tmp_path, monkeypatch):
    """Empty instruction string is allowed — endpoint must still return 200."""
    client = _create_client(tmp_path, monkeypatch)
    body = {**_VALID_BODY, "instruction": ""}
    res = client.post("/generate/rewrite-section", json=body)
    assert res.status_code == 200


def test_rewrite_section_empty_instruction_has_rewritten(tmp_path, monkeypatch):
    """Even with empty instruction the 'rewritten' field must be present."""
    client = _create_client(tmp_path, monkeypatch)
    body = {**_VALID_BODY, "instruction": ""}
    data = client.post("/generate/rewrite-section", json=body).json()
    assert "rewritten" in data


# ── 3. unknown / arbitrary bundle_id ─────────────────────────────────────────

def test_rewrite_section_unknown_bundle_returns_200(tmp_path, monkeypatch):
    """Unknown bundle_id falls back to default mock provider; must return 200."""
    client = _create_client(tmp_path, monkeypatch)
    body = {**_VALID_BODY, "bundle_id": "nonexistent_bundle_xyz"}
    res = client.post("/generate/rewrite-section", json=body)
    assert res.status_code == 200


# ── 4. long content ───────────────────────────────────────────────────────────

def test_rewrite_section_long_content(tmp_path, monkeypatch):
    """Very long current_content must not crash the endpoint."""
    client = _create_client(tmp_path, monkeypatch)
    long_content = "긴 텍스트 내용입니다. " * 200  # ~4 000 chars
    body = {**_VALID_BODY, "current_content": long_content}
    res = client.post("/generate/rewrite-section", json=body)
    assert res.status_code == 200
    data = res.json()
    assert "rewritten" in data


# ── 5. provider error ─────────────────────────────────────────────────────────

def test_rewrite_section_provider_error_returns_500(tmp_path, monkeypatch):
    """If the provider raises an exception, the endpoint must return 500."""
    monkeypatch.setenv("DECISIONDOC_PROVIDER", "mock")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DECISIONDOC_ENV", "dev")
    monkeypatch.setenv("DECISIONDOC_MAINTENANCE", "0")
    monkeypatch.delenv("DECISIONDOC_API_KEY",  raising=False)
    monkeypatch.delenv("DECISIONDOC_API_KEYS", raising=False)

    from app.providers.mock_provider import MockProvider

    def _raise(*args, **kwargs):
        raise RuntimeError("simulated LLM failure")

    monkeypatch.setattr(MockProvider, "generate_raw", _raise)

    from app.main import create_app
    client = TestClient(create_app(), raise_server_exceptions=False)
    res = client.post("/generate/rewrite-section", json=_VALID_BODY)
    assert res.status_code == 500


# ── 6. missing required field ─────────────────────────────────────────────────

def test_rewrite_section_missing_field_returns_422(tmp_path, monkeypatch):
    """Missing required field (instruction) must return 422 Unprocessable Entity."""
    client = _create_client(tmp_path, monkeypatch)
    body = {
        "bundle_id": "tech_decision",
        "section_title": "## 배경",
        "current_content": "내용입니다.",
        # 'instruction' deliberately omitted
    }
    res = client.post("/generate/rewrite-section", json=body)
    assert res.status_code == 422


# ── 7. no LLM call on maintenance mode ───────────────────────────────────────

def test_rewrite_section_maintenance_returns_503(tmp_path, monkeypatch):
    """Endpoint must be blocked during maintenance mode."""
    monkeypatch.setenv("DECISIONDOC_PROVIDER", "mock")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DECISIONDOC_ENV", "dev")
    monkeypatch.setenv("DECISIONDOC_MAINTENANCE", "1")
    monkeypatch.delenv("DECISIONDOC_API_KEY",  raising=False)
    monkeypatch.delenv("DECISIONDOC_API_KEYS", raising=False)
    from app.main import create_app
    client = TestClient(create_app())
    res = client.post("/generate/rewrite-section", json=_VALID_BODY)
    assert res.status_code == 503
