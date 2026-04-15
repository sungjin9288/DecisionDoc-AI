from app.services.markdown_utils import build_markdown_table, parse_markdown_blocks


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
            "| 페이지 | 슬라이드 제목 | 핵심 내용 | 디자인 가이드 |",
            "| --- | --- | --- | --- |",
            "| 1 | 표지 | 사업명 \\| 발주기관 \\| 제안사 | 브랜드 색상 \\| 로고 배치 |",
        ]
    )

    blocks = parse_markdown_blocks(markdown)
    assert len(blocks) == 1
    assert blocks[0]["type"] == "table"
    assert blocks[0]["rows"][0][2] == "사업명 | 발주기관 | 제안사"
    assert blocks[0]["rows"][0][3] == "브랜드 색상 | 로고 배치"
