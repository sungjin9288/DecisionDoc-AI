"""Reopen persisted fixture data across legacy and opt-in app instances."""
from contextlib import contextmanager
import json
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.schemas import ProcurementDecisionUpsert
from app.services.procurement_decision_package.review_packet import verify_procurement_review_packet
from app.storage.state_backend import LocalStateBackend
from scripts.procurement_transition_preflight import inspect_state
from tests.test_procurement_applicability_lifecycle import _packet, _complete
from tests.test_procurement_multi_opportunity import _payload
from tests.test_procurement_review_authorization import _login_existing, _ready_project
from tests.test_procurement_scoped_lifecycle import API_HEADERS, _create_user, _login_admin
from tests.test_procurement_review_store import _MemoryS3Client, _s3_backend


STATE_PATH = "tenants/system/procurement_decisions.json"


@pytest.fixture(params=["local", "fake-s3"])
def reopen(request, tmp_path, monkeypatch):
    root = tmp_path / "fixture-app"
    monkeypatch.setenv("DATA_DIR", str(root))
    monkeypatch.setenv("DECISIONDOC_PROVIDER", "mock")
    monkeypatch.setenv("DECISIONDOC_STORAGE", "local")
    monkeypatch.setenv("DECISIONDOC_API_KEY", "test-key")
    monkeypatch.setenv("DECISIONDOC_PROCUREMENT_COPILOT_ENABLED", "1")
    client = _MemoryS3Client()

    def backend(*, data_dir):
        return LocalStateBackend(data_dir) if request.param == "local" else _s3_backend(client)

    monkeypatch.setattr("app.main.get_state_backend", backend)

    @contextmanager
    def start(enabled):
        app = create_app(procurement_multi_opportunity_enabled=enabled)
        with TestClient(app) as http:
            yield SimpleNamespace(app=app, client=http, backend=app.state.state_backend)

    return start


def _scope(app, project_id):
    return SimpleNamespace(**vars(app), project_id=project_id, base=f"/projects/{project_id}")


def _legacy_packet(scope, headers, reviewer="scoped-admin"):
    response = scope.client.post(scope.base + "/procurement/review-packet",
                                 json={"reviewer": reviewer}, headers=headers)
    assert response.status_code == 200, response.text
    assert verify_procurement_review_packet(response.content)["schema_version"].endswith(".v1")
    return response


def _saved_evidence(backend):
    paths = backend.list_prefix("tenants/system/procurement_reviews")
    paths += backend.list_prefix("tenants/system/procurement_snapshots")
    return {path: backend.read_bytes(path) for path in paths}


def _attach_source(app, project_id):
    store = app.app.state.procurement_store
    record = store.get(project_id, tenant_id="system")
    snapshot = store.save_source_snapshot(
        tenant_id="system", project_id=project_id, source_kind="g2b_import",
        payload={"announcement": {"raw_text": "Fixture source for transition"}},
    )
    payload = record.model_dump(mode="json", exclude={"decision_id", "created_at", "updated_at"})
    payload["source_snapshots"] = [snapshot.model_dump(mode="json")]
    return store.upsert(ProcurementDecisionUpsert.model_validate(payload))


def test_transition_reopen_preserves_completed_bytes_and_pending_legacy_reviews(reopen):
    with reopen(False) as old:
        admin = _login_admin(old.client)
        _create_user(old.client, admin, "pending-reviewer")
        _create_user(old.client, admin, "outsider")
        project_id = _ready_project(old.client, admin, name="Transition A")
        other_id = _ready_project(old.client, admin, name="Untouched project")
        original = _attach_source(old, project_id)
        first = _scope(old, project_id)
        completed_packet = _legacy_packet(first, admin)
        completed = _complete(first, completed_packet, admin)
        assert completed.status_code == 200, completed.text
        pending = _legacy_packet(first, admin, "pending-reviewer")
        other_pending = _legacy_packet(_scope(old, other_id), admin)
        before_state = old.backend.read_bytes(STATE_PATH)
        before_evidence = _saved_evidence(old.backend)
        before_rows = json.loads(before_state)

    with reopen(True) as enabled:
        first = _scope(enabled, project_id)
        admin = _login_existing(enabled.client, "scoped-admin")
        assert enabled.backend.read_bytes(STATE_PATH) == before_state
        assert _saved_evidence(enabled.backend) == before_evidence
        projection = enabled.client.get(first.base + "/procurement/opportunities", headers=API_HEADERS)
        assert projection.status_code == 200, projection.text
        assert projection.json()["items"][0]["decision_id"] == original.decision_id
        assert enabled.backend.read_bytes(STATE_PATH) == before_state
        selection = {"decision_id": original.decision_id, "expected_selection_revision": 0,
                     "operation_id": str(uuid4())}
        selected = enabled.client.post(first.base + "/procurement/selection", json=selection, headers=API_HEADERS)
        assert selected.status_code == 200, selected.text
        store = enabled.app.state.procurement_opportunity_store
        new = store.import_opportunity(
            _payload("B", project=project_id, tenant="system"), expected_selection_revision=0,
            expected_decision_revision=0, operation_id=str(uuid4()),
        )
        aggregate = store.get(project_id, tenant_id="system")
        assert aggregate.entries[0].record == original
        assert aggregate.active_decision_id == new.decision_id
        after_rows = json.loads(enabled.backend.read_text(STATE_PATH))
        assert next(row for row in after_rows if row["project_id"] == other_id) == next(
            row for row in before_rows if row["project_id"] == other_id
        )
        assert _saved_evidence(enabled.backend) == before_evidence
        after_state = enabled.backend.read_bytes(STATE_PATH)
        assert inspect_state(after_state, tenant_id="system")["legacy_reader_compatible"] is False

    with reopen(True) as restarted:
        first = _scope(restarted, project_id)
        admin = _login_existing(restarted.client, "scoped-admin")
        reviewer = _login_existing(restarted.client, "pending-reviewer")
        outsider = _login_existing(restarted.client, "outsider")
        assert restarted.backend.read_bytes(STATE_PATH) == after_state
        assert _saved_evidence(restarted.backend) == before_evidence
        replay = restarted.client.post(first.base + "/procurement/selection", json=selection, headers=API_HEADERS)
        assert replay.json() == selected.json()
        assert restarted.backend.read_bytes(STATE_PATH) == after_state
        assert _complete(first, completed_packet, admin).content == completed.content
        for packet in (completed_packet, pending):
            sha = packet.headers["X-DecisionDoc-Packet-SHA256"]
            download = restarted.client.get(first.base + f"/procurement/reviews/{sha}/packet", headers=admin)
            assert download.status_code == 200, download.text
            assert download.content == packet.content
        assert _saved_evidence(restarted.backend) == before_evidence
        assert _complete(first, pending, outsider).status_code == 409
        assert _complete(first, pending, API_HEADERS).status_code == 401
        assert _saved_evidence(restarted.backend) == before_evidence
        # Another project's first v2 write must not strand this v1 review.
        other_done = _complete(_scope(restarted, other_id), other_pending, admin)
        assert other_done.status_code == 200, other_done.text
        # Selection B must not substitute for the original A packet.
        pending_done = _complete(first, pending, reviewer)
        assert pending_done.status_code == 200, pending_done.text
        assert _complete(first, pending, reviewer).content == pending_done.content
        assert restarted.backend.read_bytes(STATE_PATH) == after_state


@pytest.mark.parametrize("change_source", [False, True])
def test_bound_pending_packet_rechecks_sources_after_reopen(reopen, change_source):
    with reopen(False) as old:
        admin = _login_admin(old.client)
        project_id = _ready_project(old.client, admin, name="Source restart")
        original = _attach_source(old, project_id)
    with reopen(True) as enabled:
        scope = _scope(enabled, project_id)
        admin = _login_existing(enabled.client, "scoped-admin")
        packet = _packet(scope, original.decision_id, 1, admin)
        assert packet.status_code == 200, packet.text
        assert verify_procurement_review_packet(packet.content)["schema_version"].endswith(".v3")
        review_bytes = _saved_evidence(enabled.backend)
        if change_source:
            enabled.backend.write_text(original.source_snapshots[0].storage_path,
                                       '{"announcement":{"raw_text":"changed"}}')
    with reopen(True) as restarted:
        scope = _scope(restarted, project_id)
        admin = _login_existing(restarted.client, "scoped-admin")
        result = _complete(scope, packet, admin)
        assert result.status_code == (409 if change_source else 200), result.text
        if change_source:
            for path, content in review_bytes.items():
                if "/procurement_reviews/" in path:
                    assert restarted.backend.read_bytes(path) == content
        else:
            assert _complete(scope, packet, admin).content == result.content


@pytest.mark.parametrize("mode", [
    "changed_before", "changed_during", "unavailable_before", "unavailable_during",
    "missing_before", "missing_during", "replaced_before", "replaced_during",
])
def test_legacy_completion_fails_closed_on_changed_or_unavailable_state(reopen, monkeypatch, mode):
    with reopen(False) as old:
        admin = _login_admin(old.client)
        project_id = _ready_project(old.client, admin, name="Legacy guard")
        packet = _legacy_packet(_scope(old, project_id), admin)
    with reopen(True) as restarted:
        scope = _scope(restarted, project_id)
        admin = _login_existing(restarted.client, "scoped-admin")
        store = restarted.app.state.procurement_opportunity_store
        project = store.get(project_id, tenant_id="system")
        store.select(project_id, tenant_id="system", decision_id=project.active_decision_id,
                     expected_selection_revision=0, operation_id=str(uuid4()))
        before = _saved_evidence(restarted.backend)

        def alter_source():
            if mode.startswith("unavailable"):
                restarted.backend.write_text(STATE_PATH, "[")
            else:
                rows = json.loads(restarted.backend.read_text(STATE_PATH))
                if mode.startswith("missing"):
                    rows[0].update(entries=[], receipts=[], active_decision_id=None)
                elif mode.startswith("replaced"):
                    replacement = str(uuid4())
                    rows[0]["entries"][0]["record"]["decision_id"] = replacement
                    rows[0]["active_decision_id"] = replacement
                    for receipt in rows[0]["receipts"]:
                        receipt["decision_id"] = replacement
                else:
                    rows[0]["entries"][0]["record"]["opportunity"]["title"] = "Changed during review"
                restarted.backend.write_text(STATE_PATH, json.dumps(rows))

        if mode.endswith("before"):
            alter_source()
        else:
            from app.services.procurement_decision_package import reviewed_package
            build = reviewed_package.build_procurement_reviewed_package

            def build_then_change(*args, **kwargs):
                package = build(*args, **kwargs)
                alter_source()
                return package

            monkeypatch.setattr(reviewed_package, "build_procurement_reviewed_package", build_then_change)
        response = _complete(scope, packet, admin)
        expected = 503 if mode.startswith("unavailable") else 409
        assert response.status_code == expected, response.text
        code = "procurement_review_source_changed"
        if expected == 503:
            code = "procurement_source_unavailable"
        elif mode in {"missing_before", "replaced_before"}:
            code = "procurement_review_source_missing"
        assert response.json()["detail"]["code"] == code
        assert _saved_evidence(restarted.backend) == before
