"""review_preview — build lightweight preview data and review dashboard HTML."""
from __future__ import annotations

import html
import re
import zipfile
from io import BytesIO
from typing import Any

from docx import Document
from pptx import Presentation


def _dedupe_lines(lines: list[str], limit: int) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for raw in lines:
        line = " ".join(str(raw).split()).strip()
        if not line or line in seen:
            continue
        deduped.append(line)
        seen.add(line)
        if len(deduped) >= limit:
            break
    return deduped


def collect_docx_preview_lines(raw: bytes, *, limit: int = 16) -> list[str]:
    document = Document(BytesIO(raw))
    return _dedupe_lines([paragraph.text for paragraph in document.paragraphs], limit)


def collect_pptx_preview_lines(raw: bytes, *, limit: int = 16) -> list[str]:
    presentation = Presentation(BytesIO(raw))
    lines: list[str] = []
    for idx, slide in enumerate(presentation.slides, start=1):
        title = ""
        if getattr(slide.shapes, "title", None) is not None and slide.shapes.title is not None:
            title = slide.shapes.title.text.strip()
        title = title or f"슬라이드 {idx}"
        lines.append(f"[{idx}] {title}")
        body_lines: list[str] = []
        for shape in slide.shapes:
            if not getattr(shape, "has_text_frame", False):
                continue
            if getattr(slide.shapes, "title", None) is not None and shape == slide.shapes.title:
                continue
            for paragraph in shape.text_frame.paragraphs:
                text = paragraph.text.strip()
                if text:
                    body_lines.append(f"- {text}")
        lines.extend(body_lines[:2])
    return _dedupe_lines(lines, limit)


def collect_hwpx_preview_lines(raw: bytes, *, limit: int = 16) -> list[str]:
    with zipfile.ZipFile(BytesIO(raw), "r") as archive:
        xml = archive.read("Contents/section0.xml").decode("utf-8", errors="ignore")
    texts = re.findall(r"<(?:\w+:)?t>(.*?)</(?:\w+:)?t>", xml, flags=re.DOTALL)
    cleaned = [html.unescape(re.sub(r"\s+", " ", text)).strip() for text in texts]
    return _dedupe_lines(cleaned, limit)


def preview_export_bytes(export_format: str, raw: bytes, *, limit: int = 16) -> list[str]:
    if export_format == "docx":
        return collect_docx_preview_lines(raw, limit=limit)
    if export_format == "pptx":
        return collect_pptx_preview_lines(raw, limit=limit)
    if export_format == "hwp":
        return collect_hwpx_preview_lines(raw, limit=limit)
    return []


def build_review_dashboard(
    *,
    generated_at: str,
    manifest: dict[str, Any],
    bundle_previews: dict[str, dict[str, list[str]]],
) -> str:
    bundle_sections: list[str] = []
    for bundle_type, bundle in manifest.get("bundles", {}).items():
        exports = bundle.get("exports", {})
        markdown_docs = bundle.get("markdown_docs", {})
        preview_files = bundle.get("preview_files", {})

        export_links = "".join(
            f'<a class="pill" href="{html.escape(path)}">{label.upper()}</a>'
            for label, path in exports.items()
        )
        markdown_links = "".join(
            f'<a class="pill secondary" href="{html.escape(path)}">{html.escape(doc_type)}</a>'
            for doc_type, path in markdown_docs.items()
        )

        preview_blocks: list[str] = []
        for fmt in ("docx", "pptx", "hwp"):
            preview_lines = bundle_previews.get(bundle_type, {}).get(fmt, [])
            if not preview_lines:
                continue
            preview_path = preview_files.get(fmt, "")
            items = "".join(f"<li>{html.escape(line)}</li>" for line in preview_lines)
            preview_blocks.append(
                "<div class='preview-card'>"
                f"<div class='preview-head'><strong>{fmt.upper()} preview</strong>"
                + (
                    f"<a href='{html.escape(preview_path)}'>txt</a>"
                    if preview_path
                    else ""
                )
                + "</div>"
                f"<ul>{items}</ul>"
                "</div>"
            )

        pdf_embed = ""
        if exports.get("pdf"):
            pdf_embed = (
                "<div class='pdf-panel'>"
                "<div class='preview-head'><strong>PDF preview</strong></div>"
                f"<iframe src='{html.escape(exports['pdf'])}#toolbar=0&navpanes=0'></iframe>"
                "</div>"
            )

        bundle_sections.append(
            "<section class='bundle'>"
            f"<h2>{html.escape(bundle.get('title', bundle_type))}</h2>"
            f"<div class='bundle-meta'>{html.escape(bundle_type)} · 문서 {bundle.get('doc_count', 0)}개</div>"
            f"<div class='pill-row'>{export_links}</div>"
            f"<div class='pill-row'>{markdown_links}</div>"
            "<div class='preview-grid'>"
            + "".join(preview_blocks)
            + pdf_embed
            + "</div>"
            "</section>"
        )

    return f"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <title>Finished Document Review</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <style>
    :root {{
      color-scheme: light;
      --bg: #f5f7ff;
      --panel: #ffffff;
      --border: #d7ddf3;
      --text: #1f2543;
      --muted: #6b7392;
      --accent: #624fff;
      --accent-soft: #ece9ff;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Apple SD Gothic Neo", sans-serif;
      background: linear-gradient(180deg, #eef1ff 0%, var(--bg) 100%);
      color: var(--text);
    }}
    .shell {{
      width: min(1280px, calc(100vw - 40px));
      margin: 32px auto 48px;
    }}
    .hero {{
      background: linear-gradient(135deg, #1b2145 0%, #624fff 100%);
      color: white;
      border-radius: 28px;
      padding: 28px 30px;
      box-shadow: 0 24px 60px rgba(54, 63, 128, 0.18);
    }}
    .hero h1 {{ margin: 0 0 8px; font-size: 34px; }}
    .hero p {{ margin: 0; color: rgba(255,255,255,0.86); }}
    .bundle {{
      background: var(--panel);
      border: 1px solid var(--border);
      border-radius: 24px;
      padding: 24px;
      margin-top: 24px;
      box-shadow: 0 14px 36px rgba(73, 87, 155, 0.08);
    }}
    .bundle h2 {{ margin: 0 0 6px; font-size: 26px; }}
    .bundle-meta {{ color: var(--muted); margin-bottom: 14px; }}
    .pill-row {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-bottom: 12px;
    }}
    .pill {{
      display: inline-flex;
      align-items: center;
      gap: 6px;
      border-radius: 999px;
      background: var(--accent);
      color: white;
      padding: 8px 12px;
      text-decoration: none;
      font-weight: 600;
      font-size: 14px;
    }}
    .pill.secondary {{
      background: var(--accent-soft);
      color: var(--text);
    }}
    .preview-grid {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 16px;
      align-items: start;
    }}
    .preview-card, .pdf-panel {{
      border: 1px solid var(--border);
      border-radius: 18px;
      padding: 16px;
      background: #fafbff;
    }}
    .preview-head {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 10px;
      color: var(--muted);
    }}
    .preview-head a {{ color: var(--accent); text-decoration: none; font-size: 13px; }}
    ul {{ margin: 0; padding-left: 18px; }}
    li {{ margin: 0 0 8px; line-height: 1.5; }}
    iframe {{
      width: 100%;
      height: 560px;
      border: 0;
      border-radius: 12px;
      background: white;
    }}
    @media (max-width: 960px) {{
      .preview-grid {{ grid-template-columns: 1fr; }}
      .shell {{ width: min(100vw - 20px, 1280px); margin-top: 16px; }}
      iframe {{ height: 420px; }}
    }}
  </style>
</head>
<body>
  <main class="shell">
    <section class="hero">
      <h1>Finished Document Review</h1>
      <p>생성 시각: {html.escape(generated_at)} · export 파일과 preview 추출본을 한 화면에서 검토합니다.</p>
    </section>
    {''.join(bundle_sections)}
  </main>
</body>
</html>"""
