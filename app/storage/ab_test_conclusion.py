"""Resumable A/B conclusion coordination across experiment and override state."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from app.storage.ab_test_store import ABTestStore


_PENDING_CONCLUSION_FIELD = "_pending_conclusion"


def evaluate_and_conclude(
    store: ABTestStore,
    bundle_id: str,
    *,
    experiment_id: str | None = None,
) -> str | None:
    """Claim, apply, and finalize one eligible experiment conclusion."""
    operation_id = uuid.uuid4().hex
    target_incarnation: str | None = None
    target_bound = False
    concluded_at = datetime.now(timezone.utc).isoformat()

    def claim(data: dict[str, Any]) -> tuple[dict[str, Any] | None, bool]:
        nonlocal operation_id, target_bound, target_incarnation
        record = data.get(bundle_id)
        if not store._owns(record) or record.get("status") != "active":
            return None, False
        incarnation_id = store._incarnation_id(record)
        if experiment_id is not None and incarnation_id != experiment_id:
            return None, False
        if not target_bound:
            target_incarnation = incarnation_id
            target_bound = True
        elif incarnation_id != target_incarnation:
            return None, False

        pending = record.get(_PENDING_CONCLUSION_FIELD)
        if pending is not None:
            operation_id = pending["operation_id"]
            return dict(pending), False

        conclusion = store._conclusion_values(record)
        if conclusion is None:
            return None, False
        winner, winner_average, override_hint = conclusion
        pending = {
            "operation_id": operation_id,
            "winner": winner,
            "winner_avg_score": winner_average,
            "override_hint": override_hint,
            "concluded_at": concluded_at,
        }
        updated = dict(record)
        updated[_PENDING_CONCLUSION_FIELD] = pending
        data[bundle_id] = store._record_mutation(
            updated,
            previous=record,
            mutation_id=operation_id,
        )
        return dict(pending), True

    def claim_was_committed(data: dict[str, Any]) -> bool:
        record = data.get(bundle_id)
        if (
            not store._owns(record)
            or store._incarnation_id(record) != target_incarnation
            or operation_id not in store._mutation_ids(record)
        ):
            return False
        pending = record.get(_PENDING_CONCLUSION_FIELD)
        return pending is not None or record.get("status") == "concluded"

    with store._lock:
        pending = store._mutate(claim, committed=claim_was_committed)
    if pending is None:
        return None

    from app.storage.prompt_override_store import PromptOverrideStore

    PromptOverrideStore(
        store._data_dir,
        tenant_id=store._tenant_id,
        backend=store._backend,
    ).save_override(
        bundle_id=bundle_id,
        override_hint=pending["override_hint"],
        trigger_reason="ab_test_winner",
        avg_score_before=0.0,
        operation_id=pending["operation_id"],
    )

    finalize_id = uuid.uuid4().hex

    def finalize(data: dict[str, Any]) -> tuple[str | None, bool]:
        record = data.get(bundle_id)
        if (
            not store._owns(record)
            or store._incarnation_id(record) != target_incarnation
        ):
            return None, False
        if record.get("status") == "concluded":
            if pending["operation_id"] in store._mutation_ids(record):
                return record["winner"], False
            return None, False
        current_pending = record.get(_PENDING_CONCLUSION_FIELD)
        if (
            current_pending is None
            or current_pending["operation_id"] != pending["operation_id"]
        ):
            return None, False
        updated = dict(record)
        updated["status"] = "concluded"
        updated["concluded_at"] = current_pending["concluded_at"]
        updated["winner"] = current_pending["winner"]
        updated["winner_avg_score"] = current_pending["winner_avg_score"]
        updated.pop(_PENDING_CONCLUSION_FIELD)
        data[bundle_id] = store._record_mutation(
            updated,
            previous=record,
            mutation_id=finalize_id,
        )
        return current_pending["winner"], True

    def finalize_was_committed(data: dict[str, Any]) -> bool:
        record = data.get(bundle_id)
        return (
            store._owns(record)
            and store._incarnation_id(record) == target_incarnation
            and record.get("status") == "concluded"
            and pending["operation_id"] in store._mutation_ids(record)
            and finalize_id in store._mutation_ids(record)
        )

    with store._lock:
        return store._mutate(finalize, committed=finalize_was_committed)
