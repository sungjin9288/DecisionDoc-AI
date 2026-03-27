"""tenant_store.py — Tenant registry: create, read, update, deactivate tenants."""
from __future__ import annotations

import json
import logging
import shutil
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.tenant import SYSTEM_TENANT_ID, Tenant
from app.storage.state_backend import StateBackend, get_state_backend

_log = logging.getLogger("decisiondoc.storage.tenant")


class TenantStore:
    """Thread-safe JSON store for tenant registry."""

    def __init__(self, data_dir: Path, *, backend: StateBackend | None = None) -> None:
        self._data_dir = Path(data_dir)
        self._path = self._data_dir / "tenants.json"
        self._relative_path = "tenants.json"
        self._backend = backend or get_state_backend(data_dir=self._data_dir)
        self._lock = threading.Lock()
        if self._backend.kind == "local":
            self._path.parent.mkdir(parents=True, exist_ok=True)

    # ── Internal helpers ──────────────────────────────────────────────────

    def _load(self) -> dict[str, Any]:
        raw = self._backend.read_text(self._relative_path)
        if raw is None:
            return {}
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, ValueError) as exc:
            _log.error("Corrupted tenants store: %s", exc)
            return {}

    def _persist(self, data: dict[str, Any]) -> None:
        self._backend.write_text(
            self._relative_path,
            json.dumps(data, ensure_ascii=False, indent=2),
        )

    def _record_to_tenant(self, record: dict[str, Any]) -> Tenant:
        return Tenant(
            tenant_id=record["tenant_id"],
            display_name=record["display_name"],
            allowed_bundles=record.get("allowed_bundles") or [],
            custom_prompt_hints=record.get("custom_prompt_hints") or {},
            created_at=record.get("created_at", ""),
            is_active=record.get("is_active", True),
        )

    # ── Public API ────────────────────────────────────────────────────────

    def create_tenant(
        self,
        tenant_id: str,
        display_name: str,
        allowed_bundles: list[str] | None = None,
    ) -> Tenant:
        """Create and persist a new tenant. Raises ValueError if already exists."""
        with self._lock:
            data = self._load()
            if tenant_id in data:
                raise ValueError(f"Tenant already exists: {tenant_id!r}")
            record: dict[str, Any] = {
                "tenant_id": tenant_id,
                "display_name": display_name,
                "allowed_bundles": allowed_bundles or [],
                "custom_prompt_hints": {},
                "created_at": datetime.now(timezone.utc).isoformat(),
                "is_active": True,
            }
            data[tenant_id] = record
            self._persist(data)
            return self._record_to_tenant(record)

    def get_tenant(self, tenant_id: str) -> Tenant | None:
        """Return the Tenant or None if not found."""
        with self._lock:
            data = self._load()
            record = data.get(tenant_id)
            if record is None:
                return None
            return self._record_to_tenant(record)

    def list_tenants(self) -> list[Tenant]:
        """Return all tenants."""
        with self._lock:
            data = self._load()
            return [self._record_to_tenant(r) for r in data.values()]

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
        with self._lock:
            data = self._load()
            if tenant_id not in data:
                raise ValueError(f"Tenant not found: {tenant_id!r}")
            record = data[tenant_id]
            if display_name is not None:
                record["display_name"] = display_name
            if allowed_bundles is not None:
                record["allowed_bundles"] = allowed_bundles
            if is_active is not None:
                if tenant_id == SYSTEM_TENANT_ID and not is_active:
                    raise ValueError("SYSTEM_TENANT_ID cannot be deactivated")
                record["is_active"] = is_active
            data[tenant_id] = record
            self._persist(data)
            return self._record_to_tenant(record)

    def deactivate_tenant(self, tenant_id: str) -> None:
        """Deactivate a tenant (soft delete). SYSTEM_TENANT_ID cannot be deactivated."""
        self.update_tenant(tenant_id, is_active=False)

    def set_custom_hint(
        self, tenant_id: str, bundle_id: str, hint: str
    ) -> None:
        """Set a bundle-specific custom prompt hint for a tenant."""
        with self._lock:
            data = self._load()
            if tenant_id not in data:
                raise ValueError(f"Tenant not found: {tenant_id!r}")
            data[tenant_id].setdefault("custom_prompt_hints", {})[bundle_id] = hint
            self._persist(data)

    def delete_custom_hint(self, tenant_id: str, bundle_id: str) -> None:
        """Remove a bundle-specific custom prompt hint for a tenant."""
        with self._lock:
            data = self._load()
            if tenant_id not in data:
                raise ValueError(f"Tenant not found: {tenant_id!r}")
            data[tenant_id].get("custom_prompt_hints", {}).pop(bundle_id, None)
            self._persist(data)

    def get_custom_hint(self, tenant_id: str, bundle_id: str) -> str | None:
        """Return the custom hint for a bundle, or None."""
        with self._lock:
            data = self._load()
            record = data.get(tenant_id)
            if record is None:
                return None
            return record.get("custom_prompt_hints", {}).get(bundle_id)

    def rotate_api_key(self, tenant_id: str) -> str:
        """Generate a new API key for the tenant. Returns the plain key (shown once).
        Stores a SHA-256 hash of the key in the tenant record."""
        import hashlib
        import secrets
        with self._lock:
            data = self._load()
            if tenant_id not in data:
                raise ValueError(f"Tenant not found: {tenant_id!r}")
            key = "dd_" + secrets.token_urlsafe(32)
            key_hash = hashlib.sha256(key.encode()).hexdigest()
            data[tenant_id]["api_key_hash"] = key_hash
            data[tenant_id]["api_key_created_at"] = datetime.now(timezone.utc).isoformat()
            self._persist(data)
        return key

    def find_tenant_by_api_key(self, key: str) -> str | None:
        """Find and return the tenant_id for the given API key, or None."""
        import hashlib
        key_hash = hashlib.sha256(key.encode()).hexdigest()
        with self._lock:
            data = self._load()
        for tid, record in data.items():
            if record.get("api_key_hash") == key_hash and record.get("is_active", True):
                return tid
        return None

    def ensure_system_tenant(self) -> Tenant:
        """Create SYSTEM_TENANT_ID if it does not yet exist."""
        existing = self.get_tenant(SYSTEM_TENANT_ID)
        if existing is not None:
            return existing
        return self.create_tenant(
            tenant_id=SYSTEM_TENANT_ID,
            display_name="System (Default)",
            allowed_bundles=[],
        )


def migrate_legacy_data(data_dir: Path) -> None:
    """Copy legacy flat data files into the system tenant directory.

    For each legacy file that exists but whose destination does not yet exist,
    copies the file into ``<data_dir>/tenants/system/`` so that existing data
    is preserved after the multi-tenant migration.
    """
    try:
        system_dir = Path(data_dir) / "tenants" / "system"
        system_dir.mkdir(parents=True, exist_ok=True)

        legacy_pairs = [
            (Path(data_dir) / "feedback.jsonl", system_dir / "feedback.jsonl"),
            (Path(data_dir) / "prompt_overrides.json", system_dir / "prompt_overrides.json"),
            (Path(data_dir) / "ab_tests.json", system_dir / "ab_tests.json"),
            (Path(data_dir) / "eval_results.jsonl", system_dir / "eval_results.jsonl"),
        ]

        for src, dst in legacy_pairs:
            if src.exists() and not dst.exists():
                shutil.copy2(src, dst)
                _log.info("Migrated %s → %s", src.name, dst)
    except Exception as exc:
        _log.warning("migrate_legacy_data failed: %s", exc)
