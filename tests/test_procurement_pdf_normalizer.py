from __future__ import annotations

from app.services.procurement_pdf_normalizer import (
    build_procurement_pdf_context,
    parse_procurement_pdf_context,
)


def test_build_procurement_pdf_context_includes_key_sections_and_signals():
    structured = {
        "title": "2026년 파주시 출연기관 경영평가 착수보고 자료",
        "page_count": 26,
        "has_tables": True,
        "raw_text": "경영평가 개요 과업 범위 세부 추진 일정 추진 체계",
        "pages": [
            {"page": 1, "headings": ["경영평가 개요"], "preview": "경영평가 추진 배경과 목적", "has_tables": False},
            {"page": 2, "headings": ["과업 수행 범위"], "preview": "평가 지표 정리와 기관 인터뷰", "has_tables": True},
            {"page": 3, "headings": ["세부 추진 일정"], "preview": "착수 중간 완료 보고 일정", "has_tables": False},
        ],
        "sections": [
            {"heading": "Ⅰ. 경영평가 개요", "content": "경영평가 추진 배경과 목적을 설명한다."},
            {"heading": "Ⅱ. 과업 수행 범위", "content": "평가 지표 정리와 기관 인터뷰를 수행한다."},
            {"heading": "Ⅲ. 세부 추진 일정", "content": "착수, 중간, 완료 보고 일정을 제시한다."},
            {"heading": "Ⅳ. 추진 체계 및 인력 운영", "content": "PM, 평가위원, 실무진 조직을 설명한다."},
        ],
    }

    context = build_procurement_pdf_context(structured, "kickoff.pdf")

    assert "=== 공공조달 PDF 정규화 요약 ===" in context
    assert "추정 문서 유형: 착수보고 / 수행계획" in context
    assert "- 경영평가 개요" in context
    assert "- 과업 수행 범위" in context
    assert "주요 조달 신호:" in context
    assert "페이지 분류:" in context
    assert "1p [개요/배경] 경영평가 개요" in context
    assert "PPT 페이지 설계 힌트:" in context
    assert "1p 경영평가 개요 | 권장 시각자료: 문제-배경 카드" in context
    assert "일정/마일스톤" in context
    assert "발표/PPT 후보 페이지:" in context


def test_build_procurement_pdf_context_filters_numeric_noise_headings():
    structured = {
        "title": "공공 사업 문서",
        "page_count": 4,
        "has_tables": False,
        "raw_text": "내용",
        "sections": [
            {"heading": "1", "content": "noise"},
            {"heading": "02", "content": "noise"},
            {"heading": "III.", "content": "noise"},
            {"heading": "1. 추진 방향", "content": "실행 방향"},
        ],
    }

    context = build_procurement_pdf_context(structured, "sample.pdf")

    assert "- 추진 방향" in context
    assert "- 1" not in context
    assert "- 02" not in context


def test_build_procurement_pdf_context_filters_toc_and_sentence_fragments():
    structured = {
        "title": "파주시 공공기관 경영평가 착수보고",
        "page_count": 26,
        "has_tables": True,
        "raw_text": "경영평가 개요 추진일정 추진절차",
        "pages": [
            {"page": 1, "headings": ["CONTENTS"], "preview": "경영평가 개요 추진일정 추진절차", "has_tables": False},
            {"page": 2, "headings": ["지방출자·출연기관경영평가추진근거"], "preview": "평가 추진 근거와 대상 기관 범위", "has_tables": False},
        ],
        "sections": [
            {"heading": "CONTENTS", "content": ""},
            {"heading": "02 03 04", "content": "경영평가 개요 추진일정 추진절차"},
            {"heading": "지방출자·출연기관경영평가추진근거", "content": "평가 추진 근거와 대상 기관 범위를 설명한다."},
            {"heading": "「지방자치단체출자·", "content": ""},
            {"heading": "매년8월31일까지", "content": ""},
            {"heading": "시행하여야합니다.", "content": "추진근거와 평가 제외 기준을 정리한다."},
            {"heading": "파주시공공기관(장) 경영평가추진절차", "content": "평가 준비, 평가 시행, 결과 확정 절차를 설명한다."},
        ],
    }

    context = build_procurement_pdf_context(structured, "kickoff.pdf")

    assert "- 지방출자·출연기관경영평가추진근거" in context
    assert "- 파주시공공기관(장) 경영평가추진절차" in context
    assert "- CONTENTS" not in context
    assert "- 02 03 04" not in context
    assert "- 시행하여야합니다." not in context


def test_build_procurement_pdf_context_uses_page_classifier_for_ppt_candidates():
    structured = {
        "title": "공공기관 경영평가 착수보고",
        "page_count": 5,
        "has_tables": True,
        "raw_text": "경영평가 개요 평가 지표 추진 일정",
        "pages": [
            {"page": 1, "headings": ["CONTENTS"], "preview": "ONTENTS 평가 지표 추진 일정", "has_tables": False},
            {"page": 2, "headings": ["평가 지표 체계"], "preview": "평가 기준 배점 지표 설명", "has_tables": True},
            {"page": 4, "headings": ["세부 추진 일정"], "preview": "착수 중간 완료 일정", "has_tables": False},
        ],
        "sections": [
            {"heading": "평가 지표 체계", "content": "평가 기준과 배점을 설명한다."},
            {"heading": "세부 추진 일정", "content": "착수, 중간, 완료 일정을 제시한다."},
        ],
    }

    context = build_procurement_pdf_context(structured, "kickoff.pdf")

    assert "1p [개요/배경] ONTENTS" not in context
    assert "- 2p [평가기준/지표] 평가 지표 체계" in context
    assert "- 4p [일정/마일스톤] 세부 추진 일정" in context
    assert "2p 평가 지표 체계 | 권장 시각자료: 평가기준 표" in context
    assert "4p 세부 추진 일정 | 권장 시각자료: 타임라인" in context
    assert "평가 대응 전략 — 2p [평가기준/지표] 평가 지표 체계" in context
    assert "일정 및 마일스톤 — 4p [일정/마일스톤] 세부 추진 일정" in context


def test_parse_procurement_pdf_context_returns_design_hints_and_candidates():
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

    parsed = parse_procurement_pdf_context(context)

    assert parsed["page_classifications"] == [
        {"page": 3, "label": "평가기준/지표", "detail": "평가 지표 체계"}
    ]
    assert parsed["page_design_hints"] == [
        {
            "page": 3,
            "detail": "평가 지표 체계",
            "visual_type": "평가기준 표",
            "layout_hint": "상단 핵심 메시지 / 중앙 배점·평가표 / 하단 대응 포인트",
            "label": "평가기준/지표",
        }
    ]
    assert parsed["ppt_candidates"] == [
        {
            "candidate_label": "평가 대응 전략",
            "page": 3,
            "label": "평가기준/지표",
            "detail": "평가 지표 체계",
        }
    ]
