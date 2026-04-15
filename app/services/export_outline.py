"""Shared helpers for finished-document export summaries."""
from __future__ import annotations

from typing import Any

from app.services.export_labels import humanize_doc_type
from app.services.markdown_utils import parse_markdown_blocks


def _clean_text(value: Any) -> str:
    return " ".join(str(value or "").replace("**", "").replace("`", "").split())


def _truncate(text: str, limit: int = 120) -> str:
    compact = _clean_text(text)
    if len(compact) <= limit:
        return compact
    return compact[: limit - 1].rstrip() + "…"


def summarize_export_docs(docs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    summaries: list[dict[str, Any]] = []

    for idx, doc in enumerate(docs, start=1):
        markdown = str(doc.get("markdown", ""))
        doc_type = str(doc.get("doc_type", "document"))
        label = humanize_doc_type(doc_type)
        blocks = parse_markdown_blocks(markdown)

        lead = ""
        headings: list[str] = []
        table_count = 0
        bullet_count = 0

        for block in blocks:
            block_type = block.get("type")
            if block_type == "heading":
                text = _clean_text(block.get("text", ""))
                if text:
                    headings.append(text)
            elif block_type == "paragraph" and not lead:
                text = _clean_text(block.get("text", ""))
                if text:
                    lead = text
            elif block_type == "list_item":
                bullet_count += 1
                if not lead:
                    text = _clean_text(block.get("text", ""))
                    if text:
                        lead = text
            elif block_type == "table":
                table_count += 1

        primary_sections = [item for item in headings[1:4] if item]
        section_hint = " · ".join(primary_sections) if primary_sections else "핵심 섹션 요약"

        metric_parts: list[str] = []
        if table_count:
            metric_parts.append(f"표 {table_count}개")
        if bullet_count:
            metric_parts.append(f"목록 {bullet_count}개")
        metrics = " / ".join(metric_parts) if metric_parts else "서술형 중심 문서"

        summaries.append(
            {
                "index": f"{idx:02d}",
                "label": label,
                "lead": _truncate(lead or f"{label}의 핵심 내용을 정리한 문서입니다."),
                "sections": section_hint,
                "metrics": metrics,
                "table_count": table_count,
                "bullet_count": bullet_count,
                "heading_count": len(headings),
            }
        )

    return summaries


def summarize_export_package(docs: list[dict[str, Any]]) -> dict[str, str]:
    summaries = summarize_export_docs(docs)
    doc_count = len(summaries)
    table_total = sum(int(summary.get("table_count", 0) or 0) for summary in summaries)
    bullet_total = sum(int(summary.get("bullet_count", 0) or 0) for summary in summaries)
    heading_total = sum(int(summary.get("heading_count", 0) or 0) for summary in summaries)
    top_labels = " · ".join(str(summary["label"]) for summary in summaries[:3]) if summaries else "문서 구성 없음"
    return {
        "doc_count": str(doc_count),
        "table_total": str(table_total),
        "bullet_total": str(bullet_total),
        "heading_total": str(heading_total),
        "headline": top_labels,
    }
