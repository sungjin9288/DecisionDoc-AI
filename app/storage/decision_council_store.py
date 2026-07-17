"""app/storage/decision_council_store.py — Tenant-scoped Decision Council state.

Stores one canonical latest council session per project/use-case/target bundle.

Storage:
  - data/tenants/{tenant_id}/decision_council_sessions.json
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from app.schemas import DecisionCouncilSessionResponse
from app.storage.state_backend import (
    StateBackend,
    StateBackendError,
    get_state_backend,
)
from app.storage.state_lock import state_lock
from app.tenant import require_tenant_id


class DecisionCouncilStoreError(ValueError):
    """Raised when persisted Decision Council state cannot be trusted."""


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise DecisionCouncilStoreError(
                f"Duplicate key in Decision Council state: {key!r}"
            )
        result[key] = value
    return result


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class DecisionCouncilStore:
    """Thread-safe, tenant-scoped JSON-backed Decision Council store."""

    _DERIVED_RESPONSE_FIELDS = {
        "operation",
        "supported_bundle_types",
        "current_procurement_binding_status",
        "current_procurement_binding_reason_code",
        "current_procurement_binding_summary",
        "current_procurement_updated_at",
        "current_procurement_recommendation_value",
        "current_procurement_missing_data_count",
        "current_procurement_action_needed_count",
        "current_procurement_blocking_hard_filter_count",
    }

    def __init__(self, base_dir: str = "data", *, backend: StateBackend | None = None) -> None:
        self._base = Path(base_dir)
        self._backend = backend or get_state_backend(data_dir=self._base)

    def _relative_path(self, tenant_id: str) -> str:
        tenant_id = require_tenant_id(tenant_id)
        return str(Path("tenants") / tenant_id / "decision_council_sessions.json")

    def _lock(self, tenant_id: str):
        relative_path = self._relative_path(tenant_id)
        return state_lock(
            self._backend,
            data_dir=self._base,
            relative_path=relative_path,
        )

    def _load(self, tenant_id: str) -> list[Any]:
        tenant_id = require_tenant_id(tenant_id)
        try:
            raw = self._backend.read_text(self._relative_path(tenant_id))
        except (StateBackendError, UnicodeError) as exc:
            raise DecisionCouncilStoreError(
                "Invalid Decision Council state document"
            ) from exc
        if raw is None:
            return []
        if not raw.strip():
            raise DecisionCouncilStoreError("Invalid Decision Council state document")
        try:
            records = json.loads(raw, object_pairs_hook=_unique_object)
        except (json.JSONDecodeError, ValueError) as exc:
            raise DecisionCouncilStoreError(
                "Invalid Decision Council state document"
            ) from exc
        if not isinstance(records, list):
            raise DecisionCouncilStoreError("Invalid Decision Council state document")
        return records

    def _save(self, tenant_id: str, records: list[Any]) -> None:
        self._owned_sessions(records, tenant_id=tenant_id)
        payload = json.dumps(records, ensure_ascii=False, indent=2)
        try:
            self._backend.write_text(self._relative_path(tenant_id), payload)
        except StateBackendError as exc:
            raise DecisionCouncilStoreError(
                "Failed to persist Decision Council state"
            ) from exc

    @staticmethod
    def build_session_key(
        *,
        project_id: str,
        use_case: str,
        target_bundle_type: str,
    ) -> str:
        return f"{project_id}:{use_case}:{target_bundle_type}"

    @staticmethod
    def _from_dict(data: dict) -> DecisionCouncilSessionResponse:
        return DecisionCouncilSessionResponse.model_validate(data)

    @staticmethod
    def _to_dict(session: DecisionCouncilSessionResponse) -> dict:
        return session.model_dump(
            mode="json",
            exclude=DecisionCouncilStore._DERIVED_RESPONSE_FIELDS,
        )

    def _owned_sessions(
        self,
        records: list[Any],
        *,
        tenant_id: str,
    ) -> list[tuple[int, DecisionCouncilSessionResponse]]:
        tenant_id = require_tenant_id(tenant_id)
        owned: list[tuple[int, DecisionCouncilSessionResponse]] = []
        session_ids: set[str] = set()
        session_keys: set[str] = set()

        for index, record in enumerate(records):
            if not isinstance(record, dict) or record.get("tenant_id") != tenant_id:
                continue
            try:
                session = self._from_dict(record)
            except ValueError:
                continue

            expected_key = self.build_session_key(
                project_id=session.project_id,
                use_case=session.use_case,
                target_bundle_type=session.target_bundle_type,
            )
            if session.session_key != expected_key:
                raise DecisionCouncilStoreError(
                    "Decision Council session key does not match persisted identity"
                )
            if session.session_id in session_ids:
                raise DecisionCouncilStoreError(
                    "Duplicate Decision Council session records"
                )
            if session.session_key in session_keys:
                raise DecisionCouncilStoreError(
                    "Duplicate Decision Council session records"
                )
            session_ids.add(session.session_id)
            session_keys.add(session.session_key)
            owned.append((index, session))
        return owned

    def _find(
        self,
        records: list[Any],
        *,
        tenant_id: str,
        session_key: str,
    ) -> tuple[int, DecisionCouncilSessionResponse] | None:
        return next(
            (
                (index, session)
                for index, session in self._owned_sessions(
                    records,
                    tenant_id=tenant_id,
                )
                if session.session_key == session_key
            ),
            None,
        )

    def upsert_latest(
        self,
        session: DecisionCouncilSessionResponse,
        *,
        tenant_id: str,
    ) -> tuple[DecisionCouncilSessionResponse, Literal["created", "updated"]]:
        tenant_id = require_tenant_id(tenant_id)
        if session.tenant_id != tenant_id:
            raise ValueError("Decision Council session tenant does not match store scope")
        session_key = self.build_session_key(
            project_id=session.project_id,
            use_case=session.use_case,
            target_bundle_type=session.target_bundle_type,
        )
        if session.session_key != session_key:
            raise ValueError("Decision Council session key does not match session identity")

        with self._lock(tenant_id):
            now = _now_iso()
            records = self._load(tenant_id)
            existing = self._find(
                records,
                tenant_id=tenant_id,
                session_key=session_key,
            )
            session_payload = session.model_dump(
                mode="json",
                exclude=self._DERIVED_RESPONSE_FIELDS,
            )
            if existing is None:
                stored = DecisionCouncilSessionResponse.model_validate(
                    {
                        **session_payload,
                        "session_id": session.session_id or str(uuid.uuid4()),
                        "session_key": session_key,
                        "session_revision": max(1, int(session.session_revision or 1)),
                        "created_at": session.created_at or now,
                        "updated_at": now,
                    }
                )
                records.append(self._to_dict(stored))
                self._save(tenant_id, records)
                return stored.model_copy(update={"operation": "created"}), "created"

            idx, current = existing
            stored = DecisionCouncilSessionResponse.model_validate(
                {
                    **session_payload,
                    "session_id": current.session_id,
                    "session_key": session_key,
                    "session_revision": current.session_revision + 1,
                    "created_at": current.created_at,
                    "updated_at": now,
                }
            )
            records[idx] = self._to_dict(stored)
            self._save(tenant_id, records)
            return stored.model_copy(update={"operation": "updated"}), "updated"

    def get_latest(
        self,
        *,
        tenant_id: str,
        project_id: str,
        use_case: str = "public_procurement",
        target_bundle_type: str = "bid_decision_kr",
    ) -> DecisionCouncilSessionResponse | None:
        tenant_id = require_tenant_id(tenant_id)
        session_key = self.build_session_key(
            project_id=project_id,
            use_case=use_case,
            target_bundle_type=target_bundle_type,
        )
        with self._lock(tenant_id):
            records = self._load(tenant_id)
            found = self._find(
                records,
                tenant_id=tenant_id,
                session_key=session_key,
            )
            if found is None:
                return None
            return found[1]
