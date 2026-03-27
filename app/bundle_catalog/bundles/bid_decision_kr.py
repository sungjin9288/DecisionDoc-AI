"""bid_decision_kr bundle — 공공조달 Go/No-Go 의사결정 패키지 (한국어)."""
from app.bundle_catalog.spec import BundleSpec, DocumentSpec


BID_DECISION_KR = BundleSpec(
    id="bid_decision_kr",
    name_ko="입찰 참여 의사결정 패키지",
    name_en="Bid Decision Package",
    description_ko="공고 요약, Go/No-Go 메모, 입찰 준비 체크리스트, downstream handoff 요약을 생성합니다.",
    icon="🧭",
    prompt_language="ko",
    category="gov",
    prompt_hint=(
        "당신은 공공조달 Go/No-Go 의사결정을 지원하는 수주전략 리드입니다.\n"
        "작성 전 내부적으로 검토하세요: (1) blocking hard filter가 존재하는가, "
        "(2) soft-fit score와 missing data가 recommendation을 어떻게 제한하는가, "
        "(3) downstream bundle에 어떤 입력을 넘겨야 하는가.\n"
        "반드시 제공된 structured procurement state를 source of truth로 사용하세요.\n"
        "이미 계산된 hard filter, soft-fit score, recommendation을 임의로 뒤집지 마세요.\n"
        "결정 근거는 증거 기반으로 요약하고, 보완이 필요한 항목은 owner/action 중심으로 정리하세요.\n"
        "downstream handoff는 이후 `rfp_analysis_kr`, `proposal_kr`, `performance_plan_kr`에 바로 재사용할 수 있게 작성하세요.\n"
        "모든 내용은 한국어로 작성하세요."
    ),
    few_shot_example=(
        "## 공고 개요\n"
        "사업명: 행정안전부 AI 민원 서비스 고도화 사업 / 예산: 5억원 / 마감: 2026.04.30\n"
        "발주기관 핵심 니즈: 민원 상담 자동화 정확도 향상, 처리 리드타임 단축, 보안·개인정보 대응 강화\n\n"
        "## 추천 결론\n"
        "CONDITIONAL_GO — 핵심 도메인 적합도와 공공 레퍼런스는 충분하나, 최신 파트너 확약서와 제안 참여 인력 확정이 선행되어야 함\n\n"
        "## Hard Filter 결과\n"
        "- 필수 자격 및 인증: PASS — ISMS, 소프트웨어사업자 신고 충족\n"
        "- 파트너 준비도: UNKNOWN — 전문 파트너 확약서 최신본 필요\n\n"
        "## 제안 착수 인풋\n"
        "- RFP 분석: 평가항목 가설, 필수 요구사항, 발주기관 pain point 정리\n"
        "- 제안서: 공공 민원 AI 구축 레퍼런스, 보안 대응 경험, 단계별 차별화 메시지 반영\n"
        "- 수행계획: 파트너 확정 일정, PM/컨설턴트 배치, 보안 검수 절차 포함\n"
    ),
    docs=[
        DocumentSpec(
            key="opportunity_brief",
            template_file="bid_decision_kr/opportunity_brief.md.j2",
            json_schema={
                "type": "object",
                "required": [
                    "opportunity_summary",
                    "issuer_and_scope",
                    "commercial_terms",
                    "source_highlights",
                ],
                "properties": {
                    "opportunity_summary": {"type": "string"},
                    "issuer_and_scope": {"type": "string"},
                    "commercial_terms": {"type": "array", "items": {"type": "string"}},
                    "source_highlights": {"type": "array", "items": {"type": "string"}},
                },
            },
            stabilizer_defaults={
                "opportunity_summary": "",
                "issuer_and_scope": "",
                "commercial_terms": [],
                "source_highlights": [],
            },
            lint_headings=[
                "# 입찰 기회 브리프:",
                "## 공고 개요",
                "## 발주처 및 사업 범위",
                "## 상업 조건 및 일정",
                "## 원문 및 맥락 하이라이트",
            ],
            validator_headings=[
                "## 공고 개요",
                "## 발주처 및 사업 범위",
                "## 상업 조건 및 일정",
                "## 원문 및 맥락 하이라이트",
            ],
            critical_non_empty_headings=["## 공고 개요", "## 상업 조건 및 일정"],
        ),
        DocumentSpec(
            key="go_no_go_memo",
            template_file="bid_decision_kr/go_no_go_memo.md.j2",
            json_schema={
                "type": "object",
                "required": [
                    "recommendation_decision",
                    "hard_filter_findings",
                    "soft_fit_summary",
                    "decision_rationale",
                    "executive_notes",
                ],
                "properties": {
                    "recommendation_decision": {"type": "string"},
                    "hard_filter_findings": {"type": "array", "items": {"type": "string"}},
                    "soft_fit_summary": {"type": "string"},
                    "decision_rationale": {"type": "array", "items": {"type": "string"}},
                    "executive_notes": {"type": "string"},
                },
            },
            stabilizer_defaults={
                "recommendation_decision": "",
                "hard_filter_findings": [],
                "soft_fit_summary": "",
                "decision_rationale": [],
                "executive_notes": "",
            },
            lint_headings=[
                "# Go/No-Go 메모:",
                "## 추천 결론",
                "## Hard Filter 결과",
                "## Soft-fit 점수 해석",
                "## 결정 근거",
                "## 경영진 메모",
            ],
            validator_headings=[
                "## 추천 결론",
                "## Hard Filter 결과",
                "## Soft-fit 점수 해석",
                "## 결정 근거",
                "## 경영진 메모",
            ],
            critical_non_empty_headings=["## 추천 결론", "## 결정 근거"],
        ),
        DocumentSpec(
            key="bid_readiness_checklist",
            template_file="bid_decision_kr/bid_readiness_checklist.md.j2",
            json_schema={
                "type": "object",
                "required": [
                    "blocking_items",
                    "action_items",
                    "ownership_plan",
                    "readiness_summary",
                ],
                "properties": {
                    "blocking_items": {"type": "array", "items": {"type": "string"}},
                    "action_items": {"type": "array", "items": {"type": "string"}},
                    "ownership_plan": {"type": "array", "items": {"type": "string"}},
                    "readiness_summary": {"type": "string"},
                },
            },
            stabilizer_defaults={
                "blocking_items": [],
                "action_items": [],
                "ownership_plan": [],
                "readiness_summary": "",
            },
            lint_headings=[
                "# 입찰 준비 체크리스트:",
                "## 즉시 확인 필요 항목",
                "## 보완 필요 항목",
                "## 오너 및 일정",
                "## 최종 준비도 판단",
            ],
            validator_headings=[
                "## 즉시 확인 필요 항목",
                "## 보완 필요 항목",
                "## 오너 및 일정",
                "## 최종 준비도 판단",
            ],
            critical_non_empty_headings=["## 즉시 확인 필요 항목", "## 최종 준비도 판단"],
        ),
        DocumentSpec(
            key="proposal_kickoff_summary",
            template_file="bid_decision_kr/proposal_kickoff_summary.md.j2",
            json_schema={
                "type": "object",
                "required": [
                    "handoff_summary",
                    "rfp_analysis_inputs",
                    "proposal_inputs",
                    "performance_plan_inputs",
                    "next_steps",
                ],
                "properties": {
                    "handoff_summary": {"type": "string"},
                    "rfp_analysis_inputs": {"type": "array", "items": {"type": "string"}},
                    "proposal_inputs": {"type": "array", "items": {"type": "string"}},
                    "performance_plan_inputs": {"type": "array", "items": {"type": "string"}},
                    "next_steps": {"type": "array", "items": {"type": "string"}},
                },
            },
            stabilizer_defaults={
                "handoff_summary": "",
                "rfp_analysis_inputs": [],
                "proposal_inputs": [],
                "performance_plan_inputs": [],
                "next_steps": [],
            },
            lint_headings=[
                "# 제안 착수 요약:",
                "## 결정 요약",
                "## RFP 분석 인풋",
                "## 제안서 인풋",
                "## 수행계획 인풋",
                "## 다음 단계",
            ],
            validator_headings=[
                "## 결정 요약",
                "## RFP 분석 인풋",
                "## 제안서 인풋",
                "## 수행계획 인풋",
                "## 다음 단계",
            ],
            critical_non_empty_headings=["## 결정 요약", "## 다음 단계"],
        ),
    ],
)
