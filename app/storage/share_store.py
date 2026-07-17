"""Tenant-scoped storage for public document share links."""

from __future__ import annotations

import json
import os
import secrets
import threading
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, TypeVar

from app.storage.state_backend import StateBackend, StateBackendError, get_state_backend
from app.tenant import require_tenant_id


_share_locks: dict[Path, threading.RLock] = {}
_share_locks_guard = threading.Lock()
_MAX_MUTATION_ATTEMPTS = 32
_MUTATION_IDS_FIELD = "_mutation_ids"
_MAX_TRACKED_MUTATIONS = 64
_MutationResult = TypeVar("_MutationResult")


class ShareStoreError(RuntimeError):
    """Raised when persisted share-link state cannot be trusted."""


def _lock_for_path(path: Path) -> threading.RLock:
    with _share_locks_guard:
        return _share_locks.setdefault(path.resolve(), threading.RLock())


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ShareStoreError(f"Duplicate key in share state: {key!r}")
        result[key] = value
    return result


def _is_elapsed(timestamp: str) -> bool:
    expires_at = datetime.fromisoformat(timestamp)
    now = datetime.now(expires_at.tzinfo) if expires_at.tzinfo else datetime.now()
    return expires_at < now


@dataclass
class ShareLink:
    share_id: str
    tenant_id: str
    request_id: str
    title: str
    created_by: str
    created_at: str
    expires_at: str
    access_count: int = 0
    last_accessed_at: str = ""
    is_active: bool = True
    revoked_at: str = ""
    revoked_by: str = ""
    revoked_by_username: str = ""
    bundle_id: str = ""
    project_id: str = ""
    project_document_id: str = ""
    source_fingerprint: str = ""
    decision_council_document_status: str = ""
    decision_council_document_status_tone: str = ""
    decision_council_document_status_copy: str = ""
    decision_council_document_status_summary: str = ""
    procurement_review_document_status: str = ""
    procurement_review_document_status_tone: str = ""
    procurement_review_document_status_copy: str = ""
    procurement_review_document_status_summary: str = ""


class ShareStore:
    """Thread-safe public share-link state scoped to a single tenant."""

    _optional_string_fields = (
        "last_accessed_at",
        "revoked_at",
        "revoked_by",
        "revoked_by_username",
        "bundle_id",
        "project_id",
        "project_document_id",
        "source_fingerprint",
        "decision_council_document_status",
        "decision_council_document_status_tone",
        "decision_council_document_status_copy",
        "decision_council_document_status_summary",
        "procurement_review_document_status",
        "procurement_review_document_status_tone",
        "procurement_review_document_status_copy",
        "procurement_review_document_status_summary",
    )

    def __init__(
        self,
        tenant_id: str,
        *,
        data_dir: str | Path | None = None,
        backend: StateBackend | None = None,
    ) -> None:
        self.tenant_id = require_tenant_id(tenant_id)
        resolved_data_dir = Path(data_dir or os.getenv("DATA_DIR", "./data"))
        self._relative_path = str(Path("tenants") / self.tenant_id / "shares.json")
        self._path = resolved_data_dir / self._relative_path
        self._backend = backend or get_state_backend(data_dir=resolved_data_dir)
        self._lock = _lock_for_path(self._path)

    def _get_path(self) -> Path:
        return self._path

    def _owns(self, link: dict[str, Any]) -> bool:
        stored_tenant_id = link.get("tenant_id")
        return stored_tenant_id is None or stored_tenant_id == self.tenant_id

    def _validate_record(
        self,
        stored_key: object,
        link: object,
    ) -> dict[str, Any]:
        if not isinstance(stored_key, str) or not stored_key:
            raise ShareStoreError("Invalid share identity")
        if not isinstance(link, dict):
            raise ShareStoreError("Invalid share record")

        stored_tenant_id = link.get("tenant_id")
        if stored_tenant_id is not None:
            if not isinstance(stored_tenant_id, str) or not stored_tenant_id:
                raise ShareStoreError("Invalid share identity")
            if stored_tenant_id != self.tenant_id:
                return link

        required_strings = (
            "share_id",
            "request_id",
            "title",
            "created_by",
            "created_at",
            "expires_at",
        )
        if any(not isinstance(link.get(field), str) for field in required_strings):
            raise ShareStoreError("Invalid share record")
        if any(not link[field] for field in ("share_id", "request_id", "created_by")):
            raise ShareStoreError("Invalid share identity")
        if link["share_id"] != stored_key:
            raise ShareStoreError("Invalid share identity")

        for field in self._optional_string_fields:
            if field in link and not isinstance(link[field], str):
                raise ShareStoreError("Invalid share record")

        access_count = link.get("access_count")
        if (
            isinstance(access_count, bool)
            or not isinstance(access_count, int)
            or access_count < 0
        ):
            raise ShareStoreError("Invalid share access count")
        if not isinstance(link.get("is_active"), bool):
            raise ShareStoreError("Invalid share lifecycle state")
        if link.get("revoked_at") and link["is_active"]:
            raise ShareStoreError("Invalid share lifecycle state")

        try:
            datetime.fromisoformat(link["created_at"])
            datetime.fromisoformat(link["expires_at"])
            for field in ("last_accessed_at", "revoked_at"):
                timestamp = link.get(field, "")
                if timestamp:
                    datetime.fromisoformat(timestamp)
        except ValueError as exc:
            raise ShareStoreError("Invalid share timestamp") from exc
        self._mutation_ids(link)
        return link

    def _validate_state(self, data: object) -> dict[str, dict[str, Any]]:
        if not isinstance(data, dict):
            raise ShareStoreError("Invalid share state document")

        share_ids: set[str] = set()
        for stored_key, link in data.items():
            self._validate_record(stored_key, link)
            if not self._owns(link):
                continue
            share_id = link["share_id"]
            if share_id in share_ids:
                raise ShareStoreError("Duplicate share identity")
            share_ids.add(share_id)
        return data

    def _read_state(self) -> tuple[str | None, dict[str, dict[str, Any]]]:
        try:
            raw = self._backend.read_text(self._relative_path)
        except (StateBackendError, UnicodeError) as exc:
            raise ShareStoreError("Invalid share state document") from exc
        if raw is None:
            return None, {}
        return raw, self._decode_state(raw)

    def _decode_state(self, raw: str) -> dict[str, dict[str, Any]]:
        if not raw.strip():
            raise ShareStoreError("Invalid share state document")
        try:
            data = json.loads(raw, object_pairs_hook=_unique_object)
        except (json.JSONDecodeError, ShareStoreError, ValueError) as exc:
            raise ShareStoreError("Invalid share state document") from exc
        return self._validate_state(data)

    def _load(self) -> dict[str, dict[str, Any]]:
        return self._read_state()[1]

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
            raise ShareStoreError("Invalid share mutation history")
        return list(mutation_ids)

    def _record_mutation(
        self,
        record: dict[str, Any],
        *,
        previous: dict[str, Any] | None,
        mutation_id: str,
    ) -> dict[str, Any]:
        mutation_ids = self._mutation_ids(previous or {})
        if mutation_id not in mutation_ids:
            mutation_ids.append(mutation_id)
        persisted = dict(record)
        persisted[_MUTATION_IDS_FIELD] = mutation_ids[-_MAX_TRACKED_MUTATIONS:]
        return persisted

    @staticmethod
    def _public_link(link: dict[str, Any]) -> dict[str, Any]:
        public_link = dict(link)
        public_link.pop(_MUTATION_IDS_FIELD, None)
        return public_link

    def _persist_if_current(
        self,
        *,
        expected: str | None,
        data: dict[str, dict[str, Any]],
        committed: Callable[[dict[str, dict[str, Any]]], bool],
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
                except ShareStoreError:
                    pass
                else:
                    if committed(observed_data):
                        return True
            raise ShareStoreError("Failed to persist share state") from exc

    def _mutate(
        self,
        change: Callable[
            [dict[str, dict[str, Any]]],
            tuple[_MutationResult, bool],
        ],
        *,
        committed: Callable[[dict[str, dict[str, Any]]], bool],
    ) -> _MutationResult:
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
        raise ShareStoreError(
            "Share state changed too many times to persist safely"
        )

    def create(
        self,
        request_id: str,
        title: str,
        created_by: str,
        bundle_id: str = "",
        project_id: str = "",
        project_document_id: str = "",
        source_fingerprint: str = "",
        expires_days: int = 7,
        decision_council_document_status: str = "",
        decision_council_document_status_tone: str = "",
        decision_council_document_status_copy: str = "",
        decision_council_document_status_summary: str = "",
        procurement_review_document_status: str = "",
        procurement_review_document_status_tone: str = "",
        procurement_review_document_status_copy: str = "",
        procurement_review_document_status_summary: str = "",
    ) -> ShareLink:
        if isinstance(expires_days, bool) or not isinstance(expires_days, int):
            raise ValueError("Invalid share expiry")

        created_at = datetime.now()
        link = ShareLink(
            share_id=secrets.token_urlsafe(16),
            tenant_id=self.tenant_id,
            request_id=request_id,
            title=title,
            created_by=created_by,
            created_at=created_at.isoformat(),
            expires_at=(created_at + timedelta(days=expires_days)).isoformat(),
            bundle_id=bundle_id,
            project_id=project_id,
            project_document_id=project_document_id,
            source_fingerprint=source_fingerprint,
            decision_council_document_status=decision_council_document_status,
            decision_council_document_status_tone=decision_council_document_status_tone,
            decision_council_document_status_copy=decision_council_document_status_copy,
            decision_council_document_status_summary=decision_council_document_status_summary,
            procurement_review_document_status=procurement_review_document_status,
            procurement_review_document_status_tone=procurement_review_document_status_tone,
            procurement_review_document_status_copy=procurement_review_document_status_copy,
            procurement_review_document_status_summary=procurement_review_document_status_summary,
        )
        try:
            record = self._validate_record(link.share_id, asdict(link))
        except ShareStoreError as exc:
            raise ValueError(str(exc)) from exc
        mutation_id = uuid.uuid4().hex
        persisted = self._record_mutation(
            record,
            previous=None,
            mutation_id=mutation_id,
        )

        def apply(data: dict[str, dict[str, Any]]) -> tuple[ShareLink, bool]:
            if link.share_id in data:
                raise ShareStoreError("Duplicate share identity")
            data[link.share_id] = persisted
            return link, True

        def was_committed(data: dict[str, dict[str, Any]]) -> bool:
            stored = data.get(link.share_id)
            return bool(
                stored
                and self._owns(stored)
                and mutation_id in self._mutation_ids(stored)
            )

        with self._lock:
            return self._mutate(apply, committed=was_committed)

    def get(self, share_id: str) -> dict[str, Any] | None:
        with self._lock:
            data = self._load()
        stored_link = data.get(share_id)
        if not stored_link or not self._owns(stored_link):
            return None

        link = self._public_link(stored_link)
        if link["is_active"] is False:
            link["lifecycle_status"] = (
                "revoked" if link.get("revoked_at") else "inactive"
            )
        elif _is_elapsed(link["expires_at"]):
            link["is_active"] = False
            link["lifecycle_status"] = "expired"
        else:
            link["lifecycle_status"] = "active"
        return link

    def increment_access(self, share_id: str) -> None:
        mutation_id = uuid.uuid4().hex

        def apply(data: dict[str, dict[str, Any]]) -> tuple[None, bool]:
            link = data.get(share_id)
            if not link or not self._owns(link):
                return None, False
            if mutation_id in self._mutation_ids(link):
                return None, False
            updated = dict(link)
            updated["access_count"] += 1
            updated["last_accessed_at"] = datetime.now().isoformat()
            data[share_id] = self._record_mutation(
                updated,
                previous=link,
                mutation_id=mutation_id,
            )
            return None, True

        def was_committed(data: dict[str, dict[str, Any]]) -> bool:
            link = data.get(share_id)
            return bool(
                link
                and self._owns(link)
                and mutation_id in self._mutation_ids(link)
            )

        with self._lock:
            self._mutate(apply, committed=was_committed)

    def revoke(
        self,
        share_id: str,
        user_id: str,
        *,
        allow_admin_override: bool = False,
        actor_name: str = "",
    ) -> bool:
        mutation_id = uuid.uuid4().hex
        revoked_at = datetime.now().isoformat()

        def apply(data: dict[str, dict[str, Any]]) -> tuple[bool, bool]:
            link = data.get(share_id)
            if not link or not self._owns(link):
                return False, False
            if link["created_by"] != user_id and not allow_admin_override:
                return False, False
            if not link["is_active"] and link.get("revoked_at"):
                return True, False
            updated = dict(link)
            updated["is_active"] = False
            if not link.get("revoked_at"):
                updated["revoked_at"] = revoked_at
                updated["revoked_by"] = user_id
                updated["revoked_by_username"] = actor_name or user_id
            data[share_id] = self._record_mutation(
                updated,
                previous=link,
                mutation_id=mutation_id,
            )
            return True, True

        def was_committed(data: dict[str, dict[str, Any]]) -> bool:
            link = data.get(share_id)
            return bool(
                link
                and self._owns(link)
                and mutation_id in self._mutation_ids(link)
            )

        with self._lock:
            return self._mutate(apply, committed=was_committed)

    def list_by_user(self, user_id: str) -> list[dict[str, Any]]:
        with self._lock:
            data = self._load()
        return [
            self._public_link(link)
            for link in data.values()
            if self._owns(link) and link["created_by"] == user_id
        ]
