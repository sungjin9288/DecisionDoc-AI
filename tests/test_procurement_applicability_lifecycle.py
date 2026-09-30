"""Requirement projections remain source-bound through the review lifecycle."""
import io
import json
import zipfile
from uuid import uuid4

import pytest

from app.services.procurement_applicability_service import (
    ProcurementApplicabilityConflict, ProcurementApplicabilityNotFound,
)
from app.services.procurement_decision_package.review_packet import verify_procurement_review_packet
from tests.test_procurement_requirement_applicability_api import _create_payload, _read, _source, _url
from tests.test_procurement_scoped_lifecycle import (
    API_HEADERS, _create_user, _login_admin, _ready, scope as scope,
)


def _packet(scope, decision_id, revision, headers, reviewer="scoped-admin"):
    return scope.client.post(
        scope.base + f"/procurement/review-packet?decision_id={decision_id}&expected_decision_revision={revision}",
        json={"reviewer": reviewer}, headers=headers,
    )


def _create(scope, decision_id, revision, admin):
    response = scope.client.post(_url(scope, decision_id), headers=admin,
                                 json=_create_payload(scope, decision_id, revision))
    assert response.status_code == 200, response.text
    return response.json()["receipt"]["decision_revision"]


def _annotate(scope, decision_id, revision, admin, *, status="not_applicable"):
    requirement = _read(scope, decision_id, admin)[0]
    response = scope.client.post(
        _url(scope, decision_id) + f"/{requirement['requirement_id']}/applicability",
        headers=admin, json={**_source(scope, decision_id), "applicability": status,
                            "rationale": "범위 제외 근거 <script>not executable</script>",
                            "expected_decision_revision": revision, "operation_id": str(uuid4())},
    )
    assert response.status_code == 200, response.text
    return response.json()["receipt"]["decision_revision"]


def _complete(scope, packet, headers):
    return scope.client.post(
        scope.base + f"/procurement/reviews/{packet.headers['X-DecisionDoc-Packet-SHA256']}/complete",
        json={"decision": "accepted", "rationale": "Local applicability review"}, headers=headers,
    )


def _entries(packet):
    with zipfile.ZipFile(io.BytesIO(packet.content)) as archive:
        return {name: archive.read(name) for name in archive.namelist()}


def test_sources_are_admin_only_exact_and_revision_bound(scope):
    decision_id, revision = _ready(scope, "A", selection_revision=0)
    admin = _login_admin(scope.client)
    member = _create_user(scope.client, admin, "source-reader")
    url = _url(scope, decision_id) + f"/sources?expected_decision_revision={revision}"
    before = scope.backend.read_text("tenants/system/procurement_decisions.json")
    for headers, status in (({}, 401), (API_HEADERS, 401), (member, 403)):
        response = scope.client.get(url, headers=headers)
        assert response.status_code == status, response.text
    response = scope.client.get(url, headers=admin)
    assert response.status_code == 200, response.text
    assert response.headers["Cache-Control"] == "no-store"
    assert response.json()["operational_approval"] is False
    source = _source(scope, decision_id)
    assert response.json()["sources"] == [{"snapshot_id": source["snapshot_id"],
                                           "snapshot_sha256": source["snapshot_sha256"],
                                           "raw_text": source["quote"]}]
    assert "storage_path" not in response.text
    assert scope.client.get(_url(scope, decision_id) + "/sources", headers=admin).status_code == 422
    assert scope.client.get(url.replace(f"revision={revision}", "revision=1"), headers=admin).status_code == 409
    assert scope.backend.read_text("tenants/system/procurement_decisions.json") == before


def test_requirement_read_rejects_old_revision_and_racing_projection(scope, monkeypatch):
    decision_id, revision = _ready(scope, "A", selection_revision=0)
    admin = _login_admin(scope.client)
    _create(scope, decision_id, revision, admin)
    response = scope.client.get(_url(scope, decision_id) + f"?expected_decision_revision={revision}", headers=admin)
    assert response.status_code == 409
    service = scope.app.state.procurement_applicability_service

    def changed(_captured):
        raise ProcurementApplicabilityConflict("Changed during projection")

    monkeypatch.setattr(service, "assert_current", changed)
    assert scope.client.get(_url(scope, decision_id), headers=admin).status_code == 409
    assert scope.client.get(_url(scope, decision_id) + f"/sources?expected_decision_revision={revision + 1}", headers=admin).status_code == 409


@pytest.mark.parametrize("corrupt", ["not-json", '{"announcement":{"raw_text":[]}}',
                                    '{"announcement":{"raw_text":"first","raw_text":"second"}}'])
def test_source_text_errors_fail_closed_without_leaking_payload(scope, corrupt):
    decision_id, revision = _ready(scope, "A", selection_revision=0)
    admin = _login_admin(scope.client)
    entry = scope.app.state.procurement_opportunity_service.get_decision(
        scope.project_id, tenant_id="system", decision_id=decision_id,
    )
    scope.backend.write_text(entry.record.source_snapshots[-1].storage_path, corrupt)
    response = scope.client.get(_url(scope, decision_id) + f"/sources?expected_decision_revision={revision}", headers=admin)
    assert response.status_code == 503, response.text
    assert corrupt not in response.text


def test_v3_package_completion_and_replay_preserve_requirement_evidence(scope):
    decision_id, revision = _ready(scope, "A", selection_revision=0)
    admin = _login_admin(scope.client)
    actor_id = scope.client.get("/auth/me", headers=admin).json()["user_id"]
    revision = _create(scope, decision_id, revision, admin)
    revision = _annotate(scope, decision_id, revision, admin)
    packet = _packet(scope, decision_id, revision, admin)
    assert packet.status_code == 200, packet.text
    verification = verify_procurement_review_packet(packet.content, expected_tenant_id="system", expected_project_id=scope.project_id)
    assert verification["schema_version"] == "decisiondoc.procurement_review_packet.v3"
    assert verification["source_bytes_verified"] is False
    entries = _entries(packet)
    assert "requirement_applicability.docx" in entries
    package = json.loads(entries["decision_package.json"])
    row = package["package"]["requirement_applicability"]["requirements"][0]
    assert row["applicability"] == "not_applicable"
    assert row["annotations"][0]["rationale"].startswith("범위 제외")
    for name, content in entries.items():
        if name.endswith((".json", ".md", ".html")):
            assert actor_id.encode() not in content
            assert b"created_by_actor_id" not in content
            assert b'"actor_id"' not in content
    first = _complete(scope, packet, admin)
    assert first.status_code == 200, first.text
    _annotate(scope, decision_id, revision, admin, status="applies")
    replay = _complete(scope, packet, admin)
    assert replay.status_code == 200, replay.text
    assert replay.content == first.content


def test_existing_requirements_cannot_be_self_assigned_by_unassigned_member(scope):
    decision_id, revision = _ready(scope, "A", selection_revision=0)
    admin = _login_admin(scope.client)
    member = _create_user(scope.client, admin, "packet-reader")
    revision = _create(scope, decision_id, revision, admin)
    denied = _packet(scope, decision_id, revision, member, "packet-reader")
    assert denied.status_code == 404, denied.text
    assert scope.app.state.procurement_review_store.list_by_project(tenant_id="system", project_id=scope.project_id) == []
    assigned = _packet(scope, decision_id, revision, admin, "packet-reader")
    assert assigned.status_code == 200, assigned.text
    allowed = _packet(scope, decision_id, revision, member, "packet-reader")
    assert allowed.status_code == 200, allowed.text
    assert allowed.content == assigned.content


def test_changed_annotation_blocks_pending_completion(scope):
    decision_id, revision = _ready(scope, "A", selection_revision=0)
    admin = _login_admin(scope.client)
    revision = _create(scope, decision_id, revision, admin)
    packet = _packet(scope, decision_id, revision, admin)
    assert packet.status_code == 200, packet.text
    _annotate(scope, decision_id, revision, admin)
    assert _complete(scope, packet, admin).status_code == 409
    record = scope.app.state.procurement_review_store.get(
        tenant_id="system", project_id=scope.project_id, packet_sha256=packet.headers["X-DecisionDoc-Packet-SHA256"],
    )
    assert record.review_status == "pending"


def test_source_change_exports_unknown_without_erasing_previous_na(scope):
    decision_id, revision = _ready(scope, "A", selection_revision=0)
    admin = _login_admin(scope.client)
    revision = _create(scope, decision_id, revision, admin)
    revision = _annotate(scope, decision_id, revision, admin)
    original = _read(scope, decision_id, admin)[0]
    packet = _packet(scope, decision_id, revision, admin)
    assert packet.status_code == 200, packet.text
    entry = scope.app.state.procurement_opportunity_service.get_decision(
        scope.project_id, tenant_id="system", decision_id=decision_id,
    )
    path = entry.record.source_snapshots[-1].storage_path
    source = json.loads(scope.backend.read_bytes(path))
    source["announcement"]["raw_text"] = "새 원문: 검토 범위 변경"
    scope.backend.write_text(path, json.dumps(source, ensure_ascii=False))
    assert _complete(scope, packet, admin).status_code == 409
    refreshed = _packet(scope, decision_id, revision, admin)
    assert refreshed.status_code == 200, refreshed.text
    row = json.loads(_entries(refreshed)["decision_package.json"])["package"]["requirement_applicability"]["requirements"][0]
    assert row["stale"] is True
    assert row["applicability"] == "unknown"
    assert row["quote"] == original["quote"]
    assert row["annotations"][0]["applicability"] == "not_applicable"
    assert row["annotations"][0]["rationale"] == original["annotations"][0]["rationale"]


def test_preexisting_v2_packet_completes_without_adding_v3_requirements(scope, monkeypatch):
    from app.services.procurement_decision_package import review_packet

    decision_id, revision = _ready(scope, "A", selection_revision=0)
    admin = _login_admin(scope.client)
    build = review_packet.build_project_procurement_review_packet

    def v2_builder(*args, **kwargs):
        kwargs.pop("requirement_applicability", None)
        return build(*args, **kwargs)

    with monkeypatch.context() as legacy:
        legacy.setattr(review_packet, "build_project_procurement_review_packet", v2_builder)
        packet = _packet(scope, decision_id, revision, admin)
    assert packet.status_code == 200, packet.text
    assert verify_procurement_review_packet(packet.content)["schema_version"].endswith(".v2")
    completed = _complete(scope, packet, admin)
    assert completed.status_code == 200, completed.text
    assert _complete(scope, packet, admin).content == completed.content


@pytest.mark.parametrize("stage", ["prepare", "complete"])
@pytest.mark.parametrize("error", [ProcurementApplicabilityConflict, ProcurementApplicabilityNotFound])
def test_changed_requirements_at_final_recheck_never_write_review_state(scope, monkeypatch, stage, error):
    decision_id, revision = _ready(scope, "A", selection_revision=0)
    admin = _login_admin(scope.client)
    revision = _create(scope, decision_id, revision, admin)
    packet = _packet(scope, decision_id, revision, admin) if stage == "complete" else None
    store = scope.app.state.procurement_review_store
    before = store.list_by_project(tenant_id="system", project_id=scope.project_id)

    def changed(_captured):
        raise error("Changed immediately before review write")

    monkeypatch.setattr(scope.app.state.procurement_applicability_service, "assert_current", changed)
    response = _complete(scope, packet, admin) if packet is not None else _packet(scope, decision_id, revision, admin)
    assert response.status_code == 409, response.text
    assert store.list_by_project(tenant_id="system", project_id=scope.project_id) == before


@pytest.mark.parametrize("stage", ["prepare", "complete"])
def test_unavailable_source_at_final_recheck_is_503_without_review_write(scope, monkeypatch, stage):
    from app.storage.procurement_store import ProcurementDecisionStoreError

    decision_id, revision = _ready(scope, "A", selection_revision=0)
    admin = _login_admin(scope.client)
    revision = _create(scope, decision_id, revision, admin)
    packet = _packet(scope, decision_id, revision, admin) if stage == "complete" else None
    store = scope.app.state.procurement_review_store
    before = store.list_by_project(tenant_id="system", project_id=scope.project_id)

    def unavailable(_captured):
        raise ProcurementDecisionStoreError("private backend failure")

    monkeypatch.setattr(scope.app.state.procurement_applicability_service, "assert_current", unavailable)
    response = _complete(scope, packet, admin) if packet is not None else _packet(scope, decision_id, revision, admin)
    assert response.status_code == 503, response.text
    assert response.json()["detail"]["code"] == "procurement_source_unavailable"
    assert "private backend failure" not in response.text
    assert store.list_by_project(tenant_id="system", project_id=scope.project_id) == before
