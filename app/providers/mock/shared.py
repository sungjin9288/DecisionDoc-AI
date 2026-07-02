"""Shared helpers for mock provider fixture builders and generate_raw()."""
from typing import Any


def _extract_document_ops_payload(prompt: str) -> dict[str, Any]:
    marker = "Task payload JSON:"
    if marker not in prompt:
        return {}
    raw = prompt.split(marker, 1)[1].strip()
    try:
        import json as _json

        data = _json.loads(raw)
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}

def _derive_slide_points(text: str, limit: int = 3) -> list[str]:
    normalized = " ".join(str(text or "").split())
    if not normalized:
        return []
    parts = [
        item.strip()
        for item in normalized.replace(" / ", " · ").replace(" + ", " · ").split(" · ")
        if item.strip()
    ]
    if len(parts) == 1:
        parts = [
            item.strip()
            for item in normalized.split(". ")
            if item.strip()
        ]
    deduped: list[str] = []
    for part in parts:
        if part and part not in deduped:
            deduped.append(part)
        if len(deduped) >= limit:
            break
    return deduped

def _infer_visual_type(design_tip: str) -> str:
    hints = (
        ("간트", "간트 차트"),
        ("타임라인", "타임라인"),
        ("조직도", "조직도"),
        ("흐름도", "프로세스 흐름도"),
        ("다이어그램", "구조 다이어그램"),
        ("매트릭스", "매트릭스"),
        ("와이어프레임", "화면 와이어프레임"),
        ("목업", "화면 목업"),
        ("스크린샷", "스크린샷"),
        ("사진", "현장 사진"),
        ("그래프", "그래프"),
        ("차트", "차트"),
        ("표", "비교 표"),
        ("로고", "로고/브랜드 카드"),
        ("아이콘", "아이콘 카드"),
    )
    for keyword, label in hints:
        if keyword in design_tip:
            return label
    return "시각자료 카드"

def _slide(
    page: int,
    title: str,
    key_content: str,
    design_tip: str,
    *,
    core_message: str | None = None,
    evidence_points: list[str] | None = None,
    visual_type: str | None = None,
    visual_brief: str | None = None,
    layout_hint: str | None = None,
) -> dict:
    normalized_key = " ".join(str(key_content or "").split())
    normalized_tip = " ".join(str(design_tip or "").split())
    derived_points = evidence_points or _derive_slide_points(normalized_key)
    derived_visual_type = visual_type or _infer_visual_type(normalized_tip)
    derived_visual_brief = visual_brief or normalized_tip
    derived_layout_hint = layout_hint or normalized_tip
    return {
        "page": page,
        "title": title,
        "key_content": key_content,
        "core_message": core_message or normalized_key,
        "evidence_points": derived_points,
        "visual_type": derived_visual_type,
        "visual_brief": derived_visual_brief,
        "layout_hint": derived_layout_hint,
        "design_tip": design_tip,
    }

def _ctx_excerpt(ctx: str, limit: int = 360) -> str:
    compact = " ".join(line.strip() for line in ctx.splitlines() if line.strip())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 3] + "..."

def _project_subject(title: str) -> str:
    subject = str(title or "").strip()
    for suffix in (" 사업 제안서", " 제안서", " 사업수행계획서", " 수행계획서", " 발표자료", " 보고서"):
        if subject.endswith(suffix):
            subject = subject[: -len(suffix)].strip()
    return subject or str(title or "").strip()
