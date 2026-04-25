"""Report workflow service for staged planning, slide generation, and export."""
from __future__ import annotations

import json
import logging
import re
import uuid
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any, Callable

from app.services.pptx_service import build_pptx
from app.storage.report_workflow_store import (
    PlanningVersion,
    ReportWorkflowRecord,
    ReportWorkflowStore,
    SlideDraft,
    SlidePlan,
)

logger = logging.getLogger("decisiondoc.report_workflows")


ProviderFactory = Callable[[], Any]


def _clean_json_text(raw: str) -> str:
    text = str(raw or "").strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines:
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    first = min([idx for idx in [text.find("{"), text.find("[")] if idx >= 0] or [0])
    if first > 0:
        text = text[first:]
    return text


def _as_list(value: Any) -> list:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, str):
        stripped = value.strip()
        return [stripped] if stripped else []
    return [value]


def _safe_slide_id(value: Any, page: int) -> str:
    raw = str(value or "").strip()
    if raw:
        return re.sub(r"[^a-zA-Z0-9_-]+", "-", raw)[:48].strip("-") or f"slide-{page:03d}"
    return f"slide-{page:03d}"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class ReportWorkflowService:
    """Generate and export staged report workflow artifacts."""

    def __init__(self, *, store: ReportWorkflowStore, provider_factory: ProviderFactory) -> None:
        self.store = store
        self._provider_factory = provider_factory

    def generate_planning(
        self,
        report_workflow_id: str,
        *,
        tenant_id: str,
        request_id: str,
    ) -> ReportWorkflowRecord:
        rec = self._require_record(report_workflow_id, tenant_id=tenant_id)
        provider = self._provider_factory()
        prompt = self._build_planning_prompt(rec)
        warnings: list[str] = []
        try:
            raw = provider.generate_raw(prompt, request_id=request_id, max_output_tokens=3500)
            data = json.loads(_clean_json_text(raw))
        except Exception as exc:
            logger.warning("report planning provider output fallback: %s", exc)
            data = {}
            warnings.append(f"planning_json_fallback:{exc.__class__.__name__}")
        planning = self._planning_from_provider_data(data, rec)
        return self.store.save_planning(
            report_workflow_id,
            planning,
            tenant_id=tenant_id,
            quality_warnings=warnings,
        )

    def generate_slides(
        self,
        report_workflow_id: str,
        *,
        tenant_id: str,
        request_id: str,
    ) -> ReportWorkflowRecord:
        rec = self._require_record(report_workflow_id, tenant_id=tenant_id)
        if rec.planning is None or rec.planning.status != "approved":
            raise ValueError("기획안 승인 후 장표를 생성할 수 있습니다.")
        provider = self._provider_factory()
        prompt = self._build_slides_prompt(rec)
        warnings: list[str] = []
        try:
            raw = provider.generate_raw(prompt, request_id=request_id, max_output_tokens=4500)
            data = json.loads(_clean_json_text(raw))
        except Exception as exc:
            logger.warning("report slides provider output fallback: %s", exc)
            data = {}
            warnings.append(f"slides_json_fallback:{exc.__class__.__name__}")
        slides = self._slides_from_provider_data(data, rec)
        return self.store.save_slides(
            report_workflow_id,
            slides,
            tenant_id=tenant_id,
            quality_warnings=warnings,
        )

    def build_pptx_export(self, report_workflow_id: str, *, tenant_id: str) -> bytes:
        rec = self._require_record(report_workflow_id, tenant_id=tenant_id)
        if not rec.slides:
            raise ValueError("PPTX로 내보낼 장표가 없습니다.")
        slide_outline = []
        for slide in sorted(rec.slides, key=lambda item: item.page):
            slide_outline.append({
                "page": slide.page,
                "title": slide.title,
                "key_content": slide.body,
                "message": slide.body,
                "visual": slide.visual_spec,
                "layout": slide.visual_spec,
                "design_tip": slide.speaker_note,
                "evidence": slide.source_refs,
            })
        slide_data = {
            "presentation_goal": rec.goal,
            "slide_outline": slide_outline,
        }
        return build_pptx(slide_data, title=rec.title, include_outline_overview=True)

    def _require_record(self, report_workflow_id: str, *, tenant_id: str) -> ReportWorkflowRecord:
        rec = self.store.get(report_workflow_id, tenant_id=tenant_id)
        if rec is None:
            raise KeyError(f"보고서 워크플로우를 찾을 수 없습니다: {report_workflow_id}")
        return rec

    def _build_planning_prompt(self, rec: ReportWorkflowRecord) -> str:
        return f"""
You are DecisionDoc AI report workflow planner.
Return ONLY valid JSON for a staged Korean business report planning artifact.

JSON shape:
{{
  "objective": "보고서 목적",
  "audience": "대상 독자",
  "executive_message": "핵심 메시지",
  "table_of_contents": ["..."],
  "slide_plans": [
    {{
      "slide_id": "slide-001",
      "page": 1,
      "title": "장표 제목",
      "purpose": "장표 목적",
      "key_message": "핵심 주장",
      "layout": "장표 레이아웃 설명",
      "visual_direction": "시각화 방향",
      "required_evidence": ["필요 근거"]
    }}
  ],
  "open_questions": ["..."],
  "risk_notes": ["..."]
}}

Report:
- title: {rec.title}
- goal: {rec.goal}
- client: {rec.client}
- report_type: {rec.report_type}
- audience: {rec.audience}
- slide_count: {rec.slide_count}
- attachments_context: {rec.attachments_context[:4000]}
- source_refs: {", ".join(rec.source_refs)}

Create exactly {rec.slide_count} slide_plans unless the input clearly requires fewer.
""".strip()

    def _build_slides_prompt(self, rec: ReportWorkflowRecord) -> str:
        planning = asdict(rec.planning) if rec.planning else {}
        return f"""
You are DecisionDoc AI slide draft generator.
Return ONLY valid JSON for Korean presentation slide drafts.

JSON shape:
{{
  "slides": [
    {{
      "slide_id": "slide-001",
      "page": 1,
      "title": "장표 제목",
      "body": "장표 본문 핵심 bullet 또는 요약",
      "visual_spec": "도표/이미지/레이아웃 지시",
      "speaker_note": "PM 설명용 발표 노트",
      "source_refs": ["근거 자료"]
    }}
  ]
}}

Report title: {rec.title}
Report goal: {rec.goal}
Approved planning snapshot:
{json.dumps(planning, ensure_ascii=False)}
""".strip()

    def _planning_from_provider_data(self, data: Any, rec: ReportWorkflowRecord) -> PlanningVersion:
        if not isinstance(data, dict):
            data = {}
        raw_slide_plans = data.get("slide_plans")
        if raw_slide_plans is None:
            raw_slide_plans = data.get("ppt_slides")
        slide_plans = self._normalize_slide_plans(raw_slide_plans, rec)
        if not slide_plans:
            slide_plans = self._fallback_slide_plans(rec)
        toc = _as_list(data.get("table_of_contents"))
        if not toc:
            toc = [plan.title for plan in slide_plans]
        return PlanningVersion(
            plan_id=str(uuid.uuid4()),
            version=0,
            status="draft",
            objective=str(data.get("objective") or rec.goal or rec.title),
            audience=str(data.get("audience") or rec.audience or "PM/대표/의사결정권자"),
            executive_message=str(data.get("executive_message") or f"{rec.title}의 핵심 의사결정 메시지를 한 흐름으로 정리합니다."),
            table_of_contents=[str(item) for item in toc],
            slide_plans=slide_plans,
            open_questions=[str(item) for item in _as_list(data.get("open_questions"))],
            risk_notes=[str(item) for item in _as_list(data.get("risk_notes"))],
            created_by="ai",
            created_at=_now_iso(),
        )

    def _normalize_slide_plans(self, raw: Any, rec: ReportWorkflowRecord) -> list[SlidePlan]:
        plans: list[SlidePlan] = []
        for idx, item in enumerate(_as_list(raw), start=1):
            if not isinstance(item, dict):
                continue
            page = int(item.get("page") or idx)
            title = str(item.get("title") or f"{page}. 장표").strip()
            plans.append(SlidePlan(
                slide_id=_safe_slide_id(item.get("slide_id"), page),
                page=page,
                title=title,
                purpose=str(item.get("purpose") or item.get("key_content") or "보고서 핵심 내용을 설명합니다."),
                key_message=str(item.get("key_message") or item.get("key_content") or title),
                layout=str(item.get("layout") or item.get("design_tip") or "상단 핵심 메시지와 하단 근거/시각자료 배치"),
                visual_direction=str(item.get("visual_direction") or item.get("visual") or "핵심 흐름을 도식화"),
                required_evidence=[str(value) for value in _as_list(item.get("required_evidence") or item.get("evidence"))],
            ))
        return plans[: max(1, min(rec.slide_count, 40))]

    def _fallback_slide_plans(self, rec: ReportWorkflowRecord) -> list[SlidePlan]:
        titles = ["표지 및 핵심 메시지", "현황 및 문제 정의", "제안 방향", "실행 계획", "기대 효과", "승인 요청"]
        if rec.slide_count > len(titles):
            titles.extend([f"세부 장표 {idx}" for idx in range(len(titles) + 1, rec.slide_count + 1)])
        plans = []
        for idx, title in enumerate(titles[:rec.slide_count], start=1):
            plans.append(SlidePlan(
                slide_id=f"slide-{idx:03d}",
                page=idx,
                title=title,
                purpose=f"{rec.title} 보고서의 {title} 내용을 정리합니다.",
                key_message=rec.goal or title,
                layout="상단 핵심 메시지, 본문 근거, 우측 시각자료",
                visual_direction="요약 카드와 흐름도 중심",
                required_evidence=rec.source_refs[:3],
            ))
        return plans

    def _slides_from_provider_data(self, data: Any, rec: ReportWorkflowRecord) -> list[SlideDraft]:
        if not isinstance(data, dict):
            data = {}
        raw_slides = data.get("slides")
        if raw_slides is None:
            raw_slides = data.get("ppt_slides")
        slides: list[SlideDraft] = []
        for idx, item in enumerate(_as_list(raw_slides), start=1):
            if not isinstance(item, dict):
                continue
            page = int(item.get("page") or idx)
            slide_id = _safe_slide_id(item.get("slide_id"), page)
            title = str(item.get("title") or f"{page}. 장표")
            body = str(item.get("body") or item.get("key_content") or "")
            slides.append(SlideDraft(
                slide_id=slide_id,
                page=page,
                title=title,
                body=body or f"{title}: {rec.goal or rec.title}",
                visual_spec=str(item.get("visual_spec") or item.get("visual") or item.get("layout") or "핵심 메시지를 도식화"),
                speaker_note=str(item.get("speaker_note") or item.get("notes") or f"{title}의 의사결정 포인트를 설명합니다."),
                source_refs=[str(value) for value in _as_list(item.get("source_refs") or item.get("evidence") or rec.source_refs)],
            ))
        if slides:
            return sorted(slides, key=lambda item: item.page)[: max(1, min(rec.slide_count, 40))]
        return self._fallback_slides(rec)

    def _fallback_slides(self, rec: ReportWorkflowRecord) -> list[SlideDraft]:
        planning = rec.planning
        plans = planning.slide_plans if planning else self._fallback_slide_plans(rec)
        slides: list[SlideDraft] = []
        for plan in plans:
            slides.append(SlideDraft(
                slide_id=plan.slide_id,
                page=plan.page,
                title=plan.title,
                body=f"{plan.key_message}\n\n- 목적: {plan.purpose}\n- 근거: {', '.join(plan.required_evidence[:3]) or '추가 근거 확인 필요'}",
                visual_spec=plan.visual_direction or plan.layout,
                speaker_note=f"{plan.title}에서는 {plan.purpose}를 중심으로 설명합니다.",
                source_refs=plan.required_evidence or rec.source_refs,
            ))
        return slides
