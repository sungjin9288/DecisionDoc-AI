"""Tenant-scoped SSO configuration storage."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import threading
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

from app.storage.conditional_state import persist_text_if_current
from app.storage.state_backend import StateBackend, StateBackendError, get_state_backend
from app.tenant import require_tenant_id


class SSOProvider(str, Enum):
    DISABLED = "disabled"
    LDAP = "ldap"
    SAML = "saml"
    GCLOUD = "gcloud"
    OAUTH2 = "oauth2"


@dataclass
class LDAPConfig:
    server_url: str = ""
    bind_dn: str = ""
    bind_password: str = ""
    base_dn: str = ""
    user_search_filter: str = "(sAMAccountName={username})"
    group_search_base: str = ""
    admin_group: str = ""
    member_group: str = ""
    viewer_group: str = ""
    tls: bool = False


@dataclass
class SAMLConfig:
    idp_entity_id: str = ""
    idp_sso_url: str = ""
    idp_certificate: str = ""
    sp_entity_id: str = ""
    sp_acs_url: str = ""
    sp_private_key: str = ""
    sp_certificate: str = ""
    name_id_format: str = "urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress"
    attribute_username: str = "email"
    attribute_display_name: str = "displayName"
    attribute_role: str = "role"


@dataclass
class GCloudConfig:
    client_id: str = ""
    client_secret: str = ""
    hd: str = ""
    allowed_domains: list[str] = field(default_factory=list)
    default_role: str = "member"


@dataclass
class OAuth2Config:
    client_id: str = ""
    client_secret: str = ""
    auth_url: str = ""
    token_url: str = ""
    userinfo_url: str = ""
    scope: str = "openid email profile"
    redirect_uri: str = ""
    username_claim: str = "email"
    display_name_claim: str = "name"
    default_role: str = "member"


@dataclass
class SSOConfig:
    tenant_id: str
    provider: SSOProvider = SSOProvider.DISABLED
    ldap: LDAPConfig = field(default_factory=LDAPConfig)
    saml: SAMLConfig = field(default_factory=SAMLConfig)
    gcloud: GCloudConfig = field(default_factory=GCloudConfig)
    oauth2: OAuth2Config = field(default_factory=OAuth2Config)
    updated_at: str = ""


class SSOStoreError(RuntimeError):
    """Raised when persisted SSO configuration cannot be trusted."""


class SSOSecretError(RuntimeError):
    """Raised when an encrypted SSO secret cannot be decrypted."""


_sso_locks: dict[tuple[Any, ...], threading.RLock] = {}
_sso_locks_guard = threading.Lock()
_sso_stores: dict[tuple[Any, ...], "SSOStore"] = {}
_sso_stores_lock = threading.Lock()
_MUTATION_IDS_FIELD = "_mutation_ids"
_MAX_MUTATION_ATTEMPTS = 32
_MAX_TRACKED_MUTATIONS = 64


def _get_fernet_key() -> bytes:
    """Derive the Fernet key with PBKDF2 domain separation."""
    from app.config import get_sso_encryption_key

    base_key = get_sso_encryption_key().encode()
    salt = b"decisiondoc-sso-encryption-v1"
    derived = hashlib.pbkdf2_hmac(
        "sha256",
        base_key,
        salt,
        iterations=100_000,
        dklen=32,
    )
    return base64.urlsafe_b64encode(derived)


def encrypt_secret(plain: str) -> str:
    """Encrypt a non-empty secret with Fernet."""
    if not isinstance(plain, str):
        raise ValueError("SSO secret must be a string")
    if not plain:
        return ""
    from cryptography.fernet import Fernet

    return Fernet(_get_fernet_key()).encrypt(plain.encode()).decode()


def decrypt_secret(cipher: str) -> str:
    """Decrypt a Fernet token or fail closed without exposing the token."""
    if not isinstance(cipher, str):
        raise ValueError("Encrypted SSO secret must be a string")
    if not cipher:
        return ""
    try:
        from cryptography.fernet import Fernet, InvalidToken

        return Fernet(_get_fernet_key()).decrypt(cipher.encode()).decode()
    except (InvalidToken, UnicodeError, ValueError) as exc:
        raise SSOSecretError("Stored SSO secret cannot be decrypted") from exc


def _looks_encrypted(value: str) -> bool:
    if not value:
        return True
    try:
        decoded = base64.urlsafe_b64decode(value.encode())
    except (ValueError, TypeError):
        return False
    return len(decoded) >= 73 and decoded[0] == 0x80


def _config_to_dict(config: SSOConfig) -> dict[str, Any]:
    result = asdict(config)
    result["provider"] = config.provider.value
    return result


def _config_from_dict(tenant_id: str, data: dict[str, Any]) -> SSOConfig:
    return SSOConfig(
        tenant_id=tenant_id,
        provider=SSOProvider(data["provider"]),
        ldap=LDAPConfig(**data["ldap"]),
        saml=SAMLConfig(**data["saml"]),
        gcloud=GCloudConfig(**data["gcloud"]),
        oauth2=OAuth2Config(**data["oauth2"]),
        updated_at=data["updated_at"],
    )


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise SSOStoreError(f"Duplicate key in SSO state: {key!r}")
        result[key] = value
    return result


def _lock_for_state(
    backend: StateBackend,
    *,
    path: Path,
    relative_path: str,
) -> threading.RLock:
    if backend.kind == "local":
        backend_root = getattr(backend, "root", None)
        state_path = (
            Path(backend_root).resolve() / relative_path
            if backend_root is not None
            else path.resolve()
        )
        key: tuple[Any, ...] = ("local", state_path)
    elif backend.kind == "s3":
        key = (
            "s3",
            getattr(backend, "bucket", ""),
            getattr(backend, "prefix", ""),
            relative_path,
        )
    else:
        key = (backend.kind, id(backend), relative_path)
    with _sso_locks_guard:
        return _sso_locks.setdefault(key, threading.RLock())


def _backend_cache_key(
    backend: StateBackend,
    *,
    data_dir: Path,
    explicit_backend: bool,
) -> tuple[Any, ...]:
    if explicit_backend:
        return (backend.kind, id(backend))
    if backend.kind == "s3":
        return (
            "s3",
            getattr(backend, "bucket", ""),
            getattr(backend, "prefix", ""),
        )
    return ("local", data_dir.resolve())


class SSOStore:
    """Read and update one tenant's SSO configuration."""

    _TOP_LEVEL_FIELDS = {
        "tenant_id",
        "provider",
        "ldap",
        "saml",
        "gcloud",
        "oauth2",
        "updated_at",
    }
    _ROLES = {"admin", "member", "viewer"}

    def __init__(
        self,
        tenant_id: str,
        data_dir: str | Path | None = None,
        *,
        backend: StateBackend | None = None,
    ) -> None:
        self._tenant_id = require_tenant_id(tenant_id)
        self._data_dir = Path(data_dir or os.getenv("DATA_DIR", "data"))
        self._relative_path = str(Path("tenants") / self._tenant_id / "sso_config.json")
        self._path = self._data_dir / self._relative_path
        self._backend = backend or get_state_backend(data_dir=self._data_dir)
        self._lock = _lock_for_state(
            self._backend,
            path=self._path,
            relative_path=self._relative_path,
        )

    @staticmethod
    def _string_fields(
        value: object,
        config_type: type,
        *,
        non_string_fields: set[str] | None = None,
    ) -> dict[str, Any]:
        expected = set(config_type.__dataclass_fields__)
        if not isinstance(value, dict) or set(value) != expected:
            raise SSOStoreError(f"Invalid {config_type.__name__} fields")
        excluded = non_string_fields or set()
        if any(
            not isinstance(value[field_name], str) for field_name in expected - excluded
        ):
            raise SSOStoreError(f"Invalid {config_type.__name__} value")
        return value

    @staticmethod
    def _validate_secret(value: object, *, field_name: str) -> None:
        if not isinstance(value, str) or not _looks_encrypted(value):
            raise SSOStoreError(f"Invalid encrypted {field_name}")
        if value:
            try:
                decrypt_secret(value)
            except SSOSecretError as exc:
                raise SSOStoreError(f"Invalid encrypted {field_name}") from exc

    def _validate_owned(self, data: dict[str, Any], *, legacy: bool) -> None:
        expected_fields = self._TOP_LEVEL_FIELDS - ({"tenant_id"} if legacy else set())
        private_fields = set(data) - expected_fields
        if not expected_fields <= set(data) or private_fields not in (
            set(),
            {_MUTATION_IDS_FIELD},
        ):
            raise SSOStoreError("Invalid SSO configuration fields")
        self._mutation_ids(data)
        if not legacy and data.get("tenant_id") != self._tenant_id:
            raise SSOStoreError("SSO configuration tenant ownership mismatch")
        try:
            SSOProvider(data.get("provider"))
        except (TypeError, ValueError) as exc:
            raise SSOStoreError("Invalid SSO provider") from exc

        ldap = self._string_fields(
            data.get("ldap"),
            LDAPConfig,
            non_string_fields={"tls"},
        )
        if not isinstance(ldap["tls"], bool):
            raise SSOStoreError("Invalid LDAP TLS setting")
        self._validate_secret(ldap["bind_password"], field_name="LDAP password")

        saml = self._string_fields(data.get("saml"), SAMLConfig)
        self._validate_secret(saml["sp_private_key"], field_name="SAML private key")

        gcloud = self._string_fields(
            data.get("gcloud"),
            GCloudConfig,
            non_string_fields={"allowed_domains"},
        )
        if not isinstance(gcloud["allowed_domains"], list) or any(
            not isinstance(domain, str) or len(domain) > 253
            for domain in gcloud["allowed_domains"]
        ):
            raise SSOStoreError("Invalid GCloud allowed domains")
        if len(gcloud["allowed_domains"]) > 50:
            raise SSOStoreError("Invalid GCloud allowed domains")
        if gcloud["default_role"] not in self._ROLES:
            raise SSOStoreError("Invalid GCloud default role")
        self._validate_secret(
            gcloud["client_secret"], field_name="GCloud client secret"
        )

        oauth2 = self._string_fields(data.get("oauth2"), OAuth2Config)
        if oauth2["default_role"] not in self._ROLES:
            raise SSOStoreError("Invalid OAuth2 default role")
        self._validate_secret(
            oauth2["client_secret"], field_name="OAuth2 client secret"
        )

        updated_at = data.get("updated_at")
        if not isinstance(updated_at, str):
            raise SSOStoreError("Invalid SSO update timestamp")
        if updated_at:
            try:
                parsed = datetime.fromisoformat(updated_at)
            except ValueError as exc:
                raise SSOStoreError("Invalid SSO update timestamp") from exc
            if parsed.tzinfo is None or parsed.utcoffset() is None:
                raise SSOStoreError("Invalid SSO update timestamp")

    def _owns(self, data: dict[str, Any]) -> bool:
        stored_tenant_id = data.get("tenant_id")
        return stored_tenant_id is None or stored_tenant_id == self._tenant_id

    @staticmethod
    def _mutation_ids(data: dict[str, Any]) -> list[str]:
        mutation_ids = data.get(_MUTATION_IDS_FIELD, [])
        if (
            not isinstance(mutation_ids, list)
            or len(mutation_ids) > _MAX_TRACKED_MUTATIONS
            or any(
                not isinstance(mutation_id, str) or not mutation_id
                for mutation_id in mutation_ids
            )
            or len(mutation_ids) != len(set(mutation_ids))
        ):
            raise SSOStoreError("Invalid SSO mutation history")
        return list(mutation_ids)

    def _read_state(self) -> tuple[str | None, dict[str, Any] | None]:
        try:
            raw = self._backend.read_text(self._relative_path)
        except (StateBackendError, UnicodeError) as exc:
            raise SSOStoreError("Invalid SSO state document") from exc
        if raw is None:
            return None, None
        if not raw.strip():
            raise SSOStoreError("Invalid SSO state document")
        try:
            data = json.loads(raw, object_pairs_hook=_unique_object)
        except (json.JSONDecodeError, TypeError, SSOStoreError) as exc:
            raise SSOStoreError("Invalid SSO state document") from exc
        if not isinstance(data, dict):
            raise SSOStoreError("Invalid SSO state document")

        stored_tenant_id = data.get("tenant_id")
        if stored_tenant_id is not None:
            if not isinstance(stored_tenant_id, str) or not stored_tenant_id:
                raise SSOStoreError("Invalid SSO tenant identity")
            if stored_tenant_id != self._tenant_id:
                return raw, data
        self._validate_owned(data, legacy=stored_tenant_id is None)
        return raw, data

    def _load(self) -> dict[str, Any] | None:
        return self._read_state()[1]

    def _validated_for_save(self, config: SSOConfig) -> dict[str, Any]:
        if config.tenant_id != self._tenant_id:
            raise ValueError("SSO config tenant does not match store tenant")
        if not isinstance(config.provider, SSOProvider):
            raise ValueError("Invalid SSO provider")
        data = _config_to_dict(config)
        try:
            self._validate_owned(data, legacy=False)
        except SSOStoreError as exc:
            raise ValueError(str(exc)) from exc
        return data

    def _persist_if_current(
        self,
        *,
        expected: str | None,
        data: dict[str, Any],
        mutation_id: str,
    ) -> bool:
        self._validate_owned(data, legacy=False)
        payload = json.dumps(data, ensure_ascii=False, indent=2)

        def decode(raw: str) -> dict[str, Any]:
            if not raw.strip():
                raise SSOStoreError("Invalid SSO state document")
            try:
                observed = json.loads(raw, object_pairs_hook=_unique_object)
            except (json.JSONDecodeError, TypeError, SSOStoreError) as exc:
                raise SSOStoreError("Invalid SSO state document") from exc
            if not isinstance(observed, dict):
                raise SSOStoreError("Invalid SSO state document")
            stored_tenant_id = observed.get("tenant_id")
            if stored_tenant_id != self._tenant_id:
                raise SSOStoreError("SSO configuration tenant ownership mismatch")
            self._validate_owned(observed, legacy=False)
            return observed

        try:
            return persist_text_if_current(
                backend=self._backend,
                relative_path=self._relative_path,
                expected=expected,
                replacement=payload,
                decode=decode,
                committed=lambda observed: mutation_id in self._mutation_ids(observed),
                decode_errors=(SSOStoreError,),
            )
        except StateBackendError as exc:
            raise SSOStoreError("Failed to persist SSO state") from exc

    def _mutate(
        self,
        *,
        change: Callable[[SSOConfig], None] | None = None,
        replacement: SSOConfig | None = None,
    ) -> SSOConfig:
        mutation_id = secrets.token_hex(16)
        for _ in range(_MAX_MUTATION_ATTEMPTS):
            expected, existing = self._read_state()
            if existing is not None and not self._owns(existing):
                raise SSOStoreError("Foreign SSO configuration must be preserved")

            config = (
                replacement
                if replacement is not None
                else (
                    SSOConfig(tenant_id=self._tenant_id)
                    if existing is None
                    else _config_from_dict(self._tenant_id, existing)
                )
            )
            if change is not None:
                change(config)
            data = self._validated_for_save(config)
            mutation_ids = self._mutation_ids(existing or {})
            mutation_ids.append(mutation_id)
            data[_MUTATION_IDS_FIELD] = mutation_ids[-_MAX_TRACKED_MUTATIONS:]
            if self._persist_if_current(
                expected=expected,
                data=data,
                mutation_id=mutation_id,
            ):
                return config
        raise SSOStoreError("SSO state changed too many times to persist safely")

    def get(self) -> SSOConfig:
        """Return the current config or a side-effect-free disabled default."""
        with self._lock:
            data = self._load()
        if data is None or not self._owns(data):
            return SSOConfig(tenant_id=self._tenant_id)
        return _config_from_dict(self._tenant_id, data)

    def save(self, config: SSOConfig) -> None:
        """Validate and atomically replace the owned SSO configuration."""
        self._validated_for_save(config)
        with self._lock:
            self._mutate(replacement=config)

    def update(self, change: Callable[[SSOConfig], None]) -> SSOConfig:
        """Apply a partial change without exposing a read-modify-write race."""
        with self._lock:
            return self._mutate(change=change)

    def is_sso_enabled(self) -> bool:
        return self.get().provider != SSOProvider.DISABLED

    def encrypt_secret(self, plain: str) -> str:
        return encrypt_secret(plain)

    def decrypt_secret(self, cipher: str) -> str:
        return decrypt_secret(cipher)


def get_sso_store(
    tenant_id: str,
    data_dir: str | Path | None = None,
    *,
    backend: StateBackend | None = None,
) -> SSOStore:
    """Return a cached store for one tenant and one state backend."""
    tenant_id = require_tenant_id(tenant_id)
    root = Path(data_dir or os.getenv("DATA_DIR", "data"))
    explicit_backend = backend is not None
    selected_backend = backend or get_state_backend(data_dir=root)
    key = (
        tenant_id,
        root.resolve(),
        *_backend_cache_key(
            selected_backend,
            data_dir=root,
            explicit_backend=explicit_backend,
        ),
    )
    with _sso_stores_lock:
        store = _sso_stores.get(key)
        if store is None:
            store = SSOStore(
                tenant_id,
                data_dir=root,
                backend=selected_backend,
            )
            _sso_stores[key] = store
        return store
