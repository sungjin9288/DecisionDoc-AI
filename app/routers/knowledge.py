"""app/routers/knowledge.py — 프로젝트 지식 저장소 API.

파일 업로드 → 텍스트 추출 → 지식 저장 → 생성 시 컨텍스트 자동 주입.

Endpoints:
    POST   /knowledge/{project_id}/documents       파일 업로드 & 지식 등록
    GET    /knowledge/{project_id}/documents       문서 목록 조회
    GET    /knowledge/{project_id}/documents/{id}  단일 문서 조회
    PUT    /knowledge/{project_id}/documents/{id}/metadata  학습 메타 수정
    DELETE /knowledge/{project_id}/documents/{id}  문서 삭제
    GET    /knowledge/{project_id}/context         컨텍스트 미리보기
"""
from __future__ import annotations

import logging
import re

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile

from app.auth.api_key import require_api_key
from app.providers.factory import get_provider
from app.schemas import PromoteKnowledgeReferenceRequest, UpdateKnowledgeMetadataRequest

router = APIRouter(tags=["knowledge"])
_log = logging.getLogger("decisiondoc.knowledge.router")

_MAX_UPLOAD_BYTES = 20 * 1024 * 1024  # 20 MB


def _parse_csv_list(raw: str) -> list[str]:
    return [item.strip() for item in raw.split(",") if item.strip()]


def _serialize_entry(entry) -> dict:
    return {
        "doc_id": entry.doc_id,
        "filename": entry.filename,
        "text_len": len(entry.text),
        "has_style": bool(entry.style_profile),
        "tags": entry.tags,
        "created_at": entry.created_at,
        "learning_mode": entry.learning_mode,
        "quality_tier": entry.quality_tier,
        "applicable_bundles": entry.applicable_bundles,
        "source_organization": entry.source_organization,
        "reference_year": entry.reference_year,
        "success_state": entry.success_state,
        "notes": entry.notes,
    }


def _build_promoted_filename(title: str, doc_type: str) -> str:
    normalized_title = re.sub(r"\s+", " ", str(title or "").strip())
    if not normalized_title:
        normalized_title = "approved-reference"
    safe_title = re.sub(r'[\\/:*?"<>|]+', "-", normalized_title)
    safe_doc_type = re.sub(r"[^0-9A-Za-z가-힣_-]+", "-", str(doc_type or "").strip()) or "doc"
    return f"{safe_title} - {safe_doc_type}.md"


# ── 업로드 & 등록 ──────────────────────────────────────────────────────────────

@router.post("/knowledge/{project_id}/documents", dependencies=[Depends(require_api_key)])
async def upload_knowledge_document(
    project_id: str,
    request: Request,
    file: UploadFile = File(...),
    tags: str = Form(""),                    # 쉼표 구분 태그 (선택)
    analyze_style: str = Form("0"),          # "1" 이면 LLM 스타일 분석 실행
    learning_mode: str = Form("reference"),
    quality_tier: str = Form("working"),
    applicable_bundles: str = Form(""),
    source_organization: str = Form(""),
    reference_year: str = Form(""),
    success_state: str = Form("draft"),
    notes: str = Form(""),
) -> dict:
    """파일을 업로드하고 지식 저장소에 등록.

    지원 형식: .txt .md .log .pdf .docx .pptx .hwp .hwpx .xlsx .xls
               .csv .tsv .json .yaml .xml .html .rtf .odt .ods .odp .zip
               .png .jpg .jpeg .webp (provider OCR/vision fallback)
    """
    from app.services.attachment_service import extract_text_with_ai_fallback, AttachmentError
    from app.storage.knowledge_store import KnowledgeStore

    raw = await file.read()
    if len(raw) > _MAX_UPLOAD_BYTES:
        raise HTTPException(413, detail="파일 크기가 20 MB를 초과합니다.")

    filename = file.filename or "unknown"

    # 텍스트 추출
    try:
        text = extract_text_with_ai_fallback(
            filename,
            raw,
            provider=get_provider(),
            request_id=getattr(request.state, "request_id", ""),
        )
    except AttachmentError as exc:
        raise HTTPException(422, detail=str(exc)) from exc

    # 스타일 분석 (옵션)
    style_profile: dict = {}
    if analyze_style.strip() in ("1", "true", "yes"):
        try:
            from app.services.style_analyzer import analyze_document_style
            provider = get_provider()
            style_profile = await analyze_document_style(
                filename=filename,
                raw=raw,
                bundle_id="",
                provider=provider,
            )
        except Exception as exc:
            _log.warning("[Knowledge] Style analysis failed for %s: %s", filename, exc)

    # 저장
    tag_list = _parse_csv_list(tags)
    store = KnowledgeStore(project_id)
    entry = store.add_document(
        filename=filename,
        text=text,
        style_profile=style_profile if style_profile else None,
        tags=tag_list,
        learning_mode=learning_mode,
        quality_tier=quality_tier,
        applicable_bundles=_parse_csv_list(applicable_bundles),
        source_organization=source_organization,
        reference_year=reference_year,
        success_state=success_state,
        notes=notes,
    )
    return _serialize_entry(entry)


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
        "learning_mode": entry.learning_mode,
        "quality_tier": entry.quality_tier,
        "applicable_bundles": entry.applicable_bundles,
        "source_organization": entry.source_organization,
        "reference_year": entry.reference_year,
        "success_state": entry.success_state,
        "notes": entry.notes,
    }


@router.put(
    "/knowledge/{project_id}/documents/{doc_id}/metadata",
    dependencies=[Depends(require_api_key)],
)
def update_knowledge_document_metadata(
    project_id: str,
    doc_id: str,
    body: UpdateKnowledgeMetadataRequest,
) -> dict:
    """지식 문서의 학습/우선참조 메타데이터를 수정."""
    from app.storage.knowledge_store import KnowledgeStore

    store = KnowledgeStore(project_id)
    updated = store.update_metadata(doc_id, **body.model_dump(exclude_none=True))
    if not updated:
        raise HTTPException(404, detail="문서를 찾을 수 없습니다.")
    entry = store.get_document(doc_id)
    if entry is None:
        raise HTTPException(404, detail="문서를 찾을 수 없습니다.")
    payload = _serialize_entry(entry)
    payload["updated"] = True
    return payload


@router.post(
    "/knowledge/{project_id}/promote-generated",
    dependencies=[Depends(require_api_key)],
)
def promote_generated_documents_to_knowledge(
    project_id: str,
    request: Request,
    body: PromoteKnowledgeReferenceRequest,
) -> dict:
    """승인된 생성 결과를 프로젝트 지식 학습 라이브러리로 승격."""
    from app.storage.knowledge_store import KnowledgeStore

    store = KnowledgeStore(project_id)
    base_tags = [tag.strip() for tag in body.tags if tag.strip()]
    created: list[dict] = []

    for item in body.docs:
        markdown = str(item.markdown or "").strip()
        if not markdown:
            continue
        doc_tags = list(base_tags)
        if body.bundle_type not in doc_tags:
            doc_tags.append(body.bundle_type)
        if item.doc_type not in doc_tags:
            doc_tags.append(item.doc_type)
        entry = store.add_document(
            filename=_build_promoted_filename(body.title, item.doc_type),
            text=markdown,
            tags=doc_tags,
            learning_mode="approved_output",
            quality_tier=body.quality_tier,
            applicable_bundles=[body.bundle_type],
            source_organization=body.source_organization,
            reference_year=body.reference_year,
            success_state=body.success_state,
            notes=body.notes or f"승격 출처: {body.bundle_type}",
        )
        payload = _serialize_entry(entry)
        payload["doc_type"] = item.doc_type
        created.append(payload)

    if not created:
        raise HTTPException(422, detail="승격할 문서 본문이 없습니다.")

    promoted_history_entries = 0
    tenant_id = getattr(request.state, "tenant_id", "system") or "system"
    user_id = getattr(request.state, "user_id", "") or None
    if body.source_request_id:
        try:
            from app.storage.history_store import HistoryStore

            promoted_history_entries = HistoryStore(
                tenant_id,
                base_dir=str(request.app.state.data_dir),
                backend=request.app.state.state_backend,
            ).mark_promoted(
                body.source_request_id,
                project_id=project_id,
                document_count=len(created),
                quality_tier=body.quality_tier,
                success_state=body.success_state,
                promoted_at=datetime.now(UTC).isoformat(),
                user_id=user_id,
            )
        except Exception as exc:
            _log.warning(
                "[Knowledge] Failed to update history promotion state project=%s request_id=%s: %s",
                project_id,
                body.source_request_id,
                exc,
            )

    return {
        "project_id": project_id,
        "promoted": len(created),
        "bundle_type": body.bundle_type,
        "source_bundle_id": body.source_bundle_id,
        "source_request_id": body.source_request_id,
        "promoted_history_entries": promoted_history_entries,
        "documents": created,
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
def preview_knowledge_context(
    project_id: str,
    bundle_type: str = Query(default=""),
    title: str = Query(default=""),
    goal: str = Query(default=""),
) -> dict:
    """생성 프롬프트에 실제로 주입될 컨텍스트 미리보기."""
    from app.storage.knowledge_store import KnowledgeStore

    store = KnowledgeStore(project_id)
    ranking = store.rank_documents_for_context(
        bundle_type=bundle_type or None,
        title=title,
        goal=goal,
    )
    context = store.build_context(
        bundle_type=bundle_type or None,
        title=title,
        goal=goal,
    )
    style_context = store.build_style_context()
    return {
        "project_id": project_id,
        "bundle_type": bundle_type,
        "title": title,
        "goal": goal,
        "context": context,
        "style_context": style_context,
        "context_len": len(context),
        "style_context_len": len(style_context),
        "ranked_documents": ranking[:5],
    }
