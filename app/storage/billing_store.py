"""app/storage/billing_store.py — Plan management and billing account storage.

Storage: data/tenants/{tenant_id}/billing.json
"""
from __future__ import annotations

import json
import os
import threading
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone, timedelta
from pathlib import Path

from app.storage.base import BaseJsonStore


@dataclass
class PlanConfig:
    plan_id: str           # "free" | "pro" | "enterprise" | "custom"
    plan_name: str

    # Monthly limits
    monthly_generations: int    # -1 = unlimited
    monthly_tokens: int         # -1 = unlimited
    max_users: int              # -1 = unlimited
    max_bundles: int            # -1 = unlimited
    max_projects: int           # -1 = unlimited

    # Features
    features: list

    # Pricing
    base_price_usd: float
    price_per_1k_tokens: float

    # Billing
    stripe_price_id: str | None
    billing_cycle: str          # "monthly" | "annual"


PREDEFINED_PLANS: dict[str, PlanConfig] = {
    "free": PlanConfig(
        plan_id="free",
        plan_name="무료",
        monthly_generations=20,
        monthly_tokens=100_000,
        max_users=3,
        max_bundles=5,
        max_projects=3,
        features=["basic_bundles"],
        base_price_usd=0,
        price_per_1k_tokens=0,
        stripe_price_id=None,
        billing_cycle="monthly",
    ),
    "pro": PlanConfig(
        plan_id="pro",
        plan_name="프로",
        monthly_generations=200,
        monthly_tokens=2_000_000,
        max_users=20,
        max_bundles=-1,
        max_projects=-1,
        features=["basic_bundles", "gov_bundles", "approval_workflow",
                  "rfp_analysis", "g2b_integration", "custom_style"],
        base_price_usd=99,
        price_per_1k_tokens=0.002,
        stripe_price_id=None,
        billing_cycle="monthly",
    ),
    "enterprise": PlanConfig(
        plan_id="enterprise",
        plan_name="엔터프라이즈",
        monthly_generations=-1,
        monthly_tokens=-1,
        max_users=-1,
        max_bundles=-1,
        max_projects=-1,
        features=["basic_bundles", "gov_bundles", "approval_workflow",
                  "rfp_analysis", "g2b_integration", "custom_style",
                  "sso", "audit_logs", "local_llm", "finetune",
                  "multi_tenant", "api_access"],
        base_price_usd=499,
        price_per_1k_tokens=0,
        stripe_price_id=None,
        billing_cycle="monthly",
    ),
}


@dataclass
class BillingAccount:
    tenant_id: str
    plan_id: str
    status: str              # "active" | "past_due" | "canceled" | "trialing"
    trial_ends_at: str | None
    current_period_start: str
    current_period_end: str
    stripe_customer_id: str | None
    stripe_subscription_id: str | None
    card_last4: str | None
    card_brand: str | None
    created_at: str
    updated_at: str


def _default_account(tenant_id: str) -> BillingAccount:
    now = datetime.now(timezone.utc)
    period_start = now.replace(day=1).isoformat()
    period_end = (now.replace(day=1) + timedelta(days=32)).replace(day=1).isoformat()
    return BillingAccount(
        tenant_id=tenant_id,
        plan_id="free",
        status="active",
        trial_ends_at=None,
        current_period_start=period_start,
        current_period_end=period_end,
        stripe_customer_id=None,
        stripe_subscription_id=None,
        card_last4=None,
        card_brand=None,
        created_at=now.isoformat(),
        updated_at=now.isoformat(),
    )


# Singleton store instances keyed by tenant_id
_store_instances: dict[str, "BillingStore"] = {}
_store_meta_lock: threading.Lock = threading.Lock()


def get_billing_store(tenant_id: str) -> "BillingStore":
    """Return a singleton BillingStore for the given tenant."""
    with _store_meta_lock:
        if tenant_id not in _store_instances:
            _store_instances[tenant_id] = BillingStore(tenant_id)
        return _store_instances[tenant_id]


class BillingStore(BaseJsonStore):
    """Per-tenant billing account store. Thread-safe via instance lock."""

    def __init__(self, tenant_id: str) -> None:
        super().__init__()
        self._tenant_id = tenant_id
        self._data_dir = Path(os.getenv("DATA_DIR", "./data"))

    def _get_path(self) -> Path:
        return self._billing_path(self._tenant_id)

    def _billing_path(self, tenant_id: str) -> Path:
        return self._data_dir / "tenants" / tenant_id / "billing.json"

    def _load_account(self, tenant_id: str) -> BillingAccount:
        path = self._billing_path(tenant_id)
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                return BillingAccount(**data)
            except (OSError, json.JSONDecodeError, TypeError, KeyError):
                pass
        return _default_account(tenant_id)

    def _save_account(self, account: BillingAccount) -> None:
        path = self._billing_path(account.tenant_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_name(f"{path.name}.tmp.{uuid.uuid4().hex}")
        try:
            tmp_path.write_text(
                json.dumps(asdict(account), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            os.replace(tmp_path, path)
        finally:
            if tmp_path.exists():
                try:
                    tmp_path.unlink()
                except OSError:
                    pass

    # ── Public API ────────────────────────────────────────────────────────────

    def get_account(self, tenant_id: str | None = None) -> BillingAccount:
        """Return billing account, creating a free default if missing."""
        tid = tenant_id or self._tenant_id
        with self._lock:
            return self._load_account(tid)

    def get_plan(self, tenant_id: str | None = None) -> PlanConfig:
        """Return the PlanConfig for the tenant's current plan."""
        account = self.get_account(tenant_id)
        return PREDEFINED_PLANS.get(account.plan_id, PREDEFINED_PLANS["free"])

    def update_plan(
        self,
        tenant_id: str,
        plan_id: str,
        stripe_data: dict | None = None,
    ) -> None:
        with self._lock:
            account = self._load_account(tenant_id)
            account.plan_id = plan_id
            account.updated_at = datetime.now(timezone.utc).isoformat()
            if stripe_data:
                if "stripe_customer_id" in stripe_data:
                    account.stripe_customer_id = stripe_data["stripe_customer_id"]
                if "stripe_subscription_id" in stripe_data:
                    account.stripe_subscription_id = stripe_data["stripe_subscription_id"]
            self._save_account(account)

    def update_stripe_info(
        self,
        tenant_id: str,
        customer_id: str | None,
        subscription_id: str | None,
        card_last4: str | None,
        card_brand: str | None,
    ) -> None:
        with self._lock:
            account = self._load_account(tenant_id)
            if customer_id is not None:
                account.stripe_customer_id = customer_id
            if subscription_id is not None:
                account.stripe_subscription_id = subscription_id
            if card_last4 is not None:
                account.card_last4 = card_last4
            if card_brand is not None:
                account.card_brand = card_brand
            account.updated_at = datetime.now(timezone.utc).isoformat()
            self._save_account(account)

    def set_status(self, tenant_id: str, status: str) -> None:
        with self._lock:
            account = self._load_account(tenant_id)
            account.status = status
            account.updated_at = datetime.now(timezone.utc).isoformat()
            self._save_account(account)

    def is_feature_enabled(self, tenant_id: str, feature: str) -> bool:
        plan = self.get_plan(tenant_id)
        return feature in plan.features

    def get_overage_cost(self, tenant_id: str) -> float:
        """Return cost for tokens used beyond the plan's monthly limit."""
        from app.storage.usage_store import UsageStore
        plan = self.get_plan(tenant_id)
        if plan.monthly_tokens == -1 or plan.price_per_1k_tokens == 0:
            return 0.0
        summary = UsageStore().get_current_month(tenant_id)
        if summary is None:
            return 0.0
        overage = summary.total_tokens - plan.monthly_tokens
        if overage <= 0:
            return 0.0
        return (overage / 1000) * plan.price_per_1k_tokens
