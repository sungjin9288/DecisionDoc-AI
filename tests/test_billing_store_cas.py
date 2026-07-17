from __future__ import annotations

import json
from contextlib import nullcontext
from dataclasses import asdict
from pathlib import Path

import pytest

from app.storage.billing_store import BillingStore, BillingStoreError
from tests.billing_state_support import (
    BillingMemoryS3Client,
    ConflictingBillingBackend,
    FailingBillingBackend,
    billing_s3_backend,
)


def test_billing_mutation_reconciles_commit_then_successor_update(
    tmp_path: Path,
) -> None:
    client = BillingMemoryS3Client()
    bootstrap_backend, _ = billing_s3_backend(client)
    bootstrap = BillingStore("alpha", data_dir=tmp_path, backend=bootstrap_backend)
    bootstrap.update_plan("pro")
    primary = BillingStore(
        "alpha",
        data_dir=tmp_path / "primary",
        backend=billing_s3_backend(client)[0],
    )
    successor = BillingStore(
        "alpha",
        data_dir=tmp_path / "successor",
        backend=billing_s3_backend(client)[0],
    )
    primary._lock = nullcontext()
    successor._lock = nullcontext()
    client.fail_after_next_conditional_write(
        after_write=lambda: successor.set_status("past_due")
    )

    primary.update_stripe_info("cus_1", "sub_1", "4242", "visa")

    account = bootstrap.get_account()
    assert account.plan_id == "pro"
    assert account.status == "past_due"
    assert account.stripe_customer_id == "cus_1"
    assert account.stripe_subscription_id == "sub_1"
    assert account.card_last4 == "4242"
    assert account.card_brand == "visa"


def test_billing_mutation_stops_after_bounded_conflicts(tmp_path: Path) -> None:
    backend = ConflictingBillingBackend(tmp_path)
    store = BillingStore("alpha", data_dir=tmp_path, backend=backend)

    with pytest.raises(
        BillingStoreError,
        match="Billing state changed too many times to persist safely",
    ):
        store.update_plan("pro")

    assert backend.attempts == 32


def test_billing_mutation_wraps_backend_failure(tmp_path: Path) -> None:
    store = BillingStore(
        "alpha",
        data_dir=tmp_path,
        backend=FailingBillingBackend(tmp_path),
    )

    with pytest.raises(BillingStoreError, match="Failed to persist billing state"):
        store.update_plan("pro")


def test_billing_mutation_receipts_are_private_bounded_and_fail_closed(
    tmp_path: Path,
) -> None:
    store = BillingStore("alpha", data_dir=tmp_path)
    for index in range(70):
        store.set_status("active" if index % 2 else "trialing")

    account = store.get_account()
    persisted_path = tmp_path / "tenants/alpha/billing.json"
    persisted = json.loads(persisted_path.read_text(encoding="utf-8"))
    assert "_mutation_ids" not in asdict(account)
    assert len(persisted["_mutation_ids"]) == 64

    persisted["_mutation_ids"] = [
        f"mutation-{index}" for index in range(65)
    ]
    persisted_path.write_text(json.dumps(persisted), encoding="utf-8")
    original_bytes = persisted_path.read_bytes()

    with pytest.raises(BillingStoreError):
        store.get_account()
    with pytest.raises(BillingStoreError):
        store.update_plan("pro")
    assert persisted_path.read_bytes() == original_bytes
