"""app/storage/sso_store.py — SSO configuration storage for LDAP/SAML/GCloud/OAuth2.

Storage: data/tenants/{tenant_id}/sso_config.json
Secrets (passwords, private keys) are encrypted at rest with AES-256 (Fernet).
"""
from __future__ import annotations

import base64
import hashlib
import os
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from app.storage.base import BaseJsonStore, atomic_write_text


class SSOProvider(str, Enum):
    DISABLED = "disabled"
    LDAP     = "ldap"
    SAML     = "saml"
    GCLOUD   = "gcloud"
    OAUTH2   = "oauth2"


@dataclass
class LDAPConfig:
    server_url: str = ""          # ldap://host:389
    bind_dn: str = ""             # CN=svc,DC=corp,DC=local
    bind_password: str = ""       # encrypted at rest
    base_dn: str = ""             # DC=corp,DC=local
    user_search_filter: str = "(sAMAccountName={username})"
    group_search_base: str = ""
    admin_group: str = ""         # CN=DecisionDocAdmin,OU=Groups,...
    member_group: str = ""        # CN=DecisionDocMember,...
    viewer_group: str = ""
    tls: bool = False


@dataclass
class SAMLConfig:
    idp_entity_id: str = ""
    idp_sso_url: str = ""
    idp_certificate: str = ""     # PEM block
    sp_entity_id: str = ""
    sp_acs_url: str = ""          # https://yourdomain.com/saml/acs
    sp_private_key: str = ""      # encrypted at rest
    sp_certificate: str = ""
    name_id_format: str = "urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress"
    attribute_username: str = "email"
    attribute_display_name: str = "displayName"
    attribute_role: str = "role"


@dataclass
class GCloudConfig:
    client_id: str = ""
    client_secret: str = ""       # encrypted at rest
    hd: str = ""                  # hosted domain, e.g. "agency.go.kr"
    allowed_domains: list[str] = field(default_factory=list)
    default_role: str = "member"


@dataclass
class OAuth2Config:
    client_id: str = ""
    client_secret: str = ""       # encrypted at rest
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


# ── Encryption helpers ─────────────────────────────────────────────────────────

def _get_fernet_key() -> bytes:
    """Derive Fernet encryption key using PBKDF2 — stronger than plain SHA-256."""
    from app.config import get_sso_encryption_key
    base_key = get_sso_encryption_key().encode()
    # Static salt for key stretching (not password storage — salt serves as domain separation)
    salt = b"decisiondoc-sso-encryption-v1"
    derived = hashlib.pbkdf2_hmac("sha256", base_key, salt, iterations=100_000, dklen=32)
    return base64.urlsafe_b64encode(derived)


def encrypt_secret(plain: str) -> str:
    """Encrypt a secret string using Fernet (AES-256). Returns base64-encoded token."""
    if not plain:
        return ""
    from cryptography.fernet import Fernet
    key = _get_fernet_key()
    return Fernet(key).encrypt(plain.encode()).decode()


def decrypt_secret(cipher: str) -> str:
    """Decrypt a Fernet-encrypted secret. Returns plain text, or cipher on error."""
    if not cipher:
        return ""
    try:
        from cryptography.fernet import Fernet
        key = _get_fernet_key()
        return Fernet(key).decrypt(cipher.encode()).decode()
    except Exception:
        return cipher


# ── JSON serialization helpers ─────────────────────────────────────────────────

def _sso_config_to_dict(cfg: SSOConfig) -> dict:
    """Serialize SSOConfig to a plain dict for JSON storage."""
    d = asdict(cfg)
    d["provider"] = cfg.provider.value
    return d


def _sso_config_from_dict(tenant_id: str, d: dict) -> SSOConfig:
    """Reconstruct SSOConfig from a plain dict."""
    provider_val = d.get("provider", SSOProvider.DISABLED.value)
    try:
        provider = SSOProvider(provider_val)
    except ValueError:
        provider = SSOProvider.DISABLED

    ldap_data = d.get("ldap", {})
    saml_data = d.get("saml", {})
    gcloud_data = d.get("gcloud", {})
    oauth2_data = d.get("oauth2", {})

    ldap = LDAPConfig(**{k: v for k, v in ldap_data.items() if hasattr(LDAPConfig, k) or k in LDAPConfig.__dataclass_fields__})
    saml = SAMLConfig(**{k: v for k, v in saml_data.items() if k in SAMLConfig.__dataclass_fields__})
    gcloud = GCloudConfig(**{k: v for k, v in gcloud_data.items() if k in GCloudConfig.__dataclass_fields__})
    oauth2 = OAuth2Config(**{k: v for k, v in oauth2_data.items() if k in OAuth2Config.__dataclass_fields__})

    return SSOConfig(
        tenant_id=d.get("tenant_id", tenant_id),
        provider=provider,
        ldap=ldap,
        saml=saml,
        gcloud=gcloud,
        oauth2=oauth2,
        updated_at=d.get("updated_at", ""),
    )


# ── SSOStore ───────────────────────────────────────────────────────────────────

class SSOStore(BaseJsonStore):
    """Thread-safe, file-backed SSO configuration store scoped to a single tenant."""

    def __init__(self, tenant_id: str) -> None:
        super().__init__()
        self._tenant_id = tenant_id
        data_dir = Path(os.getenv("DATA_DIR", "./data"))
        tenant_dir = data_dir / "tenants" / tenant_id
        tenant_dir.mkdir(parents=True, exist_ok=True)
        self._path = tenant_dir / "sso_config.json"

    def _get_path(self) -> Path:
        return self._path

    def get(self) -> SSOConfig:
        """Load SSO config from disk. Returns default SSOConfig if file missing."""
        with self._lock:
            data = self._load()
            if not data:
                return SSOConfig(tenant_id=self._tenant_id)
            try:
                return _sso_config_from_dict(self._tenant_id, data)
            except (TypeError, KeyError):
                return SSOConfig(tenant_id=self._tenant_id)

    def save(self, config: SSOConfig) -> None:
        """Serialize and atomically write SSOConfig to disk."""
        d = _sso_config_to_dict(config)
        with self._lock:
            atomic_write_text(self._path, __import__("json").dumps(d, ensure_ascii=False, indent=2))

    def is_sso_enabled(self) -> bool:
        """Return True if SSO is configured (provider != DISABLED)."""
        return self.get().provider != SSOProvider.DISABLED

    def encrypt_secret(self, plain: str) -> str:
        """Encrypt a secret. Delegates to module-level encrypt_secret."""
        return encrypt_secret(plain)

    def decrypt_secret(self, cipher: str) -> str:
        """Decrypt a secret. Delegates to module-level decrypt_secret."""
        return decrypt_secret(cipher)


# ── Singleton factory ──────────────────────────────────────────────────────────

_sso_stores: dict[str, SSOStore] = {}
_sso_stores_lock = threading.Lock()


def get_sso_store(tenant_id: str) -> SSOStore:
    """Return a shared SSOStore instance for the given tenant."""
    with _sso_stores_lock:
        if tenant_id not in _sso_stores:
            _sso_stores[tenant_id] = SSOStore(tenant_id)
        return _sso_stores[tenant_id]
