"""Tests for enhanced PDF extraction and /generate/from-pdf endpoint.

Covers:
- extract_pdf_structured() structured output
- _extract_pdf() fallback behaviour
- POST /generate/from-pdf endpoint (success, auth, validation)
- pdf_source prompt injection in build_bundle_prompt
- SKIP_KEYS exclusion of pdf_source / pdf_sections
"""
from __future__ import annotations

import io
import json
import sys
import types
from unittest.mock import MagicMock, patch

import pytest


# ── Helpers ────────────────────────────────────────────────────────────────────

def _create_client(tmp_path, monkeypatch):
    monkeypatch.setenv("DECISIONDOC_PROVIDER", "mock")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DECISIONDOC_ENV", "dev")
    monkeypatch.setenv("DECISIONDOC_MAINTENANCE", "0")
    monkeypatch.delenv("DECISIONDOC_API_KEY", raising=False)
    monkeypatch.delenv("DECISIONDOC_API_KEYS", raising=False)
    from fastapi.testclient import TestClient
    from app.main import create_app
    return TestClient(create_app())


def _make_char(text: str, top: float, x0: float, size: float, fontname: str = "Arial") -> dict:
    return {"text": text, "top": top, "x0": x0, "size": size, "fontname": fontname}


def _make_mock_page(
    chars: list[dict] | None = None,
    text: str = "Sample text",
    tables: list | None = None,
) -> MagicMock:
    """Build a mock pdfplumber page object."""
    page = MagicMock()
    page.chars = chars if chars is not None else []
    page.extract_text.return_value = text
    page.extract_tables.return_value = tables or []
    return page


def _make_pdfplumber_mock(pages: list[MagicMock]) -> MagicMock:
    """Return a mock pdfplumber module with a fake open() context manager."""
    mock_module = MagicMock()

    mock_pdf = MagicMock()
    mock_pdf.__enter__ = lambda s: s
    mock_pdf.__exit__ = MagicMock(return_value=False)
    mock_pdf.pages = pages

    mock_module.open.return_value = mock_pdf
    return mock_module


# ── Test 1: basic structured extraction ───────────────────────────────────────

def test_extract_pdf_structured_basic():
    """extract_pdf_structured should return all expected keys with reasonable values."""
    from app.services.attachment_service import extract_pdf_structured

    heading_chars = [
        _make_char(c, top=10.0, x0=i * 8.0, size=18.0) for i, c in enumerate("Title")
    ]
    body_chars = [
        _make_char(c, top=30.0, x0=i * 6.0, size=10.0) for i, c in enumerate("Body text here")
    ]

    mock_page = _make_mock_page(chars=heading_chars + body_chars, tables=[])
    mock_pdfplumber = _make_pdfplumber_mock([mock_page])

    with patch.dict(sys.modules, {"pdfplumber": mock_pdfplumber}):
        result = extract_pdf_structured(b"%PDF fake", "test.pdf")

    assert isinstance(result, dict)
    assert "title" in result
    assert "sections" in result
    assert "raw_text" in result
    assert "page_count" in result
    assert "has_tables" in result
    assert "pages" in result
    assert isinstance(result["sections"], list)
    assert isinstance(result["pages"], list)
    assert result["page_count"] == 1
    assert result["has_tables"] is False


# ── Test 2: fallback when chars unavailable ────────────────────────────────────

def test_extract_pdf_fallback():
    """_extract_pdf should fall back to extract_text when chars is empty."""
    from app.services.attachment_service import _extract_pdf

    mock_page = _make_mock_page(chars=[], text="Fallback plain text")
    mock_pdfplumber = _make_pdfplumber_mock([mock_page])

    with patch.dict(sys.modules, {"pdfplumber": mock_pdfplumber}):
        result = _extract_pdf(b"%PDF fake", "fallback.pdf")

    assert "Fallback plain text" in result


# ── Test 3: /generate/from-pdf endpoint success ───────────────────────────────

def test_from_pdf_endpoint_success(tmp_path, monkeypatch):
    """POST /generate/from-pdf should return 200 and a valid GenerateResponse."""
    client = _create_client(tmp_path, monkeypatch)

    structured_result = {
        "title": "Test PDF Title",
        "sections": [{"heading": "Introduction", "content": "Some content"}],
        "raw_text": "Test PDF Title\nIntroduction\nSome content",
        "page_count": 1,
        "has_tables": False,
    }

    with patch(
        "app.routers.generate.extract_pdf_structured",
        return_value=structured_result,
    ):
        fake_pdf = io.BytesIO(b"%PDF-1.4 content")
        response = client.post(
            "/generate/from-pdf",
            data={"doc_types": "adr,onepager", "tenant_id": "default"},
            files={"file": ("test.pdf", fake_pdf, "application/pdf")},
        )

    assert response.status_code == 200
    body = response.json()
    assert "request_id" in body
    assert "bundle_id" in body
    assert "docs" in body
    assert len(body["docs"]) == 2
    assert [doc["doc_type"] for doc in body["docs"]] == ["adr", "onepager"]


# ── Test 4: rejects non-PDF files ─────────────────────────────────────────────

def test_from_pdf_endpoint_rejects_non_pdf(tmp_path, monkeypatch):
    """POST /generate/from-pdf should return 422 for non-PDF uploads."""
    client = _create_client(tmp_path, monkeypatch)

    fake_txt = io.BytesIO(b"This is plain text, not a PDF")
    response = client.post(
        "/generate/from-pdf",
        data={"doc_types": "adr"},
        files={"file": ("document.txt", fake_txt, "text/plain")},
    )

    assert response.status_code == 422
    assert "PDF" in response.json().get("detail", "")


# ── Test 5: rejects files over 20MB ───────────────────────────────────────────

def test_from_pdf_endpoint_too_large(tmp_path, monkeypatch):
    """POST /generate/from-pdf should return 422 when file exceeds 20MB."""
    client = _create_client(tmp_path, monkeypatch)

    oversized = io.BytesIO(b"A" * (20 * 1024 * 1024 + 1))
    response = client.post(
        "/generate/from-pdf",
        data={"doc_types": "adr"},
        files={"file": ("large.pdf", oversized, "application/pdf")},
    )

    assert response.status_code == 422
    detail = response.json().get("detail", "")
    assert "20MB" in detail or "20 MB" in detail


# ── Test 6: no auth returns 401 ───────────────────────────────────────────────

def test_from_pdf_endpoint_no_auth(tmp_path, monkeypatch):
    """POST /generate/from-pdf should return 401 when API key is required but missing."""
    monkeypatch.setenv("DECISIONDOC_PROVIDER", "mock")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DECISIONDOC_ENV", "dev")
    monkeypatch.setenv("DECISIONDOC_MAINTENANCE", "0")
    monkeypatch.setenv("DECISIONDOC_API_KEYS", "valid-key-abc")

    from fastapi.testclient import TestClient
    from app.main import create_app

    client = TestClient(create_app(), raise_server_exceptions=False)

    fake_pdf = io.BytesIO(b"%PDF-1.4 content")
    response = client.post(
        "/generate/from-pdf",
        data={"doc_types": "adr"},
        files={"file": ("test.pdf", fake_pdf, "application/pdf")},
    )

    # UnauthorizedError is mapped to 401 by the exception handler
    assert response.status_code == 401


# ── Test 7: pdf_source injected into prompt ───────────────────────────────────

def test_pdf_source_in_prompt():
    """build_bundle_prompt should include pdf_source content in the final prompt."""
    from app.domain.schema import build_bundle_prompt

    requirements = {
        "title": "Decision",
        "goal": "Test",
        "pdf_source": "This is the PDF raw text content that should appear in prompt.",
    }

    prompt = build_bundle_prompt(requirements, schema_version="v1")

    assert "참고 PDF 원문" in prompt
    assert "This is the PDF raw text content" in prompt


def test_quality_prompt_forbids_ungrounded_specifics():
    from app.domain.schema import build_bundle_prompt

    prompt = build_bundle_prompt(
        {
            "title": "Decision",
            "goal": "Test",
        },
        schema_version="v1",
    )

    assert "근거 없는 날짜, 예산, 기관명, 기술명, 배점, 일정의 임의 생성" in prompt


def test_attachment_grounding_strict_mode_in_prompt():
    from app.domain.schema import build_bundle_prompt

    prompt = build_bundle_prompt(
        {
            "title": "국토교통 교차로 안전 제안",
            "goal": "첨부 기반 제안서 초안을 작성한다.",
            "context": (
                "=== RFP 원문 (참고용) ===\n"
                "[첨부파일: uat-attachment.txt]\n"
                "국토교통 제안의 핵심 요구사항은 교차로 안전 강화와 장애인 보호 강화이다.\n"
                "=== RFP 원문 끝 ==="
            ),
        },
        schema_version="v1",
    )

    assert "[첨부/RFP grounding strict mode]" in prompt
    assert "source text에 없는 기술 스택, 제품명, 마감일, KPI 수치를 예시처럼 채우지 마세요." in prompt


def test_procurement_page_hints_in_prompt_for_slide_outline_bundle():
    from app.bundle_catalog.bundles.proposal_kr import PROPOSAL_KR
    from app.domain.schema import build_bundle_prompt

    prompt = build_bundle_prompt(
        {
            "title": "공공기관 경영평가 제안",
            "goal": "착수보고 PDF를 참고해 제안서와 PPT 설계를 만든다.",
            "_procurement_context": (
                "=== 공공조달 PDF 정규화 요약 ===\n"
                "페이지 분류:\n"
                "- 3p [평가기준/지표] 평가 지표 체계\n"
                "PPT 페이지 설계 힌트:\n"
                "- 3p 평가 지표 체계 | 권장 시각자료: 평가기준 표 | 배치 가이드: 상단 핵심 메시지 / 중앙 배점·평가표 / 하단 대응 포인트\n"
                "발표/PPT 후보 페이지:\n"
                "- 평가 대응 전략 — 3p [평가기준/지표] 평가 지표 체계\n"
                "=== 공공조달 PDF 정규화 요약 끝 ==="
            ),
        },
        schema_version="v1",
        bundle_spec=PROPOSAL_KR,
    )

    assert "[공공조달 PPT 설계 적용 규칙]" in prompt
    assert "`페이지 분류`, `PPT 페이지 설계 힌트`, `발표/PPT 후보 페이지`" in prompt
    assert "visual_type, visual_brief, layout_hint" in prompt
    assert "표, 타임라인, 조직도, 프로세스 흐름도" in prompt


def test_procurement_slide_outline_guidance_backfills_visual_and_evidence():
    from app.services.generation_service import _apply_procurement_slide_outline_guidance

    bundle = {
        "business_understanding": {
            "total_slides": 1,
            "slide_outline": [
                {
                    "page": 1,
                    "title": "평가 대응 전략",
                    "key_content": "발주처 평가 포인트와 대응 근거를 정리한다.",
                    "core_message": "",
                    "evidence_points": [],
                    "visual_type": "비교표",
                    "visual_brief": "일반 비교 자료",
                    "layout_hint": "좌우 비교 레이아웃",
                    "design_tip": "일반 비교 도식",
                }
            ],
        }
    }
    context = (
        "=== 공공조달 PDF 정규화 요약 ===\n"
        "페이지 분류:\n"
        "- 3p [평가기준/지표] 평가 지표 체계\n"
        "PPT 페이지 설계 힌트:\n"
        "- 3p 평가 지표 체계 | 권장 시각자료: 평가기준 표 | 배치 가이드: 상단 핵심 메시지 / 중앙 배점·평가표 / 하단 대응 포인트\n"
        "발표/PPT 후보 페이지:\n"
        "- 평가 대응 전략 — 3p [평가기준/지표] 평가 지표 체계\n"
        "=== 공공조달 PDF 정규화 요약 끝 ==="
    )

    guided = _apply_procurement_slide_outline_guidance(bundle, procurement_context=context)
    slide = guided["business_understanding"]["slide_outline"][0]

    assert slide["visual_type"] == "평가기준 표"
    assert slide["layout_hint"] == "상단 핵심 메시지 / 중앙 배점·평가표 / 하단 대응 포인트"
    assert "참고 페이지: 3p [평가기준/지표] 평가 지표 체계" in slide["evidence_points"]
    assert slide["visual_brief"].startswith("참고 PDF 3p")
    assert slide["title"] == "평가 대응 전략 — 평가 지표 체계"


def test_procurement_slide_outline_guidance_synthesizes_outline_when_missing():
    from app.services.generation_service import _apply_procurement_slide_outline_guidance

    bundle = {
        "performance_overview": {
            "total_slides": 0,
            "slide_outline": [],
        }
    }
    context = (
        "=== 공공조달 PDF 정규화 요약 ===\n"
        "페이지 분류:\n"
        "- 4p [표·평가표 중심] 지방출자·출연기관경영평가대상범위\n"
        "- 7p [일정/마일스톤] 파주시공공기관(장) 경영평가추진일정\n"
        "PPT 페이지 설계 힌트:\n"
        "- 4p 지방출자·출연기관경영평가대상범위 | 권장 시각자료: 비교 표 + 강조 박스 | 배치 가이드: 중앙 표 / 우측 또는 하단 핵심 시사점\n"
        "- 7p 파주시공공기관(장) 경영평가추진일정 | 권장 시각자료: 타임라인 | 배치 가이드: 가로 타임라인 / 하단 단계별 산출물\n"
        "발표/PPT 후보 페이지:\n"
        "- 평가 대응 전략 — 4p [표·평가표 중심] 지방출자·출연기관경영평가대상범위\n"
        "- 일정 및 마일스톤 — 7p [일정/마일스톤] 파주시공공기관(장) 경영평가추진일정\n"
        "=== 공공조달 PDF 정규화 요약 끝 ==="
    )

    guided = _apply_procurement_slide_outline_guidance(bundle, procurement_context=context)
    outline = guided["performance_overview"]["slide_outline"]

    assert len(outline) == 2
    assert guided["performance_overview"]["total_slides"] == 2
    assert outline[0]["title"] == "평가 대응 전략 — 지방출자·출연기관경영평가대상범위"
    assert outline[0]["visual_type"] == "비교 표 + 강조 박스"
    assert outline[1]["visual_type"] == "타임라인"


def test_procurement_slide_outline_guidance_reorders_to_procurement_page_order():
    from app.services.generation_service import _apply_procurement_slide_outline_guidance

    bundle = {
        "business_understanding": {
            "total_slides": 2,
            "slide_outline": [
                {
                    "page": 1,
                    "title": "슬라이드 1",
                    "key_content": "일정 및 마일스톤을 설명한다.",
                    "core_message": "",
                    "evidence_points": [],
                    "visual_type": "",
                    "visual_brief": "",
                    "layout_hint": "",
                    "design_tip": "",
                },
                {
                    "page": 2,
                    "title": "슬라이드 2",
                    "key_content": "평가 대응 전략을 설명한다.",
                    "core_message": "",
                    "evidence_points": [],
                    "visual_type": "",
                    "visual_brief": "",
                    "layout_hint": "",
                    "design_tip": "",
                },
            ],
        }
    }
    context = (
        "=== 공공조달 PDF 정규화 요약 ===\n"
        "페이지 분류:\n"
        "- 3p [평가기준/지표] 평가 지표 체계\n"
        "- 7p [일정/마일스톤] 세부 추진 일정\n"
        "PPT 페이지 설계 힌트:\n"
        "- 3p 평가 지표 체계 | 권장 시각자료: 평가기준 표 | 배치 가이드: 상단 핵심 메시지 / 중앙 배점·평가표 / 하단 대응 포인트\n"
        "- 7p 세부 추진 일정 | 권장 시각자료: 타임라인 | 배치 가이드: 가로 타임라인 / 하단 단계별 산출물\n"
        "발표/PPT 후보 페이지:\n"
        "- 평가 대응 전략 — 3p [평가기준/지표] 평가 지표 체계\n"
        "- 일정 및 마일스톤 — 7p [일정/마일스톤] 세부 추진 일정\n"
        "=== 공공조달 PDF 정규화 요약 끝 ==="
    )

    guided = _apply_procurement_slide_outline_guidance(bundle, procurement_context=context)
    outline = guided["business_understanding"]["slide_outline"]

    assert [item["page"] for item in outline] == [1, 2]
    assert outline[0]["title"] == "평가 대응 전략 — 평가 지표 체계"
    assert outline[1]["title"] == "일정 및 마일스톤 — 세부 추진 일정"


# ── Test 8: pdf_source excluded from clean_requirements ───────────────────────

def test_skip_keys_exclude_pdf_source():
    """_clean_requirements_for_prompt should strip pdf_source and pdf_sections."""
    from app.domain.schema import _clean_requirements_for_prompt

    requirements = {
        "title": "My Decision",
        "goal": "Validate skip keys",
        "pdf_source": "large raw text " * 500,
        "pdf_sections": '["Section A", "Section B"]',
        "context": "Some context",
    }

    cleaned = _clean_requirements_for_prompt(requirements)

    assert "pdf_source" not in cleaned
    assert "pdf_sections" not in cleaned
    assert "title" in cleaned
    assert "context" in cleaned


# ── Test 9: structured extraction returns sections list ───────────────────────

def test_structured_has_sections():
    """extract_pdf_structured should return a non-empty sections list for PDFs with headings."""
    from app.services.attachment_service import extract_pdf_structured

    chars = []
    # First heading: large font (24pt) vs body (10pt) → avg ~14pt, 24 > 14*1.2=16.8 → heading
    for i, c in enumerate("Introduction"):
        chars.append(_make_char(c, top=10.0, x0=i * 8.0, size=24.0))
    for i, c in enumerate("Body paragraph text"):
        chars.append(_make_char(c, top=30.0, x0=i * 6.0, size=10.0))
    for i, c in enumerate("Conclusion"):
        chars.append(_make_char(c, top=50.0, x0=i * 8.0, size=24.0))
    for i, c in enumerate("Final remarks"):
        chars.append(_make_char(c, top=70.0, x0=i * 6.0, size=10.0))

    mock_page = _make_mock_page(chars=chars, tables=[])
    mock_pdfplumber = _make_pdfplumber_mock([mock_page])

    with patch.dict(sys.modules, {"pdfplumber": mock_pdfplumber}):
        result = extract_pdf_structured(b"%PDF fake", "sections.pdf")

    assert len(result["sections"]) >= 2
    headings = [s["heading"] for s in result["sections"]]
    assert "Introduction" in headings
    assert "Conclusion" in headings


# ── Test 10: title detection from first large heading ─────────────────────────

def test_structured_title_detection():
    """extract_pdf_structured should detect the first large-font line as the title."""
    from app.services.attachment_service import extract_pdf_structured

    # First line: large font (24pt) only; body at 10pt → avg = mixed
    title_chars = [
        _make_char(c, top=5.0, x0=i * 10.0, size=24.0) for i, c in enumerate("MyDocTitle")
    ]
    body_chars = [
        _make_char(c, top=25.0, x0=i * 6.0, size=10.0) for i, c in enumerate("Normal body")
    ]

    mock_page = _make_mock_page(chars=title_chars + body_chars, tables=[])
    mock_pdfplumber = _make_pdfplumber_mock([mock_page])

    with patch.dict(sys.modules, {"pdfplumber": mock_pdfplumber}):
        result = extract_pdf_structured(b"%PDF fake", "title_test.pdf")

    assert result["title"] == "MyDocTitle"


def test_structured_pages_include_heading_preview_and_table_flag():
    from app.services.attachment_service import extract_pdf_structured

    heading_chars = [
        _make_char(c, top=10.0, x0=i * 8.0, size=24.0) for i, c in enumerate("세부 추진 일정")
    ]
    body_chars = [
        _make_char(c, top=30.0, x0=i * 6.0, size=10.0) for i, c in enumerate("착수 중간 완료 보고")
    ]
    mock_page = _make_mock_page(chars=heading_chars + body_chars, tables=[["A", "B"]])
    mock_pdfplumber = _make_pdfplumber_mock([mock_page])

    with patch.dict(sys.modules, {"pdfplumber": mock_pdfplumber}):
        result = extract_pdf_structured(b"%PDF fake", "pages.pdf")

    assert result["pages"] == [
        {
            "page": 1,
            "headings": ["세부 추진 일정"],
            "preview": "A B 세부 추진 일정 착수 중간 완료 보고",
            "has_tables": True,
        }
    ]


def test_reconstruct_pdf_line_text_restores_korean_word_spacing():
    from app.services.attachment_service import _reconstruct_pdf_line_text

    chars = [
        {"text": "경", "x0": 0.0, "x1": 13.2, "size": 15.0},
        {"text": "영", "x0": 13.22, "x1": 26.44, "size": 15.0},
        {"text": "평", "x0": 26.46, "x1": 39.68, "size": 15.0},
        {"text": "가", "x0": 39.70, "x1": 52.92, "size": 15.0},
        {"text": "개", "x0": 56.60, "x1": 69.82, "size": 15.0},
        {"text": "요", "x0": 69.84, "x1": 83.06, "size": 15.0},
    ]

    assert _reconstruct_pdf_line_text(chars) == "경영평가 개요"


def test_reconstruct_pdf_line_text_keeps_tight_ascii_without_extra_spaces():
    from app.services.attachment_service import _reconstruct_pdf_line_text

    chars = [
        {"text": "C", "x0": 0.0, "x1": 10.8, "size": 15.0},
        {"text": "o", "x0": 10.4, "x1": 19.6, "size": 15.0},
        {"text": "n", "x0": 19.7, "x1": 29.4, "size": 15.0},
        {"text": "t", "x0": 29.5, "x1": 35.3, "size": 15.0},
        {"text": "a", "x0": 35.0, "x1": 43.9, "size": 15.0},
        {"text": "c", "x0": 44.0, "x1": 52.6, "size": 15.0},
        {"text": "t", "x0": 53.0, "x1": 58.8, "size": 15.0},
    ]

    assert _reconstruct_pdf_line_text(chars) == "Contact"
