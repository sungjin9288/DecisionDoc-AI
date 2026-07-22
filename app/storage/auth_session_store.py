"""Tenant-scoped server authority for issued authentication sessions."""

from __future__ import annotations

import json
import os
import re
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from app.storage.state_backend import StateBackend, StateBackendError, get_state_backend
from app.tenant import require_tenant_id


_CONTRACT_VERSION = "auth-session.v1"
_SESSION_ID_PATTERN = re.compile(r"^[0-9a-f]{32}$")
_SESSION_LIFETIME = timedelta(days=30)
_MAX_CREATE_ATTEMPTS = 4
_MAX_REVOKE_ATTEMPTS = 32
_RECORD_FIELDS = {
    "contract_version",
    "session_id",
    "tenant_id",
    "user_id",
    "credential_version",
    "created_at",
    "expires_at",
    "revoked_at",
}


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

    def _validate_record(self, record: object, *, session_id: str) -> dict[str, Any]:
        if not isinstance(record, dict) or set(record) != _RECORD_FIELDS:
            raise AuthSessionStoreError("Invalid authentication session document")
        if record.get("contract_version") != _CONTRACT_VERSION:
            raise AuthSessionStoreError("Invalid authentication session contract")
        if record.get("session_id") != session_id:
            raise AuthSessionStoreError("Authentication session identity mismatch")
        if record.get("tenant_id") != self._tenant_id:
            raise AuthSessionStoreError("Authentication session tenant mismatch")
        try:
            _require_user_id(record.get("user_id"))
            _require_credential_version(record.get("credential_version"))
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

    def revoke(self, session_id: str, *, user_id: str) -> bool:
        canonical_session_id = require_auth_session_id(session_id)
        canonical_user_id = _require_user_id(user_id)
        relative_path = self._relative_path(canonical_session_id)

        for _ in range(_MAX_REVOKE_ATTEMPTS):
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
