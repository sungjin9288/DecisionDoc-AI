"""Session-bound requirements API on isolated local and fake-S3 apps."""
import hashlib
import json
from uuid import uuid4

import pytest

from app.main import create_app
from tests.test_procurement_scoped_lifecycle import (
    API_HEADERS,
    _create_user,
    _login_admin,
    _ready,
    scope as scope,
)


def _url(scope, decision_id):
    return scope.base + f"/procurement/opportunities/{decision_id}/requirements"


def test_default_app_does_not_expose_requirement_mutations(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DECISIONDOC_PROVIDER", "mock")
    app = create_app()
    assert not any("/requirements" in getattr(route, "path", "") for route in app.routes)


def test_requirement_writes_require_admin_session_before_payload_validation(scope, monkeypatch):
    decision_id, _ = _ready(scope, "A", selection_revision=0)
    monkeypatch.setenv("DECISIONDOC_OPS_KEY", "local-ops-only")
    admin = _login_admin(scope.client)
    member = _create_user(scope.client, admin, "requirements-member")
    viewer = _create_user(scope.client, admin, "requirements-viewer", role="viewer")
    before = scope.backend.read_text("tenants/system/procurement_decisions.json")
    for path in (_url(scope, decision_id), _url(scope, decision_id) + f"/{uuid4()}/applicability"):
        for headers, status in (({}, 401), (API_HEADERS, 401), ({"X-DecisionDoc-Ops-Key": "local-ops-only"}, 401), (member, 403), (viewer, 403)):
            response = scope.client.post(path, json={}, headers=headers)
            assert response.status_code == status, response.text
    assert scope.backend.read_text("tenants/system/procurement_decisions.json") == before


def test_requirement_reads_require_a_session(scope):
    decision_id, _ = _ready(scope, "A", selection_revision=0)
    for headers in ({}, API_HEADERS):
        response = scope.client.get(_url(scope, decision_id), headers=headers)
        assert response.status_code == 401, response.text


def _source(scope, decision_id):
    entry = scope.app.state.procurement_opportunity_service.get_decision(
        scope.project_id, tenant_id="system", decision_id=decision_id,
    )
    snapshot = entry.record.source_snapshots[-1]
    content = scope.backend.read_bytes(snapshot.storage_path)
    raw_text = json.loads(content)["announcement"]["raw_text"]
    return {
        "snapshot_id": snapshot.snapshot_id,
        "snapshot_sha256": hashlib.sha256(content).hexdigest(),
        "quote_start": 0, "quote_end": len(raw_text), "quote": raw_text,
    }


def _create_payload(scope, decision_id, revision):
    return {
        **_source(scope, decision_id), "title": "Review this requirement",
        "category": "executive_approval_internal_readiness",
        "expected_decision_revision": revision, "operation_id": str(uuid4()),
    }


def _read(scope, decision_id, headers):
    response = scope.client.get(_url(scope, decision_id), headers=headers)
    assert response.status_code == 200, response.text
    assert response.headers["Cache-Control"] == "no-store"
    assert response.headers["X-DecisionDoc-Operational-Approval"] == "false"
    return response.json()["requirements"]


def test_admin_lifecycle_replay_audit_and_legacy_detail_privacy(scope):
    from app.storage.audit_store import AuditStore

    decision_id, revision = _ready(scope, "A", selection_revision=0)
    admin = _login_admin(scope.client)
    actor = scope.client.get("/auth/me", headers=admin).json()["user_id"]
    payload = _create_payload(scope, decision_id, revision)
    created = scope.client.post(_url(scope, decision_id), json=payload, headers=admin)
    assert created.status_code == 200, created.text
    assert created.json()["operational_approval"] is False
    requirement = _read(scope, decision_id, admin)[0]
    assert requirement["applicability"] == "unknown"
    assert requirement["created_by_actor_id"] == actor
    operation_revision = created.json()["receipt"]["decision_revision"]
    original_record = scope.app.state.procurement_opportunity_service.get_decision(
        scope.project_id, tenant_id="system", decision_id=decision_id,
    ).record.model_dump(mode="json")
    url = _url(scope, decision_id) + f"/{requirement['requirement_id']}/applicability"
    for applicability in ("applies", "not_applicable", "unknown"):
        annotation = {
            **_source(scope, decision_id), "applicability": applicability,
            "rationale": "Human review rationale", "operation_id": str(uuid4()),
            "expected_decision_revision": operation_revision,
        }
        response = scope.client.post(url, json=annotation, headers=admin)
        assert response.status_code == 200, response.text
        operation_revision = response.json()["receipt"]["decision_revision"]
        row = _read(scope, decision_id, admin)[0]
        assert row["applicability"] == applicability
        assert row["annotations"][-1]["actor_id"] == actor
    assert len(row["annotations"]) == 3
    assert scope.app.state.procurement_opportunity_service.get_decision(
        scope.project_id, tenant_id="system", decision_id=decision_id,
    ).record.model_dump(mode="json") == original_record
    replay = scope.client.post(_url(scope, decision_id), json=payload, headers=admin)
    assert replay.json() == created.json()
    assert len(_read(scope, decision_id, admin)) == 1
    legacy = scope.client.get(_url(scope, decision_id).removesuffix("/requirements"), headers=API_HEADERS)
    assert "requirement_id" not in legacy.text
    assert "created_by_actor_id" not in legacy.text
    audit = AuditStore("system", data_dir=scope.app.state.data_dir)
    entry = audit.find_latest_entry(actions=("procurement.requirement_annotate",), result="success")
    assert entry is not None
    assert entry["detail"]["procurement_decision_revision"] == operation_revision
    assert entry["session_id"] == ""
    assert "Human review rationale" not in json.dumps(entry)
    assert payload["quote"] not in json.dumps(entry)


def test_only_exact_assignee_reads_and_actor_is_redacted(scope):
    a_id, a_revision = _ready(scope, "A", selection_revision=0)
    b_id, b_revision = _ready(scope, "B", selection_revision=1)
    admin = _login_admin(scope.client)
    member = _create_user(scope.client, admin, "assigned-reader")
    outsider = _create_user(scope.client, admin, "unassigned-reader")
    assert scope.client.get(_url(scope, a_id), headers=member).status_code == 404
    packet = scope.client.post(
        scope.base + f"/procurement/review-packet?decision_id={a_id}&expected_decision_revision={a_revision}",
        json={"reviewer": "assigned-reader"}, headers=admin,
    )
    assert packet.status_code == 200, packet.text
    for decision_id, revision in ((a_id, a_revision), (b_id, b_revision)):
        created = scope.client.post(_url(scope, decision_id), json=_create_payload(scope, decision_id, revision), headers=admin)
        assert created.status_code == 200, created.text
    requirement = _read(scope, a_id, admin)[0]
    annotated = scope.client.post(
        _url(scope, a_id) + f"/{requirement['requirement_id']}/applicability",
        json={**_source(scope, a_id), "expected_decision_revision": a_revision + 1,
              "operation_id": str(uuid4()), "applicability": "applies", "rationale": "Assigned review evidence"},
        headers=admin,
    )
    assert annotated.status_code == 200, annotated.text
    row = _read(scope, a_id, member)[0]
    assert "created_by_actor_id" not in row
    assert len(row["annotations"]) == 1
    assert "actor_id" not in row["annotations"][0]
    assert row["annotations"][0]["rationale"] == "Assigned review evidence"
    assert scope.client.get(_url(scope, b_id), headers=member).status_code == 404
    assert scope.client.get(_url(scope, a_id), headers=outsider).status_code == 404
    assert scope.client.post(_url(scope, a_id), json={}, headers=member).status_code == 403


@pytest.mark.parametrize("extra", [{"actor_id": "spoof"}, {"created_at": "2030-01-01"}, {"tenant_id": "foreign"}, {"expected_decision_revision": True}])
def test_client_cannot_supply_actor_time_or_scope(scope, extra):
    decision_id, revision = _ready(scope, "A", selection_revision=0)
    admin = _login_admin(scope.client)
    before = scope.backend.read_text("tenants/system/procurement_decisions.json")
    payload = {**_create_payload(scope, decision_id, revision), **extra}
    response = scope.client.post(_url(scope, decision_id), json=payload, headers=admin)
    assert response.status_code == 422, response.text
    assert scope.backend.read_text("tenants/system/procurement_decisions.json") == before


def test_foreign_scope_stale_revision_and_corruption_fail_closed(scope):
    decision_id, revision = _ready(scope, "A", selection_revision=0)
    admin = _login_admin(scope.client)
    payload = _create_payload(scope, decision_id, revision)
    other = scope.app.state.project_store.create(tenant_id="system", name="Other")
    foreign = scope.app.state.project_store.create(tenant_id="foreign", name="Foreign")
    for project in (other, foreign):
        url = f"/projects/{project.project_id}/procurement/opportunities/{decision_id}/requirements"
        assert scope.client.post(url, json=payload, headers=admin).status_code == 404
        assert scope.client.get(url, headers=admin).status_code == 404
    stale = scope.client.post(_url(scope, decision_id), json={**payload, "expected_decision_revision": revision - 1}, headers=admin)
    assert stale.status_code == 409, stale.text
    scope.backend.write_text("tenants/system/procurement_decisions.json", "invalid-state")
    corrupted = scope.client.get(_url(scope, decision_id), headers=admin)
    assert corrupted.status_code == 503, corrupted.text
    assert "invalid-state" not in corrupted.text


def test_replay_requires_same_current_admin_and_disabled_feature_is_closed(scope):
    decision_id, revision = _ready(scope, "A", selection_revision=0)
    admin = _login_admin(scope.client)
    other_admin = _create_user(scope.client, admin, "second-admin", role="admin")
    payload = _create_payload(scope, decision_id, revision)
    first = scope.client.post(_url(scope, decision_id), json=payload, headers=admin)
    assert first.status_code == 200, first.text
    before = scope.backend.read_text("tenants/system/procurement_decisions.json")
    conflict = scope.client.post(_url(scope, decision_id), json=payload, headers=other_admin)
    assert conflict.status_code == 409, conflict.text
    assert scope.backend.read_text("tenants/system/procurement_decisions.json") == before
    scope.app.state.procurement_copilot_enabled = False
    assert scope.client.get(_url(scope, decision_id), headers=admin).status_code == 403
    assert scope.client.post(_url(scope, decision_id), json=payload, headers=admin).status_code == 403
    assert scope.backend.read_text("tenants/system/procurement_decisions.json") == before


def test_requirement_changes_invalidate_only_its_dependent_council(scope):
    a_id, a_revision = _ready(scope, "A", selection_revision=0)
    b_id, b_revision = _ready(scope, "B", selection_revision=1)
    admin = _login_admin(scope.client)
    for decision_id, revision in ((a_id, a_revision), (b_id, b_revision)):
        response = scope.client.post(
            scope.base + f"/decision-council/run?decision_id={decision_id}&expected_decision_revision={revision}",
            json={"goal": "Review source", "context": "", "constraints": ""}, headers=API_HEADERS,
        )
        assert response.status_code == 200, response.text
        assert response.json()["current_procurement_binding_status"] == "current"
    created = scope.client.post(_url(scope, a_id), json=_create_payload(scope, a_id, a_revision), headers=admin)
    assert created.status_code == 200, created.text
    for decision_id, revision, expected in ((a_id, a_revision + 1, "stale"), (b_id, b_revision, "current")):
        response = scope.client.get(
            scope.base + f"/decision-council?decision_id={decision_id}&expected_decision_revision={revision}",
            headers=API_HEADERS,
        )
        assert response.status_code == 200, response.text
        assert response.json()["current_procurement_binding_status"] == expected


def test_raw_source_change_invalidates_read_but_replay_preserves_original_receipt(scope, monkeypatch):
    from app.storage.state_backend import StateBackendError

    decision_id, revision = _ready(scope, "A", selection_revision=0)
    admin = _login_admin(scope.client)
    create_payload = _create_payload(scope, decision_id, revision)
    created = scope.client.post(_url(scope, decision_id), json=create_payload, headers=admin)
    assert created.status_code == 200, created.text
    requirement = _read(scope, decision_id, admin)[0]
    annotate_url = _url(scope, decision_id) + f"/{requirement['requirement_id']}/applicability"
    payload = {**_source(scope, decision_id), "expected_decision_revision": revision + 1,
               "operation_id": str(uuid4()), "applicability": "applies", "rationale": "Original source review"}
    annotated = scope.client.post(annotate_url, json=payload, headers=admin)
    assert annotated.status_code == 200, annotated.text
    original = _read(scope, decision_id, admin)[0]
    entry = scope.app.state.procurement_opportunity_service.get_decision(
        scope.project_id, tenant_id="system", decision_id=decision_id,
    )
    path = entry.record.source_snapshots[-1].storage_path
    scope.backend.write_text(path, json.dumps({"announcement": {"raw_text": "Changed source"}}))
    changed = _read(scope, decision_id, admin)[0]
    assert changed["applicability"] == "unknown"
    assert changed["stale"] is True
    assert changed["annotations"] == original["annotations"]
    before = scope.backend.read_text("tenants/system/procurement_decisions.json")
    replay = scope.client.post(annotate_url, json=payload, headers=admin)
    assert replay.status_code == 200, replay.text
    assert replay.json() == annotated.json()
    assert scope.backend.read_text("tenants/system/procurement_decisions.json") == before
    read_bytes = scope.backend.read_bytes

    def unavailable(storage_path):
        if storage_path == path:
            raise StateBackendError("private backend detail")
        return read_bytes(storage_path)

    monkeypatch.setattr(scope.backend, "read_bytes", unavailable)
    failed = scope.client.get(_url(scope, decision_id), headers=admin)
    assert failed.status_code == 503, failed.text
    assert "private backend detail" not in failed.text
    assert scope.backend.read_text("tenants/system/procurement_decisions.json") == before
