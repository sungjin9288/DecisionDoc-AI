"""Strict downstream handling for persisted procurement document provenance."""
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from app.schemas.procurement_binding import ProcurementSourceBinding


_STATUSES = {"current", "stale", "unknown"}


@dataclass(frozen=True)
class ProcurementDocumentBindingResolution:
    binding: dict[str, Any] | None
    status: str
    reason_code: str
    record: object | None = None
    current_binding: dict[str, Any] | None = None


def normalize_procurement_document_binding(
    value: object,
    *,
    tenant_id: str | None = None,
    project_id: str | None = None,
) -> dict[str, Any] | None:
    """Return one canonical JSON binding and enforce its trusted scope."""
    if value is None:
        return None
    binding = ProcurementSourceBinding.model_validate(value)
    if tenant_id is not None and binding.tenant_id != tenant_id:
        raise ValueError("Procurement document binding tenant mismatch")
    if project_id is not None and binding.project_id != project_id:
        raise ValueError("Procurement document binding project mismatch")
    return binding.model_dump(mode="json")


def source_binding_from_documents(
    docs: list[dict[str, Any]],
    *,
    tenant_id: str | None = None,
    project_id: str | None = None,
) -> dict[str, Any] | None:
    """Require generated docs to omit binding together or carry one exact binding."""
    if not isinstance(docs, list) or not docs or any(not isinstance(doc, dict) for doc in docs):
        raise ValueError("Generated documents are invalid")
    raw_bindings = [doc.get("source_procurement_binding") for doc in docs]
    present = [value is not None for value in raw_bindings]
    if not any(present):
        return None
    if not all(present):
        raise ValueError("Generated document procurement bindings are incomplete")
    bindings = [
        normalize_procurement_document_binding(
            value,
            tenant_id=tenant_id,
            project_id=project_id,
        )
        for value in raw_bindings
    ]
    first = bindings[0]
    if first is None or any(binding != first for binding in bindings[1:]):
        raise ValueError("Generated document procurement bindings are inconsistent")
    return first


def validate_project_document_binding(
    value: object,
    *,
    docs: list[dict[str, Any]],
    tenant_id: str,
    project_id: str,
    allow_unembedded: bool = False,
) -> dict[str, Any] | None:
    """Validate server-supplied project provenance without inferring client claims."""
    binding = normalize_procurement_document_binding(
        value,
        tenant_id=tenant_id,
        project_id=project_id,
    )
    if binding is None:
        if isinstance(docs, list) and any(
            isinstance(doc, dict) and doc.get("source_procurement_binding") is not None
            for doc in docs
        ):
            raise ValueError("Project document binding requires trusted server provenance")
        return None
    embedded = source_binding_from_documents(
        docs,
        tenant_id=tenant_id,
        project_id=project_id,
    )
    if embedded is None:
        if allow_unembedded:
            return binding
        raise ValueError("Project document binding is missing from generated documents")
    if embedded != binding:
        raise ValueError("Project document binding does not match generated documents")
    return binding


def describe_procurement_document_binding(
    value: object,
    *,
    resolver: object | None,
) -> dict[str, str]:
    """Describe freshness without consulting a project-selected opportunity."""
    binding = normalize_procurement_document_binding(value)
    if binding is None:
        return {"status": "unknown", "reason_code": "source_binding_absent"}
    if resolver is None:
        return {"status": "unknown", "reason_code": "resolver_unavailable"}
    describe = getattr(resolver, "describe_binding", None)
    if not callable(describe):
        return {"status": "unknown", "reason_code": "resolver_unavailable"}
    try:
        result = describe(ProcurementSourceBinding.model_validate(binding))
    except Exception:
        return {"status": "unknown", "reason_code": "resolver_failed"}
    if not isinstance(result, Mapping):
        return {"status": "unknown", "reason_code": "resolver_result_invalid"}
    status = result.get("status")
    reason_code = result.get("reason_code")
    if status not in _STATUSES or not isinstance(reason_code, str):
        return {"status": "unknown", "reason_code": "resolver_result_invalid"}
    return {"status": status, "reason_code": reason_code}


def resolve_procurement_document_binding(
    value: object,
    *,
    resolver: object | None,
) -> ProcurementDocumentBindingResolution:
    """Resolve the exact bound decision without consulting project selection."""
    binding = normalize_procurement_document_binding(value)
    described = describe_procurement_document_binding(binding, resolver=resolver)
    if binding is None or resolver is None:
        return ProcurementDocumentBindingResolution(
            binding=binding,
            status=described["status"],
            reason_code=described["reason_code"],
        )

    capture = getattr(resolver, "capture", None)
    if not callable(capture):
        return ProcurementDocumentBindingResolution(
            binding=binding,
            status="unknown",
            reason_code="resolver_capture_unavailable",
        )
    try:
        captured = capture(
            binding["project_id"],
            tenant_id=binding["tenant_id"],
            decision_id=binding["decision_id"],
            expected_revision=None,
        )
        if captured is None:
            raise ValueError("Bound procurement source is missing")
        current_binding = normalize_procurement_document_binding(
            getattr(captured, "binding", None),
            tenant_id=binding["tenant_id"],
            project_id=binding["project_id"],
        )
        record = getattr(captured, "record", None)
        if (
            current_binding is None
            or getattr(record, "tenant_id", None) != binding["tenant_id"]
            or getattr(record, "project_id", None) != binding["project_id"]
            or getattr(record, "decision_id", None) != binding["decision_id"]
        ):
            raise ValueError("Resolved procurement source identity mismatch")
    except Exception:
        status = described["status"]
        reason_code = described["reason_code"]
        if status == "current":
            status = "unknown"
            reason_code = "resolver_capture_failed"
        return ProcurementDocumentBindingResolution(
            binding=binding,
            status=status,
            reason_code=reason_code,
        )

    status = described["status"]
    reason_code = described["reason_code"]
    if status == "current" and current_binding != binding:
        status = "stale"
        reason_code = "procurement_context_changed"
    return ProcurementDocumentBindingResolution(
        binding=binding,
        status=status,
        reason_code=reason_code,
        record=record,
        current_binding=current_binding,
    )


def binding_sha256(value: object) -> str:
    binding = normalize_procurement_document_binding(value)
    if binding is None:
        return ""
    content = json.dumps(
        binding,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(content).hexdigest()


def resolver_from_app_state(state: object) -> object | None:
    service = getattr(state, "service", None)
    return getattr(service, "procurement_generation_resolver", None)
