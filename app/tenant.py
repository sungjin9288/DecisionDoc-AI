"""tenant.py — Multi-tenant data model and constants."""
from __future__ import annotations

from dataclasses import dataclass

SYSTEM_TENANT_ID = "system"  # default tenant for single-tenant mode


@dataclass
class Tenant:
    tenant_id: str         # e.g. "acme-corp", "team-alpha"
    display_name: str
    allowed_bundles: list[str]    # empty list = all bundles allowed
    custom_prompt_hints: dict[str, str]  # bundle_id -> extra hint
    created_at: str
    is_active: bool = True
