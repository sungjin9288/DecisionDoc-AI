"""Layout checks for Markdown tables in the Chromium-rendered PDF export.

The PDF export prints the HTML from ``_render_html`` with Chromium. These tests
measure the same HTML at the A4 content width so that short Korean cell words
stay on one line and long unbreakable tokens still stay inside the page.
"""

from tests.async_helper import run_async

# A4 width (210mm) minus the default 20mm left/right PDF margins.
_A4_CONTENT_WIDTH_PX = round((210 - 40) / 25.4 * 96)

_TABLE_MARKDOWN = (
    "# 비교\n\n"
    "| 구분 | 경로 | 선택지 | 비고 |\n"
    "| --- | --- | --- | --- |\n"
    "| 파일 | C:\\docs\\보고서.docx | A \\| B | 역슬래시와 파이프 보존 |\n"
    "| 일정 | 2026-10-01 | 1단계 | 긴 셀 내용이 여러 줄로 감싸져야 하며 표 폭을 넘지 않아야 합니다 |\n"
    "| 링크 | https://example.test/" + "a" * 160 + " | 없음 | 긴 토큰 |\n"
)

_MEASURE_SCRIPT = """() => {
  const lineCount = el => {
    const range = document.createRange();
    range.selectNodeContents(el);
    return new Set([...range.getClientRects()].map(rect => Math.round(rect.top))).size;
  };
  const table = document.querySelector('.markdown-table');
  const body = document.querySelector('.page-body');
  return {
    cells: [...table.querySelectorAll('th, td')].map(el => ({text: el.textContent, lines: lineCount(el)})),
    tableRight: table.getBoundingClientRect().right,
    bodyRight: body.getBoundingClientRect().right,
  };
}"""


async def _measure_table() -> dict:
    from playwright.async_api import async_playwright

    from app.services.pdf_service import _render_html

    html = _render_html([{"doc_type": "adr", "markdown": _TABLE_MARKDOWN}], title="표 배치")
    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        try:
            page = await browser.new_page(viewport={"width": _A4_CONTENT_WIDTH_PX, "height": 1200})
            await page.emulate_media(media="print")
            await page.set_content(html, wait_until="domcontentloaded")
            return await page.evaluate(_MEASURE_SCRIPT)
        finally:
            await browser.close()


def test_pdf_table_keeps_short_korean_cell_words_on_one_line():
    measured = run_async(_measure_table())
    lines = {cell["text"]: cell["lines"] for cell in measured["cells"]}

    for word in ("구분", "경로", "선택지", "비고", "파일", "일정", "1단계", "링크", "없음"):
        assert lines[word] == 1, (word, lines[word])


def test_pdf_table_wraps_long_tokens_inside_the_page_width():
    measured = run_async(_measure_table())

    assert measured["tableRight"] <= measured["bodyRight"] + 1, measured
    texts = [cell["text"] for cell in measured["cells"]]
    assert "https://example.test/" + "a" * 160 in texts
    assert "C:\\docs\\보고서.docx" in texts
    assert "A | B" in texts


def test_table_cell_break_points_keep_escaped_text_and_markup_intact():
    from app.services.pdf_service import _table_cell_html

    token = "&<>" * 10 + "x" * 30
    html = _table_cell_html(f"**{token}** 짧은 단어")

    assert html.startswith("<strong>") and "</strong> 짧은 단어" in html
    assert "<wbr>" in html
    for entity in ("&amp;", "&lt;", "&gt;"):
        assert all(not piece.endswith(entity[:-1]) for piece in html.split("<wbr>")), html
    assert html.replace("<wbr>", "") == f"<strong>{'&amp;&lt;&gt;' * 10}{'x' * 30}</strong> 짧은 단어"
    assert _table_cell_html("착수") == "착수"


_WIDE_TABLE_MARKDOWN = (
    "| 구분 | 사업명 | 시작 | 파일 | 담당 | 비고 |\n"
    "| --- | --- | --- | --- | --- | --- |\n"
    "| 1 | 소프트웨어사업영향평가 | 2026-10-01T09:00:00Z | report_final_v2.docx | 정보화담당관실 | 검토완료 |\n"
    "| 2 | 클라우드전환컨설팅 | 2026-11-15T13:30:00Z | appendix_budget.xlsx | 정보보호팀 | 보류 |\n"
)


async def _measure_markdown(markdown: str) -> dict:
    from playwright.async_api import async_playwright

    from app.services.pdf_service import _render_html

    html = _render_html([{"doc_type": "adr", "markdown": markdown}], title="표 배치")
    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        try:
            page = await browser.new_page(viewport={"width": _A4_CONTENT_WIDTH_PX, "height": 1200})
            await page.emulate_media(media="print")
            await page.set_content(html, wait_until="domcontentloaded")
            return await page.evaluate(_MEASURE_SCRIPT)
        finally:
            await browser.close()


def test_pdf_wide_table_with_mid_length_tokens_stays_inside_the_page():
    measured = run_async(_measure_markdown(_WIDE_TABLE_MARKDOWN))

    assert measured["tableRight"] <= measured["bodyRight"] + 1, measured
    lines = {cell["text"]: cell["lines"] for cell in measured["cells"]}
    for word in ("구분", "시작", "파일", "담당", "비고", "보류"):
        assert lines[word] == 1, (word, lines[word])
    assert "2026-10-01T09:00:00Z" in lines
