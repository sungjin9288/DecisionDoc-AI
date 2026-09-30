"""Opt-in HTTP lifecycle for decision-scoped procurement work."""
from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.services.g2b_collector import G2BAnnouncement
from app.services.procurement_decision_package.review_packet import (
    verify_procurement_review_packet,
)
from app.storage.state_backend import LocalStateBackend
from tests.test_procurement_store_integrity import _s3_backend


API_HEADERS = {"X-DecisionDoc-Api-Key": "test-key"}


@pytest.fixture(params=["local", "fake-s3"])
def scope(request, tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "app"))
    monkeypatch.setenv("DECISIONDOC_PROVIDER", "mock")
    monkeypatch.setenv("DECISIONDOC_STORAGE", "local")
    monkeypatch.setenv("DECISIONDOC_API_KEY", "test-key")
    monkeypatch.setenv("DECISIONDOC_PROCUREMENT_COPILOT_ENABLED", "1")
    backend = (
        LocalStateBackend(tmp_path / "scoped")
        if request.param == "local"
        else _s3_backend()[0]
    )
    app = create_app(
        procurement_multi_opportunity_enabled=True,
        procurement_multi_opportunity_backend=backend,
    )
    project = app.state.project_store.create(
        tenant_id="system",
        name="Scoped lifecycle",
    )
    calls: list[str] = []

    async def fetch_announcement_detail(url_or_number: str, api_key: str = ""):
        _ = api_key
        calls.append(url_or_number)
        return G2BAnnouncement(
            bid_number=url_or_number,
            title=f"Opportunity {url_or_number}",
            issuer="DecisionDoc",
            budget="1000000",
            announcement_date="2030-01-01",
            deadline="2030-12-31",
            bid_type="service",
            category="service",
            detail_url=f"https://example.test/{url_or_number}",
            attachments=[],
            raw_text=f"Exact source bytes for {url_or_number}",
            source="api",
        )

    monkeypatch.setattr(
        "app.services.g2b_collector.fetch_announcement_detail",
        fetch_announcement_detail,
    )
    with TestClient(app) as client:
        yield SimpleNamespace(
            app=app,
            backend=backend,
            client=client,
            project_id=project.project_id,
            calls=calls,
            base=f"/projects/{project.project_id}",
        )


def _import_payload(source: str, *, selection_revision: int) -> dict:
    return {
        "url_or_number": source,
        "parsed_rfp_fields": {},
        "structured_context": f"Context {source}",
        "notes": "",
        "expected_selection_revision": selection_revision,
        "expected_decision_revision": 0,
        "operation_id": str(uuid4()),
    }


def _import(scope, source: str, *, selection_revision: int) -> dict:
    response = scope.client.post(
        scope.base + "/imports/g2b-opportunity",
        json=_import_payload(source, selection_revision=selection_revision),
        headers=API_HEADERS,
    )
    assert response.status_code == 200, response.text
    return response.json()


def _calculate(scope, decision_id: str, action: str, revision: int) -> int:
    response = scope.client.post(
        scope.base + f"/procurement/opportunities/{decision_id}/{action}",
        json={
            "expected_decision_revision": revision,
            "operation_id": str(uuid4()),
        },
        headers=API_HEADERS,
    )
    assert response.status_code == 200, response.text
    return response.json()["receipt"]["decision_revision"]


def _ready(scope, source: str, *, selection_revision: int) -> tuple[str, int]:
    imported = _import(scope, source, selection_revision=selection_revision)
    decision_id = imported["receipt"]["decision_id"]
    revision = _calculate(scope, decision_id, "evaluate", 1)
    revision = _calculate(scope, decision_id, "recommend", revision)
    return decision_id, revision


def _login_admin(client: TestClient, username: str = "scoped-admin") -> dict[str, str]:
    registered = client.post(
        "/auth/register",
        json={
            "username": username,
            "display_name": username,
            "email": f"{username}@example.test",
            "password": "Password123!",
            "role": "admin",
        },
    )
    assert registered.status_code == 200, registered.text
    logged_in = client.post(
        "/auth/login",
        json={"username": username, "password": "Password123!"},
    )
    assert logged_in.status_code == 200, logged_in.text
    return {"Authorization": f"Bearer {logged_in.json()['access_token']}"}


def _create_user(
    client: TestClient,
    admin_headers: dict[str, str],
    username: str,
    *,
    role: str = "member",
) -> dict[str, str]:
    created = client.post(
        "/admin/users",
        headers=admin_headers,
        json={
            "username": username,
            "display_name": username,
            "email": f"{username}@example.test",
            "password": "Password123!",
            "role": role,
        },
    )
    assert created.status_code == 200, created.text
    logged_in = client.post(
        "/auth/login",
        json={"username": username, "password": "Password123!"},
    )
    assert logged_in.status_code == 200, logged_in.text
    return {"Authorization": f"Bearer {logged_in.json()['access_token']}"}


def test_default_factory_keeps_scoped_lifecycle_disabled(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DECISIONDOC_PROVIDER", "mock")
    monkeypatch.setenv("DECISIONDOC_STORAGE", "local")
    monkeypatch.setenv("DECISIONDOC_API_KEY", "test-key")
    app = create_app()
    assert not hasattr(app.state, "procurement_opportunity_service")
    assert not any(
        getattr(route, "path", "").endswith("/procurement/opportunities")
        for route in app.routes
    )


def test_opt_in_import_replays_without_collector_or_v1_mutation(scope):
    payload = _import_payload("A", selection_revision=0)
    first = scope.client.post(
        scope.base + "/imports/g2b-opportunity",
        json=payload,
        headers=API_HEADERS,
    )
    assert first.status_code == 200, first.text
    before = scope.backend.read_text("tenants/system/procurement_decisions.json")
    replay = scope.client.post(
        scope.base + "/imports/g2b-opportunity",
        json=payload,
        headers=API_HEADERS,
    )
    assert replay.status_code == 200
    assert replay.json() == {
        "project_id": scope.project_id,
        "operation": "replayed",
        "project_name": "Scoped lifecycle",
        "receipt": first.json()["receipt"],
    }
    assert scope.calls == ["A"]
    assert scope.backend.read_text("tenants/system/procurement_decisions.json") == before
    assert scope.app.state.procurement_store.get(
        scope.project_id,
        tenant_id="system",
    ) is None

    changed = dict(payload, url_or_number="DIFFERENT")
    conflict = scope.client.post(
        scope.base + "/imports/g2b-opportunity",
        json=changed,
        headers=API_HEADERS,
    )
    assert conflict.status_code == 409
    assert conflict.json()["detail"]["code"] == "procurement_context_changed"
    assert scope.calls == ["A"]

    partial = scope.client.post(
        scope.base + "/imports/g2b-opportunity",
        json={
            "url_or_number": "B",
            "expected_selection_revision": 1,
        },
        headers=API_HEADERS,
    )
    assert partial.status_code == 422


def test_import_preflight_rejects_stale_revisions_before_expensive_effects(
    scope,
    monkeypatch,
):
    _import(scope, "A", selection_revision=0)
    initial_calls = list(scope.calls)

    stale_selection = _import_payload("B", selection_revision=0)
    response = scope.client.post(
        scope.base + "/imports/g2b-opportunity",
        json=stale_selection,
        headers=API_HEADERS,
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "procurement_context_changed"
    assert scope.calls == initial_calls

    parsed = 0
    saved = 0

    def observe_parse(*args, **kwargs):
        nonlocal parsed
        parsed += 1
        return {}

    original_save = scope.app.state.procurement_opportunity_snapshot_store.save_source_snapshot

    def observe_save(*args, **kwargs):
        nonlocal saved
        saved += 1
        return original_save(*args, **kwargs)

    monkeypatch.setattr("app.services.rfp_parser.parse_rfp_fields", observe_parse)
    monkeypatch.setattr(
        scope.app.state.procurement_opportunity_snapshot_store,
        "save_source_snapshot",
        observe_save,
    )
    stale_decision = _import_payload("A", selection_revision=1)
    stale_decision["parsed_rfp_fields"] = None
    response = scope.client.post(
        scope.base + "/imports/g2b-opportunity",
        json=stale_decision,
        headers=API_HEADERS,
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "procurement_context_changed"
    assert scope.calls == [*initial_calls, "A"]
    assert parsed == 0
    assert saved == 0


def test_scoped_inputs_reject_partial_pairs_and_invalid_identifiers(scope):
    decision_id, revision = _ready(scope, "A", selection_revision=0)
    admin = _login_admin(scope.client, "strict-admin")
    council_body = {"goal": "Validate scope", "context": "", "constraints": ""}

    requests = (
        scope.client.post(
            scope.base + f"/decision-council/run?decision_id={decision_id}",
            json=council_body,
            headers=API_HEADERS,
        ),
        scope.client.get(
            scope.base
            + f"/decision-council?expected_decision_revision={revision}",
            headers=API_HEADERS,
        ),
        scope.client.post(
            scope.base
            + f"/procurement/review-packet?decision_id={decision_id}",
            json={"reviewer": "strict-admin"},
            headers=admin,
        ),
        scope.client.post(
            scope.base
            + "/procurement/review-packet?decision_id=not-a-uuid"
            + f"&expected_decision_revision={revision}",
            json={"reviewer": "strict-admin"},
            headers=admin,
        ),
        scope.client.post(
            scope.base
            + f"/decision-council/run?decision_id={decision_id}"
            + "&expected_decision_revision=0",
            json=council_body,
            headers=API_HEADERS,
        ),
        scope.client.post(
            scope.base + "/imports/g2b-opportunity",
            json={
                **_import_payload("B", selection_revision=1),
                "operation_id": "not-a-uuid",
            },
            headers=API_HEADERS,
        ),
        scope.client.post(
            scope.base + "/procurement/override-reason",
            json={
                "reason": "Strict revision",
                "decision_id": decision_id,
                "expected_decision_revision": str(revision),
                "operation_id": str(uuid4()),
            },
            headers=API_HEADERS,
        ),
    )
    assert [response.status_code for response in requests] == [422] * len(requests)


def test_override_is_exact_idempotent_and_project_only_multi_fails(scope):
    a = _import(scope, "A", selection_revision=0)
    _import(scope, "B", selection_revision=1)
    decision_id = a["receipt"]["decision_id"]
    operation_id = str(uuid4())
    payload = {
        "reason": "A only operator disagreement",
        "decision_id": decision_id,
        "expected_decision_revision": 1,
        "operation_id": operation_id,
    }
    first = scope.client.post(
        scope.base + "/procurement/override-reason",
        json=payload,
        headers=API_HEADERS,
    )
    assert first.status_code == 200, first.text
    replay = scope.client.post(
        scope.base + "/procurement/override-reason",
        json=payload,
        headers=API_HEADERS,
    )
    assert replay.json() == first.json()
    state = scope.app.state.procurement_opportunity_store.get(
        scope.project_id,
        tenant_id="system",
    )
    notes = {entry.record.decision_id: entry.record.notes for entry in state.entries}
    assert "A only" in notes[decision_id]
    assert all(not value for key, value in notes.items() if key != decision_id)
    assert first.json()["receipt"]["decision_revision"] == 1

    legacy = scope.client.post(
        scope.base + "/procurement/evaluate",
        headers=API_HEADERS,
    )
    assert legacy.status_code == 409
    assert legacy.json()["detail"]["code"] == "procurement_opportunity_selection_required"


def test_scoped_council_and_review_packet_bind_exact_decision(scope):
    a_id, a_revision = _ready(scope, "A", selection_revision=0)
    _ready(scope, "B", selection_revision=1)
    council = scope.client.post(
        scope.base
        + f"/decision-council/run?decision_id={a_id}"
        + f"&expected_decision_revision={a_revision}",
        json={"goal": "Review A", "context": "", "constraints": ""},
        headers=API_HEADERS,
    )
    assert council.status_code == 200, council.text
    assert council.json()["source_binding"]["decision_id"] == a_id
    latest = scope.client.get(
        scope.base
        + f"/decision-council?decision_id={a_id}"
        + f"&expected_decision_revision={a_revision}",
        headers=API_HEADERS,
    )
    assert latest.status_code == 200
    assert latest.json()["session_id"] == council.json()["session_id"]

    ambiguous = scope.client.post(
        scope.base + "/decision-council/run",
        json={"goal": "Do not guess", "context": "", "constraints": ""},
        headers=API_HEADERS,
    )
    assert ambiguous.status_code == 409
    assert ambiguous.json()["detail"]["code"] == "procurement_opportunity_selection_required"

    admin = _login_admin(scope.client)
    packet = scope.client.post(
        scope.base
        + f"/procurement/review-packet?decision_id={a_id}"
        + f"&expected_decision_revision={a_revision}",
        json={"reviewer": "scoped-admin"},
        headers=admin,
    )
    assert packet.status_code == 200, packet.text
    verified = verify_procurement_review_packet(
        packet.content,
        expected_tenant_id="system",
        expected_project_id=scope.project_id,
    )
    assert verified["source_binding"]["decision_id"] == a_id

    legacy_packet = scope.client.post(
        scope.base + "/procurement/review-packet",
        json={"reviewer": "scoped-admin"},
        headers=admin,
    )
    assert legacy_packet.status_code == 409
    assert (
        legacy_packet.json()["detail"]["code"]
        == "procurement_opportunity_selection_required"
    )


def test_council_run_recaptures_source_and_never_reports_raced_binding_current(
    scope,
    monkeypatch,
):
    decision_id, revision = _ready(scope, "A", selection_revision=0)
    entry = scope.app.state.procurement_opportunity_service.get_decision(
        scope.project_id,
        tenant_id="system",
        decision_id=decision_id,
    )
    snapshot_path = entry.record.source_snapshots[-1].storage_path
    service = scope.app.state.decision_council_service
    original = service.run_procurement_council

    def change_source_after_save(*args, **kwargs):
        session = original(*args, **kwargs)
        scope.backend.write_text(snapshot_path, '{"changed":"during-council"}')
        return session

    monkeypatch.setattr(service, "run_procurement_council", change_source_after_save)
    response = scope.client.post(
        scope.base
        + f"/decision-council/run?decision_id={decision_id}"
        + f"&expected_decision_revision={revision}",
        json={"goal": "Review race", "context": "", "constraints": ""},
        headers=API_HEADERS,
    )
    assert response.status_code == 200, response.text
    assert response.json()["current_procurement_binding_status"] == "stale"
    assert (
        response.json()["current_procurement_binding_reason_code"]
        == "procurement_binding_changed"
    )


def test_pending_bound_review_uses_packet_source_and_completed_replay_is_exact(scope):
    a_id, a_revision = _ready(scope, "A", selection_revision=0)
    _ready(scope, "B", selection_revision=1)
    admin = _login_admin(scope.client, "review-admin")
    packet = scope.client.post(
        scope.base
        + f"/procurement/review-packet?decision_id={a_id}"
        + f"&expected_decision_revision={a_revision}",
        json={"reviewer": "review-admin"},
        headers=admin,
    )
    assert packet.status_code == 200, packet.text
    packet_sha256 = packet.headers["X-DecisionDoc-Packet-SHA256"]
    completion = {"decision": "accepted", "rationale": "A reviewed locally"}
    first = scope.client.post(
        scope.base + f"/procurement/reviews/{packet_sha256}/complete",
        json=completion,
        headers=admin,
    )
    assert first.status_code == 200, first.text
    replay = scope.client.post(
        scope.base + f"/procurement/reviews/{packet_sha256}/complete",
        json=completion,
        headers=admin,
    )
    assert replay.status_code == 200
    assert replay.content == first.content
    assert replay.headers["X-DecisionDoc-Reviewed-Package-SHA256"] == first.headers[
        "X-DecisionDoc-Reviewed-Package-SHA256"
    ]


def test_scoped_packet_and_pending_completion_enforce_tenant_and_assignee(scope):
    decision_id, revision = _ready(scope, "A", selection_revision=0)
    admin = _login_admin(scope.client, "access-admin")
    assigned = _create_user(scope.client, admin, "access-assigned")
    other = _create_user(scope.client, admin, "access-other")
    url = (
        scope.base
        + f"/procurement/review-packet?decision_id={decision_id}"
        + f"&expected_decision_revision={revision}"
    )

    denied_packet = scope.client.post(
        url,
        json={"reviewer": "access-other"},
        headers=assigned,
    )
    assert denied_packet.status_code == 403
    assert scope.app.state.procurement_review_store.list_by_project(
        tenant_id="system",
        project_id=scope.project_id,
    ) == []

    packet = scope.client.post(
        url,
        json={"reviewer": "access-assigned"},
        headers=admin,
    )
    assert packet.status_code == 200, packet.text
    packet_sha256 = packet.headers["X-DecisionDoc-Packet-SHA256"]
    pending = scope.app.state.procurement_review_store.get(
        tenant_id="system",
        project_id=scope.project_id,
        packet_sha256=packet_sha256,
    )
    completion_url = scope.base + f"/procurement/reviews/{packet_sha256}/complete"
    completion = {"decision": "accepted", "rationale": "Exact assignee only"}

    denied_completion = scope.client.post(
        completion_url,
        json=completion,
        headers=other,
    )
    assert denied_completion.status_code == 409
    assert denied_completion.json()["detail"]["code"] == "procurement_reviewer_mismatch"
    assert scope.app.state.procurement_review_store.get(
        tenant_id="system",
        project_id=scope.project_id,
        packet_sha256=packet_sha256,
    ) == pending

    scope.app.state.tenant_store.create_tenant("foreign", "Foreign")
    foreign = scope.client.post(
        "/auth/register",
        headers={"X-Tenant-ID": "foreign"},
        json={
            "username": "foreign-admin",
            "display_name": "foreign-admin",
            "email": "foreign-admin@example.test",
            "password": "Password123!",
            "role": "admin",
        },
    )
    assert foreign.status_code == 200, foreign.text
    foreign_headers = {
        "X-Tenant-ID": "foreign",
        "Authorization": f"Bearer {foreign.json()['access_token']}",
    }
    denied_tenant = scope.client.post(
        completion_url,
        json=completion,
        headers=foreign_headers,
    )
    assert denied_tenant.status_code == 404
    assert scope.app.state.procurement_review_store.get(
        tenant_id="system",
        project_id=scope.project_id,
        packet_sha256=packet_sha256,
    ) == pending


def test_active_decision_evidence_denies_members_assigned_only_to_another_decision(
    scope, monkeypatch,
):
    a_id, a_revision = _ready(scope, "A", selection_revision=0)
    b_id, b_revision = _ready(scope, "B", selection_revision=1)
    admin = _login_admin(scope.client, "evidence-admin")
    a_member = _create_user(scope.client, admin, "evidence-a")
    b_member = _create_user(scope.client, admin, "evidence-b")

    for decision_id, revision, reviewer in (
        (a_id, a_revision, "evidence-a"),
        (b_id, b_revision, "evidence-b"),
    ):
        packet = scope.client.post(
            scope.base
            + f"/procurement/review-packet?decision_id={decision_id}"
            + f"&expected_decision_revision={revision}",
            json={"reviewer": reviewer},
            headers=admin,
        )
        assert packet.status_code == 200, packet.text

    paths = (
        scope.base + "/decision-evidence-map?bundle_type=proposal_kr",
        scope.base
        + "/guided-decision-review-handoff?bundle_type=proposal_kr",
    )
    events = []
    monkeypatch.setattr("app.middleware.observability.log_event", lambda logger, event, **fields: events.append(event))
    for path in paths:
        events.clear()
        denied = scope.client.get(path, headers=a_member)
        assert denied.status_code == 404
        assert events[-1]["procurement_review_authorized_count"] == 0
        assert events[-1]["procurement_review_total"] == 0
        assert scope.client.get(path, headers=b_member).status_code == 200
        assert scope.client.get(path, headers=admin).status_code == 200

    selected = scope.client.post(
        scope.base + "/procurement/selection",
        json={
            "decision_id": a_id,
            "expected_selection_revision": 2,
            "operation_id": str(uuid4()),
        },
        headers=API_HEADERS,
    )
    assert selected.status_code == 200, selected.text
    for path in paths:
        assert scope.client.get(path, headers=a_member).status_code == 200


def test_pending_bound_review_rejects_exact_source_byte_change(scope):
    a_id, a_revision = _ready(scope, "A", selection_revision=0)
    admin = _login_admin(scope.client, "stale-admin")
    packet = scope.client.post(
        scope.base
        + f"/procurement/review-packet?decision_id={a_id}"
        + f"&expected_decision_revision={a_revision}",
        json={"reviewer": "stale-admin"},
        headers=admin,
    )
    assert packet.status_code == 200, packet.text
    packet_sha256 = packet.headers["X-DecisionDoc-Packet-SHA256"]
    entry = scope.app.state.procurement_opportunity_service.get_decision(
        scope.project_id,
        tenant_id="system",
        decision_id=a_id,
    )
    snapshot_path = entry.record.source_snapshots[0].storage_path
    scope.backend.write_text(snapshot_path, '{"changed":true}')
    rejected = scope.client.post(
        scope.base + f"/procurement/reviews/{packet_sha256}/complete",
        json={"decision": "accepted", "rationale": "Must not complete"},
        headers=admin,
    )
    assert rejected.status_code == 409
    assert rejected.json()["detail"]["code"] == "procurement_review_source_changed"
    record = scope.app.state.procurement_review_store.get(
        tenant_id="system",
        project_id=scope.project_id,
        packet_sha256=packet_sha256,
    )
    assert record.review_status == "pending"


def test_pending_bound_review_rechecks_source_after_package_build(
    scope,
    monkeypatch,
):
    decision_id, revision = _ready(scope, "A", selection_revision=0)
    admin = _login_admin(scope.client, "completion-race-admin")
    packet = scope.client.post(
        scope.base
        + f"/procurement/review-packet?decision_id={decision_id}"
        + f"&expected_decision_revision={revision}",
        json={"reviewer": "completion-race-admin"},
        headers=admin,
    )
    assert packet.status_code == 200, packet.text
    packet_sha256 = packet.headers["X-DecisionDoc-Packet-SHA256"]
    pending = scope.app.state.procurement_review_store.get(
        tenant_id="system",
        project_id=scope.project_id,
        packet_sha256=packet_sha256,
    )
    entry = scope.app.state.procurement_opportunity_service.get_decision(
        scope.project_id,
        tenant_id="system",
        decision_id=decision_id,
    )
    snapshot_path = entry.record.source_snapshots[-1].storage_path
    from app.services.procurement_decision_package import reviewed_package as module

    original = module.build_procurement_reviewed_package

    def change_source_after_build(*args, **kwargs):
        package = original(*args, **kwargs)
        scope.backend.write_text(snapshot_path, '{"changed":"during-completion"}')
        return package

    monkeypatch.setattr(
        module,
        "build_procurement_reviewed_package",
        change_source_after_build,
    )
    rejected = scope.client.post(
        scope.base + f"/procurement/reviews/{packet_sha256}/complete",
        json={"decision": "accepted", "rationale": "Must remain pending"},
        headers=admin,
    )
    assert rejected.status_code == 409
    assert rejected.json()["detail"]["code"] == "procurement_review_source_changed"
    assert scope.app.state.procurement_review_store.get(
        tenant_id="system",
        project_id=scope.project_id,
        packet_sha256=packet_sha256,
    ) == pending


def test_review_packet_rechecks_exact_source_before_prepare(scope, monkeypatch):
    a_id, a_revision = _ready(scope, "A", selection_revision=0)
    admin = _login_admin(scope.client, "race-admin")
    entry = scope.app.state.procurement_opportunity_service.get_decision(
        scope.project_id,
        tenant_id="system",
        decision_id=a_id,
    )
    snapshot_path = entry.record.source_snapshots[0].storage_path
    from app.services.procurement_decision_package import review_packet as module

    original = module.build_project_procurement_review_packet

    def change_source_after_build(*args, **kwargs):
        packet = original(*args, **kwargs)
        scope.backend.write_text(snapshot_path, '{"changed":"during-build"}')
        return packet

    monkeypatch.setattr(
        module,
        "build_project_procurement_review_packet",
        change_source_after_build,
    )
    rejected = scope.client.post(
        scope.base
        + f"/procurement/review-packet?decision_id={a_id}"
        + f"&expected_decision_revision={a_revision}",
        json={"reviewer": "race-admin"},
        headers=admin,
    )
    assert rejected.status_code == 409
    assert rejected.json()["detail"]["code"] == "procurement_context_changed"
    assert scope.app.state.procurement_review_store.list_by_project(
        tenant_id="system",
        project_id=scope.project_id,
    ) == []
