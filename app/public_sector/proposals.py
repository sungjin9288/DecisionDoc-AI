"""Public proposal outline: a skeleton from the RFP's prescribed outline or its evaluation items.

A public proposal answers the RFP's evaluation items in the outline the RFP prescribes
(제안서 작성 요령), so a fixed bundle outline can leave an item without a section. The
skeleton follows the profile instead; requirements no section claims get their own chapter
so every requirement ID has a place to be answered.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.public_sector.models import PLACEHOLDER, RfpProfile
from app.public_sector.readers import SourceDocument
from app.public_sector.report_types import CONVENTION, Section
from app.public_sector.reports import _find_section, _finding, _heading_indexes, _heading_key
from app.public_sector.requirements import trace_requirements

PRESCRIBED_BASIS = "RFP 지정 목차"
REQUIREMENTS_CHAPTER = "요구사항별 대응 방안"


@dataclass(frozen=True)
class PlannedSection:
    title: str
    level: int
    evaluation_items: tuple[str, ...] = ()
    requirement_ids: tuple[str, ...] = ()
    guidance: str = ""
    prescribed: bool = False


def plan_outline(profile: RfpProfile) -> list[PlannedSection]:
    if profile.outline:
        planned = [
            PlannedSection(s.title, s.level, tuple(s.evaluation_items), tuple(s.requirement_ids), s.guidance, prescribed=True)
            for s in profile.outline
        ]
    else:
        planned = [PlannedSection(item.name, 1, (item.name,)) for item in profile.evaluation_items]
    claimed = {requirement_id for section in planned for requirement_id in section.requirement_ids}
    unclaimed = [requirement for requirement in profile.requirements if requirement.id not in claimed]
    if unclaimed:
        planned.append(PlannedSection(REQUIREMENTS_CHAPTER, 1))
        planned += [PlannedSection(requirement.name or requirement.id, 2, (), (requirement.id,)) for requirement in unclaimed]
    return planned


def headings_for_item(profile: RfpProfile, item_name: str) -> list[str]:
    """Outline titles that answer an evaluation item, used when the item names no headings."""
    return [section.title for section in plan_outline(profile) if item_name in section.evaluation_items]


def _instruction(section: PlannedSection, profile: RfpProfile) -> str:
    points = {item.name: item.points for item in profile.evaluation_items}
    parts = []
    if section.evaluation_items:
        items = [f"{name}({points[name]:g}점)" if points.get(name) is not None else name for name in section.evaluation_items]
        parts.append("평가항목: " + ", ".join(items))
    if section.requirement_ids:
        parts.append("대응 요구사항: " + ", ".join(section.requirement_ids) + "(본문에 고유번호를 적는다)")
    if section.guidance:
        parts.append(f"RFP 작성 요령: {section.guidance}")
    return f"{PLACEHOLDER} " + " · ".join(parts) if parts else PLACEHOLDER


def proposal_skeleton(profile: RfpProfile) -> str:
    lines = [f"# {profile.project.name} 제안서", ""]
    for section in plan_outline(profile):
        lines += ["#" * (section.level + 1) + f" {section.title}", "", _instruction(section, profile), ""]
    return "\n".join(lines)


def check_proposal(document: SourceDocument, profile: RfpProfile) -> dict[str, Any]:
    headings = _heading_indexes(document)
    findings = []
    for section in plan_outline(profile):
        basis = PRESCRIBED_BASIS if section.prescribed else CONVENTION
        # Compare without leading numbering on both sides ("Ⅱ. 기술 부문" matches "2. 기술 부문").
        if _find_section(document, Section(_heading_key(section.title), (), basis), headings) is None:
            severity = "error" if section.prescribed else "warning"
            findings.append(_finding(severity, "missing_section", f"'{section.title}' 목차가 없다", basis))
    findings += [
        _finding("error", "placeholder_left", f"작성하지 않은 자리 표시가 남아 있다: {block.text[:60]}")
        for block in document.blocks if PLACEHOLDER in block.text
    ]
    trace = trace_requirements(profile, document)
    findings += [_finding("error", "requirement_missing", f"요구사항 {requirement_id}에 대응한 본문이 없다") for requirement_id in trace["missing"]]
    findings += [_finding("warning", "unknown_requirement", f"RFP에 없는 번호 {item['id']}") for item in trace["unknown_ids"]]
    counts = {severity: sum(item["severity"] == severity for item in findings) for severity in ("error", "warning")}
    return {
        "document": document.path,
        "outline_source": PRESCRIBED_BASIS if profile.outline else "평가항목",
        "requirements": trace["summary"],
        "findings": findings,
        "counts": counts,
        "passed": counts["error"] == 0,
    }
