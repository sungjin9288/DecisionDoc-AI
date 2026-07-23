"""Tenant-scoped server authority for issued authentication sessions."""

from __future__ import annotations

import json
import os
import re
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from app.auth.session_label import require_canonical_auth_session_label
from app.storage.auth_session_retention import (
    AUTH_SESSION_RETENTION_MAX_DAYS,
    AUTH_SESSION_RETENTION_MIN_DAYS,
    AUTH_SESSION_RETENTION_POLICY_DAYS,
    build_retention_recheck_receipt,
    build_retention_review_handoff,
    canonical_retention_json_bytes,
    validate_retention_review_handoff,
)
from app.storage.state_backend import StateBackend, StateBackendError, get_state_backend
from app.tenant import require_tenant_id


_CONTRACT_VERSION = "auth-session.v2"
_LEGACY_CONTRACT_VERSION = "auth-session.v1"
_SESSION_ID_PATTERN = re.compile(r"^[0-9a-f]{32}$")
_SESSION_LIFETIME = timedelta(days=30)
_MAX_CREATE_ATTEMPTS = 4
_MAX_MUTATION_ATTEMPTS = 32
_RETENTION_PREVIEW_CONTRACT_VERSION = "auth-session-retention-preview.v1"
_RETENTION_COMPARISON_CONTRACT_VERSION = "auth-session-retention-comparison.v1"
_LEGACY_RECORD_FIELDS = {
    "contract_version",
    "session_id",
    "tenant_id",
    "user_id",
    "credential_version",
    "created_at",
    "expires_at",
    "revoked_at",
}
_RECORD_FIELDS = _LEGACY_RECORD_FIELDS | {"label"}


class AuthSessionStoreError(RuntimeError):
    """Raised when authentication session state cannot be trusted."""


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise AuthSessionStoreError(
                f"Duplicate key in authentication session state: {key!r}"
            )
        result[key] = value
    return result


def require_auth_session_id(session_id: object) -> str:
    if not isinstance(session_id, str) or not _SESSION_ID_PATTERN.fullmatch(session_id):
        raise ValueError("session_id must be a lowercase 32-character hexadecimal ID")
    return session_id


def _require_user_id(user_id: object) -> str:
    if not isinstance(user_id, str) or not user_id or user_id != user_id.strip():
        raise ValueError("user_id must be a non-empty canonical string")
    return user_id


def _require_credential_version(credential_version: object) -> int:
    if type(credential_version) is not int or credential_version < 0:
        raise ValueError("credential_version must be a non-negative integer")
    return credential_version


def _parse_timestamp(value: object, *, field: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise AuthSessionStoreError(f"Invalid authentication session {field}")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise AuthSessionStoreError(
            f"Invalid authentication session {field}"
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise AuthSessionStoreError(f"Invalid authentication session {field}")
    return parsed.astimezone(timezone.utc)


class AuthSessionStore:
    """Persist and revoke one independently issued login session at a time."""

    def __init__(
        self,
        tenant_id: str,
        *,
        data_dir: str | Path | None = None,
        backend: StateBackend | None = None,
    ) -> None:
        self._tenant_id = require_tenant_id(tenant_id)
        self._data_dir = Path(data_dir or os.getenv("DATA_DIR", "./data"))
        self._backend = backend or get_state_backend(data_dir=self._data_dir)

    def _relative_path(self, session_id: str) -> str:
        return (
            Path("tenants")
            / self._tenant_id
            / "auth_sessions"
            / f"{require_auth_session_id(session_id)}.json"
        ).as_posix()

    def _relative_prefix(self) -> str:
        return (
            Path("tenants") / self._tenant_id / "auth_sessions"
        ).as_posix()

    def _validate_record(self, record: object, *, session_id: str) -> dict[str, Any]:
        if not isinstance(record, dict):
            raise AuthSessionStoreError("Invalid authentication session document")
        contract_version = record.get("contract_version")
        if contract_version == _CONTRACT_VERSION:
            expected_fields = _RECORD_FIELDS
        elif contract_version == _LEGACY_CONTRACT_VERSION:
            expected_fields = _LEGACY_RECORD_FIELDS
        else:
            raise AuthSessionStoreError("Invalid authentication session contract")
        if set(record) != expected_fields:
            raise AuthSessionStoreError("Invalid authentication session contract")
        if record.get("session_id") != session_id:
            raise AuthSessionStoreError("Authentication session identity mismatch")
        if record.get("tenant_id") != self._tenant_id:
            raise AuthSessionStoreError("Authentication session tenant mismatch")
        try:
            _require_user_id(record.get("user_id"))
            _require_credential_version(record.get("credential_version"))
            if contract_version == _CONTRACT_VERSION:
                require_canonical_auth_session_label(record.get("label"))
        except ValueError as exc:
            raise AuthSessionStoreError("Invalid authentication session authority") from exc

        created_at = _parse_timestamp(record.get("created_at"), field="created_at")
        expires_at = _parse_timestamp(record.get("expires_at"), field="expires_at")
        if expires_at <= created_at:
            raise AuthSessionStoreError("Invalid authentication session lifetime")
        revoked_at = record.get("revoked_at")
        if revoked_at is not None:
            parsed_revoked_at = _parse_timestamp(revoked_at, field="revoked_at")
            if parsed_revoked_at < created_at:
                raise AuthSessionStoreError("Invalid authentication session revocation")
        return record

    def _decode(self, raw: str, *, session_id: str) -> dict[str, Any]:
        if not raw.strip():
            raise AuthSessionStoreError("Invalid authentication session document")
        try:
            record = json.loads(raw, object_pairs_hook=_unique_object)
        except (json.JSONDecodeError, ValueError, AuthSessionStoreError) as exc:
            raise AuthSessionStoreError("Invalid authentication session document") from exc
        return self._validate_record(record, session_id=session_id)

    @staticmethod
    def _encode(record: dict[str, Any]) -> str:
        return json.dumps(record, ensure_ascii=False, indent=2, sort_keys=True)

    def _read(self, session_id: str) -> tuple[str | None, dict[str, Any] | None]:
        relative_path = self._relative_path(session_id)
        try:
            raw = self._backend.read_text(relative_path)
        except (StateBackendError, UnicodeError) as exc:
            raise AuthSessionStoreError(
                "Failed to read authentication session state"
            ) from exc
        if raw is None:
            return None, None
        return raw, self._decode(raw, session_id=session_id)

    def _list_validated_records(self) -> list[dict[str, Any]]:
        """Read every direct session object only after validating the whole prefix."""
        prefix = self._relative_prefix()
        child_prefix = f"{prefix}/"
        try:
            paths = self._backend.list_prefix(prefix)
        except StateBackendError as exc:
            raise AuthSessionStoreError(
                "Failed to list authentication session state"
            ) from exc

        records: list[dict[str, Any]] = []
        for relative_path in paths:
            if not relative_path.startswith(child_prefix):
                raise AuthSessionStoreError(
                    "Authentication session prefix contains an unexpected object"
                )
            filename = relative_path.removeprefix(child_prefix)
            if "/" in filename or not filename.endswith(".json"):
                raise AuthSessionStoreError(
                    "Authentication session prefix contains an unexpected object"
                )
            session_id = filename.removesuffix(".json")
            try:
                canonical_session_id = require_auth_session_id(session_id)
                raw = self._backend.read_text(relative_path)
            except (StateBackendError, UnicodeError, ValueError) as exc:
                raise AuthSessionStoreError(
                    "Failed to read authentication session inventory"
                ) from exc
            if raw is None:
                raise AuthSessionStoreError(
                    "Authentication session inventory changed during inspection"
                )
            records.append(self._decode(raw, session_id=canonical_session_id))
        return records

    def create(self, *, user_id: str, credential_version: int) -> str:
        canonical_user_id = _require_user_id(user_id)
        canonical_version = _require_credential_version(credential_version)
        created_at = _utcnow()
        expires_at = created_at + _SESSION_LIFETIME

        for _ in range(_MAX_CREATE_ATTEMPTS):
            session_id = uuid.uuid4().hex
            record = {
                "contract_version": _CONTRACT_VERSION,
                "session_id": session_id,
                "tenant_id": self._tenant_id,
                "user_id": canonical_user_id,
                "credential_version": canonical_version,
                "created_at": created_at.isoformat(),
                "expires_at": expires_at.isoformat(),
                "revoked_at": None,
                "label": None,
            }
            payload = self._encode(record)
            try:
                created = self._backend.write_text_if_absent(
                    self._relative_path(session_id),
                    payload,
                )
            except StateBackendError as exc:
                try:
                    observed = self._backend.read_text(self._relative_path(session_id))
                except (StateBackendError, UnicodeError):
                    observed = None
                if observed == payload:
                    return session_id
                raise AuthSessionStoreError(
                    "Failed to persist authentication session state"
                ) from exc
            if created:
                return session_id
        raise AuthSessionStoreError("Unable to allocate a unique authentication session")

    def is_current(
        self,
        session_id: str,
        *,
        user_id: str,
        credential_version: int,
    ) -> bool:
        canonical_session_id = require_auth_session_id(session_id)
        canonical_user_id = _require_user_id(user_id)
        canonical_version = _require_credential_version(credential_version)
        _, record = self._read(canonical_session_id)
        if record is None:
            return False
        return (
            record["user_id"] == canonical_user_id
            and record["credential_version"] == canonical_version
            and record["revoked_at"] is None
            and _parse_timestamp(record["expires_at"], field="expires_at") > _utcnow()
        )

    def list_active(
        self,
        *,
        user_id: str,
        credential_version: int,
    ) -> list[dict[str, Any]]:
        """Return current-version sessions after validating the whole tenant prefix."""
        canonical_user_id = _require_user_id(user_id)
        canonical_version = _require_credential_version(credential_version)
        now = _utcnow()
        active: list[dict[str, Any]] = []
        for record in self._list_validated_records():
            if (
                record["user_id"] == canonical_user_id
                and record["credential_version"] == canonical_version
                and record["revoked_at"] is None
                and _parse_timestamp(record["expires_at"], field="expires_at") > now
            ):
                active.append(record)

        active.sort(
            key=lambda record: (
                _parse_timestamp(record["created_at"], field="created_at"),
                record["session_id"],
            ),
            reverse=True,
        )
        return active

    def preview_retention(self, *, retention_days: int) -> dict[str, Any]:
        """Summarize old inactive sessions without exposing or changing records."""
        if (
            type(retention_days) is not int
            or retention_days < AUTH_SESSION_RETENTION_MIN_DAYS
            or retention_days > AUTH_SESSION_RETENTION_MAX_DAYS
        ):
            raise ValueError(
                "retention_days must be an integer between "
                f"{AUTH_SESSION_RETENTION_MIN_DAYS} and "
                f"{AUTH_SESSION_RETENTION_MAX_DAYS}"
            )

        now, inspected_sessions, active_sessions, inactive_sessions = (
            self._inspect_retention_state()
        )
        policy = self._summarize_retention_policy(
            inactive_sessions,
            now=now,
            retention_days=retention_days,
        )

        return {
            "contract_version": _RETENTION_PREVIEW_CONTRACT_VERSION,
            "generated_at": now.isoformat(),
            **policy,
            "inspected_sessions": inspected_sessions,
            "active_sessions": active_sessions,
            "read_only": True,
            "deletion_authorized": False,
        }

    def compare_retention_policies(self) -> dict[str, Any]:
        """Compare fixed retention policies against one validated inspection."""
        now, inspected_sessions, active_sessions, inactive_sessions = (
            self._inspect_retention_state()
        )
        policies = [
            self._summarize_retention_policy(
                inactive_sessions,
                now=now,
                retention_days=retention_days,
            )
            for retention_days in AUTH_SESSION_RETENTION_POLICY_DAYS
        ]
        return {
            "contract_version": _RETENTION_COMPARISON_CONTRACT_VERSION,
            "generated_at": now.isoformat(),
            "policy_days": list(AUTH_SESSION_RETENTION_POLICY_DAYS),
            "inspected_sessions": inspected_sessions,
            "active_sessions": active_sessions,
            "policies": policies,
            "read_only": True,
            "deletion_authorized": False,
            "snapshot_atomic": False,
            "requires_recheck_before_mutation": True,
        }

    def build_retention_review_handoff(self, *, retention_days: int) -> dict[str, Any]:
        """Create review evidence from one read-only retention inspection."""
        comparison = self.compare_retention_policies()
        return build_retention_review_handoff(
            tenant_id=self._tenant_id,
            retention_days=retention_days,
            comparison=comparison,
        )

    @staticmethod
    def serialize_retention_review_handoff(handoff: dict[str, Any]) -> bytes:
        return canonical_retention_json_bytes(handoff)

    def recheck_retention_review_handoff(
        self,
        *,
        source_handoff: object,
        source_handoff_sha256: object,
    ) -> dict[str, Any]:
        """Compare a verified handoff with one fresh read-only inspection."""
        source = validate_retention_review_handoff(
            source_handoff,
            expected_tenant_id=self._tenant_id,
            expected_sha256=source_handoff_sha256,
        )
        current = self.build_retention_review_handoff(
            retention_days=source["selected_policy_days"]
        )
        return build_retention_recheck_receipt(
            source_handoff=source,
            source_handoff_sha256=source_handoff_sha256,
            current_handoff=current,
        )

    @staticmethod
    def serialize_retention_recheck_receipt(receipt: dict[str, Any]) -> bytes:
        return canonical_retention_json_bytes(receipt)

    def _inspect_retention_state(
        self,
    ) -> tuple[datetime, int, int, list[tuple[datetime, str]]]:
        now = _utcnow()
        records = self._list_validated_records()
        active_sessions = 0
        inactive_sessions: list[tuple[datetime, str]] = []

        for record in records:
            expires_at = _parse_timestamp(record["expires_at"], field="expires_at")
            revoked_at = (
                _parse_timestamp(record["revoked_at"], field="revoked_at")
                if record["revoked_at"] is not None
                else None
            )
            if revoked_at is None and expires_at > now:
                active_sessions += 1
                continue

            inactive_at = min(expires_at, revoked_at) if revoked_at else expires_at
            reason = (
                "revoked"
                if revoked_at is not None and revoked_at <= expires_at
                else "expired"
            )
            inactive_sessions.append((inactive_at, reason))

        return now, len(records), active_sessions, inactive_sessions

    @staticmethod
    def _summarize_retention_policy(
        inactive_sessions: list[tuple[datetime, str]],
        *,
        now: datetime,
        retention_days: int,
    ) -> dict[str, Any]:
        eligible_before = now - timedelta(days=retention_days)
        eligible_by_reason = {"expired": 0, "revoked": 0}
        eligible_inactive_times: list[datetime] = []

        for inactive_at, reason in inactive_sessions:
            if inactive_at <= eligible_before:
                eligible_by_reason[reason] += 1
                eligible_inactive_times.append(inactive_at)

        eligible_sessions = len(eligible_inactive_times)
        return {
            "retention_days": retention_days,
            "eligible_before": eligible_before.isoformat(),
            "eligible_sessions": eligible_sessions,
            "eligible_by_reason": eligible_by_reason,
            "retained_inactive_sessions": len(inactive_sessions) - eligible_sessions,
            "oldest_eligible_inactive_at": (
                min(eligible_inactive_times).isoformat()
                if eligible_inactive_times
                else None
            ),
        }

    def set_label(
        self,
        session_id: str,
        *,
        user_id: str,
        credential_version: int,
        label: str | None,
    ) -> bool:
        """Set an owned active session label with optimistic concurrency."""
        canonical_session_id = require_auth_session_id(session_id)
        canonical_user_id = _require_user_id(user_id)
        canonical_version = _require_credential_version(credential_version)
        canonical_label = require_canonical_auth_session_label(label)
        relative_path = self._relative_path(canonical_session_id)

        for _ in range(_MAX_MUTATION_ATTEMPTS):
            expected, record = self._read(canonical_session_id)
            if (
                record is None
                or record["user_id"] != canonical_user_id
                or record["credential_version"] != canonical_version
                or record["revoked_at"] is not None
                or _parse_timestamp(record["expires_at"], field="expires_at")
                <= _utcnow()
            ):
                return False
            if (
                record["contract_version"] == _CONTRACT_VERSION
                and record.get("label") == canonical_label
            ):
                return True

            replacement_record = {
                **record,
                "contract_version": _CONTRACT_VERSION,
                "label": canonical_label,
            }
            replacement = self._encode(replacement_record)
            try:
                replaced = self._backend.replace_text_if_equal(
                    relative_path,
                    expected=expected or "",
                    replacement=replacement,
                )
            except StateBackendError as exc:
                try:
                    observed = self._backend.read_text(relative_path)
                except (StateBackendError, UnicodeError):
                    observed = None
                if observed == replacement:
                    return True
                if observed is not None:
                    try:
                        observed_record = self._decode(
                            observed,
                            session_id=canonical_session_id,
                        )
                    except AuthSessionStoreError:
                        pass
                    else:
                        if (
                            observed_record["contract_version"] == _CONTRACT_VERSION
                            and observed_record["user_id"] == canonical_user_id
                            and observed_record["credential_version"]
                            == canonical_version
                            and observed_record.get("label") == canonical_label
                        ):
                            return True
                raise AuthSessionStoreError(
                    "Failed to update authentication session label"
                ) from exc
            if replaced:
                return True

        raise AuthSessionStoreError(
            "Authentication session changed too many times to update safely"
        )

    def revoke_others(
        self,
        *,
        current_session_id: str,
        user_id: str,
        credential_version: int,
    ) -> int:
        """Revoke the active sessions visible before this operation, except current."""
        canonical_current_id = require_auth_session_id(current_session_id)
        records = self.list_active(
            user_id=user_id,
            credential_version=credential_version,
        )
        other_session_ids = [
            record["session_id"]
            for record in records
            if record["session_id"] != canonical_current_id
        ]

        for session_id in other_session_ids:
            if not self.revoke(session_id, user_id=user_id):
                raise AuthSessionStoreError(
                    "Authentication session authority changed during bulk revocation"
                )
        return len(other_session_ids)

    def revoke_all(
        self,
        *,
        current_session_id: str,
        user_id: str,
        credential_version: int,
    ) -> int:
        """Revoke every active session, keeping current usable until the final write."""
        canonical_current_id = require_auth_session_id(current_session_id)
        records = self.list_active(
            user_id=user_id,
            credential_version=credential_version,
        )
        active_session_ids = [record["session_id"] for record in records]
        if canonical_current_id not in active_session_ids:
            raise AuthSessionStoreError(
                "Current authentication session is not active in the validated snapshot"
            )
        ordered_session_ids = [
            session_id
            for session_id in active_session_ids
            if session_id != canonical_current_id
        ]
        ordered_session_ids.append(canonical_current_id)

        for session_id in ordered_session_ids:
            if not self.revoke(session_id, user_id=user_id):
                raise AuthSessionStoreError(
                    "Authentication session authority changed during full revocation"
                )
        return len(ordered_session_ids)

    def revoke(self, session_id: str, *, user_id: str) -> bool:
        canonical_session_id = require_auth_session_id(session_id)
        canonical_user_id = _require_user_id(user_id)
        relative_path = self._relative_path(canonical_session_id)

        for _ in range(_MAX_MUTATION_ATTEMPTS):
            expected, record = self._read(canonical_session_id)
            if record is None or record["user_id"] != canonical_user_id:
                return False
            if record["revoked_at"] is not None:
                return True

            replacement_record = {
                **record,
                "revoked_at": _utcnow().isoformat(),
            }
            replacement = self._encode(replacement_record)
            try:
                replaced = self._backend.replace_text_if_equal(
                    relative_path,
                    expected=expected or "",
                    replacement=replacement,
                )
            except StateBackendError as exc:
                try:
                    observed = self._backend.read_text(relative_path)
                except (StateBackendError, UnicodeError):
                    observed = None
                if observed == replacement:
                    return True
                if observed is not None:
                    try:
                        observed_record = self._decode(
                            observed,
                            session_id=canonical_session_id,
                        )
                    except AuthSessionStoreError:
                        pass
                    else:
                        if (
                            observed_record["user_id"] == canonical_user_id
                            and observed_record["revoked_at"] is not None
                        ):
                            return True
                raise AuthSessionStoreError(
                    "Failed to revoke authentication session"
                ) from exc
            if replaced:
                return True

        raise AuthSessionStoreError(
            "Authentication session changed too many times to revoke safely"
        )


def get_auth_session_store(
    tenant_id: str,
    *,
    data_dir: str | Path | None = None,
    backend: StateBackend | None = None,
) -> AuthSessionStore:
    return AuthSessionStore(tenant_id, data_dir=data_dir, backend=backend)
