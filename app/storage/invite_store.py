"""app/storage/invite_store.py — Team member invitation links."""
from __future__ import annotations

import logging
import json
import os
import threading
import uuid
from collections.abc import Callable
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, TypeVar

from app.storage.state_backend import StateBackend, StateBackendError, get_state_backend
from app.tenant import require_tenant_id

_log = logging.getLogger("decisiondoc.invite")
_Result = TypeVar("_Result")


_invite_locks: dict[Path, threading.RLock] = {}
_invite_locks_guard = threading.Lock()
_MAX_MUTATION_ATTEMPTS = 32
_MUTATION_IDS_FIELD = "_mutation_ids"
_ACCEPTANCE_ID_FIELD = "_acceptance_id"
_MAX_TRACKED_MUTATIONS = 64


class InviteStoreError(RuntimeError):
    """Raised when persisted invitation state cannot be trusted."""


def _lock_for_path(path: Path) -> threading.RLock:
    with _invite_locks_guard:
        return _invite_locks.setdefault(path.resolve(), threading.RLock())


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise InviteStoreError(f"Duplicate key in invite state: {key!r}")
        result[key] = value
    return result


class InviteStore:
    """Thread-safe invitation state scoped to a single tenant."""

    def __init__(
        self,
        tenant_id: str,
        *,
        data_dir: str | Path | None = None,
        backend: StateBackend | None = None,
    ) -> None:
        self._tenant_id = require_tenant_id(tenant_id)
        self._data_dir = Path(data_dir or os.getenv("DATA_DIR", "./data"))
        self._relative_path = str(
            Path("tenants") / self._tenant_id / "invites.json"
        )
        self._path_val = self._data_dir / self._relative_path
        self._backend = backend or get_state_backend(data_dir=self._data_dir)
        self._lock = _lock_for_path(self._path_val)

    def _validate_record(self, invite_id: str, record: object) -> None:
        if not isinstance(record, dict):
            raise InviteStoreError("Invalid invite record")
        stored_tenant_id = record.get("tenant_id")
        if not isinstance(stored_tenant_id, str) or not stored_tenant_id:
            raise InviteStoreError("Invalid invite identity")
        if stored_tenant_id != self._tenant_id:
            return
        required_strings = (
            "invite_id",
            "tenant_id",
            "email",
            "role",
            "created_by",
            "created_at",
            "expires_at",
        )
        if any(not isinstance(record.get(field), str) for field in required_strings):
            raise InviteStoreError("Invalid invite record")
        if record["invite_id"] != invite_id or not record["invite_id"]:
            raise InviteStoreError("Invalid invite identity")
        if record["role"] not in {"admin", "member", "viewer"}:
            raise InviteStoreError("Invalid invite role")
        if not isinstance(record.get("is_active"), bool):
            raise InviteStoreError("Invalid invite active state")
        used_at = record.get("used_at")
        if used_at is not None and not isinstance(used_at, str):
            raise InviteStoreError("Invalid invite use timestamp")
        if not isinstance(record.get("job_title", ""), str):
            raise InviteStoreError("Invalid invite job title")
        profiles = record.get("assigned_ai_profiles", [])
        if not isinstance(profiles, list) or any(
            not isinstance(profile, str) for profile in profiles
        ):
            raise InviteStoreError("Invalid invite AI profiles")
        try:
            datetime.fromisoformat(record["created_at"])
            datetime.fromisoformat(record["expires_at"])
            if used_at is not None:
                datetime.fromisoformat(used_at)
        except ValueError as exc:
            raise InviteStoreError("Invalid invite timestamp") from exc
        acceptance_id = record.get(_ACCEPTANCE_ID_FIELD)
        if acceptance_id is not None and (
            not isinstance(acceptance_id, str)
            or not acceptance_id
            or record["is_active"]
            or used_at is None
        ):
            raise InviteStoreError("Invalid invite acceptance state")
        self._mutation_ids(record)

    def _validate_state(self, data: object) -> dict[str, dict]:
        if not isinstance(data, dict):
            raise InviteStoreError("Invalid invite state document")
        for invite_id, record in data.items():
            if not isinstance(invite_id, str):
                raise InviteStoreError("Invalid invite record")
            self._validate_record(invite_id, record)
        return data

    def _read_state(self) -> tuple[str | None, dict[str, dict]]:
        try:
            raw = self._backend.read_text(self._relative_path)
        except (StateBackendError, UnicodeError) as exc:
            raise InviteStoreError("Invalid invite state document") from exc
        if raw is None:
            return None, {}
        return raw, self._decode_state(raw)

    def _decode_state(self, raw: str) -> dict[str, dict]:
        if not raw.strip():
            raise InviteStoreError("Invalid invite state document")
        try:
            data = json.loads(raw, object_pairs_hook=_unique_object)
        except (json.JSONDecodeError, InviteStoreError, ValueError) as exc:
            raise InviteStoreError("Invalid invite state document") from exc
        return self._validate_state(data)

    def _load(self) -> dict[str, dict]:
        return self._read_state()[1]

    @staticmethod
    def _mutation_ids(record: dict) -> list[str]:
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
            raise InviteStoreError("Invalid invite mutation history")
        return list(mutation_ids)

    def _record_mutation(
        self,
        record: dict,
        *,
        previous: dict | None,
        mutation_id: str,
    ) -> dict:
        mutation_ids = self._mutation_ids(previous or {})
        if mutation_id not in mutation_ids:
            mutation_ids.append(mutation_id)
        persisted = dict(record)
        persisted[_MUTATION_IDS_FIELD] = mutation_ids[-_MAX_TRACKED_MUTATIONS:]
        return persisted

    @staticmethod
    def _public_record(record: dict) -> dict:
        return {
            key: value
            for key, value in record.items()
            if not key.startswith("_")
        }

    def _persist_if_current(
        self,
        *,
        expected: str | None,
        data: dict[str, dict],
        committed: Callable[[dict[str, dict]], bool],
    ) -> bool:
        self._validate_state(data)
        payload = json.dumps(data, ensure_ascii=False, indent=2)
        try:
            if expected is None:
                return self._backend.write_text_if_absent(
                    self._relative_path,
                    payload,
                )
            return self._backend.replace_text_if_equal(
                self._relative_path,
                expected=expected,
                replacement=payload,
            )
        except StateBackendError as exc:
            try:
                observed = self._backend.read_text(self._relative_path)
            except (StateBackendError, UnicodeError):
                observed = None
            if observed == payload:
                return True
            if observed is not None:
                try:
                    observed_data = self._decode_state(observed)
                except InviteStoreError:
                    pass
                else:
                    if committed(observed_data):
                        return True
            raise InviteStoreError("Failed to persist invite state") from exc

    def _mutate(
        self,
        change: Callable[
            [dict[str, dict]],
            tuple[_Result, bool],
        ],
        *,
        committed: Callable[[dict[str, dict]], bool],
    ) -> _Result:
        for _ in range(_MAX_MUTATION_ATTEMPTS):
            expected, data = self._read_state()
            result, changed = change(data)
            if not changed:
                return result
            if self._persist_if_current(
                expected=expected,
                data=data,
                committed=committed,
            ):
                return result
        raise InviteStoreError(
            "Invite state changed too many times to persist safely"
        )

    def create(
        self,
        invite_id: str,
        email: str,
        role: str,
        created_by: str,
        expires_days: int = 7,
        job_title: str = "",
        assigned_ai_profiles: list[str] | None = None,
    ) -> dict:
        if (
            not isinstance(invite_id, str)
            or not invite_id
            or not isinstance(email, str)
            or not isinstance(role, str)
            or not isinstance(created_by, str)
            or not isinstance(job_title, str)
            or not isinstance(expires_days, int)
        ):
            raise ValueError("Invalid invite record")
        if assigned_ai_profiles is not None and (
            not isinstance(assigned_ai_profiles, list)
            or any(not isinstance(profile, str) for profile in assigned_ai_profiles)
        ):
            raise ValueError("Invalid invite AI profiles")
        now = datetime.now()
        mutation_id = uuid.uuid4().hex
        invite = {
            "invite_id": invite_id,
            "tenant_id": self._tenant_id,
            "email": email,
            "role": role,
            "created_by": created_by,
            "created_at": now.isoformat(),
            "expires_at": (now + timedelta(days=expires_days)).isoformat(),
            "job_title": job_title,
            "assigned_ai_profiles": list(assigned_ai_profiles or []),
            "is_active": True,
            "used_at": None,
        }
        self._validate_record(invite_id, invite)
        persisted = self._record_mutation(
            invite,
            previous=None,
            mutation_id=mutation_id,
        )

        def apply(data: dict[str, dict]) -> tuple[dict, bool]:
            if invite_id in data:
                raise ValueError(f"초대 ID가 이미 존재합니다: {invite_id}")
            data[invite_id] = persisted
            return self._public_record(invite), True

        def was_committed(data: dict[str, dict]) -> bool:
            record = data.get(invite_id)
            return bool(
                record
                and record.get("tenant_id") == self._tenant_id
                and mutation_id in self._mutation_ids(record)
            )

        with self._lock:
            return self._mutate(apply, committed=was_committed)

    def get(self, invite_id: str) -> dict | None:
        with self._lock:
            data = self._load()
            invite = data.get(invite_id)
            if not invite or invite.get("tenant_id") != self._tenant_id:
                return None
            public_invite = self._public_record(invite)
            expires_at = datetime.fromisoformat(invite["expires_at"])
            if expires_at < datetime.now(expires_at.tzinfo):
                public_invite["is_active"] = False
            return public_invite

    def accept(
        self,
        invite_id: str,
        create_account: Callable[[dict], _Result],
    ) -> _Result | None:
        """Claim one invitation before invoking the account creation callback."""
        acceptance_id = uuid.uuid4().hex
        claim_mutation_id = uuid.uuid4().hex
        accepted_at = datetime.now().isoformat()

        def claim(data: dict[str, dict]) -> tuple[dict | None, bool]:
            invite = data.get(invite_id)
            if not invite or invite.get("tenant_id") != self._tenant_id:
                return None, False
            expires_at = datetime.fromisoformat(invite["expires_at"])
            if not invite["is_active"] or expires_at < datetime.now(expires_at.tzinfo):
                return None, False
            public_invite = self._public_record(invite)
            updated = dict(invite)
            updated["is_active"] = False
            updated["used_at"] = accepted_at
            updated[_ACCEPTANCE_ID_FIELD] = acceptance_id
            data[invite_id] = self._record_mutation(
                updated,
                previous=invite,
                mutation_id=claim_mutation_id,
            )
            return public_invite, True

        def claim_was_committed(data: dict[str, dict]) -> bool:
            record = data.get(invite_id)
            return bool(
                record
                and record.get("tenant_id") == self._tenant_id
                and record.get(_ACCEPTANCE_ID_FIELD) == acceptance_id
                and claim_mutation_id in self._mutation_ids(record)
            )

        with self._lock:
            invite = self._mutate(claim, committed=claim_was_committed)
        if invite is None:
            return None

        try:
            result = create_account(invite)
        except Exception:
            self._rollback_acceptance(invite_id, acceptance_id=acceptance_id)
            raise

        self._finish_acceptance(invite_id, acceptance_id=acceptance_id)
        return result

    def _rollback_acceptance(
        self,
        invite_id: str,
        *,
        acceptance_id: str,
    ) -> None:
        mutation_id = uuid.uuid4().hex

        def apply(data: dict[str, dict]) -> tuple[None, bool]:
            invite = data.get(invite_id)
            if (
                not invite
                or invite.get("tenant_id") != self._tenant_id
                or invite.get(_ACCEPTANCE_ID_FIELD) != acceptance_id
            ):
                raise InviteStoreError("Invite acceptance claim was lost")
            updated = dict(invite)
            updated["is_active"] = True
            updated["used_at"] = None
            updated.pop(_ACCEPTANCE_ID_FIELD, None)
            data[invite_id] = self._record_mutation(
                updated,
                previous=invite,
                mutation_id=mutation_id,
            )
            return None, True

        def was_committed(data: dict[str, dict]) -> bool:
            record = data.get(invite_id)
            return bool(
                record
                and record.get("tenant_id") == self._tenant_id
                and record.get(_ACCEPTANCE_ID_FIELD) is None
                and record.get("is_active") is True
                and mutation_id in self._mutation_ids(record)
            )

        with self._lock:
            self._mutate(apply, committed=was_committed)

    def _finish_acceptance(
        self,
        invite_id: str,
        *,
        acceptance_id: str,
    ) -> None:
        mutation_id = uuid.uuid4().hex

        def apply(data: dict[str, dict]) -> tuple[None, bool]:
            invite = data.get(invite_id)
            if (
                not invite
                or invite.get("tenant_id") != self._tenant_id
                or invite.get(_ACCEPTANCE_ID_FIELD) != acceptance_id
            ):
                raise InviteStoreError("Invite acceptance claim was lost")
            updated = dict(invite)
            updated.pop(_ACCEPTANCE_ID_FIELD, None)
            data[invite_id] = self._record_mutation(
                updated,
                previous=invite,
                mutation_id=mutation_id,
            )
            return None, True

        def was_committed(data: dict[str, dict]) -> bool:
            record = data.get(invite_id)
            return bool(
                record
                and record.get("tenant_id") == self._tenant_id
                and record.get(_ACCEPTANCE_ID_FIELD) is None
                and record.get("is_active") is False
                and mutation_id in self._mutation_ids(record)
            )

        with self._lock:
            self._mutate(apply, committed=was_committed)

    def mark_used(self, invite_id: str) -> None:
        mutation_id = uuid.uuid4().hex
        used_at = datetime.now().isoformat()

        def apply(data: dict[str, dict]) -> tuple[None, bool]:
            invite = data.get(invite_id)
            if not invite or invite.get("tenant_id") != self._tenant_id:
                return None, False
            updated = dict(invite)
            updated["is_active"] = False
            updated["used_at"] = used_at
            data[invite_id] = self._record_mutation(
                updated,
                previous=invite,
                mutation_id=mutation_id,
            )
            return None, True

        def was_committed(data: dict[str, dict]) -> bool:
            record = data.get(invite_id)
            return bool(
                record
                and record.get("tenant_id") == self._tenant_id
                and mutation_id in self._mutation_ids(record)
            )

        with self._lock:
            self._mutate(apply, committed=was_committed)
