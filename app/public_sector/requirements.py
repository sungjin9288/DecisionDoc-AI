"""Requirement IDs: scan an RFP for candidates and trace a draft against the profile."""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from typing import Any

from app.public_sector.models import PLACEHOLDER, RfpProfile
from app.public_sector.readers import SourceDocument

# 과학기술정보통신부 고시 제2023-15호 「소프트웨어사업 계약 및 관리감독에 관한 지침」 별표2.
OFFICIAL_CATEGORIES = (
    "시스템 장비 구성", "기능", "성능", "인터페이스", "데이터", "테스트",
    "보안", "품질", "제약사항", "프로젝트 관리", "프로젝트 지원",
)
# Three-letter prefixes are common practice but were not found in the official notice;
# they only suggest a category and every RFP is read for its own prefixes.
CONVENTIONAL_PREFIXES = {
    "ECR": "시스템 장비 구성", "SFR": "기능", "PER": "성능", "SIR": "인터페이스",
    "DAR": "데이터", "TER": "테스트", "SER": "보안", "QUR": "품질",
    "COR": "제약사항", "PMR": "프로젝트 관리", "PSR": "프로젝트 지원",
}
_ASCII_ID_RE = re.compile(r"(?<![A-Za-z0-9])([A-Z]{2,5})\s?-\s?(\d{1,4})(?!\d)")
_KOREAN_ID_RE = re.compile(
    r"(시스템\s*장비\s*구성|기능|성능|인터페이스|데이터|테스트|보안|품질|제약\s*사항|프로젝트\s*관리|프로젝트\s*지원)"
    r"\s*요구\s*사항\s*-\s*(\d{1,4})(?!\d)"
)
_NAME_TRIM = " \t|:-·•ㆍ,/"
# Table rows flattened to text read "번호: SFR-001 / 요구사항 명칭: 통합 검색 / 우선순위: 상".
_CELL_LABEL_RE = re.compile(r"^[^:：/|]{1,15}[:：]\s*")
_NEXT_CELL_RE = re.compile(r"\s+[/|]\s+")
_NAME_MAX = 80
_MIN_MENTIONS_FOR_UNKNOWN_PREFIX = 2
_LOCATIONS_SHOWN = 3


@dataclass(frozen=True, order=True)
class RequirementKey:
    """An ID compared by prefix and number, so ``SFR-1`` and ``SFR-001`` are the same."""

    prefix: str
    number: int


@dataclass(frozen=True)
class IdMatch:
    key: RequirementKey
    text: str
    end: int


def find_ids(text: str) -> list[IdMatch]:
    matches = [
        IdMatch(RequirementKey(m.group(1), int(m.group(2))), m.group(0), m.end())
        for m in _ASCII_ID_RE.finditer(text)
    ]
    matches += [
        IdMatch(RequirementKey(re.sub(r"\s+", "", m.group(1)) + "요구사항", int(m.group(2))), m.group(0), m.end())
        for m in _KOREAN_ID_RE.finditer(text)
    ]
    return sorted(matches, key=lambda match: match.end)


def parse_requirement_id(value: str) -> RequirementKey | None:
    found = find_ids(value.strip())
    return found[0].key if len(found) == 1 and found[0].text == value.strip() else None


def _location(document: SourceDocument, paths: list[str], index: int) -> dict[str, Any]:
    block = document.blocks[index]
    return {"heading_path": paths[index], "page": block.page, "excerpt": block.text[:120]}


def _clean_name(text: str) -> str:
    name = _CELL_LABEL_RE.sub("", text.strip(_NAME_TRIM), count=1)
    return _NEXT_CELL_RE.split(name, maxsplit=1)[0].strip(_NAME_TRIM)


def _name_candidate(document: SourceDocument, index: int, match: IdMatch) -> str:
    rest = _clean_name(document.blocks[index].text[match.end:])
    if not rest and index + 1 < len(document.blocks):
        following = document.blocks[index + 1].text
        rest = "" if find_ids(following) else _clean_name(following)
    return rest[:_NAME_MAX]


def scan_requirements(document: SourceDocument, prefixes: list[str] | None = None) -> dict[str, Any]:
    """List requirement ID candidates for the session to confirm; nothing here is final."""
    wanted = {prefix.upper() for prefix in prefixes or []}
    paths = document.heading_paths()
    mentions: Counter[str] = Counter()
    first_seen: dict[RequirementKey, dict[str, Any]] = {}
    for index, block in enumerate(document.blocks):
        for match in find_ids(block.text):
            mentions[match.key.prefix] += 1
            if match.key not in first_seen:
                first_seen[match.key] = {
                    "id": match.text.replace(" ", ""),
                    "name_candidate": _name_candidate(document, index, match),
                    **_location(document, paths, index),
                }

    def keep(key: RequirementKey) -> bool:
        if wanted:
            return key.prefix in wanted
        # Unlisted prefixes (e.g. ISO-9001) count only when the RFP repeats them.
        return (
            key.prefix in CONVENTIONAL_PREFIXES
            or key.prefix.endswith("요구사항")
            or mentions[key.prefix] >= _MIN_MENTIONS_FOR_UNKNOWN_PREFIX
        )

    kept = [key for key in sorted(first_seen) if keep(key)]
    return {
        "prefix_mentions": dict(sorted(mentions.items())),
        "candidates": [
            {**first_seen[key], "category_guess": CONVENTIONAL_PREFIXES.get(key.prefix, key.prefix.removesuffix("요구사항"))}
            for key in kept
        ],
        "note": "후보 목록이다. RFP 원문과 대조해 확정한 뒤 RFP 조건 카드의 requirements에 옮긴다.",
    }


def _profile_keys(profile: RfpProfile) -> tuple[dict[RequirementKey, int], list[dict[str, str]]]:
    keys: dict[RequirementKey, int] = {}
    issues: list[dict[str, str]] = []
    for position, requirement in enumerate(profile.requirements):
        key = parse_requirement_id(requirement.id)
        if key is None:
            issues.append({"code": "unparsed_id", "id": requirement.id, "message": "고유번호 형식을 해석할 수 없습니다"})
        elif key in keys:
            issues.append({"code": "duplicate_id", "id": requirement.id, "message": "같은 고유번호가 두 번 이상 있습니다"})
        else:
            keys[key] = position
    return keys, issues


def trace_requirements(profile: RfpProfile, draft: SourceDocument) -> dict[str, Any]:
    """Where each profile requirement appears in the draft, plus IDs the RFP does not have."""
    keys, issues = _profile_keys(profile)
    prefixes = {key.prefix for key in keys}
    paths = draft.heading_paths()
    found: dict[RequirementKey, list[dict[str, Any]]] = {key: [] for key in keys}
    unknown: dict[str, list[dict[str, Any]]] = {}
    for index, block in enumerate(draft.blocks):
        if PLACEHOLDER in block.text:
            continue  # an unwritten outline line naming the IDs to answer is not an answer
        for match in find_ids(block.text):
            if match.key in found:
                found[match.key].append(_location(draft, paths, index))
            elif match.key.prefix in prefixes:
                unknown.setdefault(match.text.replace(" ", ""), []).append(_location(draft, paths, index))
    rows = []
    for key, position in keys.items():
        requirement = profile.requirements[position]
        locations = found[key]
        rows.append({
            "id": requirement.id,
            "category": requirement.category,
            "name": requirement.name,
            "status": "covered" if locations else "missing",
            "locations": locations[:_LOCATIONS_SHOWN],
            "mentions": len(locations),
        })
    missing = [row["id"] for row in rows if row["status"] == "missing"]
    return {
        "draft": draft.path,
        "summary": {"requirements": len(rows), "covered": len(rows) - len(missing), "missing": len(missing), "unknown_ids": len(unknown)},
        "missing": missing,
        "unknown_ids": [{"id": key, "locations": value[:_LOCATIONS_SHOWN]} for key, value in sorted(unknown.items())],
        "profile_issues": issues,
        "rows": rows,
        "passed": not missing and not unknown and not issues,
    }


_PATH_SEPARATOR = " > "


def _shared_root(report: dict[str, Any]) -> str:
    """The document title every location starts under, if there is exactly one."""
    roots = {
        location["heading_path"].split(_PATH_SEPARATOR)[0]
        for row in report["rows"] for location in row["locations"]
        if _PATH_SEPARATOR in location["heading_path"]
    }
    return roots.pop() if len(roots) == 1 else ""


def _where(location: dict[str, Any], root: str) -> str:
    path = location["heading_path"]
    if root and path.startswith(root + _PATH_SEPARATOR):
        path = path[len(root) + len(_PATH_SEPARATOR):]
    parts = [path or "(제목 없음)"]
    if location["page"] is not None:
        parts.append(f"p.{location['page']}")
    return " / ".join(parts)


def trace_table_markdown(report: dict[str, Any]) -> str:
    """요구사항 대비표 in Markdown; a title shared by every location is left out."""
    root = _shared_root(report)
    lines = ["| 고유번호 | 분류 | 요구사항 명칭 | 제안서 대응 위치 | 상태 |", "|---|---|---|---|---|"]
    for row in report["rows"]:
        where = "<br>".join(_where(location, root) for location in row["locations"]) or "-"
        status = "대응" if row["status"] == "covered" else "누락"
        cells = [row["id"], row["category"] or "확인 필요", row["name"] or "확인 필요", where, status]
        lines.append("| " + " | ".join(cell.replace("|", "\\|") for cell in cells) + " |")
    return "\n".join(lines) + "\n"
