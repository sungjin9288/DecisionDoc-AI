"""Tenant-scoped plan and billing account state."""

from __future__ import annotations

import json
import os
import threading
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from app.storage.state_backend import StateBackend, get_state_backend
from app.tenant import require_tenant_id


@dataclass
class PlanConfig:
    plan_id: str
    plan_name: str
    monthly_generations: int
    monthly_tokens: int
    max_users: int
    max_bundles: int
    max_projects: int
    features: list[str]
    base_price_usd: float
    price_per_1k_tokens: float
    stripe_price_id: str | None
    billing_cycle: str


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
        features=[
            "basic_bundles",
            "gov_bundles",
            "approval_workflow",
            "rfp_analysis",
            "g2b_integration",
            "custom_style",
        ],
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
        features=[
            "basic_bundles",
            "gov_bundles",
            "approval_workflow",
            "rfp_analysis",
            "g2b_integration",
            "custom_style",
            "sso",
            "audit_logs",
            "local_llm",
            "finetune",
            "multi_tenant",
            "api_access",
        ],
        base_price_usd=499,
        price_per_1k_tokens=0,
        stripe_price_id=None,
        billing_cycle="monthly",
    ),
}

_ACCOUNT_STATUSES = {"active", "past_due", "canceled", "trialing"}

_billing_locks: dict[tuple[Any, ...], threading.RLock] = {}
_billing_locks_guard = threading.Lock()

_store_instances: dict[tuple[Any, ...], "BillingStore"] = {}
_store_meta_lock = threading.Lock()


class BillingStoreError(RuntimeError):
    """Raised when persisted billing state cannot be trusted."""


@dataclass
class BillingAccount:
    tenant_id: str
    plan_id: str
    status: str
    trial_ends_at: str | None
    current_period_start: str
    current_period_end: str
    stripe_customer_id: str | None
    stripe_subscription_id: str | None
    card_last4: str | None
    card_brand: str | None
    created_at: str
    updated_at: str


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
    with _billing_locks_guard:
        return _billing_locks.setdefault(key, threading.RLock())


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise BillingStoreError(f"Duplicate key in billing state: {key!r}")
        result[key] = value
    return result


def _default_account(tenant_id: str) -> BillingAccount:
    now = datetime.now(timezone.utc)
    period_start = now.replace(day=1)
    period_end = (period_start + timedelta(days=32)).replace(day=1)
    return BillingAccount(
        tenant_id=tenant_id,
        plan_id="free",
        status="active",
        trial_ends_at=None,
        current_period_start=period_start.isoformat(),
        current_period_end=period_end.isoformat(),
        stripe_customer_id=None,
        stripe_subscription_id=None,
        card_last4=None,
        card_brand=None,
        created_at=now.isoformat(),
        updated_at=now.isoformat(),
    )


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


def _optional_input_string(value: object, *, field: str) -> str | None:
    if value is None:
        return None
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    ):
        raise ValueError(f"Invalid {field}")
    return value


def get_billing_store(
    tenant_id: str,
    data_dir: str | Path | None = None,
    *,
    backend: StateBackend | None = None,
) -> "BillingStore":
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
    with _store_meta_lock:
        store = _store_instances.get(key)
        if store is None:
            store = BillingStore(
                tenant_id,
                data_dir=root,
                backend=selected_backend,
            )
            _store_instances[key] = store
        return store


class BillingStore:
    """Read and update one tenant's billing account."""

    def __init__(
        self,
        tenant_id: str,
        data_dir: str | Path | None = None,
        *,
        backend: StateBackend | None = None,
    ) -> None:
        self._tenant_id = require_tenant_id(tenant_id)
        self._data_dir = Path(data_dir or os.getenv("DATA_DIR", "data"))
        self._relative_path = str(Path("tenants") / self._tenant_id / "billing.json")
        self._path = self._data_dir / self._relative_path
        self._backend = backend or get_state_backend(data_dir=self._data_dir)
        self._lock = _lock_for_state(
            self._backend,
            path=self._path,
            relative_path=self._relative_path,
        )

    @staticmethod
    def _optional_string(value: object, *, field: str) -> str | None:
        if value is None:
            return None
        if (
            not isinstance(value, str)
            or not value
            or value != value.strip()
            or any(ord(character) < 32 or ord(character) == 127 for character in value)
        ):
            raise BillingStoreError(f"Invalid {field}")
        return value

    @staticmethod
    def _timestamp(value: object, *, field: str) -> str:
        if not isinstance(value, str) or not value:
            raise BillingStoreError(f"Invalid {field}")
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError as exc:
            raise BillingStoreError(f"Invalid {field}") from exc
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise BillingStoreError(f"Invalid {field}")
        return value

    def _account_from_payload(self, payload: object) -> BillingAccount:
        if not isinstance(payload, dict):
            raise BillingStoreError("Invalid billing state")

        expected_fields = set(BillingAccount.__dataclass_fields__)
        if set(payload) != expected_fields:
            raise BillingStoreError("Invalid billing account fields")
        if payload.get("tenant_id") != self._tenant_id:
            raise BillingStoreError("Billing account tenant ownership mismatch")

        plan_id = payload.get("plan_id")
        if not isinstance(plan_id, str) or plan_id not in PREDEFINED_PLANS:
            raise BillingStoreError("Invalid billing plan")
        status = payload.get("status")
        if not isinstance(status, str) or status not in _ACCOUNT_STATUSES:
            raise BillingStoreError("Invalid billing status")

        trial_ends_at = self._optional_string(
            payload.get("trial_ends_at"),
            field="trial end timestamp",
        )
        if trial_ends_at is not None:
            self._timestamp(trial_ends_at, field="trial end timestamp")
        current_period_start = self._timestamp(
            payload.get("current_period_start"),
            field="billing period start",
        )
        current_period_end = self._timestamp(
            payload.get("current_period_end"),
            field="billing period end",
        )
        try:
            period_is_invalid = datetime.fromisoformat(
                current_period_end
            ) <= datetime.fromisoformat(current_period_start)
        except TypeError as exc:
            raise BillingStoreError("Invalid billing period") from exc
        if period_is_invalid:
            raise BillingStoreError("Invalid billing period")

        stripe_customer_id = self._optional_string(
            payload.get("stripe_customer_id"),
            field="Stripe customer identity",
        )
        stripe_subscription_id = self._optional_string(
            payload.get("stripe_subscription_id"),
            field="Stripe subscription identity",
        )
        card_last4 = self._optional_string(
            payload.get("card_last4"),
            field="card last four digits",
        )
        if card_last4 is not None and (
            len(card_last4) != 4 or not card_last4.isascii() or not card_last4.isdigit()
        ):
            raise BillingStoreError("Invalid card last four digits")
        card_brand = self._optional_string(
            payload.get("card_brand"),
            field="card brand",
        )
        created_at = self._timestamp(
            payload.get("created_at"),
            field="billing created timestamp",
        )
        updated_at = self._timestamp(
            payload.get("updated_at"),
            field="billing updated timestamp",
        )
        if datetime.fromisoformat(updated_at) < datetime.fromisoformat(created_at):
            raise BillingStoreError("Invalid billing update timestamp")

        return BillingAccount(
            tenant_id=self._tenant_id,
            plan_id=plan_id,
            status=status,
            trial_ends_at=trial_ends_at,
            current_period_start=current_period_start,
            current_period_end=current_period_end,
            stripe_customer_id=stripe_customer_id,
            stripe_subscription_id=stripe_subscription_id,
            card_last4=card_last4,
            card_brand=card_brand,
            created_at=created_at,
            updated_at=updated_at,
        )

    def _load_account(self) -> BillingAccount:
        raw = self._backend.read_text(self._relative_path)
        if raw is None:
            return _default_account(self._tenant_id)
        try:
            payload = json.loads(raw, object_pairs_hook=_unique_object)
        except (json.JSONDecodeError, TypeError, BillingStoreError) as exc:
            raise BillingStoreError("Invalid billing state document") from exc
        return self._account_from_payload(payload)

    def _save_account(self, account: BillingAccount) -> None:
        validated = self._account_from_payload(asdict(account))
        self._backend.write_text(
            self._relative_path,
            json.dumps(asdict(validated), ensure_ascii=False, indent=2),
        )

    @staticmethod
    def _require_plan(plan_id: object) -> str:
        if not isinstance(plan_id, str) or plan_id not in PREDEFINED_PLANS:
            raise ValueError("Invalid billing plan")
        return plan_id

    @staticmethod
    def _require_status(status: object) -> str:
        if not isinstance(status, str) or status not in _ACCOUNT_STATUSES:
            raise ValueError("Invalid billing status")
        return status

    def get_account(self) -> BillingAccount:
        with self._lock:
            return self._load_account()

    def get_account_and_plan(self) -> tuple[BillingAccount, PlanConfig]:
        with self._lock:
            account = self._load_account()
            return account, PREDEFINED_PLANS[account.plan_id]

    def get_plan(self) -> PlanConfig:
        return self.get_account_and_plan()[1]

    def update_plan(
        self,
        plan_id: str,
        stripe_data: dict | None = None,
    ) -> None:
        plan_id = self._require_plan(plan_id)
        if stripe_data is not None and not isinstance(stripe_data, dict):
            raise ValueError("Invalid Stripe billing data")
        if stripe_data is not None and set(stripe_data) - {
            "stripe_customer_id",
            "stripe_subscription_id",
        }:
            raise ValueError("Invalid Stripe billing data")
        customer_id = _optional_input_string(
            (stripe_data or {}).get("stripe_customer_id"),
            field="Stripe customer identity",
        )
        subscription_id = _optional_input_string(
            (stripe_data or {}).get("stripe_subscription_id"),
            field="Stripe subscription identity",
        )
        with self._lock:
            account = self._load_account()
            account.plan_id = plan_id
            account.updated_at = datetime.now(timezone.utc).isoformat()
            if customer_id is not None:
                account.stripe_customer_id = customer_id
            if subscription_id is not None:
                account.stripe_subscription_id = subscription_id
            self._save_account(account)

    def update_stripe_info(
        self,
        customer_id: str | None,
        subscription_id: str | None,
        card_last4: str | None,
        card_brand: str | None,
    ) -> None:
        customer_id = _optional_input_string(
            customer_id,
            field="Stripe customer identity",
        )
        subscription_id = _optional_input_string(
            subscription_id,
            field="Stripe subscription identity",
        )
        card_last4 = _optional_input_string(
            card_last4,
            field="card last four digits",
        )
        if card_last4 is not None and (
            len(card_last4) != 4 or not card_last4.isascii() or not card_last4.isdigit()
        ):
            raise ValueError("Invalid card last four digits")
        card_brand = _optional_input_string(card_brand, field="card brand")

        with self._lock:
            account = self._load_account()
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

    def set_status(self, status: str) -> None:
        status = self._require_status(status)
        with self._lock:
            account = self._load_account()
            account.status = status
            account.updated_at = datetime.now(timezone.utc).isoformat()
            self._save_account(account)

    def apply_subscription_update(
        self,
        *,
        plan_id: str,
        status: str,
        customer_id: str | None = None,
        subscription_id: str | None = None,
    ) -> None:
        plan_id = self._require_plan(plan_id)
        status = self._require_status(status)
        customer_id = _optional_input_string(
            customer_id,
            field="Stripe customer identity",
        )
        subscription_id = _optional_input_string(
            subscription_id,
            field="Stripe subscription identity",
        )
        with self._lock:
            account = self._load_account()
            account.plan_id = plan_id
            account.status = status
            if customer_id is not None:
                account.stripe_customer_id = customer_id
            if subscription_id is not None:
                account.stripe_subscription_id = subscription_id
            account.updated_at = datetime.now(timezone.utc).isoformat()
            self._save_account(account)

    def is_feature_enabled(self, feature: str) -> bool:
        if not isinstance(feature, str):
            raise ValueError("Invalid billing feature")
        return feature in self.get_plan().features

    def get_overage_cost(self) -> float:
        from app.storage.usage_store import UsageStore

        plan = self.get_plan()
        if plan.monthly_tokens == -1 or plan.price_per_1k_tokens == 0:
            return 0.0
        summary = UsageStore(
            self._data_dir,
            tenant_id=self._tenant_id,
            backend=self._backend,
        ).get_current_month()
        if summary is None:
            return 0.0
        overage = summary.total_tokens - plan.monthly_tokens
        if overage <= 0:
            return 0.0
        return (overage / 1000) * plan.price_per_1k_tokens
