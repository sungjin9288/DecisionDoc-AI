"""Decision-pinned generation inputs; no project-selection fallback for multi-source work."""

from dataclasses import dataclass
import hashlib

from app.schemas import ProcurementDecisionRecord
from app.schemas.procurement_binding import ProcurementSourceBinding
from app.services.procurement_source_binding import capture_procurement_source_binding
from app.services.procurement_decision_package.json_helpers import (
    load_json_object_content,
)
from app.storage.procurement_project_store import ProcurementProjectStore
from app.storage.procurement_store import ProcurementDecisionStoreError
from app.storage.state_backend import StateBackend, StateBackendError


class ProcurementGenerationError(ValueError):
    def __init__(self, code: str, *, status_code: int = 409):
        super().__init__(code)
        self.code = code
        self.status_code = status_code


@dataclass(frozen=True)
class CapturedProcurementSource:
    record: ProcurementDecisionRecord
    binding: ProcurementSourceBinding
    latest_snapshot: dict


class ProcurementGenerationResolver:
    def __init__(self, *, store: ProcurementProjectStore, backend: StateBackend):
        self.store = store
        self.backend = backend

    def capture(
        self,
        project_id: str,
        *,
        tenant_id: str,
        decision_id: str | None,
        expected_revision: int | None,
    ) -> CapturedProcurementSource | None:
        try:
            project = self.store.get(project_id, tenant_id=tenant_id)
            if project is None or not project.entries:
                if decision_id is not None:
                    raise ProcurementGenerationError(
                        "procurement_opportunity_not_found", status_code=404
                    )
                return None
            if decision_id is None:
                if len(project.entries) != 1:
                    raise ProcurementGenerationError(
                        "procurement_opportunity_selection_required"
                    )
                entry = project.entries[0]
            else:
                entry = next(
                    (
                        item
                        for item in project.entries
                        if item.record.decision_id == decision_id
                    ),
                    None,
                )
                if entry is None:
                    raise ProcurementGenerationError(
                        "procurement_opportunity_not_found", status_code=404
                    )
            if (
                expected_revision is not None
                and entry.decision_revision != expected_revision
            ):
                raise ProcurementGenerationError("procurement_context_changed")
            binding = capture_procurement_source_binding(entry, backend=self.backend)
            content = self.backend.read_bytes(
                entry.record.source_snapshots[-1].storage_path
            )
            fingerprint = binding.snapshots[-1]
            if (
                content is None
                or len(content) != fingerprint.size_bytes
                or hashlib.sha256(content).hexdigest() != fingerprint.sha256
            ):
                raise ProcurementGenerationError("procurement_context_changed")
            latest = load_json_object_content(
                content, label="procurement generation source"
            )
            return CapturedProcurementSource(entry.record, binding, latest)
        except ProcurementGenerationError:
            raise
        except (ValueError, ProcurementDecisionStoreError, StateBackendError) as exc:
            raise ProcurementGenerationError(
                "procurement_source_unavailable", status_code=503
            ) from exc

    def assert_current(self, source: CapturedProcurementSource) -> None:
        binding = source.binding
        current = self.capture(
            binding.project_id,
            tenant_id=binding.tenant_id,
            decision_id=binding.decision_id,
            expected_revision=binding.decision_revision,
        )
        if current is None or current.binding != binding:
            raise ProcurementGenerationError("procurement_context_changed")

    def describe_binding(
        self, binding: dict | ProcurementSourceBinding | None
    ) -> dict[str, str]:
        if binding is None:
            return {"status": "unknown", "reason_code": "procurement_source_unbound"}
        try:
            if isinstance(binding, ProcurementSourceBinding):
                binding = binding.model_dump(mode="json")
            pinned = ProcurementSourceBinding.model_validate(binding)
            current = self.capture(
                pinned.project_id,
                tenant_id=pinned.tenant_id,
                decision_id=pinned.decision_id,
                expected_revision=pinned.decision_revision,
            )
            if current is not None and current.binding == pinned:
                return {
                    "status": "current",
                    "reason_code": "procurement_source_matches",
                }
            return {"status": "stale", "reason_code": "procurement_context_changed"}
        except ProcurementGenerationError as exc:
            return {
                "status": "unknown" if exc.status_code == 503 else "stale",
                "reason_code": exc.code,
            }
