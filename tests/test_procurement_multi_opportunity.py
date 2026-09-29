"""The v2 store is isolated from application wiring and uses explicit backends."""
from __future__ import annotations

import copy
import json
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

import pytest

from app.schemas import (
    NormalizedProcurementOpportunity,
    ProcurementDecisionUpsert,
    ProcurementRecommendation,
)
from app.storage.procurement_store import ProcurementDecisionStore, ProcurementDecisionStoreError
from app.storage.state_backend import LocalStateBackend, StateBackendError
from tests.test_procurement_store_integrity import _s3_backend


PATH = "tenants/alpha/procurement_decisions.json"


@pytest.fixture(params=["local", "fake-s3"])
def backend(request, tmp_path):
    return LocalStateBackend(tmp_path) if request.param == "local" else _s3_backend()[0]


def _store(backend):
    from app.storage.procurement_project_store import ProcurementProjectStore
    return ProcurementProjectStore(backend=backend)


def _payload(source="A", *, project="project-1", tenant="alpha"):
    return ProcurementDecisionUpsert(
        tenant_id=tenant, project_id=project,
        opportunity=NormalizedProcurementOpportunity(source_kind="g2b", source_id=source, title=source),
    )


def _import(store, source="A", *, selection=0, revision=0, operation=None, payload=None):
    return store.import_opportunity(
        payload or _payload(source), expected_selection_revision=selection,
        expected_decision_revision=revision, operation_id=operation or str(uuid4()),
    )


def test_missing_read_does_not_create_state(backend):
    assert _store(backend).get("project-1", tenant_id="alpha") is None
    assert backend.read_text(PATH) is None


def test_imports_preserve_independent_identities_and_replay_original_receipt(backend):
    store = _store(backend)
    operation = str(uuid4())
    a = _import(store, operation=operation)
    b = _import(store, "B", selection=1)
    state = store.get("project-1", tenant_id="alpha")
    assert len(state.entries) == 2
    assert a.decision_id != b.decision_id
    assert state.active_decision_id == b.decision_id
    before = backend.read_text(PATH)
    assert _import(store, operation=operation) == a
    assert backend.read_text(PATH) == before
    with pytest.raises(ProcurementDecisionStoreError):
        _import(store, "C", selection=2, operation=operation)
    assert backend.read_text(PATH) == before


def test_legacy_read_is_pure_and_first_write_preserves_record_and_receipts(backend):
    legacy = ProcurementDecisionStore(backend=backend)
    old = legacy.upsert(_payload())
    before = backend.read_text(PATH)
    raw_old = json.loads(before)[0]
    store = _store(backend)
    state = store.get("project-1", tenant_id="alpha")
    assert state.entries[0].record == old
    assert state.entries[0].legacy_mutation_ids == raw_old["_mutation_ids"]
    assert state.selection_revision == 0
    assert backend.read_text(PATH) == before
    _import(store, "B")
    current = store.get("project-1", tenant_id="alpha")
    assert current.entries[0] == state.entries[0]
    assert current.entries[0].record.created_at == old.created_at


def test_refresh_clears_only_target_judgment_and_preserves_snapshot_history(backend):
    legacy = ProcurementDecisionStore(backend=backend)
    snapshot = legacy.save_source_snapshot(
        tenant_id="alpha", project_id="project-1", source_kind="g2b_import", payload={"old": "A"},
    )
    old = _payload()
    old.source_snapshots = [snapshot]
    old.notes = "A operator notes"
    old.recommendation = ProcurementRecommendation(value="GO", summary="Old judgment")
    legacy.upsert(old)
    store = _store(backend)
    b = _import(store, "B")
    before_b = store.get("project-1", tenant_id="alpha").entries[1].model_dump()
    new_snapshot = legacy.save_source_snapshot(
        tenant_id="alpha", project_id="project-1", source_kind="g2b_import", payload={"new": "A"},
    )
    refreshed = _payload()
    refreshed.source_snapshots = [new_snapshot]
    a = _import(store, selection=1, revision=1, payload=refreshed)
    state = store.get("project-1", tenant_id="alpha")
    assert state.active_decision_id == a.decision_id != b.decision_id
    assert state.entries[0].decision_revision == 2
    assert state.entries[0].record.recommendation is None
    assert state.entries[0].record.notes == "A operator notes"
    assert state.entries[0].record.source_snapshots == [snapshot, new_snapshot]
    assert state.entries[1].model_dump() == before_b


def test_select_does_not_rewrite_decisions_and_rejects_stale_revision(backend):
    store = _store(backend)
    a = _import(store)
    _import(store, "B", selection=1)
    before = store.get("project-1", tenant_id="alpha")
    receipt = store.select("project-1", tenant_id="alpha", decision_id=a.decision_id,
                           expected_selection_revision=2, operation_id=str(uuid4()))
    after = store.get("project-1", tenant_id="alpha")
    assert after.entries == before.entries
    assert receipt.selection_revision == 3
    snapshot = backend.read_text(PATH)
    with pytest.raises(ProcurementDecisionStoreError):
        store.select("project-1", tenant_id="alpha", decision_id=a.decision_id,
                     expected_selection_revision=2, operation_id=str(uuid4()))
    assert backend.read_text(PATH) == snapshot


def test_evaluation_persists_to_a_without_switching_back_from_b(backend):
    store = _store(backend)
    a = _import(store)
    record = store.get("project-1", tenant_id="alpha").entries[0].record
    b = _import(store, "B", selection=1)
    record.recommendation = ProcurementRecommendation(value="NO_GO", summary="A only")
    result = store.save_evaluation(record, expected_decision_revision=1, operation_id=str(uuid4()))
    after = store.get("project-1", tenant_id="alpha")
    assert result.decision_id == a.decision_id
    assert result.decision_revision == 2
    assert after.active_decision_id == b.decision_id
    assert after.selection_revision == 2
    assert after.entries[1].record.recommendation is None
    with pytest.raises(ProcurementDecisionStoreError):
        store.save_evaluation(record, expected_decision_revision=1, operation_id=str(uuid4()))


@pytest.mark.parametrize("field,value", [
    ("active_decision_id", "missing"), ("selection_revision", True),
    ("selection_revision", -1), ("unexpected", "field"),
])
def test_malformed_aggregate_stops_reads_and_writes(backend, field, value):
    store = _store(backend)
    _import(store)
    rows = json.loads(backend.read_text(PATH))
    rows[0][field] = value
    corrupt = json.dumps(rows)
    backend.write_text(PATH, corrupt)
    with pytest.raises(ProcurementDecisionStoreError):
        store.get("project-1", tenant_id="alpha")
    with pytest.raises(ProcurementDecisionStoreError):
        _import(store, "B", selection=1)
    assert backend.read_text(PATH) == corrupt


@pytest.mark.parametrize("kind", ["decision", "source", "project", "tenant", "duplicate-project"])
def test_scope_and_identity_corruption_are_rejected(backend, kind):
    store = _store(backend)
    _import(store)
    _import(store, "B", selection=1)
    rows = json.loads(backend.read_text(PATH))
    entries = rows[0]["entries"]
    if kind == "decision":
        entries[1]["record"]["decision_id"] = entries[0]["record"]["decision_id"]
    elif kind == "source":
        entries[1]["record"]["opportunity"] = copy.deepcopy(entries[0]["record"]["opportunity"])
    elif kind in {"project", "tenant"}:
        entries[0]["record"][f"{kind}_id"] = "elsewhere"
    else:
        rows.append(copy.deepcopy(rows[0]))
    backend.write_text(PATH, json.dumps(rows))
    with pytest.raises(ProcurementDecisionStoreError):
        store.get("project-1", tenant_id="alpha")


@pytest.mark.parametrize("revision,operation", [(True, None), (-1, None), (0, "not-a-uuid")])
def test_invalid_commands_do_not_create_state(backend, revision, operation):
    with pytest.raises(ValueError):
        _import(_store(backend), selection=revision, operation=operation)
    assert backend.read_text(PATH) is None


def test_other_projects_and_tenants_are_unchanged(backend):
    legacy = ProcurementDecisionStore(backend=backend)
    legacy.upsert(_payload(project="other-project"))
    legacy.upsert(_payload(tenant="other-tenant"))
    other = json.loads(backend.read_text(PATH))[0]
    foreign_path = "tenants/other-tenant/procurement_decisions.json"
    foreign = backend.read_text(foreign_path)
    store = _store(backend)
    a = _import(store)
    assert json.loads(backend.read_text(PATH))[0] == other
    assert backend.read_text(foreign_path) == foreign
    with pytest.raises(ProcurementDecisionStoreError):
        store.select("other-project", tenant_id="alpha", decision_id=a.decision_id,
                     expected_selection_revision=0, operation_id=str(uuid4()))


def test_failed_cas_is_not_retried(backend, monkeypatch):
    attempts = []
    def conflict(*args, **kwargs):
        attempts.append(1)
        return False
    monkeypatch.setattr(backend, "write_text_if_absent", conflict)
    with pytest.raises(ProcurementDecisionStoreError):
        _import(_store(backend))
    assert attempts == [1]
    assert backend.read_text(PATH) is None


def test_lost_success_response_reconciles_receipt_without_repeating_write(backend, monkeypatch):
    original = backend.write_text_if_absent
    attempts = []
    def lost_reply(*args, **kwargs):
        attempts.append(1)
        assert original(*args, **kwargs)
        raise StateBackendError("response lost after commit")
    monkeypatch.setattr(backend, "write_text_if_absent", lost_reply)
    store = _store(backend)
    operation = str(uuid4())
    result = _import(store, operation=operation)
    assert _import(store, operation=operation) == result
    assert attempts == [1]
    assert store.get("project-1", tenant_id="alpha").active_decision_id == result.decision_id


@pytest.mark.parametrize("kind", ["duplicate-snapshot", "unsupported-schema"])
def test_invalid_import_record_is_rejected_without_state_write(backend, kind):
    payload = _payload()
    if kind == "duplicate-snapshot":
        snapshot = ProcurementDecisionStore(backend=backend).save_source_snapshot(
            tenant_id="alpha", project_id="project-1", source_kind="g2b_import", payload={"source": "A"},
        )
        payload.source_snapshots = [snapshot, snapshot]
    else:
        payload.schema_version = "v999"
    with pytest.raises((ValueError, ProcurementDecisionStoreError)):
        _import(_store(backend), payload=payload)
    assert backend.read_text(PATH) is None


def test_legacy_decoder_does_not_mutate_input_and_v2_round_trips(backend):
    from app.storage.procurement_project_state import decode_project

    ProcurementDecisionStore(backend=backend).upsert(_payload())
    raw = json.loads(backend.read_text(PATH))[0]
    before = copy.deepcopy(raw)
    state = decode_project(raw, tenant_id="alpha", project_id="project-1")
    assert raw == before
    assert decode_project(state.model_dump(mode="json"), tenant_id="alpha", project_id="project-1") == state


@pytest.mark.parametrize("same_command", [False, True])
def test_concurrent_commands_use_one_cas_without_rebase(backend, monkeypatch, same_command):
    from app.storage.procurement_project_store import ProcurementProjectConflict

    store = _store(backend)
    _import(store)
    original = backend.replace_text_if_equal
    barrier = Barrier(2)
    attempts = []

    def simultaneous_write(*args, **kwargs):
        attempts.append(1)
        barrier.wait(timeout=5)
        return original(*args, **kwargs)

    monkeypatch.setattr(backend, "replace_text_if_equal", simultaneous_write)
    operation = str(uuid4())

    def run(source):
        try:
            return _import(_store(backend), source, selection=1,
                           operation=operation if same_command else str(uuid4()))
        except ProcurementProjectConflict as exc:
            return exc

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(run, ["B", "B" if same_command else "C"]))
    successes = [result for result in results if not isinstance(result, Exception)]
    assert len(successes) == (2 if same_command else 1)
    if same_command:
        assert successes[0] == successes[1]
    state = store.get("project-1", tenant_id="alpha")
    assert len(state.entries) == 2
    assert len(state.receipts) == 2
    assert state.selection_revision == 2
    assert state.active_decision_id == successes[0].decision_id
    assert len(attempts) == 2


def test_lost_replace_response_reconciles_after_another_project_write(backend, monkeypatch):
    store = _store(backend)
    _import(store)
    original = backend.replace_text_if_equal
    attempts = []

    def lost_reply(*args, **kwargs):
        attempts.append(1)
        assert original(*args, **kwargs)
        monkeypatch.setattr(backend, "replace_text_if_equal", original)
        _import(_store(backend), payload=_payload(project="other-project"))
        raise StateBackendError("response lost after another project committed")

    monkeypatch.setattr(backend, "replace_text_if_equal", lost_reply)
    operation = str(uuid4())
    result = _import(store, "B", selection=1, operation=operation)
    assert _import(store, "B", selection=1, operation=operation) == result
    assert attempts == [1]
    assert len(store.get("project-1", tenant_id="alpha").entries) == 2
    assert len(store.get("other-project", tenant_id="alpha").entries) == 1


def test_unreadable_lost_write_outcome_stops_without_retry(backend, monkeypatch):
    from app.storage.procurement_project_store import ProcurementProjectConflict

    original_read = backend.read_text
    original_write = backend.write_text_if_absent
    attempts = []

    def unreadable(*args, **kwargs):
        raise StateBackendError("read unavailable")

    def lost_reply(*args, **kwargs):
        attempts.append(1)
        assert original_write(*args, **kwargs)
        monkeypatch.setattr(backend, "read_text", unreadable)
        raise StateBackendError("response lost")

    monkeypatch.setattr(backend, "write_text_if_absent", lost_reply)
    with pytest.raises(ProcurementDecisionStoreError, match="outcome could not be verified") as raised:
        _import(_store(backend))
    assert not isinstance(raised.value, ProcurementProjectConflict)
    assert len(attempts) == 1
    assert len(json.loads(original_read(PATH))[0]["entries"]) == 1


@pytest.mark.parametrize("kind", ["path", "metadata", "evaluation-source"])
def test_source_evidence_cannot_be_rebound(backend, kind):
    legacy = ProcurementDecisionStore(backend=backend)
    snapshot = legacy.save_source_snapshot(
        tenant_id="alpha", project_id="project-1", source_kind="g2b_import", payload={"source": "A"},
    )
    payload = _payload()
    payload.source_snapshots = [snapshot]
    store = _store(backend)
    _import(store, payload=payload)
    before = backend.read_text(PATH)
    if kind == "evaluation-source":
        record = store.get("project-1", tenant_id="alpha").entries[0].record
        record.opportunity.source_id = "B"
        with pytest.raises(ProcurementDecisionStoreError):
            store.save_evaluation(record, expected_decision_revision=1, operation_id=str(uuid4()))
    else:
        if kind == "path":
            payload.source_snapshots[0].storage_path = "tenants/foreign/procurement_snapshots/project-1/x.json"
        else:
            payload.source_snapshots[0].source_label = "changed metadata"
        with pytest.raises((ValueError, ProcurementDecisionStoreError)):
            _import(store, payload=payload, selection=1, revision=1)
    assert backend.read_text(PATH) == before
