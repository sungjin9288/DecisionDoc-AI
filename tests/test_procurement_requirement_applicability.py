"""Step 7 requirement applicability core contract."""
from __future__ import annotations

import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.schemas import (
    NormalizedProcurementOpportunity,
    ProcurementChecklistItem,
    ProcurementChecklistSeverity,
    ProcurementDecisionUpsert,
    ProcurementHardFilterResult,
    ProcurementHardFilterStatus,
    ProcurementRecommendation,
)
from app.schemas.procurement_applicability import (
    AnnotateProcurementRequirementRequest,
    CreateProcurementRequirementRequest,
)
from app.services.procurement_applicability_service import (
    ProcurementApplicabilityConflict,
    ProcurementApplicabilityNotFound,
    ProcurementApplicabilityService,
)
from app.storage.procurement_project_store import ProcurementProjectStore
from app.storage.procurement_store import ProcurementDecisionStore
from app.storage.state_backend import LocalStateBackend
from tests.test_procurement_store_integrity import _s3_backend


TENANT = "alpha"
PROJECT = "project-1"
ACTOR = "admin-1"
STATE_PATH = f"tenants/{TENANT}/procurement_decisions.json"


@pytest.fixture(params=["local", "fake-s3"])
def backend(request, tmp_path, monkeypatch):
    monkeypatch.setenv("PYTHON_DOTENV_DISABLED", "1")
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "isolated-data"))
    return LocalStateBackend(tmp_path / "state") if request.param == "local" else _s3_backend()[0]


def _seed(backend, *, raw_text="가😀나다 자격요건", hard_filters=None, checklist_items=None):
    legacy = ProcurementDecisionStore(backend=backend)
    snapshot = legacy.save_source_snapshot(
        tenant_id=TENANT,
        project_id=PROJECT,
        source_kind="g2b_import",
        payload={"announcement": {"raw_text": raw_text}, "source": "A"},
    )
    payload = ProcurementDecisionUpsert(
        tenant_id=TENANT,
        project_id=PROJECT,
        opportunity=NormalizedProcurementOpportunity(
            source_kind="g2b", source_id="A", title="A"
        ),
        source_snapshots=[snapshot],
        hard_filters=hard_filters or [],
        checklist_items=checklist_items or [],
    )
    receipt = ProcurementProjectStore(backend=backend).import_opportunity(
        payload,
        expected_selection_revision=0,
        expected_decision_revision=0,
        operation_id=str(uuid4()),
    )
    raw = backend.read_bytes(snapshot.storage_path)
    assert raw is not None
    return receipt, snapshot, hashlib.sha256(raw).hexdigest(), raw_text


def _create_payload(snapshot, sha256, raw_text, *, revision=1, operation_id=None):
    return CreateProcurementRequirementRequest(
        title="참가 자격",
        category="eligibility_and_compliance",
        snapshot_id=snapshot.snapshot_id,
        snapshot_sha256=sha256,
        quote_start=1,
        quote_end=3,
        quote=raw_text[1:3],
        expected_decision_revision=revision,
        operation_id=operation_id or str(uuid4()),
    )


def _annotate_payload(snapshot, sha256, raw_text, *, revision, applicability="applies", actor_operation=None):
    return AnnotateProcurementRequirementRequest(
        snapshot_id=snapshot.snapshot_id,
        snapshot_sha256=sha256,
        quote_start=1,
        quote_end=3,
        quote=raw_text[1:3],
        applicability=applicability,
        rationale="원문과 내부 증빙을 대조함",
        expected_decision_revision=revision,
        operation_id=actor_operation or str(uuid4()),
    )


def _service(backend):
    return ProcurementApplicabilityService(
        store=ProcurementProjectStore(backend=backend), backend=backend
    )


def test_strict_request_contract_rejects_coercion_extra_and_blank_rationale():
    common = {
        "snapshot_id": str(uuid4()),
        "snapshot_sha256": "a" * 64,
        "quote_start": 0,
        "quote_end": 1,
        "quote": "x",
        "expected_decision_revision": 1,
        "operation_id": str(uuid4()),
    }
    with pytest.raises(ValidationError):
        CreateProcurementRequirementRequest(
            title="x", category="eligibility_and_compliance", **common, unexpected=True
        )
    with pytest.raises(ValidationError):
        CreateProcurementRequirementRequest(
            title="x", category="eligibility_and_compliance", **{**common, "quote_start": "0"}
        )
    with pytest.raises(ValidationError):
        AnnotateProcurementRequirementRequest(
            applicability="not_applicable", rationale="  ", **common
        )


def test_create_binds_exact_snapshot_bytes_unicode_quote_and_server_identity(backend):
    receipt, snapshot, sha256, raw_text = _seed(backend)
    service = _service(backend)
    result = service.create_requirement(
        PROJECT,
        tenant_id=TENANT,
        decision_id=receipt.decision_id,
        actor_id=ACTOR,
        payload=_create_payload(snapshot, sha256, raw_text),
    )
    requirements = service.list_requirements(
        PROJECT, tenant_id=TENANT, decision_id=receipt.decision_id
    )
    assert result.decision_revision == 2
    assert len(requirements) == 1
    requirement = requirements[0]
    assert str(uuid4()) != requirement["requirement_id"]
    assert requirement["quote"] == "😀나"
    assert requirement["applicability"] == "unknown"
    assert requirement["stale"] is False
    assert requirement["created_by_actor_id"] == ACTOR
    assert requirement["annotations"] == []
    assert len(requirement["source_set_sha256"]) == 64

    before = backend.read_text(STATE_PATH)
    bad = _create_payload(snapshot, "0" * 64, raw_text, revision=2)
    with pytest.raises(ProcurementApplicabilityConflict):
        service.create_requirement(
            PROJECT, tenant_id=TENANT, decision_id=receipt.decision_id,
            actor_id=ACTOR, payload=bad,
        )
    assert backend.read_text(STATE_PATH) == before


def test_quote_mismatch_scope_and_missing_requirement_are_zero_write(backend):
    receipt, snapshot, sha256, raw_text = _seed(backend)
    service = _service(backend)
    before = backend.read_text(STATE_PATH)
    mismatch = _create_payload(snapshot, sha256, raw_text).model_copy(update={"quote": "나다"})
    with pytest.raises(ProcurementApplicabilityConflict):
        service.create_requirement(
            PROJECT, tenant_id=TENANT, decision_id=receipt.decision_id,
            actor_id=ACTOR, payload=mismatch,
        )
    with pytest.raises(ProcurementApplicabilityNotFound):
        service.list_requirements(PROJECT, tenant_id=TENANT, decision_id=str(uuid4()))
    assert backend.read_text(STATE_PATH) == before


def test_annotation_appends_immutable_history_and_actor_bound_replay(backend):
    receipt, snapshot, sha256, raw_text = _seed(backend)
    service = _service(backend)
    operation_id = str(uuid4())
    created = service.create_requirement(
        PROJECT, tenant_id=TENANT, decision_id=receipt.decision_id, actor_id=ACTOR,
        payload=_create_payload(snapshot, sha256, raw_text, operation_id=operation_id),
    )
    requirement_id = service.list_requirements(
        PROJECT, tenant_id=TENANT, decision_id=receipt.decision_id
    )[0]["requirement_id"]
    annotation_operation = str(uuid4())
    payload = _annotate_payload(
        snapshot, sha256, raw_text, revision=created.decision_revision,
        actor_operation=annotation_operation,
    )
    annotated = service.annotate_requirement(
        PROJECT, tenant_id=TENANT, decision_id=receipt.decision_id,
        requirement_id=requirement_id, actor_id=ACTOR, payload=payload,
    )
    later = service.annotate_requirement(
        PROJECT, tenant_id=TENANT, decision_id=receipt.decision_id,
        requirement_id=requirement_id, actor_id=ACTOR,
        payload=_annotate_payload(snapshot, sha256, raw_text, revision=annotated.decision_revision,
                                  applicability="unknown"),
    )
    history = service.list_requirements(
        PROJECT, tenant_id=TENANT, decision_id=receipt.decision_id
    )[0]
    assert [item["applicability"] for item in history["annotations"]] == ["applies", "unknown"]
    assert history["annotations"][0]["actor_id"] == ACTOR
    assert history["annotations"][0]["expected_decision_revision"] == created.decision_revision
    assert history["annotations"][0]["operation_id"] == annotation_operation
    assert history["applicability"] == "unknown"

    before = backend.read_text(STATE_PATH)
    assert service.annotate_requirement(
        PROJECT, tenant_id=TENANT, decision_id=receipt.decision_id,
        requirement_id=requirement_id, actor_id=ACTOR, payload=payload,
    ) == annotated
    assert backend.read_text(STATE_PATH) == before
    with pytest.raises(ProcurementApplicabilityConflict):
        service.annotate_requirement(
            PROJECT, tenant_id=TENANT, decision_id=receipt.decision_id,
            requirement_id=requirement_id, actor_id="admin-2", payload=payload,
        )
    assert backend.read_text(STATE_PATH) == before
    assert later.decision_revision == 4


@pytest.mark.parametrize(
    "condition",
    ["absent", "unknown", "fail", "duplicate"],
)
def test_not_applicable_fails_closed_for_invalid_related_filter_set(backend, condition):
    filters = []
    if condition != "absent":
        status = (
            ProcurementHardFilterStatus.UNKNOWN
            if condition == "unknown"
            else ProcurementHardFilterStatus.FAIL
            if condition == "fail"
            else ProcurementHardFilterStatus.PASS
        )
        filters = [
            ProcurementHardFilterResult(
                code="mandatory_eligibility_mismatch",
                label="자격",
                status=status,
                blocking=status == ProcurementHardFilterStatus.FAIL,
            ),
            ProcurementHardFilterResult(
                code="regional_or_participation_restriction",
                label="지역",
                status="pass",
            ),
        ]
        if condition == "duplicate":
            filters.append(filters[0].model_copy())
    receipt, snapshot, sha256, raw_text = _seed(backend, hard_filters=filters)
    service = _service(backend)
    created = service.create_requirement(
        PROJECT, tenant_id=TENANT, decision_id=receipt.decision_id, actor_id=ACTOR,
        payload=_create_payload(snapshot, sha256, raw_text),
    )
    requirement_id = service.list_requirements(
        PROJECT, tenant_id=TENANT, decision_id=receipt.decision_id
    )[0]["requirement_id"]
    before = backend.read_text(STATE_PATH)
    with pytest.raises(ProcurementApplicabilityConflict):
        service.annotate_requirement(
            PROJECT, tenant_id=TENANT, decision_id=receipt.decision_id,
            requirement_id=requirement_id, actor_id=ACTOR,
            payload=_annotate_payload(snapshot, sha256, raw_text,
                                      revision=created.decision_revision,
                                      applicability="not_applicable"),
        )
    assert backend.read_text(STATE_PATH) == before


def test_not_applicable_rejects_blocked_category_and_preserves_decision_fields(backend):
    filters = [
        ProcurementHardFilterResult(
            code="mandatory_eligibility_mismatch",
            label="자격",
            status="pass",
            blocking=True,
        ),
        ProcurementHardFilterResult(
            code="regional_or_participation_restriction",
            label="지역",
            status="pass",
        ),
    ]
    checklist = [ProcurementChecklistItem(
        category="eligibility_and_compliance", title="자격", status="blocked",
        severity=ProcurementChecklistSeverity.CRITICAL,
    )]
    receipt, snapshot, sha256, raw_text = _seed(
        backend, hard_filters=filters, checklist_items=checklist
    )
    store = ProcurementProjectStore(backend=backend)
    service = ProcurementApplicabilityService(store=store, backend=backend)
    created = service.create_requirement(
        PROJECT, tenant_id=TENANT, decision_id=receipt.decision_id, actor_id=ACTOR,
        payload=_create_payload(snapshot, sha256, raw_text),
    )
    state = store.get(PROJECT, tenant_id=TENANT)
    before_record = state.entries[0].record.model_dump(mode="json")
    requirement_id = service.list_requirements(
        PROJECT, tenant_id=TENANT, decision_id=receipt.decision_id
    )[0]["requirement_id"]
    with pytest.raises(ProcurementApplicabilityConflict):
        service.annotate_requirement(
            PROJECT, tenant_id=TENANT, decision_id=receipt.decision_id,
            requirement_id=requirement_id, actor_id=ACTOR,
            payload=_annotate_payload(snapshot, sha256, raw_text,
                                      revision=created.decision_revision,
                                      applicability="not_applicable"),
        )
    assert store.get(PROJECT, tenant_id=TENANT).entries[0].record.model_dump(mode="json") == before_record


def test_source_set_change_marks_read_stale_and_cannot_reanchor_declaration(backend):
    receipt, snapshot, sha256, raw_text = _seed(backend)
    store = ProcurementProjectStore(backend=backend)
    service = ProcurementApplicabilityService(store=store, backend=backend)
    created = service.create_requirement(
        PROJECT, tenant_id=TENANT, decision_id=receipt.decision_id, actor_id=ACTOR,
        payload=_create_payload(snapshot, sha256, raw_text),
    )
    requirement_id = service.list_requirements(
        PROJECT, tenant_id=TENANT, decision_id=receipt.decision_id
    )[0]["requirement_id"]
    new_snapshot = ProcurementDecisionStore(backend=backend).save_source_snapshot(
        tenant_id=TENANT, project_id=PROJECT, source_kind="g2b_import",
        payload={"announcement": {"raw_text": "새 공고 원문"}},
    )
    state = store.get(PROJECT, tenant_id=TENANT)
    refreshed = ProcurementDecisionUpsert.model_validate(
        state.entries[0].record.model_dump(
            exclude={"decision_id", "created_at", "updated_at"}, mode="json"
        )
    )
    refreshed.source_snapshots = [new_snapshot]
    refresh = store.import_opportunity(
        refreshed, expected_selection_revision=state.selection_revision,
        expected_decision_revision=created.decision_revision,
        operation_id=str(uuid4()),
    )
    stale = service.list_requirements(
        PROJECT, tenant_id=TENANT, decision_id=receipt.decision_id
    )[0]
    assert stale["stale"] is True
    assert stale["applicability"] == "unknown"
    before = backend.read_text(STATE_PATH)
    with pytest.raises(ProcurementApplicabilityConflict):
        service.annotate_requirement(
            PROJECT, tenant_id=TENANT, decision_id=receipt.decision_id,
            requirement_id=requirement_id, actor_id=ACTOR,
            payload=_annotate_payload(snapshot, sha256, raw_text,
                                      revision=refresh.decision_revision),
        )
    assert backend.read_text(STATE_PATH) == before


def test_annotation_cannot_replace_the_requirement_quote_within_same_source_set(backend):
    receipt, snapshot, sha256, raw_text = _seed(backend)
    service = _service(backend)
    created = service.create_requirement(
        PROJECT, tenant_id=TENANT, decision_id=receipt.decision_id, actor_id=ACTOR,
        payload=_create_payload(snapshot, sha256, raw_text),
    )
    requirement_id = service.list_requirements(
        PROJECT, tenant_id=TENANT, decision_id=receipt.decision_id
    )[0]["requirement_id"]
    payload = _annotate_payload(
        snapshot, sha256, raw_text, revision=created.decision_revision
    ).model_copy(update={"quote_start": 2, "quote_end": 4, "quote": raw_text[2:4]})
    before = backend.read_text(STATE_PATH)
    with pytest.raises(ProcurementApplicabilityConflict):
        service.annotate_requirement(
            PROJECT, tenant_id=TENANT, decision_id=receipt.decision_id,
            requirement_id=requirement_id, actor_id=ACTOR, payload=payload,
        )
    assert backend.read_text(STATE_PATH) == before


def test_snapshot_bytes_drifting_after_preflight_are_rejected_inside_cas_change(
    backend, monkeypatch
):
    receipt, snapshot, sha256, raw_text = _seed(backend)
    store = ProcurementProjectStore(backend=backend)
    service = ProcurementApplicabilityService(store=store, backend=backend)
    original = store.mutate_requirement

    def drift_then_mutate(*args, **kwargs):
        backend.write_bytes(
            snapshot.storage_path,
            json.dumps(
                {"announcement": {"raw_text": raw_text}, "source": "changed"},
                ensure_ascii=False,
            ).encode("utf-8"),
            content_type="application/json",
        )
        return original(*args, **kwargs)

    monkeypatch.setattr(store, "mutate_requirement", drift_then_mutate)
    before = backend.read_text(STATE_PATH)
    with pytest.raises(ProcurementApplicabilityConflict):
        service.create_requirement(
            PROJECT, tenant_id=TENANT, decision_id=receipt.decision_id,
            actor_id=ACTOR, payload=_create_payload(snapshot, sha256, raw_text),
        )
    assert backend.read_text(STATE_PATH) == before


def test_calculation_notes_and_reimport_preserve_requirements(backend):
    receipt, snapshot, sha256, raw_text = _seed(backend)
    store = ProcurementProjectStore(backend=backend)
    service = ProcurementApplicabilityService(store=store, backend=backend)
    created = service.create_requirement(
        PROJECT, tenant_id=TENANT, decision_id=receipt.decision_id, actor_id=ACTOR,
        payload=_create_payload(snapshot, sha256, raw_text),
    )
    requirement_id = service.list_requirements(
        PROJECT, tenant_id=TENANT, decision_id=receipt.decision_id
    )[0]["requirement_id"]
    calculated = store.compute_decision(
        PROJECT, tenant_id=TENANT, decision_id=receipt.decision_id,
        action="recommend", expected_decision_revision=created.decision_revision,
        operation_id=str(uuid4()),
        compute=lambda record: record.model_copy(update={
            "recommendation": ProcurementRecommendation(value="GO", summary="unchanged")
        }),
    )
    noted = store.update_notes(
        PROJECT, tenant_id=TENANT, decision_id=receipt.decision_id,
        expected_decision_revision=calculated.decision_revision,
        operation_id=str(uuid4()),
        command_identity={"notes": "operator note"},
        update=lambda _notes: "operator note",
    )
    state = store.get(PROJECT, tenant_id=TENANT)
    reimport = ProcurementDecisionUpsert.model_validate(
        state.entries[0].record.model_dump(
            exclude={"decision_id", "created_at", "updated_at"}, mode="json"
        )
    )
    store.import_opportunity(
        reimport, expected_selection_revision=state.selection_revision,
        expected_decision_revision=noted.decision_revision,
        operation_id=str(uuid4()),
    )
    assert service.list_requirements(
        PROJECT, tenant_id=TENANT, decision_id=receipt.decision_id
    )[0]["requirement_id"] == requirement_id


def test_cas_race_has_one_write_and_loser_does_not_append_history(backend):
    receipt, snapshot, sha256, raw_text = _seed(backend)
    service = _service(backend)
    payloads = [
        _create_payload(snapshot, sha256, raw_text, operation_id=str(uuid4()))
        for _ in range(2)
    ]
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(
            service.create_requirement, PROJECT, tenant_id=TENANT,
            decision_id=receipt.decision_id, actor_id=ACTOR, payload=payload,
        ) for payload in payloads]
    outcomes = []
    for future in futures:
        try:
            outcomes.append(future.result())
        except ProcurementApplicabilityConflict:
            pass
    assert len(outcomes) == 1
    assert len(service.list_requirements(
        PROJECT, tenant_id=TENANT, decision_id=receipt.decision_id
    )) == 1


def test_legacy_record_json_is_unchanged_on_read(backend):
    legacy = ProcurementDecisionStore(backend=backend)
    legacy.upsert(ProcurementDecisionUpsert(
        tenant_id=TENANT, project_id=PROJECT,
        opportunity=NormalizedProcurementOpportunity(
            source_kind="g2b", source_id="legacy", title="legacy"
        ),
    ))
    before = backend.read_text(STATE_PATH)
    state = ProcurementProjectStore(backend=backend).get(PROJECT, tenant_id=TENANT)
    assert state.entries[0].requirements == []
    assert backend.read_text(STATE_PATH) == before
