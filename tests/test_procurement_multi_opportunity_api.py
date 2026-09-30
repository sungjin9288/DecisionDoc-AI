"""Scoped procurement API, mounted only in isolated test applications."""
import json
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.schemas import NormalizedProcurementOpportunity, ProcurementDecisionUpsert
from app.services.procurement_decision_service import ProcurementDecisionService
from app.storage.procurement_project_store import ProcurementProjectStore
from app.storage.procurement_store import ProcurementDecisionStore
from tests.test_procurement_store_integrity import _s3_backend


HEADERS = {"X-DecisionDoc-Api-Key": "test-key"}


@pytest.fixture(params=["local", "fake-s3"])
def scope(request, tmp_path, monkeypatch):
    from app.routers.projects.procurement_opportunities import router
    from app.services.procurement_opportunity_service import ProcurementOpportunityService

    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DECISIONDOC_PROVIDER", "mock")
    monkeypatch.setenv("DECISIONDOC_STORAGE", "local")
    monkeypatch.setenv("DECISIONDOC_API_KEY", "test-key")
    monkeypatch.setenv("DECISIONDOC_PROCUREMENT_COPILOT_ENABLED", "1")
    app = create_app()
    backend = app.state.state_backend if request.param == "local" else _s3_backend()[0]
    legacy = ProcurementDecisionStore(backend=backend)
    store = ProcurementProjectStore(backend=backend)
    evaluator = ProcurementDecisionService(
        procurement_store=legacy, data_dir=str(tmp_path), state_backend=backend,
        now_provider=lambda: datetime(2030, 1, 1, tzinfo=timezone.utc),
    )
    service = ProcurementOpportunityService(store=store, evaluator=evaluator)
    app.state.procurement_opportunity_service = service
    app.include_router(router)
    project = app.state.project_store.create(tenant_id="system", name="Two opportunities")
    with TestClient(app) as client:
        yield SimpleNamespace(client=client, app=app, backend=backend, store=store, legacy=legacy,
                              evaluator=evaluator, service=service, project=project.project_id,
                              url=f"/projects/{project.project_id}/procurement")


def _import(scope, source="A", *, selection=0, revision=0, project=None):
    return scope.store.import_opportunity(
        ProcurementDecisionUpsert(
            project_id=project or scope.project, tenant_id="system", notes="private operator note",
            opportunity=NormalizedProcurementOpportunity(
                source_kind="g2b", source_id=source, title=source,
                raw_text_preview="private source body", deadline="2031-01-01",
            ),
        ),
        expected_selection_revision=selection, expected_decision_revision=revision,
        operation_id=str(uuid4()),
    )


def _command(revision=1):
    return {"expected_decision_revision": revision, "operation_id": str(uuid4())}


def _bytes(scope):
    return scope.backend.read_text("tenants/system/procurement_decisions.json")


def test_list_and_detail_are_scoped_paginated_and_read_only(scope):
    a = _import(scope)
    b = _import(scope, "B", selection=1)
    before = _bytes(scope)
    response = scope.client.get(scope.url + "/opportunities?limit=1&offset=0", headers=HEADERS)
    assert response.status_code == 200
    body = response.json()
    assert body["active_decision_id"] == b.decision_id
    assert body["selection_revision"] == 2
    assert body["total"] == 2
    assert len(body["items"]) == 1
    assert body["items"][0]["decision_id"] == a.decision_id
    assert "private" not in response.text
    detail = scope.client.get(scope.url + f"/opportunities/{a.decision_id}", headers=HEADERS)
    assert detail.status_code == 200
    assert detail.json()["decision"]["opportunity"]["source_id"] == "A"
    assert detail.json()["decision_revision"] == 1
    assert _bytes(scope) == before


def test_empty_listing_does_not_migrate_or_create_state(scope):
    response = scope.client.get(scope.url + "/opportunities", headers=HEADERS)
    assert response.status_code == 200
    assert response.json()["items"] == []
    assert response.json()["active_decision_id"] is None
    assert _bytes(scope) is None


def test_select_and_replay_return_original_receipt_after_another_selection(scope):
    a = _import(scope)
    b = _import(scope, "B", selection=1)
    payload = {"decision_id": a.decision_id, "expected_selection_revision": 2, "operation_id": str(uuid4())}
    first = scope.client.post(scope.url + "/selection", json=payload, headers=HEADERS)
    assert first.status_code == 200
    scope.store.select(scope.project, tenant_id="system", decision_id=b.decision_id,
                       expected_selection_revision=3, operation_id=str(uuid4()))
    before = _bytes(scope)
    again = scope.client.post(scope.url + "/selection", json=payload, headers=HEADERS)
    assert again.json() == first.json()
    assert _bytes(scope) == before
    assert scope.store.get(scope.project, tenant_id="system").active_decision_id == b.decision_id


@pytest.mark.parametrize("action", ["evaluate", "recommend"])
def test_scoped_calculation_is_one_write_and_replay_skips_calculation(scope, monkeypatch, action):
    a = _import(scope)
    _import(scope, "B", selection=1)
    before_b = scope.store.get(scope.project, tenant_id="system").entries[1].model_dump()
    payload = _command()
    url = scope.url + f"/opportunities/{a.decision_id}/{action}"
    first = scope.client.post(url, json=payload, headers=HEADERS)
    assert first.status_code == 200
    assert first.json()["receipt"]["decision_revision"] == 2
    after = scope.store.get(scope.project, tenant_id="system")
    assert after.entries[1].model_dump() == before_b
    assert after.active_decision_id == before_b["record"]["decision_id"]
    assert len(after.receipts) == 3
    assert bool(after.entries[0].record.recommendation) == (action == "recommend")

    # Replay is the original command receipt, not a recalculation against newer state.
    _import(scope, selection=2, revision=2)
    before = _bytes(scope)
    def forbidden(*args, **kwargs):
        raise AssertionError("replayed request recalculated")
    monkeypatch.setattr(scope.evaluator, "evaluate_record", forbidden)
    replay = scope.client.post(url, json=payload, headers=HEADERS)
    assert replay.status_code == 200
    assert replay.json() == first.json()
    assert _bytes(scope) == before
    changed = scope.client.post(url, json={**payload, "expected_decision_revision": 3}, headers=HEADERS)
    assert changed.status_code == 409


def test_selection_race_rejects_evaluation_without_overwriting_b(scope, monkeypatch):
    a = _import(scope)
    b = _import(scope, "B", selection=1)
    scope.store.select(scope.project, tenant_id="system", decision_id=a.decision_id,
                       expected_selection_revision=2, operation_id=str(uuid4()))
    original = scope.evaluator.evaluate_record
    def select_during_evaluation(record):
        result = original(record)
        scope.store.select(scope.project, tenant_id="system", decision_id=b.decision_id,
                           expected_selection_revision=3, operation_id=str(uuid4()))
        return result
    monkeypatch.setattr(scope.evaluator, "evaluate_record", select_during_evaluation)
    response = scope.client.post(scope.url + f"/opportunities/{a.decision_id}/evaluate",
                                 json=_command(), headers=HEADERS)
    # Aggregate CAS cannot silently rebase even when only the selection changed.
    assert response.status_code == 409
    state = scope.store.get(scope.project, tenant_id="system")
    assert state.active_decision_id == b.decision_id
    assert state.entries[0].decision_revision == 1


@pytest.mark.parametrize("payload", [
    {"expected_decision_revision": True}, {"expected_decision_revision": -1},
    {"expected_decision_revision": "1"}, {"operation_id": "not-a-uuid"},
    {"extra": "forbidden"}, {"tenant_id": "foreign"},
])
def test_invalid_commands_are_422_and_do_not_write(scope, payload):
    a = _import(scope)
    before = _bytes(scope)
    response = scope.client.post(scope.url + f"/opportunities/{a.decision_id}/evaluate",
                                 json={**_command(), **payload}, headers=HEADERS)
    assert response.status_code == 422
    assert _bytes(scope) == before


@pytest.mark.parametrize("query", ["limit=0", "limit=101", "offset=-1"])
def test_invalid_pagination_is_rejected(scope, query):
    assert scope.client.get(scope.url + "/opportunities?" + query, headers=HEADERS).status_code == 422


def test_missing_ids_and_foreign_project_are_not_found(scope):
    foreign = scope.app.state.project_store.create(tenant_id="foreign", name="Other tenant")
    a = _import(scope)
    other = scope.app.state.project_store.create(tenant_id="system", name="Other project")
    assert scope.client.get(scope.url + f"/opportunities/{uuid4()}", headers=HEADERS).status_code == 404
    assert scope.client.get(f"/projects/{foreign.project_id}/procurement/opportunities", headers=HEADERS).status_code == 404
    assert scope.client.get(f"/projects/{other.project_id}/procurement/opportunities/{a.decision_id}", headers=HEADERS).status_code == 404
    assert scope.client.get(scope.url + "/opportunities/not-a-uuid", headers=HEADERS).status_code == 422


def test_stale_command_and_corrupt_storage_fail_closed(scope):
    a = _import(scope)
    before = _bytes(scope)
    response = scope.client.post(scope.url + f"/opportunities/{a.decision_id}/recommend",
                                 json=_command(0), headers=HEADERS)
    assert response.status_code == 409
    assert _bytes(scope) == before
    scope.backend.write_text("tenants/system/procurement_decisions.json", "not-json")
    failed = scope.client.get(scope.url + "/opportunities", headers=HEADERS)
    assert failed.status_code == 503
    assert "not-json" not in failed.text
    assert _bytes(scope) == "not-json"


def test_disabled_feature_and_missing_key_do_not_write(scope):
    _import(scope)
    before = _bytes(scope)
    assert scope.client.get(scope.url + "/opportunities").status_code == 401
    scope.app.state.procurement_copilot_enabled = False
    assert scope.client.get(scope.url + "/opportunities", headers=HEADERS).status_code == 403
    assert _bytes(scope) == before


def test_legacy_mutation_requires_explicit_id_when_multiple_opportunities(scope):
    _import(scope)
    _import(scope, "B", selection=1)
    before = _bytes(scope)
    for action in ("evaluate", "recommend"):
        response = scope.client.post(scope.url + "/" + action, headers=HEADERS)
        assert response.status_code == 409
        assert response.json()["detail"]["code"] == "procurement_opportunity_selection_required"
    assert _bytes(scope) == before


def test_single_opportunity_legacy_evaluate_and_recommend_still_work(scope):
    a = _import(scope)
    for action in ("evaluate", "recommend"):
        response = scope.client.post(scope.url + "/" + action, headers=HEADERS)
        assert response.status_code == 200
        assert response.json()["decision"]["decision_id"] == a.decision_id
    state = scope.store.get(scope.project, tenant_id="system")
    assert state.entries[0].decision_revision == 3
    assert state.entries[0].record.recommendation is not None


def test_scoped_audit_binds_receipt_and_conflict_without_source_body(scope):
    from app.storage.audit_store import AuditStore

    a = _import(scope)
    payload = _command()
    url = scope.url + f"/opportunities/{a.decision_id}/evaluate"
    response = scope.client.post(url, json=payload, headers=HEADERS)
    assert response.status_code == 200
    receipt = response.json()["receipt"]
    audit = AuditStore("system", data_dir=scope.app.state.data_dir)
    entry = audit.find_latest_entry(actions=("procurement.evaluate",), result="success")
    assert entry is not None
    for field in ("decision_id", "decision_revision", "selection_revision", "operation_id", "request_sha256"):
        assert entry["detail"]["procurement_" + field] == receipt[field]
    assert "private" not in json.dumps(entry)
    stale = _command(0)
    assert scope.client.post(url, json=stale, headers=HEADERS).status_code == 409
    failed = audit.find_latest_entry(actions=("procurement.evaluate",), result="failure")
    assert failed is not None
    assert failed["detail"]["procurement_decision_id"] == a.decision_id
    assert failed["detail"]["procurement_operation_id"] == stale["operation_id"]
    assert failed["detail"]["procurement_expected_decision_revision"] == 0
    assert "procurement_decision_revision" not in failed["detail"]


def test_viewer_cannot_write_even_with_global_key_and_member_can_evaluate(scope):
    from app.services.auth_service import issue_auth_token_pair
    from app.storage.user_store import get_user_store

    a = _import(scope)
    users = get_user_store("system", data_dir=scope.app.state.data_dir, backend=scope.app.state.state_backend)
    users.create_first_admin(username="admin", display_name="Admin", email="admin@example.test", password="Password123!")
    before = _bytes(scope)
    for role in ("viewer", "member"):
        user = users.create(username=role, display_name=role, email=f"{role}@example.test",
                            password="Password123!", role=role)
        tokens = issue_auth_token_pair(user, data_dir=scope.app.state.data_dir, backend=scope.app.state.state_backend)
        headers = {**HEADERS, "Authorization": f"Bearer {tokens['access_token']}"}
        assert scope.client.get(scope.url + "/opportunities", headers=headers).status_code == 200
        response = scope.client.post(scope.url + f"/opportunities/{a.decision_id}/evaluate",
                                     json=_command(), headers=headers)
        assert response.status_code == (403 if role == "viewer" else 200)
        if role == "viewer":
            assert _bytes(scope) == before
        forged = scope.client.get(scope.url + "/opportunities", headers={**headers, "X-Tenant-ID": "foreign"})
        assert forged.status_code == 403


def test_record_calculations_do_not_write_or_mutate_input(scope):
    a = _import(scope)
    original = scope.service.get_decision(scope.project, tenant_id="system", decision_id=a.decision_id).record
    before_record, before_bytes = original.model_dump(), _bytes(scope)
    for compute in (scope.evaluator.evaluate_record, scope.evaluator.recommend_record):
        result = compute(original)
        assert result.decision_id == a.decision_id
        assert result.hard_filters
        assert original.model_dump() == before_record
        assert _bytes(scope) == before_bytes


def test_default_factory_does_not_activate_scoped_api(scope):
    app = create_app()
    assert not hasattr(app.state, "procurement_opportunity_service")
    assert not any("/procurement/opportunities" in getattr(route, "path", "") for route in app.routes)
    with TestClient(app) as client:
        assert client.get(scope.url + "/opportunities", headers=HEADERS).status_code == 404


def test_legacy_get_projects_active_record_and_selection_revision(scope):
    _import(scope)
    b = _import(scope, "B", selection=1)
    before = _bytes(scope)
    response = scope.client.get(scope.url, headers=HEADERS)
    assert response.status_code == 200
    assert response.json()["decision"]["decision_id"] == b.decision_id
    assert response.json()["active_decision_id"] == b.decision_id
    assert response.json()["selection_revision"] == 2
    assert _bytes(scope) == before


def test_evaluation_uses_a_snapshot_while_b_is_selected(scope):
    snapshot = scope.legacy.save_source_snapshot(
        tenant_id="system", project_id=scope.project, source_kind="g2b_import",
        payload={"extracted_fields": {"deadline": "2020-01-01"}},
    )
    a = scope.legacy.upsert(ProcurementDecisionUpsert(
        tenant_id="system", project_id=scope.project, source_snapshots=[snapshot],
        opportunity=NormalizedProcurementOpportunity(source_kind="g2b", source_id="A", title="A"),
    ))
    b = _import(scope, "B")
    response = scope.client.post(scope.url + f"/opportunities/{a.decision_id}/recommend",
                                 json=_command(), headers=HEADERS)
    assert response.status_code == 200
    state = scope.store.get(scope.project, tenant_id="system")
    assert state.active_decision_id == b.decision_id
    assert state.entries[0].record.recommendation.value == "NO_GO"
    assert any(item.code == "impossible_deadline" and item.status == "fail"
               for item in state.entries[0].record.hard_filters)
    assert not state.entries[1].record.hard_filters


def test_source_revision_race_preserves_refreshed_record(scope, monkeypatch):
    a = _import(scope)
    original = scope.evaluator.evaluate_record
    def refresh_during_evaluation(record):
        result = original(record)
        _import(scope, selection=1, revision=1)
        return result
    monkeypatch.setattr(scope.evaluator, "evaluate_record", refresh_during_evaluation)
    response = scope.client.post(scope.url + f"/opportunities/{a.decision_id}/evaluate",
                                 json=_command(), headers=HEADERS)
    assert response.status_code == 409
    entry = scope.store.get(scope.project, tenant_id="system").entries[0]
    assert entry.decision_revision == 2
    assert not entry.record.hard_filters


@pytest.mark.parametrize("field,value", [
    ("decision_id", str(uuid4())), ("tenant_id", "foreign"), ("project_id", str(uuid4())),
])
def test_calculation_cannot_change_record_identity(scope, monkeypatch, field, value):
    a = _import(scope)
    before = _bytes(scope)
    monkeypatch.setattr(scope.evaluator, "evaluate_record", lambda record: record.model_copy(update={field: value}))
    response = scope.client.post(scope.url + f"/opportunities/{a.decision_id}/evaluate",
                                 json=_command(), headers=HEADERS)
    assert response.status_code == 409
    assert _bytes(scope) == before


def test_lost_api_storage_reply_does_not_recalculate(scope, monkeypatch):
    from app.storage.state_backend import StateBackendError

    a = _import(scope)
    original_write = scope.backend.replace_text_if_equal
    original_compute = scope.evaluator.evaluate_record
    calculations = []
    def calculate(record):
        calculations.append(record.decision_id)
        return original_compute(record)
    def lost_reply(*args, **kwargs):
        assert original_write(*args, **kwargs)
        raise StateBackendError("lost reply")
    monkeypatch.setattr(scope.evaluator, "evaluate_record", calculate)
    monkeypatch.setattr(scope.backend, "replace_text_if_equal", lost_reply)
    payload = _command()
    url = scope.url + f"/opportunities/{a.decision_id}/evaluate"
    response = scope.client.post(url, json=payload, headers=HEADERS)
    assert response.status_code == 200
    assert scope.client.post(url, json=payload, headers=HEADERS).json() == response.json()
    assert calculations == [a.decision_id]
