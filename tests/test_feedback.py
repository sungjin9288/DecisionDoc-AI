"""Tests for FeedbackStore and POST /feedback endpoint."""

import json

import pytest
from fastapi.testclient import TestClient

from app.storage.feedback_store import FeedbackStore


# ── Unit tests: FeedbackStore ─────────────────────────────────────


def test_feedback_store_save_writes_jsonl(tmp_path):
    """save() appends a JSONL record with feedback_id and timestamp."""
    store = FeedbackStore(data_dir=tmp_path)
    feedback_id = store.save(
        {
            "bundle_type": "tech_decision",
            "rating": 5,
            "comment": "Great!",
            "bundle_id": "b-1",
        }
    )
    assert isinstance(feedback_id, str)
    assert len(feedback_id) > 0

    lines = (tmp_path / "tenants" / "system" / "feedback.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["feedback_id"] == feedback_id
    assert record["rating"] == 5
    assert record["bundle_type"] == "tech_decision"
    assert "timestamp" in record


def test_feedback_store_get_high_rated_filters_correctly(tmp_path):
    """get_high_rated_examples() returns only matching bundle_type with rating >= min_rating."""
    store = FeedbackStore(data_dir=tmp_path)
    store.save({"bundle_type": "tech_decision", "rating": 5, "comment": "Excellent", "bundle_id": "b-1"})
    store.save({"bundle_type": "tech_decision", "rating": 2, "comment": "Bad", "bundle_id": "b-2"})
    store.save({"bundle_type": "proposal_kr", "rating": 5, "comment": "Good proposal", "bundle_id": "b-3"})

    results = store.get_high_rated_examples("tech_decision", min_rating=4)
    assert len(results) == 1
    assert results[0]["comment"] == "Excellent"


def test_feedback_store_get_high_rated_returns_empty_on_no_match(tmp_path):
    """Returns empty list when no records match the criteria."""
    store = FeedbackStore(data_dir=tmp_path)
    store.save({"bundle_type": "tech_decision", "rating": 1, "comment": "Bad", "bundle_id": "b-1"})

    results = store.get_high_rated_examples("tech_decision", min_rating=4)
    assert results == []


def test_feedback_store_get_high_rated_empty_file(tmp_path):
    """Returns empty list when feedback file does not exist."""
    store = FeedbackStore(data_dir=tmp_path)
    results = store.get_high_rated_examples("tech_decision")
    assert results == []


# ── Integration tests: POST /feedback ────────────────────────────


def _create_client(tmp_path, monkeypatch):
    monkeypatch.setenv("DECISIONDOC_PROVIDER", "mock")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DECISIONDOC_ENV", "dev")
    monkeypatch.setenv("DECISIONDOC_MAINTENANCE", "0")
    monkeypatch.delenv("DECISIONDOC_API_KEY", raising=False)
    monkeypatch.delenv("DECISIONDOC_API_KEYS", raising=False)

    from app.main import create_app

    return TestClient(create_app())


def test_post_feedback_returns_200(tmp_path, monkeypatch):
    client = _create_client(tmp_path, monkeypatch)
    response = client.post(
        "/feedback",
        json={
            "bundle_id": "b-123",
            "bundle_type": "tech_decision",
            "rating": 4,
            "comment": "Helpful!",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert "feedback_id" in body
    assert body["saved"] is True


def test_post_feedback_missing_fields_returns_422(tmp_path, monkeypatch):
    client = _create_client(tmp_path, monkeypatch)
    response = client.post("/feedback", json={"rating": 3})
    assert response.status_code == 422
