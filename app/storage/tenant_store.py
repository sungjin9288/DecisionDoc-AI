"""tenant_store.py — Tenant registry: create, read, update, deactivate tenants."""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import secrets
import shutil
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, TypeVar

from app.storage.conditional_state import persist_text_if_current
from app.storage.state_backend import StateBackend, StateBackendError, get_state_backend
from app.tenant import SYSTEM_TENANT_ID, Tenant, require_tenant_id

_log = logging.getLogger("decisiondoc.storage.tenant")
_registry_locks: dict[Path, threading.RLock] = {}
_registry_locks_guard = threading.Lock()
_STATE_METADATA_KEY = ""  # Public tenant identifiers reject the empty string.
_MUTATION_IDS_FIELD = "_registry_mutation_ids"
TENANT_REGISTRY_METADATA_FIELDS = frozenset({_STATE_METADATA_KEY})
_MAX_MUTATION_ATTEMPTS = 32
_MAX_TRACKED_MUTATIONS = 64
_MutationResult = TypeVar("_MutationResult")


class TenantRegistryError(ValueError):
    """Raised when the persisted tenant registry cannot be trusted."""


def _lock_for_path(path: Path) -> threading.RLock:
    with _registry_locks_guard:
        return _registry_locks.setdefault(path.resolve(), threading.RLock())


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise TenantRegistryError(f"Duplicate key in tenant registry: {key!r}")
        result[key] = value
    return result


class TenantStore:
    """Thread-safe JSON store for tenant registry."""

    def __init__(self, data_dir: Path, *, backend: StateBackend | None = None) -> None:
        self._data_dir = Path(data_dir)
        self._path = self._data_dir / "tenants.json"
        self._relative_path = "tenants.json"
        self._backend = backend or get_state_backend(data_dir=self._data_dir)
        self._lock = _lock_for_path(self._path)
        if self._backend.kind == "local":
            self._path.parent.mkdir(parents=True, exist_ok=True)

    # ── Internal helpers ──────────────────────────────────────────────────

    @staticmethod
    def _tenant_id(value: object) -> str:
        return require_tenant_id(value)

    @staticmethod
    def _mutation_ids(data: dict[str, Any]) -> list[str]:
        if _STATE_METADATA_KEY not in data:
            return []
        metadata = data[_STATE_METADATA_KEY]
        if not isinstance(metadata, dict) or set(metadata) != {_MUTATION_IDS_FIELD}:
            raise TenantRegistryError("Invalid tenant registry mutation history")
        mutation_ids = metadata.get(_MUTATION_IDS_FIELD)
        if (
            not isinstance(mutation_ids, list)
            or len(mutation_ids) > _MAX_TRACKED_MUTATIONS
            or any(
                not isinstance(mutation_id, str) or not mutation_id
                for mutation_id in mutation_ids
            )
            or len(mutation_ids) != len(set(mutation_ids))
        ):
            raise TenantRegistryError("Invalid tenant registry mutation history")
        return list(mutation_ids)

    def _read_state(self) -> tuple[str | None, dict[str, Any]]:
        try:
            raw = self._backend.read_text(self._relative_path)
        except (StateBackendError, UnicodeError) as exc:
            raise TenantRegistryError("Invalid tenant registry") from exc
        if raw is None:
            return None, {}
        if not raw.strip():
            raise TenantRegistryError("Invalid tenant registry")
        try:
            data = json.loads(raw, object_pairs_hook=_unique_object)
        except (json.JSONDecodeError, ValueError) as exc:
            _log.error("Corrupted tenants store: %s", exc)
            raise TenantRegistryError("Invalid tenant registry") from exc
        if not isinstance(data, dict):
            raise TenantRegistryError("Invalid tenant registry")
        self._mutation_ids(data)
        return raw, data

    def _load(self) -> dict[str, Any]:
        return self._read_state()[1]

    def _persist_if_current(
        self,
        *,
        expected: str | None,
        data: dict[str, Any],
        mutation_id: str,
        committed: Callable[[dict[str, Any]], bool] | None = None,
    ) -> bool:
        self._mutation_ids(data)
        payload = json.dumps(data, ensure_ascii=False, indent=2)

        def decode(raw: str) -> dict[str, Any]:
            if not raw.strip():
                raise TenantRegistryError("Invalid tenant registry")
            try:
                observed = json.loads(raw, object_pairs_hook=_unique_object)
            except (json.JSONDecodeError, ValueError) as exc:
                raise TenantRegistryError("Invalid tenant registry") from exc
            if not isinstance(observed, dict):
                raise TenantRegistryError("Invalid tenant registry")
            self._mutation_ids(observed)
            return observed

        try:
            return persist_text_if_current(
                backend=self._backend,
                relative_path=self._relative_path,
                expected=expected,
                replacement=payload,
                decode=decode,
                committed=lambda observed: (
                    mutation_id in self._mutation_ids(observed)
                    and (committed is None or committed(observed))
                ),
                decode_errors=(TenantRegistryError,),
            )
        except StateBackendError as exc:
            raise TenantRegistryError("Failed to persist tenant registry") from exc

    def _mutate(
        self,
        mutation_id: str,
        change: Callable[[dict[str, Any]], tuple[_MutationResult, bool]],
        *,
        committed: Callable[[dict[str, Any]], bool] | None = None,
    ) -> _MutationResult:
        for _ in range(_MAX_MUTATION_ATTEMPTS):
            expected, data = self._read_state()
            result, changed = change(data)
            if not changed:
                return result

            mutation_ids = self._mutation_ids(data)
            mutation_ids.append(mutation_id)
            data[_STATE_METADATA_KEY] = {
                _MUTATION_IDS_FIELD: mutation_ids[-_MAX_TRACKED_MUTATIONS:]
            }
            if self._persist_if_current(
                expected=expected,
                data=data,
                mutation_id=mutation_id,
                committed=committed,
            ):
                return result
        raise TenantRegistryError(
            "Tenant registry changed too many times to persist safely"
        )

    @staticmethod
    def _record_to_tenant(tenant_id: str, record: Any) -> Tenant:
        tenant_id = TenantStore._tenant_id(tenant_id)
        if not isinstance(record, dict):
            raise ValueError("Invalid tenant record")
        if require_tenant_id(record.get("tenant_id")) != tenant_id:
            raise ValueError("Tenant record ownership mismatch")

        display_name = record.get("display_name")
        if not isinstance(display_name, str) or not display_name.strip():
            raise ValueError("Invalid tenant display_name")

        allowed_bundles = record.get("allowed_bundles", [])
        if allowed_bundles is None:
            allowed_bundles = []
        if not isinstance(allowed_bundles, list) or not all(
            isinstance(bundle_id, str) and bundle_id for bundle_id in allowed_bundles
        ):
            raise ValueError("Invalid tenant allowed_bundles")

        custom_prompt_hints = record.get("custom_prompt_hints", {})
        if custom_prompt_hints is None:
            custom_prompt_hints = {}
        if not isinstance(custom_prompt_hints, dict) or not all(
            isinstance(bundle_id, str) and bundle_id and isinstance(hint, str)
            for bundle_id, hint in custom_prompt_hints.items()
        ):
            raise ValueError("Invalid tenant custom_prompt_hints")

        created_at = record.get("created_at", "")
        is_active = record.get("is_active", True)
        if not isinstance(created_at, str) or not isinstance(is_active, bool):
            raise ValueError("Invalid tenant record")

        return Tenant(
            tenant_id=tenant_id,
            display_name=display_name,
            allowed_bundles=list(allowed_bundles),
            custom_prompt_hints=dict(custom_prompt_hints),
            created_at=created_at,
            is_active=is_active,
        )

    @staticmethod
    def _require_display_name(display_name: Any) -> str:
        if not isinstance(display_name, str) or not display_name.strip():
            raise ValueError("Invalid tenant display_name")
        return display_name

    @staticmethod
    def _require_allowed_bundles(allowed_bundles: Any) -> list[str]:
        if not isinstance(allowed_bundles, list) or not all(
            isinstance(bundle_id, str) and bundle_id for bundle_id in allowed_bundles
        ):
            raise ValueError("Invalid tenant allowed_bundles")
        return list(allowed_bundles)

    def _owned_record(self, data: dict[str, Any], tenant_id: str) -> dict[str, Any]:
        record = data.get(tenant_id)
        if record is None:
            raise ValueError(f"Tenant not found: {tenant_id!r}")
        self._record_to_tenant(tenant_id, record)
        return record

    def _tenant_id_for_api_key_hash(
        self,
        data: dict[str, Any],
        key_hash: str,
    ) -> str | None:
        matches: list[str] = []
        for tenant_id, record in data.items():
            if tenant_id in TENANT_REGISTRY_METADATA_FIELDS:
                continue
            try:
                tenant = self._record_to_tenant(tenant_id, record)
            except ValueError:
                continue
            stored_hash = record.get("api_key_hash")
            if (
                tenant.is_active
                and isinstance(stored_hash, str)
                and hmac.compare_digest(stored_hash, key_hash)
            ):
                matches.append(tenant_id)
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            _log.error("Duplicate active tenant API key hash")
        return None

    # ── Public API ────────────────────────────────────────────────────────

    def create_tenant(
        self,
        tenant_id: str,
        display_name: str,
        allowed_bundles: list[str] | None = None,
    ) -> Tenant:
        """Create and persist a new tenant. Raises ValueError if already exists."""
        tenant_id = self._tenant_id(tenant_id)
        display_name = self._require_display_name(display_name)
        bundles = self._require_allowed_bundles(
            [] if allowed_bundles is None else allowed_bundles
        )
        mutation_id = secrets.token_hex(16)
        created_at = datetime.now(timezone.utc).isoformat()

        def create(data: dict[str, Any]) -> tuple[Tenant, bool]:
            if tenant_id in data:
                raise ValueError(f"Tenant already exists: {tenant_id!r}")
            record: dict[str, Any] = {
                "tenant_id": tenant_id,
                "display_name": display_name,
                "allowed_bundles": bundles,
                "custom_prompt_hints": {},
                "created_at": created_at,
                "is_active": True,
            }
            data[tenant_id] = record
            return self._record_to_tenant(tenant_id, record), True

        with self._lock:
            return self._mutate(mutation_id, create)

    def get_tenant(self, tenant_id: str) -> Tenant | None:
        """Return the Tenant or None if not found."""
        tenant_id = self._tenant_id(tenant_id)
        with self._lock:
            data = self._load()
            record = data.get(tenant_id)
            if record is None:
                return None
            try:
                return self._record_to_tenant(tenant_id, record)
            except ValueError as exc:
                _log.warning("Ignoring invalid tenant record %r: %s", tenant_id, exc)
                return None

    def list_tenants(self) -> list[Tenant]:
        """Return all tenants."""
        with self._lock:
            data = self._load()
            tenants: list[Tenant] = []
            for tenant_id, record in data.items():
                if tenant_id in TENANT_REGISTRY_METADATA_FIELDS:
                    continue
                try:
                    tenants.append(self._record_to_tenant(tenant_id, record))
                except ValueError as exc:
                    _log.warning(
                        "Ignoring invalid tenant record %r: %s", tenant_id, exc
                    )
            return tenants

    def update_tenant(
        self,
        tenant_id: str,
        *,
        display_name: str | None = None,
        allowed_bundles: list[str] | None = None,
        is_active: bool | None = None,
    ) -> Tenant:
        """Update mutable fields of a tenant. Raises ValueError if not found.

        SYSTEM_TENANT_ID cannot be deactivated.
        """
        tenant_id = self._tenant_id(tenant_id)
        if display_name is not None:
            display_name = self._require_display_name(display_name)
        if allowed_bundles is not None:
            allowed_bundles = self._require_allowed_bundles(allowed_bundles)
        if is_active is not None and not isinstance(is_active, bool):
            raise ValueError("Invalid tenant is_active")
        mutation_id = secrets.token_hex(16)

        def update(data: dict[str, Any]) -> tuple[Tenant, bool]:
            record = self._owned_record(data, tenant_id)
            if display_name is not None:
                record["display_name"] = display_name
            if allowed_bundles is not None:
                record["allowed_bundles"] = allowed_bundles
            if is_active is not None:
                if tenant_id == SYSTEM_TENANT_ID and not is_active:
                    raise ValueError("SYSTEM_TENANT_ID cannot be deactivated")
                record["is_active"] = is_active
            changed = any(
                value is not None
                for value in (display_name, allowed_bundles, is_active)
            )
            return self._record_to_tenant(tenant_id, record), changed

        with self._lock:
            return self._mutate(mutation_id, update)

    def deactivate_tenant(self, tenant_id: str) -> None:
        """Deactivate a tenant (soft delete). SYSTEM_TENANT_ID cannot be deactivated."""
        self.update_tenant(tenant_id, is_active=False)

    def set_custom_hint(self, tenant_id: str, bundle_id: str, hint: str) -> None:
        """Set a bundle-specific custom prompt hint for a tenant."""
        tenant_id = self._tenant_id(tenant_id)
        if not isinstance(bundle_id, str) or not bundle_id:
            raise ValueError("Invalid bundle_id")
        if not isinstance(hint, str) or not hint.strip():
            raise ValueError("Invalid hint")
        mutation_id = secrets.token_hex(16)

        def set_hint(data: dict[str, Any]) -> tuple[None, bool]:
            record = self._owned_record(data, tenant_id)
            record.setdefault("custom_prompt_hints", {})[bundle_id] = hint
            return None, True

        with self._lock:
            self._mutate(mutation_id, set_hint)

    def delete_custom_hint(self, tenant_id: str, bundle_id: str) -> None:
        """Remove a bundle-specific custom prompt hint for a tenant."""
        tenant_id = self._tenant_id(tenant_id)
        if not isinstance(bundle_id, str) or not bundle_id:
            raise ValueError("Invalid bundle_id")
        mutation_id = secrets.token_hex(16)

        def delete_hint(data: dict[str, Any]) -> tuple[None, bool]:
            record = self._owned_record(data, tenant_id)
            hints = record.get("custom_prompt_hints", {})
            if bundle_id not in hints:
                return None, False
            hints.pop(bundle_id)
            return None, True

        with self._lock:
            self._mutate(mutation_id, delete_hint)

    def get_custom_hint(self, tenant_id: str, bundle_id: str) -> str | None:
        """Return the custom hint for a bundle, or None."""
        tenant_id = self._tenant_id(tenant_id)
        with self._lock:
            data = self._load()
            record = data.get(tenant_id)
            if record is None:
                return None
            try:
                tenant = self._record_to_tenant(tenant_id, record)
            except ValueError as exc:
                _log.warning("Ignoring invalid tenant record %r: %s", tenant_id, exc)
                return None
            return tenant.custom_prompt_hints.get(bundle_id)

    def rotate_api_key(self, tenant_id: str) -> str:
        """Generate a new API key for the tenant. Returns the plain key (shown once).
        Stores a SHA-256 hash of the key in the tenant record."""
        tenant_id = self._tenant_id(tenant_id)
        mutation_id = secrets.token_hex(16)
        key = "dd_" + secrets.token_urlsafe(32)
        key_hash = hashlib.sha256(key.encode()).hexdigest()
        created_at = datetime.now(timezone.utc).isoformat()

        def rotate(data: dict[str, Any]) -> tuple[str, bool]:
            record = self._owned_record(data, tenant_id)
            record["api_key_hash"] = key_hash
            record["api_key_created_at"] = created_at
            return key, True

        def rotation_is_current(data: dict[str, Any]) -> bool:
            return self._tenant_id_for_api_key_hash(data, key_hash) == tenant_id

        with self._lock:
            return self._mutate(
                mutation_id,
                rotate,
                committed=rotation_is_current,
            )

    def find_tenant_by_api_key(self, key: str) -> str | None:
        """Find and return the tenant_id for the given API key, or None."""
        if not isinstance(key, str) or not key:
            return None
        key_hash = hashlib.sha256(key.encode()).hexdigest()
        with self._lock:
            data = self._load()
            return self._tenant_id_for_api_key_hash(data, key_hash)

    def ensure_system_tenant(self) -> Tenant:
        """Create SYSTEM_TENANT_ID if it does not yet exist."""
        mutation_id = secrets.token_hex(16)
        created_at = datetime.now(timezone.utc).isoformat()

        def ensure(data: dict[str, Any]) -> tuple[Tenant, bool]:
            record = data.get(SYSTEM_TENANT_ID)
            if record is not None:
                return self._record_to_tenant(SYSTEM_TENANT_ID, record), False
            record = {
                "tenant_id": SYSTEM_TENANT_ID,
                "display_name": "System (Default)",
                "allowed_bundles": [],
                "custom_prompt_hints": {},
                "created_at": created_at,
                "is_active": True,
            }
            data[SYSTEM_TENANT_ID] = record
            return self._record_to_tenant(SYSTEM_TENANT_ID, record), True

        with self._lock:
            return self._mutate(mutation_id, ensure)


def migrate_legacy_data(data_dir: Path) -> None:
    """Copy legacy flat data files into the system tenant directory.

    For each legacy file or knowledge/fine-tune directory that exists but whose destination
    does not yet exist, copies it into ``<data_dir>/tenants/system/`` so that
    existing data is preserved after the multi-tenant migration.
    """
    try:
        system_dir = Path(data_dir) / "tenants" / "system"
        system_dir.mkdir(parents=True, exist_ok=True)

        legacy_pairs = [
            (Path(data_dir) / "feedback.jsonl", system_dir / "feedback.jsonl"),
            (
                Path(data_dir) / "prompt_overrides.json",
                system_dir / "prompt_overrides.json",
            ),
            (Path(data_dir) / "ab_tests.json", system_dir / "ab_tests.json"),
            (Path(data_dir) / "eval_results.jsonl", system_dir / "eval_results.jsonl"),
            (
                Path(data_dir) / "request_patterns.jsonl",
                system_dir / "request_patterns.jsonl",
            ),
        ]

        for src, dst in legacy_pairs:
            if src.exists() and not dst.exists():
                shutil.copy2(src, dst)
                _log.info("Migrated %s → %s", src.name, dst)

        legacy_finetune_dir = Path(data_dir) / "finetune"
        system_finetune_dir = system_dir / "finetune"
        if legacy_finetune_dir.is_dir() and not system_finetune_dir.exists():
            shutil.copytree(legacy_finetune_dir, system_finetune_dir)
            _log.info("Migrated %s → %s", legacy_finetune_dir.name, system_finetune_dir)

        legacy_knowledge_dir = Path(data_dir) / "knowledge"
        system_knowledge_dir = system_dir / "knowledge"
        if legacy_knowledge_dir.is_dir() and not system_knowledge_dir.exists():
            shutil.copytree(legacy_knowledge_dir, system_knowledge_dir)
            _log.info(
                "Migrated %s → %s", legacy_knowledge_dir.name, system_knowledge_dir
            )
    except Exception as exc:
        _log.warning("migrate_legacy_data failed: %s", exc)
