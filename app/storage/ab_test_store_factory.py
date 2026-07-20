"""Cached A/B test store construction."""

from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import Any

from app.storage import ab_test_store as ab_test_store_module
from app.storage.state_backend import StateBackend, get_state_backend
from app.storage.state_lock import state_backend_identity
from app.tenant import require_tenant_id

_stores: dict[tuple[Any, ...], ab_test_store_module.ABTestStore] = {}
_stores_guard = threading.Lock()


def get_cached_ab_test_store(
    tenant_id: str,
    data_dir: str | Path | None = None,
    *,
    backend: StateBackend | None = None,
) -> ab_test_store_module.ABTestStore:
    """Return one cached store for a tenant, data root, and backend."""
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
    with _stores_guard:
        store = _stores.get(key)
        if store is None:
            store = ab_test_store_module.ABTestStore(
                root,
                tenant_id=tenant_id,
                backend=selected_backend,
            )
            _stores[key] = store
        return store


def clear_cached_ab_test_stores() -> None:
    """Discard cached stores after application configuration changes."""
    with _stores_guard:
        _stores.clear()
