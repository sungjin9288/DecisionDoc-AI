"""app/storage/user_store.py — Tenant-scoped user account storage.

Storage: data/tenants/{tenant_id}/users.json
Thread-safe via threading.Lock per store instance.
"""
from __future__ import annotations

import threading
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path

import bcrypt

from app.storage.base import BaseJsonStore


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


def _hash_password(password: str) -> str:
    """Hash a plain-text password with bcrypt rounds=12."""
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=12)).decode()


def _check_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode(), hashed.encode())
    except Exception:
        return False


def _validate_password(password: str) -> None:
    if len(password) < 8:
        raise ValueError("비밀번호는 최소 8자 이상이어야 합니다.")
    if not any(c.isdigit() for c in password):
        raise ValueError("비밀번호에 숫자가 포함되어야 합니다.")
    if not any(c.isalpha() for c in password):
        raise ValueError("비밀번호에 문자가 포함되어야 합니다.")


class UserStore(BaseJsonStore):
    """Thread-safe, file-backed user store scoped to a single tenant."""

    def __init__(self, tenant_dir: Path) -> None:
        super().__init__()
        self._path = tenant_dir / "users.json"
        tenant_dir.mkdir(parents=True, exist_ok=True)
        if not self._path.exists():
            self._save({})

    def _get_path(self) -> Path:
        return self._path

    # ── internal helpers ──────────────────────────────────────────────────

    def _to_user(self, d: dict) -> User:
        d = dict(d)
        d["role"] = UserRole(d["role"])
        return User(**d)

    # ── public API ────────────────────────────────────────────────────────

    def create(
        self,
        tenant_id: str,
        username: str,
        display_name: str,
        email: str,
        password: str,
        role: UserRole | str = UserRole.MEMBER,
    ) -> User:
        """Create a new user. Raises ValueError if username already exists."""
        _validate_password(password)
        if isinstance(role, str):
            role = UserRole(role)
        with self._lock:
            data = self._load()
            # Check uniqueness within tenant
            for u in data.values():
                if u["tenant_id"] == tenant_id and u["username"] == username:
                    raise ValueError(f"사용자 이름 '{username}'이(가) 이미 존재합니다.")
            user_id = str(uuid.uuid4())
            user = User(
                user_id=user_id,
                tenant_id=tenant_id,
                username=username,
                display_name=display_name,
                email=email,
                password_hash=_hash_password(password),
                role=role,
                is_active=True,
                created_at=_now_iso(),
                last_login=None,
                avatar_color=_pick_avatar_color(username),
            )
            data[user_id] = asdict(user)
            self._save(data)
            return user

    def get_by_id(self, user_id: str) -> User | None:
        with self._lock:
            data = self._load()
        rec = data.get(user_id)
        return self._to_user(rec) if rec else None

    def get_by_username(self, tenant_id: str, username: str) -> User | None:
        with self._lock:
            data = self._load()
        for u in data.values():
            if u["tenant_id"] == tenant_id and u["username"] == username:
                return self._to_user(u)
        return None

    def verify_password(self, user_id: str, password: str) -> bool:
        with self._lock:
            data = self._load()
        rec = data.get(user_id)
        if not rec:
            return False
        return _check_password(password, rec["password_hash"])

    def list_by_tenant(self, tenant_id: str, role: UserRole | str | None = None) -> list[User]:
        with self._lock:
            data = self._load()
        users = [
            self._to_user(u) for u in data.values()
            if u["tenant_id"] == tenant_id
        ]
        if role is not None:
            role_val = UserRole(role) if isinstance(role, str) else role
            users = [u for u in users if u.role == role_val]
        return sorted(users, key=lambda u: u.created_at)

    def update(self, user_id: str, **kwargs) -> User:
        """Update allowed fields: display_name, email, role, is_active."""
        allowed = {"display_name", "email", "role", "is_active"}
        unknown = set(kwargs) - allowed
        if unknown:
            raise ValueError(f"수정 불가 필드: {unknown}")
        with self._lock:
            data = self._load()
            rec = data.get(user_id)
            if not rec:
                raise ValueError(f"사용자를 찾을 수 없습니다: {user_id}")
            for k, v in kwargs.items():
                if v is None:
                    continue
                if k == "role":
                    rec["role"] = UserRole(v).value if isinstance(v, str) else UserRole(v).value
                else:
                    rec[k] = v
            data[user_id] = rec
            self._save(data)
            return self._to_user(rec)

    def change_password(self, user_id: str, old_password: str, new_password: str) -> bool:
        """Returns False if old_password is wrong; raises ValueError if new_password weak."""
        if not self.verify_password(user_id, old_password):
            return False
        _validate_password(new_password)
        with self._lock:
            data = self._load()
            rec = data.get(user_id)
            if not rec:
                return False
            rec["password_hash"] = _hash_password(new_password)
            data[user_id] = rec
            self._save(data)
        return True

    def deactivate(self, user_id: str) -> None:
        self.update(user_id, is_active=False)

    def update_last_login(self, user_id: str) -> None:
        with self._lock:
            data = self._load()
            if user_id in data:
                data[user_id]["last_login"] = _now_iso()
                self._save(data)


# ── per-tenant factory ─────────────────────────────────────────────────────────

_user_stores: dict[str, UserStore] = {}
_us_lock = threading.Lock()


def get_user_store(tenant_id: str) -> UserStore:
    """Return a shared UserStore instance for the given tenant."""
    with _us_lock:
        if tenant_id not in _user_stores:
            data_dir = Path(__import__("os").getenv("DATA_DIR", "./data"))
            tenant_dir = data_dir / "tenants" / tenant_id
            _user_stores[tenant_id] = UserStore(tenant_dir)
        return _user_stores[tenant_id]
