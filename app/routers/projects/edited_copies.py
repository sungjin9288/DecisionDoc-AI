"""Session-bound edited-copy persistence; no provider or approval effects."""

from dataclasses import asdict
import logging

from fastapi import APIRouter, Depends, HTTPException, Request

from app.dependencies import (
    get_tenant_id,
    require_session_bound_generated_document_reviewer,
)
from app.observability.logging import log_event
from app.schemas.edited_project_copies import SaveEditedCopyRequest
from app.services.edited_project_copy_service import (
    EditedCopyConflict,
    save_edited_copy,
    source_hash,
)
from app.storage.project_state_mutation import ProjectStoreError
from app.storage.user_store import get_user_store

router = APIRouter(
    dependencies=[Depends(require_session_bound_generated_document_reviewer)]
)
logger = logging.getLogger("decisiondoc.edited_copies")


def _actor(request: Request):
    tenant = get_tenant_id(request)
    user = get_user_store(
        tenant,
        data_dir=request.app.state.data_dir,
        backend=request.app.state.state_backend,
    ).get_by_id(request.state.user_id)
    if (
        user is None
        or not user.is_active
        or user.username != request.state.username
        or user.role.value not in {"admin", "member"}
        or user.role.value != request.state.user_role
    ):
        raise HTTPException(403, "Current tenant membership required")
    return tenant, user.user_id


@router.get("/projects/{project_id}/documents/{doc_id}/editable-source")
def editable_source(project_id: str, doc_id: str, request: Request):
    tenant, _ = _actor(request)
    try:
        project = request.app.state.project_store.get(project_id, tenant_id=tenant)
        doc = (
            next((d for d in project.documents if d.doc_id == doc_id), None)
            if project
            else None
        )
        if doc is None:
            raise HTTPException(404, "Document not found")
        return {
            "document": asdict(doc),
            "parent_sha256": source_hash(doc),
            "project_id": project_id,
        }
    except ProjectStoreError as exc:
        raise HTTPException(503, "Project state unavailable") from exc


@router.post("/projects/{project_id}/documents/{doc_id}/edited-copies")
def save_copy(
    project_id: str, doc_id: str, payload: SaveEditedCopyRequest, request: Request
):
    tenant, actor = _actor(request)
    try:
        doc = save_edited_copy(
            request.app.state.project_store,
            tenant_id=tenant,
            actor_id=actor,
            project_id=project_id,
            parent_id=doc_id,
            payload=payload,
        )
    except KeyError as exc:
        raise HTTPException(404, "Document not found") from exc
    except EditedCopyConflict as exc:
        raise HTTPException(409, str(exc)) from exc
    except ProjectStoreError as exc:
        raise HTTPException(503, "Project state unavailable") from exc
    request.state.generated_document_review_project_id = project_id
    request.state.generated_document_review_document_id = doc.doc_id
    request.state.generated_document_review_operational_approval = False
    log_event(
        logger,
        {
            "event": "project.edited_copy.saved",
            "request_id": getattr(request.state, "request_id", ""),
            "project_id": project_id,
            "document_id": doc.doc_id,
        },
    )
    return {
        "document": asdict(doc),
        "project_id": project_id,
        "operation_id": payload.operation_id,
        "parent_sha256": source_hash(doc),
        "operational_approval": False,
    }
