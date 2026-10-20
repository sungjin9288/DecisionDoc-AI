"""조견표: evaluation items mapped to draft headings and confirmed PDF pages."""
from __future__ import annotations

from pathlib import Path

from app.public_sector.crosswalk import build_crosswalk, crosswalk_table_markdown
from app.public_sector.models import RfpProfile
from app.public_sector.readers import Block, SourceDocument, read_document
from tests.async_helper import run_async

FILLER = "\n".join(f"- 세부 설명 문장 {index}: 검색 품질과 운영 절차를 설명한다." for index in range(40))
DRAFT_MD = f"""# 기술 제안서

## 목차
- Ⅰ. 사업 이해
- 1. 검색 기능
- 2. 권한 관리

## Ⅰ. 사업 이해
사업 목표를 정리한다.
{FILLER}

### 1. 검색 기능
통합 검색은 SFR-001을 충족한다.
{FILLER}

### 2. 권한 관리
SFR-002 권한별 열람 제어를 제공한다.
"""


def _profile() -> RfpProfile:
    return RfpProfile.model_validate({
        "schema_version": "publicdoc.rfp_profile.v1",
        "project": {"name": "[합성] 문서관리시스템 고도화"},
        "evaluation_items": [
            {"name": "사업 이해도", "points": 10, "headings": ["Ⅰ. 사업 이해"]},
            {"name": "기술 부문", "points": 60, "headings": ["1. 검색 기능", "2. 권한 관리"]},
            {"name": "프로젝트 관리", "points": 20},
        ],
    })


def _draft(tmp_path: Path) -> SourceDocument:
    path = tmp_path / "draft.md"
    path.write_text(DRAFT_MD, encoding="utf-8")
    return read_document(path)


def test_structured_draft_maps_items_and_asks_for_the_pdf_for_pages(tmp_path: Path) -> None:
    report = build_crosswalk(_profile(), _draft(tmp_path))

    assert [row["status"] for row in report["rows"]] == ["mapped", "mapped", "unmapped"]
    assert report["unmapped"] == ["프로젝트 관리"]
    assert report["pages_available"] is False and "--pdf" in report["note"]
    table = crosswalk_table_markdown(report)
    assert "| 사업 이해도 | 10 | Ⅰ. 사업 이해 | 확인 필요 |" in table
    assert "| 프로젝트 관리 | 20 | 프로젝트 관리 (찾지 못함) | - |" in table


def test_pdf_pages_follow_body_text_not_cover_or_table_of_contents() -> None:
    # Cover summary on p.1 and contents on p.2 repeat the headings; the body starts on p.2.
    draft = SourceDocument("draft.md", "md", (
        Block("기술 제안서", 1), Block("Ⅰ. 사업 이해", 2), Block("사업 목표를 정리한다."),
        Block("1. 검색 기능", 3), Block("통합 검색은 SFR-001을 충족한다."),
    ))
    pdf = SourceDocument("draft.pdf", "pdf", (
        Block("Ⅰ. 사업 이해", page=1), Block("1. 검색 기능", page=1), Block("완성형 문서 패키지", page=1),
        Block("Ⅰ. 사업 이해", page=2), Block("1. 검색 기능", page=2), Block("2. 권한 관리", page=2),
        Block("Ⅰ. 사업 이해", page=2), Block("사업 목표를 정리한다.", page=2),
        Block("1. 검색 기능", page=3), Block("통합 검색은 SFR-001을", page=3), Block("충족한다.", page=3),
    ))
    profile = RfpProfile.model_validate({
        "schema_version": "publicdoc.rfp_profile.v1",
        "project": {"name": "합성"},
        "evaluation_items": [{"name": "사업 이해도", "headings": ["Ⅰ. 사업 이해", "1. 검색 기능"]}],
    })

    placements = build_crosswalk(profile, draft, pdf)["rows"][0]["placements"]

    assert [(p["page"], p["page_basis"]) for p in placements] == [(2, "본문 확인"), (3, "본문 확인")]


def test_pdf_alone_marks_guessed_pages_for_review() -> None:
    pdf = SourceDocument("draft.pdf", "pdf", (Block("Ⅰ. 사업 이해", page=4), Block("본문", page=4)))
    profile = RfpProfile.model_validate({
        "schema_version": "publicdoc.rfp_profile.v1",
        "project": {"name": "합성"},
        "evaluation_items": [{"name": "사업 이해도", "headings": ["Ⅰ. 사업 이해"]}],
    })

    report = build_crosswalk(profile, pdf)

    assert report["unconfirmed_pages"] == ["Ⅰ. 사업 이해"]
    assert "| 4 (확인 필요) |" in crosswalk_table_markdown(report)


def test_rendered_pdf_pages_are_confirmed_against_the_draft(tmp_path: Path) -> None:
    from app.services.pdf_service import build_pdf

    pdf_path = tmp_path / "proposal.pdf"
    pdf_path.write_bytes(run_async(build_pdf([{"doc_type": "tech_proposal", "markdown": DRAFT_MD}], "[합성] 제안서")))
    pdf = read_document(pdf_path)

    report = build_crosswalk(_profile(), _draft(tmp_path), pdf)

    placements = [p for row in report["rows"][:2] for p in row["placements"]]
    assert all(p["page_basis"] == "본문 확인" for p in placements)
    pages = [p["page"] for p in placements]
    assert pages == sorted(pages) and len(set(pages)) >= 2
    # Each confirmed page really holds the heading followed by its body text.
    for placement in placements:
        texts = [block.text for block in pdf.blocks if block.page == placement["page"]]
        assert any(placement["heading"].replace(" ", "") in text.replace(" ", "") for text in texts)


def test_pdf_bullets_and_table_cells_still_confirm_the_body() -> None:
    # Office-to-PDF conversion turns "- " into a bullet glyph line and "| a | b |" into one line per cell.
    draft = SourceDocument("draft.md", "md", (
        Block("현황 및 문제점", 2), Block("- 부서별 공유폴더에 문서가 분산되어 있다"),
        Block("추진 일정", 2), Block("| 마일스톤 | 시점 | 완료 기준 |"),
        Block("적용 기술", 2), Block("| 구성 영역 | 적용 기술 | 적용 목적 |"),
    ))
    pdf = SourceDocument("draft.pdf", "pdf", (
        Block("핵심 섹션: 현황 및 문제점", page=1),
        Block("현황 및 문제점", page=4), Block("", page=4), Block("부서별 공유폴더에 문서가", page=4),
        Block("추진 일정", page=7), Block("마일스톤", page=7), Block("시점", page=7), Block("완료 기준", page=7),
        # The table under 적용 기술 repeats the heading as a column name.
        Block("적용 기술", page=8), Block("구성 영역", page=8), Block("적용 기술", page=8), Block("적용 목적", page=8),
    ))
    profile = RfpProfile.model_validate({
        "schema_version": "publicdoc.rfp_profile.v1",
        "project": {"name": "합성"},
        "evaluation_items": [{"name": "이해도", "headings": ["현황 및 문제점", "추진 일정", "적용 기술"]}],
    })

    placements = build_crosswalk(profile, draft, pdf)["rows"][0]["placements"]

    assert [(p["page"], p["page_basis"]) for p in placements] == [(4, "본문 확인"), (7, "본문 확인"), (8, "본문 확인")]
