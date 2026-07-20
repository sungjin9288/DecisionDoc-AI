"""Tenant-scoped fine-tuned model lifecycle registry."""

from __future__ import annotations

import json
import math
import os
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, TypeVar

from app.storage.conditional_state import persist_text_if_current
from app.storage.state_backend import StateBackend, StateBackendError, get_state_backend
from app.storage.state_lock import state_backend_identity, state_lock
from app.tenant import require_tenant_id


class ModelRegistryError(RuntimeError):
    """Raised when persisted model authority cannot be trusted."""


_VALID_STATUSES = frozenset({"training", "ready", "failed", "deprecated"})
_model_registries: dict[tuple[Any, ...], "ModelRegistry"] = {}
_model_registries_guard = threading.Lock()
_INCARNATION_ID_FIELD = "_incarnation_id"
_MUTATION_IDS_FIELD = "_mutation_ids"
_MAX_TRACKED_MUTATIONS = 64
_MAX_MUTATION_ATTEMPTS = 32
_MutationResult = TypeVar("_MutationResult")


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ModelRegistryError(f"Duplicate key in model registry: {key!r}")
        result[key] = value
    return result


class ModelRegistry:
    """Read and update model lifecycle authority for one tenant."""

    _RECORD_FIELDS = {
        "model_id",
        "base_model",
        "bundle_id",
        "tenant_id",
        "status",
        "training_file_id",
        "record_count",
        "avg_score_before",
        "avg_score_after",
        "openai_job_id",
        "created_at",
        "ready_at",
        "eval_result",
    }
    _PRIVATE_FIELDS = {_INCARNATION_ID_FIELD, _MUTATION_IDS_FIELD}

    def __init__(
        self,
        data_dir: Path | None = None,
        *,
        tenant_id: str,
        backend: StateBackend | None = None,
    ) -> None:
        self._tenant_id = require_tenant_id(tenant_id)
        self._data_dir = Path(data_dir or os.getenv("DATA_DIR", "./data"))
        self._relative_path = str(
            Path("tenants") / self._tenant_id / "model_registry.json"
        )
        self._backend = backend or get_state_backend(data_dir=self._data_dir)
        self._lock = state_lock(
            self._backend,
            data_dir=self._data_dir,
            relative_path=self._relative_path,
        )

    @staticmethod
    def _text(value: object, *, field_name: str) -> str:
        if (
            not isinstance(value, str)
            or not value
            or value != value.strip()
            or any(ord(character) < 32 or ord(character) == 127 for character in value)
        ):
            raise ModelRegistryError(f"Invalid model {field_name}")
        return value

    @staticmethod
    def _timestamp(
        value: object,
        *,
        field_name: str,
        allow_none: bool,
    ) -> str | None:
        if value is None and allow_none:
            return None
        if not isinstance(value, str) or not value or value != value.strip():
            raise ModelRegistryError(f"Invalid model {field_name}")
        try:
            timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ModelRegistryError(f"Invalid model {field_name}") from exc
        if timestamp.tzinfo is None or timestamp.utcoffset() != timezone.utc.utcoffset(
            timestamp
        ):
            raise ModelRegistryError(f"Invalid model {field_name}")
        return value

    @staticmethod
    def _score(
        value: object,
        *,
        field_name: str,
        allow_none: bool,
    ) -> float | None:
        if value is None and allow_none:
            return None
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            or not 0.0 <= float(value) <= 1.0
        ):
            raise ModelRegistryError(f"Invalid model {field_name}")
        return float(value)

    def _owns(self, model: object) -> bool:
        return isinstance(model, dict) and model.get("tenant_id") in {
            None,
            self._tenant_id,
        }

    def _validate_owned(self, model: dict[str, Any], *, legacy: bool) -> None:
        expected_fields = self._RECORD_FIELDS - ({"tenant_id"} if legacy else set())
        if not expected_fields.issubset(model) or not set(model).issubset(
            expected_fields | self._PRIVATE_FIELDS
        ):
            raise ModelRegistryError("Invalid model registry fields")

        self._text(model.get("model_id"), field_name="identity")
        self._text(model.get("base_model"), field_name="base model")
        bundle_id = model.get("bundle_id")
        if bundle_id is not None:
            self._text(bundle_id, field_name="bundle identity")
        if not legacy and model.get("tenant_id") != self._tenant_id:
            raise ModelRegistryError("Model registry tenant ownership mismatch")
        if model.get("status") not in _VALID_STATUSES:
            raise ModelRegistryError("Invalid model status")
        self._text(model.get("training_file_id"), field_name="training file identity")
        record_count = model.get("record_count")
        if (
            isinstance(record_count, bool)
            or not isinstance(record_count, int)
            or record_count < 1
        ):
            raise ModelRegistryError("Invalid model training record count")
        self._score(
            model.get("avg_score_before"),
            field_name="baseline score",
            allow_none=False,
        )
        self._score(
            model.get("avg_score_after"),
            field_name="evaluation score",
            allow_none=True,
        )
        self._text(model.get("openai_job_id"), field_name="provider job identity")
        self._timestamp(
            model.get("created_at"), field_name="creation timestamp", allow_none=False
        )
        self._timestamp(
            model.get("ready_at"), field_name="ready timestamp", allow_none=True
        )
        if model.get("eval_result") is not None and not isinstance(
            model.get("eval_result"), dict
        ):
            raise ModelRegistryError("Invalid model evaluation result")
        if model.get("status") == "ready":
            if model["model_id"].startswith("pending:"):
                raise ModelRegistryError("Invalid ready model authority")
        self._incarnation_id(model)
        self._mutation_ids(model)

    def _decode_state(self, raw: str) -> list[dict[str, Any]]:
        try:
            data = json.loads(raw, object_pairs_hook=_unique_object)
        except (json.JSONDecodeError, TypeError, ModelRegistryError) as exc:
            raise ModelRegistryError("Invalid model registry document") from exc
        if not isinstance(data, list):
            raise ModelRegistryError("Invalid model registry collection")

        models: list[dict[str, Any]] = []
        for model in data:
            if not isinstance(model, dict):
                raise ModelRegistryError("Invalid model registry record")
            stored_tenant_id = model.get("tenant_id")
            if stored_tenant_id is not None:
                if not isinstance(stored_tenant_id, str) or not stored_tenant_id:
                    raise ModelRegistryError("Invalid model registry tenant identity")
                if stored_tenant_id != self._tenant_id:
                    models.append(model)
                    continue
            self._validate_owned(model, legacy=stored_tenant_id is None)
            models.append(model)

        owned = [model for model in models if self._owns(model)]
        model_ids = [model["model_id"] for model in owned]
        job_ids = [model["openai_job_id"] for model in owned]
        if len(model_ids) != len(set(model_ids)):
            raise ModelRegistryError("Duplicate model identity in registry")
        if len(job_ids) != len(set(job_ids)):
            raise ModelRegistryError("Duplicate provider job identity in registry")
        return models

    def _read_state(self) -> tuple[str | None, list[dict[str, Any]]]:
        try:
            raw = self._backend.read_text(self._relative_path)
        except (StateBackendError, UnicodeError) as exc:
            raise ModelRegistryError("Model registry could not be read") from exc
        if raw is None:
            return None, []
        return raw, self._decode_state(raw)

    def _read_all(self) -> list[dict[str, Any]]:
        return self._read_state()[1]

    def _read_owned(self) -> list[dict[str, Any]]:
        return [model for model in self._read_all() if self._owns(model)]

    @staticmethod
    def _incarnation_id(model: dict[str, Any]) -> str | None:
        incarnation_id = model.get(_INCARNATION_ID_FIELD)
        if incarnation_id is not None and (
            not isinstance(incarnation_id, str) or not incarnation_id
        ):
            raise ModelRegistryError("Invalid model incarnation")
        return incarnation_id

    def _effective_incarnation_id(self, model: dict[str, Any]) -> str:
        incarnation_id = self._incarnation_id(model)
        if incarnation_id is not None:
            return incarnation_id
        identity = "|".join(
            (
                self._tenant_id,
                str(model.get("openai_job_id") or ""),
                str(model.get("created_at") or ""),
            )
        )
        return f"legacy:{uuid.uuid5(uuid.NAMESPACE_URL, identity).hex}"

    @staticmethod
    def _mutation_ids(model: dict[str, Any]) -> list[str]:
        mutation_ids = model.get(_MUTATION_IDS_FIELD, [])
        if (
            not isinstance(mutation_ids, list)
            or len(mutation_ids) > _MAX_TRACKED_MUTATIONS
            or any(
                not isinstance(mutation_id, str) or not mutation_id
                for mutation_id in mutation_ids
            )
            or len(mutation_ids) != len(set(mutation_ids))
        ):
            raise ModelRegistryError("Invalid model mutation history")
        return list(mutation_ids)

    def _record_mutation(
        self,
        model: dict[str, Any],
        *,
        previous: dict[str, Any],
        mutation_id: str,
        incarnation_id: str,
    ) -> dict[str, Any]:
        mutation_ids = self._mutation_ids(previous)
        if mutation_id not in mutation_ids:
            mutation_ids.append(mutation_id)
        persisted = dict(model)
        persisted[_INCARNATION_ID_FIELD] = incarnation_id
        persisted[_MUTATION_IDS_FIELD] = mutation_ids[-_MAX_TRACKED_MUTATIONS:]
        return persisted

    @staticmethod
    def _public_model(model: dict[str, Any]) -> dict[str, Any]:
        public = dict(model)
        public.pop(_INCARNATION_ID_FIELD, None)
        public.pop(_MUTATION_IDS_FIELD, None)
        return public

    def _persist_if_current(
        self,
        *,
        expected: str | None,
        models: list[dict[str, Any]],
        committed: Callable[[list[dict[str, Any]]], bool],
    ) -> bool:
        for model in models:
            if self._owns(model):
                self._validate_owned(model, legacy=model.get("tenant_id") is None)
        replacement = json.dumps(models, ensure_ascii=False, indent=2)
        try:
            return persist_text_if_current(
                backend=self._backend,
                relative_path=self._relative_path,
                expected=expected,
                replacement=replacement,
                decode=self._decode_state,
                committed=committed,
                decode_errors=(ModelRegistryError,),
            )
        except StateBackendError as exc:
            raise ModelRegistryError("Model registry could not be written") from exc

    def _mutate(
        self,
        change: Callable[
            [list[dict[str, Any]]],
            tuple[_MutationResult, bool],
        ],
        *,
        committed: Callable[[list[dict[str, Any]]], bool],
    ) -> _MutationResult:
        for _ in range(_MAX_MUTATION_ATTEMPTS):
            expected, models = self._read_state()
            result, changed = change(models)
            if not changed:
                return result
            if self._persist_if_current(
                expected=expected,
                models=models,
                committed=committed,
            ):
                return result
        raise ModelRegistryError(
            "Model registry changed too many times to persist safely"
        )

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
        """Register a unique provider job with status ``training``."""
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
        self._validate_owned(record, legacy=False)
        mutation_id = uuid.uuid4().hex
        incarnation_id = uuid.uuid4().hex
        persisted = self._record_mutation(
            record,
            previous={},
            mutation_id=mutation_id,
            incarnation_id=incarnation_id,
        )

        def apply(models: list[dict[str, Any]]) -> tuple[dict[str, Any], bool]:
            owned = [model for model in models if self._owns(model)]
            if any(model["model_id"] == model_id for model in owned):
                raise ModelRegistryError("Model identity is already registered")
            if any(model["openai_job_id"] == openai_job_id for model in owned):
                raise ModelRegistryError("Provider job identity is already registered")
            models.append(dict(persisted))
            return self._public_model(record), True

        def was_committed(models: list[dict[str, Any]]) -> bool:
            return any(
                self._owns(model)
                and model.get("openai_job_id") == openai_job_id
                and self._effective_incarnation_id(model) == incarnation_id
                and mutation_id in self._mutation_ids(model)
                for model in models
            )

        with self._lock:
            return self._mutate(apply, committed=was_committed)

    def update_status(
        self,
        openai_job_id: str,
        status: str,
        *,
        model_id: str | None = None,
        ready_at: str | None = None,
    ) -> bool:
        if status not in _VALID_STATUSES:
            raise ValueError(
                f"Invalid status '{status}'. Must be one of {_VALID_STATUSES}"
            )
        self._text(openai_job_id, field_name="provider job identity")
        if model_id is not None:
            self._text(model_id, field_name="identity")
        if ready_at is not None:
            self._timestamp(ready_at, field_name="ready timestamp", allow_none=False)

        mutation_id = uuid.uuid4().hex
        target_incarnation: str | None = None
        target_bound = False

        def apply(models: list[dict[str, Any]]) -> tuple[bool, bool]:
            nonlocal target_bound, target_incarnation
            target_index = next(
                (
                    index
                    for index, model in enumerate(models)
                    if self._owns(model) and model["openai_job_id"] == openai_job_id
                ),
                None,
            )
            if target_index is None:
                return False, False
            target = models[target_index]
            incarnation_id = self._effective_incarnation_id(target)
            if not target_bound:
                target_incarnation = incarnation_id
                target_bound = True
            elif incarnation_id != target_incarnation:
                return False, False
            if mutation_id in self._mutation_ids(target):
                return True, False

            candidate_model_id = model_id or target["model_id"]
            if status == "ready" and candidate_model_id.startswith("pending:"):
                raise ModelRegistryError("A pending model identity cannot be promoted")
            if model_id is not None and any(
                self._owns(existing)
                and index != target_index
                and existing["model_id"] == model_id
                for index, existing in enumerate(models)
            ):
                raise ModelRegistryError("Model identity is already registered")

            updated = dict(target)
            updated["status"] = status
            if model_id is not None:
                updated["model_id"] = model_id
            if status == "ready":
                updated["ready_at"] = ready_at or datetime.now(timezone.utc).isoformat()
            elif ready_at is not None:
                updated["ready_at"] = ready_at
            models[target_index] = self._record_mutation(
                updated,
                previous=target,
                mutation_id=mutation_id,
                incarnation_id=incarnation_id,
            )
            return True, True

        def was_committed(models: list[dict[str, Any]]) -> bool:
            return any(
                self._owns(model)
                and model.get("openai_job_id") == openai_job_id
                and self._effective_incarnation_id(model) == target_incarnation
                and mutation_id in self._mutation_ids(model)
                for model in models
            )

        with self._lock:
            return self._mutate(apply, committed=was_committed)

    def update_eval_result(
        self,
        model_id: str,
        *,
        avg_score_after: float,
        eval_result: dict[str, Any] | None = None,
    ) -> bool:
        self._text(model_id, field_name="identity")
        score = self._score(
            avg_score_after,
            field_name="evaluation score",
            allow_none=False,
        )
        if eval_result is not None and not isinstance(eval_result, dict):
            raise ModelRegistryError("Invalid model evaluation result")

        mutation_id = uuid.uuid4().hex
        target_incarnation: str | None = None
        target_bound = False

        def apply(models: list[dict[str, Any]]) -> tuple[bool, bool]:
            nonlocal target_bound, target_incarnation
            target_index = next(
                (
                    index
                    for index, model in enumerate(models)
                    if self._owns(model) and model["model_id"] == model_id
                ),
                None,
            )
            if target_index is None:
                return False, False
            target = models[target_index]
            incarnation_id = self._effective_incarnation_id(target)
            if not target_bound:
                target_incarnation = incarnation_id
                target_bound = True
            elif incarnation_id != target_incarnation:
                return False, False
            if mutation_id in self._mutation_ids(target):
                return True, False

            updated = dict(target)
            updated["avg_score_after"] = score
            if eval_result is not None:
                updated["eval_result"] = eval_result
            models[target_index] = self._record_mutation(
                updated,
                previous=target,
                mutation_id=mutation_id,
                incarnation_id=incarnation_id,
            )
            return True, True

        def was_committed(models: list[dict[str, Any]]) -> bool:
            return any(
                self._owns(model)
                and model.get("model_id") == model_id
                and self._effective_incarnation_id(model) == target_incarnation
                and mutation_id in self._mutation_ids(model)
                for model in models
            )

        with self._lock:
            return self._mutate(apply, committed=was_committed)

    def get_active_model(self, bundle_id: str | None) -> dict[str, Any] | None:
        if bundle_id is not None:
            self._text(bundle_id, field_name="bundle identity")
        with self._lock:
            models = self._read_owned()
        ready = [
            model
            for model in models
            if model["status"] == "ready"
            and (model["bundle_id"] == bundle_id or model["bundle_id"] is None)
        ]
        bundle_specific = [model for model in ready if model["bundle_id"] == bundle_id]
        candidates = bundle_specific or ready
        if not candidates:
            return None
        return self._public_model(
            max(
                candidates,
                key=lambda model: (
                    model["avg_score_after"] is not None,
                    model["avg_score_after"] or 0.0,
                    model["created_at"],
                ),
            )
        )

    def get_model(self, model_id: str) -> dict[str, Any] | None:
        self._text(model_id, field_name="identity")
        with self._lock:
            model = next(
                (
                    model
                    for model in self._read_owned()
                    if model["model_id"] == model_id
                ),
                None,
            )
        return self._public_model(model) if model is not None else None

    def get_model_by_job(self, openai_job_id: str) -> dict[str, Any] | None:
        self._text(openai_job_id, field_name="provider job identity")
        with self._lock:
            model = next(
                (
                    model
                    for model in self._read_owned()
                    if model["openai_job_id"] == openai_job_id
                ),
                None,
            )
        return self._public_model(model) if model is not None else None

    def list_models(
        self,
        *,
        bundle_id: str | None = None,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        if bundle_id is not None:
            self._text(bundle_id, field_name="bundle identity")
        if status is not None and status not in _VALID_STATUSES:
            raise ModelRegistryError("Invalid model status filter")
        with self._lock:
            results = self._read_owned()
        if bundle_id is not None:
            results = [model for model in results if model["bundle_id"] == bundle_id]
        if status is not None:
            results = [model for model in results if model["status"] == status]
        return [self._public_model(model) for model in results]

    def deprecate_model(self, model_id: str) -> bool:
        self._text(model_id, field_name="identity")
        mutation_id = uuid.uuid4().hex
        target_incarnation: str | None = None
        target_bound = False

        def apply(models: list[dict[str, Any]]) -> tuple[bool, bool]:
            nonlocal target_bound, target_incarnation
            target_index = next(
                (
                    index
                    for index, model in enumerate(models)
                    if self._owns(model) and model["model_id"] == model_id
                ),
                None,
            )
            if target_index is None:
                return False, False
            target = models[target_index]
            incarnation_id = self._effective_incarnation_id(target)
            if not target_bound:
                target_incarnation = incarnation_id
                target_bound = True
            elif incarnation_id != target_incarnation:
                return False, False
            if mutation_id in self._mutation_ids(target):
                return True, False

            updated = dict(target)
            updated["status"] = "deprecated"
            models[target_index] = self._record_mutation(
                updated,
                previous=target,
                mutation_id=mutation_id,
                incarnation_id=incarnation_id,
            )
            return True, True

        def was_committed(models: list[dict[str, Any]]) -> bool:
            return any(
                self._owns(model)
                and model.get("model_id") == model_id
                and self._effective_incarnation_id(model) == target_incarnation
                and mutation_id in self._mutation_ids(model)
                for model in models
            )

        with self._lock:
            return self._mutate(apply, committed=was_committed)

    def has_active_training(self, bundle_id: str | None) -> bool:
        if bundle_id is not None:
            self._text(bundle_id, field_name="bundle identity")
        with self._lock:
            models = self._read_owned()
        return any(
            model["status"] == "training" and model["bundle_id"] == bundle_id
            for model in models
        )


def get_model_registry(
    tenant_id: str,
    data_dir: str | Path | None = None,
    *,
    backend: StateBackend | None = None,
) -> ModelRegistry:
    """Return a cached registry for one tenant and one state backend."""
    tenant_id = require_tenant_id(tenant_id)
    root = Path(data_dir or os.getenv("DATA_DIR", "./data"))
    explicit_backend = backend is not None
    selected_backend = backend or get_state_backend(data_dir=root)
    key = (
        tenant_id,
        root.resolve(),
        *state_backend_identity(
            selected_backend,
            data_dir=root,
            explicit_backend=explicit_backend,
        ),
    )
    with _model_registries_guard:
        registry = _model_registries.get(key)
        if registry is None:
            registry = ModelRegistry(
                root, tenant_id=tenant_id, backend=selected_backend
            )
            _model_registries[key] = registry
        return registry


def clear_model_registry_cache() -> None:
    with _model_registries_guard:
        _model_registries.clear()


get_model_registry.cache_clear = clear_model_registry_cache  # type: ignore[attr-defined]
