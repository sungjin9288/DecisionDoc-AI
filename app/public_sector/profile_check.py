"""Check an RFP condition profile before using it, and list what is still unknown."""
from __future__ import annotations

from typing import Any

from app.public_sector.models import RfpProfile
from app.public_sector.requirements import OFFICIAL_CATEGORIES, parse_requirement_id

_POINT_TOLERANCE = 0.01


def _finding(severity: str, code: str, message: str, target: str = "") -> dict[str, str]:
    return {"severity": severity, "code": code, "message": message, "target": target}


def _requirement_findings(profile: RfpProfile) -> list[dict[str, str]]:
    findings = []
    seen = set()
    for requirement in profile.requirements:
        key = parse_requirement_id(requirement.id)
        if key is None:
            findings.append(_finding("error", "unparsed_id", "고유번호 형식을 해석할 수 없다", requirement.id))
        elif key in seen:
            findings.append(_finding("error", "duplicate_id", "같은 고유번호가 두 번 이상 있다", requirement.id))
        seen.add(key)
        if requirement.category and requirement.category not in OFFICIAL_CATEGORIES:
            findings.append(_finding("warning", "unofficial_category", "고시의 요구사항 분류 11종에 없는 분류다", requirement.id))
        if not requirement.name:
            findings.append(_finding("info", "missing_name", "요구사항 명칭 확인 필요", requirement.id))
    if not profile.requirements:
        findings.append(_finding("info", "no_requirements", "요구사항 목록이 비어 있다. RFP에 고유번호가 없는지 확인 필요"))
    return findings


def _evaluation_findings(profile: RfpProfile) -> list[dict[str, str]]:
    findings = []
    items = profile.evaluation_items
    if not items:
        return [_finding("info", "no_evaluation_items", "평가항목 확인 필요")]
    for item in items:
        if item.points is None:
            findings.append(_finding("info", "missing_points", "배점 확인 필요", item.name))
        if not item.headings:
            findings.append(_finding("info", "no_headings", "이 평가항목에 답하는 제안서 목차를 정하지 않았다", item.name))
    technical = profile.scoring.technical
    points = [item.points for item in items]
    if technical is not None and None not in points and abs(sum(points) - technical) > _POINT_TOLERANCE:
        findings.append(_finding("warning", "points_mismatch", f"평가항목 배점 합계 {sum(points):g}점이 기술 배점 {technical:g}점과 다르다"))
    return findings


def _unknown_conditions(profile: RfpProfile) -> list[dict[str, str]]:
    submission, scoring = profile.submission, profile.scoring
    unknown = {
        "제출 형식": not submission.formats,
        "전체 용량 한도": submission.max_total_mb is None,
        "본문 쪽수 제한": submission.page_limit is None,
        "블라인드 평가 여부": submission.blind_evaluation is None,
        "기술·가격 배점": scoring.technical is None or scoring.price is None,
        "협상적격 기준": scoring.pass_ratio is None,
    }
    return [_finding("info", "unknown_condition", f"{label} 확인 필요", label) for label, missing in unknown.items() if missing]


def check_profile(profile: RfpProfile) -> dict[str, Any]:
    findings = _requirement_findings(profile) + _evaluation_findings(profile) + _unknown_conditions(profile)
    counts = {severity: sum(item["severity"] == severity for item in findings) for severity in ("error", "warning", "info")}
    return {"findings": findings, "counts": counts, "passed": counts["error"] == 0}
