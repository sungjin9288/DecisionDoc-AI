"""CAS-backed v2 procurement store for explicit multi-opportunity app instances."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Callable
from uuid import uuid4

from app.schemas import ProcurementDecisionRecord, ProcurementDecisionUpsert
from app.storage.conditional_state import persist_text_if_current
from app.storage.procurement_project_state import (
    ProcurementDecisionEntry,
    ProcurementMutationReceipt,
    ProcurementProjectState,
    decode_project,
    require_operation_id,
    require_revision,
)
from app.storage.procurement_store import (
    ProcurementDecisionStore,
    ProcurementDecisionStoreError,
    _require_path_segment,
    validate_procurement_record,
)
from app.storage.state_backend import StateBackend, StateBackendError
from app.tenant import require_tenant_id


class ProcurementProjectConflict(ProcurementDecisionStoreError):
    """The caller must refresh state; its command must not be silently rebased."""


class ProcurementProjectStore:
    def __init__(self, *, backend: StateBackend) -> None:
        self._backend = backend

    @staticmethod
    def _path(tenant_id: str) -> str:
        return f"tenants/{require_tenant_id(tenant_id)}/procurement_decisions.json"

    @staticmethod
    def _projects(rows: list[Any], tenant_id: str) -> dict[str, tuple[int, ProcurementProjectState]]:
        projects = {}
        decisions: set[str] = set()
        for index, row in enumerate(rows):
            if not isinstance(row, dict) or row.get("tenant_id") != tenant_id:
                continue
            project = decode_project(row, tenant_id=tenant_id, project_id=row.get("project_id"))
            if project.project_id in projects:
                raise ProcurementDecisionStoreError("Duplicate procurement project records")
            for entry in project.entries:
                if entry.record.decision_id in decisions:
                    raise ProcurementDecisionStoreError("Duplicate procurement decision records")
                decisions.add(entry.record.decision_id)
            projects[project.project_id] = (index, project)
        return projects

    def _read(self, tenant_id: str) -> tuple[str | None, list[Any], dict[str, tuple[int, ProcurementProjectState]]]:
        try:
            raw = self._backend.read_text(self._path(tenant_id))
            rows = [] if raw is None else ProcurementDecisionStore._decode_records(raw)
            return raw, rows, self._projects(rows, tenant_id)
        except (StateBackendError, UnicodeError) as exc:
            raise ProcurementDecisionStoreError("Cannot read procurement project state") from exc

    def get(self, project_id: str, *, tenant_id: str) -> ProcurementProjectState | None:
        _require_path_segment(project_id, field="project_id")
        _, _, projects = self._read(tenant_id)
        found = projects.get(project_id)
        return found[1] if found else None

    @staticmethod
    def _entry(project: ProcurementProjectState, decision_id: str) -> ProcurementDecisionEntry:
        for entry in project.entries:
            if entry.record.decision_id == decision_id:
                return entry
        raise ProcurementProjectConflict("Procurement decision not found in project")

    @staticmethod
    def _expect(actual: int, expected: int) -> None:
        if actual != expected:
            raise ProcurementProjectConflict("Procurement revision changed")

    @staticmethod
    def _replay(project: ProcurementProjectState, operation_id: str, digest: str) -> ProcurementMutationReceipt | None:
        for receipt in project.receipts:
            if receipt.operation_id == operation_id:
                if receipt.request_sha256 != digest:
                    raise ProcurementProjectConflict("Procurement operation ID reused with different input")
                return receipt
        return None

    @staticmethod
    def _command_digest(
        *,
        tenant_id: str,
        project_id: str,
        command: dict[str, Any],
    ) -> str:
        encoded = json.dumps(
            {"tenant_id": tenant_id, "project_id": project_id, **command},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    def replay_operation(
        self,
        project_id: str,
        *,
        tenant_id: str,
        operation_id: str,
        command: dict[str, Any],
    ) -> ProcurementMutationReceipt | None:
        """Return an exact prior receipt without executing command side effects."""
        require_operation_id(operation_id)
        _require_path_segment(project_id, field="project_id")
        require_tenant_id(tenant_id)
        digest = self._command_digest(
            tenant_id=tenant_id,
            project_id=project_id,
            command=command,
        )
        project = self.get(project_id, tenant_id=tenant_id)
        return self._replay(project, operation_id, digest) if project else None

    def assert_import_preconditions(
        self,
        project_id: str,
        *,
        tenant_id: str,
        expected_selection_revision: int,
        expected_decision_revision: int | None = None,
        source_kind: str | None = None,
        source_id: str | None = None,
    ) -> None:
        """Fail stale imports before collector, provider, or snapshot side effects."""
        require_revision(expected_selection_revision)
        _require_path_segment(project_id, field="project_id")
        require_tenant_id(tenant_id)
        if (source_kind is None) != (source_id is None):
            raise ValueError("source_kind and source_id must be provided together")
        if expected_decision_revision is None:
            if source_kind is not None:
                raise ValueError("expected_decision_revision is required for source checks")
        else:
            require_revision(expected_decision_revision)

        project = self.get(project_id, tenant_id=tenant_id)
        selection_revision = project.selection_revision if project else 0
        self._expect(selection_revision, expected_selection_revision)
        if source_kind is None:
            return

        entry = next(
            (
                item
                for item in (project.entries if project else [])
                if item.record.opportunity is not None
                and (
                    item.record.opportunity.source_kind,
                    item.record.opportunity.source_id,
                )
                == (source_kind, source_id)
            ),
            None,
        )
        self._expect(
            entry.decision_revision if entry else 0,
            expected_decision_revision,
        )

    def _mutate(
        self, *, tenant_id: str, project_id: str, operation_id: str,
        command: dict[str, Any], change: Callable[[ProcurementProjectState], ProcurementDecisionEntry],
    ) -> ProcurementMutationReceipt:
        require_operation_id(operation_id)
        _require_path_segment(project_id, field="project_id")
        require_tenant_id(tenant_id)
        digest = self._command_digest(
            tenant_id=tenant_id,
            project_id=project_id,
            command=command,
        )
        expected, rows, projects = self._read(tenant_id)
        found = projects.get(project_id)
        project = found[1] if found else ProcurementProjectState(tenant_id=tenant_id, project_id=project_id)
        prior = self._replay(project, operation_id, digest)
        if prior is not None:
            return prior
        entry = change(project)
        receipt = ProcurementMutationReceipt(
            operation_id=operation_id, request_sha256=digest, decision_id=entry.record.decision_id,
            decision_revision=entry.decision_revision, selection_revision=project.selection_revision,
        )
        project.receipts.append(receipt)
        payload = project.model_dump(mode="json")
        decode_project(payload, tenant_id=tenant_id, project_id=project_id)
        if found:
            rows[found[0]] = payload
        else:
            rows.append(payload)
        self._projects(rows, tenant_id)

        def decode(raw: str) -> dict[str, tuple[int, ProcurementProjectState]]:
            return self._projects(ProcurementDecisionStore._decode_records(raw), tenant_id)

        def committed(observed: dict[str, tuple[int, ProcurementProjectState]]) -> bool:
            current = observed.get(project_id)
            return current is not None and self._replay(current[1], operation_id, digest) == receipt

        try:
            saved = persist_text_if_current(
                backend=self._backend, relative_path=self._path(tenant_id), expected=expected,
                replacement=json.dumps(rows, ensure_ascii=False, indent=2, allow_nan=False),
                decode=decode, committed=committed, decode_errors=(ProcurementDecisionStoreError,),
            )
        except StateBackendError as exc:
            raise ProcurementDecisionStoreError("Procurement write outcome could not be verified") from exc
        if not saved:
            # A concurrent identical command may have won; never repeat the write.
            current = self.get(project_id, tenant_id=tenant_id)
            prior = self._replay(current, operation_id, digest) if current else None
            if prior is not None:
                return prior
            raise ProcurementProjectConflict("Procurement state changed during conditional write")
        return receipt

    def import_opportunity(
        self, payload: ProcurementDecisionUpsert, *, expected_selection_revision: int,
        expected_decision_revision: int, operation_id: str,
        request_identity: dict[str, Any] | None = None,
    ) -> ProcurementMutationReceipt:
        require_revision(expected_selection_revision)
        require_revision(expected_decision_revision)
        payload = ProcurementDecisionUpsert.model_validate(payload.model_dump(mode="json"))
        if payload.opportunity is None:
            raise ValueError("An imported opportunity is required")
        if payload.schema_version != "v1":
            raise ValueError("Unsupported procurement decision schema")
        snapshot_ids = [snapshot.snapshot_id for snapshot in payload.source_snapshots]
        if len(snapshot_ids) != len(set(snapshot_ids)):
            raise ValueError("Duplicate procurement source snapshot metadata")

        def change(project: ProcurementProjectState) -> ProcurementDecisionEntry:
            self._expect(project.selection_revision, expected_selection_revision)
            source = (payload.opportunity.source_kind, payload.opportunity.source_id)
            entry = next((item for item in project.entries if item.record.opportunity is None or
                          (item.record.opportunity.source_kind, item.record.opportunity.source_id) == source), None)
            self._expect(entry.decision_revision if entry else 0, expected_decision_revision)
            now = datetime.now(timezone.utc).isoformat()
            previous = entry.record if entry else None
            snapshots = list(previous.source_snapshots) if previous else []
            by_id = {snapshot.snapshot_id: snapshot for snapshot in snapshots}
            for snapshot in payload.source_snapshots:
                if snapshot.snapshot_id in by_id:
                    if by_id[snapshot.snapshot_id] != snapshot:
                        raise ProcurementProjectConflict("Source snapshot metadata changed")
                else:
                    snapshots.append(snapshot)
                    by_id[snapshot.snapshot_id] = snapshot
            imported = ProcurementDecisionUpsert(
                tenant_id=payload.tenant_id, project_id=payload.project_id,
                schema_version=previous.schema_version if previous else payload.schema_version,
                opportunity=payload.opportunity, source_snapshots=snapshots,
                notes=payload.notes or (previous.notes if previous else ""),
            )
            record = validate_procurement_record({
                **imported.model_dump(mode="json"), "decision_id": previous.decision_id if previous else str(uuid4()),
                "created_at": previous.created_at if previous else now, "updated_at": now,
            })
            if entry:
                entry.record = record
                entry.decision_revision += 1
            else:
                entry = ProcurementDecisionEntry(record=record)
                project.entries.append(entry)
            if project.active_decision_id != record.decision_id:
                project.active_decision_id = record.decision_id
                project.selection_revision += 1
            return entry

        command = self.import_command(
            payload=payload,
            expected_selection_revision=expected_selection_revision,
            expected_decision_revision=expected_decision_revision,
            request_identity=request_identity,
        )
        return self._mutate(
            tenant_id=payload.tenant_id, project_id=payload.project_id, operation_id=operation_id,
            command=command,
            change=change,
        )

    @staticmethod
    def import_command(
        *,
        payload: ProcurementDecisionUpsert | None,
        expected_selection_revision: int,
        expected_decision_revision: int,
        request_identity: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if request_identity is None:
            if payload is None:
                raise ValueError("payload is required without request_identity")
            import_payload: dict[str, Any] = payload.model_dump(mode="json")
        else:
            import_payload = dict(request_identity)
        return {
            "action": "import",
            "payload": import_payload,
            "expected_selection_revision": expected_selection_revision,
            "expected_decision_revision": expected_decision_revision,
        }

    def update_notes(
        self,
        project_id: str,
        *,
        tenant_id: str,
        decision_id: str,
        expected_decision_revision: int,
        operation_id: str,
        command_identity: dict[str, Any],
        update: Callable[[str], str],
    ) -> ProcurementMutationReceipt:
        require_revision(expected_decision_revision)
        _require_path_segment(decision_id, field="decision_id")

        def change(project: ProcurementProjectState) -> ProcurementDecisionEntry:
            entry = self._entry(project, decision_id)
            self._expect(entry.decision_revision, expected_decision_revision)
            notes = update(entry.record.notes)
            if not isinstance(notes, str):
                raise ValueError("Updated procurement notes must be text")
            entry.record = entry.record.model_copy(
                update={
                    "notes": notes,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                },
                deep=True,
            )
            return entry

        return self._mutate(
            tenant_id=tenant_id,
            project_id=project_id,
            operation_id=operation_id,
            command={
                "action": "update_notes",
                "decision_id": decision_id,
                "expected_decision_revision": expected_decision_revision,
                "command_identity": command_identity,
            },
            change=change,
        )

    @staticmethod
    def requirement_command(
        *,
        action: str,
        decision_id: str,
        expected_decision_revision: int,
        actor_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        if action not in {"create_requirement", "annotate_requirement"}:
            raise ValueError("Unsupported procurement requirement mutation")
        if not isinstance(actor_id, str) or not actor_id.strip():
            raise ValueError("actor_id must not be blank")
        return {
            "action": action,
            "decision_id": decision_id,
            "expected_decision_revision": expected_decision_revision,
            "actor_id": actor_id,
            "payload": payload,
        }

    def replay_requirement_operation(
        self,
        project_id: str,
        *,
        tenant_id: str,
        operation_id: str,
        action: str,
        decision_id: str,
        expected_decision_revision: int,
        actor_id: str,
        payload: dict[str, Any],
    ) -> ProcurementMutationReceipt | None:
        command = self.requirement_command(
            action=action,
            decision_id=decision_id,
            expected_decision_revision=expected_decision_revision,
            actor_id=actor_id,
            payload=payload,
        )
        return self.replay_operation(
            project_id,
            tenant_id=tenant_id,
            operation_id=operation_id,
            command=command,
        )

    def mutate_requirement(
        self,
        project_id: str,
        *,
        tenant_id: str,
        decision_id: str,
        expected_decision_revision: int,
        operation_id: str,
        actor_id: str,
        action: str,
        payload: dict[str, Any],
        change: Callable[[ProcurementDecisionEntry], None],
    ) -> ProcurementMutationReceipt:
        require_revision(expected_decision_revision)
        _require_path_segment(decision_id, field="decision_id")
        command = self.requirement_command(
            action=action,
            decision_id=decision_id,
            expected_decision_revision=expected_decision_revision,
            actor_id=actor_id,
            payload=payload,
        )

        def mutate(project: ProcurementProjectState) -> ProcurementDecisionEntry:
            entry = self._entry(project, decision_id)
            self._expect(entry.decision_revision, expected_decision_revision)
            change(entry)
            entry.decision_revision += 1
            return entry

        return self._mutate(
            tenant_id=tenant_id,
            project_id=project_id,
            operation_id=operation_id,
            command=command,
            change=mutate,
        )

    def select(
        self, project_id: str, *, tenant_id: str, decision_id: str,
        expected_selection_revision: int, operation_id: str,
    ) -> ProcurementMutationReceipt:
        require_revision(expected_selection_revision)
        _require_path_segment(decision_id, field="decision_id")

        def change(project: ProcurementProjectState) -> ProcurementDecisionEntry:
            self._expect(project.selection_revision, expected_selection_revision)
            entry = self._entry(project, decision_id)
            if project.active_decision_id != decision_id:
                project.active_decision_id = decision_id
                project.selection_revision += 1
            return entry

        return self._mutate(
            tenant_id=tenant_id, project_id=project_id, operation_id=operation_id,
            command={"action": "select", "decision_id": decision_id,
                     "expected_selection_revision": expected_selection_revision}, change=change,
        )

    def save_evaluation(
        self, record: ProcurementDecisionRecord, *, expected_decision_revision: int, operation_id: str,
    ) -> ProcurementMutationReceipt:
        require_revision(expected_decision_revision)
        record = validate_procurement_record(record.model_dump(mode="json"))

        def change(project: ProcurementProjectState) -> ProcurementDecisionEntry:
            entry = self._entry(project, record.decision_id)
            self._expect(entry.decision_revision, expected_decision_revision)
            before = entry.record
            if record.opportunity != before.opportunity or record.source_snapshots != before.source_snapshots:
                raise ProcurementProjectConflict("Evaluation cannot replace source evidence")
            entry.record = record.model_copy(update={
                "created_at": before.created_at, "schema_version": before.schema_version,
                "notes": before.notes, "updated_at": datetime.now(timezone.utc).isoformat(),
            }, deep=True)
            entry.decision_revision += 1
            return entry

        return self._mutate(
            tenant_id=record.tenant_id, project_id=record.project_id, operation_id=operation_id,
            command={"action": "evaluate", "record": record.model_dump(mode="json"),
                     "expected_decision_revision": expected_decision_revision}, change=change,
        )

    def compute_decision(
        self, project_id: str, *, tenant_id: str, decision_id: str,
        action: str, expected_decision_revision: int, operation_id: str,
        compute: Callable[[ProcurementDecisionRecord], ProcurementDecisionRecord],
    ) -> ProcurementMutationReceipt:
        """Replay by command identity before running a time-dependent calculation."""
        require_revision(expected_decision_revision)
        _require_path_segment(decision_id, field="decision_id")
        if action not in {"evaluate", "recommend"}:
            raise ValueError("Unsupported procurement calculation")

        def change(project: ProcurementProjectState) -> ProcurementDecisionEntry:
            entry = self._entry(project, decision_id)
            self._expect(entry.decision_revision, expected_decision_revision)
            before = entry.record
            result = validate_procurement_record(compute(before.model_copy(deep=True)).model_dump(mode="json"))
            if (result.decision_id, result.tenant_id, result.project_id) != (decision_id, tenant_id, project_id):
                raise ProcurementProjectConflict("Calculation cannot replace decision identity")
            if result.opportunity != before.opportunity or result.source_snapshots != before.source_snapshots:
                raise ProcurementProjectConflict("Calculation cannot replace source evidence")
            entry.record = result.model_copy(update={
                "created_at": before.created_at, "schema_version": before.schema_version,
                "notes": before.notes, "updated_at": datetime.now(timezone.utc).isoformat(),
            }, deep=True)
            entry.decision_revision += 1
            return entry

        return self._mutate(
            tenant_id=tenant_id, project_id=project_id, operation_id=operation_id,
            command={"action": action, "decision_id": decision_id,
                     "expected_decision_revision": expected_decision_revision}, change=change,
        )
