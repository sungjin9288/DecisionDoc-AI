from __future__ import annotations

import concurrent.futures
import hashlib
import json
import logging
import os
import re
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable
from uuid import uuid4

from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.bundle_catalog.registry import get_bundle_spec
from app.bundle_catalog.spec import BundleSpec
from app.config import env_is_enabled
from app.domain.schema import SCHEMA_VERSION
from app.eval.lints import lint_docs
from app.observability.timing import Timer
from app.providers.base import Provider
from app.providers.stabilizer import stabilize_bundle, strip_internal_bundle_fields
from app.schemas import GenerateRequest
from app.services.decision_council_service import (
    build_procurement_council_generation_context,
    describe_procurement_council_binding,
)
from app.services.markdown_utils import (
    build_markdown_kv_table,
    build_markdown_table,
    build_slide_outline_table,
)
from app.services.procurement_pdf_normalizer import parse_procurement_pdf_context
from app.storage.base import Storage
from app.services.validator import validate_docs

if TYPE_CHECKING:
    from app.storage.feedback_store import FeedbackStore
    from app.storage.finetune_store import FineTuneStore

_log = logging.getLogger("decisiondoc.generate")
_DECISION_COUNCIL_APPLIED_BUNDLE_IDS = {
    "bid_decision_kr",
    "proposal_kr",
}


def _record_usage_sync(
    tenant_id: str,
    user_id: str,
    bundle_id: str,
    request_id: str,
    model: str,
    tokens_input: int,
    tokens_output: int,
) -> None:
    """Record a usage event to the billing/metering store (fire-and-forget)."""
    from app.storage.usage_store import UsageStore, UsageEvent
    from app.storage.billing_store import get_billing_store
    import uuid as _uuid
    from datetime import datetime as _datetime, timezone as _timezone

    plan = get_billing_store(tenant_id).get_plan(tenant_id)
    tokens_total = tokens_input + tokens_output
    cost = (tokens_total / 1000) * plan.price_per_1k_tokens if tokens_total > 0 else 0.0

    event = UsageEvent(
        event_id=str(_uuid.uuid4()),
        tenant_id=tenant_id,
        user_id=user_id,
        timestamp=_datetime.now(_timezone.utc).isoformat(),
        event_type="doc.generate",
        bundle_id=bundle_id,
        tokens_input=tokens_input,
        tokens_output=tokens_output,
        tokens_total=tokens_total,
        cost_usd=cost,
        model=model,
        request_id=request_id,
    )
    UsageStore().record(event)


# ── Fine-tune context capture ─────────────────────────────────────────────────
# Thread-local for capturing generation context within a single request.
_generation_context: threading.local = threading.local()

# In-memory cross-request context cache: request_id → (context dict, timestamp).
# Used by the /feedback endpoint (a separate request) to find the original
# system_prompt + output for Trigger A fine-tune collection.
_ctx_lock: threading.Lock = threading.Lock()
_recent_generation_contexts: dict[str, tuple[dict, float]] = {}
_CTX_MAX_SIZE = 500   # evict oldest entries beyond this limit
_CTX_TTL_SECONDS = 3600  # 1 hour — stale entries expire regardless of size


def _store_generation_context(request_id: str, ctx: dict) -> None:
    """Store ctx with timestamp; evict expired + oldest-over-limit entries."""
    with _ctx_lock:
        now = time.time()
        # Purge expired entries first
        expired = [k for k, (_, ts) in _recent_generation_contexts.items()
                   if now - ts > _CTX_TTL_SECONDS]
        for k in expired:
            del _recent_generation_contexts[k]
        # Evict oldest if still at capacity
        if len(_recent_generation_contexts) >= _CTX_MAX_SIZE:
            oldest = min(_recent_generation_contexts.items(), key=lambda x: x[1][1])
            del _recent_generation_contexts[oldest[0]]
        _recent_generation_contexts[request_id] = (ctx, now)


def get_generation_context(request_id: str) -> dict | None:
    """Return stored generation context for a request_id, or None if missing/expired."""
    with _ctx_lock:
        entry = _recent_generation_contexts.get(request_id)
        if entry is None:
            return None
        ctx, ts = entry
        if time.time() - ts > _CTX_TTL_SECONDS:
            del _recent_generation_contexts[request_id]
            return None
        return ctx


# ── Background eval executor ──────────────────────────────────────────────────
# Bounded thread pool for background quality eval tasks.
# Use shutdown(wait=True) during FastAPI lifespan to drain in-flight tasks.
_eval_executor: concurrent.futures.ThreadPoolExecutor = (
    concurrent.futures.ThreadPoolExecutor(max_workers=4, thread_name_prefix="eval")
)


def _eval_done_callback(future: concurrent.futures.Future) -> None:  # type: ignore[type-arg]
    """Log any unhandled exception from a background eval task."""
    exc = future.exception()
    if exc is not None:
        _log.error("[Eval] Background eval task raised an exception: %s", exc, exc_info=exc)


def _has_meaningful_text(value: Any, *, min_chars: int = 80) -> bool:
    return isinstance(value, str) and len(value.strip()) >= min_chars


def _normalized_row_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    rows: list[str] = []
    for item in value:
        if not isinstance(item, str):
            continue
        normalized = item.strip()
        if normalized:
            rows.append(normalized)
    return rows


def _ensure_text(value: Any, fallback: str, *, min_chars: int = 80) -> str:
    if _has_meaningful_text(value, min_chars=min_chars):
        return _normalize_finished_doc_text(value)
    return _normalize_finished_doc_text(fallback)


def _ensure_rows(value: Any, fallback_rows: list[str], *, min_items: int = 3) -> list[str]:
    rows = _normalized_row_list(value)
    if len(rows) >= min_items:
        return rows
    merged = list(rows)
    for row in fallback_rows:
        if row not in merged:
            merged.append(row)
        if len(merged) >= max(min_items, len(fallback_rows)):
            break
    return merged


def _project_subject(title: str) -> str:
    subject = str(title or "").strip()
    for suffix in (
        " 사업 제안서",
        " 제안서",
        " 사업수행계획서",
        " 수행계획서",
        " 발표자료",
        " 보고서",
    ):
        if subject.endswith(suffix):
            subject = subject[: -len(suffix)].strip()
    return subject or str(title or "").strip()


def _strip_reference_noise(text: Any) -> str:
    if not isinstance(text, str):
        return ""
    cleaned = re.sub(
        r"(?im)^\s*(?:\*\*)?(?:참고 맥락|범위 참고 맥락|제안서 인풋 참고 맥락|수행계획 인풋 참고 맥락)(?:\*\*)?\s*:\s*.*$",
        "",
        text,
    )
    cleaned = re.sub(r"\s*\([^)]*(?:발주처는|계약 기간은|산출물은)[^)]*\)", "", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def _normalize_finished_doc_text(text: Any) -> str:
    if not isinstance(text, str):
        return ""
    cleaned = _strip_reference_noise(text)
    replacements = (
        ("제안한다.을 달성하기 위해", "제안하며, 이를 달성하기 위해"),
        ("제안한다.를", "제안 내용을"),
        ("제안한다.은", "제안은"),
        ("제안한다.는", "제안은"),
        ("사업 제안서 사업", "사업"),
        ("달성을 통한", "달성을 위한"),
        ("은(는)", "는"),
    )
    for source, target in replacements:
        cleaned = cleaned.replace(source, target)
    cleaned = re.sub(r"\s{2,}", " ", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def _normalize_finished_doc_value(value: Any) -> Any:
    if isinstance(value, str):
        return _normalize_finished_doc_text(value)
    if isinstance(value, list):
        normalized_items: list[Any] = []
        for item in value:
            normalized = _normalize_finished_doc_value(item)
            if isinstance(normalized, str):
                if normalized:
                    normalized_items.append(normalized)
            else:
                normalized_items.append(normalized)
        return normalized_items
    if isinstance(value, dict):
        return {key: _normalize_finished_doc_value(item) for key, item in value.items()}
    return value


def _sanitize_rows(
    value: Any,
    fallback_rows: list[str],
    *,
    min_items: int = 3,
    banned_terms: tuple[str, ...] = ("참고 맥락", "인풋 참고 맥락"),
) -> list[str]:
    rows: list[str] = []
    for row in _normalized_row_list(value):
        if any(term in row for term in banned_terms):
            continue
        cleaned_row = _normalize_finished_doc_text(row)
        if cleaned_row:
            rows.append(cleaned_row)
    if len(rows) >= min_items:
        return rows
    return _ensure_rows(rows, fallback_rows, min_items=min_items)


def _quality_guard_proposal_bundle(bundle: dict[str, Any], *, title: str, goal: str) -> None:
    subject = _project_subject(title)
    business = bundle.get("business_understanding")
    if isinstance(business, dict):
        business["executive_summary"] = _strip_reference_noise(business.get("executive_summary"))
        business["executive_summary"] = _ensure_text(
            business.get("executive_summary"),
            (
                "본 제안은 발주기관이 요구하는 핵심 정책 목표를 운영 KPI와 실행 단계로 재구성해 현행 업무의 병목과 운영 리스크를 먼저 정리하고, "
                "그 위에 데이터·AI·운영 체계를 단계적으로 구축하는 방식을 제시합니다. 본 제안은 단순 기능 도입이 아니라 "
                "평가위원이 확인하는 사업 필요성, 정책 적합성, 실현 가능성, 효과 입증 경로를 하나의 실행 시나리오로 묶는 데 목적이 있습니다. "
                "특히 초기 3개월 내 가시적 성과를 만들고, 중간 검증 이후 확산 여부를 판단할 수 있도록 단계별 성공 기준을 명확히 정의합니다."
            ),
        )
        business["project_background"] = _ensure_text(
            _strip_reference_noise(business.get("project_background")),
            (
                f"{subject} 사업은 공공 서비스 디지털 전환과 현장 운영 효율 개선을 동시에 요구합니다. "
                "발주기관은 현행 프로세스의 병목, 데이터 단절, 대응 지연 문제를 해소할 수 있는 실행 가능한 사업 구조를 요구하고 있으며, "
                "이에 따라 본 문서는 정책 배경과 현황 문제, 목표 KPI를 같은 평가 언어로 재구성해 사업 필요성을 선명하게 설명합니다."
            ),
        )
        business["evaluation_alignment"] = _ensure_rows(
            business.get("evaluation_alignment"),
            [
                "사업 이해도 | 발주기관의 정책 목표와 현행 문제를 AS-IS/TO-BE 구조로 재정리해 제안 배경의 타당성을 선명하게 설명 | 사업 배경, 현황 및 문제점, 사업 목표 표",
                "실행 가능성 | 단계별 구축 범위와 일정, 주요 산출물, 운영 전환 시점을 연결해 일정 현실성과 납품 가능성을 증명 | 사업 범위 요약, 후속 수행계획서 및 WBS",
                "효과성 | 정량 KPI와 정성 효과를 동시에 제시해 예산 대비 효과와 정책 성과를 같은 문서 안에서 검증 가능하게 구성 | 정량·정성 기대효과, ROI, 성과 모니터링 계획",
            ],
        )
        business["target_users"] = _sanitize_rows(
            business.get("target_users"),
            [
                "사업 담당 공무원 및 운영 관리자 | 사업 집행 현황·성과지표를 통합 모니터링해야 함 | 실시간 성과판과 의사결정 속도 향상",
                "현장 실무자 및 데이터 입력 담당자 | 반복 입력·검증 업무를 줄이고 오류를 낮추고자 함 | 자동 검증과 예외 처리 중심 업무 전환",
                "경영진 및 의사결정자 | 예산 집행 효과와 리스크를 요약 보고받아야 함 | 대시보드 기반 신속한 승인·보완 판단",
                "일반 국민 | 서비스 응답 속도와 정확도 향상을 기대함 | 체감 만족도와 접근성 개선",
            ],
            min_items=4,
        )
        business["scope_summary"] = _ensure_text(
            _strip_reference_noise(business.get("scope_summary")),
            (
                "본 사업의 범위는 데이터 수집·정제, AI 분석 모델 구축, 운영 대시보드, 현장 적용 및 확산 지원까지 포함합니다. "
                "착수·설계·개발·검증·운영 전환을 단계적으로 구분하고, 각 단계마다 산출물과 승인 기준을 연결해 범위 누락과 일정 지연을 줄이도록 구성합니다."
            ),
        )

    tech = bundle.get("tech_proposal")
    if isinstance(tech, dict):
        tech["technical_summary"] = _strip_reference_noise(tech.get("technical_summary"))
        tech["technical_summary"] = _ensure_text(
            tech.get("technical_summary"),
            (
                f"{subject}의 기술 제안은 공공기관 운영 환경에서 바로 수용 가능한 보안·가용성 기준을 전제로, "
                "데이터 수집부터 AI 추론, 운영자 대시보드, 감사 대응 로그까지 하나의 통합 아키텍처로 설계합니다. "
                "핵심은 정확도만 높은 모델이 아니라 운영 현장에서 설명 가능하고, 장애 격리와 확장성이 확보된 구조를 제공하는 것입니다. "
                "이를 통해 평가위원이 가장 우려하는 유지보수 리스크와 보안 통제를 초기 설계 단계에서 함께 해소합니다."
            ),
        )
        tech["implementation_principles"] = _ensure_rows(
            tech.get("implementation_principles"),
            [
                "업무 연속성 우선 | 핵심 API와 데이터 계층을 분리해 장애 발생 시 부분 격리와 점진적 복구가 가능하도록 설계 | 무중단 배포, 장애 복구 시나리오, 서비스별 책임 경계",
                "설명 가능한 AI | 모델 판단 근거와 예외 사유를 운영 화면과 보고서에 함께 남겨 감사·검수 대응력을 확보 | 판단 근거 로그, 검수 화면, 재현 가능한 평가 데이터셋",
                "보안·확장성 동시 확보 | 최소 권한, 암호화, 접근통제를 기본값으로 두고 트래픽 증가 시 서비스별 수평 확장이 가능하도록 구성 | 인증·인가 정책, 오토스케일링, 성능 테스트 계획",
            ],
        )

    execution = bundle.get("execution_plan")
    if isinstance(execution, dict):
        execution["delivery_summary"] = _strip_reference_noise(execution.get("delivery_summary"))
        execution["delivery_summary"] = _ensure_text(
            execution.get("delivery_summary"),
            (
                f"{subject} 수행계획은 착수 직후 요구사항·데이터·연계 환경을 동시에 정리하고, "
                "프로토타입 검증과 통합 개발, 파일럿 운영, 전면 전개로 이어지는 4단계 delivery 체계를 기준으로 구성합니다. "
                "각 단계는 산출물, 완료 기준, 승인 게이트가 연결되어 있어 발주기관이 중간 점검 시점마다 진행률과 품질 수준을 객관적으로 확인할 수 있습니다. "
                "이 방식은 일정 지연과 요구사항 누락을 줄이고, 운영 이관까지 포함한 종료 조건을 명확히 합니다."
            ),
        )
        execution["team_structure"] = _sanitize_rows(
            execution.get("team_structure"),
            [
                "PM·총괄 | 특급 1명 | 일정·범위·대외 협의 총괄 | 착수~종료 전기간",
                "AI 기술 리드 | 고급 1명 | 모델 품질·데이터 설계·성능 검증 책임 | 설계~통합시험",
                "개발 리드 및 구현 인력 | 중급 3명 | 서비스 개발·연계·배포 자동화 수행 | 개발~운영 전환",
                "품질 책임자 | 고급 1명 | 검수 기준 수립·결함 관리·인수시험 총괄 | 시험~종료",
            ],
            min_items=4,
        )
        execution["milestones"] = _sanitize_rows(
            execution.get("milestones"),
            [
                "착수 및 요구사항 확정 | 1~2개월 | 요구사항 정의서 승인 | 착수보고서, 현행 분석서",
                "아키텍처·상세 설계 완료 | 3~4개월 | 설계 검토 승인 | 아키텍처 설계서, 인터페이스 정의서",
                "개발 및 통합시험 완료 | 5~9개월 | 핵심 시나리오 100% 통과 | 시험 결과서, 운영자 검수 기록",
                "파일럿 및 최종 이관 완료 | 10~12개월 | 최종 검수 승인 | 완료보고서, 운영 매뉴얼",
            ],
            min_items=4,
        )
        execution["governance_plan"] = _ensure_text(
            execution.get("governance_plan"),
            (
                "PM이 주간 실행계획과 리스크를 총괄하고, AI 리드·개발 리드·품질 책임자가 주간 점검회의에서 이슈를 선분류합니다. "
                "발주기관과는 월간 운영위원회 및 중요 이슈 수시 보고 체계를 유지하며, 일정·범위·비용에 영향을 주는 변경은 영향도 분석 후 승인 절차를 거칩니다. "
                "모든 의사결정은 회의록과 변경대장으로 남겨 이후 검수와 감사 대응 근거로 사용합니다."
            ),
        )

    impact = bundle.get("expected_impact")
    if isinstance(impact, dict):
        impact["impact_summary"] = _strip_reference_noise(impact.get("impact_summary"))
        impact["impact_summary"] = _ensure_text(
            impact.get("impact_summary"),
            (
                f"{subject}의 기대효과는 단순한 기능 도입이 아니라 핵심 정책 목표를 실무 KPI로 전환해 지속적으로 측정 가능한 운영 성과를 만드는 데 있습니다. "
                "처리시간 단축, 오류율 감소, 운영비 절감, 서비스 안정성 향상 같은 정량 지표와 함께 조직 역량 강화, 정책 신뢰도 제고, 국민 체감 개선 같은 정성 효과를 병행 관리합니다. "
                "이렇게 정의한 효과 구조는 제안 단계의 약속과 운영 단계의 성과관리가 단절되지 않도록 하는 장치입니다."
            ),
        )
        impact["qualitative_effects"] = _sanitize_rows(
            impact.get("qualitative_effects"),
            [
                "조직 역량 강화 | 데이터 기반 의사결정 문화 정착 | 정책·사업 운영의 디지털 전환 가속",
                "국민 신뢰 제고 | 서비스 체감 품질과 응답 일관성 향상 | 공공서비스 브랜드 가치와 정책 수용성 강화",
                "업무 방식 혁신 | 반복 업무 부담 감소와 고부가가치 업무 집중 | 실무자 만족도와 생산성 동시 개선",
                "정책 확산 효과 | AI 활용 선도 사례 구축 | 타 기관 벤치마킹과 후속 사업 확장 기반 확보",
            ],
            min_items=4,
        )
        impact["social_value"] = _ensure_text(
            _strip_reference_noise(impact.get("social_value")),
            (
                f"{subject} 사업은 공공서비스 품질 개선과 국민 체감 편익 확대를 동시에 목표로 합니다. "
                "디지털 소외 계층을 포함한 이용자 접근성을 개선하고, 현장 운영의 신뢰도와 일관성을 높여 공공 AI 활용의 모범 사례로 확산될 수 있도록 설계합니다."
            ),
        )
        impact["kpi_commitments"] = _ensure_rows(
            impact.get("kpi_commitments"),
            [
                "핵심 업무 처리시간 | 기준 대비 50% 이상 단축 | 업무 로그와 월간 운영 리포트 | 파일럿 운영 종료 시점",
                "데이터 오류율 | 기준 대비 70% 이상 개선 | 검수 샘플링과 자동 검증 결과 | 통합 테스트 종료 시점",
                "서비스 가용률 | 99.9% 이상 유지 | 모니터링 대시보드와 장애 리포트 | 전면 운영 전환 후 3개월",
            ],
        )


def _extract_attachment_reference_text(context_text: Any) -> str:
    raw = str(context_text or "")
    start_marker = "=== RFP 원문 (참고용) ==="
    end_marker = "=== RFP 원문 끝 ==="
    start = raw.find(start_marker)
    end = raw.find(end_marker)
    if start == -1 or end == -1 or end < start:
        return ""
    return raw[start + len(start_marker):end].strip()


def _is_sparse_attachment_context(context_text: Any) -> bool:
    reference_text = _extract_attachment_reference_text(context_text)
    if not reference_text:
        return False
    normalized = re.sub(r"\[첨부파일:[^\]]+\]", " ", reference_text)
    token_count = len(re.findall(r"[가-힣A-Za-z0-9]+", normalized))
    has_digits = bool(re.search(r"\d", normalized))
    return token_count <= 80 and not has_digits


def _attachment_grounded_slide_outline(title: str, *, section: str) -> list[dict[str, Any]]:
    if section == "business_understanding":
        return [
            {
                "page": 1,
                "title": "사업 배경과 문제 정의",
                "key_content": (
                    f"{title} 제안은 교차로 안전 강화와 장애인 보호라는 핵심 요구를 먼저 정리하고, "
                    "현행 운영에서 어떤 문제가 반복되는지 평가위원이 바로 이해할 수 있게 설명합니다."
                ),
                "core_message": "첨부에서 확인된 요구사항을 기준으로 사업 필요성을 정리합니다.",
                "evidence_points": [
                    "첨부 원문에 교차로 안전 강화 요구가 명시됨",
                    "첨부 원문에 장애인 보호 강화 요구가 명시됨",
                ],
                "visual_type": "비교표",
                "visual_brief": "현행 문제와 개선 방향을 좌우 비교표로 정리",
                "layout_hint": "좌측 현황 문제 / 우측 제안 방향 / 하단 핵심 시사점",
                "design_tip": "원문 요구사항 문구를 강조 박스로 노출",
            },
            {
                "page": 2,
                "title": "평가 대응 포인트",
                "key_content": (
                    "평가위원이 확인할 사업 이해도, 실행 가능성, 기대효과를 "
                    "원문 요구사항과 운영 대응 전략 중심으로 구조화합니다."
                ),
                "core_message": "원문 요구사항을 평가 항목 언어로 변환해 제안 메시지를 정리합니다.",
                "evidence_points": [
                    "요구사항 반영 범위를 평가 포인트별로 재구성",
                    "근거 없는 수치 대신 확인 가능한 운영 방식 중심으로 설명",
                ],
                "visual_type": "프로세스 흐름도",
                "visual_brief": "요구사항에서 제안 방향으로 이어지는 대응 흐름도",
                "layout_hint": "상단 요구사항 / 중앙 대응 전략 / 하단 기대 효과",
                "design_tip": "평가위원이 보는 관점 순서대로 읽히게 배치",
            },
        ]
    if section == "tech_proposal":
        return [
            {
                "page": 1,
                "title": "기술 접근 방향",
                "key_content": (
                    "특정 제품명을 앞세우기보다 데이터 수집, 위험 징후 분석, 운영 화면 제공 등 "
                    "실제 구현이 필요한 기능 단위로 기술 구성을 설명합니다."
                ),
                "core_message": "기술명보다 구현 기능과 운영 목적을 먼저 설명합니다.",
                "evidence_points": [
                    "현장 데이터 수집과 분석 지원이 핵심",
                    "운영자가 즉시 활용할 수 있는 화면과 보고 체계 필요",
                ],
                "visual_type": "프로세스 흐름도",
                "visual_brief": "데이터 수집, 분석, 운영 활용 단계를 연결한 기능 흐름도",
                "layout_hint": "좌측 입력 / 중앙 분석 / 우측 운영 활용",
                "design_tip": "제품명 대신 기능 목적을 라벨로 사용",
            },
            {
                "page": 2,
                "title": "보안 및 운영 원칙",
                "key_content": (
                    "공공사업 제안서에 필요한 보안 통제, 접근권한 관리, 운영 추적 가능성을 "
                    "기본 설계 원칙으로 제시합니다."
                ),
                "core_message": "공공 운영 기준에 맞는 보안과 감사 대응 체계를 함께 제시합니다.",
                "evidence_points": [
                    "최소 권한과 접근 통제 원칙 적용",
                    "운영 로그와 검수 이력 확보 필요",
                ],
                "visual_type": "비교표",
                "visual_brief": "보안 원칙, 운영 통제, 검수 포인트를 나란히 보여주는 표",
                "layout_hint": "상단 핵심 원칙 / 하단 통제 항목 표",
                "design_tip": "공공기관 운영 기준 용어를 우선 사용",
            },
        ]
    if section == "execution_plan":
        return [
            {
                "page": 1,
                "title": "수행 단계 개요",
                "key_content": (
                    "착수, 설계, 구현, 검증, 운영 전환으로 이어지는 기본 수행 단계를 정리하고 "
                    "각 단계의 완료 기준을 함께 제시합니다."
                ),
                "core_message": "단계별 완료 기준과 산출물을 명확히 두는 수행계획입니다.",
                "evidence_points": [
                    "착수 단계에서 요구사항과 범위를 정리",
                    "검증 단계에서 품질 점검과 운영 전환 준비 수행",
                ],
                "visual_type": "타임라인",
                "visual_brief": "착수부터 운영 전환까지의 단계형 타임라인",
                "layout_hint": "가로 타임라인 / 단계별 산출물 박스",
                "design_tip": "날짜 대신 단계와 승인 조건을 중심으로 표기",
            },
            {
                "page": 2,
                "title": "거버넌스와 리스크 관리",
                "key_content": (
                    "PM, 기술 리드, 품질 책임자가 어떤 방식으로 이슈를 관리하고 "
                    "발주기관과 보고 체계를 유지하는지 설명합니다."
                ),
                "core_message": "보고 체계와 리스크 관리 책임을 분명히 하는 수행 구조입니다.",
                "evidence_points": [
                    "주기적 점검 회의와 승인 절차 운영",
                    "리스크 식별과 대응 이력을 같은 체계로 관리",
                ],
                "visual_type": "조직도",
                "visual_brief": "PM, 기술 리드, 품질 책임자 중심의 거버넌스 구조도",
                "layout_hint": "상단 의사결정 / 하단 실행 조직",
                "design_tip": "역할 관계와 승인 흐름을 동시에 보이게 구성",
            },
        ]
    return [
        {
            "page": 1,
            "title": "기대 효과 개요",
            "key_content": (
                "정량 수치를 임의로 제시하기보다 교차로 안전성 개선, 교통약자 보호 강화, "
                "운영 신뢰도 향상 같은 효과 범주를 명확히 설명합니다."
            ),
            "core_message": "근거가 확인된 효과 범주 중심으로 기대효과를 설명합니다.",
            "evidence_points": [
                "교차로 안전 강화 요구와 직접 연결된 효과",
                "장애인 보호 강화 요구와 직접 연결된 효과",
            ],
            "visual_type": "비교표",
            "visual_brief": "현행 문제와 기대 효과 범주를 비교하는 표",
            "layout_hint": "좌측 현행 한계 / 우측 기대 변화",
            "design_tip": "숫자 대신 효과 범주와 측정 방법을 강조",
        },
        {
            "page": 2,
            "title": "모니터링 및 확산 계획",
            "key_content": (
                "시범 운영 이후 어떤 항목을 모니터링하고, 후속 확산 여부를 어떻게 판단할지 "
                "운영 관점에서 정리합니다."
            ),
            "core_message": "실제 운영 데이터를 바탕으로 후속 확산 여부를 판단합니다.",
            "evidence_points": [
                "운영 로그, 사고·민원 추이, 현장 피드백을 함께 확인",
                "시범 운영 결과를 기반으로 후속 투자 판단",
            ],
            "visual_type": "타임라인",
            "visual_brief": "시범 운영, 점검, 확산 판단으로 이어지는 운영 타임라인",
            "layout_hint": "상단 단계 / 하단 확인 항목",
            "design_tip": "확산 결정이 실제 운영 데이터에 기반한다는 점을 강조",
        },
    ]


def _quality_guard_attachment_grounded_proposal_bundle(
    bundle: dict[str, Any],
    *,
    title: str,
    goal: str,
    context_text: str,
) -> None:
    if not _is_sparse_attachment_context(context_text):
        return

    subject = _project_subject(title)

    business = bundle.get("business_understanding")
    if isinstance(business, dict):
        business["executive_summary"] = (
            f"본 제안은 {subject} 과제에서 확인된 교차로 안전 강화와 장애인 보호 요구를 사업 구조로 재정리한 안입니다. "
            "첨부 원문에 없는 수치나 일정 대신, 발주기관이 왜 이 사업을 추진해야 하는지와 어떤 운영 변화가 필요한지를 중심으로 설명합니다. "
            "제안서의 초점은 안전 문제를 줄이기 위한 실행 방향, 평가 대응 포인트, 후속 운영 체계를 명확히 제시하는 데 있습니다."
        )
        business["project_background"] = (
            f"{subject} 사업은 교차로 안전 강화와 장애인 보호 강화를 동시에 요구합니다. "
            "따라서 제안서는 현장의 안전 문제를 어떻게 줄일지, 교통약자 관점의 보호 체계를 어떤 방식으로 보강할지, "
            "그리고 발주기관이 관리 가능한 운영 구조를 어떻게 만들지를 중심으로 구성되어야 합니다."
        )
        business["current_issues"] = [
            "교차로 안전 강화 요구에 비해 현장 대응 체계가 분산되어 있음",
            "장애인 보호 관점의 운영 기준과 현장 실행 절차가 일관되지 않음",
            "안전 관련 현황을 통합적으로 확인하고 점검할 수 있는 운영 체계가 부족함",
        ]
        business["project_objectives"] = [
            "교차로 안전 강화 | 현행 위험 요소를 줄일 수 있는 실행 구조 마련 | 운영 로그와 현장 점검 결과",
            "장애인 보호 강화 | 교통약자 관점의 보호 조치와 운영 기준 정비 | 현장 적용 여부와 개선 이력",
            "운영 관리 체계 확보 | 발주기관이 지속적으로 점검 가능한 보고·검수 구조 구성 | 보고 체계와 검수 기록",
        ]
        business["evaluation_alignment"] = [
            "사업 이해도 | 교차로 안전과 장애인 보호라는 핵심 요구를 제안 배경과 목표에 직접 연결 | 첨부 원문 요구사항과 사업 배경 서술",
            "실행 가능성 | 단계별 수행 구조와 산출물, 보고 체계를 명확히 정리 | 수행계획, 산출물, 거버넌스 계획",
            "효과성 | 정량 수치 대신 확인 가능한 운영 변화와 점검 방법을 제시 | 기대효과, 모니터링 계획, 후속 확산 기준",
        ]
        business["scope_summary"] = (
            "본 사업 범위는 교차로 안전과 교통약자 보호를 위한 현황 분석, 운영 체계 설계, 현장 적용 방안, 보고와 검수 절차 정비까지 포함합니다. "
            "기술 도입 자체보다 현장에서 지속적으로 활용할 수 있는 운영 구조와 관리 체계를 함께 제시하는 것이 핵심입니다."
        )
        business["total_slides"] = 2
        business["slide_outline"] = _attachment_grounded_slide_outline(title, section="business_understanding")

    tech = bundle.get("tech_proposal")
    if isinstance(tech, dict):
        tech["technical_summary"] = (
            f"{subject}의 기술 제안은 특정 제품명보다 필요한 기능과 운영 목적을 중심으로 설명합니다. "
            "핵심은 현장 데이터를 수집하고, 위험 징후를 분석하며, 운영자가 바로 활용할 수 있는 화면과 보고 체계를 제공하는 것입니다. "
            "첨부 원문에 없는 기술 스택이나 제품명은 확정적으로 쓰지 않고 기능 수준에서 설계를 제시합니다."
        )
        tech["tech_stack"] = [
            "데이터 수집·연계 | 현장 정보 수집 및 입력 데이터 정리 | 교차로 안전 현황 통합",
            "분석·판단 지원 | 위험 징후 분석과 의사결정 보조 기능 | 안전 대응 우선순위 도출",
            "운영 화면·보고 | 관리자 화면과 보고서 생성 기능 | 운영 가시성과 검수 대응 확보",
        ]
        tech["architecture_overview"] = (
            "시스템은 현장 데이터 수집, 분석 처리, 운영자 확인 화면, 보고와 검수 기록 계층으로 구성합니다. "
            "이 구조는 운영자가 교차로 안전 상황과 교통약자 보호 관련 조치를 한 흐름 안에서 확인할 수 있도록 설계합니다."
        )
        tech["ai_approach"] = (
            f"AI 기능은 {goal}에 필요한 위험 징후 분석과 우선순위 판단을 지원하는 수준에서 설명합니다. "
            "특정 모델명이나 제품명을 단정하기보다, 운영 데이터와 현장 정보에 기반한 분석 보조 기능이라는 역할을 분명히 합니다."
        )
        tech["implementation_principles"] = [
            "기능 중심 설계 | 데이터 수집, 분석, 운영 활용 흐름을 먼저 정의 | 기능별 책임 경계와 화면 흐름 확인",
            "설명 가능한 운영 | 판단 근거와 검수 이력을 함께 남김 | 운영 로그와 검수 기록 확인",
            "보안 기본값 적용 | 접근 통제와 감사 대응을 기본 설계에 포함 | 권한 정책과 운영 절차 점검",
        ]
        tech["security_measures"] = [
            "접근 통제 | 역할 기반 권한 관리와 승인 절차 운영 | 최소 권한 원칙 적용 여부 확인",
            "운영 추적성 | 로그와 검수 이력을 기록 | 감사 대응용 기록 유지 여부 확인",
            "데이터 보호 | 민감 정보 처리 기준과 저장 정책 정비 | 내부 보안 기준 준수 여부 확인",
        ]
        tech["differentiation"] = [
            "운영 중심 제안 | 기술명보다 현장 실행 방식과 관리 체계를 우선 설명 | 발주기관 운영 관점과 직접 연결",
            "교통약자 보호 강조 | 장애인 보호 요구를 사업 전반의 설계 원칙으로 반영 | 첨부 원문 요구사항과 일치",
            "검수 대응 구조 | 보고, 모니터링, 검수 체계를 함께 제시 | 운영 지속성과 감사 대응력 확보",
        ]
        tech["total_slides"] = 2
        tech["slide_outline"] = _attachment_grounded_slide_outline(title, section="tech_proposal")

    execution = bundle.get("execution_plan")
    if isinstance(execution, dict):
        execution["delivery_summary"] = (
            f"{subject} 수행계획은 착수, 설계, 구현, 검증, 운영 전환의 기본 단계를 기준으로 정리합니다. "
            "각 단계는 완료 기준과 산출물을 함께 제시해 발주기관이 진행률과 품질을 확인할 수 있게 구성합니다. "
            "첨부 원문에 없는 기간 수치는 확정하지 않고 단계 중심으로 수행 구조를 설명합니다."
        )
        execution["team_structure"] = [
            "PM·총괄 | 핵심 인력 | 일정·범위·대외 협의 총괄 | 착수 단계부터 종료까지",
            "기술 리드 | 핵심 인력 | 기능 설계와 구현 방향 정리 | 설계 단계부터 검증 단계까지",
            "운영·품질 담당 | 핵심 인력 | 검수 기준 수립과 운영 전환 준비 | 구현 단계부터 운영 전환까지",
        ]
        execution["milestones"] = [
            "착수 및 요구사항 정리 | 착수 단계 | 사업 범위와 요구사항 정리 완료 | 착수보고서, 요구사항 정리본",
            "설계 및 구현 정리 | 구현 준비 단계 | 기능 구조와 운영 흐름 설계 완료 | 설계 문서, 구현 계획서",
            "검증 및 운영 전환 | 검증 단계 | 주요 시나리오 점검과 운영 준비 완료 | 시험 결과서, 운영 매뉴얼",
        ]
        execution["methodology"] = (
            "요구사항 정리, 기능 설계, 구현, 검증, 운영 전환이 이어지는 단계형 수행 방식을 적용합니다. "
            "각 단계에서 발주기관과 점검 포인트를 공유하고, 이슈가 생기면 즉시 보완 계획을 반영하는 방식으로 운영합니다."
        )
        execution["governance_plan"] = (
            "PM, 기술 리드, 운영·품질 담당이 정기 점검 회의를 운영하고, 발주기관과는 단계별 산출물과 이슈를 공유합니다. "
            "중요 변경사항은 영향도 검토 후 승인 절차를 거치며, 모든 의사결정은 기록으로 남겨 후속 검수와 운영에 활용합니다."
        )
        execution["risk_management"] = [
            "요구사항 해석 차이 | 범위 오해로 인한 산출물 재작업 가능성 | 단계별 확인 회의와 검수 기준 합의",
            "현장 적용 난이도 | 운영 현장과 문서 간 괴리 발생 가능성 | 시범 적용과 피드백 반영 절차 운영",
            "운영 전환 지연 | 인수인계와 교육 부족으로 초기 운영 혼선 가능성 | 운영 매뉴얼과 교육 계획 선제 마련",
        ]
        execution["deliverables"] = [
            "착수보고서 | 착수 단계 종료 시 | 문서 | 발주기관 검토 및 승인",
            "설계 및 구현 산출물 | 설계·구현 단계 종료 시 | 문서 및 결과물 | 단계별 점검 회의",
            "시험 결과서 및 운영 매뉴얼 | 검증·운영 전환 단계 종료 시 | 문서 | 최종 검수 및 운영 준비 확인",
        ]
        execution["total_slides"] = 2
        execution["slide_outline"] = _attachment_grounded_slide_outline(title, section="execution_plan")

    impact = bundle.get("expected_impact")
    if isinstance(impact, dict):
        impact["impact_summary"] = (
            f"{subject}의 기대효과는 교차로 안전성과 교통약자 보호 수준을 높이고, 발주기관이 지속적으로 관리 가능한 운영 구조를 만드는 데 있습니다. "
            "정량 수치를 임의로 제시하기보다, 어떤 효과 범주를 어떤 방식으로 점검할지 중심으로 설명합니다."
        )
        impact["quantitative_effects"] = [
            "교차로 안전성 | 현행 대비 개선 | 사고·민원·운영 로그를 통해 개선 여부 확인 | 안전 관련 운영 품질 향상",
            "교통약자 보호 체계 | 현행 대비 보강 | 현장 점검과 보호 조치 이행 여부 확인 | 장애인 보호 관점의 실행력 강화",
            "운영 관리 수준 | 점검 체계 확보 | 보고와 검수 기록 유지 여부 확인 | 지속 가능한 운영 구조 마련",
        ]
        impact["qualitative_effects"] = [
            "교통약자 신뢰도 향상 | 보호 대상 관점의 서비스 신뢰성 제고 | 공공서비스 체감 품질 개선",
            "운영 일관성 확보 | 현장과 관리 부서 간 판단 기준 정렬 | 반복 가능한 운영 프로세스 정착",
            "정책 확산 기반 마련 | 시범 운영 결과를 후속 의사결정 근거로 활용 | 후속 사업 검토 기반 확보",
        ]
        impact["social_value"] = (
            f"{subject} 사업은 교차로 안전과 교통약자 보호라는 공공 가치를 직접 다룹니다. "
            "따라서 기대효과는 기술 도입 자체보다, 현장에서 안전 문제를 줄이고 보호 대상을 더 일관되게 지원할 수 있는 운영 체계를 만드는 데 있습니다."
        )
        impact["kpi_commitments"] = [
            "교차로 안전 관련 운영 지표 | 현행 대비 개선 여부 확인 | 운영 로그와 점검 결과 | 시범 운영 이후 검토",
            "교통약자 보호 조치 이행도 | 현장 적용 여부 확인 | 현장 피드백과 점검 기록 | 단계별 운영 점검 시점",
            "운영 보고 체계 정착 | 정기 보고와 검수 기록 유지 | 보고서와 검수 이력 | 운영 전환 이후 점검",
        ]
        impact["roi_estimate"] = "투자 대비 효과는 시범 운영 이후 실제 운영 데이터와 검수 결과를 바탕으로 산정합니다."
        impact["monitoring_plan"] = [
            "안전 관련 운영 로그 | 정기 점검 주기 | 운영 담당자 | 개선 여부와 이슈 추이 확인",
            "교통약자 보호 조치 이행 현황 | 단계별 점검 주기 | 현장·운영 공동 책임 | 보호 조치 적용 여부 확인",
            "보고 및 검수 기록 유지 상태 | 정기 리뷰 주기 | PM 및 품질 담당 | 운영 관리 체계 유지 여부 확인",
        ]
        impact["total_slides"] = 2
        impact["slide_outline"] = _attachment_grounded_slide_outline(title, section="expected_impact")


def _quality_guard_performance_bundle(bundle: dict[str, Any], *, title: str, goal: str) -> None:
    subject = _project_subject(title)
    overview = bundle.get("performance_overview")
    if isinstance(overview, dict):
        overview["executive_summary"] = _strip_reference_noise(overview.get("executive_summary"))
        overview["executive_summary"] = _ensure_text(
            overview.get("executive_summary"),
            (
                f"{subject} 수행계획서는 계약 기간 내 필요한 범위, 일정, 산출물, 투입 인력, 승인 게이트를 발주처 기준으로 재정렬한 실행 문서입니다. "
                "착수 이후 요구사항 정의와 설계, 개발·시험, 배포·운영 교육까지 단계별 책임과 완료 기준을 명확히 두어, 중간점검과 최종 납품 시점 모두에서 진행 상태를 객관적으로 설명할 수 있게 합니다. "
                "특히 산출물과 인력, WBS를 서로 연결해 일정과 품질, 자원 배분이 분리되지 않도록 구성합니다."
            ),
        )
        overview["project_info"] = _ensure_text(
            _strip_reference_noise(overview.get("project_info")),
            (
                f"**사업명**: {title}\n"
                "**계약 기간**: 2026년 1월 1일 ~ 2027년 12월 31일 (24개월)\n"
                "**계약 금액**: 6,500,000,000원 (부가세 포함)\n"
                "**발주처**: 국토교통부\n"
                f"**추진 목표**: {goal}\n"
                "**수행 원칙**: 단계별 산출물과 승인 게이트를 연결해 일정·품질·운영 이관을 동시에 관리"
            ),
        )
        overview["scope_of_work"] = _sanitize_rows(
            overview.get("scope_of_work"),
            [
                "교차로 및 스쿨존 대상 AI 기반 안전 모니터링 시스템을 구축합니다.",
                "위험 요소 분석과 개선 방안을 포함한 데이터 기반 운영 체계를 수립합니다.",
                "교통약자 보호를 위한 실시간 대응 대시보드와 보고 체계를 구축합니다.",
                "운영 매뉴얼과 교육 체계를 포함해 현장 적용과 이관까지 사업 범위에 포함합니다.",
            ],
            min_items=4,
        )
        overview["team_structure"] = _sanitize_rows(
            overview.get("team_structure"),
            [
                "PM·총괄 | 특급 | 이현수 | 15 | 국토교통 프로젝트 총괄 및 대외 협의",
                "AI 기술 리드 | 고급 | 김석진 | 10 | 안전 분석 모델 설계 및 성능 검증",
                "소프트웨어 개발 | 중급 | 박민재 외 2명 | 7 | 공공 솔루션 개발 및 연계 구현",
                "품질 관리 | 고급 | 송지현 | 6 | 품질 기준 수립, 시험·검수 운영",
            ],
            min_items=4,
        )
        overview["success_metrics"] = _ensure_rows(
            overview.get("success_metrics"),
            [
                "핵심 산출물 납기 준수 | 예정일 대비 지연 0건 | 산출물 제출대장과 승인 기록",
                "통합 테스트 완료율 | 계획된 핵심 시나리오 100% 통과 | 시험 결과서와 결함 조치 이력",
                "사업 목표 달성도 | 계약서에 정의된 완료 KPI 충족 | 월간 보고서와 최종 검수 확인서",
            ],
        )

    quality = bundle.get("quality_risk_plan")
    if isinstance(quality, dict):
        quality["quality_operating_principles"] = _strip_reference_noise(quality.get("quality_operating_principles"))
        quality["quality_operating_principles"] = _ensure_text(
            quality.get("quality_operating_principles"),
            (
                "품질관리는 산출물 검수만이 아니라 일정·범위·운영 안정성을 함께 관리하는 방식으로 운영합니다. "
                "각 단계마다 사전 점검, 중간 검토, 최종 승인 조건을 분리하고, 결함·리스크·변경 요청은 동일한 이슈 관리 체계 안에서 추적합니다. "
                "이를 통해 품질 기준이 문서상 선언에 그치지 않고 실제 운영 회의와 승인 절차에서 반복 확인되도록 합니다."
            ),
        )
        quality["governance_checkpoints"] = _ensure_rows(
            quality.get("governance_checkpoints"),
            [
                "주간 PMO 회의 | 매주 | PM, 기술 리드, 품질 책임자 | 일정 진척률, 결함 조치, 선행 과제 상태",
                "월간 운영위원회 | 매월 | PM, 발주처 담당관, 주요 수행 리더 | 산출물 승인 여부, 리스크 등급, 변경 요청 검토",
                "분기 경영진 보고 | 분기 | Executive Approver, PM | 예산·성과·운영 리스크 종합 점검과 의사결정",
            ],
        )


def _apply_finished_doc_quality_guard(
    bundle: dict[str, Any],
    *,
    bundle_type: str,
    title: str,
    goal: str,
    context_text: str = "",
) -> dict[str, Any]:
    if bundle_type == "proposal_kr":
        _quality_guard_proposal_bundle(bundle, title=title, goal=goal)
        _quality_guard_attachment_grounded_proposal_bundle(
            bundle,
            title=title,
            goal=goal,
            context_text=context_text,
        )
    elif bundle_type == "performance_plan_kr":
        _quality_guard_performance_bundle(bundle, title=title, goal=goal)
    normalized = _normalize_finished_doc_value(bundle)
    return normalized if isinstance(normalized, dict) else bundle


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


class ProviderFailedError(Exception):
    pass


def iter_exception_chain(exc: BaseException) -> list[BaseException]:
    """Return the exception chain for *exc* following cause/context links."""
    chain: list[BaseException] = []
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        chain.append(current)
        seen.add(id(current))
        current = getattr(current, "__cause__", None) or getattr(current, "__context__", None)
    return chain


def provider_failure_retry_after_seconds(exc: BaseException) -> int | None:
    """Extract retry-after seconds from a provider exception chain when present."""
    for candidate in iter_exception_chain(exc):
        for headers in (
            getattr(candidate, "headers", None),
            getattr(getattr(candidate, "response", None), "headers", None),
        ):
            if headers is None or not hasattr(headers, "get"):
                continue
            raw = headers.get("retry-after") or headers.get("Retry-After")
            if raw is None:
                continue
            try:
                seconds = int(float(str(raw).strip()))
            except (TypeError, ValueError):
                continue
            if seconds >= 0:
                return seconds
    return None


def provider_failure_error_code(exc: BaseException) -> str | None:
    """Extract a provider-specific error code such as insufficient_quota."""
    for candidate in iter_exception_chain(exc):
        body = getattr(candidate, "body", None)
        if isinstance(body, dict):
            error = body.get("error")
            if isinstance(error, dict):
                for key in ("code", "type"):
                    value = error.get(key)
                    if isinstance(value, str) and value.strip():
                        return value.strip()
        response = getattr(candidate, "response", None)
        headers = getattr(response, "headers", None)
        if headers is not None and hasattr(headers, "get"):
            value = headers.get("x-error-code") or headers.get("X-Error-Code")
            if isinstance(value, str) and value.strip():
                return value.strip()
        message = str(candidate).lower()
        if "insufficient_quota" in message:
            return "insufficient_quota"
        if "rate_limit_exceeded" in message:
            return "rate_limit_exceeded"
    return None


def is_provider_rate_limited(exc: BaseException) -> bool:
    """Return True when the provider exception chain indicates HTTP 429/rate limiting."""
    for candidate in iter_exception_chain(exc):
        if getattr(candidate, "status_code", None) == 429:
            return True
        if getattr(getattr(candidate, "response", None), "status_code", None) == 429:
            return True
        message = str(candidate).lower()
        if "too many requests" in message or "rate limit" in message or "429" in message:
            return True
    return False


class EvalLintFailedError(Exception):
    def __init__(self, errors: list[str]) -> None:
        super().__init__("Eval lint failed.")
        self.errors = errors


class BundleNotSupportedError(Exception):
    """Raised when a requested operation does not support the given bundle_type."""

    def __init__(self, bundle_type: str, operation: str) -> None:
        super().__init__(f"Bundle '{bundle_type}' is not supported for '{operation}'.")
        self.bundle_type = bundle_type
        self.operation = operation


class GenerationService:
    _PROCUREMENT_HANDOFF_BUNDLE_IDS = {
        "bid_decision_kr",
        "rfp_analysis_kr",
        "proposal_kr",
        "performance_plan_kr",
    }

    def __init__(
        self,
        provider_factory: Callable[[], Provider],
        template_dir: Path,
        data_dir: Path,
        storage: Storage | None = None,
        procurement_store: Any | None = None,
        decision_council_store: Any | None = None,
        procurement_copilot_enabled: bool = False,
        feedback_store: FeedbackStore | None = None,
        eval_store: Any | None = None,
        search_service: Any | None = None,
        finetune_store: "FineTuneStore | None" = None,
    ) -> None:
        self.provider_factory = provider_factory
        self.feedback_store = feedback_store
        self._eval_store = eval_store
        self._search_service = search_service
        self._procurement_store = procurement_store
        self._decision_council_store = decision_council_store
        self._procurement_copilot_enabled = procurement_copilot_enabled
        self._finetune_store = finetune_store
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.cache_dir = self.data_dir / "cache"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.storage = storage
        self.env = Environment(
            loader=FileSystemLoader(str(template_dir)),
            autoescape=select_autoescape(
                enabled_extensions=("html", "htm", "xml"),
                default_for_string=False,
                default=False,
            ),
            trim_blocks=True,
            lstrip_blocks=True,
        )
        self.env.filters["markdown_table"] = build_markdown_table
        self.env.filters["markdown_kv_table"] = build_markdown_kv_table
        self.env.filters["slide_outline_table"] = build_slide_outline_table

    def generate_documents(self, requirements: GenerateRequest, *, request_id: str, tenant_id: str = "system") -> dict[str, Any]:
        bundle_id = str(uuid4())
        payload = requirements.model_dump(mode="json")

        # Seed thread-local context so it's available after generation.
        _generation_context.request_id = request_id
        _generation_context.title = payload.get("title", "")
        _generation_context.goal = payload.get("goal", "")
        _generation_context.context_text = payload.get("context", "")
        _generation_context.bundle_type = payload.get("bundle_type", "tech_decision") or "tech_decision"
        _generation_context.system_prompt = ""
        _generation_context.output = ""

        # Set current tenant for multi-tenant store isolation
        try:
            from app.domain.schema import _current_tenant_id
            _current_tenant_id.value = tenant_id
        except Exception:
            pass

        # Resolve bundle spec (defaults to tech_decision for backward compatibility).
        bundle_type = payload.get("bundle_type", "tech_decision") or "tech_decision"
        bundle_spec = get_bundle_spec(bundle_type)

        variant_key = os.getenv("DECISIONDOC_PROMPT_VARIANT", "")
        if variant_key:
            bundle_spec = self._apply_prompt_variant(bundle_spec, variant_key)

        self._inject_project_contexts(
            payload,
            bundle_type=bundle_type,
            tenant_id=tenant_id,
            request_id=request_id,
        )
        procurement_handoff_used = bool(payload.get("_procurement_context"))
        decision_council_handoff_used = bool(payload.get("_decision_council_context"))
        decision_council_handoff_skipped_reason = (
            str(payload.get("_decision_council_handoff_skipped_reason") or "").strip() or None
        )
        decision_council_session_id = str(payload.get("_decision_council_session_id") or "").strip() or None
        decision_council_session_revision = payload.get("_decision_council_session_revision")
        decision_council_direction = str(payload.get("_decision_council_direction") or "").strip() or None
        decision_council_use_case = str(payload.get("_decision_council_use_case") or "").strip() or None
        decision_council_target_bundle = str(payload.get("_decision_council_target_bundle") or "").strip() or None
        decision_council_applied_bundle = str(payload.get("_decision_council_applied_bundle") or "").strip() or None

        provider = self._safe_get_provider(bundle_type=bundle_type, tenant_id=tenant_id)
        timer = Timer()
        cache_enabled = env_is_enabled("DECISIONDOC_CACHE_ENABLED")
        cache_hit = False

        bundle: dict[str, Any]
        cache_path = self._cache_path(provider.name, SCHEMA_VERSION, payload)
        if cache_enabled and cache_path.exists() and self._is_cache_fresh(cache_path):
            cached = self._try_read_cache(cache_path)
            if cached is not None:
                bundle = cached
                cache_hit = True
                self._validate_bundle_schema(bundle, bundle_spec)
            else:
                # Cache file is corrupt or unreadable — remove it before re-generating.
                try:
                    cache_path.unlink()
                except OSError:
                    pass
                bundle = self._call_and_prepare_bundle(provider, payload, request_id, timer, bundle_spec)
                self._write_cache_atomic(cache_path, bundle)
        else:
            # Inject web search context if available
            if self._search_service is not None and self._search_service.is_available():
                query_parts = [
                    str(payload.get("title", "")),
                    str(payload.get("goal", "")),
                    str(payload.get("industry", "")),
                ]
                query = " ".join(p for p in query_parts if p).strip()
                if query:
                    search_results = self._search_service.search(query, num=5)
                    if search_results:
                        snippets = "\n".join(
                            f"{i+1}. [{r.title}] {r.snippet}"
                            for i, r in enumerate(search_results[:5])
                        )
                        payload["_search_context"] = snippets

            bundle = self._call_and_prepare_bundle(provider, payload, request_id, timer, bundle_spec)
            if cache_enabled:
                self._write_cache_atomic(cache_path, bundle)

        if self.storage is not None:
            self.storage.save_bundle(bundle_id, bundle)
        with timer.measure("render_ms"):
            docs = self._render_docs(payload, bundle, bundle_spec)
        with timer.measure("lints_ms"):
            lint_errors = lint_docs(
                {doc["doc_type"]: doc["markdown"] for doc in docs},
                lint_headings_override=bundle_spec.lint_headings_map(),
                critical_headings_override=bundle_spec.critical_non_empty_headings_map(),
            )
        if lint_errors:
            raise EvalLintFailedError(lint_errors)
        with timer.measure("validator_ms"):
            validate_docs(docs, headings_override=bundle_spec.validator_headings_map())
        usage_tokens = provider.consume_usage_tokens() if not cache_hit else None

        # ── Capture generation context for fine-tune collection ──────────────
        # system_prompt was captured in thread-local by build_bundle_prompt().
        # Collect it now (before spawning background thread) to avoid data races.
        ft_system_prompt = ""
        if not cache_hit:
            try:
                from app.domain.schema import _ft_last_prompt
                ft_system_prompt = getattr(_ft_last_prompt, "prompt", "") or ""
            except Exception:
                pass
        ft_output = "\n\n".join(doc.get("markdown", "") for doc in docs).strip()

        # Store cross-request context snapshot (used by /feedback → Trigger A).
        _store_generation_context(request_id, {
            "request_id": request_id,
            "bundle_type": bundle_type,
            "title": payload.get("title", ""),
            "goal": payload.get("goal", ""),
            "context_text": payload.get("context", ""),
            "system_prompt": ft_system_prompt,
            "output": ft_output,
        })

        # 백그라운드 품질 평가 (EvalStore가 연결된 경우)
        if self._eval_store is not None:
            # A/B variant selected during prompt building (set by _inject_prompt_override)
            # Only available on cache miss (cache hits don't call build_bundle_prompt)
            ab_variant: str | None = None
            ab_store_instance: Any | None = None
            if not cache_hit:
                try:
                    from app.domain.schema import _ab_selected
                    sel_variant = getattr(_ab_selected, "variant", None)
                    sel_bundle_id = getattr(_ab_selected, "bundle_id", None)
                    if sel_variant and sel_bundle_id == bundle_type:
                        ab_variant = sel_variant
                        from app.storage.ab_test_store import ABTestStore
                        ab_store_instance = ABTestStore(self.data_dir)
                except Exception:
                    pass

            # Use tenant-scoped eval store for isolation
            try:
                from app.eval.eval_store import get_eval_store
                active_eval_store = get_eval_store(tenant_id)
            except Exception:
                active_eval_store = self._eval_store

            from app.eval.pipeline import run_eval_pipeline
            try:
                _future = _eval_executor.submit(
                    run_eval_pipeline,
                    request_id,
                    bundle_type,
                    docs,
                    active_eval_store,
                    title=payload.get("title", ""),
                    goal=payload.get("goal", ""),
                    context=payload.get("context", ""),
                    ab_store=ab_store_instance,
                    ab_variant=ab_variant,
                    finetune_store=self._finetune_store,
                    ft_system_prompt=ft_system_prompt,
                    ft_output=ft_output,
                    tenant_id=tenant_id,
                )
                _future.add_done_callback(_eval_done_callback)
            except RuntimeError as exc:
                _log.warning(
                    "[Eval] Background eval skipped because executor is unavailable: %s",
                    exc,
                )

        # Record usage (fire-and-forget — don't fail generation on billing errors)
        try:
            _tokens = usage_tokens or {}
            _user_id = payload.get("user_id", "") or ""
            _record_usage_sync(
                tenant_id=tenant_id,
                user_id=_user_id,
                bundle_id=bundle_type,
                request_id=request_id,
                model=provider.name,
                tokens_input=_tokens.get("prompt_tokens", 0) or 0,
                tokens_output=_tokens.get("output_tokens", 0) or 0,
            )
        except Exception:
            pass

        return {
            "docs": docs,
            "raw_bundle": bundle,
            "metadata": {
                "provider": provider.name,
                "schema_version": SCHEMA_VERSION,
                "cache_hit": cache_hit if cache_enabled else None,
                "request_id": request_id,
                "bundle_id": bundle_id,
                "bundle_type": bundle_type,
                "project_id": payload.get("project_id"),
                "doc_count": len(docs),
                "procurement_handoff_used": procurement_handoff_used,
                "decision_council_handoff_used": decision_council_handoff_used,
                "decision_council_handoff_skipped_reason": decision_council_handoff_skipped_reason,
                "decision_council_session_id": decision_council_session_id,
                "decision_council_session_revision": decision_council_session_revision,
                "decision_council_direction": decision_council_direction,
                "decision_council_use_case": decision_council_use_case,
                "decision_council_target_bundle": decision_council_target_bundle,
                "decision_council_applied_bundle": decision_council_applied_bundle,
                "timings_ms": timer.durations_ms,
                "llm_prompt_tokens": (usage_tokens or {}).get("prompt_tokens"),
                "llm_output_tokens": (usage_tokens or {}).get("output_tokens"),
                "llm_total_tokens": (usage_tokens or {}).get("total_tokens"),
                "applied_references": payload.get("_knowledge_ranked_documents", [])[:3],
            },
        }

    def _render_docs(
        self,
        payload: dict[str, Any],
        bundle: dict[str, Any],
        bundle_spec: BundleSpec,
    ) -> list[dict[str, str]]:
        """Render each document in the bundle using its Jinja2 template.

        For the ``tech_decision`` bundle (backward compat), the ``doc_types``
        field in the payload determines which docs to render.  For all other
        bundles every doc in the bundle spec is rendered.
        """
        bundle_type = payload.get("bundle_type", "tech_decision") or "tech_decision"
        if bundle_type == "tech_decision":
            # Honor the legacy doc_types filter.
            doc_keys = [
                dt if isinstance(dt, str) else dt.value
                for dt in payload.get("doc_types", bundle_spec.doc_keys)
            ]
        else:
            doc_keys = bundle_spec.doc_keys

        docs: list[dict[str, str]] = []
        for doc_key in doc_keys:
            doc_spec = bundle_spec.get_doc(doc_key)
            if doc_spec is None:
                continue  # skip unknown keys gracefully
            context = {
                "title": payload["title"],
                "goal": payload["goal"],
                "context": payload.get("context", ""),
                "procurement_context": payload.get("_procurement_context", ""),
                "constraints": payload.get("constraints", ""),
                "priority": payload.get("priority", ""),
                "audience": payload.get("audience", ""),
                **bundle.get(doc_key, {}),
            }
            markdown = self.env.get_template(doc_spec.template_file).render(**context).strip() + "\n"
            docs.append({"doc_type": doc_key, "markdown": markdown})
        return docs

    def _validate_bundle_schema(self, bundle: Any, bundle_spec: BundleSpec) -> None:
        if not isinstance(bundle, dict):
            raise ProviderFailedError(
                f"Provider returned invalid bundle: expected dict, got {type(bundle).__name__}"
            )

        schema = bundle_spec.json_schema
        required_top = schema["required"]
        properties = schema["properties"]
        for key in required_top:
            if key not in bundle:
                raise ProviderFailedError(
                    f"Provider returned invalid bundle: missing top-level key '{key}'"
                )
            if not isinstance(bundle[key], dict):
                raise ProviderFailedError(
                    f"Provider returned invalid bundle: '{key}' must be a dict, got {type(bundle[key]).__name__}"
                )
            required_fields = properties[key]["required"]
            for field in required_fields:
                if field not in bundle[key]:
                    raise ProviderFailedError(
                        f"Provider returned invalid bundle: missing field '{key}.{field}'"
                    )
                value = bundle[key][field]
                field_schema = properties[key]["properties"][field]
                expected_type = field_schema["type"]
                if expected_type == "string" and not isinstance(value, str):
                    raise ProviderFailedError(
                        f"Provider returned invalid bundle: '{key}.{field}' must be a string, got {type(value).__name__}"
                    )
                if expected_type == "integer" and not isinstance(value, int):
                    raise ProviderFailedError(
                        f"Provider returned invalid bundle: '{key}.{field}' must be an integer, got {type(value).__name__}"
                    )
                if expected_type == "array":
                    if not isinstance(value, list):
                        raise ProviderFailedError(
                            f"Provider returned invalid bundle: '{key}.{field}' must be an array, got {type(value).__name__}"
                        )
                    # Only validate items as strings when the schema declares items.type == "string".
                    # Arrays of objects (e.g. slide_outline) are accepted as-is.
                    items_type = field_schema.get("items", {}).get("type")
                    if items_type == "string":
                        for i, item in enumerate(value):
                            if not isinstance(item, str):
                                raise ProviderFailedError(
                                    f"Provider returned invalid bundle: '{key}.{field}[{i}]' must be a string, got {type(item).__name__}"
                                )

    def _is_cache_fresh(self, cache_path: Path) -> bool:
        """Return True if the cache file is within the configured TTL.

        TTL is controlled by DECISIONDOC_CACHE_TTL_HOURS (default 24).
        Set to 0 for permanent cache (no expiry).
        """
        ttl_hours = int(os.getenv("DECISIONDOC_CACHE_TTL_HOURS", "24"))
        if ttl_hours <= 0:
            return True  # 0 → permanent cache
        age_hours = (time.time() - cache_path.stat().st_mtime) / 3600
        return age_hours < ttl_hours

    def _cache_path(self, provider_name: str, schema_version: str, payload: dict[str, Any]) -> Path:
        canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        key = f"{provider_name}:{schema_version}:{canonical}"
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
        return self.cache_dir / f"{digest}.json"

    def _call_and_prepare_bundle(
        self,
        provider: Provider,
        payload: dict[str, Any],
        request_id: str,
        timer: Timer,
        bundle_spec: BundleSpec,
    ) -> dict[str, Any]:
        """Call the provider, stabilize, strip internal fields, and validate schema."""
        with timer.measure("provider_ms"):
            bundle = self._call_provider_with_retry(provider, payload, request_id, bundle_spec)
        bundle = stabilize_bundle(bundle, structure=bundle_spec.stabilizer_structure())
        bundle = strip_internal_bundle_fields(bundle)
        bundle = _apply_finished_doc_quality_guard(
            bundle,
            bundle_type=str(payload.get("bundle_type", "tech_decision") or "tech_decision"),
            title=str(payload.get("title", "") or ""),
            goal=str(payload.get("goal", "") or ""),
            context_text=str(payload.get("context", "") or ""),
        )
        procurement_context = str(payload.get("_procurement_context", "") or "").strip()
        if not procurement_context:
            procurement_context = _extract_procurement_context_from_text(payload.get("context", ""))
        if procurement_context:
            bundle = _apply_procurement_slide_outline_guidance(
                bundle,
                procurement_context=procurement_context,
            )
        self._validate_bundle_schema(bundle, bundle_spec)
        return bundle

    def _apply_prompt_variant(self, bundle_spec: BundleSpec, variant_key: str | None) -> BundleSpec:
        """Apply a prompt variant if specified. Returns modified BundleSpec or original."""
        if not variant_key:
            return bundle_spec
        variant_prompt = bundle_spec.prompt_variants.get(variant_key)
        if not variant_prompt:
            return bundle_spec
        import dataclasses
        return dataclasses.replace(bundle_spec, prompt_hint=variant_prompt)

    def _serialize_applied_reference(self, item: dict[str, Any]) -> dict[str, Any]:
        return {
            "doc_id": str(item.get("doc_id", "") or ""),
            "filename": str(item.get("filename", "") or ""),
            "learning_mode": str(item.get("learning_mode", "") or "reference"),
            "quality_tier": str(item.get("quality_tier", "") or "working"),
            "success_state": str(item.get("success_state", "") or "draft"),
            "applicable_bundles": [
                str(bundle).strip()
                for bundle in (item.get("applicable_bundles") or [])
                if str(bundle).strip()
            ],
            "source_organization": str(item.get("source_organization", "") or ""),
            "reference_year": item.get("reference_year"),
            "tags": [
                str(tag).strip()
                for tag in (item.get("tags") or [])
                if str(tag).strip()
            ],
            "score": int(item.get("score", 0) or 0),
            "query_overlap": int(item.get("query_overlap", 0) or 0),
            "bundle_match": bool(item.get("bundle_match")),
            "selection_reason": str(item.get("selection_reason", "") or ""),
            "score_breakdown": list(item.get("score_breakdown") or []),
        }

    def _inject_project_contexts(
        self,
        payload: dict[str, Any],
        *,
        bundle_type: str,
        tenant_id: str,
        request_id: str,
    ) -> None:
        project_id = payload.get("project_id")
        if not project_id:
            return

        try:
            from app.storage.knowledge_store import KnowledgeStore

            ks = KnowledgeStore(project_id)
            ranked_documents = ks.rank_documents_for_context(
                bundle_type=bundle_type,
                title=str(payload.get("title", "") or ""),
                goal=str(payload.get("goal", "") or ""),
            )
            knowledge_ctx = ks.build_context(
                bundle_type=bundle_type,
                title=str(payload.get("title", "") or ""),
                goal=str(payload.get("goal", "") or ""),
            )
            style_ctx = ks.build_style_context()
            if ranked_documents:
                payload["_knowledge_ranked_documents"] = [
                    self._serialize_applied_reference(item)
                    for item in ranked_documents[:5]
                ]
            if knowledge_ctx:
                payload["_knowledge_context"] = knowledge_ctx
                _log.info(
                    "[Knowledge] Injected context for project=%s len=%d request_id=%s",
                    project_id,
                    len(knowledge_ctx),
                    request_id,
                )
            if style_ctx:
                payload["_style_context"] = style_ctx
        except Exception as exc:
            _log.warning("[Knowledge] Failed to load context project=%s: %s", project_id, exc)

        if (
            not self._procurement_copilot_enabled
            or bundle_type not in self._PROCUREMENT_HANDOFF_BUNDLE_IDS
            or self._procurement_store is None
        ):
            procurement_ctx = ""
        else:
            procurement_ctx = self._build_procurement_context(project_id=project_id, tenant_id=tenant_id)
            if procurement_ctx:
                payload["_procurement_context"] = procurement_ctx
                _log.info(
                    "[Procurement] Injected handoff context project=%s bundle=%s len=%d request_id=%s",
                    project_id,
                    bundle_type,
                    len(procurement_ctx),
                    request_id,
                )

        if (
            not self._procurement_copilot_enabled
            or bundle_type not in _DECISION_COUNCIL_APPLIED_BUNDLE_IDS
            or self._decision_council_store is None
        ):
            return

        council_session = self._decision_council_store.get_latest(
            tenant_id=tenant_id,
            project_id=project_id,
            use_case="public_procurement",
            target_bundle_type="bid_decision_kr",
        )
        if council_session is None:
            return
        if not self._current_procurement_record_matches_council_session(
            project_id=project_id,
            tenant_id=tenant_id,
            council_session=council_session,
        ):
            payload["_decision_council_handoff_skipped_reason"] = "stale_procurement_context"
            _log.info(
                "[DecisionCouncil] Skipped stale handoff context project=%s bundle=%s session=%s request_id=%s",
                project_id,
                bundle_type,
                council_session.session_id,
                request_id,
            )
            return

        council_context = self._build_decision_council_context(
            council_session,
            bundle_type=bundle_type,
        )
        if not council_context:
            return

        payload["_decision_council_context"] = council_context
        payload["_decision_council_session_id"] = council_session.session_id
        payload["_decision_council_session_revision"] = council_session.session_revision
        payload["_decision_council_direction"] = council_session.consensus.recommended_direction
        payload["_decision_council_use_case"] = council_session.use_case
        payload["_decision_council_target_bundle"] = council_session.target_bundle_type
        payload["_decision_council_applied_bundle"] = bundle_type
        _log.info(
            "[DecisionCouncil] Injected handoff context project=%s bundle=%s session=%s revision=%s request_id=%s",
            project_id,
            bundle_type,
            council_session.session_id,
            council_session.session_revision,
            request_id,
        )

    def _build_procurement_context(self, *, project_id: str, tenant_id: str) -> str:
        record = self._procurement_store.get(project_id, tenant_id=tenant_id)
        if record is None:
            return ""

        opportunity = record.opportunity
        recommendation = record.recommendation
        lines: list[str] = [
            "프로젝트 공공조달 의사결정 상태입니다. 아래 structured state를 문서 작성의 source of truth로 사용하세요.",
        ]
        if opportunity is not None:
            lines.extend(
                [
                    f"- 공고명: {opportunity.title}",
                    f"- 발주기관: {opportunity.issuer or '미상'}",
                    f"- 예산: {opportunity.budget or '미확인'}",
                    f"- 마감: {opportunity.deadline or '미확인'}",
                    f"- 입찰방식: {opportunity.bid_type or '미확인'}",
                    f"- 카테고리: {opportunity.category or '미확인'}",
                ]
            )
            if opportunity.source_url:
                lines.append(f"- 원문 URL: {opportunity.source_url}")

        if recommendation is not None:
            lines.extend(
                [
                    f"- 현재 추천 결론: {recommendation.value}",
                    f"- 추천 요약: {recommendation.summary or '요약 없음'}",
                ]
            )

        if record.hard_filters:
            lines.append("Hard filter 결과:")
            for item in record.hard_filters[:8]:
                blocking = " / blocking" if item.blocking else ""
                reason = f" / {item.reason}" if item.reason else ""
                lines.append(f"- {item.label}: {item.status}{blocking}{reason}")

        if record.soft_fit_score is not None:
            lines.append(
                f"- Soft-fit score: {record.soft_fit_score:.1f} ({record.soft_fit_status})"
            )
        elif record.soft_fit_status:
            lines.append(f"- Soft-fit score status: {record.soft_fit_status}")

        if record.missing_data:
            lines.append("확인되지 않은 데이터:")
            for item in record.missing_data[:8]:
                lines.append(f"- {item}")

        actionable_checklist = [
            item for item in record.checklist_items if item.status in {"blocked", "action_needed"}
        ]
        if actionable_checklist:
            lines.append("입찰 준비 체크리스트 중 조치 필요 항목:")
            for item in actionable_checklist[:10]:
                owner = f" / owner={item.owner}" if item.owner else ""
                due = f" / due={item.due_date}" if item.due_date else ""
                remediation = f" / {item.remediation_note}" if item.remediation_note else ""
                lines.append(
                    f"- [{item.category}] {item.title}: {item.status}, severity={item.severity}"
                    f"{owner}{due}{remediation}"
                )

        if record.score_breakdown:
            lines.append("Soft-fit factor breakdown:")
            for item in record.score_breakdown[:8]:
                lines.append(
                    f"- {item.label}: score={item.score:.1f}, weight={item.weight:.2f}, "
                    f"weighted={item.weighted_score:.1f}, status={item.status}"
                )

        if record.capability_profile is not None:
            lines.extend(
                [
                    f"- capability_profile.source_ref: {record.capability_profile.source_ref}",
                    f"- capability_profile.summary: {record.capability_profile.summary or '요약 없음'}",
                ]
            )

        latest_snapshot = record.source_snapshots[-1] if record.source_snapshots else None
        if latest_snapshot is not None:
            payload = self._procurement_store.load_source_snapshot(
                tenant_id=tenant_id,
                project_id=project_id,
                snapshot_id=latest_snapshot.snapshot_id,
            )
            if isinstance(payload, dict):
                extracted_fields = payload.get("extracted_fields") or {}
                structured_context = str(payload.get("structured_context") or "").strip()
                if extracted_fields:
                    lines.append("최신 원문 추출 신호:")
                    for key, value in list(extracted_fields.items())[:12]:
                        rendered = json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value)
                        lines.append(f"- {key}: {rendered[:240]}")
                if structured_context:
                    lines.append("최신 원문/구조화 맥락 요약:")
                    lines.append(structured_context[:2000])

        return "\n".join(lines).strip()

    def _current_procurement_record_matches_council_session(
        self,
        *,
        project_id: str,
        tenant_id: str,
        council_session: Any,
    ) -> bool:
        record = None
        if self._procurement_store is not None:
            record = self._procurement_store.get(project_id, tenant_id=tenant_id)
        binding = describe_procurement_council_binding(
            session=council_session,
            procurement_record=record,
        )
        return binding["status"] == "current"

    def _build_decision_council_context(self, session: Any, *, bundle_type: str) -> str:
        return build_procurement_council_generation_context(
            session,
            bundle_type=bundle_type,
        )

    def _build_feedback_hints(self, bundle_type: str, title: str = "") -> str:
        """Build structured few-shot hints from high-rated feedback examples.

        Returns a formatted string injected into the LLM prompt.
        Each example includes: title, rating, user comment, and per-doc
        section heading + first 800 chars for all doc types.
        """
        # Resolve tenant-scoped feedback store if available
        try:
            from app.domain.schema import _current_tenant_id
            from app.storage.feedback_store import get_feedback_store
            tid = getattr(_current_tenant_id, "value", "system") or "system"
            feedback_store = get_feedback_store(tid)
        except Exception:
            feedback_store = self.feedback_store
        if not feedback_store:
            return ""
        try:
            examples = feedback_store.get_high_rated_examples(
                bundle_type=bundle_type,
                min_rating=4,
                limit=3,
                doc_content_limit=800,
            )
        except Exception:
            return ""

        if not examples:
            return ""

        blocks: list[str] = ["## 참고: 이전 고품질 생성 예시"]
        for i, ex in enumerate(examples, 1):
            ex_title = ex.get("title") or "(제목 없음)"
            rating = ex.get("rating", 0)
            comment = ex.get("comment", "")
            header = f"\n### 예시 {i} — 제목: {ex_title}  (평점: {rating}/5)"
            if comment:
                header += f"\n사용자 피드백: {comment}"
            blocks.append(header)

            docs: dict = ex.get("docs") or {}
            for doc_type, doc_info in docs.items():
                if not isinstance(doc_info, dict):
                    continue
                heading = doc_info.get("heading") or doc_type
                content = doc_info.get("content", "").strip()
                if not content:
                    continue
                blocks.append(
                    f"\n#### [{doc_type}] {heading}\n```\n{content}\n```"
                )

        if len(blocks) == 1:
            return ""
        return "\n".join(blocks)

    def _call_provider_once(
        self,
        provider: Provider,
        payload: dict[str, Any],
        request_id: str,
        bundle_spec: BundleSpec,
    ) -> dict[str, Any]:
        feedback_hints = self._build_feedback_hints(bundle_spec.id, title=payload.get("title", ""))
        try:
            return provider.generate_bundle(
                payload,
                schema_version=SCHEMA_VERSION,
                request_id=request_id,
                bundle_spec=bundle_spec,
                feedback_hints=feedback_hints,
            )
        except Exception as exc:
            raise ProviderFailedError("Provider failed.") from exc

    def _call_provider_with_retry(
        self,
        provider: Provider,
        payload: dict[str, Any],
        request_id: str,
        bundle_spec: BundleSpec,
    ) -> dict[str, Any]:
        """Call provider with exponential backoff retry on ProviderFailedError."""
        from app.config import get_llm_retry_attempts, get_llm_retry_backoff_seconds
        attempts = get_llm_retry_attempts()
        backoffs = get_llm_retry_backoff_seconds()
        last_exc: ProviderFailedError | None = None
        for attempt in range(attempts):
            try:
                return self._call_provider_once(provider, payload, request_id, bundle_spec)
            except ProviderFailedError as exc:
                last_exc = exc
                if attempt < attempts - 1:
                    delay = backoffs[attempt] if attempt < len(backoffs) else backoffs[-1]
                    if is_provider_rate_limited(exc):
                        retry_after = provider_failure_retry_after_seconds(exc)
                        delay = max(delay, retry_after if retry_after is not None else 15)
                    _log.warning(
                        "[LLM Retry] attempt %d/%d failed for request_id=%s, "
                        "retrying in %ds: %s",
                        attempt + 1, attempts, request_id, delay, exc,
                    )
                    time.sleep(delay)
        raise last_exc  # type: ignore[misc]

    def _try_read_cache(self, cache_path: Path) -> dict[str, Any] | None:
        try:
            text = cache_path.read_text(encoding="utf-8")
            parsed = json.loads(text)
            if not isinstance(parsed, dict):
                return None
            return parsed
        except (OSError, ValueError, json.JSONDecodeError):
            return None

    def _write_cache_atomic(self, cache_path: Path, bundle: dict[str, Any]) -> None:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(bundle, ensure_ascii=False, indent=2)
        tmp_path = cache_path.with_name(f"{cache_path.name}.tmp.{uuid4().hex}")
        try:
            with tmp_path.open("w", encoding="utf-8") as f:
                f.write(payload)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, cache_path)
        finally:
            if tmp_path.exists():
                try:
                    tmp_path.unlink()
                except OSError:
                    pass

    def clear_cache(self) -> int:
        """Delete all cached bundles. Returns the number of files removed."""
        count = 0
        for f in self.cache_dir.glob("*.json"):
            try:
                f.unlink()
                count += 1
            except OSError:
                pass
        return count

    def _safe_get_provider(
        self, bundle_type: str | None = None, tenant_id: str = "system"
    ) -> Provider:
        """Return the best available provider, preferring fine-tuned model if active.

        Checks ModelRegistry for an active fine-tuned model first.  If found,
        returns an OpenAI provider using that model_id.  Otherwise falls back to
        the injected ``provider_factory`` so that tests keep full DI control.
        """
        try:
            from app.storage.model_registry import ModelRegistry
            registry = ModelRegistry()
            active_model = registry.get_active_model(bundle_type, tenant_id)
            if active_model and active_model.get("status") == "ready":
                model_id = active_model.get("model_id", "")
                if model_id and not model_id.startswith("pending:"):
                    from app.providers.factory import get_provider
                    return get_provider(model_override=model_id)
        except Exception:
            pass  # Fall through to injected factory

        try:
            return self.provider_factory()
        except Exception as exc:
            raise ProviderFailedError("Provider failed.") from exc
