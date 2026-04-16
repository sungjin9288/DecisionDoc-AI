"""Normalize structured public-procurement PDFs into generation-friendly context."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

_ROMAN_OR_NUMBER_PREFIX = re.compile(
    r"^\s*(?:[0-9]+[.)]|[0-9]+(?:\.[0-9]+)+|[ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩ]+[.)]?|[IVXLC]+[.)]?|[가-힣A-Z][.)]|[①-⑳]|[■□●○▶▷◆◇])\s*"
)
_NOISE_HEADING = re.compile(r"^[\d\s./()_-]+$")
_TOC_OR_MENU = re.compile(r"^(?:contents?|ontents|contact)$", re.IGNORECASE)
_SENTENCE_LIKE_ENDING = re.compile(
    r"(?:합니다|하였다|합니다\.|하였다\.|입니다|입니다\.|됩니다|됩니다\.|"
    r"하여야|해야|따라|까지|제고|도출|제공|운영|포함되어야)$"
)
_STRUCTURE_KEYWORD = re.compile(
    r"(?:개요|배경|목적|범위|체계|일정|절차|근거|대상|기준|지표|계획|방향|전략|산출물|보고|인력|조직|거버넌스|시기|편람|평가)"
)
_SECTION_FOCUS_KEYWORD = re.compile(
    r"(?:개요|배경|목적|범위|체계|일정|절차|근거|대상|기준|지표|계획|방향|전략|산출물|보고|인력|조직|거버넌스|시기|편람)$"
)
_WHITESPACE = re.compile(r"\s+")

_DOC_KIND_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("착수보고 / 수행계획", ("착수보고", "착수 보고", "수행계획", "수행 계획", "추진계획")),
    ("제안요청 / 공고 분석", ("제안요청", "제안 요청", "입찰공고", "공고", "RFP", "rfp")),
    ("경영평가 / 평가 대응", ("경영평가", "평가계획", "평가 대응", "평가 개요")),
    ("제안서 / 사업계획", ("제안서", "사업계획", "사업 계획", "기술제안", "제안 개요")),
    ("중간 / 결과 보고", ("중간보고", "중간 보고", "완료보고", "완료 보고", "결과보고", "결과 보고")),
]

_SIGNAL_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("평가/심사", ("평가", "심사", "배점", "기준", "지표")),
    ("과업/요구사항", ("과업", "요구", "범위", "업무", "제안", "목표")),
    ("일정/마일스톤", ("일정", "로드맵", "마일스톤", "착수", "중간", "완료", "추진계획")),
    ("추진체계/인력", ("인력", "조직", "거버넌스", "보고", "운영체계", "수행체계")),
    ("산출물/보고", ("산출물", "보고서", "성과물", "납품", "결과물")),
]

_PPT_CANDIDATE_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("사업 개요/배경", ("개요", "배경", "목적", "필요성", "추진방향")),
    ("평가 대응 전략", ("평가", "심사", "배점", "지표", "전략")),
    ("수행 범위/요구사항", ("과업", "범위", "요구", "업무")),
    ("일정 및 마일스톤", ("일정", "로드맵", "마일스톤", "추진계획")),
    ("추진체계/거버넌스", ("조직", "인력", "거버넌스", "보고", "운영체계")),
    ("산출물/보고 체계", ("산출물", "보고서", "성과물", "납품")),
]

_PAGE_CLASS_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("개요/배경", ("개요", "배경", "목적", "필요성", "착수보고")),
    ("평가기준/지표", ("평가", "심사", "기준", "지표", "편람")),
    ("과업범위/요구사항", ("과업", "범위", "요구", "업무")),
    ("일정/마일스톤", ("일정", "로드맵", "마일스톤", "시기")),
    ("추진절차/방법", ("절차", "방법", "프로세스")),
    ("조직/거버넌스", ("조직", "인력", "거버넌스", "보고", "운영체계", "수행체계")),
    ("산출물/보고체계", ("산출물", "보고서", "성과물", "납품")),
]

_PAGE_DESIGN_HINTS: dict[str, tuple[str, str]] = {
    "개요/배경": ("문제-배경 카드", "좌측 문제 요약 / 우측 배경 근거 카드"),
    "평가기준/지표": ("평가기준 표", "상단 핵심 메시지 / 중앙 배점·평가표 / 하단 대응 포인트"),
    "표·평가표 중심": ("비교 표 + 강조 박스", "중앙 표 / 우측 또는 하단 핵심 시사점"),
    "표·도식 중심": ("도식 + 보조 표", "좌측 도식 / 우측 핵심 수치 또는 표"),
    "과업범위/요구사항": ("범위 분해 카드", "좌측 과업 범위 / 우측 요구사항·산출물"),
    "일정/마일스톤": ("타임라인", "가로 타임라인 / 하단 단계별 산출물"),
    "추진절차/방법": ("프로세스 흐름도", "좌측 단계 흐름 / 우측 단계별 역할"),
    "조직/거버넌스": ("거버넌스 조직도", "중앙 조직도 / 하단 보고 체계"),
    "산출물/보고체계": ("보고 체계 표", "상단 보고 일정 / 하단 산출물 표"),
    "일반 본문": ("요약 카드", "좌측 핵심 메시지 / 우측 보조 근거"),
}

_PAGE_CLASS_LINE_RE = re.compile(r"^(?P<page>\d+)p \[(?P<label>[^\]]+)\] (?P<detail>.+)$")
_PAGE_HINT_LINE_RE = re.compile(
    r"^(?P<page>\d+)p (?P<detail>.+?) \| 권장 시각자료: (?P<visual_type>.+?) \| 배치 가이드: (?P<layout_hint>.+)$"
)
_PPT_CANDIDATE_LINE_RE = re.compile(
    r"^(?P<candidate_label>.+?)\s+—\s+(?P<page>\d+)p \[(?P<label>[^\]]+)\] (?P<detail>.+)$"
)


def _normalize_text(text: str) -> str:
    text = _WHITESPACE.sub(" ", str(text or "")).strip()
    return text


def _clean_heading(text: str) -> str:
    cleaned = _normalize_text(text)
    cleaned = _ROMAN_OR_NUMBER_PREFIX.sub("", cleaned).strip(" -:")
    return cleaned


def _is_meaningful_heading(text: str) -> bool:
    if not text or len(text) < 2:
        return False
    if _NOISE_HEADING.fullmatch(text):
        return False
    if _TOC_OR_MENU.fullmatch(text):
        return False
    return True


def _score_heading(text: str, content: str) -> int:
    score = 0
    length = len(text)
    content_length = len(content)

    if not _is_meaningful_heading(text):
        return -10

    if 5 <= length <= 24:
        score += 3
    elif length <= 36:
        score += 1
    else:
        score -= 1

    if content_length >= 80:
        score += 3
    elif content_length >= 30:
        score += 2
    elif content_length > 0:
        score += 1
    else:
        score -= 2

    if _SENTENCE_LIKE_ENDING.search(text):
        score -= 3
    if text.startswith("「") or text.endswith("」"):
        score -= 2
    if re.search(r"\d{1,2}월\s*\d{1,2}일", text):
        score -= 3
    if not _STRUCTURE_KEYWORD.search(text):
        score -= 3
    if " " in text:
        score += 1
    return score


def _dedupe_preserve_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        key = item.casefold()
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def _collect_heading_candidates(structured: dict[str, Any]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for section in structured.get("sections", []) or []:
        if not isinstance(section, dict):
            continue
        heading = _clean_heading(section.get("heading", ""))
        content = _normalize_text(section.get("content", ""))
        score = _score_heading(heading, content)
        if score >= 1:
            candidates.append({"heading": heading, "content": content, "score": score})
    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = candidate["heading"].casefold()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(candidate)
    return deduped


def _collect_headings(structured: dict[str, Any]) -> list[str]:
    candidates = _collect_heading_candidates(structured)
    preferred = [
        candidate["heading"]
        for candidate in candidates
        if candidate["score"] >= 4 and _SECTION_FOCUS_KEYWORD.search(candidate["heading"])
    ]
    broad_preferred = [candidate["heading"] for candidate in candidates if candidate["score"] >= 4]
    fallback = [candidate["heading"] for candidate in candidates]
    return preferred or broad_preferred or fallback[:8]


def _infer_doc_kind(title: str, headings: list[str], raw_text: str) -> str:
    haystack = " ".join([title, *headings[:10], raw_text[:2000]]).lower()
    for label, keywords in _DOC_KIND_RULES:
        if any(keyword.lower() in haystack for keyword in keywords):
            return label
    return "공공 사업 문서"


def _collect_signal_lines(headings: list[str], sections: list[dict[str, Any]]) -> list[str]:
    lines: list[str] = []
    for label, keywords in _SIGNAL_RULES:
        matches: list[str] = []
        for heading in headings:
            if any(keyword in heading for keyword in keywords):
                matches.append(heading)
        if not matches:
            for section in sections[:20]:
                if not isinstance(section, dict):
                    continue
                content = _normalize_text(section.get("content", ""))
                if any(keyword in content for keyword in keywords):
                    preview = content.split(".")[0].split("다.")[0].strip()
                    if preview:
                        matches.append(preview[:60])
                if matches:
                    break
        if matches:
            lines.append(f"{label}: {', '.join(_dedupe_preserve_order(matches)[:3])}")
    return lines


def _collect_ppt_candidates(headings: list[str]) -> list[str]:
    candidates: list[str] = []
    for label, keywords in _PPT_CANDIDATE_RULES:
        for heading in headings:
            if any(keyword in heading for keyword in keywords):
                candidates.append(f"{label} — {heading}")
                break
    return _dedupe_preserve_order(candidates)


def _classify_page(page: dict[str, Any]) -> str:
    headings = " ".join(page.get("headings", []) or [])
    preview = _normalize_text(page.get("preview", ""))
    haystack = f"{headings} {preview}"
    if any(keyword in haystack for keyword in ("개요", "배경", "목적", "필요성", "착수보고")):
        return "개요/배경"
    if any(keyword in haystack for keyword in ("평가", "심사", "기준", "지표", "편람")):
        return "평가기준/지표"
    if page.get("has_tables"):
        if any(keyword in haystack for keyword in ("대상", "기관", "범위", "현황", "비교")):
            return "표·평가표 중심"
        return "표·도식 중심"
    for label, keywords in _PAGE_CLASS_RULES:
        if any(keyword in haystack for keyword in keywords):
            return label
    return "일반 본문"


def _collect_page_classification_lines(structured: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    for page in structured.get("pages", []) or []:
        if not isinstance(page, dict):
            continue
        page_no = page.get("page")
        headings = [
            cleaned
            for item in page.get("headings", []) or []
            if (cleaned := _clean_heading(item)) and _is_meaningful_heading(cleaned)
        ]
        heading = headings[0] if headings else ""
        label = _classify_page(page)
        preview = _normalize_text(page.get("preview", ""))
        if not heading and ("ontents" in preview.casefold() or "contact" in preview.casefold()):
            continue
        detail = heading or preview[:36]
        if not detail:
            continue
        lines.append(f"{page_no}p [{label}] {detail}")
    return _dedupe_preserve_order(lines)


def _collect_ppt_candidates_from_pages(structured: dict[str, Any]) -> list[str]:
    candidates: list[str] = []
    seen_labels: set[str] = set()
    page_lines = _collect_page_classification_lines(structured)
    for page_line in page_lines:
        if "[일정/마일스톤]" in page_line:
            label = "일정 및 마일스톤"
        elif "[조직/거버넌스]" in page_line:
            label = "추진체계/거버넌스"
        elif "[평가기준/지표]" in page_line or "[표·평가표 중심]" in page_line:
            label = "평가 대응 전략"
        elif "[과업범위/요구사항]" in page_line:
            label = "수행 범위/요구사항"
        elif "[개요/배경]" in page_line:
            label = "사업 개요/배경"
        else:
            continue
        if label in seen_labels:
            continue
        seen_labels.add(label)
        candidates.append(f"{label} — {page_line}")
    return _dedupe_preserve_order(candidates)


def _collect_page_design_hints(structured: dict[str, Any]) -> list[str]:
    hints: list[str] = []
    for page_line in _collect_page_classification_lines(structured):
        match = re.match(r"(?P<page>\d+p) \[(?P<label>[^\]]+)\] (?P<detail>.+)", page_line)
        if not match:
            continue
        label = match.group("label")
        detail = match.group("detail")
        visual_type, layout_hint = _PAGE_DESIGN_HINTS.get(
            label,
            ("요약 카드", "좌측 핵심 메시지 / 우측 보조 근거"),
        )
        hints.append(
            f"{match.group('page')} {detail} | 권장 시각자료: {visual_type} | 배치 가이드: {layout_hint}"
        )
    return _dedupe_preserve_order(hints)


def _collect_review_notes(sections: list[dict[str, Any]]) -> list[str]:
    notes: list[str] = []
    for section in sections[:12]:
        if not isinstance(section, dict):
            continue
        heading = _clean_heading(section.get("heading", ""))
        content = _normalize_text(section.get("content", ""))
        if not content:
            continue
        if heading and _score_heading(heading, content) < 4:
            heading = ""
        preview = content.split(".")[0].split("다.")[0].strip()
        if not preview:
            preview = content[:80]
        note = f"{heading}: {preview[:90]}" if heading else preview[:90]
        notes.append(note)
        if len(notes) >= 4:
            break
    return notes


def parse_procurement_pdf_context(context: str) -> dict[str, list[dict[str, Any]]]:
    """Parse the normalized procurement context block back into structured hints.

    This is used by post-generation repair so the bundle output can be aligned with
    the procurement page classifier and PPT design hints that were injected into the prompt.
    """
    if not isinstance(context, str) or not context.strip():
        return {
            "page_classifications": [],
            "page_design_hints": [],
            "ppt_candidates": [],
        }

    page_classifications: list[dict[str, Any]] = []
    page_design_hints: list[dict[str, Any]] = []
    ppt_candidates: list[dict[str, Any]] = []
    page_class_map: dict[int, dict[str, Any]] = {}

    for raw_line in context.splitlines():
        line = raw_line.strip()
        if line.startswith("- "):
            line = line[2:].strip()
        if not line:
            continue

        class_match = _PAGE_CLASS_LINE_RE.match(line)
        if class_match:
            item = {
                "page": int(class_match.group("page")),
                "label": class_match.group("label").strip(),
                "detail": class_match.group("detail").strip(),
            }
            page_classifications.append(item)
            page_class_map[item["page"]] = item
            continue

        hint_match = _PAGE_HINT_LINE_RE.match(line)
        if hint_match:
            page = int(hint_match.group("page"))
            page_hint = {
                "page": page,
                "detail": hint_match.group("detail").strip(),
                "visual_type": hint_match.group("visual_type").strip(),
                "layout_hint": hint_match.group("layout_hint").strip(),
            }
            class_info = page_class_map.get(page, {})
            if class_info:
                page_hint["label"] = class_info.get("label", "")
            page_design_hints.append(page_hint)
            continue

        candidate_match = _PPT_CANDIDATE_LINE_RE.match(line)
        if candidate_match:
            ppt_candidates.append({
                "candidate_label": candidate_match.group("candidate_label").strip(),
                "page": int(candidate_match.group("page")),
                "label": candidate_match.group("label").strip(),
                "detail": candidate_match.group("detail").strip(),
            })

    # Backfill classification labels into design hints when the section order changes.
    if page_design_hints and page_class_map:
        for hint in page_design_hints:
            if not hint.get("label") and hint["page"] in page_class_map:
                hint["label"] = page_class_map[hint["page"]]["label"]

    return {
        "page_classifications": page_classifications,
        "page_design_hints": page_design_hints,
        "ppt_candidates": ppt_candidates,
    }


def build_procurement_pdf_context(
    structured: dict[str, Any],
    filename: str,
    *,
    max_chars: int = 3_500,
) -> str:
    """Build a concise procurement-oriented summary block from structured PDF data."""
    if not isinstance(structured, dict):
        return ""

    title = _normalize_text(structured.get("title", "")) or Path(filename).stem
    sections = structured.get("sections", []) or []
    headings = _collect_headings(structured)
    doc_kind = _infer_doc_kind(title, headings, _normalize_text(structured.get("raw_text", "")))
    page_count = int(structured.get("page_count") or 0)
    has_tables = bool(structured.get("has_tables"))
    signal_lines = _collect_signal_lines(headings, sections)
    page_classification_lines = _collect_page_classification_lines(structured)
    page_design_hints = _collect_page_design_hints(structured)
    ppt_candidates = _collect_ppt_candidates_from_pages(structured) or _collect_ppt_candidates(headings)
    review_notes = _collect_review_notes(sections)

    lines: list[str] = [
        "=== 공공조달 PDF 정규화 요약 ===",
        f"문서명: {title}",
        f"추정 문서 유형: {doc_kind}",
        f"페이지 수: {page_count}",
        f"표 포함: {'예' if has_tables else '아니오'}",
        "",
        "핵심 섹션:",
    ]
    if headings:
        lines.extend(f"- {heading}" for heading in headings[:8])
    else:
        lines.append("- 명확한 섹션 제목을 추출하지 못했습니다.")

    lines.extend(["", "주요 조달 신호:"])
    if signal_lines:
        lines.extend(f"- {line}" for line in signal_lines[:6])
    else:
        lines.append("- 평가/과업/일정/조직 관련 신호를 명시적으로 추출하지 못했습니다.")

    lines.extend(["", "페이지 분류:"])
    if page_classification_lines:
        lines.extend(f"- {line}" for line in page_classification_lines[:8])
    else:
        lines.append("- 페이지 단위 분류 정보를 구성하지 못했습니다.")

    lines.extend(["", "PPT 페이지 설계 힌트:"])
    if page_design_hints:
        lines.extend(f"- {line}" for line in page_design_hints[:6])
    else:
        lines.append("- 페이지별 시각자료/배치 가이드를 구성하지 못했습니다.")

    lines.extend(["", "발표/PPT 후보 페이지:"])
    if ppt_candidates:
        lines.extend(f"- {line}" for line in ppt_candidates[:6])
    else:
        lines.append("- 섹션 제목 기반 PPT 후보 페이지를 구성하지 못했습니다.")

    lines.extend(["", "검토 메모:"])
    if review_notes:
        lines.extend(f"- {line}" for line in review_notes)
    else:
        lines.append("- 본문 요약을 생성하지 못했습니다.")
    lines.append("=== 공공조달 PDF 정규화 요약 끝 ===")

    context = "\n".join(lines).strip()
    if len(context) > max_chars:
        context = context[: max_chars - 16].rstrip() + "\n...(이하 생략)"
    return context
