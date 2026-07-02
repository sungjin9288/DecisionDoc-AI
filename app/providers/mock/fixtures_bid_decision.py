"""Mock fixture builders for the bid_decision_kr bundle."""
from app.providers.mock.shared import _ctx_excerpt


def _bid_decision_opportunity_brief(title: str, goal: str, ctx: str) -> dict:
    excerpt = _ctx_excerpt(ctx, 1200)
    return {
        "opportunity_summary": (
            f"{title} 공고에 대해 {goal} 관점에서 초기 입찰 검토를 수행합니다. "
            f"현재 확보된 structured decision context는 다음과 같습니다: {excerpt}"
        ),
        "issuer_and_scope": (
            f"발주기관 요구와 사업 범위를 기준으로 당사 적합성을 검토합니다. "
            f"project-scoped procurement state와 최신 source snapshot을 함께 반영합니다. {excerpt}"
        ),
        "commercial_terms": [
            "예산, 마감, 입찰방식, 계약 범위를 동일 화면에서 확인하고 우선 리스크를 식별합니다.",
            "수주 여부 판단 전 필수 자격, 일정 압박, 파트너 필요 여부를 함께 검토합니다.",
            f"참고 procurement context: {excerpt}",
        ],
        "source_highlights": [
            "공고 원문에서 즉시 확인할 핵심 조건과 발주기관의 기대치를 추렸습니다.",
            "기존 project capability profile과 충돌하거나 보완이 필요한 지점을 별도로 표시합니다.",
            f"원문/구조화 맥락 요약: {excerpt}",
        ],
    }

def _bid_decision_go_no_go_memo(title: str, goal: str, ctx: str) -> dict:
    excerpt = _ctx_excerpt(ctx, 1200)
    return {
        "recommendation_decision": (
            f"{title}에 대한 현재 Go/No-Go 판단은 structured state를 기준으로 정리합니다. "
            f"{excerpt}"
        ),
        "hard_filter_findings": [
            "blocking fail 여부를 최우선으로 검토하고, 통과 여부를 근거와 함께 명시합니다.",
            "필수 자격, 인증, 유사 실적, 일정 적합성은 narrative보다 먼저 해석합니다.",
            f"현재 decision context: {excerpt}",
        ],
        "soft_fit_summary": (
            f"정량 점수와 factor breakdown은 입찰 적합도를 보조 설명하는 용도로 사용합니다. {excerpt}"
        ),
        "decision_rationale": [
            "권고 결론은 hard filter, weighted fit score, missing data 상태를 함께 반영합니다.",
            "보완 가능 항목과 즉시 차단 항목을 분리하여 경영진 판단 시간을 줄입니다.",
            f"현재 structured rationale reference: {excerpt}",
        ],
        "executive_notes": (
            f"{goal} 관점에서 경영진이 확인해야 할 리스크, 승인 조건, 다음 단계 의사결정을 요약합니다. {excerpt}"
        ),
    }

def _bid_decision_checklist(title: str, goal: str, ctx: str) -> dict:
    excerpt = _ctx_excerpt(ctx, 1200)
    return {
        "blocking_items": [
            "즉시 입찰 참여를 막는 자격·인증·기한 이슈가 있는지 먼저 확인합니다.",
            f"차단 항목 근거는 procurement checklist/action-needed 상태에서 파생합니다. {excerpt}",
        ],
        "action_items": [
            "보완 가능한 증빙, 파트너 확보, 인력 배치, 질의응답 준비 항목을 분리합니다.",
            "실무 담당자가 바로 조치할 수 있도록 remediation note 중심으로 정리합니다.",
            f"추가 검토 맥락: {excerpt}",
        ],
        "ownership_plan": [
            "BD Lead: 입찰 자격 및 레퍼런스 증빙 정리",
            "Delivery Lead: 핵심 인력 가용성과 일정 적합성 확인",
            "Executive Approver: Go/Conditional Go 승인 조건 확정",
        ],
        "readiness_summary": (
            f"{title} 입찰 준비도는 현재 structured checklist를 기준으로 판단합니다. {excerpt}"
        ),
    }

def _bid_decision_handoff(title: str, goal: str, ctx: str) -> dict:
    excerpt = _ctx_excerpt(ctx, 1200)
    return {
        "handoff_summary": (
            f"{title} 의사결정 결과를 downstream bundle로 넘기기 위한 착수 요약입니다. "
            f"{goal}을 달성하기 위해 현재 procurement state를 그대로 이어받습니다. {excerpt}"
        ),
        "rfp_analysis_inputs": [
            "발주기관 핵심 니즈와 평가항목 가설을 먼저 정리합니다.",
            "hard filter와 source snapshot에서 확인된 필수 요구사항을 그대로 가져갑니다.",
            f"RFP 분석 참고 맥락: {excerpt}",
        ],
        "proposal_inputs": [
            "제안서 차별화 포인트는 recommendation evidence와 capability profile을 우선 반영합니다.",
            "Conditional Go 조건이 있다면 제안 전략과 리스크 대응 메시지에 포함합니다.",
            f"제안서 인풋 참고 맥락: {excerpt}",
        ],
        "performance_plan_inputs": [
            "수행계획서는 일정, 인력, 산출물, 리스크 관점에서 checklist 결과를 계승합니다.",
            "schedule/partner readiness와 보안·인프라 의무사항을 계획서 전제조건으로 둡니다.",
            f"수행계획 인풋 참고 맥락: {excerpt}",
        ],
        "next_steps": [
            "RFP 분석서 초안을 생성해 평가항목과 win strategy를 구체화합니다.",
            "제안서와 수행계획서 생성 전에 Conditional Go 보완 과제를 닫습니다.",
            "승인권자 리뷰용 결재 흐름에 연결할 핵심 메시지를 확정합니다.",
        ],
    }
