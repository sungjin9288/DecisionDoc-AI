"""Decision-scoped requirement applicability with exact source evidence."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from app.schemas import ProcurementHardFilterStatus
from app.schemas.procurement_binding import ProcurementSourceBinding
from app.schemas.procurement_applicability import (
    AnnotateProcurementRequirementRequest,
    CreateProcurementRequirementRequest,
    ProcurementApplicabilityAnnotation,
    ProcurementRequirement,
)
from app.services.procurement_decision.checklist import (
    CHECKLIST_CATEGORY_HARD_FILTER_CODES,
)
from app.services.procurement_opportunity_service import ProcurementOpportunityNotFound
from app.services.procurement_source_binding import capture_procurement_source_binding
from app.storage.procurement_project_state import (
    ProcurementDecisionEntry,
    ProcurementMutationReceipt,
)
from app.storage.procurement_project_store import (
    ProcurementProjectConflict,
    ProcurementProjectStore,
)
from app.storage.procurement_store import ProcurementDecisionStoreError, _unique_object
from app.storage.state_backend import StateBackend, StateBackendError


class ProcurementApplicabilityNotFound(ProcurementOpportunityNotFound):
    pass


class ProcurementApplicabilityConflict(ProcurementProjectConflict):
    pass


@dataclass(frozen=True)
class CapturedProcurementRequirements:
    entry: ProcurementDecisionEntry
    binding: ProcurementSourceBinding
    source_set_sha256: str


def redact_requirement_actors(requirements: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {**{key: value for key, value in item.items() if key != "created_by_actor_id"},
         "annotations": [{key: value for key, value in event.items() if key != "actor_id"}
                         for event in item["annotations"]]}
        for item in requirements
    ]


class ProcurementApplicabilityService:
    def __init__(self, *, store: ProcurementProjectStore, backend: StateBackend) -> None:
        self.store = store
        self._backend = backend

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def _entry(
        self, project_id: str, *, tenant_id: str, decision_id: str
    ) -> ProcurementDecisionEntry:
        project = self.store.get(project_id, tenant_id=tenant_id)
        if project is not None:
            for entry in project.entries:
                if entry.record.decision_id == decision_id:
                    return entry
        raise ProcurementApplicabilityNotFound("Procurement opportunity not found")

    def _read_snapshot(self, storage_path: str) -> bytes:
        try:
            raw = self._backend.read_bytes(storage_path)
        except StateBackendError as exc:
            raise ProcurementDecisionStoreError(
                "Cannot read procurement source snapshot"
            ) from exc
        if raw is None:
            raise ProcurementDecisionStoreError("Procurement source snapshot is missing")
        return raw

    def capture(
        self, project_id: str, *, tenant_id: str, decision_id: str,
        expected_revision: int | None = None,
    ) -> CapturedProcurementRequirements:
        entry = self._entry(project_id, tenant_id=tenant_id, decision_id=decision_id)
        if expected_revision is not None and entry.decision_revision != expected_revision:
            raise ProcurementApplicabilityConflict("Procurement revision changed")
        try:
            binding = capture_procurement_source_binding(entry, backend=self._backend)
        except ProcurementDecisionStoreError:
            raise
        except ValueError as exc:
            raise ProcurementDecisionStoreError("Procurement source unavailable") from exc
        fingerprints = [item.model_dump(mode="json") for item in binding.snapshots]
        source_set_sha256 = hashlib.sha256(json.dumps(
            fingerprints, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")).hexdigest()
        return CapturedProcurementRequirements(entry, binding, source_set_sha256)

    def assert_current(self, captured: CapturedProcurementRequirements) -> None:
        binding = captured.binding
        current = self.capture(
            binding.project_id, tenant_id=binding.tenant_id, decision_id=binding.decision_id,
            expected_revision=binding.decision_revision,
        )
        if current != captured:
            raise ProcurementApplicabilityConflict("Procurement requirements or source changed")

    @staticmethod
    def project_requirements(captured: CapturedProcurementRequirements) -> list[dict[str, Any]]:
        return ProcurementApplicabilityService._project_requirements(
            captured.entry, captured.source_set_sha256,
        )

    @staticmethod
    def export_projection(captured: CapturedProcurementRequirements) -> dict[str, Any]:
        return {
            "schema_version": "procurement.requirement_applicability.v1",
            "decision_id": captured.binding.decision_id,
            "decision_revision": captured.binding.decision_revision,
            "source_set_sha256": captured.source_set_sha256,
            "requirements": redact_requirement_actors(
                ProcurementApplicabilityService.project_requirements(captured),
            ),
        }

    def list_sources(self, captured: CapturedProcurementRequirements) -> list[dict[str, str]]:
        sources = []
        for snapshot, fingerprint in zip(captured.entry.record.source_snapshots, captured.binding.snapshots):
            raw = self._read_snapshot(snapshot.storage_path)
            if hashlib.sha256(raw).hexdigest() != fingerprint.sha256:
                raise ProcurementApplicabilityConflict("Procurement source changed")
            try:
                payload = json.loads(raw, object_pairs_hook=_unique_object)
                raw_text = payload["announcement"]["raw_text"]
                if not isinstance(raw_text, str):
                    raise ValueError("Missing raw text")
            except (ValueError, UnicodeError, TypeError, KeyError) as exc:
                raise ProcurementDecisionStoreError("Procurement source text unavailable") from exc
            sources.append({"snapshot_id": snapshot.snapshot_id,
                            "snapshot_sha256": fingerprint.sha256, "raw_text": raw_text})
        self.assert_current(captured)
        return sources

    def _capture_source_set(
        self, entry: ProcurementDecisionEntry
    ) -> tuple[str, dict[str, bytes]]:
        fingerprints = []
        contents: dict[str, bytes] = {}
        for snapshot in entry.record.source_snapshots:
            raw = self._read_snapshot(snapshot.storage_path)
            contents[snapshot.snapshot_id] = raw
            fingerprints.append(
                {
                    "snapshot_id": snapshot.snapshot_id,
                    "sha256": hashlib.sha256(raw).hexdigest(),
                    "size_bytes": len(raw),
                }
            )
        encoded = json.dumps(
            fingerprints,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest(), contents

    def _source_set_sha256(self, entry: ProcurementDecisionEntry) -> str:
        return self._capture_source_set(entry)[0]

    def _validate_source(
        self,
        entry: ProcurementDecisionEntry,
        *,
        snapshot_id: str,
        snapshot_sha256: str,
        quote_start: int,
        quote_end: int,
        quote: str,
    ) -> str:
        if not any(
            item.snapshot_id == snapshot_id for item in entry.record.source_snapshots
        ):
            raise ProcurementApplicabilityConflict(
                "Procurement source snapshot is not in the current source set"
            )
        source_set_sha256, contents = self._capture_source_set(entry)
        raw = contents[snapshot_id]
        if hashlib.sha256(raw).hexdigest() != snapshot_sha256:
            raise ProcurementApplicabilityConflict("Procurement source snapshot changed")
        try:
            payload = json.loads(raw, object_pairs_hook=_unique_object)
            raw_text = payload["announcement"]["raw_text"]
        except (UnicodeError, json.JSONDecodeError, TypeError, KeyError, ValueError) as exc:
            raise ProcurementApplicabilityConflict(
                "Procurement source snapshot has no announcement raw text"
            ) from exc
        if not isinstance(raw_text, str):
            raise ProcurementApplicabilityConflict(
                "Procurement source snapshot has no announcement raw text"
            )
        if quote_end > len(raw_text) or raw_text[quote_start:quote_end] != quote:
            raise ProcurementApplicabilityConflict(
                "Procurement source quote does not match exact snapshot text"
            )
        return source_set_sha256

    @staticmethod
    def _request_payload(
        payload: CreateProcurementRequirementRequest
        | AnnotateProcurementRequirementRequest,
    ) -> dict[str, Any]:
        return payload.model_dump(mode="json")

    def _replay(
        self,
        project_id: str,
        *,
        tenant_id: str,
        decision_id: str,
        actor_id: str,
        action: str,
        payload: CreateProcurementRequirementRequest
        | AnnotateProcurementRequirementRequest,
    ) -> ProcurementMutationReceipt | None:
        request = self._request_payload(payload)
        try:
            return self.store.replay_requirement_operation(
                project_id,
                tenant_id=tenant_id,
                operation_id=payload.operation_id,
                action=action,
                decision_id=decision_id,
                expected_decision_revision=payload.expected_decision_revision,
                actor_id=actor_id,
                payload=request,
            )
        except ProcurementProjectConflict as exc:
            raise ProcurementApplicabilityConflict(str(exc)) from exc

    def create_requirement(
        self,
        project_id: str,
        *,
        tenant_id: str,
        decision_id: str,
        actor_id: str,
        payload: CreateProcurementRequirementRequest,
    ) -> ProcurementMutationReceipt:
        payload = CreateProcurementRequirementRequest.model_validate(
            payload.model_dump(mode="json")
        )
        replay = self._replay(
            project_id,
            tenant_id=tenant_id,
            decision_id=decision_id,
            actor_id=actor_id,
            action="create_requirement",
            payload=payload,
        )
        if replay is not None:
            return replay
        entry = self._entry(project_id, tenant_id=tenant_id, decision_id=decision_id)
        if entry.decision_revision != payload.expected_decision_revision:
            raise ProcurementApplicabilityConflict("Procurement revision changed")
        if payload.category not in CHECKLIST_CATEGORY_HARD_FILTER_CODES:
            raise ValueError("Unsupported procurement requirement category")
        source_set_sha256 = self._validate_source(
            entry,
            snapshot_id=payload.snapshot_id,
            snapshot_sha256=payload.snapshot_sha256,
            quote_start=payload.quote_start,
            quote_end=payload.quote_end,
            quote=payload.quote,
        )

        def change(current: ProcurementDecisionEntry) -> None:
            confirmed_source_set = self._validate_source(
                current,
                snapshot_id=payload.snapshot_id,
                snapshot_sha256=payload.snapshot_sha256,
                quote_start=payload.quote_start,
                quote_end=payload.quote_end,
                quote=payload.quote,
            )
            if confirmed_source_set != source_set_sha256:
                raise ProcurementApplicabilityConflict(
                    "Procurement source set changed during requirement creation"
                )
            current.requirements.append(
                ProcurementRequirement(
                    requirement_id=str(uuid4()),
                    title=payload.title,
                    category=payload.category,
                    snapshot_id=payload.snapshot_id,
                    snapshot_sha256=payload.snapshot_sha256,
                    source_set_sha256=source_set_sha256,
                    quote_start=payload.quote_start,
                    quote_end=payload.quote_end,
                    quote=payload.quote,
                    created_by_actor_id=actor_id,
                    created_at=self._now(),
                )
            )

        request = self._request_payload(payload)
        try:
            return self.store.mutate_requirement(
                project_id,
                tenant_id=tenant_id,
                decision_id=decision_id,
                expected_decision_revision=payload.expected_decision_revision,
                operation_id=payload.operation_id,
                actor_id=actor_id,
                action="create_requirement",
                payload=request,
                change=change,
            )
        except ProcurementProjectConflict as exc:
            raise ProcurementApplicabilityConflict(str(exc)) from exc

    @staticmethod
    def _require_not_applicable_allowed(
        entry: ProcurementDecisionEntry, requirement: ProcurementRequirement
    ) -> None:
        expected_codes = CHECKLIST_CATEGORY_HARD_FILTER_CODES[requirement.category]
        by_code: dict[str, list[Any]] = {
            code: [item for item in entry.record.hard_filters if item.code == code]
            for code in expected_codes
        }
        if any(
            len(items) != 1
            or items[0].status != ProcurementHardFilterStatus.PASS
            for items in by_code.values()
        ):
            raise ProcurementApplicabilityConflict(
                "Related hard filters must each have one passing result"
            )
        if any(
            item.category == requirement.category and item.status == "blocked"
            for item in entry.record.checklist_items
        ):
            raise ProcurementApplicabilityConflict(
                "Blocked checklist category cannot be marked not applicable"
            )

    def annotate_requirement(
        self,
        project_id: str,
        *,
        tenant_id: str,
        decision_id: str,
        requirement_id: str,
        actor_id: str,
        payload: AnnotateProcurementRequirementRequest,
    ) -> ProcurementMutationReceipt:
        payload = AnnotateProcurementRequirementRequest.model_validate(
            payload.model_dump(mode="json")
        )
        action = "annotate_requirement"
        request = {"requirement_id": requirement_id, **self._request_payload(payload)}
        try:
            replay = self.store.replay_requirement_operation(
                project_id,
                tenant_id=tenant_id,
                operation_id=payload.operation_id,
                action=action,
                decision_id=decision_id,
                expected_decision_revision=payload.expected_decision_revision,
                actor_id=actor_id,
                payload=request,
            )
        except ProcurementProjectConflict as exc:
            raise ProcurementApplicabilityConflict(str(exc)) from exc
        if replay is not None:
            return replay
        entry = self._entry(project_id, tenant_id=tenant_id, decision_id=decision_id)
        if entry.decision_revision != payload.expected_decision_revision:
            raise ProcurementApplicabilityConflict("Procurement revision changed")
        requirement = next(
            (
                item
                for item in entry.requirements
                if item.requirement_id == requirement_id
            ),
            None,
        )
        if requirement is None:
            raise ProcurementApplicabilityNotFound("Procurement requirement not found")
        if (
            payload.snapshot_id,
            payload.snapshot_sha256,
            payload.quote_start,
            payload.quote_end,
            payload.quote,
        ) != (
            requirement.snapshot_id,
            requirement.snapshot_sha256,
            requirement.quote_start,
            requirement.quote_end,
            requirement.quote,
        ):
            raise ProcurementApplicabilityConflict(
                "Applicability annotation cannot replace requirement source evidence"
            )
        source_set_sha256 = self._validate_source(
            entry,
            snapshot_id=payload.snapshot_id,
            snapshot_sha256=payload.snapshot_sha256,
            quote_start=payload.quote_start,
            quote_end=payload.quote_end,
            quote=payload.quote,
        )
        if requirement.source_set_sha256 != source_set_sha256:
            raise ProcurementApplicabilityConflict(
                "Procurement requirement source set is stale"
            )
        if payload.applicability == "not_applicable":
            self._require_not_applicable_allowed(entry, requirement)

        def change(current: ProcurementDecisionEntry) -> None:
            target = next(
                item
                for item in current.requirements
                if item.requirement_id == requirement_id
            )
            confirmed_source_set = self._validate_source(
                current,
                snapshot_id=payload.snapshot_id,
                snapshot_sha256=payload.snapshot_sha256,
                quote_start=payload.quote_start,
                quote_end=payload.quote_end,
                quote=payload.quote,
            )
            if (
                confirmed_source_set != source_set_sha256
                or target.source_set_sha256 != confirmed_source_set
            ):
                raise ProcurementApplicabilityConflict(
                    "Procurement source set changed during applicability annotation"
                )
            target.annotations.append(
                ProcurementApplicabilityAnnotation(
                    annotation_id=str(uuid4()),
                    applicability=payload.applicability,
                    rationale=payload.rationale,
                    snapshot_id=payload.snapshot_id,
                    snapshot_sha256=payload.snapshot_sha256,
                    source_set_sha256=source_set_sha256,
                    quote_start=payload.quote_start,
                    quote_end=payload.quote_end,
                    quote=payload.quote,
                    actor_id=actor_id,
                    created_at=self._now(),
                    expected_decision_revision=payload.expected_decision_revision,
                    operation_id=payload.operation_id,
                )
            )

        try:
            return self.store.mutate_requirement(
                project_id,
                tenant_id=tenant_id,
                decision_id=decision_id,
                expected_decision_revision=payload.expected_decision_revision,
                operation_id=payload.operation_id,
                actor_id=actor_id,
                action=action,
                payload=request,
                change=change,
            )
        except ProcurementProjectConflict as exc:
            raise ProcurementApplicabilityConflict(str(exc)) from exc

    def list_requirements(
        self, project_id: str, *, tenant_id: str, decision_id: str
    ) -> list[dict[str, Any]]:
        entry = self._entry(project_id, tenant_id=tenant_id, decision_id=decision_id)
        source_set_sha256 = self._source_set_sha256(entry)
        return self._project_requirements(entry, source_set_sha256)

    @staticmethod
    def _project_requirements(entry: ProcurementDecisionEntry, source_set_sha256: str) -> list[dict[str, Any]]:
        result = []
        for requirement in entry.requirements:
            stale = requirement.source_set_sha256 != source_set_sha256
            if requirement.annotations and not stale:
                latest = requirement.annotations[-1]
                stale = latest.source_set_sha256 != source_set_sha256
                applicability = "unknown" if stale else latest.applicability
            else:
                applicability = "unknown"
            item = requirement.model_dump(mode="json")
            item.update({"applicability": applicability, "stale": stale})
            result.append(item)
        return result
