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
from app.providers.mock.registry import _CONTENT_BUILDERS
from app.providers.mock.shared import _ctx_excerpt, _extract_document_ops_payload


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
            str(requirements.get("_procurement_review_context") or "").strip(),
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

        if "DecisionDoc DocumentOps Agent" in prompt:
            payload = _extract_document_ops_payload(prompt)
            task_type = str(payload.get("task_type") or "")
            requirements = payload.get("requirements") if isinstance(payload.get("requirements"), dict) else {}
            source_references = payload.get("source_references") if isinstance(payload.get("source_references"), list) else []
            title = str(requirements.get("title") or "DecisionDoc 문서")
            goal = str(
                requirements.get("goal")
                or requirements.get("decision_needed")
                or requirements.get("objective")
                or "검토 가능한 실행 방향 수립"
            )
            source_labels = [
                str(item.get("id") or item.get("title") or item.get("path"))
                for item in source_references
                if isinstance(item, dict) and (item.get("id") or item.get("title") or item.get("path"))
            ]
            gaps = [] if source_labels else ["공식 근거 또는 기준 문서 확인 필요"]
            if task_type == "develop_quality_improvement":
                current_draft = str(
                    requirements.get("draft")
                    or requirements.get("current_draft")
                    or requirements.get("goal")
                    or ""
                )
                critique = [
                    "승인자가 먼저 판단해야 할 질문과 권고가 초안 앞부분에 충분히 드러나야 합니다.",
                    "확인된 근거, 가정, TODO가 섞이면 학습 후보와 제출 문서 모두에서 리스크가 커집니다.",
                    "운영 책임, 개인정보, 보안, 로그/감사 항목은 별도 검토 지점으로 분리해야 합니다.",
                ]
                revision_tasks = [
                    "핵심 판단을 첫 섹션으로 이동하고 승인 질문을 명시합니다.",
                    "출처가 없는 수치, 일정, 성과 표현은 TODO 또는 가정으로 낮춥니다.",
                    "남은 source gap과 owner gap을 문서 끝에 별도 정리합니다.",
                ]
                source_note = "확인된 source reference를 기준으로 개선합니다." if source_labels else "source reference가 없어 확인 필요 항목을 TODO로 유지합니다."
                draft = (
                    f"# {title} 개선안\n\n"
                    "## 품질 개선 요약\n"
                    f"{goal}에 맞춰 기존 초안의 판단 순서, 근거 구분, 운영 리스크를 다시 정리합니다. {source_note}\n\n"
                    "## 개선본\n"
                    "- 승인 질문: 현재 제안이 실행 가능한 의사결정 단위인지 검토합니다.\n"
                    "- 근거 상태: confirmed, assumption, TODO를 분리하고 출처 없는 표현은 단정하지 않습니다.\n"
                    "- 운영 관점: 개인정보, 보안, 운영책임, 로그/감사, 변경관리 항목을 후속 검토 대상으로 둡니다.\n\n"
                    "## 기존 초안 반영\n"
                    f"{_ctx_excerpt(current_draft, 360) if current_draft else '기존 초안 본문은 제공되지 않았으므로 개선 방향만 제시합니다.'}\n\n"
                    "## 남은 리스크\n"
                    "source gap, owner gap, 승인 전 검토 범위를 문서 리뷰 단계에서 다시 확인합니다."
                )
            elif task_type == "evidence_gap_review":
                critique = [
                    "초안의 수치, 일정, 기관명은 source-backed claim인지 재확인이 필요합니다.",
                    "confirmed와 TODO가 섞이지 않도록 제출 전 evidence status를 분리해야 합니다.",
                ]
                revision_tasks = [
                    "확인된 claim만 confirmed로 유지합니다.",
                    "출처가 없는 항목은 TODO/source-needed로 이동합니다.",
                ]
                draft = (
                    f"# {title}\n\n"
                    "## 근거 점검 결과\n"
                    "- confirmed: 현재 입력에서 공식 근거로 확정 가능한 항목은 제한적입니다.\n"
                    "- assumed: 사용자 초안의 방향성은 검토 대상으로 유지합니다.\n"
                    "- TODO: 수치, KPI, 일정, 기관명은 제출 전 출처 확인이 필요합니다.\n"
                    "\n## 공유 판단\n근거가 확인되지 않은 항목은 단정 표현을 피하고 TODO로 분리합니다."
                )
            elif task_type == "decision_brief":
                critique = [
                    "결정 질문과 권고가 앞부분에서 바로 확인되어야 합니다.",
                    "남은 TODO를 리스크와 다음 액션으로 연결해야 합니다.",
                ]
                revision_tasks = [
                    "권고안을 첫 섹션에 배치합니다.",
                    "선택지, 리스크, 다음 owner gap을 짧게 정리합니다.",
                ]
                draft = (
                    f"# {title}\n\n"
                    f"## 결정 필요\n{goal}\n\n"
                    "## 권고\n확인된 근거와 남은 TODO를 분리한 뒤 승인자가 선택할 수 있는 실행안을 제시합니다.\n\n"
                    "## 리스크\n공식 근거가 없는 수치나 성과 주장은 제출 문서에서 단정하지 않습니다."
                )
            else:
                critique = [
                    "문제, 근거, 실행 경로, 운영 책임이 승인 흐름에 맞게 연결되어야 합니다.",
                    "정책 문서에서 개인정보, 보안, 로그/감사 검토가 누락되지 않아야 합니다.",
                ]
                revision_tasks = [
                    "승인 질문과 정책 필요성을 앞부분에 배치합니다.",
                    "근거 상태와 운영 리스크를 별도 섹션으로 분리합니다.",
                ]
                draft = (
                    f"# {title}\n\n"
                    f"## 핵심 판단\n{goal}을 달성하기 위해 문제, 근거, 실행 경로, 운영 책임을 분리합니다.\n\n"
                    "## 정책 기획 방향\n"
                    "- 문제와 반복 원인을 먼저 정의합니다.\n"
                    "- 기존 인프라와 운영 절차를 활용하는 실행 경로를 제시합니다.\n"
                    "- 개인정보, 보안, 로그관리, 운영책임, 변경관리를 검토합니다."
                )
            return _json.dumps({
                "plan": [
                    "요구사항과 승인 질문을 분리합니다.",
                    "확인된 근거, 가정, TODO를 구분합니다.",
                    "정책 논리와 운영 절차를 연결해 공유 가능한 초안을 작성합니다.",
                ],
                "critique": critique,
                "revision_tasks": revision_tasks,
                "draft": draft,
                "evidence_status": {
                    "confirmed": source_labels,
                    "assumptions": ["입력된 요구사항은 검토 초안 기준으로 유효하다고 가정"],
                    "gaps": gaps,
                    "source_references": source_labels,
                },
                "qa": {
                    "hard_gate_pass": not gaps,
                    "warnings": gaps,
                    "mock_provider": True,
                },
            }, ensure_ascii=False)

        if "report workflow planner" in prompt.lower():
            return _json.dumps({
                "objective": "보고서 목적과 승인 흐름을 한눈에 이해할 수 있게 구성합니다.",
                "audience": "PM, 대표, 최종 의사결정권자",
                "executive_message": "기획 승인 후 장표 제작으로 이어지는 단계형 보고서 품질 관리를 적용합니다.",
                "planning_brief": "보고서 제작 전 승인권자가 검토할 의사결정 질문, 근거 전략, 장표별 완성 기준을 먼저 확정합니다.",
                "audience_decision_needs": [
                    "프로젝트 목적과 승인 요청 범위가 명확한가",
                    "첨부자료 근거가 핵심 주장에 충분히 연결되는가",
                    "실행 계획과 리스크 대응이 승인 가능한 수준인가",
                ],
                "narrative_arc": [
                    "핵심 메시지로 의사결정 안건을 먼저 제시",
                    "현황 진단에서 문제와 근거를 연결",
                    "제안 방향과 실행 계획으로 해결 가능성을 설명",
                    "기대 효과와 승인 요청으로 다음 액션을 명확화",
                ],
                "source_strategy": [
                    "입력 요구사항은 표지/핵심 메시지 장표에 반영",
                    "첨부자료 요약은 현황 진단과 제안 방향의 required_evidence로 매핑",
                    "근거가 부족한 항목은 open_questions와 data_needs로 분리",
                ],
                "template_guidance": [
                    "각 장표는 headline, evidence, decision block 구조를 기본으로 사용",
                    "정량 근거는 카드 또는 표, 실행 흐름은 단계형 다이어그램으로 표현",
                    "승인 요청 장표는 결정 항목과 후속 액션을 분리해 표시",
                ],
                "quality_bar": [
                    "장표별 decision_question이 key_message와 직접 연결됨",
                    "각 장표의 required_evidence와 data_needs가 구분됨",
                    "PM이 수정 요청 없이 제작 담당자에게 넘길 수 있을 만큼 구체적임",
                ],
                "table_of_contents": ["핵심 메시지", "현황 진단", "제안 방향", "실행 계획", "기대 효과", "승인 요청"],
                "slide_plans": [
                    {
                        "slide_id": f"slide-{idx:03d}",
                        "page": idx,
                        "title": title,
                        "purpose": f"{title} 내용을 의사결정자가 검토할 수 있게 설명합니다.",
                        "key_message": f"{title} 기준의 핵심 판단 포인트를 제시합니다.",
                        "decision_question": f"{title} 장표에서 승인권자가 판단해야 할 핵심 질문은 무엇인가?",
                        "narrative_role": "전체 보고서 흐름에서 다음 의사결정으로 넘어가기 위한 근거를 제공합니다.",
                        "layout": "상단 핵심 메시지, 좌측 근거, 우측 시각자료",
                        "visual_direction": "요약 카드와 흐름도 중심",
                        "required_evidence": ["입력 요구사항", "첨부자료 요약"],
                        "content_blocks": ["핵심 주장", "근거 요약", "승인 판단 포인트"],
                        "data_needs": ["정량 수치 확인", "첨부자료 출처 매핑"],
                        "design_notes": ["headline은 한 문장 결론으로 작성", "근거와 의사결정 블록을 시각적으로 분리"],
                        "acceptance_criteria": ["핵심 질문에 대한 답이 명확함", "필요 근거와 추가 확인 항목이 구분됨"],
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
