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

_log = logging.getLogger("decisiondoc.storage.model_registry")

_VALID_STATUSES = frozenset({"training", "ready", "failed", "deprecated"})


class ModelRegistry:
    """Thread-safe JSON store for fine-tuned model lifecycle management."""

    def __init__(self, data_dir: Path | None = None) -> None:
        if data_dir is None:
            data_dir = Path(os.getenv("DATA_DIR", "./data"))
        self._data_dir = Path(data_dir)
        self._lock = threading.Lock()

    def _registry_path(self, tenant_id: str) -> Path:
        path = self._data_dir / "tenants" / tenant_id / "model_registry.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def _load(self, tenant_id: str) -> list[dict[str, Any]]:
        path = self._registry_path(tenant_id)
        if not path.exists():
            return []
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return data if isinstance(data, list) else []
        except (json.JSONDecodeError, OSError) as exc:
            _log.warning("Failed to load model registry for tenant %s: %s", tenant_id, exc)
            return []

    def _save(self, tenant_id: str, models: list[dict[str, Any]]) -> None:
        path = self._registry_path(tenant_id)
        tmp = path.with_suffix(".tmp")
        try:
            tmp.write_text(json.dumps(models, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(path)
        except OSError as exc:
            _log.error("Failed to save model registry for tenant %s: %s", tenant_id, exc)
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass

    # ── Public API ────────────────────────────────────────────────────────────

    def register_model(
        self,
        *,
        model_id: str,
        base_model: str,
        bundle_id: str | None,
        tenant_id: str,
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
            "tenant_id": tenant_id,
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
            models = self._load(tenant_id)
            models.append(record)
            self._save(tenant_id, models)
        _log.info(
            "[ModelRegistry] Registered model_id=%s bundle=%s tenant=%s status=training",
            model_id, bundle_id, tenant_id,
        )
        return record

    def update_status(
        self,
        openai_job_id: str,
        status: str,
        *,
        tenant_id: str,
        model_id: str | None = None,
        ready_at: str | None = None,
    ) -> bool:
        """Update status (and optionally model_id, ready_at) by OpenAI job ID.

        Returns True if a record was found and updated, False otherwise.
        """
        if status not in _VALID_STATUSES:
            raise ValueError(f"Invalid status '{status}'. Must be one of {_VALID_STATUSES}")
        with self._lock:
            models = self._load(tenant_id)
            updated = False
            for m in models:
                if m.get("openai_job_id") == openai_job_id:
                    m["status"] = status
                    if model_id is not None:
                        m["model_id"] = model_id
                    if ready_at is not None:
                        m["ready_at"] = ready_at
                    updated = True
                    break
            if updated:
                self._save(tenant_id, models)
        return updated

    def update_eval_result(
        self,
        model_id: str,
        *,
        tenant_id: str,
        avg_score_after: float,
        eval_result: dict[str, Any] | None = None,
    ) -> bool:
        """Update avg_score_after and eval_result for a model.

        Returns True if found and updated.
        """
        with self._lock:
            models = self._load(tenant_id)
            updated = False
            for m in models:
                if m.get("model_id") == model_id:
                    m["avg_score_after"] = avg_score_after
                    if eval_result is not None:
                        m["eval_result"] = eval_result
                    updated = True
                    break
            if updated:
                self._save(tenant_id, models)
        return updated

    def get_active_model(
        self, bundle_id: str | None, tenant_id: str
    ) -> dict[str, Any] | None:
        """Return the best 'ready' model for a bundle+tenant.

        Selection priority:
          1. Bundle-specific model (bundle_id matches) over general (bundle_id=None)
          2. Highest avg_score_after (or most-recently created if no eval)
        Returns None if no ready model exists.
        """
        with self._lock:
            models = self._load(tenant_id)

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

    def get_model(self, model_id: str, tenant_id: str) -> dict[str, Any] | None:
        """Return a single model record by model_id, or None."""
        with self._lock:
            models = self._load(tenant_id)
        for m in models:
            if m.get("model_id") == model_id:
                return m
        return None

    def get_model_by_job(self, openai_job_id: str, tenant_id: str) -> dict[str, Any] | None:
        """Return a model record by OpenAI job ID, or None."""
        with self._lock:
            models = self._load(tenant_id)
        for m in models:
            if m.get("openai_job_id") == openai_job_id:
                return m
        return None

    def list_models(
        self,
        tenant_id: str | None = None,
        bundle_id: str | None = None,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        """List models with optional filters.

        If tenant_id is None, lists all tenants' models (scans all tenant dirs).
        """
        results: list[dict[str, Any]] = []

        if tenant_id is not None:
            with self._lock:
                models = self._load(tenant_id)
            results = list(models)
        else:
            # Scan all tenant directories
            tenants_dir = self._data_dir / "tenants"
            if tenants_dir.exists():
                for tid_path in tenants_dir.iterdir():
                    if tid_path.is_dir():
                        reg_path = tid_path / "model_registry.json"
                        if reg_path.exists():
                            with self._lock:
                                results.extend(self._load(tid_path.name))

        if bundle_id is not None:
            results = [m for m in results if m.get("bundle_id") == bundle_id]
        if status is not None:
            results = [m for m in results if m.get("status") == status]

        return results

    def deprecate_model(self, model_id: str, tenant_id: str) -> bool:
        """Set a model's status to 'deprecated'. Returns True if found."""
        with self._lock:
            models = self._load(tenant_id)
            updated = False
            for m in models:
                if m.get("model_id") == model_id:
                    m["status"] = "deprecated"
                    updated = True
                    break
            if updated:
                self._save(tenant_id, models)
        return updated

    def has_active_training(self, bundle_id: str | None, tenant_id: str) -> bool:
        """Return True if there is already a training job in progress."""
        with self._lock:
            models = self._load(tenant_id)
        return any(
            m.get("status") == "training"
            and m.get("bundle_id") == bundle_id
            for m in models
        )


@functools.lru_cache(maxsize=50)
def get_model_registry(tenant_id: str = "system") -> ModelRegistry:
    """Return a cached ModelRegistry instance."""
    data_dir = Path(os.getenv("DATA_DIR", "./data"))
    return ModelRegistry(data_dir)


def clear_model_registry_cache() -> None:
    """Invalidate the registry cache."""
    get_model_registry.cache_clear()
