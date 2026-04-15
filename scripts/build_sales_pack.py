#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass
from pathlib import Path
import sys


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from build_sales_intro_pdf import _build_html, _build_pdf_from_html, _resolve_repo_path


@dataclass(frozen=True)
class SalesDocument:
    key: str
    source: str
    title: str
    slug: str


DOCUMENTS: tuple[SalesDocument, ...] = (
    SalesDocument(
        key="executive_intro",
        source="docs/sales/executive_intro.md",
        title="DecisionDoc AI 소개서",
        slug="decisiondoc_ai_executive_intro_ko",
    ),
    SalesDocument(
        key="meeting_onepager",
        source="docs/sales/meeting_onepager.md",
        title="DecisionDoc AI 미팅용 1장 요약",
        slug="decisiondoc_ai_meeting_onepager_ko",
    ),
    SalesDocument(
        key="notebooklm_comparison",
        source="docs/sales/notebooklm_comparison.md",
        title="DecisionDoc AI vs NotebookLM",
        slug="decisiondoc_ai_notebooklm_comparison_ko",
    ),
    SalesDocument(
        key="internal_deployment_brief",
        source="docs/sales/internal_deployment_brief.md",
        title="DecisionDoc AI 내부 설치형 도입 설명서",
        slug="decisiondoc_ai_internal_deployment_brief_ko",
    ),
)


def _select_documents(keys: list[str] | None) -> list[SalesDocument]:
    if not keys:
        return list(DOCUMENTS)
    wanted = {key.strip() for key in keys if key.strip()}
    return [doc for doc in DOCUMENTS if doc.key in wanted]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the DecisionDoc AI sales PDF pack.")
    parser.add_argument(
        "--docs",
        nargs="*",
        choices=[doc.key for doc in DOCUMENTS],
        help="Subset of sales docs to build. Defaults to all.",
    )
    parser.add_argument(
        "--output-dir",
        default="output/pdf",
        help="Output directory for generated HTML/PDF files.",
    )
    parser.add_argument(
        "--html-only",
        action="store_true",
        help="Only write HTML artifacts.",
    )
    args = parser.parse_args(argv)

    output_dir = _resolve_repo_path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    docs = _select_documents(args.docs)
    if not docs:
        raise SystemExit("No sales docs selected.")

    for doc in docs:
        markdown = _resolve_repo_path(doc.source).read_text(encoding="utf-8")
        html_text = _build_html(markdown, title=doc.title)
        html_path = output_dir / f"{doc.slug}.html"
        pdf_path = output_dir / f"{doc.slug}.pdf"
        html_path.write_text(html_text, encoding="utf-8")
        print(f"html_written={html_path}")
        if args.html_only:
            continue
        pdf_bytes = asyncio.run(_build_pdf_from_html(html_text))
        pdf_path.write_bytes(pdf_bytes)
        print(f"pdf_written={pdf_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
