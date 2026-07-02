"""Structured-slide visual panel renderers (placeholder, cards, KPI, matrix,
timeline, flow, governance) plus generated-image/SVG asset handling."""
from __future__ import annotations

import base64
import html
import re

from io import BytesIO
from typing import Any

from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_AUTO_SHAPE_TYPE
from pptx.enum.text import PP_ALIGN
from pptx.util import Inches, Pt

from app.services.markdown_utils import slide_outline_evidence, slide_outline_visual
from app.services.pptx.constants import (
    _COLOR_BG_ACCENT,
    _COLOR_BORDER,
    _COLOR_CARD,
    _COLOR_CARD_SOFT,
    _COLOR_TEXT_DARK,
    _COLOR_TEXT_LIGHT,
    _COLOR_TEXT_MUTED,
)
from app.services.pptx.primitives import (
    _add_card,
    _add_text_box,
    _clean_slide_text,
    _expand_slide_line,
    _style_text_frame,
)


def _structured_visual_lines(item: dict[str, Any]) -> list[str]:
    raw_visual_type = _clean_slide_text(item.get("visual_type", ""))
    raw_visual_brief = _clean_slide_text(item.get("visual_brief", ""))
    derived_visual = slide_outline_visual(item)
    visual_type = raw_visual_type or (derived_visual.split(" — ", 1)[0] if " — " in derived_visual else derived_visual)
    visual_brief = raw_visual_brief or (derived_visual.split(" — ", 1)[1] if " — " in derived_visual else "")

    lines = ["시각자료 자리"]
    if visual_type:
        lines.append(visual_type)
    if visual_brief:
        lines.extend(_expand_slide_line(visual_brief, max_len=28)[:2])
    return lines[:4]


def _visual_kind(item: dict[str, Any]) -> str:
    visual = slide_outline_visual(item)
    lowered = visual.lower()
    if any(keyword in visual for keyword in ["타임라인", "로드맵", "간트", "마일스톤"]):
        return "timeline"
    if any(keyword in visual for keyword in ["거버넌스", "조직도", "보고", "역할"]):
        return "governance"
    if any(keyword in visual for keyword in ["프로세스", "흐름도", "절차", "플로우"]):
        return "flow"
    if any(keyword in visual for keyword in ["매트릭스", "matrix", "평가표", "우선순위"]) or "matrix" in lowered:
        return "matrix"
    if any(keyword in visual for keyword in ["KPI", "지표", "성과", "metric", "scorecard"]) or "kpi" in lowered:
        return "kpi"
    if any(keyword in visual for keyword in ["비교", "카드", "차트", "지표", "목표", "매트릭스"]) or "card" in lowered:
        return "cards"
    return "placeholder"


def _render_visual_placeholder(
    slide: Any,
    item: dict[str, Any],
    *,
    left: float,
    top: float,
    width: float,
    height: float,
) -> None:
    _add_card(
        slide,
        left=left,
        top=top,
        width=width,
        height=height,
        title="권장 시각자료",
        body=_structured_visual_lines(item),
        fill_color=_COLOR_CARD_SOFT,
        title_color=_COLOR_BG_ACCENT,
        body_color=_COLOR_TEXT_DARK,
    )


def _render_visual_image_asset(
    slide: Any,
    item: dict[str, Any],
    asset: dict[str, Any],
    *,
    left: float,
    top: float,
    width: float,
    height: float,
) -> bool:
    media_type = str(asset.get("media_type", "") or "").strip().lower()
    if media_type not in {"image/png", "image/jpeg", "image/webp"}:
        return False
    encoded = str(asset.get("content_base64", "") or "").strip()
    if not encoded:
        return False
    try:
        raw = base64.b64decode(encoded)
    except Exception:
        return False
    if not raw:
        return False

    background = slide.shapes.add_shape(
        MSO_AUTO_SHAPE_TYPE.ROUNDED_RECTANGLE,
        Inches(left),
        Inches(top),
        Inches(width),
        Inches(height),
    )
    background.fill.solid()
    background.fill.fore_color.rgb = _COLOR_CARD
    background.line.color.rgb = _COLOR_BORDER
    background.line.width = Pt(1)

    _add_text_box(
        slide,
        left=left + 0.18,
        top=top + 0.08,
        width=width - 0.36,
        height=0.28,
        text="생성 시각자료",
        font_size_pt=12,
        bold=True,
        color=_COLOR_BG_ACCENT,
    )

    try:
        slide.shapes.add_picture(
            BytesIO(raw),
            Inches(left + 0.18),
            Inches(top + 0.42),
            width=Inches(width - 0.36),
            height=Inches(height - 0.64),
        )
    except Exception:
        return False

    caption = _clean_slide_text(asset.get("visual_brief", "")) or slide_outline_visual(item)
    if caption:
        _add_text_box(
            slide,
            left=left + 0.2,
            top=top + height - 0.24,
            width=width - 0.4,
            height=0.18,
            text=caption,
            font_size_pt=9,
            color=_COLOR_TEXT_MUTED,
        )
    return True


def _svg_asset_text_lines(asset: dict[str, Any], *, slide_title: str = "") -> list[str]:
    media_type = str(asset.get("media_type", "") or "").strip().lower()
    if media_type != "image/svg+xml":
        return []
    encoded = str(asset.get("content_base64", "") or "").strip()
    if not encoded:
        return []
    try:
        raw = base64.b64decode(encoded)
        svg_text = raw.decode("utf-8", errors="ignore")
    except Exception:
        return []

    ignored = {
        _clean_slide_text(slide_title),
        "Timeline Asset",
        "Flow Asset",
        "Governance Asset",
        "Chart Asset",
        "Image Fallback Asset",
    }
    labels: list[str] = []
    for match in re.finditer(r"<text\b[^>]*>(.*?)</text>", svg_text, flags=re.IGNORECASE | re.DOTALL):
        label = _clean_slide_text(re.sub(r"<[^>]+>", "", html.unescape(match.group(1))))
        if not label or label in ignored or label.isdigit():
            continue
        if label not in labels:
            labels.append(label)
        if len(labels) >= 6:
            break
    return labels


def _with_svg_asset_evidence(item: dict[str, Any], asset: dict[str, Any]) -> dict[str, Any]:
    slide_title = _clean_slide_text(asset.get("slide_title", "")) or _clean_slide_text(item.get("title", ""))
    labels = _svg_asset_text_lines(asset, slide_title=slide_title)
    if not labels:
        return item
    enriched = dict(item)
    existing = slide_outline_evidence(item)
    merged: list[str] = []
    for label in [*labels, *existing]:
        if label and label not in merged:
            merged.append(label)
    enriched["evidence_points"] = merged[:6]
    enriched["visual_type"] = _clean_slide_text(asset.get("visual_type", "")) or _clean_slide_text(item.get("visual_type", ""))
    enriched["visual_brief"] = _clean_slide_text(asset.get("visual_brief", "")) or _clean_slide_text(item.get("visual_brief", ""))
    enriched["layout_hint"] = _clean_slide_text(asset.get("layout_hint", "")) or _clean_slide_text(item.get("layout_hint", ""))
    return enriched


def _render_visual_cards(
    slide: Any,
    item: dict[str, Any],
    *,
    left: float,
    top: float,
    width: float,
    height: float,
) -> None:
    _add_card(
        slide,
        left=left,
        top=top,
        width=width,
        height=0.55,
        title="비교 카드",
        body="핵심 근거를 시각 카드로 배치",
        fill_color=_COLOR_CARD_SOFT,
        title_color=_COLOR_BG_ACCENT,
        body_color=_COLOR_TEXT_DARK,
    )
    points = slide_outline_evidence(item)[:4] or _structured_visual_lines(item)[1:4]
    positions = [(left, top + 0.72), (left + 2.0, top + 0.72), (left, top + 1.92), (left + 2.0, top + 1.92)]
    for point, (card_left, card_top) in zip(points, positions, strict=False):
        _add_card(
            slide,
            left=card_left,
            top=card_top,
            width=1.85,
            height=1.0,
            title="핵심 포인트",
            body=_expand_slide_line(point, max_len=18)[:2],
            fill_color=_COLOR_CARD,
            title_color=_COLOR_TEXT_DARK,
            body_color=_COLOR_TEXT_MUTED,
        )


def _render_visual_kpi(
    slide: Any,
    item: dict[str, Any],
    *,
    left: float,
    top: float,
    width: float,
    height: float,
) -> None:
    _add_card(
        slide,
        left=left,
        top=top,
        width=width,
        height=0.55,
        title="KPI / 핵심 지표",
        body="성과 지표를 editable scorecard로 배치",
        fill_color=_COLOR_CARD_SOFT,
        title_color=_COLOR_BG_ACCENT,
        body_color=_COLOR_TEXT_DARK,
    )
    points = slide_outline_evidence(item)[:4] or _structured_visual_lines(item)[1:4]
    if not points:
        points = ["성과 지표", "운영 효과", "승인 기준"]
    positions = [(left, top + 0.85), (left + 2.05, top + 0.85), (left, top + 2.0), (left + 2.05, top + 2.0)]
    for idx, (point, (card_left, card_top)) in enumerate(zip(points[:4], positions, strict=False), start=1):
        _add_card(
            slide,
            left=card_left,
            top=card_top,
            width=1.9,
            height=0.95,
            title=f"KPI {idx}",
            body=_expand_slide_line(point, max_len=18)[:2],
            fill_color=_COLOR_CARD,
            title_color=_COLOR_BG_ACCENT,
            body_color=_COLOR_TEXT_DARK,
        )


def _render_visual_matrix(
    slide: Any,
    item: dict[str, Any],
    *,
    left: float,
    top: float,
    width: float,
    height: float,
) -> None:
    _add_card(
        slide,
        left=left,
        top=top,
        width=width,
        height=0.55,
        title="의사결정 매트릭스",
        body="기준별 판단을 editable table로 정리",
        fill_color=_COLOR_CARD_SOFT,
        title_color=_COLOR_BG_ACCENT,
        body_color=_COLOR_TEXT_DARK,
    )
    criteria = item.get("acceptance_criteria")
    if not isinstance(criteria, list) or not criteria:
        criteria = slide_outline_evidence(item)[:3]
    rows = []
    for idx, criterion in enumerate(criteria[:4], start=1):
        rows.append([
            f"기준 {idx}",
            _clean_slide_text(criterion),
            "확인 필요",
        ])
    if not rows:
        rows = [["기준 1", "핵심 메시지와 근거 정합성", "확인 필요"]]

    table_shape = slide.shapes.add_table(
        len(rows) + 1,
        3,
        Inches(left),
        Inches(top + 0.85),
        Inches(width),
        Inches(min(2.15, height - 0.9)),
    )
    table = table_shape.table
    headers = ["판단 기준", "내용", "상태"]
    for col_idx, header in enumerate(headers):
        cell = table.cell(0, col_idx)
        cell.text = header
        cell.fill.solid()
        cell.fill.fore_color.rgb = _COLOR_BG_ACCENT
        _style_text_frame(cell.text_frame, font_size_pt=9, bold=True, color=_COLOR_TEXT_LIGHT, align=PP_ALIGN.CENTER)
    for row_idx, row in enumerate(rows, start=1):
        for col_idx, value in enumerate(row):
            cell = table.cell(row_idx, col_idx)
            cell.text = value
            if row_idx % 2 == 1:
                cell.fill.solid()
                cell.fill.fore_color.rgb = RGBColor(250, 250, 255)
            _style_text_frame(cell.text_frame, font_size_pt=8, color=_COLOR_TEXT_DARK)


def _render_visual_timeline(
    slide: Any,
    item: dict[str, Any],
    *,
    left: float,
    top: float,
    width: float,
    height: float,
) -> None:
    _add_card(
        slide,
        left=left,
        top=top,
        width=width,
        height=0.55,
        title="타임라인 도식",
        body="단계별 흐름과 마일스톤을 시각화",
        fill_color=_COLOR_CARD_SOFT,
        title_color=_COLOR_BG_ACCENT,
        body_color=_COLOR_TEXT_DARK,
    )
    points = slide_outline_evidence(item)[:4] or _structured_visual_lines(item)[1:4]
    if not points:
        points = ["1단계", "2단계", "3단계"]
    step_width = min(1.1, (width - 0.4) / max(1, len(points)))
    for idx, point in enumerate(points, start=1):
        node_left = left + 0.1 + (idx - 1) * step_width
        _add_card(
            slide,
            left=node_left,
            top=top + 1.2,
            width=0.95,
            height=1.35,
            title=f"{idx:02d}",
            body=_expand_slide_line(point, max_len=14)[:3],
            fill_color=_COLOR_CARD,
            title_color=_COLOR_BG_ACCENT,
            body_color=_COLOR_TEXT_DARK,
        )
        if idx < len(points):
            _add_text_box(
                slide,
                left=node_left + 0.92,
                top=top + 1.65,
                width=0.18,
                height=0.2,
                text="→",
                font_size_pt=18,
                bold=True,
                color=_COLOR_BG_ACCENT,
                align=PP_ALIGN.CENTER,
            )


def _render_visual_flow(
    slide: Any,
    item: dict[str, Any],
    *,
    left: float,
    top: float,
    width: float,
    height: float,
) -> None:
    _add_card(
        slide,
        left=left,
        top=top,
        width=width,
        height=0.55,
        title="프로세스 흐름",
        body="단계별 업무 흐름과 전환 포인트를 표현",
        fill_color=_COLOR_CARD_SOFT,
        title_color=_COLOR_BG_ACCENT,
        body_color=_COLOR_TEXT_DARK,
    )
    points = slide_outline_evidence(item)[:3] or _structured_visual_lines(item)[1:4]
    if not points:
        points = ["입력", "처리", "결과"]
    for idx, point in enumerate(points, start=1):
        box_top = top + 0.82 + (idx - 1) * 0.88
        _add_card(
            slide,
            left=left + 0.3,
            top=box_top,
            width=width - 0.6,
            height=0.62,
            title=f"단계 {idx}",
            body=_expand_slide_line(point, max_len=28)[:2],
            fill_color=_COLOR_CARD,
            title_color=_COLOR_TEXT_DARK,
            body_color=_COLOR_TEXT_MUTED,
        )
        if idx < len(points):
            _add_text_box(
                slide,
                left=left + (width / 2) - 0.1,
                top=box_top + 0.58,
                width=0.2,
                height=0.2,
                text="↓",
                font_size_pt=18,
                bold=True,
                color=_COLOR_BG_ACCENT,
                align=PP_ALIGN.CENTER,
            )


def _render_visual_governance(
    slide: Any,
    item: dict[str, Any],
    *,
    left: float,
    top: float,
    width: float,
    height: float,
) -> None:
    _add_card(
        slide,
        left=left,
        top=top,
        width=width,
        height=0.55,
        title="거버넌스 구조",
        body="의사결정과 보고 흐름을 시각화",
        fill_color=_COLOR_CARD_SOFT,
        title_color=_COLOR_BG_ACCENT,
        body_color=_COLOR_TEXT_DARK,
    )
    points = slide_outline_evidence(item)[:3]
    headline = points[0] if points else "총괄 의사결정"
    children = points[1:] or ["실무 운영", "성과 보고"]
    _add_card(
        slide,
        left=left + 1.0,
        top=top + 0.82,
        width=2.0,
        height=0.72,
        title="총괄",
        body=_expand_slide_line(headline, max_len=18)[:2],
        fill_color=_COLOR_CARD,
        title_color=_COLOR_BG_ACCENT,
        body_color=_COLOR_TEXT_DARK,
    )
    child_positions = [left + 0.2, left + 2.15, left + 4.1]
    for child, child_left in zip(children[:3], child_positions, strict=False):
        _add_text_box(
            slide,
            left=child_left + 0.85,
            top=top + 1.46,
            width=0.2,
            height=0.2,
            text="↓",
            font_size_pt=18,
            bold=True,
            color=_COLOR_BG_ACCENT,
            align=PP_ALIGN.CENTER,
        )
        _add_card(
            slide,
            left=child_left,
            top=top + 1.72,
            width=1.75,
            height=0.92,
            title="역할",
            body=_expand_slide_line(child, max_len=16)[:2],
            fill_color=_COLOR_CARD,
            title_color=_COLOR_TEXT_DARK,
            body_color=_COLOR_TEXT_MUTED,
        )


def _render_structured_visual_panel(
    slide: Any,
    item: dict[str, Any],
    asset: dict[str, Any] | None = None,
    *,
    left: float,
    top: float,
    width: float,
    height: float,
) -> None:
    if asset and _render_visual_image_asset(slide, item, asset, left=left, top=top, width=width, height=height):
        return
    if asset and str(asset.get("media_type", "") or "").strip().lower() == "image/svg+xml":
        item = _with_svg_asset_evidence(item, asset)
    kind = _visual_kind(item)
    if kind == "timeline":
        _render_visual_timeline(slide, item, left=left, top=top, width=width, height=height)
        return
    if kind == "flow":
        _render_visual_flow(slide, item, left=left, top=top, width=width, height=height)
        return
    if kind == "governance":
        _render_visual_governance(slide, item, left=left, top=top, width=width, height=height)
        return
    if kind == "matrix":
        _render_visual_matrix(slide, item, left=left, top=top, width=width, height=height)
        return
    if kind == "kpi":
        _render_visual_kpi(slide, item, left=left, top=top, width=width, height=height)
        return
    if kind == "cards":
        _render_visual_cards(slide, item, left=left, top=top, width=width, height=height)
        return
    _render_visual_placeholder(slide, item, left=left, top=top, width=width, height=height)
