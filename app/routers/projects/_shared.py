"""app/routers/projects/_shared.py — Cross-cutting helpers for the projects router package.

Extracted from app/routers/projects.py (moved verbatim; no behavior changes).
These helpers are used by more than one domain sub-router (core, meeting
recordings, procurement) so they live here to avoid circular imports between
sibling sub-modules.
"""
from __future__ import annotations

from dataclasses import asdict

from fastapi import HTTPException, Request

from app.services.decision_council_service import (
    describe_procurement_council_document_status,
)
from app.services.meeting_recording_service import TRANSCRIPTION_FAILED_MESSAGE
from app.services.procurement_review_handoff import (
    describe_procurement_review_document_status,
    load_validated_procurement_review_evidence,
)
from app.services.procurement_document_binding import (
    resolve_procurement_document_binding,
    resolver_from_app_state,
)
from app.schemas.procurement_binding import ProcurementSourceBinding


def _resolve_gov_options(gov_options_dict: dict | None):
    if not gov_options_dict:
        return None
    try:
        from app.schemas import GovDocOptions
        return GovDocOptions(**gov_options_dict)
    except Exception:
        return None


def _load_pdf_builder():
    try:
        from app.services.pdf_service import build_pdf as _build_pdf
    except ImportError as exc:
        raise HTTPException(
            status_code=503,
            detail="PDF export is not available in this deployment.",
        ) from exc
    return _build_pdf


def _serialize_meeting_recording(recording) -> dict:
    payload = asdict(recording)
    if payload.get("transcript_error"):
        payload["transcript_error"] = TRANSCRIPTION_FAILED_MESSAGE
    return payload


def _serialize_meeting_recording_summary(recording) -> dict:
    payload = _serialize_meeting_recording(recording)
    transcript = payload.pop("transcript_text", "") or ""
    payload["transcript_preview"] = transcript[:400]
    payload["has_transcript"] = bool(transcript.strip())
    return payload


def _serialize_project_detail(
    request: Request,
    *,
    tenant_id: str,
    project,
) -> dict:
    payload = asdict(project)
    meeting_recording_store = getattr(request.app.state, "meeting_recording_store", None)
    if meeting_recording_store is not None:
        payload["meeting_recordings"] = [
            _serialize_meeting_recording_summary(recording)
            for recording in meeting_recording_store.list_by_project(
                tenant_id=tenant_id,
                project_id=project.project_id,
            )
        ]
    payload["documents"] = _serialize_project_documents(
        request,
        tenant_id=tenant_id,
        project=project,
    )
    return payload


def _serialize_project_documents(
    request: Request,
    *,
    tenant_id: str,
    project,
) -> list[dict]:
    documents = asdict(project).get("documents", [])
    resolver = resolver_from_app_state(request.app.state)
    resolved_documents = []
    for doc in documents:
        source = resolve_procurement_document_binding(
            doc.get("source_procurement_binding"),
            resolver=resolver,
        )
        doc["source_procurement_binding_status"] = source.status
        doc["source_procurement_binding_reason_code"] = source.reason_code
        resolved_documents.append((doc, source))
    if not getattr(request.app.state, "procurement_copilot_enabled", False):
        return documents

    service = getattr(request.app.state, "decision_council_service", None)
    procurement_store = getattr(request.app.state, "procurement_store", None)
    legacy_procurement_record = None
    legacy_latest_session = None
    if resolver is None and procurement_store is not None:
        legacy_procurement_record = procurement_store.get(
            project.project_id,
            tenant_id=tenant_id,
        )
    if resolver is None and service is not None:
        legacy_latest_session = service.get_latest_procurement_council(
            tenant_id=tenant_id,
            project_id=project.project_id,
        )
        if legacy_latest_session is not None:
            legacy_latest_session = service.attach_procurement_binding(
                session=legacy_latest_session,
                procurement_record=legacy_procurement_record,
            )

    review_store = getattr(request.app.state, "procurement_review_store", None)

    for doc, source in resolved_documents:
        source_binding = source.binding
        procurement_record = (
            source.record
            if source_binding is not None
            else legacy_procurement_record
        )
        latest_session = legacy_latest_session
        if service is not None and source_binding is not None:
            latest_session = service.get_latest_procurement_council(
                tenant_id=tenant_id,
                project_id=project.project_id,
                decision_id=source_binding["decision_id"],
            )
            if latest_session is not None:
                current_binding = (
                    ProcurementSourceBinding.model_validate(source.current_binding)
                    if source.current_binding is not None
                    else None
                )
                latest_session = service.attach_procurement_binding(
                    session=latest_session,
                    procurement_record=procurement_record,
                    source_binding=current_binding,
                )
                stored_binding = ProcurementSourceBinding.model_validate(source_binding)
                if latest_session.source_binding != stored_binding:
                    latest_session = latest_session.model_copy(
                        update={
                            "current_procurement_binding_status": "stale",
                            "current_procurement_binding_reason_code": (
                                "document_procurement_binding_mismatch"
                            ),
                            "current_procurement_binding_summary": (
                                "Council source binding does not match the saved "
                                "document source binding."
                            ),
                        }
                    )
        status_meta = describe_procurement_council_document_status(
            bundle_id=str(doc.get("bundle_id") or ""),
            source_session_id=doc.get("source_decision_council_session_id"),
            source_session_revision=doc.get("source_decision_council_session_revision"),
            latest_session=latest_session,
        )
        if status_meta:
            doc["decision_council_document_status"] = status_meta["status"]
            doc["decision_council_document_status_tone"] = status_meta["tone"]
            doc["decision_council_document_status_copy"] = status_meta["copy"]
            doc["decision_council_document_status_summary"] = status_meta["summary"]

        packet_sha256 = str(
            doc.get("source_procurement_review_packet_sha256") or ""
        ).strip()
        review_record = None
        if review_store is not None and packet_sha256:
            try:
                review_record = load_validated_procurement_review_evidence(
                    review_store,
                    tenant_id=tenant_id,
                    project_id=project.project_id,
                    packet_sha256=packet_sha256,
                )
            except ValueError:
                review_record = None
        review_status_meta = describe_procurement_review_document_status(
            bundle_id=str(doc.get("bundle_id") or ""),
            packet_sha256=packet_sha256 or None,
            source_updated_at=doc.get("source_procurement_review_source_updated_at"),
            source_decision=doc.get("source_procurement_review_decision"),
            review_record=review_record,
            procurement_record=procurement_record,
        )
        if (
            review_status_meta
            and review_status_meta["status"] == "current"
            and source_binding is not None
            and source.status != "current"
        ):
            review_status_meta = {
                "status": (
                    "stale_procurement_review"
                    if source.status == "stale"
                    else "review_source_unverified"
                ),
                "tone": "danger" if source.status == "stale" else "warning",
                "copy": (
                    "현재 procurement 대비 이전 review 기준"
                    if source.status == "stale"
                    else "검토 source 확인 필요"
                ),
                "summary": (
                    "문서의 procurement source binding이 현재 source와 일치하지 "
                    "않아 timestamp만으로 review를 current로 판정할 수 없습니다."
                ),
            }
        if not review_status_meta:
            continue
        doc["procurement_review_document_status"] = review_status_meta["status"]
        doc["procurement_review_document_status_tone"] = review_status_meta["tone"]
        doc["procurement_review_document_status_copy"] = review_status_meta["copy"]
        doc["procurement_review_document_status_summary"] = review_status_meta["summary"]
    return documents
