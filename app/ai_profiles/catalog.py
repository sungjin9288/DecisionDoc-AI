"""Built-in AI role profiles and bundle access helpers."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from fastapi import HTTPException, Request


@dataclass(frozen=True)
class AiProfile:
    key: str
    label: str
    job_title_hint: str
    description: str
    bundle_ids: tuple[str, ...]

    def to_dict(self) -> dict:
        return {
            "key": self.key,
            "label": self.label,
            "job_title_hint": self.job_title_hint,
            "description": self.description,
            "bundle_ids": list(self.bundle_ids),
        }


AI_PROFILE_ORDER: tuple[str, ...] = ("proposal_bd", "delivery_pm", "executive")

AI_PROFILE_CATALOG: dict[str, AiProfile] = {
    "proposal_bd": AiProfile(
        key="proposal_bd",
        label="제안/영업 AI",
        job_title_hint="영업 / BD / 제안 리드",
        description="공고 탐색, 기회 선별, 제안/RFP handoff 중심 역할",
        bundle_ids=(
            "proposal_kr",
            "rfp_analysis_kr",
            "marketing_plan_kr",
            "investment_pitch_kr",
            "feasibility_report_kr",
            "bid_decision_kr",
        ),
    ),
    "delivery_pm": AiProfile(
        key="delivery_pm",
        label="PM AI",
        job_title_hint="PM / Delivery Lead",
        description="수행 적합도, readiness, 계획/보고 문서 중심 역할",
        bundle_ids=(
            "meeting_minutes_kr",
            "project_report_kr",
            "performance_plan_kr",
            "interim_report_kr",
            "completion_report_kr",
            "task_order_kr",
            "okr_plan_kr",
            "prd_kr",
            "contract_kr",
        ),
    ),
    "executive": AiProfile(
        key="executive",
        label="최종 승인 AI",
        job_title_hint="최종 승인권자 / 임원 / 이사진",
        description="최종 의사결정, 승인, executive summary 중심 역할",
        bundle_ids=(
            "tech_decision",
            "bid_decision_kr",
            "presentation_kr",
            "business_plan_kr",
            "feasibility_report_kr",
        ),
    ),
}


def normalize_ai_profile_keys(values: Iterable[str] | None) -> list[str]:
    if not values:
        return []
    seen: set[str] = set()
    normalized: list[str] = []
    for raw in values:
        key = str(raw or "").strip()
        if not key:
            continue
        if key not in AI_PROFILE_CATALOG:
            raise ValueError(f"알 수 없는 AI profile입니다: {key}")
        if key in seen:
            continue
        seen.add(key)
        normalized.append(key)
    return normalized


def default_ai_profiles_for_role(role: str) -> list[str]:
    return list(AI_PROFILE_ORDER) if str(role or "").strip() == "admin" else []


def list_ai_profiles(keys: Iterable[str] | None = None) -> list[dict]:
    normalized = (
        list(AI_PROFILE_ORDER)
        if keys is None
        else [key for key in AI_PROFILE_ORDER if key in set(normalize_ai_profile_keys(keys))]
    )
    return [AI_PROFILE_CATALOG[key].to_dict() for key in normalized]


def bundle_ids_for_ai_profiles(keys: Iterable[str] | None) -> set[str]:
    bundle_ids: set[str] = set()
    for key in normalize_ai_profile_keys(keys):
        bundle_ids.update(AI_PROFILE_CATALOG[key].bundle_ids)
    return bundle_ids


def effective_bundle_ids_for_request(request: Request) -> set[str]:
    from app.bundle_catalog.registry import BUNDLE_REGISTRY
    from app.storage.user_store import get_user_store

    allowed = set(BUNDLE_REGISTRY.keys())
    tenant = getattr(request.state, "tenant", None)
    if tenant and tenant.allowed_bundles:
        allowed &= set(tenant.allowed_bundles)

    user_id = getattr(request.state, "user_id", None)
    user_role = getattr(request.state, "user_role", None)
    if not user_id or user_role == "admin":
        return allowed

    tenant_id = getattr(request.state, "tenant_id", "system") or "system"
    user = get_user_store(tenant_id).get_by_id(user_id)
    if not user:
        return set()

    assigned = bundle_ids_for_ai_profiles(getattr(user, "assigned_ai_profiles", []))
    if not assigned:
        return set()
    return allowed & assigned


def ensure_bundle_access(request: Request, bundle_id: str) -> None:
    if bundle_id not in effective_bundle_ids_for_request(request):
        raise HTTPException(
            status_code=403,
            detail="현재 계정에 할당되지 않은 AI입니다. 관리자에게 업무 AI 배정을 요청하세요.",
        )
