#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import html
from pathlib import Path
import re
import sys

from playwright.async_api import async_playwright


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _render_inline(text: str) -> str:
    rendered = html.escape(text)
    rendered = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", rendered)
    rendered = re.sub(r"`([^`]+)`", r"<code>\1</code>", rendered)
    return rendered


def _is_markdown_table_separator(text: str) -> bool:
    stripped = text.strip()
    if not stripped.startswith("|"):
        return False
    cells = [cell.strip() for cell in stripped.strip("|").split("|")]
    return bool(cells) and all(cell and set(cell) <= {"-", ":"} for cell in cells)


def _parse_table_cells(text: str) -> list[str]:
    return [cell.strip() for cell in text.strip().strip("|").split("|")]


def _markdown_to_html(markdown: str) -> str:
    lines: list[str] = []
    in_list = False

    def close_list() -> None:
        nonlocal in_list
        if in_list:
            lines.append("</ul>")
            in_list = False

    raw_lines = markdown.splitlines()
    index = 0
    while index < len(raw_lines):
        raw = raw_lines[index]
        line = raw.rstrip()
        stripped = line.strip()

        if stripped.startswith("|") and index + 1 < len(raw_lines):
            separator = raw_lines[index + 1].strip()
            if _is_markdown_table_separator(separator):
                close_list()
                headers = _parse_table_cells(stripped)
                body_rows: list[list[str]] = []
                index += 2
                while index < len(raw_lines):
                    row_text = raw_lines[index].strip()
                    if not row_text.startswith("|"):
                        break
                    body_rows.append(_parse_table_cells(row_text))
                    index += 1

                lines.append("<table>")
                lines.append("<thead><tr>")
                lines.extend(f"<th>{_render_inline(cell)}</th>" for cell in headers)
                lines.append("</tr></thead>")
                if body_rows:
                    lines.append("<tbody>")
                    for row in body_rows:
                        lines.append("<tr>")
                        lines.extend(f"<td>{_render_inline(cell)}</td>" for cell in row)
                        lines.append("</tr>")
                    lines.append("</tbody>")
                lines.append("</table>")
                continue

        if stripped.startswith("### "):
            close_list()
            lines.append(f"<h3>{_render_inline(stripped[4:])}</h3>")
        elif stripped.startswith("## "):
            close_list()
            lines.append(f"<h2>{_render_inline(stripped[3:])}</h2>")
        elif stripped.startswith("# "):
            close_list()
            lines.append(f"<h1>{_render_inline(stripped[2:])}</h1>")
        elif stripped.startswith(("- ", "* ")):
            if not in_list:
                lines.append("<ul>")
                in_list = True
            lines.append(f"<li>{_render_inline(stripped[2:])}</li>")
        elif not stripped:
            close_list()
            lines.append("<div class='spacer'></div>")
        else:
            close_list()
            lines.append(f"<p>{_render_inline(stripped)}</p>")

        index += 1
    close_list()
    return "\n".join(lines)


def _build_html(markdown: str, *, title: str) -> str:
    content = _markdown_to_html(markdown)
    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{html.escape(title)}</title>
  <style>
    @page {{
      size: A4;
      margin: 20mm 18mm 18mm 18mm;
    }}
    body {{
      font-family: "Apple SD Gothic Neo", "Malgun Gothic", "Nanum Gothic", sans-serif;
      color: #111827;
      margin: 0;
      background: #f4f6f8;
    }}
    .page {{
      width: 210mm;
      min-height: 297mm;
      margin: 0 auto;
      background: white;
      box-sizing: border-box;
      padding: 18mm 18mm 20mm 18mm;
    }}
    .eyebrow {{
      display: inline-block;
      padding: 4px 10px;
      border-radius: 999px;
      background: #e8f1fb;
      color: #124a84;
      font-size: 10pt;
      font-weight: 700;
      letter-spacing: 0.04em;
    }}
    .hero {{
      margin-top: 10mm;
      margin-bottom: 10mm;
      padding: 10mm;
      border: 1px solid #d6dde5;
      border-radius: 14px;
      background: linear-gradient(180deg, #f8fbff 0%, #ffffff 100%);
    }}
    h1 {{
      font-size: 24pt;
      line-height: 1.2;
      margin: 0 0 4mm 0;
      color: #0f172a;
    }}
    h2 {{
      font-size: 15pt;
      margin: 8mm 0 3mm 0;
      padding-bottom: 2mm;
      border-bottom: 1px solid #dbe2ea;
      color: #0f172a;
    }}
    h3 {{
      font-size: 12pt;
      margin: 5mm 0 2mm 0;
      color: #1f2937;
    }}
    p, li {{
      font-size: 10.5pt;
      line-height: 1.65;
      margin: 0 0 2.2mm 0;
    }}
    ul {{
      margin: 0 0 2mm 0;
      padding-left: 5mm;
    }}
    code {{
      font-family: "SFMono-Regular", "Menlo", "Consolas", monospace;
      font-size: 9pt;
      padding: 1px 5px;
      border-radius: 6px;
      background: #eef2f7;
      color: #1e3a5f;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      margin: 3mm 0 4mm 0;
      font-size: 9.6pt;
    }}
    th, td {{
      border: 1px solid #d6dde5;
      padding: 2.5mm 2.8mm;
      text-align: left;
      vertical-align: top;
      line-height: 1.5;
    }}
    th {{
      background: #f4f7fb;
      color: #0f172a;
      font-weight: 700;
    }}
    .summary {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 4mm;
      margin-top: 6mm;
    }}
    .summary-card {{
      border: 1px solid #d6dde5;
      border-radius: 12px;
      padding: 4mm;
      background: #fbfdff;
    }}
    .summary-card h3 {{
      margin-top: 0;
    }}
    .spacer {{
      height: 2mm;
    }}
    .footer-note {{
      margin-top: 10mm;
      padding-top: 4mm;
      border-top: 1px solid #e5e7eb;
      color: #475569;
      font-size: 9pt;
    }}
  </style>
</head>
<body>
  <div class="page">
    <div class="eyebrow">DecisionDoc AI</div>
    <div class="hero">
      <h1>{html.escape(title)}</h1>
      <p>내부 설치형 AI 문서 운영 플랫폼</p>
      <div class="summary">
        <div class="summary-card">
          <h3>핵심 포지션</h3>
          <p>자료를 정리하는 도구가 아니라, 조직이 실제 문서를 만들고 승인하고 제출하는 운영 플랫폼입니다.</p>
        </div>
        <div class="summary-card">
          <h3>권장 도입 형태</h3>
          <p>운영자 공용 환경과 고객사 전용 환경을 분리하는 웹 기반 내부 설치형 구조를 권장합니다.</p>
        </div>
      </div>
    </div>
    {content}
    <div class="footer-note">
      본 문서는 외부 소개 및 초기 미팅용 요약본입니다. 실제 도입 시에는 고객사별 전용 운영 환경, 권한 정책, 데이터 분리 정책 기준으로 별도 제안이 가능합니다.
    </div>
  </div>
</body>
</html>
"""


async def _build_pdf_from_html(html_text: str) -> bytes:
    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        try:
            page = await browser.new_page()
            await page.set_content(html_text, wait_until="domcontentloaded")
            pdf_bytes = await page.pdf(
                format="A4",
                print_background=True,
                prefer_css_page_size=True,
            )
        finally:
            await browser.close()

    return pdf_bytes


def _resolve_repo_path(value: str) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return REPO_ROOT / path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build DecisionDoc AI sales PDF from markdown.")
    parser.add_argument(
        "--source",
        default="docs/sales/executive_intro.md",
        help="Markdown source path",
    )
    parser.add_argument(
        "--html-output",
        default="output/pdf/decisiondoc_ai_executive_intro_ko.html",
        help="Intermediate HTML output path",
    )
    parser.add_argument(
        "--pdf-output",
        default="output/pdf/decisiondoc_ai_executive_intro_ko.pdf",
        help="Final PDF output path",
    )
    parser.add_argument(
        "--html-only",
        action="store_true",
        help="Only build the intermediate HTML file",
    )
    parser.add_argument(
        "--title",
        default="DecisionDoc AI 소개서",
        help="Document title shown in the rendered HTML/PDF",
    )
    args = parser.parse_args(argv)

    source_path = _resolve_repo_path(args.source)
    html_output = _resolve_repo_path(args.html_output)
    pdf_output = _resolve_repo_path(args.pdf_output)

    markdown = source_path.read_text(encoding="utf-8")
    title = args.title
    html_text = _build_html(markdown, title=title)
    html_output.parent.mkdir(parents=True, exist_ok=True)
    html_output.write_text(html_text, encoding="utf-8")
    print(f"html_written={html_output}")

    if args.html_only:
        return 0

    pdf_output.parent.mkdir(parents=True, exist_ok=True)
    pdf_bytes = asyncio.run(_build_pdf_from_html(html_text))
    pdf_output.write_bytes(pdf_bytes)
    print(f"pdf_written={pdf_output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
