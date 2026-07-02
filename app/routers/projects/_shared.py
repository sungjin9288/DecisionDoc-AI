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


def _serialize_meeting_recording_summary(recording) -> dict:
    payload = asdict(recording)
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
    if not getattr(request.app.state, "procurement_copilot_enabled", False):
        return payload

    service = getattr(request.app.state, "decision_council_service", None)
    procurement_store = getattr(request.app.state, "procurement_store", None)
    if service is None or procurement_store is None:
        return payload

    latest_session = service.get_latest_procurement_council(
        tenant_id=tenant_id,
        project_id=project.project_id,
    )
    if latest_session is not None:
        latest_session = service.attach_procurement_binding(
            session=latest_session,
            procurement_record=procurement_store.get(project.project_id, tenant_id=tenant_id),
        )

    for doc in payload.get("documents", []):
        status_meta = describe_procurement_council_document_status(
            bundle_id=str(doc.get("bundle_id") or ""),
            source_session_id=doc.get("source_decision_council_session_id"),
            source_session_revision=doc.get("source_decision_council_session_revision"),
            latest_session=latest_session,
        )
        if not status_meta:
            continue
        doc["decision_council_document_status"] = status_meta["status"]
        doc["decision_council_document_status_tone"] = status_meta["tone"]
        doc["decision_council_document_status_copy"] = status_meta["copy"]
        doc["decision_council_document_status_summary"] = status_meta["summary"]
    return payload
