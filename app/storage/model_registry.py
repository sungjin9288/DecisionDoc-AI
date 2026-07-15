"""model_registry.py — 파인튜닝 모델 레지스트리.

학습된 OpenAI 파인튜닝 모델을 테넌트별로 추적하고 관리합니다.

Storage layout:
    data/tenants/{tenant_id}/model_registry.json  — list of model records

Record shape:
    {
      "model_id": str,           # e.g. "ft:gpt-4o-mini:org:decisiondoc:abc123"
      "base_model": str,         # "gpt-4o-mini" | "gpt-4o"
      "bundle_id": str | None,   # None = general model, str = bundle-specific
      "tenant_id": str,
      "status": "training" | "ready" | "failed" | "deprecated",
      "training_file_id": str,   # OpenAI file ID
      "record_count": int,
      "avg_score_before": float,
      "avg_score_after": float | None,
      "openai_job_id": str,
      "created_at": str,         # ISO 8601
      "ready_at": str | None,
      "eval_result": dict | None
    }
"""
from __future__ import annotations

import functools
import json
import logging
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.storage.base import atomic_write_text
from app.tenant import require_tenant_id

_log = logging.getLogger("decisiondoc.storage.model_registry")

_VALID_STATUSES = frozenset({"training", "ready", "failed", "deprecated"})
_path_locks: dict[Path, threading.Lock] = {}
_path_locks_guard = threading.Lock()


def _lock_for_path(path: Path) -> threading.Lock:
    with _path_locks_guard:
        return _path_locks.setdefault(path.resolve(), threading.Lock())


class ModelRegistry:
    """Thread-safe JSON store for fine-tuned model lifecycle management."""

    def __init__(self, data_dir: Path | None = None, *, tenant_id: str) -> None:
        if data_dir is None:
            data_dir = Path(os.getenv("DATA_DIR", "./data"))
        self._tenant_id = require_tenant_id(tenant_id)
        self._path = Path(data_dir) / "tenants" / self._tenant_id / "model_registry.json"
        self._lock = _lock_for_path(self._path)

    def _owns(self, model: Any) -> bool:
        if not isinstance(model, dict):
            return False
        stored_tenant_id = model.get("tenant_id")
        return stored_tenant_id is None or stored_tenant_id == self._tenant_id

    def _read_all(self) -> list[dict[str, Any]]:
        if not self._path.exists():
            return []
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            _log.warning(
                "Failed to load model registry for tenant %s: %s",
                self._tenant_id,
                exc,
            )
            return []
        if not isinstance(data, list):
            return []
        return [model for model in data if isinstance(model, dict)]

    def _read_owned(self) -> list[dict[str, Any]]:
        return [model for model in self._read_all() if self._owns(model)]

    def _save(self, models: list[dict[str, Any]]) -> None:
        atomic_write_text(
            self._path,
            json.dumps(models, ensure_ascii=False, indent=2),
        )

    # ── Public API ────────────────────────────────────────────────────────────

    def register_model(
        self,
        *,
        model_id: str,
        base_model: str,
        bundle_id: str | None,
        training_file_id: str,
        record_count: int,
        avg_score_before: float,
        openai_job_id: str,
    ) -> dict[str, Any]:
        """Register a new model in the registry with status='training'.

        Returns the created model record.
        """
        record: dict[str, Any] = {
            "model_id": model_id,
            "base_model": base_model,
            "bundle_id": bundle_id,
            "tenant_id": self._tenant_id,
            "status": "training",
            "training_file_id": training_file_id,
            "record_count": record_count,
            "avg_score_before": avg_score_before,
            "avg_score_after": None,
            "openai_job_id": openai_job_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "ready_at": None,
            "eval_result": None,
        }
        with self._lock:
            models = self._read_all()
            models.append(record)
            self._save(models)
        _log.info(
            "[ModelRegistry] Registered model_id=%s bundle=%s tenant=%s status=training",
            model_id, bundle_id, self._tenant_id,
        )
        return record

    def update_status(
        self,
        openai_job_id: str,
        status: str,
        *,
        model_id: str | None = None,
        ready_at: str | None = None,
    ) -> bool:
        """Update status (and optionally model_id, ready_at) by OpenAI job ID.

        Returns True if a record was found and updated, False otherwise.
        """
        if status not in _VALID_STATUSES:
            raise ValueError(f"Invalid status '{status}'. Must be one of {_VALID_STATUSES}")
        with self._lock:
            models = self._read_all()
            updated = False
            for m in models:
                if self._owns(m) and m.get("openai_job_id") == openai_job_id:
                    m["status"] = status
                    if model_id is not None:
                        m["model_id"] = model_id
                    if ready_at is not None:
                        m["ready_at"] = ready_at
                    updated = True
                    break
            if updated:
                self._save(models)
        return updated

    def update_eval_result(
        self,
        model_id: str,
        *,
        avg_score_after: float,
        eval_result: dict[str, Any] | None = None,
    ) -> bool:
        """Update avg_score_after and eval_result for a model.

        Returns True if found and updated.
        """
        with self._lock:
            models = self._read_all()
            updated = False
            for m in models:
                if self._owns(m) and m.get("model_id") == model_id:
                    m["avg_score_after"] = avg_score_after
                    if eval_result is not None:
                        m["eval_result"] = eval_result
                    updated = True
                    break
            if updated:
                self._save(models)
        return updated

    def get_active_model(self, bundle_id: str | None) -> dict[str, Any] | None:
        """Return the best 'ready' model for a bundle in this registry's tenant.

        Selection priority:
          1. Bundle-specific model (bundle_id matches) over general (bundle_id=None)
          2. Highest avg_score_after (or most-recently created if no eval)
        Returns None if no ready model exists.
        """
        with self._lock:
            models = self._read_owned()

        ready = [
            m for m in models
            if m.get("status") == "ready"
            and (m.get("bundle_id") == bundle_id or m.get("bundle_id") is None)
        ]
        if not ready:
            return None

        # Prefer bundle-specific over general
        bundle_specific = [m for m in ready if m.get("bundle_id") == bundle_id]
        candidates = bundle_specific if bundle_specific else ready

        # Sort: models with eval score first (desc), then by created_at (desc)
        def sort_key(m: dict[str, Any]):
            score = m.get("avg_score_after")
            ts = m.get("created_at", "")
            has_score = score is not None
            return (has_score, score or 0.0, ts)

        return sorted(candidates, key=sort_key, reverse=True)[0]

    def get_model(self, model_id: str) -> dict[str, Any] | None:
        """Return a single model record by model_id, or None."""
        with self._lock:
            models = self._read_owned()
        for m in models:
            if m.get("model_id") == model_id:
                return m
        return None

    def get_model_by_job(self, openai_job_id: str) -> dict[str, Any] | None:
        """Return a model record by OpenAI job ID, or None."""
        with self._lock:
            models = self._read_owned()
        for m in models:
            if m.get("openai_job_id") == openai_job_id:
                return m
        return None

    def list_models(
        self,
        *,
        bundle_id: str | None = None,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        """List models for one tenant with optional bundle and status filters."""
        with self._lock:
            results = self._read_owned()

        if bundle_id is not None:
            results = [m for m in results if m.get("bundle_id") == bundle_id]
        if status is not None:
            results = [m for m in results if m.get("status") == status]

        return results

    def deprecate_model(self, model_id: str) -> bool:
        """Set a model's status to 'deprecated'. Returns True if found."""
        with self._lock:
            models = self._read_all()
            updated = False
            for m in models:
                if self._owns(m) and m.get("model_id") == model_id:
                    m["status"] = "deprecated"
                    updated = True
                    break
            if updated:
                self._save(models)
        return updated

    def has_active_training(self, bundle_id: str | None) -> bool:
        """Return True if there is already a training job in progress."""
        with self._lock:
            models = self._read_owned()
        return any(
            m.get("status") == "training"
            and m.get("bundle_id") == bundle_id
            for m in models
        )


@functools.lru_cache(maxsize=50)
def get_model_registry(tenant_id: str) -> ModelRegistry:
    """Return a cached ModelRegistry bound to one tenant."""
    data_dir = Path(os.getenv("DATA_DIR", "./data"))
    return ModelRegistry(data_dir, tenant_id=tenant_id)


def clear_model_registry_cache() -> None:
    """Invalidate the registry cache."""
    get_model_registry.cache_clear()
