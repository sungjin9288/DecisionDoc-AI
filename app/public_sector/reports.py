"""Stage reports: section check, fulfilment table check and a skeleton to write into."""
from __future__ import annotations

import re
from typing import Any

from app.public_sector.models import PLACEHOLDER, Obligation, RfpProfile
from app.public_sector.readers import SourceDocument
from app.public_sector.report_types import STATUS_PENDING, ReportType, Section, obligation_sources

_NUMBERING_RE = re.compile(
    r"^(?:붙임\s*\d*\.?|제\s*\d+\s*[장절]|[ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩⅪⅫ]+\.?|\d+(?:[.-]\d+)*[.)]?|[가-하][.)]"
    r"|\(\d+\)|\([가-하]\)|[①-⑳□○■●◦▪·-])\s*"
)
_OBLIGATION_LABEL = {"tasks": "과업", "commitments": "제안 약속"}


def _heading_key(text: str) -> str:
    return re.sub(r"\s+", "", _NUMBERING_RE.sub("", text.strip(), count=1))


def _heading_indexes(document: SourceDocument) -> list[int]:
    indexes = [index for index, block in enumerate(document.blocks) if block.heading_level is not None]
    # Without heading styles (e.g. PDF) any short line may be a heading.
    return indexes or [index for index, block in enumerate(document.blocks) if len(block.text) <= 40]


def _find_section(document: SourceDocument, section: Section, heading_indexes: list[int]) -> int | None:
    keys = [re.sub(r"\s+", "", name) for name in section.names]
    for index in heading_indexes:
        key = _heading_key(document.blocks[index].text)
        if any(key.startswith(name) for name in keys):
            return index
    return None


def _section_text(document: SourceDocument, start: int) -> str:
    level = document.blocks[start].heading_level
    parts = []
    for block in document.blocks[start + 1:]:
        if block.heading_level is not None and (level is None or block.heading_level <= level):
            break
        parts.append(block.text)
    return "".join(parts)


def _finding(severity: str, code: str, message: str, basis: str = "") -> dict[str, str]:
    return {"severity": severity, "code": code, "message": message, "basis": basis}


def _section_findings(document: SourceDocument, report: ReportType) -> tuple[list[dict[str, str]], dict[str, int]]:
    headings = _heading_indexes(document)
    found: dict[str, int] = {}
    findings = []
    for section in report.sections:
        index = _find_section(document, section, headings)
        if index is None:
            severity = "error" if section.official else "warning"
            findings.append(_finding(severity, "missing_section", f"'{section.title}' 섹션이 없다", section.basis))
        else:
            found[section.title] = index
    for rule in report.length_rules:
        if rule.section not in found:
            continue
        length = len(re.sub(r"\s+", "", _section_text(document, found[rule.section])))
        low, high = rule.target_chars * (1 - rule.tolerance), rule.target_chars * (1 + rule.tolerance)
        if not low <= length <= high:
            findings.append(_finding("warning", "section_length", f"'{rule.section}' 분량 {length}자(공백 제외)가 {rule.target_chars}자 내외를 벗어난다", rule.basis))
    return findings, found


def _table_rows(document: SourceDocument) -> list[list[str]]:
    rows = []
    for block in document.blocks:
        if "|" in block.text:
            cells = [cell.strip() for cell in block.text.strip().strip("|").split("|")]
            rows.append([re.sub(r"\s+", " ", cell) for cell in cells])
    return rows


def _obligations(profile: RfpProfile, report: ReportType) -> list[tuple[str, Obligation]]:
    return [(source, item) for source in obligation_sources(report) for item in getattr(profile, source)]


def _fulfilment_findings(document: SourceDocument, report: ReportType, profile: RfpProfile | None) -> tuple[list[dict[str, str]], list[dict[str, Any]]]:
    if profile is None or not report.statuses:
        return [], []
    rows = _table_rows(document)
    allowed = (*report.statuses, STATUS_PENDING)
    findings, results, seen = [], [], set()
    for source, obligation in _obligations(profile, report):
        label = f"{_OBLIGATION_LABEL[source]} {obligation.id}"
        if obligation.id in seen:
            findings.append(_finding("error", "duplicate_obligation", f"{label} 번호가 중복된다"))
            continue
        seen.add(obligation.id)
        row = next((cells for cells in rows if obligation.id in cells), None)
        status = next((cell for cell in row if cell in allowed), None) if row else None
        results.append({"source": source, "id": obligation.id, "name": obligation.name, "in_table": row is not None, "status": status})
        if row is None:
            findings.append(_finding("error", "obligation_missing", f"{label}이(가) 이행 대비표에 없다"))
        elif status is None:
            findings.append(_finding("error", "status_invalid", f"{label}의 상태가 없거나 허용 값({', '.join(report.statuses)})이 아니다"))
        elif status == STATUS_PENDING:
            findings.append(_finding("warning", "status_pending", f"{label}의 상태가 '{STATUS_PENDING}'로 남아 있다"))
    return findings, results


def check_report(document: SourceDocument, report: ReportType, profile: RfpProfile | None = None) -> dict[str, Any]:
    section_findings, found = _section_findings(document, report)
    fulfilment_findings, fulfilment = _fulfilment_findings(document, report, profile)
    placeholder = [
        _finding("error", "placeholder_left", f"작성하지 않은 자리 표시 '{PLACEHOLDER}'가 남아 있다: {block.text[:60]}")
        for block in document.blocks if PLACEHOLDER in block.text
    ]
    findings = section_findings + fulfilment_findings + placeholder
    counts = {severity: sum(item["severity"] == severity for item in findings) for severity in ("error", "warning")}
    return {
        "document": document.path,
        "report_type": report.id,
        "sections_found": sorted(found),
        "fulfilment": fulfilment,
        "findings": findings,
        "counts": counts,
        "passed": counts["error"] == 0,
        "note": report.note,
    }


def report_skeleton(report: ReportType, profile: RfpProfile | None = None) -> str:
    """A Markdown outline with every section and, when needed, the fulfilment table."""
    title = profile.project.name if profile else ""
    lines = [f"# {report.name}" + (f": {title}" if title else ""), ""]
    for number, section in enumerate(report.sections, start=1):
        lines += [f"## {number}. {section.title}", "", PLACEHOLDER, ""]
    if report.statuses and profile is not None and _obligations(profile, report):
        lines += [
            "## 붙임. 과업 이행 대비표", "",
            f"{PLACEHOLDER} 상태는 {', '.join(report.statuses)} 중 하나로 바꾸고 이 문장은 지운다.", "",
            "| 구분 | 번호 | 항목 | 출처 | 상태 | 비고 |", "|---|---|---|---|---|---|",
        ]
        for source, item in _obligations(profile, report):
            cells = [_OBLIGATION_LABEL[source], item.id, item.name or STATUS_PENDING, item.source or "-", STATUS_PENDING, ""]
            lines.append("| " + " | ".join(cell.replace("|", "\\|") for cell in cells) + " |")
        lines.append("")
    return "\n".join(lines)
