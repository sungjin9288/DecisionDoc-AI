"""Procurement (parsed RFP PDF) slide-outline guidance.

Merges page-level design hints extracted from a normalized procurement PDF
context into a bundle's ``slide_outline`` fields, either by aligning
existing slides to the best-matching hint or synthesizing new slides when
none exist.
"""
from __future__ import annotations

import re
from typing import Any

from app.services.procurement_pdf_normalizer import parse_procurement_pdf_context


def _procurement_text_key(text: Any) -> str:
    return re.sub(r"\s+", "", str(text or "")).casefold()


def _extract_procurement_context_from_text(text: Any) -> str:
    raw = str(text or "")
    start = raw.find("=== 공공조달 PDF 정규화 요약 ===")
    end = raw.find("=== 공공조달 PDF 정규화 요약 끝 ===")
    if start == -1 or end == -1 or end < start:
        return ""
    end += len("=== 공공조달 PDF 정규화 요약 끝 ===")
    return raw[start:end].strip()


def _procurement_overlap_score(slide: dict[str, Any], hint: dict[str, Any]) -> int:
    haystack = " ".join(
        [
            str(slide.get("title", "") or ""),
            str(slide.get("core_message", "") or ""),
            str(slide.get("key_content", "") or ""),
            " ".join(str(item) for item in slide.get("evidence_points", []) or []),
        ]
    )
    haystack_key = _procurement_text_key(haystack)
    detail_key = _procurement_text_key(hint.get("detail", ""))
    label_key = _procurement_text_key(hint.get("label", ""))
    candidate_key = _procurement_text_key(hint.get("candidate_label", ""))
    score = 0
    if detail_key and detail_key in haystack_key:
        score += 8
    elif detail_key:
        detail_tokens = [token for token in re.findall(r"[가-힣A-Za-z0-9]+", str(hint.get("detail", ""))) if len(token) >= 2]
        score += sum(2 for token in detail_tokens if _procurement_text_key(token) in haystack_key)
    if label_key and label_key in haystack_key:
        score += 4
    if candidate_key and candidate_key in haystack_key:
        score += 5
    return score


def _is_generic_slide_title(title: Any) -> bool:
    normalized = str(title or "").strip().casefold()
    if not normalized:
        return True
    return normalized in {
        "표지",
        "목차",
        "슬라이드",
        "slide",
        "slide 1",
        "slide 2",
        "slide 3",
        "slide 4",
        "slide 5",
    } or normalized.startswith("슬라이드 ")


def _merge_slide_outline_with_hint(
    item: dict[str, Any],
    *,
    hint: dict[str, Any] | None,
    fallback_page: int,
    replace_title: bool = False,
    prefer_hint_fields: bool = False,
) -> dict[str, Any]:
    merged = {
        "page": int(item.get("page") or fallback_page),
        "title": str(item.get("title", "") or "").strip(),
        "key_content": str(item.get("key_content", "") or "").strip(),
        "core_message": str(item.get("core_message", "") or "").strip(),
        "evidence_points": [
            str(point).strip()
            for point in item.get("evidence_points", []) or []
            if str(point).strip()
        ],
        "visual_type": str(item.get("visual_type", "") or "").strip(),
        "visual_brief": str(item.get("visual_brief", "") or "").strip(),
        "layout_hint": str(item.get("layout_hint", "") or "").strip(),
        "design_tip": str(item.get("design_tip", "") or "").strip(),
    }
    if not hint:
        return merged

    detail = str(hint.get("detail", "") or "").strip()
    label = str(hint.get("label", "") or "").strip()
    candidate_label = str(hint.get("candidate_label", "") or "").strip()
    page = int(hint.get("page") or merged["page"])
    visual_type = str(hint.get("visual_type", "") or "").strip()
    layout_hint = str(hint.get("layout_hint", "") or "").strip()

    if replace_title or not merged["title"]:
        if candidate_label and detail:
            merged["title"] = f"{candidate_label} — {detail}"
        else:
            merged["title"] = detail or candidate_label or label or f"조달 근거 페이지 {page}"
    if not merged["core_message"]:
        merged["core_message"] = (
            f"{detail}를 중심으로 발주처가 확인하는 핵심 검토 기준을 정리합니다."
            if detail
            else f"{candidate_label or label or '조달 근거'} 관점의 핵심 내용을 요약합니다."
        )
    if not merged["key_content"]:
        merged["key_content"] = (
            f"참고 자료 {page}페이지의 핵심 내용을 바탕으로 {candidate_label or label or '검토 포인트'}를 설명합니다. "
            f"발주처 관점에서 필요한 근거와 대응 포인트를 함께 제시합니다."
        )
    procurement_evidence = f"참고 페이지: {page}p [{label or '일반 본문'}] {detail}".strip()
    if procurement_evidence not in merged["evidence_points"]:
        merged["evidence_points"] = [*merged["evidence_points"][:3], procurement_evidence]
    if prefer_hint_fields or not merged["visual_type"]:
        merged["visual_type"] = visual_type
    if prefer_hint_fields or not merged["layout_hint"]:
        merged["layout_hint"] = layout_hint
    if prefer_hint_fields or not merged["visual_brief"]:
        merged["visual_brief"] = (
            f"참고 PDF {page}p '{detail}'를 근거로 {visual_type or '요약 카드'} 중심 시각자료를 구성합니다."
        )
    if prefer_hint_fields or not merged["design_tip"]:
        merged["design_tip"] = (
            f"조달 근거 페이지 {page}의 구조를 재사용하고, {candidate_label or label or '핵심 근거'}를 한 장에서 바로 읽히게 정리하세요."
        )
    merged["_procurement_hint_page"] = page
    return merged


def _synthesize_procurement_slides(hints: list[dict[str, Any]], *, limit: int = 3) -> list[dict[str, Any]]:
    synthesized: list[dict[str, Any]] = []
    for idx, hint in enumerate(hints[:limit], start=1):
        detail = str(hint.get("detail", "") or "").strip()
        label = str(hint.get("label", "") or "").strip()
        candidate_label = str(hint.get("candidate_label", "") or "").strip()
        title = detail or candidate_label or label or f"조달 근거 {idx}"
        synthesized.append(
            _merge_slide_outline_with_hint(
                {
                    "page": idx,
                    "title": title,
                    "key_content": "",
                    "core_message": "",
                    "evidence_points": [],
                    "visual_type": "",
                    "visual_brief": "",
                    "layout_hint": "",
                    "design_tip": "",
                },
                hint=hint,
                fallback_page=idx,
                replace_title=True,
                prefer_hint_fields=True,
            )
        )
    for idx, slide in enumerate(synthesized, start=1):
        slide["page"] = idx
        slide.pop("_procurement_hint_page", None)
    return synthesized


def _apply_procurement_slide_outline_guidance(
    bundle: dict[str, Any],
    *,
    procurement_context: str,
) -> dict[str, Any]:
    parsed = parse_procurement_pdf_context(procurement_context)
    base_hints = parsed.get("page_design_hints", [])
    if not isinstance(base_hints, list) or not base_hints:
        return bundle

    candidate_map = {
        int(item["page"]): str(item.get("candidate_label", "") or "").strip()
        for item in parsed.get("ppt_candidates", [])
        if isinstance(item, dict) and str(item.get("page", "")).isdigit()
    }
    hints: list[dict[str, Any]] = []
    for hint in base_hints:
        if not isinstance(hint, dict):
            continue
        page = int(hint.get("page") or 0)
        merged_hint = dict(hint)
        if candidate_map.get(page):
            merged_hint["candidate_label"] = candidate_map[page]
        hints.append(merged_hint)
    if not hints:
        return bundle

    for doc_value in bundle.values():
        if not isinstance(doc_value, dict) or "slide_outline" not in doc_value:
            continue
        outline = doc_value.get("slide_outline")
        if not isinstance(outline, list) or not outline:
            synthesized = _synthesize_procurement_slides(hints)
            if synthesized:
                doc_value["slide_outline"] = synthesized
                if not isinstance(doc_value.get("total_slides"), int) or doc_value.get("total_slides", 0) < len(synthesized):
                    doc_value["total_slides"] = len(synthesized)
            continue

        remaining = [dict(hint) for hint in hints]
        guided: list[dict[str, Any]] = []
        matched_pages: list[int] = []
        for idx, item in enumerate(outline, start=1):
            if not isinstance(item, dict):
                continue
            best_hint = None
            best_score = 0
            for candidate in remaining:
                score = _procurement_overlap_score(item, candidate)
                if score > best_score:
                    best_score = score
                    best_hint = candidate
            if best_hint is None and remaining:
                best_hint = remaining[0]
            if best_hint is not None and best_hint in remaining:
                remaining.remove(best_hint)
            title_key = _procurement_text_key(item.get("title"))
            detail_key = _procurement_text_key(best_hint.get("detail", "")) if best_hint else ""
            candidate_key = _procurement_text_key(best_hint.get("candidate_label", "")) if best_hint else ""
            title_needs_detail = bool(
                best_hint
                and detail_key
                and detail_key not in title_key
                and candidate_key
                and candidate_key in title_key
            )
            replace_title = (
                _is_generic_slide_title(item.get("title"))
                or best_score <= 1
                or title_needs_detail
                or bool(best_hint and detail_key and detail_key not in title_key and best_score <= 5)
            )
            prefer_hint_fields = bool(best_hint and (replace_title or best_score <= 5))
            merged = _merge_slide_outline_with_hint(
                item,
                hint=best_hint,
                fallback_page=idx,
                replace_title=replace_title,
                prefer_hint_fields=prefer_hint_fields,
            )
            hint_page = merged.get("_procurement_hint_page")
            if isinstance(hint_page, int):
                matched_pages.append(hint_page)
            guided.append(merged)

        if guided and matched_pages and len(matched_pages) >= min(2, len(guided)):
            guided.sort(key=lambda item: int(item.get("_procurement_hint_page") or 10_000))
            for new_page, slide in enumerate(guided, start=1):
                slide["page"] = new_page
                slide.pop("_procurement_hint_page", None)
        else:
            for slide in guided:
                slide.pop("_procurement_hint_page", None)

        if guided:
            doc_value["slide_outline"] = guided
            if not isinstance(doc_value.get("total_slides"), int) or doc_value.get("total_slides", 0) < len(guided):
                doc_value["total_slides"] = len(guided)
    return bundle
