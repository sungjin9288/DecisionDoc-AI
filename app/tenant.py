"""tenant.py — Multi-tenant data model and constants."""
from __future__ import annotations

from dataclasses import dataclass

SYSTEM_TENANT_ID = "system"  # default tenant for single-tenant mode


def require_tenant_id(tenant_id: object) -> str:
    """Return a safe tenant identifier or raise before scoped state is used."""
    if (
        not isinstance(tenant_id, str)
        or not tenant_id
        or tenant_id != tenant_id.strip()
        or tenant_id in {".", ".."}
        or "/" in tenant_id
        or "\\" in tenant_id
        or "\x00" in tenant_id
    ):
        raise ValueError("Invalid tenant_id")
    return tenant_id


@dataclass
class Tenant:
    tenant_id: str         # e.g. "acme-corp", "team-alpha"
    display_name: str
    allowed_bundles: list[str]    # empty list = all bundles allowed
    custom_prompt_hints: dict[str, str]  # bundle_id -> extra hint
    created_at: str
    is_active: bool = True
