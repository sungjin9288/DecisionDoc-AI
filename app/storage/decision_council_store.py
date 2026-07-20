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
from typing import Any, Callable, Literal, TypeVar

from app.schemas import DecisionCouncilSessionResponse
from app.storage.conditional_state import persist_text_if_current
from app.storage.state_backend import (
    StateBackend,
    StateBackendError,
    get_state_backend,
)
from app.storage.state_lock import state_lock
from app.tenant import require_tenant_id


class DecisionCouncilStoreError(ValueError):
    """Raised when persisted Decision Council state cannot be trusted."""


_MUTATION_IDS_FIELD = "_mutation_ids"
_MAX_TRACKED_MUTATIONS = 64
_MAX_MUTATION_ATTEMPTS = 32
_MutationResult = TypeVar("_MutationResult")


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

    def __init__(
        self, base_dir: str = "data", *, backend: StateBackend | None = None
    ) -> None:
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

    @staticmethod
    def _decode_records(raw: str) -> list[Any]:
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

    def _read_state(self, tenant_id: str) -> tuple[str | None, list[Any]]:
        tenant_id = require_tenant_id(tenant_id)
        try:
            raw = self._backend.read_text(self._relative_path(tenant_id))
        except (StateBackendError, UnicodeError) as exc:
            raise DecisionCouncilStoreError(
                "Invalid Decision Council state document"
            ) from exc
        if raw is None:
            return None, []
        return raw, self._decode_records(raw)

    def _load(self, tenant_id: str) -> list[Any]:
        return self._read_state(tenant_id)[1]

    @staticmethod
    def _mutation_ids(record: dict[str, Any]) -> list[str]:
        mutation_ids = record.get(_MUTATION_IDS_FIELD, [])
        if (
            not isinstance(mutation_ids, list)
            or len(mutation_ids) > _MAX_TRACKED_MUTATIONS
            or any(
                not isinstance(mutation_id, str) or not mutation_id
                for mutation_id in mutation_ids
            )
            or len(mutation_ids) != len(set(mutation_ids))
        ):
            raise DecisionCouncilStoreError("Invalid Decision Council mutation history")
        return list(mutation_ids)

    def _record_payload(
        self,
        session: DecisionCouncilSessionResponse,
        *,
        previous: dict[str, Any] | None,
        mutation_id: str,
    ) -> dict[str, Any]:
        mutation_ids = self._mutation_ids(previous or {})
        if mutation_id not in mutation_ids:
            mutation_ids.append(mutation_id)
        persisted = self._to_dict(session)
        persisted[_MUTATION_IDS_FIELD] = mutation_ids[-_MAX_TRACKED_MUTATIONS:]
        return persisted

    def _persist_if_current(
        self,
        tenant_id: str,
        *,
        expected: str | None,
        records: list[Any],
        committed: Callable[[list[Any]], bool],
    ) -> bool:
        tenant_id = require_tenant_id(tenant_id)
        self._owned_sessions(records, tenant_id=tenant_id)
        payload = json.dumps(records, ensure_ascii=False, indent=2)

        def decode(raw: str) -> list[Any]:
            observed = self._decode_records(raw)
            self._owned_sessions(observed, tenant_id=tenant_id)
            return observed

        try:
            return persist_text_if_current(
                backend=self._backend,
                relative_path=self._relative_path(tenant_id),
                expected=expected,
                replacement=payload,
                decode=decode,
                committed=committed,
                decode_errors=(DecisionCouncilStoreError,),
            )
        except StateBackendError as exc:
            raise DecisionCouncilStoreError(
                "Failed to persist Decision Council state"
            ) from exc

    def _mutate_state(
        self,
        tenant_id: str,
        change: Callable[[list[Any]], tuple[_MutationResult, bool]],
        *,
        committed: Callable[[list[Any]], bool],
    ) -> _MutationResult:
        tenant_id = require_tenant_id(tenant_id)
        for _ in range(_MAX_MUTATION_ATTEMPTS):
            expected, records = self._read_state(tenant_id)
            self._owned_sessions(records, tenant_id=tenant_id)
            result, changed = change(records)
            if not changed:
                return result
            if self._persist_if_current(
                tenant_id,
                expected=expected,
                records=records,
                committed=committed,
            ):
                return result
        raise DecisionCouncilStoreError(
            "Decision Council state changed too many times to persist safely"
        )

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
        public = dict(data)
        DecisionCouncilStore._mutation_ids(public)
        public.pop(_MUTATION_IDS_FIELD, None)
        return DecisionCouncilSessionResponse.model_validate(public)

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
            except DecisionCouncilStoreError:
                raise
            except (TypeError, ValueError):
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
            raise ValueError(
                "Decision Council session tenant does not match store scope"
            )
        session_key = self.build_session_key(
            project_id=session.project_id,
            use_case=session.use_case,
            target_bundle_type=session.target_bundle_type,
        )
        if session.session_key != session_key:
            raise ValueError(
                "Decision Council session key does not match session identity"
            )

        mutation_id = uuid.uuid4().hex
        new_session_id = session.session_id or str(uuid.uuid4())
        target_session_id: str | None = None
        target_bound = False
        session_payload = session.model_dump(
            mode="json",
            exclude=self._DERIVED_RESPONSE_FIELDS,
        )

        def apply(
            records: list[Any],
        ) -> tuple[
            tuple[DecisionCouncilSessionResponse, Literal["created", "updated"]],
            bool,
        ]:
            nonlocal target_bound, target_session_id
            now = _now_iso()
            existing = self._find(
                records,
                tenant_id=tenant_id,
                session_key=session_key,
            )
            if existing is None:
                if target_bound and target_session_id != new_session_id:
                    raise DecisionCouncilStoreError(
                        "Decision Council session identity changed during mutation"
                    )
                target_bound = True
                target_session_id = new_session_id
                stored = DecisionCouncilSessionResponse.model_validate(
                    {
                        **session_payload,
                        "session_id": new_session_id,
                        "session_key": session_key,
                        "session_revision": max(1, int(session.session_revision or 1)),
                        "created_at": session.created_at or now,
                        "updated_at": now,
                    }
                )
                records.append(
                    self._record_payload(
                        stored,
                        previous=None,
                        mutation_id=mutation_id,
                    )
                )
                return (
                    stored.model_copy(update={"operation": "created"}),
                    "created",
                ), True

            idx, current = existing
            if not target_bound:
                target_bound = True
                target_session_id = current.session_id
            elif target_session_id == new_session_id:
                target_session_id = current.session_id
            elif current.session_id != target_session_id:
                raise DecisionCouncilStoreError(
                    "Decision Council session identity changed during mutation"
                )

            previous = records[idx]
            if mutation_id in self._mutation_ids(previous):
                return (
                    current.model_copy(update={"operation": "updated"}),
                    "updated",
                ), False
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
            records[idx] = self._record_payload(
                stored,
                previous=previous,
                mutation_id=mutation_id,
            )
            return (
                stored.model_copy(update={"operation": "updated"}),
                "updated",
            ), True

        def was_committed(records: list[Any]) -> bool:
            existing = self._find(
                records,
                tenant_id=tenant_id,
                session_key=session_key,
            )
            if existing is None:
                return False
            idx, current = existing
            return (
                current.session_id == target_session_id
                and mutation_id in self._mutation_ids(records[idx])
            )

        with self._lock(tenant_id):
            return self._mutate_state(
                tenant_id=tenant_id,
                change=apply,
                committed=was_committed,
            )

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
