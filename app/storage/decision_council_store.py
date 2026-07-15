"""app/storage/decision_council_store.py — Tenant-scoped Decision Council state.

Stores one canonical latest council session per project/use-case/target bundle.

Storage:
  - data/tenants/{tenant_id}/decision_council_sessions.json
"""
from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from app.schemas import DecisionCouncilSessionResponse
from app.storage.base import BaseJsonStore, atomic_write_text
from app.storage.state_backend import StateBackend, get_state_backend
from app.tenant import require_tenant_id


_path_locks: dict[Path, threading.Lock] = {}
_path_locks_guard = threading.Lock()


def _lock_for_path(path: Path) -> threading.Lock:
    with _path_locks_guard:
        return _path_locks.setdefault(path.resolve(), threading.Lock())


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class DecisionCouncilStore(BaseJsonStore):
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
        super().__init__()
        self._base = Path(base_dir)
        self._backend = backend or get_state_backend(data_dir=self._base)

    def _get_path(self) -> Path:
        return self._base / "tenants"

    def _path(self, tenant_id: str) -> Path:
        tenant_id = require_tenant_id(tenant_id)
        return self._base / "tenants" / tenant_id / "decision_council_sessions.json"

    def _relative_path(self, tenant_id: str) -> str:
        tenant_id = require_tenant_id(tenant_id)
        return str(Path("tenants") / tenant_id / "decision_council_sessions.json")

    def _load(self, tenant_id: str) -> list[Any]:
        raw = self._backend.read_text(self._relative_path(tenant_id))
        if raw is None or not raw.strip():
            return []
        try:
            records = json.loads(raw)
        except (json.JSONDecodeError, ValueError) as exc:
            raise ValueError("Invalid Decision Council state document") from exc
        if not isinstance(records, list):
            raise ValueError("Invalid Decision Council state document")
        return records

    def _save(self, tenant_id: str, records: list[Any]) -> None:
        payload = json.dumps(records, ensure_ascii=False, indent=2)
        if self._backend.kind == "local":
            atomic_write_text(self._path(tenant_id), payload)
            return
        self._backend.write_text(self._relative_path(tenant_id), payload)

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

    def _find(
        self,
        *,
        tenant_id: str,
        session_key: str,
    ) -> tuple[list[Any], int, DecisionCouncilSessionResponse] | None:
        records = self._load(tenant_id)
        matches: list[tuple[int, DecisionCouncilSessionResponse]] = []
        for idx, record in enumerate(records):
            if not isinstance(record, dict):
                continue
            if record.get("session_key") == session_key:
                if record.get("tenant_id") != tenant_id:
                    continue
                try:
                    session = self._from_dict(record)
                except ValueError:
                    continue
                matches.append((idx, session))
        if len(matches) > 1:
            raise ValueError("Duplicate Decision Council session records")
        if not matches:
            return None
        idx, session = matches[0]
        return records, idx, session

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

        with _lock_for_path(self._path(tenant_id)):
            now = _now_iso()
            existing = self._find(tenant_id=tenant_id, session_key=session_key)
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
                records = self._load(tenant_id)
                records.append(self._to_dict(stored))
                self._save(tenant_id, records)
                return stored.model_copy(update={"operation": "created"}), "created"

            records, idx, current = existing
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
        with _lock_for_path(self._path(tenant_id)):
            session_key = self.build_session_key(
                project_id=project_id,
                use_case=use_case,
                target_bundle_type=target_bundle_type,
            )
            found = self._find(tenant_id=tenant_id, session_key=session_key)
            if found is None:
                return None
            return found[2]
