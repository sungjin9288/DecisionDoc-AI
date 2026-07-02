"""Deterministic synthesis helpers for building a procurement Decision Council session.

``CouncilSynthesisMixin`` holds the private, stateless-ish builder methods used
by ``DecisionCouncilService.run_procurement_council`` to turn a
``ProcurementDecisionRecord`` into role opinions, consensus, and a drafting
handoff. Split out of ``decision_council_service.py`` (moved verbatim; no
behavior changes) to keep each module under the file-size ceiling.
"""
from __future__ import annotations

from app.schemas import (
    DecisionCouncilConsensus,
    DecisionCouncilHandoff,
    DecisionCouncilRoleOpinion,
    ProcurementDecisionRecord,
)


class CouncilSynthesisMixin:
    """Private builder methods for role opinions, consensus, and handoff."""

    def _build_role_opinions(
        self,
        *,
        goal: str,
        procurement_record: ProcurementDecisionRecord,
        top_risks: list[str],
        disagreements: list[str],
        conditions: list[str],
        open_questions: list[str],
    ) -> list[DecisionCouncilRoleOpinion]:
        opportunity = procurement_record.opportunity
        recommendation = procurement_record.recommendation
        assert opportunity is not None
        assert recommendation is not None

        common_evidence = self._build_evidence_refs(procurement_record)
        requirement_stance = self._map_stance(
            recommendation.value,
            caution=bool(procurement_record.missing_data),
        )
        risk_stance = self._map_stance(
            recommendation.value,
            caution=bool(procurement_record.checklist_items or procurement_record.missing_data),
            prefer_block_on_no_go=True,
        )
        strategist_stance = self._map_stance(recommendation.value, caution=bool(conditions))
        compliance_stance = self._map_stance(
            recommendation.value,
            caution=bool(procurement_record.missing_data or procurement_record.hard_filters),
            prefer_block_on_no_go=True,
        )
        drafting_stance = self._map_stance(recommendation.value, caution=bool(conditions))

        role_payloads = [
            {
                "role": "Requirement Analyst",
                "stance": requirement_stance,
                "summary": (
                    f"{opportunity.title} 공고는 {goal} 관점에서 검토할 가치가 있으며, "
                    f"발주기관={opportunity.issuer or '미상'}, 예산={opportunity.budget or '미확인'}, "
                    f"마감={opportunity.deadline or '미확인'} 신호를 우선 source of truth로 삼아야 합니다."
                ),
                "evidence_refs": common_evidence,
                "risks": top_risks[:3],
                "disagreements": disagreements[:1],
                "recommended_actions": [
                    "공고 핵심 요구사항과 당사 capability evidence를 1:1로 대조합니다.",
                    "bid_decision_kr에 마감·예산·입찰방식과 같은 운영 조건을 먼저 고정합니다.",
                ],
            },
            {
                "role": "Risk Reviewer",
                "stance": risk_stance,
                "summary": (
                    f"현재 recommendation={recommendation.value}이며, hard filter / checklist / missing data 중 "
                    "문서상 확정 사실처럼 쓰면 안 되는 리스크를 우선 제어해야 합니다."
                ),
                "evidence_refs": common_evidence,
                "risks": top_risks,
                "disagreements": disagreements[:2],
                "recommended_actions": [
                    "blocking fail과 action_needed 항목을 narrative보다 먼저 요약합니다.",
                    "확인되지 않은 데이터는 확정 표현 대신 pending question으로 남깁니다.",
                ],
            },
            {
                "role": "Domain Strategist",
                "stance": strategist_stance,
                "summary": (
                    f"soft_fit_score={self._format_soft_fit(procurement_record)} 기준으로, "
                    f"현재 최선의 방향은 {self._render_direction_label(recommendation.value)}입니다."
                ),
                "evidence_refs": common_evidence,
                "risks": top_risks[:2],
                "disagreements": disagreements[:1],
                "recommended_actions": self._build_strategy_actions(recommendation.value, conditions),
            },
            {
                "role": "Compliance Reviewer",
                "stance": compliance_stance,
                "summary": (
                    "필수 자격, 인증, 일정, 파트너/레퍼런스 충족 여부를 확정 근거와 함께 표기해야 하며, "
                    "근거가 없으면 충족으로 쓰지 않아야 합니다."
                ),
                "evidence_refs": common_evidence,
                "risks": top_risks[:3],
                "disagreements": disagreements[:1],
                "recommended_actions": [
                    "자격/인증/실적 부족 신호를 별도 섹션으로 노출합니다.",
                    "미충족 또는 미확인 항목은 조건부 진행 여부와 함께 표시합니다.",
                ],
            },
            {
                "role": "Drafting Lead",
                "stance": drafting_stance,
                "summary": (
                    "bid_decision_kr는 회의 transcript가 아니라 경영 판단 문서이므로, "
                    "권고 방향·근거·조건·금지 주장 범위를 짧고 명시적으로 정리해야 합니다."
                ),
                "evidence_refs": common_evidence,
                "risks": top_risks[:2],
                "disagreements": disagreements[:1],
                "recommended_actions": [
                    "첫 단락에서 recommendation 방향과 조건을 명시합니다.",
                    "열린 질문과 후속 조치를 마지막 decision gate로 분리합니다.",
                    *([f"추가 확인 질문: {open_questions[0]}"] if open_questions else []),
                ],
            },
        ]
        return [DecisionCouncilRoleOpinion.model_validate(payload) for payload in role_payloads]

    def _build_consensus(
        self,
        *,
        procurement_record: ProcurementDecisionRecord,
        top_risks: list[str],
        disagreements: list[str],
        conditions: list[str],
        open_questions: list[str],
    ) -> DecisionCouncilConsensus:
        recommendation = procurement_record.recommendation
        assert recommendation is not None
        direction = self._map_direction(recommendation.value)
        alignment = self._map_alignment(
            recommendation.value,
            disagreements=disagreements,
            conditions=conditions,
            open_questions=open_questions,
        )
        return DecisionCouncilConsensus.model_validate(
            {
                "alignment": alignment,
                "recommended_direction": direction,
                "summary": (
                    f"Council은 procurement recommendation={recommendation.value}를 기준으로 "
                    f"{self._render_direction_label(recommendation.value)} 방향을 권고합니다. "
                    "bid_decision_kr는 결론과 근거, 조건, 미해결 질문을 분리해 전달해야 합니다."
                ),
                "strategy_options": self._build_strategy_options(recommendation.value, conditions),
                "disagreements": disagreements,
                "top_risks": top_risks,
                "conditions": conditions,
                "open_questions": open_questions,
            }
        )

    def _build_handoff(
        self,
        *,
        goal: str,
        context: str,
        constraints: str,
        procurement_record: ProcurementDecisionRecord,
        top_risks: list[str],
        conditions: list[str],
        open_questions: list[str],
        consensus: DecisionCouncilConsensus,
    ) -> DecisionCouncilHandoff:
        recommendation = procurement_record.recommendation
        opportunity = procurement_record.opportunity
        assert recommendation is not None
        assert opportunity is not None
        must_include = [
            f"최종 권고 방향: {consensus.recommended_direction}",
            f"현재 procurement recommendation: {recommendation.value}",
            f"recommendation summary: {recommendation.summary or '요약 없음'}",
            f"공고명: {opportunity.title}",
            f"발주기관: {opportunity.issuer or '미상'} / 예산: {opportunity.budget or '미확인'} / 마감: {opportunity.deadline or '미확인'}",
        ]
        must_address = [
            *conditions[:4],
            *top_risks[:4],
        ]
        must_not_claim = self._build_prohibited_claims(procurement_record)
        return DecisionCouncilHandoff.model_validate(
            {
                "target_bundle_type": "bid_decision_kr",
                "recommended_direction": consensus.recommended_direction,
                "drafting_brief": (
                    f"목표는 '{goal}'에 맞춰 {opportunity.title} 입찰 여부 판단을 경영진이 빠르게 검토할 수 있는 "
                    "bid_decision_kr를 작성하는 것입니다. "
                    f"현재 방향은 {self._render_direction_label(recommendation.value)}이며, "
                    "권고 결론과 근거, 조건, 열린 질문을 명시적으로 구분하세요."
                    + (f" 추가 맥락: {context.strip()}" if context.strip() else "")
                    + (f" 제약: {constraints.strip()}" if constraints.strip() else "")
                ),
                "must_include": must_include,
                "must_address": must_address,
                "must_not_claim": must_not_claim,
                "open_questions": open_questions,
                "source_procurement_decision_id": procurement_record.decision_id,
            }
        )

    def _build_top_risks(
        self,
        *,
        procurement_record: ProcurementDecisionRecord,
        hard_failures: list,
        actionable_items: list,
        missing_data: list[str],
    ) -> list[str]:
        risks: list[str] = []
        for item in hard_failures[:3]:
            reason = item.reason or f"{item.label} 조건 미충족"
            risks.append(f"Hard filter blocking: {item.label} — {reason}")
        for item in actionable_items[:4]:
            remediation = item.remediation_note or item.status
            risks.append(f"Checklist follow-up: [{item.category}] {item.title} — {remediation}")
        for item in missing_data[:3]:
            risks.append(f"Missing evidence: {item}")
        if procurement_record.soft_fit_status and procurement_record.soft_fit_status != "scored":
            risks.append(f"Soft-fit score status={procurement_record.soft_fit_status} 이므로 과신을 피해야 합니다.")
        return self._unique(risks)[:6] or ["치명적 blocker는 없지만 원문과 capability evidence 재확인이 필요합니다."]

    def _build_conditions(
        self,
        *,
        recommendation_value: str,
        actionable_items: list,
        missing_data: list[str],
    ) -> list[str]:
        conditions: list[str] = []
        if recommendation_value == "CONDITIONAL_GO":
            conditions.append("조건부 진행 전 필수 보완 항목의 owner와 due date를 확정해야 합니다.")
        if recommendation_value == "NO_GO":
            conditions.append("대외 제출 진행보다 내부 의사결정 메모와 예외 사유 검토를 우선해야 합니다.")
        for item in actionable_items[:3]:
            conditions.append(f"{item.title} 항목의 remediation 근거를 문서화해야 합니다.")
        for item in missing_data[:2]:
            conditions.append(f"'{item}' 관련 증빙 또는 확인 주체를 명시해야 합니다.")
        return self._unique(conditions)[:5]

    def _build_open_questions(self, *, missing_data: list[str], actionable_items: list) -> list[str]:
        questions = [f"{item}는 현재 확보됐는가?" for item in missing_data[:4]]
        for item in actionable_items[:3]:
            questions.append(f"{item.title}의 owner와 완료 기준은 무엇인가?")
        return self._unique(questions)[:6]

    def _build_disagreements(
        self,
        *,
        recommendation_value: str,
        hard_failures: list,
        actionable_items: list,
        missing_data: list[str],
        soft_fit_score: float | None,
    ) -> list[str]:
        disagreements: list[str] = []
        if recommendation_value == "CONDITIONAL_GO":
            disagreements.append(
                "Domain Strategist는 기회 적합성을 이유로 조건부 진행을 지지하지만, Risk Reviewer와 Compliance Reviewer는 "
                "미해결 checklist와 missing data가 문서에서 과소표현되는 것을 반대합니다."
            )
        if recommendation_value == "NO_GO" and (soft_fit_score or 0) >= 60:
            disagreements.append(
                "Domain Strategist는 전략적 레퍼런스 또는 관계 관리 가치가 남아 있다고 보지만, "
                "Compliance Reviewer는 현재 blocker 기준으로는 입찰 진행을 지지하지 않습니다."
            )
        if recommendation_value == "GO" and (actionable_items or missing_data):
            disagreements.append(
                "Requirement Analyst와 Domain Strategist는 GO 방향에 무게를 두지만, Risk Reviewer는 "
                "남은 보완 항목을 확정 사실처럼 쓰지 않는 조건이 필요하다고 봅니다."
            )
        if hard_failures and recommendation_value != "NO_GO":
            disagreements.append(
                "Hard filter blocker가 남아 있어 Risk Reviewer는 방향을 더 보수적으로 해석해야 한다고 봅니다."
            )
        return self._unique(disagreements)[:3]

    def _build_strategy_options(self, recommendation_value: str, conditions: list[str]) -> list[str]:
        if recommendation_value == "GO":
            return [
                "즉시 Go로 정리하고 핵심 근거와 차별화 포인트를 문서 전면에 배치",
                "남은 확인 항목이 있으면 승인 조건으로만 짧게 부기",
            ]
        if recommendation_value == "CONDITIONAL_GO":
            return [
                "조건부 Go로 정리하고 보완 선행조건을 별도 gate로 제시",
                "조건 해소 전에는 proposal/RFP 상세 계획으로 확장하지 않음",
                *conditions[:1],
            ]
        return [
            "현 시점 No-Go로 정리하고 blocker와 missing evidence를 명시",
            "전략 가치가 있다면 예외 검토 또는 future pipeline 후보로만 기록",
        ]

    def _build_strategy_actions(self, recommendation_value: str, conditions: list[str]) -> list[str]:
        if recommendation_value == "GO":
            return [
                "bid_decision_kr에서 즉시 진행 근거를 명시합니다.",
                "downstream 문서로 넘길 차별화 포인트를 먼저 정리합니다.",
            ]
        if recommendation_value == "CONDITIONAL_GO":
            return [
                "조건부 진행 전제와 승인 조건을 한 문단으로 고정합니다.",
                *conditions[:2],
            ]
        return [
            "No-Go 판단의 blocker를 경영진이 한 번에 읽을 수 있게 정리합니다.",
            "예외 진행이 필요한 경우 override review 필요성을 명시합니다.",
        ]

    def _build_prohibited_claims(self, procurement_record: ProcurementDecisionRecord) -> list[str]:
        claims: list[str] = []
        for item in procurement_record.missing_data[:4]:
            claims.append(f"'{item}'가 확보됐다고 단정하지 말 것")
        for item in procurement_record.hard_filters:
            if item.blocking and item.status == "fail":
                claims.append(f"{item.label} 조건을 충족한다고 쓰지 말 것")
        if procurement_record.recommendation and procurement_record.recommendation.value == "NO_GO":
            claims.append("현재 상태를 사실상 GO 또는 제출 확정으로 표현하지 말 것")
        return self._unique(claims)[:6]

    def _build_evidence_refs(self, procurement_record: ProcurementDecisionRecord) -> list[str]:
        opportunity = procurement_record.opportunity
        refs = [
            f"decision_id={procurement_record.decision_id}",
            f"recommendation={procurement_record.recommendation.value if procurement_record.recommendation else 'none'}",
            f"soft_fit_status={procurement_record.soft_fit_status}",
        ]
        if opportunity is not None:
            refs.extend(
                [
                    f"opportunity.title={opportunity.title}",
                    f"opportunity.issuer={opportunity.issuer or '미상'}",
                ]
            )
        if procurement_record.source_snapshots:
            refs.append(f"latest_snapshot_id={procurement_record.source_snapshots[-1].snapshot_id}")
        return refs

    @staticmethod
    def _map_direction(recommendation_value: str) -> str:
        if recommendation_value == "GO":
            return "proceed"
        if recommendation_value == "CONDITIONAL_GO":
            return "proceed_with_conditions"
        return "do_not_proceed"

    @staticmethod
    def _render_direction_label(recommendation_value: str) -> str:
        if recommendation_value == "GO":
            return "즉시 진행"
        if recommendation_value == "CONDITIONAL_GO":
            return "조건부 진행"
        return "현 시점 미진행"

    @staticmethod
    def _map_alignment(
        recommendation_value: str,
        *,
        disagreements: list[str],
        conditions: list[str],
        open_questions: list[str],
    ) -> str:
        if recommendation_value == "GO" and not disagreements and not conditions and not open_questions:
            return "aligned"
        if recommendation_value == "NO_GO" and not disagreements:
            return "aligned"
        if len(disagreements) >= 2:
            return "contested"
        return "mixed"

    @staticmethod
    def _map_stance(
        recommendation_value: str,
        *,
        caution: bool = False,
        prefer_block_on_no_go: bool = False,
    ) -> str:
        if recommendation_value == "NO_GO":
            return "block" if prefer_block_on_no_go else "caution"
        if recommendation_value == "CONDITIONAL_GO":
            return "caution"
        return "caution" if caution else "support"

    @staticmethod
    def _format_soft_fit(procurement_record: ProcurementDecisionRecord) -> str:
        if procurement_record.soft_fit_score is None:
            return str(procurement_record.soft_fit_status)
        return f"{procurement_record.soft_fit_score:.1f} ({procurement_record.soft_fit_status})"

    @staticmethod
    def _unique(values: list[str]) -> list[str]:
        seen: set[str] = set()
        ordered: list[str] = []
        for value in values:
            normalized = str(value or "").strip()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            ordered.append(normalized)
        return ordered
