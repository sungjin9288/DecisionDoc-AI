"""Mock provider — returns realistic sample content without calling any LLM.

For the tech_decision bundle, hardcoded English sample data is returned.
For other bundles, contextual Korean sample data is generated from the
requirements (title, goal, context) so the output shows meaningful document
direction — including slide-by-slide PPT construction guides — even without
a real API key.
"""
import base64

from typing import Any

from app.providers.base import Provider


_MOCK_PNG_BASE64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO5tm8sAAAAASUVORK5CYII="
)


class MockProvider(Provider):
    name = "mock"

    def extract_attachment_text(self, filename: str, raw: bytes, *, request_id: str) -> str:
        stem = filename.rsplit(".", 1)[0]
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        source_label = "스캔 PDF" if ext == "pdf" else "시각 자료"
        return (
            f"[AI 분석 첨부: {filename}]\n"
            f"파일 '{stem}'은 {source_label}로 인식되었습니다.\n"
            "추정 내용:\n"
            "- 제목 또는 캡션이 포함된 이미지/도표/문서일 가능성이 높습니다.\n"
            "- 문서에는 핵심 메시지, 시각자료 설명, 활용 포인트를 함께 반영하세요.\n"
            "- 필요하면 원본 이미지 주변의 맥락 설명을 추가로 입력하세요."
        )

    def generate_bundle(
        self,
        requirements: dict[str, Any],
        *,
        schema_version: str,
        request_id: str,
        bundle_spec: Any = None,
        feedback_hints: str = "",
    ) -> dict[str, Any]:
        if bundle_spec is not None and bundle_spec.id != "tech_decision":
            return self._mock_from_spec(bundle_spec, requirements)

        assumptions = requirements.get("assumptions") or [
            "Current requirements are stable for this MVP.",
            "Windows local development is the primary environment.",
        ]
        checks = [
            "Validate document section completeness.",
            "Confirm output readability for mixed audience.",
        ]

        return {
            "adr": {
                "decision": "Use FastAPI API-only service with schema-first provider bundle generation.",
                "options": [
                    "Option A: Keep mock provider default and add adapters.",
                    "Option B: Immediate full LLM dependency (deferred).",
                ],
                "risks": [
                    "Provider SDK integration may fail due to missing keys or environment setup.",
                    "Generated bundle may violate schema if provider output drifts.",
                ],
                "assumptions": assumptions,
                "checks": checks,
                "next_actions": [
                    "Run live-provider tests in secured CI or local env.",
                    "Add provider-specific prompt/version tracking.",
                ],
            },
            "onepager": {
                "problem": "Decision documentation workflows are inconsistent and manual.",
                "recommendation": "Generate standardized bundle once, then render all docs from templates.",
                "impact": [
                    "Improves consistency across ADR, onepager, eval plan, and ops checklist.",
                    "Enables regression testing for structure and validator conformance.",
                ],
                "checks": checks,
            },
            "eval_plan": {
                "metrics": ["Generation success rate", "Validator pass rate", "Response latency"],
                "test_cases": [
                    "Minimal payload with defaults",
                    "Invalid input returns 422",
                    "Provider failure returns PROVIDER_FAILED",
                ],
                "failure_criteria": [
                    "Missing required bundle keys",
                    "Rendered docs fail validator checks",
                ],
                "monitoring": [
                    "Track status codes and provider name in metadata.",
                    "Avoid logging raw payloads containing sensitive text.",
                ],
            },
            "ops_checklist": {
                "security": [
                    "Use environment variables for provider API keys only.",
                    "Never include keys in source, logs, or docs examples.",
                ],
                "reliability": [
                    "Enforce one provider call per request with timeout guard.",
                    "Fail closed on JSON/schema validation errors.",
                ],
                "cost": [
                    "Default provider is mock for offline and low-cost operation.",
                    "Use optional cache to reduce repeated live-provider calls.",
                ],
                "operations": [
                    "Use provider env switch: mock|openai|gemini.",
                    "Run networked tests only with pytest -m live.",
                ],
            },
        }

    def _mock_from_spec(self, bundle_spec: Any, requirements: dict[str, Any]) -> dict[str, Any]:
        title = requirements.get("title") or "프로젝트"
        goal  = requirements.get("goal")  or "목표 달성"
        ctx_parts = [
            str(requirements.get("context") or "").strip(),
            str(requirements.get("_procurement_context") or "").strip(),
            str(requirements.get("_decision_council_context") or "").strip(),
        ]
        ctx = "\n\n".join(part for part in ctx_parts if part)
        bundle_id = bundle_spec.id
        result: dict[str, Any] = {}
        for doc in bundle_spec.docs:
            builder = _CONTENT_BUILDERS.get((bundle_id, doc.key))
            if builder:
                result[doc.key] = builder(title, goal, ctx)
            else:
                result[doc.key] = self._generic_doc(doc, title, goal, ctx)
        return result

    @staticmethod
    def _generic_doc(doc_spec: Any, title: str, goal: str, ctx: str = "") -> dict[str, Any]:
        section: dict[str, Any] = {}
        ctx_line = f" 참고 맥락: {_ctx_excerpt(ctx, 220)}" if ctx else ""
        for field_name, default in doc_spec.stabilizer_defaults.items():
            if isinstance(default, str):
                section[field_name] = (
                    f"{title} 프로젝트에서 {field_name} 항목은 {goal}을 달성하기 위한 "
                    f"핵심 요소로, 구체적인 실행 계획과 기대 효과를 중심으로 작성되어야 합니다.{ctx_line}"
                )
            elif isinstance(default, list):
                section[field_name] = [
                    f"{title} — {field_name} 세부 항목 1: 실행 전략 및 방향",
                    f"{title} — {field_name} 세부 항목 2: 기대 효과 및 성과 지표",
                ]
                if ctx_line:
                    section[field_name].append(f"{title} — {field_name} 참고 맥락: {_ctx_excerpt(ctx, 160)}")
            else:
                section[field_name] = default
        return section

    def generate_raw(self, prompt: str, *, request_id: str, max_output_tokens: int | None = None) -> str:
        """Generate raw JSON for testing (no LLM call).

        Handles two prompt types:
        - Pattern analysis prompt (contains '공통된 문서 유형 패턴'): returns bundle detection JSON
        - Sketch prompt (default): returns section/slide outline JSON
        """
        import json as _json

        # Detect pattern analysis prompt from BundleAutoExpander
        if "공통된 문서 유형 패턴" in prompt:
            return _json.dumps({
                "detected": True,
                "bundle_id": "mock_auto_bundle_kr",
                "bundle_name": "모의 자동 번들",
                "description": "테스트용 자동 생성 번들입니다.",
                "icon": "🤖",
                "sections": [
                    {"id": "overview", "title": "개요", "required": True},
                    {"id": "details", "title": "세부 내용", "required": True},
                    {"id": "action_plan", "title": "실행 계획", "required": True},
                    {"id": "risks", "title": "리스크 분석", "required": False},
                    {"id": "summary", "title": "요약 및 결론", "required": True},
                ],
                "confidence": 0.85,
            }, ensure_ascii=False)

        if "report workflow planner" in prompt.lower():
            return _json.dumps({
                "objective": "보고서 목적과 승인 흐름을 한눈에 이해할 수 있게 구성합니다.",
                "audience": "PM, 대표, 최종 의사결정권자",
                "executive_message": "기획 승인 후 장표 제작으로 이어지는 단계형 보고서 품질 관리를 적용합니다.",
                "table_of_contents": ["핵심 메시지", "현황 진단", "제안 방향", "실행 계획", "기대 효과", "승인 요청"],
                "slide_plans": [
                    {
                        "slide_id": f"slide-{idx:03d}",
                        "page": idx,
                        "title": title,
                        "purpose": f"{title} 내용을 의사결정자가 검토할 수 있게 설명합니다.",
                        "key_message": f"{title} 기준의 핵심 판단 포인트를 제시합니다.",
                        "layout": "상단 핵심 메시지, 좌측 근거, 우측 시각자료",
                        "visual_direction": "요약 카드와 흐름도 중심",
                        "required_evidence": ["입력 요구사항", "첨부자료 요약"],
                    }
                    for idx, title in enumerate(["핵심 메시지", "현황 진단", "제안 방향", "실행 계획", "기대 효과", "승인 요청"], start=1)
                ],
                "open_questions": ["최종 승인자는 누구인지 확인이 필요합니다."],
                "risk_notes": ["첨부자료가 부족하면 장표별 근거가 약해질 수 있습니다."],
            }, ensure_ascii=False)

        if "slide draft generator" in prompt.lower():
            return _json.dumps({
                "slides": [
                    {
                        "slide_id": f"slide-{idx:03d}",
                        "page": idx,
                        "title": title,
                        "body": f"{title} 장표는 핵심 메시지, 근거, 실행 포인트를 3개 bullet로 정리합니다.",
                        "visual_spec": "우측에 요약 카드와 간단한 프로세스 다이어그램 배치",
                        "speaker_note": f"PM은 {title}에서 의사결정 포인트와 다음 액션을 설명합니다.",
                        "source_refs": ["approved_planning"],
                    }
                    for idx, title in enumerate(["핵심 메시지", "현황 진단", "제안 방향", "실행 계획", "기대 효과", "승인 요청"], start=1)
                ]
            }, ensure_ascii=False)

        # Default: sketch prompt
        is_ppt = "ppt_slides" in prompt and '"page"' in prompt

        sections = [
            {"heading": "## 개요 및 배경", "bullets": ["현황 분석 결과 핵심 과제 3가지 도출", "목표 달성을 위한 우선순위 설정", "기대 효과 및 성과 지표 정의"]},
            {"heading": "## 핵심 내용", "bullets": ["주요 의사결정 사항 및 근거", "실행 방안 및 단계별 계획", "리스크 관리 방안"]},
            {"heading": "## 실행 계획", "bullets": ["단계별 일정 및 담당자", "예산 및 자원 배분", "성과 측정 및 피드백 체계"]},
        ]
        ppt_slides = None
        if is_ppt:
            ppt_slides = [
                {"page": 1, "title": "표지 및 목차", "key_content": "프로젝트 목적·발표자·날짜"},
                {"page": 2, "title": "현황 및 문제점", "key_content": "핵심 과제 3가지 + 근거 데이터"},
                {"page": 3, "title": "제안 방향", "key_content": "솔루션 개요 및 차별점"},
                {"page": 4, "title": "실행 계획", "key_content": "단계별 로드맵 + 일정"},
                {"page": 5, "title": "기대 효과", "key_content": "수치 목표 + ROI"},
                {"page": 6, "title": "Q&A", "key_content": "예상 질문 및 답변 포인트"},
            ]
        return _json.dumps(
            {"sections": sections, "ppt_slides": ppt_slides},
            ensure_ascii=False,
        )

    def consume_usage_tokens(self) -> dict[str, int] | None:
        return {"prompt_tokens": 0, "output_tokens": 0, "total_tokens": 0}

    def generate_visual_asset(
        self,
        prompt: str,
        *,
        request_id: str,
        size: str = "1536x1024",
        style: str = "natural",
    ) -> dict[str, Any]:
        return {
            "media_type": "image/png",
            "data": base64.b64decode(_MOCK_PNG_BASE64),
            "revised_prompt": prompt,
            "model": "mock-image",
        }


# ===========================================================================
# Slide helper
# ===========================================================================

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


# ===========================================================================
# proposal_kr builders
# ===========================================================================

def _proposal_business_understanding(title: str, goal: str, ctx: str) -> dict:
    subject = _project_subject(title)
    ctx_line = f" {ctx}" if ctx else ""
    return {
        "executive_summary": (
            "본 제안은 핵심 정책 목표를 공공기관이 실제 운영 KPI로 관리할 수 있도록 데이터 통합, AI 분석, 운영 대시보드를 하나의 사업 범위로 묶은 안입니다. "
            "사업 배경과 현황 문제를 정책 목표와 연결해 설명하고, 단계별 추진 전략과 기대효과를 같은 KPI 체계 안에서 제시해 평가위원이 실현 가능성과 효과성을 동시에 확인할 수 있게 구성합니다. "
            "또한 초기 구축과 파일럿, 확산 단계를 구분해 예산 집행과 성과 검증 시점을 명확히 합니다."
        ),
        "project_background": (
            f"{subject} 사업은 공공 서비스 디지털 전환과 현장 운영 효율 개선을 동시에 요구합니다.{ctx_line} "
            "공공 서비스 디지털 전환 가속화와 AI 기술의 급격한 발전으로 인해, "
            "기존 수작업 중심의 업무 프로세스를 AI 기반 업무 지원 체계로 전환하는 것이 "
            "국가 경쟁력 강화와 서비스 품질 향상을 위한 핵심 과제로 부상하고 있습니다."
        ),
        "current_issues": [
            "기존 시스템의 노후화로 인한 처리 속도 저하 및 운영 비용 증가",
            "부서 간 데이터 사일로로 인한 통합 분석 및 의사결정 지연",
            "수작업 중심 업무로 인한 오류 발생률 증가와 담당자 업무 부담 가중",
            "실시간 현황 파악 불가로 인한 선제적 대응 체계 부재",
        ],
        "project_objectives": [
            "핵심 업무 자동화 | 주요 프로세스 자동화율 65% 달성 | 월간 자동처리율, 인력 투입시간",
            "정책 목표 달성 | 핵심 정책 목표와 직접 연결되는 운영 KPI 체계 구축 | KPI 달성률, 정책 반영 리드타임",
            "실시간 대응 체계 | 이상 징후 탐지 후 5분 이내 알림 전파 | 탐지-알림 지연시간, 대응 건수",
            "효율성 개선 | 운영 비용 20% 절감 및 처리 속도 2배 향상 | 건당 처리원가, 평균 처리시간",
        ],
        "evaluation_alignment": [
            "사업 이해도 | 정책 목표와 현행 병목을 정량 지표와 함께 재정리해 발주 배경의 타당성을 분명히 제시 | 사업 배경, 문제점, 목표 표",
            "실행 가능성 | 단계별 구축 범위와 산출물, 승인 게이트를 연결해 납품 가능성과 일정 현실성을 설명 | 사업 범위 요약, 수행 일정, 산출물 계획",
            "효과성 | 처리시간·오류율·운영비 절감 KPI를 사전 정의해 예산 대비 효과를 측정 가능한 구조로 제시 | 기대효과, ROI, 성과 모니터링 계획",
        ],
        "target_users": [
            "사업 담당 공무원 및 운영 관리자 | 사업 집행 현황·성과지표를 통합 모니터링해야 함 | 실시간 성과판과 의사결정 속도 향상",
            "현장 실무자 및 데이터 입력 담당자 | 반복 입력·검증 업무를 줄이고 오류를 낮추고자 함 | 자동 검증과 예외 처리 중심 업무 전환",
            "경영진 및 의사결정자 | 예산 집행 효과와 리스크를 요약 보고받아야 함 | 대시보드 기반 신속한 승인·보완 판단",
            "일반 국민 | 서비스 응답 속도와 정확도 향상을 기대함 | 체감 만족도와 접근성 개선",
        ],
        "scope_summary": (
            "본 사업의 범위는 AI 시스템 설계·개발·운영 전 과정을 포함합니다. "
            "1단계(3개월): 현황 분석 및 요구사항 정의, 2단계(6개월): 핵심 AI 모듈 개발 및 연동, "
            "3단계(3개월): 파일럿 운영 및 성과 검증 후 전면 확산으로 구성됩니다."
        ),
        "total_slides": 11,
        "slide_outline": [
            _slide(1, "표지",
                   f"사업명: {title} | 발주기관명 | 제안사명 | 제안일자",
                   "브랜드 색상 그라디언트 배경(진한 네이비 또는 딥퍼플). 사업명은 중앙 대형 Bold 폰트. 하단에 발주기관·제안사 로고 좌우 배치."),
            _slide(2, "목차",
                   "① 사업 배경 및 필요성 ② 현황 및 문제점(AS-IS) ③ 사업 목표 ④ 대상 사용자 ⑤ 사업 범위 ⑥ 추진 전략 ⑦ 기대 효과 ⑧ 제안사 역량",
                   "좌측에 번호·목차 텍스트, 우측에 관련 아이콘 또는 일러스트. 각 항목에 슬라이드 번호 표기."),
            _slide(3, "사업 추진 배경",
                   f"정책 환경 변화 + 기술 트렌드(AI·빅데이터 확산) + {subject} 필요성 3단 구조",
                   "3단 레이아웃(정책·기술·필요성). 상단에 인용 통계. 아이콘+짧은 설명 카드 형태 권장."),
            _slide(4, "현황 분석 (AS-IS)",
                   "현재 업무 흐름도 + 주요 Pain Point 3~4개 강조. 수치로 문제 심각성 표현",
                   "좌측: 현재 프로세스 플로우차트. 우측: Pain Point 카드(빨간 강조색). 숫자(오류율·처리시간) 크게 표시."),
            _slide(5, "문제점 심화 분석",
                   "4대 핵심 문제점을 각각 원인→영향→손실규모 구조로 서술",
                   "2×2 매트릭스 또는 4분할 카드 레이아웃. 문제별 아이콘+임팩트 문구."),
            _slide(6, "사업 목표 및 비전",
                   "비전 선언문 + 3~4개 정량 목표(처리속도 ○%↑, 비용 ○%↓) + 단계별 달성 로드맵",
                   "중앙에 비전 문구(대형 인용 스타일). 하단에 목표 지표를 아이콘+숫자 카드로 배열."),
            _slide(7, "핵심 추진 과제",
                   "과제 1: 데이터 통합 플랫폼 / 과제 2: AI 모델 개발 / 과제 3: 운영 자동화 / 과제 4: 성과 관리",
                   "가로 타임라인 또는 4열 카드. 각 과제에 번호+아이콘+한 줄 설명."),
            _slide(8, "주요 대상 사용자",
                   "사용자 페르소나 3~4개: 역할·니즈·기대 효과. 이해관계자 지도(Power-Interest Grid)",
                   "좌측: 페르소나 카드. 우측: 이해관계자 매트릭스. 따뜻한 컬러 포인트."),
            _slide(9, "사업 범위",
                   "In-Scope vs Out-of-Scope 명확 구분. 3단계 구축 로드맵 요약",
                   "좌우 분할(In/Out). 각 항목에 체크/X 아이콘. 하단에 단계별 로드맵 바."),
            _slide(10, "기대 효과 요약",
                   "정량 효과(수치) 3개 + 정성 효과(텍스트) 2개. ROI 하이라이트",
                   "상단: 숫자 강조 인포그래픽. 하단: 정성 효과 아이콘 카드. 녹색 계열 포인트."),
            _slide(11, "제안사 역량 소개",
                   "유사 프로젝트 수행 실적 + 핵심 기술 역량 + 인증·수상 실적",
                   "로고+실적 리스트 레이아웃. 수행 사례는 Before/After 축약 형태. 신뢰감 있는 블루 계열."),
        ],
    }


def _proposal_tech_proposal(title: str, goal: str, ctx: str) -> dict:
    return {
        "technical_summary": (
            f"{title}의 기술 제안은 공공 보안 기준을 충족하는 데이터 수집·AI 처리·운영 통제 구조를 하나의 아키텍처로 설계한 것이 핵심입니다. "
            f"{goal} 달성을 위해 모델 성능뿐 아니라 설명 가능성, 장애 격리, 운영 확장성까지 초기 설계에 포함했고, "
            "감사 대응과 유지보수 편의성을 높이기 위해 로그·권한·배포 체계를 함께 제안합니다."
        ),
        "tech_stack": [
            "AI 서비스 백엔드 | Python 3.11 / FastAPI | 업무별 AI 기능 API 게이트웨이와 서비스 오케스트레이션",
            "모델 학습·추론 | PyTorch / Hugging Face Transformers | 공공 도메인 특화 모델 튜닝 및 추론",
            "실시간 이벤트 처리 | Apache Kafka | 센서·업무 이벤트 스트리밍 및 비동기 처리",
            "데이터 계층 | PostgreSQL + Redis | 정형 데이터 영속화와 조회 캐시 최적화",
            "운영 인프라 | Kubernetes (EKS) | 무중단 배포와 서비스별 탄력 확장",
            "운영자 UI | React + TypeScript | 현황판·알림·리포트 중심 대시보드 제공",
        ],
        "architecture_overview": (
            f"{title} 시스템은 마이크로서비스 아키텍처를 기반으로 설계됩니다. "
            "데이터 수집 레이어 → AI 처리 레이어 → 결과 제공 레이어 3계층 구조로 구성되며, "
            "각 서비스는 독립적으로 확장 가능하도록 설계하여 장애 격리 및 탄력적 운영을 보장합니다."
        ),
        "ai_approach": (
            "사업 목표 달성을 위해 지도학습(분류·회귀) 및 이상 탐지(비지도 학습) 모델을 병행 적용합니다. "
            "사전 학습된 대형 언어 모델(LLM)을 파인튜닝하여 도메인 특화 문서 분석에 활용하고, "
            "강화학습 기반 최적화 알고리즘으로 운영 효율을 지속적으로 개선합니다."
        ),
        "implementation_principles": [
            "업무 연속성 우선 | 데이터 수집·AI 처리·결과 제공 계층을 분리해 장애가 특정 서비스에 국한되도록 설계 | 서비스별 헬스체크와 장애 복구 시나리오",
            "설명 가능한 AI | 모델 판단 근거와 예외 사유를 운영 화면과 보고서에 함께 남겨 검수·감사 대응력을 확보 | 판단 근거 로그, 검수 화면, 샘플링 리뷰",
            "보안·확장성 기본값화 | 최소 권한, 암호화, 접근통제를 기본값으로 두고 서비스별 수평 확장이 가능하도록 구성 | 인증·인가 정책, 성능 테스트, 오토스케일링 계획",
        ],
        "security_measures": [
            "클라우드 보안 인증 | 국가정보원 CSAP 기준 준수 및 연 1회 취약점 점검 | 공공 클라우드 운영 통제 충족",
            "개인정보 보호 | AES-256 저장 암호화와 최소 권한 접근제어 | 개인정보보호법·전자정부법 준수",
            "API 보안 | OAuth 2.0 + JWT 인증 및 Rate Limiting | 비인가 호출 차단과 남용 방지",
            "AI 안전성 | 프롬프트 인젝션 필터링과 출력 검수 규칙 적용 | 민감정보 유출 및 오답 확산 방지",
        ],
        "differentiation": [
            f"도메인 특화 AI 모델 | 기존 범용 솔루션 대비 {title} 정확도 15% 이상 향상 | 파일럿 기준 성능지표와 재현 시나리오",
            "하이브리드 처리 구조 | 실시간 처리와 배치 분석을 병행해 상황별 최적 대응 | SLA와 운영 비용을 동시에 관리",
            "설명 가능한 AI | AI 판단 근거를 업무 화면에 직접 노출 | 공공기관 감사·검수 대응 신뢰 확보",
            "개방형 아키텍처 | 오픈소스 기반 구축으로 벤더 종속 최소화 | 장기 유지보수 비용 절감과 확장성 확보",
        ],
        "total_slides": 15,
        "slide_outline": [
            _slide(1, "기술 제안 개요",
                   f"{title} 기술 솔루션 핵심 요약: 아키텍처 철학·핵심 기술·차별화 포인트 3줄 요약",
                   "임팩트 있는 표지. 우측에 시스템 아키텍처 썸네일. 기술 회사 신뢰감 강조."),
            _slide(2, "기술 스택 전체 구성",
                   "레이어별 기술 스택 한눈에: 데이터·AI·백엔드·프론트엔드·인프라 5단 구조",
                   "수평 레이어 다이어그램. 레이어별 배경색 구분. 각 기술 아이콘(로고) + 역할 한 줄."),
            _slide(3, "전체 시스템 아키텍처",
                   "3계층 아키텍처: 데이터 수집 → AI 처리 → 결과 제공. 주요 컴포넌트 연결 흐름",
                   "가로 흐름도(Flowchart). 컴포넌트는 박스+아이콘. 연결선에 데이터 흐름 레이블."),
            _slide(4, "데이터 수집·처리 파이프라인",
                   "데이터 소스(IoT·API·DB) → 수집 → 정제·변환 → 저장 흐름 상세 설명",
                   "파이프라인 화살표 다이어그램. 각 단계 박스에 처리량·속도 수치 표기."),
            _slide(5, "AI 모델 설계",
                   "사용 모델 종류(분류·이상탐지·NLP 등) + 학습 데이터 전략 + 성능 목표 지표",
                   "중앙에 모델 구조 다이어그램. 정확도·재현율 목표 수치를 박스 강조."),
            _slide(6, "AI 학습·추론 파이프라인(MLOps)",
                   "데이터 수집 → 전처리 → 학습 → 평가 → 배포 → 모니터링 사이클 시각화",
                   "순환 화살표(Circular Flow) 다이어그램. CI/CD 자동화 구간 강조."),
            _slide(7, "백엔드 API 구조",
                   "API Gateway → 서비스별 마이크로서비스 구조. 주요 엔드포인트 테이블",
                   "좌측: 아키텍처 다이어그램. 우측: 주요 API 엔드포인트 표. 다크 배경+코드 폰트."),
            _slide(8, "프론트엔드 및 대시보드 구성",
                   "대시보드 와이어프레임: 실시간 현황판·KPI 위젯·알림 패널·리포트 탭 구성",
                   "실제 대시보드 목업 또는 와이어프레임. 주요 화면 3~4개 썸네일 배치."),
            _slide(9, "인프라·클라우드 아키텍처",
                   "AWS/Azure/NCP 기반 인프라 구성도. VPC·서브넷·로드밸런서·DB 클러스터",
                   "클라우드 아이콘(AWS 공식) + 네트워크 구성도. HA 구성 이중화 표시."),
            _slide(10, "보안 설계",
                   "보안 레이어 구성: 네트워크·앱·데이터·AI 모델 보안 + 인증·접근제어 체계",
                   "양파 레이어(Onion) 보안 다이어그램. CSAP·개인정보보호법 인증 마크 삽입."),
            _slide(11, "성능·확장성 설계",
                   "현재 목표 처리량(TPS) + 오토스케일링 정책 + 장애 대응(Failover) 시나리오",
                   "성능 그래프(부하 테스트 시뮬레이션). SLA 99.9% 가용성 강조 배너."),
            _slide(12, "AI 차별화 포인트",
                   f"경쟁사 대비 비교표: 정확도·처리속도·비용·설명가능성 4개 축으로 {title} 우위 증명",
                   "레이더 차트 또는 비교 테이블. XAI(설명가능 AI) 예시 이미지 삽입."),
            _slide(13, "유사 프로젝트 기술 레퍼런스",
                   "유사 사업 2~3건: 적용 기술·성과 지표·기간 요약. 기술 연속성 증명",
                   "프로젝트별 카드 레이아웃(로고+사업명+성과 수치). 타임라인으로 기술 축적 이력."),
            _slide(14, "기술 리스크 및 대응 방안",
                   "리스크 3~4개: 데이터품질·모델성능·연동이슈·보안 + 각 대응전략",
                   "리스크 매트릭스(확률×영향도). 신호등 색상 코딩. 대응 방안 화살표 연결."),
            _slide(15, "기술 제안 요약 및 마무리",
                   "핵심 기술 포인트 3줄 요약 + Q&A 안내 + 제안사 연락처",
                   "미니멀한 마지막 슬라이드. 중앙 핵심 메시지 대형 Bold. 하단 담당자 연락처."),
        ],
    }


def _proposal_execution_plan(title: str, goal: str, ctx: str) -> dict:
    return {
        "delivery_summary": (
            f"{title} 수행계획은 요구사항 분석, 프로토타입 검증, 통합 개발, 파일럿 운영, 전면 전개를 단계별 승인 게이트와 함께 관리하는 delivery 체계로 설계했습니다. "
            "각 단계는 산출물, 완료 기준, 품질 점검 항목이 연결되어 있어 발주기관이 중간점검 시점마다 진행 상태를 객관적으로 확인할 수 있습니다. "
            "이를 통해 일정 지연과 요구사항 누락을 줄이고, 운영 이관까지 포함한 종료 조건을 명확히 합니다."
        ),
        "team_structure": [
            "PM | 1명·특급 | 전체 사업 총괄, 고객사 소통, 리스크 관리 및 일정 조율 | 착수 즉시",
            "AI 엔지니어 | 3명·고급 | 모델 설계·학습·최적화 및 MLOps 파이프라인 구축 | 설계 단계부터",
            "백엔드 개발자 | 2명·중급 | API 서버·데이터 파이프라인·연동 시스템 개발 | 설계 단계부터",
            "프론트엔드 개발자 | 1명·중급 | 운영자 대시보드 및 사용자 인터페이스 개발 | 개발 단계부터",
            "데이터 엔지니어 | 1명·고급 | 데이터 수집·정제·적재 파이프라인 설계 및 운영 | 분석 단계부터",
            "품질 관리(QA) | 1명·중급 | 테스트 계획 수립, 성능·보안·기능 검증 | 통합 단계부터",
        ],
        "milestones": [
            "착수·분석 완료 | 1개월차 | 요구사항 정의서 및 아키텍처 설계서 승인 | 착수보고서, 요구사항 정의서",
            "AI 프로토타입 검증 | 3개월차 | 핵심 AI 모델 성능 목표 달성 및 내부 검증 통과 | 모델 성능 보고서",
            "통합 개발 완료 | 6개월차 | 전체 시스템 통합 및 알파 테스트 시작 | 통합 시제품, 시험결과서",
            "파일럿 운영 개시 | 8개월차 | 실사용자 대상 베타 서비스와 운영 리허설 완료 | 파일럿 운영 계획서",
            "성과 검증 완료 | 10개월차 | KPI 달성 여부 검증 및 전면 운영 전환 승인 | 성과 검증 보고서",
            "최종 납품 및 이관 | 12개월차 | 최종 산출물 승인 및 유지보수 체계 이관 | 완료보고서, 운영 매뉴얼",
        ],
        "methodology": (
            "애자일(Scrum) 방법론을 기반으로 2주 단위 스프린트를 운영합니다. "
            "매 스프린트 종료 시 고객사 데모 및 피드백 반영으로 방향성을 지속 검증하며, "
            "CI/CD 파이프라인을 통해 코드 품질과 배포 안정성을 자동으로 보장합니다."
        ),
        "governance_plan": (
            "PM이 주간 실행계획과 리스크를 총괄하고, AI 리드·개발 리드·품질 책임자가 주간 점검회의에서 이슈를 선분류합니다. "
            "발주기관과는 월간 운영위원회 및 중요 이슈 수시 보고 체계를 유지하며, 일정·범위·비용에 영향을 주는 변경은 영향도 분석 후 승인 절차를 거칩니다. "
            "모든 의사결정은 회의록과 변경대장으로 남겨 이후 검수와 감사 대응 근거로 사용합니다."
        ),
        "risk_management": [
            "데이터 품질 부족 | 모델 학습 지연 및 정확도 저하 | 데이터 정제 프로세스 조기 수립과 합성 데이터 보완",
            "일정 지연 | 파일럿 개시 및 납품 일정 차질 | MoSCoW 기반 우선순위 재조정과 버퍼 스프린트 확보",
            "레거시 연동 이슈 | 통합 일정 지연 및 기능 범위 축소 | API 어댑터 레이어 설계로 인터페이스 표준화",
            "보안 취약점 | 운영 전환 지연 및 감사 대응 리스크 | Security by Design과 사전 취약점 점검 적용",
        ],
        "deliverables": [
            "요구사항 정의서 및 시스템 아키텍처 설계서 | 1개월차 | 문서(PDF/DOCX) | 착수보고 및 설계 검토",
            "AI 모델 학습 결과 보고서 | 3개월차 | 문서(PDF) | 성능지표 리뷰 및 승인",
            "소스코드 및 배포 패키지 | 6개월차 | Docker 이미지·소스 패키지 | 통합 테스트 결과 확인",
            "운영자 매뉴얼 및 API 명세서 | 10개월차 | 문서(PDF/DOCX) | 운영 리허설 및 사용자 교육",
            "파일럿 운영 결과 보고서 및 개선 권고안 | 12개월차 | 문서(PDF/PPTX) | 최종 완료보고 검수",
        ],
        "total_slides": 12,
        "slide_outline": [
            _slide(1, "수행 계획 개요",
                   f"{title} 수행 전략 요약: 추진 방법론·팀 구성·핵심 마일스톤 3줄 요약",
                   "표지 디자인. 우측에 간트 차트 썸네일. 안정감 있는 네이비 계열 배경."),
            _slide(2, "수행 조직도",
                   "PM 중심 역할 계층도. 각 포지션 이름·역할·담당 업무 명시. 고객사 연락 채널 표시",
                   "조직도(Org Chart) 형태. PM→팀원 계층 구조. 역할별 색상 코딩."),
            _slide(3, "핵심 인력 소개",
                   "PM·AI리드·개발리드 3명 상세 프로필: 경력·자격증·유사 프로젝트 실적",
                   "인물 카드 레이아웃(사진 자리+이름+역할+경력 요약). 자격증·실적 뱃지 형태."),
            _slide(4, "수행 방법론",
                   "애자일 Scrum 2주 스프린트 구조: 계획→개발→검증→리뷰 사이클 시각화",
                   "순환 화살표 다이어그램(Sprint Cycle). 각 단계 아이콘."),
            _slide(5, "전체 추진 일정 (마스터 스케줄)",
                   "12개월 간트 차트: 단계별 작업·마일스톤·검수·납품 일정 한눈에",
                   "가로 간트 차트(전체 슬라이드 너비 활용). 단계별 색상 구분. 마일스톤 다이아몬드 마커."),
            _slide(6, "1단계 수행 내용 (1~3개월)",
                   "현황 분석·요구사항 정의·아키텍처 설계. 산출물: RFP 분석서·설계서",
                   "단계 강조 배너. 주요 Task 리스트. 산출물 박스 별도 표시."),
            _slide(7, "2단계 수행 내용 (4~8개월)",
                   "AI 모델 개발·시스템 통합·테스트. 2주 스프린트 8회 운영 계획",
                   "스프린트 번호별 주요 목표 표. 기능별 개발 완료 기준(체크리스트)."),
            _slide(8, "3단계 수행 내용 (9~12개월)",
                   "파일럿 운영·성과 검증·전면 확산·산출물 납품. 이관 체계 수립",
                   "파일럿→확산 화살표 전환 다이어그램. 수용 테스트(UAT) 체크리스트."),
            _slide(9, "주요 마일스톤 및 산출물",
                   "6개 마일스톤 타임라인 + 각 마일스톤별 핵심 산출물 목록",
                   "수평 타임라인(마일스톤 마커). 각 마커 아래 산출물 목록."),
            _slide(10, "리스크 관리 계획",
                   "4대 리스크: 발생 가능성×영향도 매트릭스 + 각 대응 방안",
                   "리스크 매트릭스(2×2 또는 3×3 그리드). 신호등 색상. 리스크 오너 명시."),
            _slide(11, "품질 관리 계획",
                   "테스트 전략: 단위·통합·성능·보안·인수 테스트 5단계 + 품질 기준",
                   "테스트 피라미드 다이어그램. 단계별 커버리지 목표."),
            _slide(12, "수행 역량 및 마무리",
                   "유사 사업 수행 실적 + 핵심 경쟁력 요약 + 성공적 납품 의지 표명",
                   "실적 표(사업명·기간·규모·성과). 표지와 동일 테마로 마무리."),
        ],
    }


def _proposal_expected_impact(title: str, goal: str, ctx: str) -> dict:
    subject = _project_subject(title)
    return {
        "impact_summary": (
            f"{subject} 사업의 기대효과는 핵심 정책 목표를 정량 KPI와 정성 효과로 함께 관리할 수 있는 운영 구조를 만드는 데 있습니다. "
            "처리시간 단축, 오류율 감소, 운영비 절감, 서비스 가용성 향상 같은 정량 지표와 함께 조직 역량 강화와 국민 체감 품질 개선을 병행 관리하여, "
            "제안 단계의 약속이 실제 운영 성과관리로 이어지도록 설계했습니다."
        ),
        "quantitative_effects": [
            "핵심 업무 처리 시간 | 8시간 | 3.2시간 | 주요 업무 처리시간 60% 단축",
            "연간 운영비 | 12억 원 | 9억 원 | 수작업 재배치로 연간 3억 원 절감",
            "데이터 오류율 | 12% | 2% 이하 | AI 자동 검증으로 품질 일관성 확보",
            "서비스 가용률 | 97.5% | 99.9% | 24/7 운영 안정성 확보",
        ],
        "qualitative_effects": [
            "조직 역량 강화 | 데이터 기반 의사결정 문화 정착 | 정책·사업 운영의 디지털 전환 가속",
            "국민 신뢰 제고 | 서비스 체감 품질과 응답 일관성 향상 | 공공서비스 브랜드 가치와 정책 수용성 강화",
            "업무 방식 혁신 | 반복 업무 부담 감소와 고부가가치 업무 집중 | 실무자 만족도와 생산성 동시 개선",
            "정책 확산 효과 | AI 활용 선도 사례 구축 | 타 기관 벤치마킹과 후속 사업 확장 기반 확보",
        ],
        "social_value": (
            f"{subject} 사업을 통해 공공서비스 품질을 획기적으로 개선함으로써 "
            "국민 생활 편의성 향상과 행정 신뢰도 제고에 기여합니다. "
            "디지털 소외 계층을 위한 접근성 개선과 취약계층 우선 서비스 설계를 통해 "
            "포용적 디지털 전환을 실현하며, AI 공공 활용 표준 사례를 선도합니다."
        ),
        "kpi_commitments": [
            "핵심 업무 처리시간 | 기준 대비 50% 이상 단축 | 업무 로그와 월간 운영 리포트 | 파일럿 운영 종료 시점",
            "데이터 오류율 | 기준 대비 70% 이상 개선 | 검수 샘플링과 자동 검증 결과 | 통합 테스트 종료 시점",
            "서비스 가용률 | 99.9% 이상 유지 | 모니터링 대시보드와 장애 리포트 | 전면 운영 전환 후 3개월",
        ],
        "roi_estimate": (
            "초기 투자 대비 3년 내 ROI 220% 달성 예상. "
            "연간 운영비 절감(3억) + 처리 속도 향상에 따른 간접 경제 효과(5억) 합산 시 "
            "사업비 회수 기간 약 18개월로 추정됩니다."
        ),
        "monitoring_plan": [
            "처리 속도·오류율·만족도 KPI | 월간 | PM·운영 관리자 | 목표 대비 달성률 95% 이상",
            "분기별 성과 보고서 | 분기 | PM·발주처 협의체 | 핵심 KPI 편차 10% 이내 관리",
            "AI 모델 정확도·재현율 | 주간 | AI 엔지니어 | 임계값 이하 시 재학습 및 원인 분석",
        ],
        "total_slides": 10,
        "slide_outline": [
            _slide(1, "기대효과 요약",
                   f"{subject} 도입으로 얻는 3대 핵심 효과 한눈에: 속도·비용·품질 개선 수치",
                   "강렬한 임팩트 슬라이드. 3개 큰 숫자(60%·25%·99.9%) 중앙 배치. 녹색·파란색 포인트."),
            _slide(2, "업무 효율화 효과",
                   "AS-IS vs TO-BE 처리 시간 비교. 업무별 자동화 전·후 소요 시간 표",
                   "좌우 분할(AS-IS 회색 / TO-BE 파란색 강조). 처리 시간 막대 비교 차트."),
            _slide(3, "비용 절감 효과",
                   "연간 절감 금액(3억) 세부 내역: 인건비·운영비·오류 수정비 항목별 분류",
                   "파이 차트 또는 스택 막대 차트. 절감 금액 크게 표시(대형 숫자)."),
            _slide(4, "품질·정확도 향상",
                   "오류율 12%→2% 개선 추이 그래프 + 자동화 검증으로 품질 일관성 확보",
                   "꺾은선 그래프(개선 추이). 오류율 수치 before/after 강조 박스."),
            _slide(5, "서비스 가용성 및 안정성",
                   "99.9% SLA 달성 근거: 이중화 구성·자동 복구·모니터링 체계 설명",
                   "가용성 게이지(원형 프로그레스 바 99.9%). Down Time 계산(연간 8.7시간 이하)."),
            _slide(6, "정성적 효과",
                   "조직 디지털 역량 강화 + 직원 업무 만족도 향상 + 서비스 신뢰도 제고",
                   "아이콘+한 줄 설명 카드 3~4개. 따뜻한 컬러 포인트(오렌지·그린)."),
            _slide(7, "사회적 가치",
                   "포용적 디지털 전환: 취약계층 접근성 개선 + AI 공공 선도 사례 효과",
                   "사회적 가치 키워드 클라우드 또는 아이콘 맵. 따뜻한 인간적 이미지."),
            _slide(8, "ROI 분석",
                   "투자비용 vs 3년 누적 절감액 비교. Break-Even Point 18개월 표시. ROI 220%",
                   "손익분기 그래프(X: 월, Y: 누적 효과). 투자비용 선 vs 누적효과 선 교차."),
            _slide(9, "성과 모니터링 계획",
                   "KPI 대시보드 구성 + 월별/분기별 보고 체계 + 모델 재학습 주기",
                   "대시보드 목업 와이어프레임. KPI 지표 표(지표명·현재값·목표값·측정주기)."),
            _slide(10, "결론 — 왜 지금, 왜 우리인가",
                   f"{subject} 도입의 시급성 + 제안사 차별화 + 성공 확신 메시지",
                   "강렬한 마무리 슬라이드. 중앙 대형 키 메시지 1문장. 표지 테마 동일 적용."),
        ],
    }


# ===========================================================================
# bid_decision_kr builders
# ===========================================================================

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


# ===========================================================================
# rfp_analysis_kr builders
# ===========================================================================

def _rfp_analysis_summary(title: str, goal: str, ctx: str) -> dict:
    excerpt = _ctx_excerpt(ctx, 520)
    return {
        "project_overview": (
            f"{title} 공고를 기준으로 {goal}에 필요한 평가 포인트를 정리합니다. {excerpt}"
        ),
        "budget_schedule": "예산, 계약 기간, 제안 마감과 질의응답 일정을 procurement state와 함께 검토합니다.",
        "issuer_needs": [
            "발주기관의 문제 정의와 평가 우선순위를 procurement context와 source snapshot에서 추출합니다.",
            f"핵심 맥락: {excerpt}",
        ],
        "evaluation_criteria": [
            "필수 자격·인증·유사 실적 요구를 평가항목 해석의 출발점으로 둡니다.",
            "hard filter에서 확인된 blocking 조건을 평가 리스크로 명시합니다.",
        ],
        "mandatory_requirements": [
            "입찰참가자격, 보안 의무, 일정 제약, 핵심 기술 범위를 필수 요구사항으로 정리합니다.",
            f"현재 procurement context: {excerpt}",
        ],
        "optional_requirements": [
            "가점 요소와 차별화 요소를 별도로 분리해 win strategy에 연결합니다.",
        ],
        "win_probability": (
            f"현재 recommendation과 soft-fit breakdown을 반영해 수주 가능성 판단 근거를 요약합니다. {excerpt}"
        ),
    }


def _rfp_analysis_win_strategy(title: str, goal: str, ctx: str) -> dict:
    excerpt = _ctx_excerpt(ctx, 520)
    return {
        "swot_analysis": (
            f"{title} 입찰에 대한 SWOT 분석은 procurement recommendation과 capability profile을 기준으로 작성합니다. {excerpt}"
        ),
        "differentiation_points": [
            "기존 공공 레퍼런스와 domain fit 점수에 근거한 차별화 포인트를 우선 배치합니다.",
            "Conditional Go 보완 항목은 차별화와 동시에 리스크 완화 계획으로 표현합니다.",
        ],
        "risk_factors": [
            "blocking hard filter와 action-needed checklist는 제안 리스크로 직접 연결합니다.",
            f"리스크 근거: {excerpt}",
        ],
        "response_strategy": (
            f"{goal} 달성을 위해 procurement checklist와 recommendation evidence를 대응 전략으로 전환합니다. {excerpt}"
        ),
        "key_messages": [
            "발주기관 핵심 니즈와 당사 적합성을 한 문장으로 연결합니다.",
            "승인 조건이 있다면 제안 전략에 필요한 선결 과제로 명시합니다.",
            f"참고 맥락: {excerpt}",
        ],
    }


# ===========================================================================
# performance_plan_kr builders
# ===========================================================================

def _performance_overview(title: str, goal: str, ctx: str) -> dict:
    subject = _project_subject(title)
    excerpt = _ctx_excerpt(ctx, 520)
    return {
        "executive_summary": (
            f"{subject} 수행계획서는 계약 범위, 일정, 산출물, 투입 인력, 승인 게이트를 하나의 실행 문서로 정리한 결과물입니다. "
            "착수 이후 요구사항 정의와 설계, 개발·시험, 배포·운영 교육까지 단계별 책임과 완료 기준을 명확히 두어 발주처가 중간점검과 최종 검수 시점 모두에서 진행 상태를 객관적으로 확인할 수 있게 구성했습니다. "
            "특히 산출물·인력·WBS를 서로 연결해 일정과 품질, 자원 배분이 분리되지 않도록 설계했습니다. "
            f"조달 연계 참고: {excerpt}"
        ),
        "project_info": (
            f"**사업명**: {title}\n"
            f"**계약 기간**: 2026년 1월 1일 ~ 2027년 12월 31일 (24개월)\n"
            f"**계약 금액**: 6,500,000,000원 (부가세 포함)\n"
            f"**발주처**: 국토교통부\n"
            f"**추진 목표**: {goal}\n"
            "**수행 원칙**: 단계별 산출물과 승인 게이트를 연결해 일정·품질·운영 이관을 동시에 관리"
        ),
        "scope_of_work": [
            "교차로 및 스쿨존 대상 AI 기반 안전 모니터링 시스템을 구축합니다.",
            "위험 요소 분석과 개선 방안을 포함한 데이터 기반 운영 체계를 수립합니다.",
            "교통약자 보호를 위한 실시간 대응 대시보드와 보고 체계를 구축합니다.",
            "운영 매뉴얼과 교육 체계를 포함해 현장 적용과 이관까지 사업 범위에 포함합니다.",
        ],
        "deliverables": [
            "착수보고서 | 2026년 1월 15일 | HWP+PDF | 발주처 PM 서면 승인",
            "중간보고서 | 2026년 6월 30일 | HWP+PDF | 월간 점검회의 검토",
            "운영 매뉴얼 | 2027년 12월 15일 | HWP+PDF | 현장 시연 및 교육 결과 확인",
            "최종보고서 | 2027년 12월 31일 | HWP+PDF | 최종 검수위원회 승인",
        ],
        "team_structure": [
            "PM·총괄 | 특급 | 이현수 | 15 | 국토교통 프로젝트 경험 10년",
            "AI 기술 리드 | 고급 | 김석진 | 10 | 안전 분석 알고리즘 구현 경력 5년",
            "소프트웨어 개발 | 중급 | 박민재 외 2명 | 7 | 공공 솔루션 개발 경험",
            "품질 관리 | 고급 | 송지현 | 6 | ISO 품질 인증 및 검수 경험",
        ],
        "success_metrics": [
            "핵심 산출물 납기 준수 | 예정일 대비 지연 0건 | 산출물 제출대장과 승인 기록",
            "통합 테스트 완료율 | 계획된 핵심 시나리오 100% 통과 | 시험 결과서와 결함 조치 이력",
            "사업 목표 달성도 | 계약서에 정의된 완료 KPI 충족 | 월간 보고서와 최종 검수 확인서",
        ],
        "wbs_summary": [
            "1단계 착수 및 요구사항 정의 | 2026년 1월 ~ 2026년 3월 | 착수보고서, 요구사항 정의서 | M1: 착수보고 완료",
            "2단계 시스템 설계 | 2026년 4월 ~ 2026년 6월 | 아키텍처 설계서, 데이터 정의서 | M2: 설계 검토 승인",
            "3단계 개발 및 테스트 | 2026년 7월 ~ 2027년 9월 | 개발 산출물, 시험 결과서 | M3: 통합 테스트 통과",
            "4단계 배포 및 운영 교육 | 2027년 10월 ~ 2027년 12월 | 운영 매뉴얼, 완료보고서 | M4: 최종 납품",
        ],
        "total_slides": 8,
        "slide_outline": [
            _slide(1, "사업 개요",
                   f"{subject} 사업 목적, 계약 기간·예산, 발주처 핵심 요구사항 요약",
                   "표지 이후 첫 슬라이드. 사업명과 목표를 한 문장으로 강조."),
            _slide(2, "사업 배경과 추진 필요성",
                   "교통약자 안전 확보 필요성, 현행 운영 한계, 정책·행정 맥락 정리",
                   "배경 사진 1장 + 문제 정의 3포인트 카드."),
            _slide(3, "수행 범위",
                   "AI 모니터링, 위험 분석, 대시보드, 교육·운영 체계 등 범위 4개 축 설명",
                   "4분할 범위 다이어그램 또는 아이콘 카드."),
            _slide(4, "핵심 산출물",
                   "착수보고서, 중간보고서, 운영 매뉴얼, 최종보고서 제출 시점과 검수 방안",
                   "산출물 표를 중심으로 구성."),
            _slide(5, "투입 인력 및 역할",
                   "PM, AI 리드, 개발, 품질관리의 책임과 전문성, M/M 배분",
                   "조직도 + 인력 표 조합."),
            _slide(6, "WBS 및 마일스톤",
                   "4단계 일정, 단계별 산출물, 주요 승인 게이트 정리",
                   "타임라인 또는 표 형태."),
            _slide(7, "추진 거버넌스",
                   "PMO 운영, 주간 점검, 이슈 escalation, 발주처 보고 구조 정리",
                   "거버넌스 흐름도와 보고 주기 배지."),
            _slide(8, "기대 성과와 다음 단계",
                   "완료 기준, 인수 조건, 사업 종료 후 기대되는 운영 상태",
                   "마무리 슬라이드. 성공 지표 3개 강조."),
        ],
    }


def _performance_quality_risk(title: str, goal: str, ctx: str) -> dict:
    excerpt = _ctx_excerpt(ctx, 520)
    return {
        "quality_operating_principles": (
            "품질관리는 산출물 검수만이 아니라 일정·범위·운영 안정성을 함께 관리하는 방식으로 운영합니다. "
            "각 단계마다 사전 점검, 중간 검토, 최종 승인 조건을 분리하고, 결함·리스크·변경 요청은 동일한 이슈 관리 체계 안에서 추적합니다. "
            "이를 통해 품질 기준이 선언에 그치지 않고 실제 운영 회의와 승인 절차에서 반복 확인되도록 합니다. "
            f"또한 최근 조달 의사결정 상태와 원문 추출 신호를 품질 관리 기준에 반영합니다: {excerpt}"
        ),
        "quality_standards": [
            "기능 적합성 | 교차로/스쿨존 위험 감지 정확도 92% 이상 | 월별 정확도 측정 보고",
            "성능 효율성 | 경보 이벤트 처리 응답시간 3초 이내 | 부하 테스트 결과서",
            "운영 안정성 | 장애 복구 시간 30분 이내 | 모의 장애 복구 리허설",
        ],
        "inspection_criteria": [
            "착수보고서 | 착수 단계 종료 시 | 요구사항 누락 0건 | 착수보고 회의록",
            "중간보고서 | 개발 단계 종료 시 | 핵심 기능 시연 완료 | 중간보고 검토서",
            "최종보고서 | 사업 종료 시 | 계약서에 정의된 완료 지표 충족 | 최종 검수 확인서",
        ],
        "risk_matrix": [
            "데이터 누락 | 중 | 상 | 현장 센서 데이터 품질 진단 및 예비 수집 계획 운영",
            "시스템 오류 | 중 | 중 | 핵심 모듈 이중화와 장애 대응 Runbook 준비",
            "일정 지연 | 상 | 중 | 주간 PMO 점검과 선행 과제 조기 경보 체계 운영",
        ],
        "change_management": (
            "변경 요청은 PM이 접수 후 영향도(범위, 일정, 비용)를 분석하고, 발주처 승인 회의에서 결정합니다. 승인된 변경만 WBS와 산출물 목록에 반영하며 모든 이력은 변경대장으로 관리합니다."
        ),
        "reporting_structure": (
            f"{goal} 달성을 위해 PM 주간보고, 월간 운영위원회, 분기별 경영진 보고 체계를 운영합니다. 주요 이슈는 Delivery Lead와 품질 책임자가 사전 검토하고, 최종 의사결정은 Executive Approver가 수행합니다."
        ),
        "governance_checkpoints": [
            "주간 PMO 회의 | 매주 | PM, 기술 리드, 품질 책임자 | 일정 진척률, 결함 조치, 선행 과제 상태",
            "월간 운영위원회 | 매월 | PM, 발주처 담당관, 주요 수행 리더 | 산출물 승인 여부, 리스크 등급, 변경 요청 검토",
            "분기 경영진 보고 | 분기 | Executive Approver, PM | 예산·성과·운영 리스크 종합 점검과 의사결정",
        ],
        "total_slides": 6,
        "slide_outline": [
            _slide(1, "품질관리 개요",
                   "품질 목표, 품질지표, 검수 운영 원칙 요약",
                   "품질 KPI 배지와 핵심 문장 강조."),
            _slide(2, "품질 기준 상세",
                   "기능 적합성, 성능 효율성, 운영 안정성 기준과 측정 방식 정리",
                   "품질 기준 표 중심 구성."),
            _slide(3, "검수 기준과 승인 체계",
                   "착수·중간·최종 산출물 검수 시점, 승인 기준, 증빙 문서 정리",
                   "검수 절차 플로우 + 표."),
            _slide(4, "리스크 매트릭스",
                   "데이터, 시스템, 일정 리스크의 가능성과 영향도, 대응 계획",
                   "리스크 표 또는 2x2 matrix 시각화."),
            _slide(5, "변경관리 및 이슈 대응",
                   "변경 요청 처리, 영향도 검토, 승인 절차, 이력 관리 원칙",
                   "변경관리 흐름도."),
            _slide(6, "보고 체계와 운영 통제",
                   f"{goal} 달성을 위한 주간·월간·분기 보고 체계와 escalation 규칙",
                   "보고 cadence 타임라인과 책임자 구분."),
        ],
    }


# ===========================================================================
# business_plan_kr builders
# ===========================================================================

def _business_overview(title: str, goal: str, ctx: str) -> dict:
    ctx_line = f" {ctx}" if ctx else ""
    return {
        "vision": (
            f"{title}을 통해 {goal}을 실현하고, 지속 가능한 성장 기반을 구축합니다.{ctx_line} "
            "기술 혁신과 고객 중심 사고를 바탕으로 시장을 선도하는 기업으로 도약합니다."
        ),
        "problem_statement": (
            f"현재 시장에서는 {goal}에 대한 수요가 급증하고 있음에도 불구하고, "
            "기존 솔루션들은 높은 비용, 복잡한 도입 과정, 낮은 사용자 편의성 등의 문제로 "
            "실제 수요를 충족시키지 못하고 있습니다."
        ),
        "solution": (
            f"{title}은 {goal}을 위한 올인원 플랫폼을 제공합니다. "
            "AI 기반 자동화로 기존 대비 70% 시간을 절약하고, SaaS 형태의 월 구독 모델로 "
            "초기 비용 부담 없이 즉시 도입 가능합니다."
        ),
        "target_market": [
            "1차 타겟: 연 매출 10~100억 규모 중소기업 (국내 약 7만 개사)",
            "2차 타겟: 시리즈 A 이전 스타트업 및 예비창업자 (연간 10만 팀)",
            "3차 타겟: 프리랜서 및 1인 기업 (국내 약 150만 명)",
        ],
        "unique_value": (
            f"경쟁사 대비 {title}의 핵심 차별점은 '전문가 수준의 결과를 10분 만에'입니다. "
            "단순 템플릿 제공이 아닌 AI가 사용자의 맥락을 이해하고 최적화된 결과를 생성하며, "
            "한국 비즈니스 환경에 특화된 로컬라이제이션으로 해외 경쟁 제품의 한계를 극복합니다."
        ),
        "total_slides": 10,
        "slide_outline": [
            _slide(1, "표지 / 회사 소개",
                   f"회사명·사업명({title})·슬로건·발표일. 핵심 가치 제안 1줄",
                   "로고 중앙 + 슬로건 대형 Bold. 브랜드 컬러 그라디언트 배경."),
            _slide(2, "우리가 해결하는 문제",
                   "현재 시장의 Pain Point 3가지. 현재 상황 → 문제 → 고객이 겪는 결과 스토리 구조",
                   "감성적 공감 이미지(좌측) + 문제 포인트 텍스트(우측). Before 상황 시각화."),
            _slide(3, "솔루션 개요",
                   f"{title} 핵심 기능 3가지 + 작동 방식 간략 데모 흐름",
                   "3단 아이콘 카드(기능별). 중앙에 제품 스크린샷 또는 목업 이미지."),
            _slide(4, "제품 데모 / 핵심 화면",
                   "주요 화면 2~3개 스크린샷 + 각 화면의 핵심 기능 설명 말풍선",
                   "실제 제품 스크린샷. 화면 주변에 설명 말풍선. 맥북/아이폰 목업 프레임 활용."),
            _slide(5, "타겟 시장 및 규모",
                   "TAM→SAM→SOM 깔때기 + 핵심 고객 세그먼트 페르소나 2개",
                   "깔때기(Funnel) 다이어그램 + 시장 규모 숫자 강조. 시장 성장률 그래프 삽입."),
            _slide(6, "경쟁 우위 분석",
                   "경쟁사 비교 매트릭스: 기능·가격·사용성·지원 4개 축. 우리 제품 우위 강조",
                   "비교 테이블(경쟁사 회색, 우리 회사 강조색). 레이더 차트로 경쟁 포지션 시각화."),
            _slide(7, "핵심 가치 제안",
                   f"'{title}만의 이유' — 왜 지금, 왜 우리인가. 고객 성공 사례 1건 미리보기",
                   "중앙에 핵심 문구 대형 Bold. 좌우에 전·후 비교 수치. 고객 인용 문구 박스."),
            _slide(8, "비즈니스 모델 요약",
                   "수익 모델 요약: 무료→유료 전환 구조 + 가격 티어 + 핵심 파트너십",
                   "가격 티어 카드(Free·Pro·Enterprise). 수익 흐름 화살표. 파트너 로고 배열."),
            _slide(9, "팀 소개",
                   "창업자·CTO·마케터 핵심 3~4명 프로필: 경력·강점·역할",
                   "인물 카드 레이아웃. 전 직장 로고·학교 배지 표시. 팀 다양성과 전문성 강조."),
            _slide(10, "투자 제안 및 마무리",
                   "펀딩 목표·사용 계획·기대 성과. Call-to-Action: 미팅 요청·연락처",
                   "펀딩 사용처 파이 차트. 마일스톤 타임라인. 하단에 연락처+QR코드."),
        ],
    }


def _business_market_analysis(title: str, goal: str, ctx: str) -> dict:
    return {
        "market_size": (
            f"{title} 타겟 시장의 국내 총 규모는 약 2조 원(TAM)으로 추정되며, "
            "당사가 실현 가능한 서비스 대상 시장(SAM)은 약 3,000억 원입니다. "
            "초기 5년 내 목표 점유율 5% 확보 시 약 150억 원 매출을 목표로 합니다."
        ),
        "competitors": [
            "국내 A사: 시장점유율 30%, 대기업 특화 — 중소기업 접근성 낮음",
            "해외 B사: 기능 우수하나 한국어 지원 미흡, 높은 구독료($500+/월)",
            "국내 C사: 저가 포지셔닝이나 AI 기능 부재, 템플릿 수준에 그침",
        ],
        "market_trends": [
            "생성형 AI 도입 가속화: 2025년 국내 기업 AI 도입률 45% → 2027년 70% 목표",
            "비용 효율화 압박: 경기 불확실성으로 SaaS 구독 모델 선호도 급증",
            "디지털 전환 정부 지원: 중기부·과기부 SME 디지털 전환 지원 예산 1조 원",
        ],
        "customer_segments": [
            "얼리어답터: 스타트업·IT기업 — 신기술 수용성 높고 즉각 피드백 가능",
            "메인 세그먼트: 제조·유통 중소기업 — 디지털 전환 필요성 절감",
            "확장 세그먼트: 공공기관·교육기관 — 안정성 중시, 긴 의사결정 사이클",
        ],
        "entry_strategy": (
            "PLG(Product-Led Growth) 전략으로 무료 플랜을 통해 사용자 기반을 확보한 후 "
            "프리미엄 전환을 유도합니다. 초기 6개월은 스타트업·IT기업 집중 공략으로 "
            "레퍼런스를 구축하고, 이후 중소기업 대상 영업·파트너십 채널을 확장합니다."
        ),
        "total_slides": 12,
        "slide_outline": [
            _slide(1, "시장 분석 개요",
                   f"{title} 목표 시장 핵심 요약: 시장 규모·성장률·핵심 트렌드 3줄",
                   "데이터 중심 표지. 시장 규모 숫자(2조 원) 대형 강조. 분석 출처 하단 표기."),
            _slide(2, "시장 규모 (TAM·SAM·SOM)",
                   "TAM 2조 → SAM 3,000억 → SOM 150억(5년 목표) 깔때기 시각화",
                   "깔때기 또는 동심원 다이어그램. 각 단계 숫자+근거 텍스트."),
            _slide(3, "시장 성장률 트렌드",
                   "5개년 시장 성장 CAGR + 정부 지원 정책 타임라인",
                   "꺾은선+막대 콤보 차트. 연도별 성장률 수치. 정부 정책 이벤트 화살표 표시."),
            _slide(4, "핵심 시장 트렌드 3가지",
                   "AI 확산·SaaS 선호·정부 지원 — 각 트렌드의 우리 사업 기회 연결",
                   "3단 카드 레이아웃(트렌드 아이콘+설명+기회 포인트). 트렌드→기회 화살표."),
            _slide(5, "경쟁사 분석 개요",
                   "주요 경쟁사 3곳 포지셔닝 맵: X축(가격) × Y축(기능 수준)",
                   "포지셔닝 맵 산점도. 경쟁사 원, 우리 회사 별 마커. 유리한 영역 음영 처리."),
            _slide(6, "경쟁사 상세 비교",
                   "경쟁사별 강점·약점·가격·타겟 고객 비교 테이블",
                   "비교 매트릭스 테이블. 우리 회사 행 강조색. 체크/X 아이콘으로 기능 유무 시각화."),
            _slide(7, "우리의 경쟁 우위",
                   "경쟁사 대비 차별화 포인트 3가지 + 모방 불가 핵심 역량",
                   "3단 차별화 카드(아이콘+제목+설명). 경쟁 해자(Moat) 요소 강조 배너."),
            _slide(8, "고객 세그먼트 분석",
                   "3개 세그먼트 페르소나: 역할·Pain Point·구매 기준·예산 범위",
                   "세그먼트별 페르소나 카드. 우선 공략 세그먼트 별표 표시."),
            _slide(9, "고객 여정 맵",
                   "주요 세그먼트의 인지→관심→검토→구매→사용→추천 6단계 여정",
                   "수평 여정 다이어그램. 단계별 고객 감정(이모지). 우리 제품 개입 포인트 강조."),
            _slide(10, "시장 진입 전략",
                   "PLG 전략: 무료→유료 전환 퍼널 + 채널별 획득 비용(CAC) 추정",
                   "퍼널 다이어그램(인지→가입→활성→유료). 단계별 전환율·비용 표기."),
            _slide(11, "초기 공략 시장 계획",
                   "6개월 집중 타겟: IT·스타트업 생태계. 파트너십·이벤트·콘텐츠 채널 믹스",
                   "채널 믹스 파이 차트. 6개월 액션 플랜 타임라인."),
            _slide(12, "시장 기회 결론",
                   f"시장 타이밍의 적절성 + {title}의 시장 적합성(PMF) 가설 + 다음 단계",
                   "결론 강조 슬라이드. 핵심 수치 3개 재강조. Call-to-Action 버튼 스타일 텍스트."),
        ],
    }


def _business_model(title: str, goal: str, ctx: str) -> dict:
    return {
        "revenue_streams": [
            "SaaS 구독: Basic(월 3만원)·Pro(월 9만원)·Enterprise(월 30만원~) 3 티어",
            "사용량 기반 과금: AI 생성 건수 초과분에 대한 추가 과금 (건당 500원)",
            "기업 커스터마이징: 대형 고객사 전용 온프레미스 구축 및 커스텀 모듈 개발",
        ],
        "cost_structure": [
            "인프라 비용: AI API 호출비·서버 운영비 — 매출 대비 약 25% 예상",
            "인건비: 개발·세일즈·CS 팀 인건비 — 초기 50%, 스케일업 후 35%로 절감",
            "마케팅·영업: 초기 MAU 확보를 위한 성과형 광고·콘텐츠 마케팅",
        ],
        "key_partnerships": [
            "AI API 파트너 (OpenAI/Anthropic): 안정적 AI 인프라 확보 및 기술 협력",
            "회계·법무 SaaS 연동 파트너: 생태계 확장으로 Lock-in 효과 강화",
            "중소기업진흥공단·창업진흥원: 공공 지원 사업 연계 및 레퍼런스 확보",
        ],
        "pricing_strategy": (
            "경쟁사 대비 30~40% 저렴한 가격으로 시장 침투를 가속화합니다. "
            "개인·스타트업은 무료 플랜(월 10건 무료)으로 진입 장벽을 낮추고, "
            "연간 구독 선결제 시 20% 할인 혜택으로 장기 고객 전환율을 높입니다."
        ),
        "growth_levers": [
            "바이럴 성장: 생성 문서 하단 브랜딩 삽입 및 공유 기능으로 자연 확산",
            "콘텐츠 마케팅: SEO 최적화 블로그·유튜브 채널로 유기적 트래픽 확보",
            "파트너 에코시스템: 리셀러·에이전시 채널 확장으로 영업력 레버리지",
        ],
        "total_slides": 11,
        "slide_outline": [
            _slide(1, "사업 모델 개요",
                   f"{title} 수익 창출 방식 한눈에: 누가 무엇에 얼마를 지불하는가",
                   "비즈니스 모델 캔버스 전체 또는 핵심 블록 발췌. Value Proposition 중심."),
            _slide(2, "수익 모델 구조",
                   "3가지 수익원: SaaS 구독·사용량 과금·커스터마이징. 각 비중 예상",
                   "수익원별 파이 차트(예상 비중). 각 모델 설명 카드 3개. 연간 MRR 성장 목표."),
            _slide(3, "가격 정책 (Pricing Tiers)",
                   "Free·Basic·Pro·Enterprise 4단 가격표. 각 티어 포함 기능 비교",
                   "가격 테이블. 추천 티어 강조 색상+배지. 연간 vs 월간 전환 절약액 표시."),
            _slide(4, "Unit Economics",
                   "CAC·LTV·LTV:CAC 비율·Churn Rate 목표. 손익분기 고객 수 계산",
                   "핵심 지표 4개 숫자 카드. LTV vs CAC 막대 비교 차트."),
            _slide(5, "비용 구조",
                   "고정비 vs 변동비 분류. 규모 확장 시 단위 비용 절감 곡선",
                   "비용 분류 테이블(항목·금액·비율). 매출 대비 비용 추이 꺾은선."),
            _slide(6, "수익성 전망 (P&L 요약)",
                   "3년 손익계산서 요약: 매출·비용·영업이익 연도별 추이",
                   "3년 막대+꺾은선 콤보 차트. 흑자 전환 시점 강조 배너."),
            _slide(7, "핵심 파트너십",
                   "파트너 유형 3가지: 기술(AI API)·유통(리셀러)·공공(정부지원). 각 시너지",
                   "파트너 로고 배치 + 협력 내용 한 줄. 파트너십 → 비즈니스 효과 화살표."),
            _slide(8, "성장 동력 (Growth Levers)",
                   "바이럴·콘텐츠·파트너 3개 채널의 예상 기여 비중 + 실행 방법",
                   "성장 엔진 플라이휠(순환 화살표). 채널별 KPI 목표. MAU 성장 목표 그래프."),
            _slide(9, "고객 생애 가치 최적화",
                   "온보딩→활성화→유지→확장→추천 5단계 고객 성공 전략",
                   "고객 수명 주기 수평 다이어그램. Churn 감소·NPS 향상 목표 수치."),
            _slide(10, "재무 목표 및 마일스톤",
                   "MRR·ARR·유료 고객 수 12·24·36개월 목표. 펀딩 계획 연계",
                   "타임라인+목표 수치 결합. 주요 재무 마일스톤 다이아몬드 마커."),
            _slide(11, "사업 모델 요약 및 마무리",
                   "핵심 수익 구조 3줄 요약 + 비즈니스 모델의 확장성·방어성 강조",
                   "미니멀 마무리 슬라이드. 핵심 메시지 대형 Bold. Next Steps 3개 아이콘."),
        ],
    }


def _business_execution_roadmap(title: str, goal: str, ctx: str) -> dict:
    return {
        "short_term_goals": [
            "MVP 출시 및 베타 사용자 100명 확보 (3개월)",
            "핵심 기능 피드백 반영 및 제품-시장 적합성(PMF) 검증",
            "초기 유료 전환 고객 20개사 확보, MRR 600만 원 달성",
        ],
        "mid_term_goals": [
            "월간 활성 사용자(MAU) 2,000명 돌파 (12개월)",
            "프리미엄 전환율 15% 달성, MRR 3,000만 원 목표",
            "Series A 투자 유치 (20억 원) 및 팀 15명으로 확장",
        ],
        "long_term_goals": [
            "국내 시장점유율 5% 확보, ARR 50억 원 달성 (3년)",
            "동남아 2개국 진출 및 글로벌 사용자 비중 30% 달성",
            "Series B 투자 유치 또는 IPO 준비 착수 (5년)",
        ],
        "key_milestones": [
            "M1 (3개월): 베타 출시 및 첫 유료 고객 확보",
            "M2 (6개월): PMF 검증 완료 및 그로스 엔진 가동",
            "M3 (12개월): 시리즈 A 클로징 및 팀 본격 확장",
            "M4 (24개월): 국내 시장 안정화 및 해외 파일럿",
            "M5 (36개월): 글로벌 확장 및 흑자 전환",
        ],
        "resource_requirements": [
            "인력: 개발 5명·마케팅 2명·세일즈 2명·CS 1명 (총 10명, 12개월 기준)",
            "초기 자본금: 5억 원 (운영비 3억 + 마케팅 1억 + 예비 1억)",
            "인프라: AWS 클라우드 서버 월 200만 원 예산",
        ],
        "total_slides": 10,
        "slide_outline": [
            _slide(1, "실행 로드맵 개요",
                   f"{title} 3개년 실행 계획 한눈에: 단기·중기·장기 목표 + 핵심 마일스톤",
                   "타임라인 표지. 3개년 구간 색상 구분(파랑→초록→보라). 핵심 마일스톤 별표 표시."),
            _slide(2, "단기 목표 (0~6개월)",
                   "MVP 출시→PMF 검증→유료 전환 20개사 달성. 월별 세부 실행 계획",
                   "월별 간트 차트(6개월). 주차별 핵심 Task. 목표 달성 기준(OKR 형태) 표."),
            _slide(3, "중기 목표 (6~18개월)",
                   "그로스 엔진 가동: MAU 2,000명·MRR 3,000만·시리즈 A 클로징",
                   "분기별 성장 그래프(MAU·MRR). 시리즈 A 유치 타임라인. 팀 확장 로드맵."),
            _slide(4, "장기 목표 (18개월~3년)",
                   "시장 점유율 5%·ARR 50억·동남아 진출. 글로벌 확장 전략 요약",
                   "세계 지도(진출 국가 핀 표시). 연도별 ARR 막대 차트."),
            _slide(5, "핵심 마일스톤 타임라인",
                   "M1~M5 마일스톤: 달성 시점·측정 기준·책임자 명시",
                   "수평 타임라인(다이아몬드 마커). 마커별 날짜·성과 지표."),
            _slide(6, "분기별 OKR",
                   "Q1~Q4 목표(O)와 핵심 결과(KR) 3개씩. 분기별 우선순위 명확화",
                   "OKR 테이블(분기별 행, O/KR 열). 달성 가중치 표시."),
            _slide(7, "팀 빌딩 계획",
                   "분기별 채용 포지션·인원. 1년 내 10명→2년 내 25명 확장 계획",
                   "조직 성장 타임라인. 분기별 추가 포지션 강조 박스."),
            _slide(8, "필요 자원 및 자금 계획",
                   "초기 자본 5억 배분: 인건비·인프라·마케팅·예비. 투자 유치 계획",
                   "파이 차트(자금 배분). 런웨이 계산(월 번율 vs 잔여 자금)."),
            _slide(9, "리스크 및 대응 계획",
                   "PMF 실패·경쟁사 반응·자금 소진·핵심 인력 이탈 4대 리스크 + 대응",
                   "리스크 매트릭스(2×2). 신호등 색상. Pivot 시나리오 별도 박스."),
            _slide(10, "성공 기준 및 Exit 전략",
                   "3년 내 흑자 전환 조건 + IPO/M&A 시나리오 검토",
                   "성공 기준 체크리스트. Exit 옵션 2개(IPO vs M&A) 비교 표. 강렬한 마무리 비전."),
        ],
    }


# ===========================================================================
# edu_plan_kr builders
# ===========================================================================

def _edu_objective(title: str, goal: str, ctx: str) -> dict:
    ctx_line = f" {ctx}" if ctx else ""
    return {
        "vision": (
            f"{title} 교육과정은 {goal}을 통해 학습자의 실질적인 역량을 키우는 것을 비전으로 합니다.{ctx_line} "
            "단순 지식 전달을 넘어 현장에서 바로 적용 가능한 실무 중심 교육을 지향합니다."
        ),
        "target_learners": [
            "비전공자로 관련 분야 입문을 원하는 성인 학습자 (대학생·직장인)",
            f"{title} 분야 기초 지식을 갖추고 심화 역량을 키우려는 중급자",
            "현업에서 새로운 기술·트렌드를 습득하고자 하는 실무자",
            "창업·부업·이직을 준비하는 커리어 전환자",
        ],
        "core_competencies": [
            f"{title} 핵심 개념 이해 및 현장 적용 능력",
            "도구·플랫폼 활용 실무 기술 (hands-on 프로젝트 기반)",
            "문제 해결 및 비판적 사고력 — 실제 케이스 스터디 훈련",
            "협업 및 커뮤니케이션 역량 — 팀 프로젝트 및 발표 경험",
        ],
        "learning_outcomes": [
            f"과정 수료 후 {goal} 관련 실무 프로젝트를 독립적으로 수행할 수 있다",
            "배운 내용을 실제 업무나 개인 프로젝트에 즉시 적용할 수 있다",
            "관련 자격증 취득 또는 포트폴리오 3개 이상 구성이 가능하다",
        ],
        "total_slides": 8,
        "slide_outline": [
            _slide(1, "교육 기관 소개 및 표지",
                   f"기관명·과정명({title})·대상·기간·슬로건",
                   "따뜻하고 전문적인 교육 이미지. 기관 로고 상단. 과정명 대형 Bold. 그린 또는 블루 계열."),
            _slide(2, "교육 비전 및 철학",
                   f"'{title}이 추구하는 교육 철학' — 왜 이 과정이 필요한가. 3대 교육 가치",
                   "비전 문구 중앙 대형 인용 스타일. 하단에 3대 가치 아이콘 카드. 따뜻한 컬러 배경."),
            _slide(3, "교육 대상 및 페르소나",
                   "수강 대상 4유형 페르소나: 역할·현재 고민·이 과정에서 얻는 것",
                   "4개 페르소나 카드(아바타 이미지+직업+Pain Point). '내가 해당된다'는 공감 구성."),
            _slide(4, "이 과정을 수료하면",
                   "Before(지금) vs After(수료 후) 비교: 할 수 있는 것, 갖게 되는 것",
                   "좌우 분할(Before 회색 / After 컬러). After 쪽에 포트폴리오·자격증·취업 아이콘."),
            _slide(5, "핵심 역량 4가지",
                   "4개 핵심 역량을 아이콘+한 줄 설명+습득 방법 구조로 제시",
                   "4분할 카드 레이아웃. 각 역량 아이콘+강조 컬러. 하단에 역량 간 연계성 화살표."),
            _slide(6, "학습 성취 기준",
                   "수료 조건과 성취 기준 4가지: 측정 가능한 행동 목표로 서술",
                   "체크리스트 스타일. 달성 가능성 강조(퍼센트/기간 명시). 수료생 성과 사례 인용."),
            _slide(7, "교육 차별화 포인트",
                   "타 과정 대비 우리 과정의 3가지 차별점: 실무·멘토·커뮤니티",
                   "차별점 3개 카드. 실무자 멘토 사진·후기 인용."),
            _slide(8, "수강 신청 안내",
                   "모집 일정·정원·수강료·할인 혜택·신청 방법. Call-to-Action",
                   "정보 정리 표(항목-내용). CTA 버튼 스타일 박스('지금 신청하기'). QR코드+연락처."),
        ],
    }


def _edu_curriculum(title: str, goal: str, ctx: str) -> dict:
    return {
        "subject_structure": [
            f"Module 1. {title} 기초 이론 (4주): 핵심 개념·원리·트렌드 이해",
            "Module 2. 도구 및 환경 세팅 (2주): 실습 환경 구축 및 핵심 툴 사용법",
            "Module 3. 실습 프로젝트 I (4주): 기본 케이스 중심 실습 및 피드백",
            "Module 4. 심화 응용 (3주): 복잡한 시나리오 대응 및 최적화 전략",
            "Module 5. 캡스톤 프로젝트 (3주): 실제 문제 해결 팀 프로젝트 발표",
        ],
        "weekly_plan": [
            "1~2주차: 오리엔테이션, 학습 목표 설정, 기초 이론 강의",
            "3~4주차: 핵심 도구 실습 및 미니 과제 수행",
            "5~8주차: 실습 프로젝트 I 수행 (매주 멘토 피드백 세션)",
            "9~11주차: 심화 케이스 분석 및 개인 역량 강화",
            "12~14주차: 팀 캡스톤 프로젝트 기획·개발·발표 준비",
            "15~16주차: 최종 발표, 수료식 및 취업·커리어 연계 세션",
        ],
        "special_activities": [
            "현업 전문가 특강 (격주 1회): 실제 업무 사례 및 커리어 인사이트 공유",
            "스터디 그룹 운영: 3~4인 자율 팀 구성, 주간 학습 내용 복습 및 토론",
            "포트폴리오 리뷰 세션: 외부 현업 멘토 초빙, 1:1 작품 피드백",
        ],
        "materials_and_tools": [
            "강의 영상: LMS(학습관리시스템) 통해 온디맨드 제공, 반복 수강 가능",
            "실습 환경: 클라우드 기반 개발 환경 제공 (별도 설치 불필요)",
            "교재: PDF 핵심 요약 자료 + 추천 도서 목록 제공",
        ],
        "total_slides": 12,
        "slide_outline": [
            _slide(1, "커리큘럼 전체 구성",
                   f"{title} 전체 커리큘럼 한눈에: 5개 모듈·16주 구성·핵심 성과",
                   "커리큘럼 로드맵 다이어그램(수평 흐름). 모듈별 컬러 구분. 각 모듈 위에 키워드 태그."),
            _slide(2, "Module 1 — 기초 이론 (1~4주)",
                   "핵심 개념·이론·용어 정리. 강의 형식: 온라인 영상+퀴즈. 주차별 주제",
                   "주차별 타임라인 바. 강의 주제 리스트. 학습 목표 박스 강조."),
            _slide(3, "Module 2 — 도구 실습 (5~6주)",
                   "사용 도구 목록 + 설치·세팅 가이드 요약 + 실습 환경 구성",
                   "도구 아이콘 배열(로고 그리드). 클라우드 환경 다이어그램. QR코드로 세팅 가이드."),
            _slide(4, "Module 3 — 실습 프로젝트 I (7~10주)",
                   "실습 프로젝트 주제 3개 + 매주 피드백 세션 구조 + 제출 형식",
                   "프로젝트 주제 카드 3개. 피드백 사이클 화살표 다이어그램. 작품 예시 썸네일."),
            _slide(5, "Module 4 — 심화 응용 (11~13주)",
                   "심화 케이스 3개 + 최적화 전략 + 개인 맞춤 심화 트랙",
                   "케이스 스터디 카드. 난이도 레벨 게이지. 선택 심화 트랙 분기 다이어그램."),
            _slide(6, "Module 5 — 캡스톤 프로젝트 (14~16주)",
                   "팀 구성→문제 정의→개발→발표 4단계 프로세스 + 평가 기준",
                   "프로젝트 단계 플로우차트. 팀 구성 방법(3~4인). 발표 일정 및 심사 위원 구성."),
            _slide(7, "주차별 상세 커리큘럼",
                   "전체 16주 주차별 강의 주제·과제·이벤트 한눈에 보기",
                   "16행 표(주차·주제·활동·산출물). 특강·프로젝트 행 컬러 강조."),
            _slide(8, "현업 전문가 특강",
                   "특강 라인업 예시: 강사 3~4명 프로필 + 강의 주제 + 일정",
                   "강사 카드(사진+이름+직함+주제). 격주 특강 일정 캘린더."),
            _slide(9, "스터디 그룹 운영 방법",
                   "팀 구성 기준 + 주간 스터디 가이드 + 온라인 커뮤니티 활용법",
                   "스터디 그룹 구조도(팀장+멤버). 슬랙 채널 구조 예시 이미지."),
            _slide(10, "포트폴리오 구성 가이드",
                   "수료 후 갖게 되는 포트폴리오 3개 예시: 주제·구성·기대 평가",
                   "포트폴리오 예시 썸네일 3개. 각 포트폴리오 포함 요소 리스트."),
            _slide(11, "교재 및 학습 자료",
                   "LMS 구조 + 핵심 교재 목록 + 추천 도서·유튜브·링크 모음",
                   "LMS 화면 목업. 교재 커버 이미지 3~4개. QR코드로 추천 자료 링크."),
            _slide(12, "커리큘럼 요약 및 수강 안내",
                   "16주 과정 압축 요약 + 수강 전 준비사항 + 문의 채널",
                   "커리큘럼 요약 인포그래픽(5모듈 원형 다이어그램). 준비사항 체크리스트."),
        ],
    }


def _edu_assessment(title: str, goal: str, ctx: str) -> dict:
    return {
        "assessment_methods": [
            "퀴즈 (20%): 매 모듈 종료 후 온라인 자동 채점 — 개념 이해도 확인",
            "과제 (30%): 실습 프로젝트 I·II 결과물 제출 — 기술 적용 역량 평가",
            "팀 프로젝트 (35%): 캡스톤 프로젝트 발표 및 동료 평가 포함",
            "출석 및 참여도 (15%): 수업 참여·커뮤니티 활동·스터디 기여도",
        ],
        "evaluation_criteria": [
            "과제: 완성도(40%) + 창의성(30%) + 코드/결과물 품질(30%)",
            "팀 프로젝트: 문제 정의(20%) + 해결 전략(30%) + 구현 완성도(30%) + 발표(20%)",
            "퀴즈: 정답률 80% 이상 시 해당 모듈 통과",
            "포트폴리오: 현업 멘토 평가 — 실무 적용 가능성·완성도·차별성 중심",
        ],
        "feedback_process": (
            "과제 제출 후 7일 이내 강사의 서면 피드백을 제공합니다. "
            "점수와 함께 잘한 점·개선 방향·추가 학습 자료를 명시하며, "
            "최종 프로젝트는 발표 당일 현장 피드백 + 2주 내 서면 평가 리포트를 제공합니다."
        ),
        "appeal_process": (
            "성적에 이의가 있을 경우 결과 공지 후 5일 이내에 LMS 내 이의신청 폼을 통해 접수합니다. "
            "강사와 교육 운영팀이 함께 재검토하며, 신청 후 7일 이내 최종 결론을 통보합니다."
        ),
        "total_slides": 8,
        "slide_outline": [
            _slide(1, "평가 체계 개요",
                   "전체 평가 구성: 퀴즈·과제·팀 프로젝트·참여도 4가지 + 비중 도넛 차트",
                   "도넛 파이 차트(비중별 컬러). 공정하고 투명한 인상 주는 클린 디자인."),
            _slide(2, "퀴즈 평가 (20%)",
                   "실시 시점(모듈별)·문항 수·통과 기준(80%)·재시험 정책",
                   "퀴즈 일정 타임라인. 문제 유형 예시 스크린샷. LMS 자동 채점 흐름 설명."),
            _slide(3, "과제 평가 (30%)",
                   "제출 과제 목록 + 각 과제별 평가 기준표(완성도·창의성·품질)",
                   "과제별 행·평가 기준별 열 테이블. 가중치 표시. 우수 과제 예시 썸네일."),
            _slide(4, "팀 프로젝트 평가 (35%)",
                   "캡스톤 프로젝트 평가 4개 축: 문제정의·전략·구현·발표. 동료 평가 포함",
                   "레이더 차트(4개 축). 평가 단계 플로우(자체→동료→멘토→강사)."),
            _slide(5, "출석 및 참여도 (15%)",
                   "출석 기준(80% 이상 필수)·커뮤니티 활동 점수·스터디 기여도",
                   "출석 게이지 시각화. 참여도 점수 항목별 표."),
            _slide(6, "수료 기준 및 인증서",
                   "수료 조건: 출석 80%+총점 60점 이상. 수료증 샘플 이미지",
                   "수료 조건 체크리스트. 수료증 디자인 목업 이미지. 우수 수료생 인증 조건."),
            _slide(7, "피드백 및 이의신청 절차",
                   "피드백 제공 타임라인(7일 이내) + 이의신청 5일 내 접수→7일 내 결론",
                   "프로세스 플로우차트(제출→채점→피드백→이의신청→재검토)."),
            _slide(8, "평가 투명성 및 공정성 원칙",
                   "루브릭 공개 원칙·외부 멘토 참여·동료 평가 운영 방식",
                   "투명성 아이콘(저울·눈) 강조 디자인. 루브릭 예시 표 삽입."),
        ],
    }


def _edu_operation_plan(title: str, goal: str, ctx: str) -> dict:
    return {
        "facilities_and_staff": [
            "강사진: 현업 10년+ 전문가 2명 (메인) + 보조 강사 1명 + 멘토 네트워크 5명",
            "운영 인력: 교육 매니저 1명, CS 담당 1명, LMS 관리자 1명",
            "오프라인 공간: 30석 규모 강의실 1개 + 팀 스터디룸 2개 (필요시 대관)",
            "온라인 인프라: LMS 플랫폼, 화상회의 도구(Zoom/Meet), 슬랙 워크스페이스",
        ],
        "annual_schedule": [
            "1분기 (1~3월): 상반기 과정 모집 및 오리엔테이션, 1기 수강생 교육 시작",
            "2분기 (4~6월): 1기 교육 진행·수료, 2기 모집 및 커리큘럼 개선 반영",
            "3분기 (7~9월): 2기 교육 진행, 하반기 특별 단기 과정 기획·운영",
            "4분기 (10~12월): 3기 모집·교육, 연간 성과 분석 및 내년 커리큘럼 개편",
        ],
        "budget_plan": [
            "인건비: 강사료·운영 인력 인건비 — 총 예산의 55% (연간 약 5,500만 원)",
            "마케팅·홍보: SNS·검색광고·콘텐츠 마케팅 — 총 예산의 20% (2,000만 원)",
            "인프라·플랫폼: LMS 구독·클라우드 실습 환경·소프트웨어 라이선스 — 10%",
            "시설·운영: 강의실 대관·교재 제작·행정비용 — 10%, 예비비 5%",
        ],
        "emergency_plan": (
            "강사 급작스러운 불가 상황 시: 보조 강사 즉시 대체, 해당 차시 1주 이월 운영. "
            "자연재해·감염병 등 집합 금지 상황 시: 전면 온라인 전환 (화상 강의 + LMS 비동기 학습). "
            "LMS 시스템 장애 시: 72시간 이내 복구를 SLA로 보장, 장애 기간 수강 기한 자동 연장."
        ),
        "total_slides": 10,
        "slide_outline": [
            _slide(1, "운영 계획 개요",
                   f"{title} 연간 운영 계획 요약: 기수·인력·예산·일정 4가지 핵심 요소",
                   "4개 핵심 지표 카드(기수 수·총 인원·예산·운영 기간). 다크 블루 또는 그린 배경."),
            _slide(2, "운영 조직 및 인력 구성",
                   "강사진 소개 + 운영 인력 역할 분장표 + 외부 멘토 네트워크",
                   "조직도(강사장→강사→운영→CS). 각 포지션 사진+이름+역할."),
            _slide(3, "시설 및 인프라",
                   "오프라인 시설(강의실·스터디룸) 레이아웃 + 온라인 인프라 구성도",
                   "시설 사진 또는 플로어 맵. 온라인 도구 아이콘 구성도(LMS→Zoom→Slack)."),
            _slide(4, "연간 운영 일정 (캘린더)",
                   "4분기 캘린더: 모집·개강·수료·특강·방학 일정 한눈에",
                   "12개월 캘린더 레이아웃. 이벤트별 색상 코딩. 기수별 구간 강조 표시."),
            _slide(5, "기수별 모집 및 운영 계획",
                   "1기~3기 모집 인원·모집 채널·합격 기준·오리엔테이션 일정",
                   "기수별 행+항목별 열 테이블. 모집 채널 비중 파이 차트."),
            _slide(6, "예산 계획",
                   "항목별 예산 배분: 인건비·마케팅·인프라·시설·예비비",
                   "도넛 파이 차트(항목별 비중). 항목별 금액 표(월·연간)."),
            _slide(7, "마케팅 및 모집 전략",
                   "채널별 모집 전략: SNS(인스타·유튜브)·검색광고·커뮤니티·추천 할인",
                   "채널 믹스 막대 차트(예산 비중). 모집 퍼널(인지→관심→지원→등록)."),
            _slide(8, "품질 관리 및 개선 프로세스",
                   "수강생 만족도 조사 → 분석 → 커리큘럼 개선 → 다음 기수 반영 사이클",
                   "PDCA 사이클 다이어그램. 만족도 측정 지표(NPS·완료율·추천율)."),
            _slide(9, "비상 운영 계획",
                   "강사 불가·감염병·시스템 장애·수강생 미달 4개 시나리오별 대응 방안",
                   "시나리오별 카드(빨간 테두리+대응 방안). 의사결정 트리 플로우차트."),
            _slide(10, "기대 성과 및 운영 비전",
                   f"3년 내 수료생 500명 목표 + 취업률·만족도 KPI + {title} 브랜드 성장 계획",
                   "성장 목표 그래프(수강생 수 누적). 취업률·NPS 게이지. 마무리 비전 문구."),
        ],
    }


# ===========================================================================
# presentation_kr builders
# ===========================================================================

def _presentation_slide_structure(title: str, goal: str, ctx: str) -> dict:
    ctx_note = f" ({ctx})" if ctx else ""
    return {
        "presentation_goal": f"{title}에 관한 발표를 통해 {goal}을 청중에게 효과적으로 전달합니다.{ctx_note}",
        "target_audience": "수업 담당 교수 및 동료 학생 / 업무 발표 참석자",
        "key_messages": [
            f"{title}의 핵심 문제와 해결 방향",
            f"{goal}을 통해 기대되는 구체적 효과",
            "실행 가능한 다음 단계와 결론",
        ],
        "total_slides": 5,
        "slide_outline": [
            _slide(1, f"{title} — 발표 개요",
                   f"발표 배경: {goal}\n발표 구성: 문제 → 분석 → 해결책 → 기대 효과 → 결론",
                   "표지 슬라이드. 제목 중앙 대형 Bold, 배경 심플하게."),
            _slide(2, "문제 정의 및 배경",
                   f"{title}이 해결하려는 핵심 문제\n현재 Pain Point 2~3가지\n해결 시 기대 변화",
                   "좌측 현재 상황 아이콘, 우측 문제 카드. 핵심 수치 강조 박스."),
            _slide(3, "핵심 내용 및 분석",
                   f"{goal}을 달성하기 위한 핵심 접근법\n주요 근거 데이터 또는 논리 구조",
                   "2~3단 분할 또는 비교 테이블. 핵심 키워드 Bold."),
            _slide(4, "제안 및 기대 효과",
                   "제안하는 해결책 또는 결론\n예상 효과: 효율 향상, 비용 절감\n실행 로드맵",
                   "Before/After 비교 또는 로드맵 타임라인."),
            _slide(5, "결론 및 Q&A",
                   f"핵심 메시지 3줄 요약\n{title} 발표의 의의\nQ&A 안내",
                   "미니멀 마무리. 핵심 메시지 중앙 Bold. 하단 참고문헌."),
        ],
    }


def _presentation_slide_script(title: str, goal: str, ctx: str) -> dict:  # noqa: ARG001
    return {
        "opening": (
            f"안녕하세요. '{title}'을 주제로 발표를 맡은 [발표자]입니다. "
            f"{goal}에 대해 함께 살펴보겠습니다. 약 [X]분간 진행됩니다."
        ),
        "body_scripts": [
            f"[슬라이드 2] 먼저 문제 배경입니다. {title}과 관련하여 현재 [문제]가 발생하고 있습니다.",
            f"[슬라이드 3] {goal}을 달성하기 위해 [접근 방법]을 선택하였습니다.",
            "[슬라이드 4] 기대 효과는 [효과 1], [효과 2]이며 실행 계획은 [로드맵]입니다.",
        ],
        "closing": f"오늘 발표에서는 {title}의 문제, 분석, 제안을 살펴보았습니다. 청취해주셔서 감사합니다.",
        "time_allocation": "오프닝: 1분 / 본론: 11분 / 결론 및 Q&A: 3분 (총 15분)",
    }


def _presentation_qa_preparation(title: str, goal: str, ctx: str) -> dict:  # noqa: ARG001
    return {
        "anticipated_questions": [
            f"{goal}을 선택한 근거는 무엇인가요?",
            "제안의 한계점이나 위험 요소는 없나요?",
            "다른 대안과 비교 시 장점은 무엇인가요?",
            "실제 적용에 필요한 자원은 얼마나 되나요?",
        ],
        "answers": [
            f"{goal} 선택 이유는 [근거 1]과 [근거 2]입니다.",
            "한계로는 [한계 1]이 있으며, [대응 방안]을 준비했습니다.",
            "[대안 A]보다 [장점 1], [장점 2] 측면에서 우위입니다.",
            "[예상 기간]과 [예산]이 필요합니다.",
        ],
        "difficult_questions": [
            "데이터 신뢰성 → 복수 출처 교차 검증으로 보장.",
            "플랜 B → [대안 방안] 준비, 단계적 rollback 고려.",
        ],
        "presentation_tips": [
            "핵심 수치는 슬라이드에 미리 표시 후 구두로 강조.",
            "모르는 질문엔 솔직히 인정하고 추가 조사 후 공유 약속.",
            "각 슬라이드 배분 시간을 미리 연습하여 시간 준수.",
        ],
    }


# ===========================================================================
# Registry: (bundle_id, doc_key) → content builder function
# ===========================================================================
_CONTENT_BUILDERS: dict[tuple[str, str], Any] = {
    ("bid_decision_kr",  "opportunity_brief"):      _bid_decision_opportunity_brief,
    ("bid_decision_kr",  "go_no_go_memo"):          _bid_decision_go_no_go_memo,
    ("bid_decision_kr",  "bid_readiness_checklist"): _bid_decision_checklist,
    ("bid_decision_kr",  "proposal_kickoff_summary"): _bid_decision_handoff,
    ("proposal_kr",      "business_understanding"): _proposal_business_understanding,
    ("proposal_kr",      "tech_proposal"):          _proposal_tech_proposal,
    ("proposal_kr",      "execution_plan"):         _proposal_execution_plan,
    ("proposal_kr",      "expected_impact"):        _proposal_expected_impact,
    ("rfp_analysis_kr",  "rfp_summary"):            _rfp_analysis_summary,
    ("rfp_analysis_kr",  "win_strategy"):           _rfp_analysis_win_strategy,
    ("performance_plan_kr", "performance_overview"): _performance_overview,
    ("performance_plan_kr", "quality_risk_plan"):    _performance_quality_risk,
    ("business_plan_kr", "business_overview"):      _business_overview,
    ("business_plan_kr", "market_analysis"):        _business_market_analysis,
    ("business_plan_kr", "business_model"):         _business_model,
    ("business_plan_kr", "execution_roadmap"):      _business_execution_roadmap,
    ("edu_plan_kr",      "edu_objective"):          _edu_objective,
    ("edu_plan_kr",      "curriculum"):             _edu_curriculum,
    ("edu_plan_kr",      "assessment"):             _edu_assessment,
    ("edu_plan_kr",      "operation_plan"):         _edu_operation_plan,
    ("presentation_kr",  "slide_structure"):        _presentation_slide_structure,
    ("presentation_kr",  "slide_script"):           _presentation_slide_script,
    ("presentation_kr",  "qa_preparation"):         _presentation_qa_preparation,
}
