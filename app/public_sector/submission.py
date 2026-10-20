"""Submission package check: the files to submit against the RFP's stated conditions.

Conditions come from the RFP profile. PPS-run evaluations require PDF, at most 300MB in
total and separate quantitative, qualitative and cost-saving files (조달청 협상에 의한 계약
제안서평가 세부기준 제6조의2); other conditions, including blind evaluation, are whatever
the RFP states. A condition the profile leaves unknown is reported, never assumed met.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from app.public_sector.models import RfpProfile
from app.public_sector.readers import (
    SUPPORTED_SUFFIXES,
    ReaderError,
    metadata_text,
    pdf_page_count,
    read_document,
)

_MB = 1024 * 1024
_SUMMARY_MARKERS = ("요약",)


def _finding(severity: str, code: str, message: str, target: str = "") -> dict[str, str]:
    return {"severity": severity, "code": code, "message": message, "target": target}


def _norm(text: str) -> str:
    return re.sub(r"\s+", "", text).lower()


def collect_files(paths: list[str | Path]) -> list[Path]:
    files: list[Path] = []
    for item in map(Path, paths):
        if item.is_dir():
            files += sorted(path for path in item.iterdir() if path.is_file() and not path.name.startswith("."))
        elif item.is_file():
            files.append(item)
        else:
            raise ReaderError(f"파일이 없습니다: {item}")
    return files


def _format_findings(profile: RfpProfile, files: list[Path]) -> list[dict[str, str]]:
    rules = profile.submission
    findings = []
    allowed = {fmt.lower().lstrip(".") for fmt in rules.formats}
    if not allowed:
        findings.append(_finding("info", "unknown_condition", "제출 형식 확인 필요"))
    for path in files:
        if allowed and path.suffix.lower().lstrip(".") not in allowed:
            findings.append(_finding("error", "format_not_allowed", f"허용 형식({', '.join(sorted(allowed))})이 아니다", path.name))
    total = sum(path.stat().st_size for path in files)
    if rules.max_total_mb is None:
        findings.append(_finding("info", "unknown_condition", "전체 용량 한도 확인 필요"))
    elif total > rules.max_total_mb * _MB:
        findings.append(_finding("error", "over_size", f"전체 {total / _MB:.1f}MB가 한도 {rules.max_total_mb:g}MB를 넘는다"))
    for label in rules.separate_files:
        if not any(_norm(label) in _norm(path.stem) for path in files):
            findings.append(_finding("warning", "separate_file_not_found", f"'{label}' 파일을 파일 이름에서 찾지 못했다. 별도 파일로 냈는지 확인한다", label))
    return findings


def _page_findings(profile: RfpProfile, files: list[Path]) -> tuple[list[dict[str, str]], dict[str, int]]:
    rules = profile.submission
    findings, pages = [], {}
    for path in files:
        if path.suffix.lower() == ".pdf":
            pages[path.name] = pdf_page_count(path.read_bytes())
    for name, count in pages.items():
        is_summary = any(marker in name for marker in _SUMMARY_MARKERS)
        limit = rules.summary_page_limit if is_summary else rules.page_limit
        if limit is not None and count > limit:
            kind = "요약본" if is_summary else "본문"
            findings.append(_finding("warning", "over_page_limit", f"{kind} {count}쪽이 제한 {limit}쪽을 넘는다. 표지·목차 포함 여부는 RFP 기준으로 확인한다", name))
    if rules.page_limit is None:
        findings.append(_finding("info", "unknown_condition", "본문 쪽수 제한 확인 필요"))
    return findings, pages


def _blind_findings(profile: RfpProfile, files: list[Path], identifiers: list[str]) -> list[dict[str, str]]:
    blind = profile.submission.blind_evaluation
    if blind is None:
        return [_finding("info", "unknown_condition", "블라인드 평가 여부 확인 필요")]
    if not blind:
        return []
    names = [value for value in (item.strip() for item in identifiers) if value]
    if not names:
        return [_finding("error", "identifiers_missing", "블라인드 평가인데 검사할 회사 식별 정보(회사명, 약칭, 대표자 등)가 주어지지 않았다")]
    findings = []
    for path in files:
        texts = {"메타데이터": metadata_text(path), "파일 이름": path.name}
        if path.suffix.lower() in SUPPORTED_SUFFIXES:
            texts["본문"] = read_document(path).full_text()
        for place, text in texts.items():
            for name in names:
                if _norm(name) in _norm(text):
                    findings.append(_finding("error", "identifier_exposed", f"{place}에 '{name}'이(가) 있다", path.name))
    return findings


def check_submission(profile: RfpProfile, paths: list[str | Path], identifiers: list[str] | None = None) -> dict[str, Any]:
    files = collect_files(paths)
    if not files:
        raise ReaderError("검사할 제출 파일이 없습니다")
    page_findings, pages = _page_findings(profile, files)
    findings = _format_findings(profile, files) + page_findings + _blind_findings(profile, files, identifiers or [])
    counts = {severity: sum(item["severity"] == severity for item in findings) for severity in ("error", "warning", "info")}
    return {
        "files": [{"name": path.name, "bytes": path.stat().st_size, "pages": pages.get(path.name)} for path in files],
        "total_mb": round(sum(path.stat().st_size for path in files) / _MB, 2),
        "findings": findings,
        "counts": counts,
        "passed": counts["error"] == 0,
        "note": "검사 통과는 제출·접수·평가 결과를 뜻하지 않는다.",
    }
