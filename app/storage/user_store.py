"""app/storage/user_store.py — Tenant-scoped user account storage.

Storage: data/tenants/{tenant_id}/users.json
Process-local locks reduce contention; backend CAS preserves worker-safe updates.
"""
from __future__ import annotations

import json
import os
import threading
import uuid
from dataclasses import asdict, dataclass, field as dc_field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable, TypeVar

import bcrypt

from app.ai_profiles.catalog import (
    default_ai_profiles_for_role,
    normalize_ai_profile_keys,
)
from app.storage.state_backend import StateBackend, StateBackendError, get_state_backend
from app.tenant import require_tenant_id


_user_locks: dict[Path, threading.RLock] = {}
_user_locks_guard = threading.Lock()
_MAX_MUTATION_ATTEMPTS = 32
_MUTATION_IDS_FIELD = "_mutation_ids"
_MAX_TRACKED_MUTATIONS = 64
_MutationResult = TypeVar("_MutationResult")


class UserStoreError(RuntimeError):
    """Raised when persisted user state cannot be trusted."""


class UserStoreAlreadyInitialized(ValueError):
    """Raised when a tenant already has its first user."""


def _lock_for_path(path: Path) -> threading.RLock:
    with _user_locks_guard:
        return _user_locks.setdefault(path.resolve(), threading.RLock())


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise UserStoreError(f"Duplicate key in user state: {key!r}")
        result[key] = value
    return result


class UserRole(str, Enum):
    ADMIN = "admin"    # 전체 관리, 사용자 초대/삭제
    MEMBER = "member"  # 문서 생성/결재 참여
    VIEWER = "viewer"  # 읽기 전용


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


_AVATAR_COLORS = [
    "#6366f1", "#ec4899", "#f59e0b", "#10b981", "#3b82f6",
    "#8b5cf6", "#ef4444", "#14b8a6", "#f97316", "#06b6d4",
]


def _pick_avatar_color(username: str) -> str:
    idx = sum(ord(c) for c in username) % len(_AVATAR_COLORS)
    return _AVATAR_COLORS[idx]


@dataclass
class User:
    user_id: str
    tenant_id: str
    username: str          # 로그인 ID (unique per tenant)
    display_name: str      # 화면 표시 이름
    email: str
    password_hash: str     # bcrypt hash — never returned to clients
    role: UserRole
    is_active: bool
    created_at: str
    last_login: str | None
    avatar_color: str      # hex color for avatar placeholder
    credential_version: int = 0
    job_title: str = ""
    assigned_ai_profiles: list[str] = dc_field(default_factory=list)


def _hash_password(password: str) -> str:
    """Hash a plain-text password with bcrypt rounds=12."""
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=12)).decode()


def _check_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode(), hashed.encode())
    except Exception:
        return False


def _validate_password(password: str) -> None:
    if not isinstance(password, str):
        raise ValueError("비밀번호는 문자열이어야 합니다.")
    if len(password) < 8:
        raise ValueError("비밀번호는 최소 8자 이상이어야 합니다.")
    if not any(c.isdigit() for c in password):
        raise ValueError("비밀번호에 숫자가 포함되어야 합니다.")
    if not any(c.isalpha() for c in password):
        raise ValueError("비밀번호에 문자가 포함되어야 합니다.")


class UserStore:
    """Thread-safe user state scoped to a single tenant."""

    def __init__(self, tenant_dir: Path, *, backend: StateBackend | None = None) -> None:
        self._tenant_dir = Path(tenant_dir)
        self._tenant_id = require_tenant_id(self._tenant_dir.name)
        self._path = self._tenant_dir / "users.json"
        if self._tenant_dir.parent.name == "tenants":
            data_dir = self._tenant_dir.parent.parent
        else:
            data_dir = self._tenant_dir.parent
        self._relative_path = self._path.relative_to(data_dir).as_posix()
        self._backend = backend or get_state_backend(data_dir=data_dir)
        self._lock = _lock_for_path(self._path)

    def _validate_record(self, user_id: str, record: object) -> None:
        if not isinstance(record, dict):
            raise UserStoreError("Invalid user record")
        stored_tenant_id = record.get("tenant_id")
        if not isinstance(stored_tenant_id, str) or not stored_tenant_id:
            raise UserStoreError("Invalid user identity")
        if stored_tenant_id != self._tenant_id:
            return

        required_strings = (
            "user_id",
            "tenant_id",
            "username",
            "display_name",
            "email",
            "password_hash",
            "created_at",
            "avatar_color",
        )
        if any(not isinstance(record.get(field), str) for field in required_strings):
            raise UserStoreError("Invalid user record")
        if (
            not user_id
            or record["user_id"] != user_id
            or not record["username"]
            or not record["password_hash"]
            or not record["created_at"]
        ):
            raise UserStoreError("Invalid user identity")
        try:
            UserRole(record.get("role"))
        except ValueError as exc:
            raise UserStoreError("Invalid user role") from exc
        if not isinstance(record.get("is_active"), bool):
            raise UserStoreError("Invalid user active state")
        last_login = record.get("last_login")
        if last_login is not None and not isinstance(last_login, str):
            raise UserStoreError("Invalid user login timestamp")
        try:
            datetime.fromisoformat(record["created_at"])
            if last_login is not None:
                datetime.fromisoformat(last_login)
        except ValueError as exc:
            raise UserStoreError("Invalid user timestamp") from exc
        job_title = record.get("job_title", "")
        if not isinstance(job_title, str):
            raise UserStoreError("Invalid user job title")
        credential_version = record.get("credential_version", 0)
        if type(credential_version) is not int or credential_version < 0:
            raise UserStoreError("Invalid user credential version")
        profiles = record.get("assigned_ai_profiles", [])
        if not isinstance(profiles, list) or any(
            not isinstance(profile, str) for profile in profiles
        ):
            raise UserStoreError("Invalid user AI profiles")
        self._mutation_ids(record)

    def _validate_state(self, data: object) -> dict[str, dict]:
        if not isinstance(data, dict):
            raise UserStoreError("Invalid user state document")

        usernames: set[str] = set()
        for user_id, record in data.items():
            if not isinstance(user_id, str) or not isinstance(record, dict):
                raise UserStoreError("Invalid user record")
            self._validate_record(user_id, record)
            if record.get("tenant_id") != self._tenant_id:
                continue
            username = record["username"]
            if username in usernames:
                raise UserStoreError("Duplicate username in user state")
            usernames.add(username)
        return data

    def _read_state(self) -> tuple[str | None, dict[str, dict]]:
        try:
            raw = self._backend.read_text(self._relative_path)
        except (StateBackendError, UnicodeError) as exc:
            raise UserStoreError("Invalid user state document") from exc
        if raw is None:
            return None, {}
        return raw, self._decode_state(raw)

    def _decode_state(self, raw: str) -> dict[str, dict]:
        if not raw.strip():
            raise UserStoreError("Invalid user state document")
        try:
            data = json.loads(raw, object_pairs_hook=_unique_object)
        except (json.JSONDecodeError, UserStoreError, ValueError) as exc:
            raise UserStoreError("Invalid user state document") from exc
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
            raise UserStoreError("Invalid user mutation history")
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
                except UserStoreError:
                    pass
                else:
                    if committed(observed_data):
                        return True
            raise UserStoreError("Failed to persist user state") from exc

    def _mutate(
        self,
        change: Callable[
            [dict[str, dict]],
            tuple[_MutationResult, bool],
        ],
        *,
        committed: Callable[[dict[str, dict]], bool],
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
        raise UserStoreError(
            "User state changed too many times to persist safely"
        )

    # ── internal helpers ──────────────────────────────────────────────────

    def _to_user(self, d: dict) -> User:
        return User(
            user_id=d["user_id"],
            tenant_id=d["tenant_id"],
            username=d["username"],
            display_name=d["display_name"],
            email=d["email"],
            password_hash=d["password_hash"],
            role=UserRole(d["role"]),
            is_active=d["is_active"],
            created_at=d["created_at"],
            last_login=d.get("last_login"),
            avatar_color=d["avatar_color"],
            credential_version=d.get("credential_version", 0),
            job_title=d.get("job_title", ""),
            assigned_ai_profiles=d.get("assigned_ai_profiles", []),
        )

    def _owns(self, record: dict | None) -> bool:
        return bool(record and record.get("tenant_id") == self._tenant_id)

    # ── public API ────────────────────────────────────────────────────────

    def create(
        self,
        username: str,
        display_name: str,
        email: str,
        password: str,
        role: UserRole | str = UserRole.MEMBER,
        job_title: str = "",
        assigned_ai_profiles: list[str] | None = None,
    ) -> User:
        """Create a new user. Raises ValueError if username already exists."""
        return self._create(
            username=username,
            display_name=display_name,
            email=email,
            password=password,
            role=role,
            job_title=job_title,
            assigned_ai_profiles=assigned_ai_profiles,
            require_empty=False,
        )

    def create_first_admin(
        self,
        username: str,
        display_name: str,
        email: str,
        password: str,
    ) -> User:
        """Atomically create the first tenant user as an administrator."""
        return self._create(
            username=username,
            display_name=display_name,
            email=email,
            password=password,
            role=UserRole.ADMIN,
            job_title="",
            assigned_ai_profiles=None,
            require_empty=True,
        )

    def _create(
        self,
        *,
        username: str,
        display_name: str,
        email: str,
        password: str,
        role: UserRole | str,
        job_title: str,
        assigned_ai_profiles: list[str] | None,
        require_empty: bool,
    ) -> User:
        if (
            not isinstance(username, str)
            or not username
            or not isinstance(display_name, str)
            or not isinstance(email, str)
            or not isinstance(job_title, str)
        ):
            raise ValueError("Invalid user record")
        if assigned_ai_profiles is not None and (
            not isinstance(assigned_ai_profiles, list)
            or any(not isinstance(profile, str) for profile in assigned_ai_profiles)
        ):
            raise ValueError("Invalid user AI profiles")
        _validate_password(password)
        if isinstance(role, str):
            role = UserRole(role)
        normalized_profiles = (
            default_ai_profiles_for_role(role.value)
            if assigned_ai_profiles is None
            else normalize_ai_profile_keys(assigned_ai_profiles)
        )
        mutation_id = uuid.uuid4().hex
        user: User | None = None

        def apply(data: dict[str, dict]) -> tuple[User, bool]:
            nonlocal user
            if require_empty and any(
                self._owns(record) for record in data.values()
            ):
                raise UserStoreAlreadyInitialized(
                    "이미 사용자가 존재합니다. 관리자에게 초대를 요청하세요."
                )
            for record in data.values():
                if self._owns(record) and record["username"] == username:
                    raise ValueError(
                        f"사용자 이름 '{username}'이(가) 이미 존재합니다."
                    )
            if user is None:
                user_id = str(uuid.uuid4())
                user = User(
                    user_id=user_id,
                    tenant_id=self._tenant_id,
                    username=username,
                    display_name=display_name,
                    email=email,
                    password_hash=_hash_password(password),
                    role=role,
                    is_active=True,
                    created_at=_now_iso(),
                    last_login=None,
                    avatar_color=_pick_avatar_color(username),
                    credential_version=0,
                    job_title=(job_title or "").strip(),
                    assigned_ai_profiles=normalized_profiles,
                )
                self._validate_record(user_id, asdict(user))
            data[user.user_id] = self._record_mutation(
                asdict(user),
                previous=None,
                mutation_id=mutation_id,
            )
            return user, True

        def was_committed(data: dict[str, dict]) -> bool:
            if user is None:
                return False
            record = data.get(user.user_id)
            return bool(
                self._owns(record)
                and mutation_id in self._mutation_ids(record)
            )

        with self._lock:
            return self._mutate(apply, committed=was_committed)

    def get_by_id(self, user_id: str) -> User | None:
        with self._lock:
            data = self._load()
        rec = data.get(user_id)
        return self._to_user(rec) if self._owns(rec) else None

    def get_by_username(self, username: str) -> User | None:
        with self._lock:
            data = self._load()
        for u in data.values():
            if self._owns(u) and u["username"] == username:
                return self._to_user(u)
        return None

    def verify_password(self, user_id: str, password: str) -> bool:
        with self._lock:
            data = self._load()
        rec = data.get(user_id)
        if not self._owns(rec):
            return False
        return _check_password(password, rec["password_hash"])

    def list_users(self, role: UserRole | str | None = None) -> list[User]:
        with self._lock:
            data = self._load()
        users = [self._to_user(u) for u in data.values() if self._owns(u)]
        if role is not None:
            role_val = UserRole(role) if isinstance(role, str) else role
            users = [u for u in users if u.role == role_val]
        return sorted(users, key=lambda u: u.created_at)

    def update(self, user_id: str, **kwargs) -> User:
        """Update allowed fields: display_name, email, role, is_active."""
        allowed = {
            "display_name",
            "email",
            "role",
            "is_active",
            "job_title",
            "assigned_ai_profiles",
        }
        unknown = set(kwargs) - allowed
        if unknown:
            raise ValueError(f"수정 불가 필드: {unknown}")
        updates: dict[str, Any] = {}
        for key, value in kwargs.items():
            if value is None:
                continue
            if key == "role":
                updates[key] = UserRole(value).value
            elif key == "assigned_ai_profiles":
                updates[key] = normalize_ai_profile_keys(value)
            elif key == "job_title":
                updates[key] = str(value or "").strip()
            else:
                updates[key] = value
        mutation_id = uuid.uuid4().hex

        def apply(data: dict[str, dict]) -> tuple[User, bool]:
            record = data.get(user_id)
            if not self._owns(record):
                raise ValueError(f"사용자를 찾을 수 없습니다: {user_id}")
            if not updates:
                return self._to_user(record), False
            updated = dict(record)
            updated.update(updates)
            data[user_id] = self._record_mutation(
                updated,
                previous=record,
                mutation_id=mutation_id,
            )
            return self._to_user(data[user_id]), True

        def was_committed(data: dict[str, dict]) -> bool:
            record = data.get(user_id)
            return bool(
                self._owns(record)
                and mutation_id in self._mutation_ids(record)
            )

        with self._lock:
            return self._mutate(apply, committed=was_committed)

    def change_password(self, user_id: str, old_password: str, new_password: str) -> bool:
        """Returns False if old_password is wrong; raises ValueError if new_password weak."""
        mutation_id = uuid.uuid4().hex
        new_password_hash: str | None = None

        def apply(data: dict[str, dict]) -> tuple[bool, bool]:
            nonlocal new_password_hash
            record = data.get(user_id)
            if not self._owns(record) or not _check_password(
                old_password,
                record["password_hash"],
            ):
                return False, False
            if new_password_hash is None:
                _validate_password(new_password)
                new_password_hash = _hash_password(new_password)
            updated = dict(record)
            updated["password_hash"] = new_password_hash
            updated["credential_version"] = record.get("credential_version", 0) + 1
            data[user_id] = self._record_mutation(
                updated,
                previous=record,
                mutation_id=mutation_id,
            )
            return True, True

        def was_committed(data: dict[str, dict]) -> bool:
            record = data.get(user_id)
            return bool(
                self._owns(record)
                and mutation_id in self._mutation_ids(record)
            )

        with self._lock:
            return self._mutate(apply, committed=was_committed)

    def deactivate(self, user_id: str) -> None:
        self.update(user_id, is_active=False)

    def update_last_login(self, user_id: str) -> None:
        mutation_id = uuid.uuid4().hex
        last_login = _now_iso()

        def apply(data: dict[str, dict]) -> tuple[None, bool]:
            record = data.get(user_id)
            if not self._owns(record):
                return None, False
            updated = dict(record)
            updated["last_login"] = last_login
            data[user_id] = self._record_mutation(
                updated,
                previous=record,
                mutation_id=mutation_id,
            )
            return None, True

        def was_committed(data: dict[str, dict]) -> bool:
            record = data.get(user_id)
            return bool(
                self._owns(record)
                and mutation_id in self._mutation_ids(record)
            )

        with self._lock:
            self._mutate(apply, committed=was_committed)

    def has_any_users(self) -> bool:
        """Return True when the tenant has at least one registered user.

        Corrupted state fails closed instead of looking like an empty tenant.
        """
        with self._lock:
            data = self._load()
        return any(self._owns(record) for record in data.values())


# ── per-tenant factory ─────────────────────────────────────────────────────────

_user_stores: dict[tuple[str, str, str, str, str], UserStore] = {}
_us_lock = threading.Lock()


def get_user_store(
    tenant_id: str,
    *,
    data_dir: str | Path | None = None,
    backend: StateBackend | None = None,
) -> UserStore:
    """Return a shared UserStore instance for the given tenant."""
    tenant_id = require_tenant_id(tenant_id)
    resolved_data_dir = Path(
        data_dir or os.getenv("DATA_DIR", "./data")
    ).resolve()
    tenant_dir = resolved_data_dir / "tenants" / tenant_id
    if backend is not None:
        return UserStore(tenant_dir, backend=backend)

    state_backend = get_state_backend(data_dir=resolved_data_dir)
    storage_kind = os.getenv("DECISIONDOC_STATE_STORAGE") or os.getenv(
        "DECISIONDOC_STORAGE", "local"
    )
    bucket = os.getenv("DECISIONDOC_STATE_S3_BUCKET") or os.getenv(
        "DECISIONDOC_S3_BUCKET", ""
    )
    prefix = os.getenv("DECISIONDOC_STATE_S3_PREFIX") or os.getenv(
        "DECISIONDOC_S3_PREFIX", ""
    )
    cache_key = (tenant_id, str(resolved_data_dir), storage_kind, bucket, prefix)
    with _us_lock:
        if cache_key not in _user_stores:
            _user_stores[cache_key] = UserStore(tenant_dir, backend=state_backend)
        return _user_stores[cache_key]
