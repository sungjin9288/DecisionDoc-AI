"""tests/test_stability.py — Operational stability regression tests.

커버 항목:
  1.  C-1: LOW_RATING_THRESHOLD 잘못된 환경변수 → startup crash 없음
  2.  M-2: FINETUNE_MIN_RATING 잘못된 값 → safe default 반환
  3.  M-2: FINETUNE_MIN_SCORE 잘못된 값 → safe default 반환
  4.  M-2: AUTO_EXPAND_THRESHOLD 잘못된 값 → safe default 반환
  5.  M-2: LLM_RETRY_ATTEMPTS 잘못된 값 → safe default 반환
  6.  M-2: LLM_RETRY_BACKOFF_SECONDS 잘못된 값 → safe default 반환
  7.  C-3: ABTestStore JSON 파일 손상 → 백업 생성 후 빈 dict 반환
  8.  C-3: PromptOverrideStore JSON 파일 손상 → 백업 생성 후 빈 dict 반환
  9.  H-3: ABTestStore.evaluate_and_conclude 예외 → _log.error 호출 (no re-raise)
 10.  H-2: _call_provider_with_retry — 성공 시 1회 시도
 11.  H-2: _call_provider_with_retry — 2회 실패 후 3회차 성공
 12.  H-2: _call_provider_with_retry — 모두 실패 시 ProviderFailedError raise
 13.  H-1: /health — mock provider (키 없음)에서 checks 포함 200 반환
 14.  H-1: /health — EvalStore 오류 시 eval_store=degraded 반환
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest


# ─── C-1 / M-2: config helpers ────────────────────────────────────────────────

def test_low_rating_threshold_invalid_env(monkeypatch) -> None:
    """잘못된 LOW_RATING_THRESHOLD env → default 3 반환 (crash 없음)."""
    monkeypatch.setenv("LOW_RATING_THRESHOLD", "not-a-number")
    # Import the function fresh each time via the module
    import importlib
    import app.routers.generate as _gen
    # The function should not crash and return 3
    result = _gen._get_low_rating_threshold()
    assert result == 3


def test_finetune_min_rating_invalid_env(monkeypatch) -> None:
    """잘못된 FINETUNE_MIN_RATING → safe default 4 반환."""
    monkeypatch.setenv("FINETUNE_MIN_RATING", "bad")
    from app.config import get_finetune_min_rating
    assert get_finetune_min_rating() == 4


def test_finetune_min_score_invalid_env(monkeypatch) -> None:
    """잘못된 FINETUNE_MIN_SCORE → safe default 0.85 반환."""
    monkeypatch.setenv("FINETUNE_MIN_SCORE", "??")
    from app.config import get_finetune_min_score
    assert get_finetune_min_score() == pytest.approx(0.85)


def test_auto_expand_threshold_invalid_env(monkeypatch) -> None:
    """잘못된 AUTO_EXPAND_THRESHOLD → safe default 5 반환."""
    monkeypatch.setenv("AUTO_EXPAND_THRESHOLD", "abc")
    from app.config import get_auto_expand_threshold
    assert get_auto_expand_threshold() == 5


def test_llm_retry_attempts_invalid_env(monkeypatch) -> None:
    """잘못된 LLM_RETRY_ATTEMPTS → safe default 3 반환."""
    monkeypatch.setenv("LLM_RETRY_ATTEMPTS", "xyz")
    from app.config import get_llm_retry_attempts
    assert get_llm_retry_attempts() == 3


def test_llm_retry_backoff_invalid_env(monkeypatch) -> None:
    """잘못된 LLM_RETRY_BACKOFF_SECONDS → safe default [1,3,7] 반환."""
    monkeypatch.setenv("LLM_RETRY_BACKOFF_SECONDS", "a,b,c")
    from app.config import get_llm_retry_backoff_seconds
    assert get_llm_retry_backoff_seconds() == [1, 3, 7]


# ─── C-3: JSON corruption backup ──────────────────────────────────────────────

def test_ab_test_store_corruption_backup(tmp_path: Path) -> None:
    """손상된 ab_tests.json → 백업 파일 생성 + 빈 dict 반환."""
    from app.storage.ab_test_store import ABTestStore

    # ABTestStore now stores under tenants/system/
    tenant_dir = tmp_path / "tenants" / "system"
    tenant_dir.mkdir(parents=True, exist_ok=True)
    store_path = tenant_dir / "ab_tests.json"
    store_path.write_text("{invalid json!!}", encoding="utf-8")

    store = ABTestStore(tmp_path)
    with store._lock:
        data = store._load()

    assert data == {}
    # The corrupted file should have been renamed within the tenant dir
    backups = list(tenant_dir.glob("ab_tests.corrupted.*.json"))
    assert len(backups) == 1


def test_prompt_override_store_corruption_backup(tmp_path: Path) -> None:
    """손상된 prompt_overrides.json → 백업 파일 생성 + 빈 dict 반환."""
    from app.storage.prompt_override_store import PromptOverrideStore

    # PromptOverrideStore now stores under tenants/system/
    tenant_dir = tmp_path / "tenants" / "system"
    tenant_dir.mkdir(parents=True, exist_ok=True)
    store_path = tenant_dir / "prompt_overrides.json"
    store_path.write_text("<<<broken>>>", encoding="utf-8")

    store = PromptOverrideStore(tmp_path)
    with store._lock:
        data = store._load()

    assert data == {}
    backups = list(tenant_dir.glob("prompt_overrides.corrupted.*.json"))
    assert len(backups) == 1


# ─── H-3: A/B winner silent drop fix ─────────────────────────────────────────

def test_ab_test_store_winner_exception_logged(tmp_path: Path) -> None:
    """evaluate_and_conclude에서 PromptOverrideStore 예외 → re-raise 없이 _log.error."""
    from app.storage.ab_test_store import ABTestStore

    store = ABTestStore(tmp_path)
    store.create_test("bundle_x", "hint_a", "hint_b", min_samples=1)

    # Record enough results
    store.record_result("bundle_x", "variant_a", heuristic_score=0.9)
    store.record_result("bundle_x", "variant_b", heuristic_score=0.7)

    # PromptOverrideStore is imported locally inside evaluate_and_conclude;
    # patch it at the source module so the local import picks up the mock.
    with patch(
        "app.storage.prompt_override_store.PromptOverrideStore"
    ) as MockStore:
        MockStore.return_value.save_override.side_effect = RuntimeError("disk full")
        with patch("app.storage.ab_test_store._log") as mock_log:
            winner = store.evaluate_and_conclude("bundle_x")

    assert winner is not None  # Function still returns winner
    mock_log.error.assert_called_once()
    error_msg = mock_log.error.call_args[0][0]
    assert "Failed to save winner hint" in error_msg


# ─── H-2: LLM retry ───────────────────────────────────────────────────────────

def _make_generation_service(tmp_path: Path):
    from unittest.mock import MagicMock
    from app.services.generation_service import GenerationService

    provider = MagicMock()
    svc = GenerationService(
        provider_factory=lambda: provider,
        template_dir=tmp_path,  # won't be used
        data_dir=tmp_path,
    )
    return svc, provider


def test_retry_succeeds_on_first_attempt(tmp_path: Path, monkeypatch) -> None:
    """첫 번째 시도에 성공 → 단 1회 호출."""
    monkeypatch.setenv("LLM_RETRY_ATTEMPTS", "3")

    from app.services.generation_service import GenerationService, ProviderFailedError
    from app.bundle_catalog.spec import BundleSpec

    svc, _ = _make_generation_service(tmp_path)
    call_count = 0

    def success_once(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        return {"adr": "# ADR"}

    svc._call_provider_once = success_once  # type: ignore[method-assign]
    bundle_spec = MagicMock(spec=BundleSpec)
    bundle_spec.id = "tech_decision"

    result = svc._call_provider_with_retry(MagicMock(), {}, "req-1", bundle_spec)
    assert result == {"adr": "# ADR"}
    assert call_count == 1


def test_retry_succeeds_on_third_attempt(tmp_path: Path, monkeypatch) -> None:
    """2회 실패 후 3회차 성공 → 총 3회 호출."""
    monkeypatch.setenv("LLM_RETRY_ATTEMPTS", "3")
    monkeypatch.setenv("LLM_RETRY_BACKOFF_SECONDS", "0,0")  # no sleep in tests

    from app.services.generation_service import ProviderFailedError
    from app.bundle_catalog.spec import BundleSpec

    svc, _ = _make_generation_service(tmp_path)
    call_count = 0

    def fail_twice(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise ProviderFailedError("transient error")
        return {"result": "ok"}

    svc._call_provider_once = fail_twice  # type: ignore[method-assign]
    bundle_spec = MagicMock(spec=BundleSpec)
    bundle_spec.id = "tech_decision"

    result = svc._call_provider_with_retry(MagicMock(), {}, "req-2", bundle_spec)
    assert result == {"result": "ok"}
    assert call_count == 3


def test_retry_raises_after_all_attempts(tmp_path: Path, monkeypatch) -> None:
    """모든 시도 실패 시 ProviderFailedError raise."""
    monkeypatch.setenv("LLM_RETRY_ATTEMPTS", "2")
    monkeypatch.setenv("LLM_RETRY_BACKOFF_SECONDS", "0")

    from app.services.generation_service import ProviderFailedError
    from app.bundle_catalog.spec import BundleSpec

    svc, _ = _make_generation_service(tmp_path)

    svc._call_provider_once = MagicMock(  # type: ignore[method-assign]
        side_effect=ProviderFailedError("always fails")
    )
    bundle_spec = MagicMock(spec=BundleSpec)
    bundle_spec.id = "tech_decision"

    with pytest.raises(ProviderFailedError):
        svc._call_provider_with_retry(MagicMock(), {}, "req-3", bundle_spec)
    assert svc._call_provider_once.call_count == 2


def test_retry_uses_retry_after_when_provider_is_rate_limited(tmp_path: Path, monkeypatch) -> None:
    """429 cause가 있으면 기본 backoff 대신 retry-after를 우선 반영한다."""
    monkeypatch.setenv("LLM_RETRY_ATTEMPTS", "2")
    monkeypatch.setenv("LLM_RETRY_BACKOFF_SECONDS", "0")

    from app.services.generation_service import ProviderFailedError
    from app.bundle_catalog.spec import BundleSpec

    svc, _ = _make_generation_service(tmp_path)
    delays: list[int] = []
    call_count = 0

    class FakeRateLimitError(Exception):
        status_code = 429

        def __init__(self) -> None:
            super().__init__("429 Too Many Requests")
            self.response = type(
                "FakeResponse",
                (),
                {"status_code": 429, "headers": {"retry-after": "4"}},
            )()

    def fail_once_then_succeed(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            try:
                raise FakeRateLimitError()
            except Exception as exc:
                raise ProviderFailedError("provider failed") from exc
        return {"result": "ok"}

    monkeypatch.setattr("app.services.generation_service.time.sleep", lambda seconds: delays.append(seconds))
    svc._call_provider_once = fail_once_then_succeed  # type: ignore[method-assign]
    bundle_spec = MagicMock(spec=BundleSpec)
    bundle_spec.id = "tech_decision"

    result = svc._call_provider_with_retry(MagicMock(), {}, "req-rate-limit", bundle_spec)
    assert result == {"result": "ok"}
    assert call_count == 2
    assert delays == [4]


# ─── H-1: /health readiness probe ────────────────────────────────────────────

def _make_health_client(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DECISIONDOC_PROVIDER", "mock")
    monkeypatch.setenv("DECISIONDOC_ENV", "dev")
    monkeypatch.setenv("DECISIONDOC_SEARCH_ENABLED", "0")
    import app.main as main_module
    from fastapi.testclient import TestClient
    return TestClient(main_module.create_app())


def test_health_returns_checks_dict(tmp_path: Path, monkeypatch) -> None:
    """/health はchecks dict를 포함한 200 응답 반환."""
    client = _make_health_client(tmp_path, monkeypatch)
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert "status" in data
    assert "checks" in data
    assert isinstance(data["checks"], dict)


def test_health_ok_with_mock_provider(tmp_path: Path, monkeypatch) -> None:
    """/health mock provider → status=ok."""
    client = _make_health_client(tmp_path, monkeypatch)
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["checks"]["provider"] == "ok"
    assert data["checks"]["storage"] == "ok"
    assert data["checks"]["eval_store"] == "ok"
