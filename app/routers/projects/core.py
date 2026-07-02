"""app/routers/projects/core.py — Project CRUD, search, stats, archive, and document endpoints.

Extracted from app/routers/projects.py (moved verbatim; no behavior changes).
"""
from __future__ import annotations

import json as _json
import re
import urllib.parse
from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response

from app.auth.api_key import require_api_key
from app.dependencies import get_tenant_id, get_user_id, require_admin
from app.schemas import AddDocumentToProjectRequest, CreateProjectRequest, UpdateProjectRequest
from app.services.docx_service import build_docx
from app.services.excel_service import build_excel
from app.services.hwp_service import build_hwp

from app.routers.projects._shared import _load_pdf_builder, _resolve_gov_options, _serialize_project_detail

import logging

logger = logging.getLogger("decisiondoc.projects")

router = APIRouter()


@router.post("/projects", dependencies=[Depends(require_api_key)])
def create_project_endpoint(payload: CreateProjectRequest, request: Request) -> dict:
    """Create a new project."""
    tenant_id = get_tenant_id(request)
    project_store = request.app.state.project_store
    proj = project_store.create(
        tenant_id=tenant_id,
        name=payload.name,
        description=payload.description,
        client=payload.client,
        contract_number=payload.contract_number,
        fiscal_year=payload.fiscal_year,
    )
    return asdict(proj)


@router.get("/projects/search", dependencies=[Depends(require_api_key)])
def search_projects_endpoint(
    request: Request,
    q: str = "",
    fiscal_year: int | None = None,
) -> dict:
    """Search projects by name, client, document title, tags."""
    tenant_id = get_tenant_id(request)
    if not q:
        return {"results": []}
    project_store = request.app.state.project_store
    results = project_store.search(tenant_id, q, fiscal_year=fiscal_year)
    return {"results": results}


@router.get("/projects/stats", dependencies=[Depends(require_api_key)])
def project_stats_endpoint(request: Request) -> dict:
    """Get project dashboard stats."""
    tenant_id = get_tenant_id(request)
    project_store = request.app.state.project_store
    return project_store.get_stats(tenant_id)


@router.get("/projects/archive/{fiscal_year}", dependencies=[Depends(require_api_key)])
def project_archive_endpoint(fiscal_year: int, request: Request) -> dict:
    """Get yearly archive summary."""
    tenant_id = get_tenant_id(request)
    project_store = request.app.state.project_store
    return project_store.get_yearly_archive(tenant_id, fiscal_year)


@router.get("/projects", dependencies=[Depends(require_api_key)])
def list_projects_endpoint(
    request: Request,
    status: str | None = None,
    fiscal_year: int | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict:
    """List projects for the current tenant with pagination."""
    tenant_id = get_tenant_id(request)
    project_store = request.app.state.project_store
    projects = project_store.list_by_tenant(tenant_id, status=status, fiscal_year=fiscal_year)
    total = len(projects)
    limit = max(1, min(limit, 200))
    paginated = projects[offset: offset + limit]
    return {
        "projects": [asdict(p) for p in paginated],
        "total": total,
        "limit": limit,
        "offset": offset,
        "has_more": (offset + limit) < total,
    }


@router.get("/projects/{project_id}", dependencies=[Depends(require_api_key)])
def get_project_endpoint(project_id: str, request: Request) -> dict:
    """Get project detail with all documents."""
    tenant_id = get_tenant_id(request)
    project_store = request.app.state.project_store
    proj = project_store.get(project_id, tenant_id=tenant_id)
    if proj is None:
        raise HTTPException(status_code=404, detail=f"프로젝트를 찾을 수 없습니다: {project_id}")
    return _serialize_project_detail(request, tenant_id=tenant_id, project=proj)


@router.patch("/projects/{project_id}", dependencies=[Depends(require_api_key)])
def update_project_endpoint(project_id: str, payload: UpdateProjectRequest, request: Request) -> dict:
    """Update project fields."""
    tenant_id = get_tenant_id(request)
    project_store = request.app.state.project_store
    try:
        proj = project_store.update(
            project_id,
            tenant_id=tenant_id,
            **{k: v for k, v in payload.model_dump().items() if v is not None}
        )
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return asdict(proj)


@router.delete("/projects/{project_id}", dependencies=[Depends(require_api_key)])
def delete_project_endpoint(project_id: str, request: Request) -> dict:
    """Permanently delete a project (admin only). Documents are unlinked, not deleted."""
    require_admin(request)
    tenant_id = get_tenant_id(request)
    project_store = request.app.state.project_store
    try:
        project_store.delete(project_id, tenant_id=tenant_id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    logger.info(
        "[Project] Deleted project %s by user %s",
        project_id,
        get_user_id(request),
    )
    return {"message": "프로젝트가 삭제되었습니다.", "project_id": project_id}


@router.post("/projects/{project_id}/archive", dependencies=[Depends(require_api_key)])
def archive_project_endpoint(project_id: str, request: Request) -> dict:
    """Archive a project."""
    tenant_id = get_tenant_id(request)
    project_store = request.app.state.project_store
    try:
        proj = project_store.archive(project_id, tenant_id=tenant_id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return asdict(proj)


@router.post("/projects/{project_id}/documents", dependencies=[Depends(require_api_key)])
def add_document_to_project_endpoint(
    project_id: str, payload: AddDocumentToProjectRequest, request: Request
) -> dict:
    """Manually add a document to a project."""
    tenant_id = get_tenant_id(request)
    project_store = request.app.state.project_store
    try:
        doc = project_store.add_document(
            project_id=project_id,
            request_id=payload.request_id,
            bundle_id=payload.bundle_id,
            title=payload.title,
            docs=payload.docs,
            approval_id=payload.approval_id,
            tags=payload.tags,
            tenant_id=tenant_id,
        )
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return asdict(doc)


@router.delete("/projects/{project_id}/documents/{doc_id}", dependencies=[Depends(require_api_key)])
def remove_document_from_project_endpoint(
    project_id: str, doc_id: str, request: Request
) -> dict:
    """Remove a document from a project."""
    tenant_id = get_tenant_id(request)
    project_store = request.app.state.project_store
    try:
        project_store.remove_document(project_id, doc_id, tenant_id=tenant_id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"ok": True}


@router.get(
    "/projects/{project_id}/documents/{doc_id}/download/{fmt}",
    dependencies=[Depends(require_api_key)],
)
async def download_project_doc_endpoint(
    project_id: str, doc_id: str, fmt: str, request: Request
) -> Response:
    """Download a specific project document."""
    tenant_id = get_tenant_id(request)
    project_store = request.app.state.project_store
    proj = project_store.get(project_id, tenant_id=tenant_id)
    if proj is None:
        raise HTTPException(status_code=404, detail=f"프로젝트를 찾을 수 없습니다: {project_id}")
    doc = next((d for d in proj.documents if d.doc_id == doc_id), None)
    if doc is None:
        raise HTTPException(status_code=404, detail=f"문서를 찾을 수 없습니다: {doc_id}")
    try:
        docs = _json.loads(doc.doc_snapshot)
    except Exception:
        docs = []
    gov_opts = _resolve_gov_options(doc.gov_options)
    title = doc.title
    safe_title = re.sub(r'[\\/*?:"<>|]', "_", title)[:100]
    encoded_title = urllib.parse.quote(safe_title, safe="")
    fmt_lower = fmt.lower().lstrip(".")
    if fmt_lower == "docx":
        content = build_docx(docs, title=title, gov_options=gov_opts)
        media_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        ext = "docx"
    elif fmt_lower == "pdf":
        build_pdf = _load_pdf_builder()
        content = await build_pdf(docs, title=title, gov_options=gov_opts)
        media_type = "application/pdf"
        ext = "pdf"
    elif fmt_lower in ("hwp", "hwpx"):
        content = build_hwp(docs, title=title, gov_options=gov_opts)
        media_type = "application/hwp+zip"
        ext = "hwpx"
    elif fmt_lower in ("excel", "xlsx"):
        content = build_excel(docs, title=title)
        media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ext = "xlsx"
    else:
        raise HTTPException(status_code=400, detail=f"지원하지 않는 포맷: {fmt}")
    return Response(
        content=content,
        media_type=media_type,
        headers={
            "Content-Disposition": (
                f'attachment; filename="document.{ext}"; '
                f"filename*=UTF-8''{encoded_title}.{ext}"
            )
        },
    )
