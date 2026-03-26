"""app/routers/knowledge.py — 프로젝트 지식 저장소 API.

파일 업로드 → 텍스트 추출 → 지식 저장 → 생성 시 컨텍스트 자동 주입.

Endpoints:
    POST   /knowledge/{project_id}/documents       파일 업로드 & 지식 등록
    GET    /knowledge/{project_id}/documents       문서 목록 조회
    GET    /knowledge/{project_id}/documents/{id}  단일 문서 조회
    DELETE /knowledge/{project_id}/documents/{id}  문서 삭제
    GET    /knowledge/{project_id}/context         컨텍스트 미리보기
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile

from app.auth.api_key import require_api_key

router = APIRouter(tags=["knowledge"])
_log = logging.getLogger("decisiondoc.knowledge.router")

_MAX_UPLOAD_BYTES = 20 * 1024 * 1024  # 20 MB


# ── 업로드 & 등록 ──────────────────────────────────────────────────────────────

@router.post("/knowledge/{project_id}/documents", dependencies=[Depends(require_api_key)])
async def upload_knowledge_document(
    project_id: str,
    request: Request,
    file: UploadFile = File(...),
    tags: str = Form(""),           # 쉼표 구분 태그 (선택)
    analyze_style: str = Form("0"), # "1" 이면 LLM 스타일 분석 실행
) -> dict:
    """파일을 업로드하고 지식 저장소에 등록.

    지원 형식: .txt .md .pdf .docx .pptx .hwp .hwpx .xlsx .xls .csv
    """
    from app.services.attachment_service import extract_text, AttachmentError
    from app.storage.knowledge_store import KnowledgeStore

    raw = await file.read()
    if len(raw) > _MAX_UPLOAD_BYTES:
        raise HTTPException(413, detail="파일 크기가 20 MB를 초과합니다.")

    filename = file.filename or "unknown"

    # 텍스트 추출
    try:
        text = extract_text(filename, raw)
    except AttachmentError as exc:
        raise HTTPException(422, detail=str(exc)) from exc

    # 스타일 분석 (옵션)
    style_profile: dict = {}
    if analyze_style.strip() in ("1", "true", "yes"):
        try:
            from app.services.style_analyzer import analyze_document_style
            provider = request.app.state.provider
            style_profile = await analyze_document_style(
                filename=filename,
                raw=raw,
                bundle_id="",
                provider=provider,
            )
        except Exception as exc:
            _log.warning("[Knowledge] Style analysis failed for %s: %s", filename, exc)

    # 저장
    tag_list = [t.strip() for t in tags.split(",") if t.strip()]
    store = KnowledgeStore(project_id)
    entry = store.add_document(
        filename=filename,
        text=text,
        style_profile=style_profile if style_profile else None,
        tags=tag_list,
    )

    return {
        "doc_id": entry.doc_id,
        "filename": entry.filename,
        "text_len": len(entry.text),
        "has_style": bool(entry.style_profile),
        "tags": entry.tags,
        "created_at": entry.created_at,
    }


# ── 목록 조회 ──────────────────────────────────────────────────────────────────

@router.get("/knowledge/{project_id}/documents", dependencies=[Depends(require_api_key)])
def list_knowledge_documents(project_id: str) -> dict:
    """프로젝트의 지식 문서 목록."""
    from app.storage.knowledge_store import KnowledgeStore

    store = KnowledgeStore(project_id)
    docs = store.list_documents()
    return {"project_id": project_id, "count": len(docs), "documents": docs}


# ── 단일 문서 조회 ─────────────────────────────────────────────────────────────

@router.get(
    "/knowledge/{project_id}/documents/{doc_id}",
    dependencies=[Depends(require_api_key)],
)
def get_knowledge_document(project_id: str, doc_id: str) -> dict:
    """단일 문서 전문 + 스타일 프로필 조회."""
    from app.storage.knowledge_store import KnowledgeStore

    entry = KnowledgeStore(project_id).get_document(doc_id)
    if entry is None:
        raise HTTPException(404, detail="문서를 찾을 수 없습니다.")
    return {
        "doc_id": entry.doc_id,
        "filename": entry.filename,
        "text": entry.text,
        "style_profile": entry.style_profile,
        "tags": entry.tags,
        "created_at": entry.created_at,
    }


# ── 삭제 ──────────────────────────────────────────────────────────────────────

@router.delete(
    "/knowledge/{project_id}/documents/{doc_id}",
    dependencies=[Depends(require_api_key)],
)
def delete_knowledge_document(project_id: str, doc_id: str) -> dict:
    """지식 문서 삭제."""
    from app.storage.knowledge_store import KnowledgeStore

    deleted = KnowledgeStore(project_id).delete_document(doc_id)
    if not deleted:
        raise HTTPException(404, detail="문서를 찾을 수 없습니다.")
    return {"deleted": True, "doc_id": doc_id}


# ── 컨텍스트 미리보기 ──────────────────────────────────────────────────────────

@router.get("/knowledge/{project_id}/context", dependencies=[Depends(require_api_key)])
def preview_knowledge_context(project_id: str) -> dict:
    """생성 프롬프트에 실제로 주입될 컨텍스트 미리보기."""
    from app.storage.knowledge_store import KnowledgeStore

    store = KnowledgeStore(project_id)
    context = store.build_context()
    style_context = store.build_style_context()
    return {
        "project_id": project_id,
        "context": context,
        "style_context": style_context,
        "context_len": len(context),
        "style_context_len": len(style_context),
    }
