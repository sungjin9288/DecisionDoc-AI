"""Generate visual assets for slide-oriented outputs.

This service provides a practical mixed strategy:
- photo / illustration style requests use the active provider when supported
- timeline / flow / governance / chart requests are rendered as deterministic SVGs

The result can be shown in the web UI immediately and selectively embedded into
PPTX exports when a raster image asset is available.
"""
from __future__ import annotations

import base64
import html
from typing import Any
from uuid import uuid4

from app.providers.base import Provider
from app.services.markdown_utils import (
    slide_outline_evidence,
    slide_outline_layout,
    slide_outline_message,
    slide_outline_visual,
)

_MAX_PROVIDER_IMAGE_ASSETS = 2


def _clean_text(value: Any) -> str:
    return " ".join(str(value or "").replace("**", "").replace("`", "").split()).strip()


def _normalize_slide_docs(docs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for doc in docs:
        if not isinstance(doc, dict):
            continue
        doc_type = _clean_text(doc.get("doc_type", "")) or "document"
        slide_outline = doc.get("slide_outline")
        if not isinstance(slide_outline, list):
            continue
        for index, item in enumerate(slide_outline, start=1):
            if not isinstance(item, dict):
                continue
            title = _clean_text(item.get("title", "")) or f"슬라이드 {index}"
            items.append(
                {
                    "doc_type": doc_type,
                    "slide_title": title,
                    "item": item,
                }
            )
    return items


def _visual_request_kind(item: dict[str, Any]) -> str:
    visual = slide_outline_visual(item)
    text = f"{visual} {_clean_text(item.get('visual_type', ''))} {_clean_text(item.get('visual_brief', ''))}".lower()
    if any(keyword in text for keyword in ["사진", "image", "photo", "현장", "배경", "히어로", "mockup", "목업", "일러스트", "illustration", "스크린샷"]):
        return "provider_image"
    if any(keyword in text for keyword in ["타임라인", "로드맵", "간트", "마일스톤"]):
        return "timeline"
    if any(keyword in text for keyword in ["거버넌스", "조직도", "보고", "역할"]):
        return "governance"
    if any(keyword in text for keyword in ["프로세스", "흐름도", "플로우", "절차"]):
        return "flow"
    if any(keyword in text for keyword in ["차트", "그래프", "지표", "비교", "매트릭스", "표", "카드"]):
        return "chart"
    return "chart"


def _svg_escape(value: Any) -> str:
    return html.escape(_clean_text(value))


def _svg_lines(values: list[str], *, limit: int = 4) -> list[str]:
    lines = [_clean_text(value) for value in values if _clean_text(value)]
    return lines[:limit]


def _asset_payload(
    *,
    doc_type: str,
    slide_title: str,
    item: dict[str, Any],
    media_type: str,
    raw: bytes,
    source_kind: str,
    prompt: str = "",
    source_model: str = "",
) -> dict[str, Any]:
    return {
        "asset_id": str(uuid4()),
        "doc_type": doc_type,
        "slide_title": slide_title,
        "visual_type": _clean_text(item.get("visual_type", "")) or slide_outline_visual(item),
        "visual_brief": _clean_text(item.get("visual_brief", "")),
        "layout_hint": _clean_text(item.get("layout_hint", "")) or slide_outline_layout(item),
        "source_kind": source_kind,
        "source_model": source_model,
        "prompt": prompt,
        "media_type": media_type,
        "encoding": "base64",
        "content_base64": base64.b64encode(raw).decode("ascii"),
    }


def _build_image_prompt(
    *,
    slide_title: str,
    title: str,
    goal: str,
    item: dict[str, Any],
) -> str:
    message = slide_outline_message(item)
    evidence = "; ".join(slide_outline_evidence(item)[:3])
    visual = slide_outline_visual(item)
    brief = _clean_text(item.get("visual_brief", ""))
    return (
        "Create a presentation-ready visual for a Korean consulting proposal slide. "
        f"Project title: {title}. Slide title: {slide_title}. Goal: {goal}. "
        f"Core message: {message}. Evidence: {evidence}. "
        f"Requested visual: {visual}. Visual brief: {brief}. "
        "Use a clean, credible corporate style. No watermarks. Minimize visible text."
    )


def _svg_shell(title: str, subtitle: str, body: str) -> str:
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="675" viewBox="0 0 1200 675">'
        '<defs>'
        '<linearGradient id="bg" x1="0%" y1="0%" x2="100%" y2="100%">'
        '<stop offset="0%" stop-color="#1b2145"/><stop offset="100%" stop-color="#624fff"/>'
        "</linearGradient>"
        "</defs>"
        '<rect width="1200" height="675" rx="32" fill="url(#bg)"/>'
        '<rect x="56" y="56" width="1088" height="563" rx="28" fill="#f8f9ff" opacity="0.98"/>'
        f'<text x="96" y="126" font-family="Arial, sans-serif" font-size="20" font-weight="700" fill="#624fff">{_svg_escape(subtitle)}</text>'
        f'<text x="96" y="178" font-family="Arial, sans-serif" font-size="36" font-weight="700" fill="#1f2543">{_svg_escape(title)}</text>'
        f"{body}"
        "</svg>"
    )


def _render_timeline_svg(slide_title: str, item: dict[str, Any]) -> bytes:
    points = _svg_lines(slide_outline_evidence(item), limit=4) or ["준비", "실행", "점검", "보고"]
    nodes: list[str] = []
    start_x = 140
    gap = 230
    for index, point in enumerate(points):
        cx = start_x + (index * gap)
        nodes.append(f'<circle cx="{cx}" cy="360" r="34" fill="#624fff" opacity="0.95"/>')
        nodes.append(f'<text x="{cx}" y="368" text-anchor="middle" font-family="Arial, sans-serif" font-size="16" font-weight="700" fill="#ffffff">{index + 1}</text>')
        nodes.append(f'<text x="{cx}" y="438" text-anchor="middle" font-family="Arial, sans-serif" font-size="20" font-weight="700" fill="#1f2543">{_svg_escape(point)}</text>')
        if index < len(points) - 1:
            nodes.append(f'<line x1="{cx + 34}" y1="360" x2="{cx + gap - 34}" y2="360" stroke="#b5bde9" stroke-width="10" stroke-linecap="round"/>')
    return _svg_shell(slide_title, "Timeline Asset", "".join(nodes)).encode("utf-8")


def _render_flow_svg(slide_title: str, item: dict[str, Any]) -> bytes:
    points = _svg_lines(slide_outline_evidence(item), limit=4) or ["입력", "분석", "실행", "결과"]
    boxes: list[str] = []
    start_y = 220
    for index, point in enumerate(points):
        y = start_y + (index * 92)
        boxes.append(f'<rect x="190" y="{y}" width="820" height="64" rx="18" fill="#ffffff" stroke="#c9cff2" stroke-width="2"/>')
        boxes.append(f'<text x="230" y="{y + 39}" font-family="Arial, sans-serif" font-size="22" font-weight="700" fill="#1f2543">{_svg_escape(point)}</text>')
        if index < len(points) - 1:
            boxes.append(f'<line x1="600" y1="{y + 64}" x2="600" y2="{y + 92}" stroke="#624fff" stroke-width="8" stroke-linecap="round"/>')
            boxes.append(f'<polygon points="590,{y + 90} 610,{y + 90} 600,{y + 108}" fill="#624fff"/>')
    return _svg_shell(slide_title, "Flow Asset", "".join(boxes)).encode("utf-8")


def _render_governance_svg(slide_title: str, item: dict[str, Any]) -> bytes:
    points = _svg_lines(slide_outline_evidence(item), limit=3)
    root = points[0] if points else "총괄 PMO"
    children = points[1:] or ["실무 운영", "성과 보고"]
    body = [
        '<rect x="430" y="210" width="340" height="78" rx="20" fill="#624fff"/>',
        f'<text x="600" y="257" text-anchor="middle" font-family="Arial, sans-serif" font-size="28" font-weight="700" fill="#ffffff">{_svg_escape(root)}</text>',
    ]
    positions = [270, 680]
    for child, x in zip(children[:2], positions, strict=False):
        body.append(f'<line x1="600" y1="288" x2="{x + 120}" y2="360" stroke="#b5bde9" stroke-width="8" stroke-linecap="round"/>')
        body.append(f'<rect x="{x}" y="360" width="240" height="74" rx="18" fill="#ffffff" stroke="#c9cff2" stroke-width="2"/>')
        body.append(f'<text x="{x + 120}" y="405" text-anchor="middle" font-family="Arial, sans-serif" font-size="24" font-weight="700" fill="#1f2543">{_svg_escape(child)}</text>')
    return _svg_shell(slide_title, "Governance Asset", "".join(body)).encode("utf-8")


def _render_chart_svg(slide_title: str, item: dict[str, Any]) -> bytes:
    points = _svg_lines(slide_outline_evidence(item), limit=4) or ["핵심 과제", "차별성", "성과 지표", "리스크 대응"]
    bars: list[str] = []
    base_x = 220
    for index, point in enumerate(points):
        x = base_x + (index * 180)
        height = 90 + (index * 36)
        y = 500 - height
        bars.append(f'<rect x="{x}" y="{y}" width="92" height="{height}" rx="18" fill="#624fff" opacity="{0.68 + (index * 0.08):.2f}"/>')
        bars.append(f'<text x="{x + 46}" y="540" text-anchor="middle" font-family="Arial, sans-serif" font-size="18" font-weight="700" fill="#1f2543">{_svg_escape(point)}</text>')
    bars.append('<line x1="180" y1="500" x2="1020" y2="500" stroke="#c9cff2" stroke-width="4" stroke-linecap="round"/>')
    return _svg_shell(slide_title, "Chart Asset", "".join(bars)).encode("utf-8")


def _render_image_fallback_svg(slide_title: str, item: dict[str, Any]) -> bytes:
    visual = _clean_text(item.get("visual_type", "")) or slide_outline_visual(item) or "이미지"
    brief = _clean_text(item.get("visual_brief", "")) or slide_outline_message(item)
    body = (
        '<rect x="130" y="230" width="940" height="250" rx="28" fill="#ffffff" stroke="#c9cff2" stroke-width="2"/>'
        '<circle cx="250" cy="355" r="64" fill="#eef2ff"/>'
        '<path d="M215 380 L250 328 L282 366 L318 320 L364 392 L215 392 Z" fill="#624fff" opacity="0.88"/>'
        f'<text x="420" y="326" font-family="Arial, sans-serif" font-size="28" font-weight="700" fill="#1f2543">{_svg_escape(visual)}</text>'
        f'<text x="420" y="376" font-family="Arial, sans-serif" font-size="22" fill="#5b6488">{_svg_escape(brief)}</text>'
        '<text x="420" y="420" font-family="Arial, sans-serif" font-size="18" fill="#7b84a8">Provider image unavailable — SVG fallback preview</text>'
    )
    return _svg_shell(slide_title, "Image Fallback Asset", body).encode("utf-8")


def _render_svg_asset(kind: str, slide_title: str, item: dict[str, Any]) -> bytes:
    if kind == "timeline":
        return _render_timeline_svg(slide_title, item)
    if kind == "flow":
        return _render_flow_svg(slide_title, item)
    if kind == "governance":
        return _render_governance_svg(slide_title, item)
    if kind == "provider_image":
        return _render_image_fallback_svg(slide_title, item)
    return _render_chart_svg(slide_title, item)


def generate_visual_assets_from_docs(
    docs: list[dict[str, Any]],
    *,
    title: str,
    goal: str,
    provider: Provider,
    request_id: str,
    max_assets: int = 6,
) -> list[dict[str, Any]]:
    assets: list[dict[str, Any]] = []
    provider_image_count = 0
    for slide in _normalize_slide_docs(docs):
        if len(assets) >= max_assets:
            break
        doc_type = slide["doc_type"]
        slide_title = slide["slide_title"]
        item = slide["item"]
        kind = _visual_request_kind(item)
        if kind == "provider_image" and provider_image_count < _MAX_PROVIDER_IMAGE_ASSETS:
            prompt = _build_image_prompt(
                slide_title=slide_title,
                title=title,
                goal=goal,
                item=item,
            )
            try:
                generated = provider.generate_visual_asset(
                    prompt,
                    request_id=request_id,
                    size="1536x1024",
                    style="natural",
                )
                raw = generated.get("data", b"")
                media_type = str(generated.get("media_type", "image/png") or "image/png")
                if isinstance(raw, bytes) and raw:
                    assets.append(
                        _asset_payload(
                            doc_type=doc_type,
                            slide_title=slide_title,
                            item=item,
                            media_type=media_type,
                            raw=raw,
                            source_kind="provider_image",
                            prompt=str(generated.get("revised_prompt", "") or prompt),
                            source_model=str(generated.get("model", "") or provider.name),
                        )
                    )
                    provider_image_count += 1
                    continue
            except Exception:
                pass
        raw = _render_svg_asset(kind, slide_title, item)
        assets.append(
            _asset_payload(
                doc_type=doc_type,
                slide_title=slide_title,
                item=item,
                media_type="image/svg+xml",
                raw=raw,
                source_kind="generated_svg",
            )
        )
    return assets


def index_visual_assets_by_slide_title(assets: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for asset in assets:
        if not isinstance(asset, dict):
            continue
        title = _clean_text(asset.get("slide_title", ""))
        if title and title not in indexed:
            indexed[title] = asset
    return indexed


def group_visual_assets_by_doc_type(assets: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for asset in assets:
        if not isinstance(asset, dict):
            continue
        doc_type = _clean_text(asset.get("doc_type", ""))
        if not doc_type:
            continue
        bucket = grouped.setdefault(doc_type, [])
        bucket.append(asset)
    return grouped


def decode_visual_asset_bytes(asset: dict[str, Any]) -> bytes:
    encoded = _clean_text(asset.get("content_base64", ""))
    if not encoded:
        return b""
    try:
        return base64.b64decode(encoded)
    except Exception:
        return b""


def visual_asset_data_uri(asset: dict[str, Any]) -> str:
    media_type = _clean_text(asset.get("media_type", "")) or "application/octet-stream"
    encoded = _clean_text(asset.get("content_base64", ""))
    if not encoded:
        return ""
    return f"data:{media_type};base64,{encoded}"
