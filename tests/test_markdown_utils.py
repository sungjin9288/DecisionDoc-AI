from app.services.markdown_utils import (
    build_markdown_table,
    build_slide_outline_table,
    parse_markdown_blocks,
)


def test_build_markdown_table_escapes_pipe_characters() -> None:
    table = build_markdown_table(
        [["1", "표지", "사업명 | 발주기관 | 제안사", "브랜드 색상 | 로고 배치"]],
        ["페이지", "슬라이드 제목", "핵심 내용", "디자인 가이드"],
    )

    assert "사업명 \\| 발주기관 \\| 제안사" in table
    assert "브랜드 색상 \\| 로고 배치" in table


def test_parse_markdown_blocks_preserves_escaped_pipe_cells() -> None:
    markdown = "\n".join(
        [
            "| 페이지 | 슬라이드 제목 | 핵심 메시지 | 입증 포인트 | 권장 시각자료 | 배치 가이드 |",
            "| --- | --- | --- | --- | --- | --- |",
            "| 1 | 표지 | 사업명 \\| 발주기관 \\| 제안사 | 평가 포인트 1 \\| 평가 포인트 2 | 비교 표 | 브랜드 색상 \\| 로고 배치 |",
        ]
    )

    blocks = parse_markdown_blocks(markdown)
    assert len(blocks) == 1
    assert blocks[0]["type"] == "table"
    assert blocks[0]["rows"][0][2] == "사업명 | 발주기관 | 제안사"
    assert blocks[0]["rows"][0][3] == "평가 포인트 1 | 평가 포인트 2"
    assert blocks[0]["rows"][0][5] == "브랜드 색상 | 로고 배치"


def test_build_slide_outline_table_renders_visual_and_layout_guidance() -> None:
    table = build_slide_outline_table(
        [
            {
                "page": 3,
                "title": "사업 배경",
                "core_message": "정책 목표와 현장 병목을 한 장에서 연결해 보여준다.",
                "evidence_points": ["정책 지표 3개 제시", "현장 병목 수치 2개 강조"],
                "visual_type": "프로세스 흐름도",
                "visual_brief": "좌측 현행 프로세스, 우측 개선 후 프로세스 비교",
                "layout_hint": "상단 결론 문장, 좌우 2단 비교, 우측 하단에 KPI 배지 배치",
            }
        ]
    )

    assert "| 페이지 | 슬라이드 제목 | 핵심 메시지 | 입증 포인트 | 권장 시각자료 | 배치 가이드 |" in table
    assert "정책 지표 3개 제시 · 현장 병목 수치 2개 강조" in table
    assert "프로세스 흐름도 — 좌측 현행 프로세스, 우측 개선 후 프로세스 비교" in table
    assert "상단 결론 문장, 좌우 2단 비교, 우측 하단에 KPI 배지 배치" in table
