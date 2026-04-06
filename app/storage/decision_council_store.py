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
from typing import Literal

from app.schemas import DecisionCouncilSessionResponse
from app.storage.base import BaseJsonStore, atomic_write_text
from app.storage.state_backend import StateBackend, get_state_backend


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
        tenant_dir = self._base / "tenants" / tenant_id
        if self._backend.kind == "local":
            tenant_dir.mkdir(parents=True, exist_ok=True)
        return tenant_dir / "decision_council_sessions.json"

    def _relative_path(self, tenant_id: str) -> str:
        return str(Path("tenants") / tenant_id / "decision_council_sessions.json")

    def _load(self, tenant_id: str) -> list[dict]:
        raw = self._backend.read_text(self._relative_path(tenant_id))
        if raw is None:
            return []
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            return []

    def _save(self, tenant_id: str, records: list[dict]) -> None:
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
    ) -> tuple[list[dict], int, DecisionCouncilSessionResponse] | None:
        records = self._load(tenant_id)
        for idx, record in enumerate(records):
            if record.get("session_key") == session_key:
                session = self._from_dict(record)
                if session.tenant_id != tenant_id:
                    return None
                return records, idx, session
        return None

    def upsert_latest(
        self,
        session: DecisionCouncilSessionResponse,
    ) -> tuple[DecisionCouncilSessionResponse, Literal["created", "updated"]]:
        with self._lock:
            now = _now_iso()
            session_key = session.session_key or self.build_session_key(
                project_id=session.project_id,
                use_case=session.use_case,
                target_bundle_type=session.target_bundle_type,
            )
            existing = self._find(tenant_id=session.tenant_id, session_key=session_key)
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
                records = self._load(session.tenant_id)
                records.append(self._to_dict(stored))
                self._save(session.tenant_id, records)
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
            self._save(session.tenant_id, records)
            return stored.model_copy(update={"operation": "updated"}), "updated"

    def get_latest(
        self,
        *,
        tenant_id: str,
        project_id: str,
        use_case: str = "public_procurement",
        target_bundle_type: str = "bid_decision_kr",
    ) -> DecisionCouncilSessionResponse | None:
        with self._lock:
            session_key = self.build_session_key(
                project_id=project_id,
                use_case=use_case,
                target_bundle_type=target_bundle_type,
            )
            found = self._find(tenant_id=tenant_id, session_key=session_key)
            if found is None:
                return None
            return found[2]
