"""Structured slide-outline helpers and the guided per-slide renderer."""
from __future__ import annotations

from typing import Any

from pptx import Presentation

from app.services.markdown_utils import (
    slide_outline_evidence,
    slide_outline_layout,
    slide_outline_message,
    slide_outline_visual,
)
from app.services.pptx.constants import (
    _COLOR_BG_ACCENT,
    _COLOR_BG_SOFT,
    _COLOR_CARD,
    _COLOR_CARD_SOFT,
    _COLOR_TEXT_DARK,
    _COLOR_TEXT_MUTED,
)
from app.services.pptx.primitives import (
    _add_card,
    _clean_slide_text,
    _expand_slide_line,
    _set_slide_background,
    _style_text_frame,
)
from app.services.pptx.visual_panels import _render_structured_visual_panel


def _structured_slide_summaries(slide_outline: list[dict[str, Any]]) -> list[dict[str, str]]:
    summaries: list[dict[str, str]] = []
    for idx, item in enumerate(slide_outline[:4], start=1):
        title = _clean_slide_text(item.get("title", "")) or f"슬라이드 {idx}"
        lead = slide_outline_message(item) or "핵심 메시지 없음"
        evidence = slide_outline_evidence(item)
        visual = slide_outline_visual(item)
        metrics = f"핵심 항목 {max(1, len(evidence) or 1)}개"
        metric_items = [metrics]
        if visual:
            metric_items.append(f"시각자료 {visual}")
        summaries.append(
            {
                "index": f"{idx:02d}",
                "label": title,
                "lead": lead,
                "ppt_lead": _clean_slide_text(_expand_slide_line(lead, max_len=54)[0]) if lead else "",
                "sections": title,
                "metrics": metrics,
                "metric_items": metric_items,
            }
        )
    return summaries


def _structured_slide_lines(item: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    core_message = slide_outline_message(item)
    if core_message:
        lines.extend(_expand_slide_line(core_message, max_len=58)[:2])
    for evidence in slide_outline_evidence(item)[:3]:
        lines.append(f"입증 포인트: {evidence}")
    return lines[:5] or ["핵심 메시지 없음"]


def _structured_slide_guidance(item: dict[str, Any]) -> list[str]:
    guidance: list[str] = []
    visual = slide_outline_visual(item)
    layout = slide_outline_layout(item)
    if visual:
        guidance.append(f"권장 시각자료: {visual}")
    if layout:
        guidance.extend(_expand_slide_line(f"배치 가이드: {layout}", max_len=34)[:2])
    return guidance[:3]


def _structured_slide_decision_question(item: dict[str, Any]) -> str:
    return _clean_slide_text(item.get("decision_question", "")) or "이 장표에서 승인권자가 판단해야 할 결론은 무엇인가?"


def _structured_slide_narrative_role(item: dict[str, Any]) -> str:
    return _clean_slide_text(item.get("narrative_role", ""))


def _structured_slide_list_field(item: dict[str, Any], field: str, *, limit: int = 3) -> list[str]:
    raw = item.get(field)
    if isinstance(raw, list):
        return [_clean_slide_text(value) for value in raw if _clean_slide_text(value)][:limit]
    value = _clean_slide_text(raw)
    return [value] if value else []


def _structured_slide_content_blocks(item: dict[str, Any]) -> list[str]:
    blocks = _structured_slide_list_field(item, "content_blocks", limit=3)
    if blocks:
        return blocks
    evidence = slide_outline_evidence(item)
    if evidence:
        return [f"근거 블록: {value}" for value in evidence[:2]]
    return ["핵심 메시지", "근거", "의사결정 포인트"]


def _structured_slide_data_needs(item: dict[str, Any]) -> list[str]:
    data_needs = _structured_slide_list_field(item, "data_needs", limit=2)
    if data_needs:
        return data_needs
    return slide_outline_evidence(item)[:2]


def _structured_slide_acceptance_criteria(item: dict[str, Any]) -> list[str]:
    raw = item.get("acceptance_criteria")
    if isinstance(raw, list):
        criteria = [_clean_slide_text(value) for value in raw if _clean_slide_text(value)]
    else:
        criteria = []
    if criteria:
        return criteria[:3]
    evidence = slide_outline_evidence(item)
    if evidence:
        return [f"근거 확인: {value}" for value in evidence[:3]]
    return ["핵심 메시지, 근거, 시각화가 한 장표 안에서 연결됨"]


def _render_structured_guided_slide(
    prs: Presentation,
    item: dict[str, Any],
    *,
    notes: str = "",
    asset: dict[str, Any] | None = None,
) -> None:
    slide = prs.slides.add_slide(prs.slide_layouts[5])
    _set_slide_background(slide, _COLOR_BG_SOFT)
    title = _clean_slide_text(item.get("title", "")) or "슬라이드"
    slide.shapes.title.text = title
    _style_text_frame(
        slide.shapes.title.text_frame,
        font_size_pt=24,
        bold=True,
        color=_COLOR_TEXT_DARK,
    )

    message_lines = _expand_slide_line(slide_outline_message(item), max_len=38)[:2]
    evidence_lines = [f"입증 포인트: {point}" for point in slide_outline_evidence(item)[:3]]
    role = _structured_slide_narrative_role(item)
    role_lines = _expand_slide_line(f"스토리 역할: {role}", max_len=38)[:1] if role else []
    content_lines = message_lines + role_lines + evidence_lines[:2]
    _add_card(
        slide,
        left=0.65,
        top=1.25,
        width=4.15,
        height=1.72,
        title="핵심 메시지",
        body=content_lines or ["핵심 메시지 없음"],
        fill_color=_COLOR_CARD,
        title_color=_COLOR_TEXT_DARK,
        body_color=_COLOR_TEXT_DARK,
    )

    _add_card(
        slide,
        left=0.65,
        top=3.1,
        width=4.15,
        height=0.56,
        title="장표 구성",
        body=_structured_slide_content_blocks(item),
        fill_color=_COLOR_CARD,
        title_color=_COLOR_TEXT_DARK,
        body_color=_COLOR_TEXT_MUTED,
    )

    _add_card(
        slide,
        left=0.65,
        top=3.82,
        width=4.15,
        height=0.76,
        title="의사결정 질문",
        body=_expand_slide_line(_structured_slide_decision_question(item), max_len=34)[:2],
        fill_color=_COLOR_CARD_SOFT,
        title_color=_COLOR_BG_ACCENT,
        body_color=_COLOR_TEXT_DARK,
    )

    _add_card(
        slide,
        left=0.65,
        top=4.72,
        width=4.15,
        height=0.78,
        title="승인 기준",
        body=_structured_slide_acceptance_criteria(item),
        fill_color=_COLOR_CARD,
        title_color=_COLOR_TEXT_DARK,
        body_color=_COLOR_TEXT_MUTED,
    )

    _add_card(
        slide,
        left=5.0,
        top=4.45,
        width=4.0,
        height=0.95,
        title="시각자료 배치 / 검증 가이드",
        body=(
            _structured_slide_guidance(item)
            + [f"검증 필요: {need}" for need in _structured_slide_data_needs(item)]
        )[:4] or ["배치 가이드 없음"],
        fill_color=_COLOR_CARD,
        title_color=_COLOR_TEXT_DARK,
        body_color=_COLOR_TEXT_MUTED,
    )

    _render_structured_visual_panel(
        slide,
        asset=asset,
        left=5.0,
        top=1.25,
        width=4.0,
        height=3.0,
        item=item,
    )

    if notes.strip():
        slide.notes_slide.notes_text_frame.text = notes.strip()
