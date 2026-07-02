"""app/routers/generate/core.py — Core document generation endpoints.

Split out of the former app/routers/generate.py (2,170 lines) to keep each
sub-module under the file-size limit. Covers:
  POST /generate
  POST /generate/with-attachments
  POST /generate/from-documents
  POST /generate/from-pdf

Pure code relocation — no behavior changes.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile

from app.auth.api_key import require_api_key
from app.maintenance.mode import require_not_maintenance
from app.observability.logging import log_event
from app.providers.factory import get_provider_for_capability
from app.schemas import GenerateRequest, GenerateResponse
from app.services.attachment_service import AttachmentError

from app.routers.generate._shared import (
    _build_procurement_attachment_context,
    _extract_uploaded_documents,
    _raise_if_legacy_binary_hwp_uploads,
)

logger = logging.getLogger("decisiondoc.generate")

router = APIRouter(tags=["generate"])


def _facade():
    """Return the `app.routers.generate` package module.

    Some existing tests patch library functions (``extract_multiple``,
    ``extract_pdf_structured``, ``_run_generate``) via
    ``unittest.mock.patch("app.routers.generate.<name>", ...)`` — a pattern
    written against the pre-split single-file module. Looking these up on the
    facade module at call time keeps those patches effective after the split.
    """
    import app.routers.generate as _generate_pkg

    return _generate_pkg


@router.post(
    "/generate",
    response_model=GenerateResponse,
    dependencies=[Depends(require_not_maintenance), Depends(require_api_key)],
)
def generate(
    payload: GenerateRequest,
    request: Request,
) -> GenerateResponse:
    # Keep sync — providers use anyio.run() internally and require a thread-pool context.
    return _facade()._run_generate(payload, request)


@router.post(
    "/generate/with-attachments",
    response_model=GenerateResponse,
    dependencies=[Depends(require_not_maintenance), Depends(require_api_key)],
)
def generate_with_attachments(
    request: Request,
    payload: str = Form(..., description="GenerateRequest as JSON string"),
    attachments: list[UploadFile] = File(default=[]),
) -> GenerateResponse:
    # Keep sync — file bytes read via upload.file.read() to stay in sync context.
    try:
        req = GenerateRequest.model_validate_json(payload)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Invalid payload JSON: {exc}") from exc

    if attachments:
        _raise_if_legacy_binary_hwp_uploads(attachments)
        file_data: list[tuple[str, bytes]] = []
        for upload in attachments:
            if not upload.filename:
                continue
            raw = upload.file.read()
            if not raw:
                continue
            file_data.append((upload.filename, raw))
        if file_data:
            from app.services.rfp_parser import build_rfp_context
            combined = _facade().extract_multiple(
                file_data,
                provider=get_provider_for_capability("attachment"),
                request_id=request.state.request_id,
            )
            procurement_context = _build_procurement_attachment_context(file_data)
            rfp_context = build_rfp_context(combined, normalized_context=procurement_context)
            existing = req.context or ""
            merged = rfp_context + ("\n\n" + existing if existing else "")
            req = req.model_copy(update={"context": merged})

    return _facade()._run_generate(req, request)


@router.post(
    "/generate/from-documents",
    response_model=GenerateResponse,
    dependencies=[Depends(require_not_maintenance), Depends(require_api_key)],
)
def generate_from_documents(
    request: Request,
    files: list[UploadFile] = File(..., description="지원 문서 파일 목록"),
    title: str = Form(default="", description="생성 문서 제목"),
    goal: str = Form(
        default="업로드 문서를 근거로 의사결정 문서를 작성합니다.",
        description="생성 목표",
    ),
    context: str = Form(default="", description="추가 컨텍스트"),
    doc_types: str = Form(
        default="adr,onepager,eval_plan,ops_checklist",
        description="생성할 문서 유형 (콤마 구분)",
    ),
    bundle_type: str = Form(default="tech_decision", description="번들 유형"),
    tenant_id: str = Form(default="default", description="테넌트 ID"),
) -> GenerateResponse:
    """Upload one or more documents and generate a bundle directly from them."""
    from app.schemas import GenerateRequest as _GenerateRequest

    _raise_if_legacy_binary_hwp_uploads(files)
    combined_text, parsed_filenames, procurement_context = _extract_uploaded_documents(
        files,
        provider=get_provider_for_capability("attachment"),
        request_id=request.state.request_id,
    )
    doc_types_list = [dt.strip() for dt in doc_types.split(",") if dt.strip()]
    merged_parts = [part for part in [procurement_context, combined_text, context] if part]
    merged_context = "\n\n".join(merged_parts)
    first_name = parsed_filenames[0]
    default_title = Path(first_name).stem

    try:
        req = _GenerateRequest(
            title=title.strip() or default_title,
            goal=goal,
            context=merged_context,
            doc_types=doc_types_list,
            bundle_type=bundle_type,
        )
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"요청 생성 실패: {exc}") from exc

    request.state.document_ingestion_files = parsed_filenames
    if procurement_context:
        request.state.document_ingestion_procurement_context = procurement_context[:1_000]
    log_event(
        logger,
        {
            "event": "generate.from_documents.started",
            "request_id": request.state.request_id,
            "bundle_type": bundle_type,
            "files_count": len(parsed_filenames),
            "files": parsed_filenames,
            "tenant_id": tenant_id,
        },
    )

    return _facade()._run_generate(req, request)


@router.post(
    "/generate/from-pdf",
    response_model=GenerateResponse,
    dependencies=[Depends(require_not_maintenance), Depends(require_api_key)],
)
def generate_from_pdf(
    request: Request,
    file: UploadFile = File(..., description="PDF 파일 (최대 20MB)"),
    doc_types: str = Form(default="adr,onepager", description="생성할 문서 유형 (콤마 구분)"),
    tenant_id: str = Form(default="default", description="테넌트 ID"),
) -> GenerateResponse:
    """PDF 파일을 업로드하여 구조화된 의사결정 문서를 생성합니다.

    PDF에서 텍스트를 구조화 추출한 뒤 GenerationService를 통해 문서 번들을 생성합니다.
    """
    from app.schemas import GenerateRequest as _GenerateRequest

    # ── Validate file ──────────────────────────────────────────────────────────
    filename = file.filename or "upload.pdf"
    if not filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=422, detail="PDF 파일만 허용됩니다.")

    raw = file.file.read()
    if len(raw) > 20 * 1024 * 1024:
        raise HTTPException(status_code=422, detail="파일 크기가 20MB를 초과합니다.")

    # ── Structured extraction ──────────────────────────────────────────────────
    try:
        structured = _facade().extract_pdf_structured(raw, filename)
    except AttachmentError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    from app.services.procurement_pdf_normalizer import build_procurement_pdf_context
    procurement_pdf_context = build_procurement_pdf_context(structured, filename)

    # ── Build requirements ─────────────────────────────────────────────────────
    filename_stem = Path(filename).stem
    doc_types_list = [dt.strip() for dt in doc_types.split(",") if dt.strip()]

    requirements: dict = {
        "title": structured["title"] or filename_stem,
        "background": f"PDF 문서 '{filename}'에서 추출된 내용을 기반으로 문서를 재구성합니다.",
        "pdf_source": structured["raw_text"],
        "pdf_sections": json.dumps(
            [s["heading"] for s in structured["sections"]], ensure_ascii=False
        ),
        "doc_types": doc_types_list,
    }

    # ── Build GenerateRequest ──────────────────────────────────────────────────
    try:
        req = _GenerateRequest(
            title=requirements["title"],
            goal=f"PDF 문서 '{filename}'의 내용을 기반으로 의사결정 문서를 작성합니다.",
            context="\n\n".join(
                part for part in [procurement_pdf_context, structured["raw_text"][:3000]] if part
            ),
            doc_types=doc_types_list,
            bundle_type="tech_decision",
        )
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"요청 생성 실패: {exc}") from exc

    # Inject PDF-specific fields into the requirements dict that will reach the
    # prompt builder via GenerationService (stored as req attributes are not
    # directly accessible; we piggyback on context which is already set).
    # We also attach them as extra state so the prompt builder can detect them.
    request.state.pdf_source = structured["raw_text"]
    request.state.pdf_structured = structured
    request.state.pdf_procurement_context = procurement_pdf_context[:1_000] if procurement_pdf_context else ""

    log_event(
        logger,
        {
            "event": "generate.from_pdf.started",
            "request_id": request.state.request_id,
            "filename": filename,
            "page_count": structured["page_count"],
            "has_tables": structured["has_tables"],
            "sections_count": len(structured["sections"]),
        },
    )

    return _facade()._run_generate(req, request)
