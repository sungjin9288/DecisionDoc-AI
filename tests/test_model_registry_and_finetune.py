"""tests/test_model_registry_and_finetune.py — ModelRegistry + FineTune 인프라 테스트.

커버 항목:
  Group 1: ModelRegistry unit tests (tests 1–13)
  Group 2: Config functions (tests 14–17)
  Group 3: get_provider_for_bundle (tests 18–19)
  Group 4: API endpoints (tests 20–24)
"""
from __future__ import annotations

import importlib.util
import os
import sys
import types
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest


# ── Optional-dependency stubs ─────────────────────────────────────────────────
# app/main.py imports several optional packages (docx, xlsxwriter, pptx,
# playwright) at module level. When those packages are not installed in the
# current environment we inject lightweight stubs into sys.modules so that the
# module import succeeds without actually needing the real packages.
#
# IMPORTANT: we only stub packages that are genuinely absent from the
# environment.  Stubbing an installed package at collection time would corrupt
# sys.modules for other test modules that legitimately use the real library.

def _stub_missing_module(name: str) -> None:
    """Insert a MagicMock stub for *name* only if the root package is not installed."""
    root = name.split(".")[0]
    if importlib.util.find_spec(root) is not None:
        return  # Real package is installed — leave sys.modules untouched
    parts = name.split(".")
    for i in range(1, len(parts) + 1):
        key = ".".join(parts[:i])
        if key not in sys.modules:
            sys.modules[key] = MagicMock()


for _mod in [
    "docx",
    "docx.shared",
    "docx.enum",
    "docx.enum.text",
    "xlsxwriter",
    "pptx",
    "pptx.util",
    "pptx.dml",
    "pptx.dml.color",
    "pptx.enum",
    "pptx.enum.text",
    "playwright",
    "playwright.async_api",
]:
    _stub_missing_module(_mod)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _make_registry(tmp_path: Path):
    from app.storage.model_registry import ModelRegistry
    return ModelRegistry(tmp_path)


def _reg_model(registry, **overrides) -> dict[str, Any]:
    """Register a test model with sensible defaults."""
    defaults = dict(
        model_id="ft:gpt-4o-mini:org:test:abc123",
        base_model="gpt-4o-mini",
        bundle_id="business_plan_kr",
        tenant_id="system",
        training_file_id="file-abc123",
        record_count=55,
        avg_score_before=0.72,
        openai_job_id="ftjob-abc123",
    )
    defaults.update(overrides)
    return registry.register_model(**defaults)


def _make_client(tmp_path: Path, monkeypatch):
    """Create a TestClient with model registry endpoints available."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DECISIONDOC_PROVIDER", "mock")
    monkeypatch.setenv("DECISIONDOC_ENV", "dev")
    monkeypatch.setenv("DECISIONDOC_OPS_KEY", "test-ops-key")
    monkeypatch.setenv("DECISIONDOC_SEARCH_ENABLED", "0")

    # Clear LRU cache so the new DATA_DIR is picked up
    from app.storage.model_registry import get_model_registry
    get_model_registry.cache_clear()

    import app.main as main_module
    from fastapi.testclient import TestClient
    return TestClient(main_module.create_app())


# ── Group 1: ModelRegistry unit tests ──────────────────────────────────────────

def test_01_register_model(tmp_path: Path) -> None:
    """register_model returns a record with all required fields and correct defaults."""
    registry = _make_registry(tmp_path)
    record = _reg_model(registry)

    assert record["model_id"] == "ft:gpt-4o-mini:org:test:abc123"
    assert record["status"] == "training"
    assert record["created_at"] is not None
    assert record["ready_at"] is None
    assert record["avg_score_after"] is None
    assert record["eval_result"] is None
    assert record["tenant_id"] == "system"
    assert record["base_model"] == "gpt-4o-mini"
    assert record["bundle_id"] == "business_plan_kr"
    assert record["training_file_id"] == "file-abc123"
    assert record["record_count"] == 55
    assert record["avg_score_before"] == pytest.approx(0.72)
    assert record["openai_job_id"] == "ftjob-abc123"


def test_02_register_model_persisted(tmp_path: Path) -> None:
    """A registered model is persisted and visible from a fresh registry instance."""
    registry = _make_registry(tmp_path)
    _reg_model(registry)

    # Create a brand-new instance pointing to the same directory
    from app.storage.model_registry import ModelRegistry
    registry2 = ModelRegistry(tmp_path)
    models = registry2.list_models(tenant_id="system")

    assert len(models) == 1
    assert models[0]["model_id"] == "ft:gpt-4o-mini:org:test:abc123"


def test_03_update_status_ready(tmp_path: Path) -> None:
    """update_status with 'ready' and ready_at timestamp reflects the change."""
    registry = _make_registry(tmp_path)
    _reg_model(registry)

    updated = registry.update_status(
        "ftjob-abc123",
        "ready",
        tenant_id="system",
        ready_at="2026-03-17T12:00:00+00:00",
    )

    assert updated is True
    model = registry.get_model("ft:gpt-4o-mini:org:test:abc123", "system")
    assert model is not None
    assert model["status"] == "ready"
    assert model["ready_at"] == "2026-03-17T12:00:00+00:00"


def test_04_update_status_failed(tmp_path: Path) -> None:
    """update_status with 'failed' marks the model correctly."""
    registry = _make_registry(tmp_path)
    _reg_model(registry)

    updated = registry.update_status("ftjob-abc123", "failed", tenant_id="system")

    assert updated is True
    model = registry.get_model("ft:gpt-4o-mini:org:test:abc123", "system")
    assert model is not None
    assert model["status"] == "failed"


def test_05_update_eval_result(tmp_path: Path) -> None:
    """update_eval_result stores avg_score_after and eval_result dict."""
    registry = _make_registry(tmp_path)
    _reg_model(registry)
    registry.update_status("ftjob-abc123", "ready", tenant_id="system")

    eval_data = {"sample_count": 10, "promoted": True}
    updated = registry.update_eval_result(
        "ft:gpt-4o-mini:org:test:abc123",
        tenant_id="system",
        avg_score_after=0.81,
        eval_result=eval_data,
    )

    assert updated is True
    model = registry.get_model("ft:gpt-4o-mini:org:test:abc123", "system")
    assert model is not None
    assert model["avg_score_after"] == pytest.approx(0.81)
    assert model["eval_result"] == eval_data


def test_06_get_active_model_none(tmp_path: Path) -> None:
    """An empty registry returns None for get_active_model."""
    registry = _make_registry(tmp_path)
    result = registry.get_active_model("business_plan_kr", "system")
    assert result is None


def test_07_get_active_model_returns_ready(tmp_path: Path) -> None:
    """get_active_model returns a model once it is promoted to 'ready'."""
    registry = _make_registry(tmp_path)
    _reg_model(registry)
    registry.update_status("ftjob-abc123", "ready", tenant_id="system")

    active = registry.get_active_model("business_plan_kr", "system")
    assert active is not None
    assert active["status"] == "ready"
    assert active["model_id"] == "ft:gpt-4o-mini:org:test:abc123"


def test_08_get_active_model_bundle_specific_preferred(tmp_path: Path) -> None:
    """A bundle-specific ready model takes priority over a general (bundle_id=None) model."""
    registry = _make_registry(tmp_path)

    # Register a general model (no bundle)
    _reg_model(
        registry,
        model_id="ft:gpt-4o-mini:org:test:general",
        bundle_id=None,
        openai_job_id="ftjob-general",
    )
    registry.update_status("ftjob-general", "ready", tenant_id="system")

    # Register a bundle-specific model
    _reg_model(
        registry,
        model_id="ft:gpt-4o-mini:org:test:specific",
        bundle_id="business_plan_kr",
        openai_job_id="ftjob-specific",
    )
    registry.update_status("ftjob-specific", "ready", tenant_id="system")

    active = registry.get_active_model("business_plan_kr", "system")
    assert active is not None
    assert active["model_id"] == "ft:gpt-4o-mini:org:test:specific"


def test_09_deprecate_model(tmp_path: Path) -> None:
    """deprecate_model sets status to 'deprecated' and get_active_model returns None."""
    registry = _make_registry(tmp_path)
    _reg_model(registry)
    registry.update_status("ftjob-abc123", "ready", tenant_id="system")

    result = registry.deprecate_model("ft:gpt-4o-mini:org:test:abc123", "system")
    assert result is True

    model = registry.get_model("ft:gpt-4o-mini:org:test:abc123", "system")
    assert model is not None
    assert model["status"] == "deprecated"

    active = registry.get_active_model("business_plan_kr", "system")
    assert active is None


def test_10_has_active_training(tmp_path: Path) -> None:
    """has_active_training is True while status='training', False after 'ready'."""
    registry = _make_registry(tmp_path)
    _reg_model(registry)

    assert registry.has_active_training("business_plan_kr", "system") is True

    registry.update_status("ftjob-abc123", "ready", tenant_id="system")
    assert registry.has_active_training("business_plan_kr", "system") is False


def test_11_list_models_filter(tmp_path: Path) -> None:
    """list_models with bundle_id filter returns only models for that bundle."""
    registry = _make_registry(tmp_path)
    _reg_model(
        registry,
        model_id="ft:gpt-4o-mini:org:test:bundle-a",
        bundle_id="bundle_a",
        openai_job_id="ftjob-a",
    )
    _reg_model(
        registry,
        model_id="ft:gpt-4o-mini:org:test:bundle-b",
        bundle_id="bundle_b",
        openai_job_id="ftjob-b",
    )

    bundle_a_models = registry.list_models(tenant_id="system", bundle_id="bundle_a")
    assert len(bundle_a_models) == 1
    assert bundle_a_models[0]["bundle_id"] == "bundle_a"

    bundle_b_models = registry.list_models(tenant_id="system", bundle_id="bundle_b")
    assert len(bundle_b_models) == 1
    assert bundle_b_models[0]["bundle_id"] == "bundle_b"

    all_models = registry.list_models(tenant_id="system")
    assert len(all_models) == 2


def test_12_get_model_not_found(tmp_path: Path) -> None:
    """get_model returns None for an unknown model_id."""
    registry = _make_registry(tmp_path)
    result = registry.get_model("ft:gpt-4o-mini:org:test:nonexistent", "system")
    assert result is None


def test_13_invalid_status_raises(tmp_path: Path) -> None:
    """update_status with an invalid status string raises ValueError."""
    registry = _make_registry(tmp_path)
    _reg_model(registry)

    with pytest.raises(ValueError, match="Invalid status"):
        registry.update_status("ftjob-abc123", "unknown", tenant_id="system")


# ── Group 2: Config functions ───────────────────────────────────────────────────

def test_14_config_finetune_auto_threshold_default() -> None:
    """get_finetune_auto_threshold returns 50 by default (no env var set)."""
    from app.config import get_finetune_auto_threshold

    # Ensure the env var is absent before reading the default
    original = os.environ.pop("FINETUNE_AUTO_THRESHOLD", None)
    try:
        assert get_finetune_auto_threshold() == 50
    finally:
        if original is not None:
            os.environ["FINETUNE_AUTO_THRESHOLD"] = original


def test_15_config_finetune_base_model_default() -> None:
    """get_finetune_base_model returns 'gpt-4o-mini' by default."""
    from app.config import get_finetune_base_model

    original = os.environ.pop("FINETUNE_BASE_MODEL", None)
    try:
        assert get_finetune_base_model() == "gpt-4o-mini"
    finally:
        if original is not None:
            os.environ["FINETUNE_BASE_MODEL"] = original


def test_16_config_finetune_promotion_threshold_default() -> None:
    """get_finetune_promotion_threshold returns 0.05 by default."""
    from app.config import get_finetune_promotion_threshold

    original = os.environ.pop("FINETUNE_PROMOTION_THRESHOLD", None)
    try:
        assert get_finetune_promotion_threshold() == pytest.approx(0.05)
    finally:
        if original is not None:
            os.environ["FINETUNE_PROMOTION_THRESHOLD"] = original


def test_17_config_env_override(monkeypatch) -> None:
    """Setting FINETUNE_AUTO_THRESHOLD=100 is returned by get_finetune_auto_threshold."""
    from app.config import get_finetune_auto_threshold

    monkeypatch.setenv("FINETUNE_AUTO_THRESHOLD", "100")
    assert get_finetune_auto_threshold() == 100


# ── Group 3: get_provider_for_bundle ───────────────────────────────────────────

def test_18_get_provider_for_bundle_no_model(tmp_path: Path, monkeypatch) -> None:
    """With an empty registry, get_provider_for_bundle returns the mock provider."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DECISIONDOC_PROVIDER", "mock")

    from app.storage.model_registry import get_model_registry
    get_model_registry.cache_clear()

    from app.providers.factory import get_provider_for_bundle
    from app.providers.mock_provider import MockProvider

    provider = get_provider_for_bundle("business_plan_kr", "system")
    assert isinstance(provider, MockProvider)


def test_19_get_provider_for_bundle_falls_back_on_error(monkeypatch) -> None:
    """If ModelRegistry.__init__ raises, get_provider_for_bundle still returns a provider."""
    monkeypatch.setenv("DECISIONDOC_PROVIDER", "mock")

    # Patch ModelRegistry to raise on instantiation
    import app.storage.model_registry as reg_mod
    original_init = reg_mod.ModelRegistry.__init__

    def _bad_init(self, *args, **kwargs):
        raise RuntimeError("simulated registry failure")

    monkeypatch.setattr(reg_mod.ModelRegistry, "__init__", _bad_init)

    from app.providers.factory import get_provider_for_bundle
    from app.providers.base import Provider

    # Should not raise — silently falls back
    provider = get_provider_for_bundle("business_plan_kr", "system")
    assert isinstance(provider, Provider)


# ── Group 4: API endpoints ──────────────────────────────────────────────────────

_OPS_HEADERS = {"X-DecisionDoc-Ops-Key": "test-ops-key"}


def test_20_get_models_empty(tmp_path: Path, monkeypatch) -> None:
    """GET /models returns an empty list when no models have been registered."""
    client = _make_client(tmp_path, monkeypatch)
    resp = client.get("/models")
    assert resp.status_code == 200
    assert resp.json() == []


def test_21_get_model_not_found(tmp_path: Path, monkeypatch) -> None:
    """GET /models/{model_id} returns 404 for an unknown model ID."""
    client = _make_client(tmp_path, monkeypatch)
    resp = client.get("/models/ft:gpt-4o-mini:org:test:nonexistent")
    assert resp.status_code == 404


def test_22_deprecate_model_not_found(tmp_path: Path, monkeypatch) -> None:
    """POST /admin/models/{model_id}/deprecate returns 404 for a non-existent model."""
    client = _make_client(tmp_path, monkeypatch)
    resp = client.post(
        "/admin/models/ft:gpt-4o-mini:org:test:ghost/deprecate",
        headers=_OPS_HEADERS,
    )
    assert resp.status_code == 404


def test_23_trigger_training_not_enough_data(tmp_path: Path, monkeypatch) -> None:
    """POST /admin/models/trigger-training returns triggered=False when data is insufficient."""
    client = _make_client(tmp_path, monkeypatch)
    resp = client.post(
        "/admin/models/trigger-training",
        json={"bundle_id": "test_bundle"},
        headers=_OPS_HEADERS,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["triggered"] is False
    assert "message" in data


def test_24_admin_list_jobs_no_api_key(tmp_path: Path, monkeypatch) -> None:
    """GET /admin/models/jobs returns [] gracefully when OPENAI_API_KEY is absent."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    client = _make_client(tmp_path, monkeypatch)
    resp = client.get("/admin/models/jobs", headers=_OPS_HEADERS)
    assert resp.status_code == 200
    assert resp.json() == []
