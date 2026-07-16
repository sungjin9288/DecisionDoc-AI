"""app/storage/user_store.py — Tenant-scoped user account storage.

Storage: data/tenants/{tenant_id}/users.json
Thread-safe within one process across stores that share a data root.
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
from typing import Any

import bcrypt

from app.ai_profiles.catalog import (
    default_ai_profiles_for_role,
    normalize_ai_profile_keys,
)
from app.storage.state_backend import StateBackend, get_state_backend
from app.tenant import require_tenant_id


_user_locks: dict[Path, threading.RLock] = {}
_user_locks_guard = threading.Lock()


class UserStoreError(ValueError):
    """Raised when persisted user state cannot be trusted."""


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
        profiles = record.get("assigned_ai_profiles", [])
        if not isinstance(profiles, list) or any(
            not isinstance(profile, str) for profile in profiles
        ):
            raise UserStoreError("Invalid user AI profiles")

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

    def _load(self) -> dict[str, dict]:
        raw = self._backend.read_text(self._relative_path)
        if raw is None:
            return {}
        if not raw.strip():
            raise UserStoreError("Invalid user state document")
        try:
            data = json.loads(raw, object_pairs_hook=_unique_object)
        except (json.JSONDecodeError, ValueError) as exc:
            raise UserStoreError("Invalid user state document") from exc
        return self._validate_state(data)

    def _save(self, data: dict[str, dict]) -> None:
        self._validate_state(data)
        self._backend.write_text(
            self._relative_path,
            json.dumps(data, ensure_ascii=False, indent=2),
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
        if (
            not isinstance(username, str)
            or not username
            or not isinstance(display_name, str)
            or not isinstance(email, str)
            or not isinstance(job_title, str)
        ):
            raise UserStoreError("Invalid user record")
        if assigned_ai_profiles is not None and (
            not isinstance(assigned_ai_profiles, list)
            or any(not isinstance(profile, str) for profile in assigned_ai_profiles)
        ):
            raise UserStoreError("Invalid user AI profiles")
        _validate_password(password)
        if isinstance(role, str):
            role = UserRole(role)
        normalized_profiles = (
            default_ai_profiles_for_role(role.value)
            if assigned_ai_profiles is None
            else normalize_ai_profile_keys(assigned_ai_profiles)
        )
        with self._lock:
            data = self._load()
            for u in data.values():
                if self._owns(u) and u["username"] == username:
                    raise ValueError(f"사용자 이름 '{username}'이(가) 이미 존재합니다.")
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
                job_title=(job_title or "").strip(),
                assigned_ai_profiles=normalized_profiles,
            )
            self._validate_record(user_id, asdict(user))
            data[user_id] = asdict(user)
            self._save(data)
            return user

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
        with self._lock:
            data = self._load()
            rec = data.get(user_id)
            if not self._owns(rec):
                raise ValueError(f"사용자를 찾을 수 없습니다: {user_id}")
            for k, v in kwargs.items():
                if v is None:
                    continue
                if k == "role":
                    rec["role"] = UserRole(v).value if isinstance(v, str) else UserRole(v).value
                elif k == "assigned_ai_profiles":
                    rec["assigned_ai_profiles"] = normalize_ai_profile_keys(v)
                elif k == "job_title":
                    rec["job_title"] = str(v or "").strip()
                else:
                    rec[k] = v
            data[user_id] = rec
            self._save(data)
            return self._to_user(rec)

    def change_password(self, user_id: str, old_password: str, new_password: str) -> bool:
        """Returns False if old_password is wrong; raises ValueError if new_password weak."""
        with self._lock:
            data = self._load()
            rec = data.get(user_id)
            if not self._owns(rec) or not _check_password(old_password, rec["password_hash"]):
                return False
            _validate_password(new_password)
            rec["password_hash"] = _hash_password(new_password)
            data[user_id] = rec
            self._save(data)
        return True

    def deactivate(self, user_id: str) -> None:
        self.update(user_id, is_active=False)

    def update_last_login(self, user_id: str) -> None:
        with self._lock:
            data = self._load()
            if self._owns(data.get(user_id)):
                data[user_id]["last_login"] = _now_iso()
                self._save(data)

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
