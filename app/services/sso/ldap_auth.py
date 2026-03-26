"""LDAP/Active-Directory authentication for SSO.

Uses ldap3 library (optional dependency — ImportError handled gracefully).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.storage.sso_store import LDAPConfig


@dataclass
class LDAPUser:
    username: str
    display_name: str
    email: str
    role: str   # admin | member | viewer


def authenticate_ldap(config: LDAPConfig, username: str, password: str) -> LDAPUser | None:
    """Authenticate user against LDAP/AD. Returns LDAPUser or None if failed.

    Raises RuntimeError if ldap3 is not installed.
    Raises ValueError on bad config.
    """
    try:
        import ldap3
    except ImportError:
        raise RuntimeError("ldap3 not installed. Run: pip install ldap3")

    if not config.server_url:
        raise ValueError("LDAP server_url is not configured")

    server = ldap3.Server(config.server_url, use_ssl=config.tls, get_info=ldap3.ALL)

    # First bind with service account to search
    conn = ldap3.Connection(server, user=config.bind_dn, password=config.bind_password, auto_bind=False)
    if not conn.bind():
        raise ValueError(f"Service bind failed: {conn.last_error}")

    # Search for user DN
    search_filter = config.user_search_filter.replace("{username}", ldap3.utils.conv.escape_filter_chars(username))
    conn.search(config.base_dn, search_filter, attributes=["dn", "cn", "mail", "displayName", "memberOf"])

    if not conn.entries:
        return None

    entry = conn.entries[0]
    user_dn = entry.entry_dn

    # Bind as the found user to verify password
    user_conn = ldap3.Connection(server, user=user_dn, password=password, auto_bind=False)
    if not user_conn.bind():
        return None

    # Determine role from group membership
    member_of = _get_attr(entry, "memberOf", [])
    role = _determine_role(config, member_of)

    display_name = _get_attr(entry, "displayName") or _get_attr(entry, "cn") or username
    email = _get_attr(entry, "mail") or ""

    return LDAPUser(username=username, display_name=display_name, email=email, role=role)


def test_ldap_connection(config: LDAPConfig) -> dict:
    """Test LDAP connection with service account. Returns {"ok": bool, "message": str}."""
    try:
        import ldap3
    except ImportError:
        return {"ok": False, "message": "ldap3 not installed"}

    if not config.server_url:
        return {"ok": False, "message": "server_url is empty"}

    try:
        server = ldap3.Server(config.server_url, use_ssl=config.tls, get_info=ldap3.ALL, connect_timeout=5)
        conn = ldap3.Connection(server, user=config.bind_dn, password=config.bind_password, auto_bind=False)
        if conn.bind():
            conn.unbind()
            return {"ok": True, "message": f"Connected to {config.server_url} successfully"}
        else:
            return {"ok": False, "message": f"Bind failed: {conn.last_error}"}
    except Exception as exc:
        return {"ok": False, "message": str(exc)}


def _get_attr(entry, attr: str, default=None):
    """Safely retrieve a single attribute value from an ldap3 entry."""
    try:
        val = getattr(entry, attr, None)
        if val is None:
            return default
        values = val.values
        if isinstance(values, list):
            return values[0] if values else default
        return str(val) if val else default
    except Exception:
        return default


def _determine_role(config: LDAPConfig, member_of: list[str]) -> str:
    """Determine user role from group membership. Returns admin/member/viewer."""
    member_of_lower = [g.lower() for g in (member_of or [])]
    if config.admin_group and config.admin_group.lower() in member_of_lower:
        return "admin"
    if config.member_group and config.member_group.lower() in member_of_lower:
        return "member"
    if config.viewer_group and config.viewer_group.lower() in member_of_lower:
        return "viewer"
    # Default: member if no group configured, viewer otherwise
    if not any([config.admin_group, config.member_group, config.viewer_group]):
        return "member"
    return "viewer"
