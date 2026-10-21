"""조견표: which draft heading answers each evaluation item, and on which PDF page.

PPS evaluation requires a cross-reference table with the page of each evaluation
item (조달청 협상에 의한 계약 제안서평가 세부기준 제6조의2). Page numbers come from
the rendered PDF that is actually submitted.

A heading's text also appears on cover summaries, the table of contents and running
headers, so a PDF page is confirmed by the body text that follows the heading in the
structured draft. With a PDF alone, pages fall back to skipping TOC-like pages and
the row says so.
"""
from __future__ import annotations

import re
from typing import Any

from app.public_sector.models import RfpProfile
from app.public_sector.readers import SourceDocument

_TOC_MIN_TARGETS = 3
_FOLLOW_SNIPPET = 10
_FOLLOW_WINDOW = 5
# Markdown marks (-, |, **) become bullets, cell breaks or nothing in a PDF, so compare letters only.
_NOT_LETTER_RE = re.compile(r"[^0-9A-Za-z\uac00-\ud7a3]")


def _norm(text: str) -> str:
    return re.sub(r"\s+", "", text)


def _letters(text: str) -> str:
    return _NOT_LETTER_RE.sub("", text)


def _is_heading_line(block_text: str, target: str) -> bool:
    """The line is the heading itself (allowing a number or mark), not a sentence citing it."""
    block, wanted = _norm(block_text), _norm(target)
    return bool(wanted) and wanted in block and len(block) <= len(wanted) + max(4, len(wanted) // 3)


def _heading_indexes(document: SourceDocument, target: str, *, headings_only: bool) -> list[int]:
    return [
        index for index, block in enumerate(document.blocks)
        if (block.heading_level is not None or not headings_only) and _is_heading_line(block.text, target)
    ]


def _follow_snippet(draft: SourceDocument, index: int) -> str:
    for block in draft.blocks[index + 1:]:
        if block.heading_level is not None:
            return ""
        return _letters(block.text)[:_FOLLOW_SNIPPET]
    return ""


def _followed_by(pages: SourceDocument, index: int, snippet: str, headings: list[str]) -> bool:
    """The draft's body text follows this line before any other draft heading does.

    Stopping at the next heading keeps a table-of-contents line, whose neighbours are
    other headings, from borrowing body text further down the page.
    """
    following = []
    for block in pages.blocks[index + 1:index + 1 + _FOLLOW_WINDOW]:
        if any(_is_heading_line(block.text, heading) for heading in headings):
            break
        following.append(_letters(block.text))
    return bool(snippet) and snippet in "".join(following)


def _toc_pages(pages: SourceDocument, targets: list[str]) -> set[int]:
    hits: dict[int, set[str]] = {}
    for target in targets:
        for index in _heading_indexes(pages, target, headings_only=False):
            hits.setdefault(pages.blocks[index].page, set()).add(target)
    threshold = max(_TOC_MIN_TARGETS, (len(set(targets)) + 1) // 2)
    return {page for page, found in hits.items() if len(found) >= threshold}


def _place(target: str, draft: SourceDocument, pages: SourceDocument | None, toc: set[int]) -> dict[str, Any]:
    structured = not draft.has_pages
    in_draft = _heading_indexes(draft, target, headings_only=True) if structured else []
    placement = {"heading": target, "found": bool(in_draft) or not structured, "page": None, "page_basis": None}
    if pages is None:
        return placement
    candidates = _heading_indexes(pages, target, headings_only=False)
    snippet = _follow_snippet(draft, in_draft[0]) if in_draft else ""
    # Other headings only: a table right below may repeat the target as a column name.
    headings = [block.text for block in draft.blocks if block.heading_level is not None and _norm(block.text) != _norm(target)]
    confirmed = [index for index in candidates if _followed_by(pages, index, snippet, headings)]
    outside_toc = [index for index in candidates if pages.blocks[index].page not in toc]
    for basis, chosen in (("본문 확인", confirmed), ("목차 제외 추정", outside_toc), ("목차에서만 발견", candidates)):
        if chosen:
            placement.update(found=True, page=pages.blocks[chosen[0]].page, page_basis=basis)
            return placement
    placement["found"] = bool(in_draft)
    return placement


def build_crosswalk(profile: RfpProfile, draft: SourceDocument, pdf: SourceDocument | None = None) -> dict[str, Any]:
    pages = pdf if pdf is not None else (draft if draft.has_pages else None)
    targets_by_item = [item.headings or [item.name] for item in profile.evaluation_items]
    toc = _toc_pages(pages, [t for targets in targets_by_item for t in targets]) if pages else set()
    rows = []
    for item, targets in zip(profile.evaluation_items, targets_by_item):
        placements = [_place(target, draft, pages, toc) for target in targets]
        found = sum(placement["found"] for placement in placements)
        rows.append({
            "item": item.name,
            "points": item.points,
            "kind": item.kind,
            "headings_declared": bool(item.headings),
            "placements": placements,
            "status": "mapped" if found == len(placements) else "partial" if found else "unmapped",
        })
    unmapped = [row["item"] for row in rows if row["status"] != "mapped"]
    unconfirmed = [
        placement["heading"] for row in rows for placement in row["placements"]
        if pages is not None and placement["found"] and placement["page_basis"] != "본문 확인"
    ]
    return {
        "draft": draft.path,
        "pdf": pdf.path if pdf is not None else None,
        "pages_available": pages is not None,
        "toc_pages": sorted(toc),
        "rows": rows,
        "unmapped": unmapped,
        "unconfirmed_pages": unconfirmed,
        "passed": bool(rows) and not unmapped,
        "note": "" if pages is not None else "쪽 번호는 --pdf로 제출할 PDF를 함께 주어야 채워진다.",
    }


def _points(value: float | None) -> str:
    if value is None:
        return "확인 필요"
    return str(int(value)) if float(value).is_integer() else str(value)


def _page_cell(placement: dict[str, Any]) -> str:
    if placement["page"] is None:
        return "확인 필요" if placement["found"] else "-"
    suffix = "" if placement["page_basis"] == "본문 확인" else " (확인 필요)"
    return f"{placement['page']}{suffix}"


def crosswalk_table_markdown(report: dict[str, Any]) -> str:
    """조견표 in Markdown."""
    lines = ["| 평가항목 | 배점 | 제안서 목차 | 쪽 |", "|---|---|---|---|"]
    for row in report["rows"]:
        headings = "<br>".join(p["heading"] if p["found"] else f"{p['heading']} (찾지 못함)" for p in row["placements"])
        pages = "<br>".join(_page_cell(p) for p in row["placements"])
        cells = [row["item"], _points(row["points"]), headings, pages]
        lines.append("| " + " | ".join(cell.replace("|", "\\|") for cell in cells) + " |")
    return "\n".join(lines) + "\n"
