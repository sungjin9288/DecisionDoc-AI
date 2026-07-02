"""app/routers/generate/export.py — Document export / binary-format endpoints.

Split out of the former app/routers/generate.py (2,170 lines) to keep each
sub-module under the file-size limit. Covers:
  POST /generate/export
  POST /generate/pptx
  POST /generate/visual-assets
  POST /generate/stream
  POST /generate/docx
  POST /generate/pdf
  POST /generate/excel
  POST /generate/hwp
  POST /generate/export-edited
  GET  /generate/export-zip

Pure code relocation — no behavior changes.
"""
from __future__ import annotations

import asyncio
import io
import json
import logging
import re
import threading
import urllib.parse
import zipfile
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response, StreamingResponse

from app.ai_profiles.catalog import ensure_bundle_access
from app.auth.api_key import require_api_key
from app.dependencies import require_auth as _require_auth
from app.maintenance.mode import require_not_maintenance
from app.observability.logging import log_event
from app.observability.timing import Timer
from app.providers.factory import get_provider_for_bundle
from app.schemas import (
    EditedExportRequest,
    GenerateExportResponse,
    GenerateRequest,
    GenerateResponse,
    GenerateVisualAssetsRequest,
    GenerateVisualAssetsResponse,
)
from app.services.docx_service import build_docx
from app.services.excel_service import build_excel
from app.services.hwp_service import build_hwp
from app.services.pptx_service import build_pptx_from_docs

from app.routers.generate._shared import (
    _apply_generate_state,
    _build_generate_log_event,
    _build_structured_slide_data,
    _ensure_procurement_bundle_enabled,
    _ensure_procurement_override_reason_for_downstream,
    _generate_visual_assets_for_docs,
    _get_zip_docs,
    _load_pdf_builder,
    _mark_decision_council_handoff_context,
    _mark_procurement_downstream_resolved_context,
    _resolve_gov_options,
)

logger = logging.getLogger("decisiondoc.generate")

router = APIRouter(tags=["generate"])


def _facade():
    """Return the `app.routers.generate` package module.

    Some existing tests patch library functions (``generate_visual_assets_from_docs``,
    ``build_docx``, ``build_pptx``) via
    ``unittest.mock.patch("app.routers.generate.<name>", ...)`` — a pattern
    written against the pre-split single-file module. Looking these up on the
    facade module at call time keeps those patches effective after the split.
    """
    import app.routers.generate as _generate_pkg

    return _generate_pkg


@router.post(
    "/generate/export",
    response_model=GenerateExportResponse,
    dependencies=[Depends(require_not_maintenance), Depends(require_api_key)],
)
def generate_export(
    payload: GenerateRequest,
    request: Request,
) -> GenerateExportResponse:
    # Keep sync endpoints to avoid nested event-loop issues because providers use anyio.run internally.
    _ensure_procurement_bundle_enabled(payload.bundle_type, request)
    service = request.app.state.service
    storage = request.app.state.storage
    template_version = request.app.state.template_version
    request_id = request.state.request_id
    tenant_id = getattr(request.state, "tenant_id", "system") or "system"
    ensure_bundle_access(request, payload.bundle_type)
    _ensure_procurement_override_reason_for_downstream(payload, request, tenant_id=tenant_id)
    _mark_procurement_downstream_resolved_context(payload, request, tenant_id=tenant_id)
    result = service.generate_documents(payload, request_id=request_id, tenant_id=tenant_id)
    docs = result["docs"]
    bundle_id = result["metadata"]["bundle_id"]
    export_timer = Timer()
    with export_timer.measure("export_ms"):
        # Pre-compute all file metadata before any writes to keep files/paths consistent
        planned = [
            {
                "doc_type": doc["doc_type"],
                "markdown": doc["markdown"],
                "path": storage.get_export_path(bundle_id, doc["doc_type"]),
            }
            for doc in docs
        ]
        for item in planned:
            storage.save_export(bundle_id, item["doc_type"], item["markdown"])
        files = [{"doc_type": item["doc_type"], "path": item["path"]} for item in planned]
        export_dir = storage.get_export_dir(bundle_id)

    _apply_generate_state(request, result, template_version)
    request.state.export_ms = export_timer.durations_ms.get("export_ms")

    log_event_data = _build_generate_log_event(request, result, request_id, template_version)
    log_event_data["export_ms"] = request.state.export_ms
    log_event(logger, log_event_data)

    metadata = result["metadata"]
    return GenerateExportResponse(
        request_id=request_id,
        bundle_id=bundle_id,
        title=payload.title,
        provider=metadata["provider"],
        schema_version=metadata["schema_version"],
        cache_hit=metadata["cache_hit"],
        export_dir=str(export_dir),
        files=files,
    )


@router.post(
    "/generate/pptx",
    dependencies=[Depends(require_not_maintenance), Depends(require_api_key)],
)
def generate_pptx_endpoint(
    payload: GenerateRequest,
    request: Request,
) -> Response:
    """Generate a PPTX download from presentation bundles or rendered docs."""
    service = request.app.state.service
    template_version = request.app.state.template_version
    request_id = request.state.request_id
    tenant_id = getattr(request.state, "tenant_id", "system") or "system"
    ensure_bundle_access(request, payload.bundle_type)
    _ensure_procurement_override_reason_for_downstream(payload, request, tenant_id=tenant_id)
    _mark_procurement_downstream_resolved_context(payload, request, tenant_id=tenant_id)
    result = service.generate_documents(payload, request_id=request_id, tenant_id=tenant_id)
    _apply_generate_state(request, result, template_version)
    log_event(logger, _build_generate_log_event(request, result, request_id, template_version))

    safe_title = re.sub(r'[\\/*?:"<>|]', "_", payload.title)[:100]
    encoded_title = urllib.parse.quote(safe_title, safe="")
    structured_slide_data = None
    visual_assets: list[dict[str, Any]] = []
    if payload.bundle_type == "presentation_kr" and isinstance(result["raw_bundle"].get("slide_structure"), dict):
        structured_slide_data = result["raw_bundle"].get("slide_structure", {})
    else:
        structured_slide_data = _build_structured_slide_data(result["raw_bundle"], payload.goal)

    if structured_slide_data is not None:
        try:
            visual_assets = _facade().generate_visual_assets_from_docs(
                [
                    {
                        "doc_type": payload.bundle_type,
                        "slide_outline": structured_slide_data.get("slide_outline", []),
                    }
                ],
                title=payload.title,
                goal=payload.goal,
                provider=get_provider_for_bundle(payload.bundle_type, tenant_id),
                request_id=request_id,
                max_assets=min(6, max(1, len(structured_slide_data.get("slide_outline", []) or []))),
            )
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("[VisualAssets] PPT visual asset generation failed: %s", exc)
        pptx_bytes = _facade().build_pptx(
            structured_slide_data,
            title=payload.title,
            include_outline_overview=payload.bundle_type != "presentation_kr",
            visual_assets=visual_assets,
        )
    else:
        pptx_bytes = build_pptx_from_docs(result["docs"], title=payload.title)

    return Response(
        content=pptx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        headers={
            "Content-Disposition": (
                f"attachment; filename=\"presentation.pptx\"; "
                f"filename*=UTF-8''{encoded_title}.pptx"
            )
        },
    )


@router.post(
    "/generate/visual-assets",
    response_model=GenerateVisualAssetsResponse,
    dependencies=[Depends(require_not_maintenance), Depends(require_api_key)],
)
def generate_visual_assets_endpoint(
    payload: GenerateVisualAssetsRequest,
    request: Request,
) -> GenerateVisualAssetsResponse:
    """Generate reusable visual assets from slide_outline metadata."""
    tenant_id = getattr(request.state, "tenant_id", "system") or "system"
    assets = _facade().generate_visual_assets_from_docs(
        [doc.model_dump() for doc in payload.docs],
        title=payload.title,
        goal=payload.goal,
        provider=get_provider_for_bundle(payload.bundle_type, tenant_id),
        request_id=request.state.request_id,
        max_assets=payload.max_assets,
    )
    return GenerateVisualAssetsResponse(
        title=payload.title,
        bundle_type=payload.bundle_type,
        count=len(assets),
        assets=assets,
    )


@router.post(
    "/generate/stream",
    dependencies=[Depends(require_not_maintenance), Depends(require_api_key)],
)
async def generate_stream(
    payload: GenerateRequest,
    request: Request,
) -> StreamingResponse:
    """SSE streaming endpoint — yields progress events every 2 s, then the final result."""
    _ensure_procurement_bundle_enabled(payload.bundle_type, request)
    service = request.app.state.service
    template_version = request.app.state.template_version
    project_store = request.app.state.project_store
    request_id = request.state.request_id
    tenant_id = getattr(request.state, "tenant_id", "system") or "system"
    ensure_bundle_access(request, payload.bundle_type)
    _ensure_procurement_override_reason_for_downstream(payload, request, tenant_id=tenant_id)
    _mark_procurement_downstream_resolved_context(payload, request, tenant_id=tenant_id)
    _mark_decision_council_handoff_context(payload, request, tenant_id=tenant_id)
    loop = asyncio.get_event_loop()
    q: asyncio.Queue = asyncio.Queue()

    def _worker() -> None:
        try:
            result = service.generate_documents(payload, request_id=request_id, tenant_id=tenant_id)
            loop.call_soon_threadsafe(q.put_nowait, ("done", result))
        except Exception as exc:  # noqa: BLE001
            loop.call_soon_threadsafe(q.put_nowait, ("error", exc))

    async def _event_stream():
        threading.Thread(target=_worker, daemon=True).start()
        _STEPS = [
            "AI가 문서를 생성하는 중...",
            "번들 스키마를 검증하는 중...",
            "문서를 렌더링하는 중...",
            "품질 검사를 수행하는 중...",
        ]
        step = 0
        while True:
            try:
                event_type, data = await asyncio.wait_for(q.get(), timeout=2.0)
            except asyncio.TimeoutError:
                msg = _STEPS[step % len(_STEPS)]
                step += 1
                yield f"event: progress\ndata: {json.dumps({'step': step, 'msg': msg})}\n\n"
                if step > 80:  # 160 s hard limit
                    yield (
                        f"event: error\ndata: "
                        f"{json.dumps({'code': 'STREAM_TIMEOUT', 'message': '응답 시간 초과'})}\n\n"
                    )
                    return
                continue

            if event_type == "done":
                result = data
                _apply_generate_state(request, result, template_version)
                log_event(
                    logger,
                    _build_generate_log_event(request, result, request_id, template_version),
                )
                metadata = result["metadata"]
                resp = GenerateResponse(
                    request_id=request_id,
                    bundle_id=metadata["bundle_id"],
                    title=payload.title,
                    provider=metadata["provider"],
                    schema_version=metadata["schema_version"],
                    cache_hit=metadata["cache_hit"],
                    llm_total_tokens=metadata.get("llm_total_tokens"),
                    applied_references=metadata.get("applied_references", []),
                    docs=result["docs"],
                )
                yield f"event: complete\ndata: {resp.model_dump_json()}\n\n"
                # Auto-link to project if project_id provided
                if getattr(payload, "project_id", None):
                    try:
                        project_store.add_document(
                            project_id=payload.project_id,
                            request_id=request_id,
                            bundle_id=payload.bundle_type,
                            title=payload.title,
                            docs=result["docs"],
                            approval_id=None,
                            tags=[],
                            source_decision_council_session_id=metadata.get("decision_council_session_id"),
                            source_decision_council_session_revision=metadata.get("decision_council_session_revision"),
                            source_decision_council_direction=metadata.get("decision_council_direction"),
                        )
                    except Exception:
                        pass  # project link is non-critical
                return
            else:  # error
                err = json.dumps({"code": type(data).__name__, "message": str(data)})
                yield f"event: error\ndata: {err}\n\n"
                return

    return StreamingResponse(
        _event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post(
    "/generate/docx",
    dependencies=[Depends(require_not_maintenance), Depends(require_api_key)],
)
def generate_docx_endpoint(
    payload: GenerateRequest,
    request: Request,
) -> Response:
    """Generate a .docx from any bundle and return it as a download."""
    _ensure_procurement_bundle_enabled(payload.bundle_type, request)
    service = request.app.state.service
    template_version = request.app.state.template_version
    request_id = request.state.request_id
    tenant_id = getattr(request.state, "tenant_id", "system") or "system"
    ensure_bundle_access(request, payload.bundle_type)
    _ensure_procurement_override_reason_for_downstream(payload, request, tenant_id=tenant_id)
    _mark_procurement_downstream_resolved_context(payload, request, tenant_id=tenant_id)
    result = service.generate_documents(payload, request_id=request_id, tenant_id=tenant_id)
    _apply_generate_state(request, result, template_version)
    log_event(logger, _build_generate_log_event(request, result, request_id, template_version))

    safe_title = re.sub(r'[\\/*?:"<>|]', "_", payload.title)[:100]
    encoded_title = urllib.parse.quote(safe_title, safe="")
    visual_assets = _generate_visual_assets_for_docs(
        result["docs"],
        title=payload.title,
        goal=payload.goal,
        bundle_type=payload.bundle_type,
        tenant_id=tenant_id,
        request_id=request_id,
    )
    docx_bytes = _facade().build_docx(result["docs"], title=payload.title, gov_options=None, visual_assets=visual_assets)

    return Response(
        content=docx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={
            "Content-Disposition": (
                f"attachment; filename=\"document.docx\"; "
                f"filename*=UTF-8''{encoded_title}.docx"
            )
        },
    )


@router.post(
    "/generate/pdf",
    dependencies=[Depends(require_not_maintenance), Depends(require_api_key)],
)
async def generate_pdf_endpoint(
    payload: GenerateRequest,
    request: Request,
) -> Response:
    """Generate a PDF from any bundle via Playwright and return as download."""
    _ensure_procurement_bundle_enabled(payload.bundle_type, request)
    service = request.app.state.service
    template_version = request.app.state.template_version
    request_id = request.state.request_id
    tenant_id = getattr(request.state, "tenant_id", "system") or "system"
    ensure_bundle_access(request, payload.bundle_type)
    _ensure_procurement_override_reason_for_downstream(payload, request, tenant_id=tenant_id)
    _mark_procurement_downstream_resolved_context(payload, request, tenant_id=tenant_id)
    result = service.generate_documents(payload, request_id=request_id, tenant_id=tenant_id)
    _apply_generate_state(request, result, template_version)
    log_event(logger, _build_generate_log_event(request, result, request_id, template_version))

    safe_title = re.sub(r'[\\/*?:"<>|]', "_", payload.title)[:100]
    encoded_title = urllib.parse.quote(safe_title, safe="")
    build_pdf = _load_pdf_builder()
    visual_assets = _generate_visual_assets_for_docs(
        result["docs"],
        title=payload.title,
        goal=payload.goal,
        bundle_type=payload.bundle_type,
        tenant_id=tenant_id,
        request_id=request_id,
    )
    pdf_bytes = await build_pdf(result["docs"], title=payload.title, gov_options=None, visual_assets=visual_assets)

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": (
                f"attachment; filename=\"document.pdf\"; "
                f"filename*=UTF-8''{encoded_title}.pdf"
            )
        },
    )


@router.post(
    "/generate/excel",
    dependencies=[Depends(require_not_maintenance), Depends(require_api_key)],
)
def generate_excel_endpoint(
    payload: GenerateRequest,
    request: Request,
) -> Response:
    """Generate an Excel (.xlsx) from any bundle and return as download."""
    _ensure_procurement_bundle_enabled(payload.bundle_type, request)
    service = request.app.state.service
    template_version = request.app.state.template_version
    request_id = request.state.request_id
    tenant_id = getattr(request.state, "tenant_id", "system") or "system"
    ensure_bundle_access(request, payload.bundle_type)
    _ensure_procurement_override_reason_for_downstream(payload, request, tenant_id=tenant_id)
    _mark_procurement_downstream_resolved_context(payload, request, tenant_id=tenant_id)
    result = service.generate_documents(payload, request_id=request_id, tenant_id=tenant_id)
    _apply_generate_state(request, result, template_version)
    log_event(logger, _build_generate_log_event(request, result, request_id, template_version))

    safe_title = re.sub(r'[\\/*?:"<>|]', "_", payload.title)[:100]
    encoded_title = urllib.parse.quote(safe_title, safe="")
    excel_bytes = build_excel(result["docs"], title=payload.title)

    return Response(
        content=excel_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": (
                f"attachment; filename=\"document.xlsx\"; "
                f"filename*=UTF-8''{encoded_title}.xlsx"
            )
        },
    )


@router.post(
    "/generate/hwp",
    dependencies=[Depends(require_not_maintenance), Depends(require_api_key)],
)
def generate_hwp_endpoint(
    payload: GenerateRequest,
    request: Request,
) -> Response:
    """Generate an hwpx (HancomOffice) file from any bundle and return as download."""
    _ensure_procurement_bundle_enabled(payload.bundle_type, request)
    service = request.app.state.service
    template_version = request.app.state.template_version
    request_id = request.state.request_id
    tenant_id = getattr(request.state, "tenant_id", "system") or "system"
    ensure_bundle_access(request, payload.bundle_type)
    _ensure_procurement_override_reason_for_downstream(payload, request, tenant_id=tenant_id)
    _mark_procurement_downstream_resolved_context(payload, request, tenant_id=tenant_id)
    result = service.generate_documents(payload, request_id=request_id, tenant_id=tenant_id)
    _apply_generate_state(request, result, template_version)
    log_event(logger, _build_generate_log_event(request, result, request_id, template_version))

    safe_title = re.sub(r'[\\/*?:"<>|]', "_", payload.title)[:100]
    encoded_title = urllib.parse.quote(safe_title, safe="")
    visual_assets = _generate_visual_assets_for_docs(
        result["docs"],
        title=payload.title,
        goal=payload.goal,
        bundle_type=payload.bundle_type,
        tenant_id=tenant_id,
        request_id=request_id,
    )
    hwp_bytes = build_hwp(result["docs"], title=payload.title, gov_options=None, visual_assets=visual_assets)

    return Response(
        content=hwp_bytes,
        media_type="application/hwp+zip",
        headers={
            "Content-Disposition": (
                f"attachment; filename=\"document.hwpx\"; "
                f"filename*=UTF-8''{encoded_title}.hwpx"
            )
        },
    )


@router.post(
    "/generate/export-edited",
    dependencies=[Depends(require_not_maintenance), Depends(require_api_key)],
)
async def generate_export_edited_endpoint(
    payload: EditedExportRequest,
    request: Request,
) -> Response:
    """Export pre-rendered (possibly user-edited) docs to the requested format.

    Does **not** call the LLM — uses the docs list directly.
    Supported formats: docx, pdf, excel, hwp, pptx.
    """
    tenant_id = getattr(request.state, "tenant_id", "system") or "system"
    request_id = request.state.request_id
    docs = [
        {
            "doc_type": d.doc_type,
            "markdown": d.markdown,
            "total_slides": d.total_slides,
            "slide_outline": d.slide_outline,
        }
        for d in payload.docs
    ]
    title = payload.title or "문서"
    safe_title = re.sub(r'[\\/*?:"<>|]', "_", title)[:100]
    encoded_title = urllib.parse.quote(safe_title, safe="")
    fmt = payload.format.lower().lstrip(".")
    gov_opts = _resolve_gov_options(payload.gov_options)
    visual_assets = [asset.model_dump() for asset in payload.visual_assets] if payload.visual_assets else _generate_visual_assets_for_docs(
        docs,
        title=title,
        goal="",
        bundle_type=payload.bundle_type,
        tenant_id=tenant_id,
        request_id=request_id,
    )

    if fmt == "docx":
        content = _facade().build_docx(docs, title=title, gov_options=gov_opts, visual_assets=visual_assets)
        media_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        ext = "docx"
    elif fmt == "pdf":
        build_pdf = _load_pdf_builder()
        content = await build_pdf(docs, title=title, gov_options=gov_opts, visual_assets=visual_assets)
        media_type = "application/pdf"
        ext = "pdf"
    elif fmt in ("excel", "xlsx"):
        content = build_excel(docs, title=title)
        media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ext = "xlsx"
    elif fmt in ("hwp", "hwpx"):
        content = build_hwp(docs, title=title, gov_options=gov_opts, visual_assets=visual_assets)
        media_type = "application/hwp+zip"
        ext = "hwpx"
    elif fmt in ("ppt", "pptx"):
        slide_outline = []
        for doc in docs:
            for item in doc.get("slide_outline", []) or []:
                if not isinstance(item, dict):
                    continue
                item_title = str(item.get("title", "")).strip()
                if not item_title or "PPT 구성 가이드" in item_title:
                    continue
                slide_outline.append(item)
        if slide_outline:
            content = _facade().build_pptx(
                {
                    "presentation_goal": title,
                    "slide_outline": slide_outline,
                },
                title=title,
                include_outline_overview=payload.bundle_type != "presentation_kr",
                visual_assets=visual_assets,
            )
        else:
            content = build_pptx_from_docs(docs, title=title)
        media_type = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
        ext = "pptx"
    else:
        raise HTTPException(status_code=400, detail=f"지원하지 않는 형식입니다: {payload.format}")

    return Response(
        content=content,
        media_type=media_type,
        headers={
            "Content-Disposition": (
                f"attachment; filename=\"document.{ext}\"; "
                f"filename*=UTF-8''{encoded_title}.{ext}"
            )
        },
    )


@router.get(
    "/generate/export-zip",
    dependencies=[Depends(require_not_maintenance), Depends(require_api_key)],
)
def export_zip(request: Request, request_id: str, formats: str = "docx"):
    """Export cached generation results as a ZIP of converted files."""
    _require_auth(request)
    cached = _get_zip_docs(request_id)
    if cached is None:
        raise HTTPException(status_code=404, detail="No cached documents found for this request_id.")
    docs, title = cached

    valid_formats = {"docx", "pdf", "xlsx", "hwp", "pptx"}
    requested = [f.strip().lower() for f in formats.split(",") if f.strip()]
    actual_formats = [f for f in requested if f in valid_formats]
    if not actual_formats:
        raise HTTPException(status_code=400, detail=f"No valid formats requested. Valid: {', '.join(sorted(valid_formats))}")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for fmt in actual_formats:
            try:
                if fmt == "docx":
                    content = build_docx(docs, title=title)
                    zf.writestr(f"{title or 'document'}.docx", content)
                elif fmt == "pdf":
                    from app.services.pdf_service import build_pdf
                    content = asyncio.get_event_loop().run_until_complete(build_pdf(docs, title=title))
                    zf.writestr(f"{title or 'document'}.pdf", content)
                elif fmt == "xlsx":
                    content = build_excel(docs, title=title)
                    zf.writestr(f"{title or 'document'}.xlsx", content)
                elif fmt == "hwp":
                    content = build_hwp(docs, title=title)
                    zf.writestr(f"{title or 'document'}.hwpx", content)
                elif fmt == "pptx":
                    content = build_pptx_from_docs(docs, title=title)
                    zf.writestr(f"{title or 'document'}.pptx", content)
            except Exception:
                logger.warning("Failed to convert to %s", fmt, exc_info=True)
    buf.seek(0)
    safe_title = urllib.parse.quote(title[:50], safe="") if title else "export"
    return Response(
        content=buf.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{safe_title}.zip"'},
    )
