"""tests/test_golden_examples.py — 골든 예시 업데이트 검증.

각 번들에 대해:
1. 번들이 오류 없이 로드되는지 확인
2. few_shot_example이 400자 이상인지 확인
3. 골든 예시 .md 파일이 존재하고 내용이 있는지 확인
4. 핵심 콘텐츠 키워드가 포함되어 있는지 확인

대상 번들 (8개):
- proposal_kr         — 보건복지부 복지급여 AI 자동심사 (18억원, 12개월)
- rfp_analysis_kr     — 국토교통부 도로시설물 AI 안전점검 (22억원)
- performance_plan_kr — 기획재정부 NAFIS 고도화 (35억원, 18개월)
- completion_report_kr— 서울시 AI 민원상담 챗봇 (8억원)
- interim_report_kr   — 경기도 복지 통합관리 플랫폼 (12억원)
- task_order_kr       — 조달청 전자조달 AI 계약관리 (15억원)
- project_report_kr   — NIA 공공 AI 학습 데이터 구축 (24억원)
- meeting_minutes_kr  — 행안부 디지털정부 AI 전략 킥오프
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

# ── 경로 상수 ─────────────────────────────────────────────────────────────────
BUNDLES_DIR = Path(__file__).parent.parent / "app" / "bundle_catalog" / "bundles"
GOLDEN_DIR = Path(__file__).parent.parent / "app" / "bundle_catalog" / "golden_examples"

BUNDLE_IDS = [
    "proposal_kr",
    "rfp_analysis_kr",
    "performance_plan_kr",
    "completion_report_kr",
    "interim_report_kr",
    "task_order_kr",
    "project_report_kr",
    "meeting_minutes_kr",
]

MIN_FEW_SHOT_CHARS = 400
MIN_MD_CHARS = 500


# ── 헬퍼 ──────────────────────────────────────────────────────────────────────

def _load_bundle_spec(bundle_id: str):
    """번들 Python 파일을 임포트해 BundleSpec 객체를 반환."""
    import importlib
    module_name = f"app.bundle_catalog.bundles.{bundle_id}"
    module = importlib.import_module(module_name)
    # BundleSpec 인스턴스 찾기 (모듈 최상위 변수)
    from app.bundle_catalog.spec import BundleSpec
    for attr in dir(module):
        obj = getattr(module, attr)
        if isinstance(obj, BundleSpec) and obj.id == bundle_id:
            return obj
    raise RuntimeError(f"BundleSpec with id='{bundle_id}' not found in {module_name}")


def _get_golden_md(bundle_id: str) -> Path:
    return GOLDEN_DIR / f"{bundle_id}_example.md"


# ── 번들 로드 + few_shot_example 길이 테스트 ──────────────────────────────────

class TestBundleLoadsWithoutError:
    """각 번들이 오류 없이 임포트되는지 확인."""

    @pytest.mark.parametrize("bundle_id", BUNDLE_IDS)
    def test_bundle_imports_without_error(self, bundle_id: str):
        spec = _load_bundle_spec(bundle_id)
        assert spec is not None, f"{bundle_id} BundleSpec를 로드할 수 없습니다"
        assert spec.id == bundle_id, f"id 불일치: 예상 {bundle_id}, 실제 {spec.id}"

    @pytest.mark.parametrize("bundle_id", BUNDLE_IDS)
    def test_bundle_has_docs(self, bundle_id: str):
        spec = _load_bundle_spec(bundle_id)
        assert len(spec.docs) >= 1, f"{bundle_id}에 docs가 없습니다"


class TestFewShotExampleLength:
    """few_shot_example이 최소 400자 이상인지 확인."""

    @pytest.mark.parametrize("bundle_id", BUNDLE_IDS)
    def test_few_shot_example_min_length(self, bundle_id: str):
        spec = _load_bundle_spec(bundle_id)
        length = len(spec.few_shot_example)
        assert length >= MIN_FEW_SHOT_CHARS, (
            f"{bundle_id}.few_shot_example 길이 {length}자 — "
            f"최소 {MIN_FEW_SHOT_CHARS}자 필요"
        )

    @pytest.mark.parametrize("bundle_id", BUNDLE_IDS)
    def test_few_shot_example_is_string(self, bundle_id: str):
        spec = _load_bundle_spec(bundle_id)
        assert isinstance(spec.few_shot_example, str), (
            f"{bundle_id}.few_shot_example이 str이 아닙니다: {type(spec.few_shot_example)}"
        )


# ── 골든 예시 .md 파일 테스트 ─────────────────────────────────────────────────

class TestGoldenMdFiles:
    """골든 예시 .md 파일의 존재 및 내용 확인."""

    @pytest.mark.parametrize("bundle_id", BUNDLE_IDS)
    def test_md_file_exists(self, bundle_id: str):
        path = _get_golden_md(bundle_id)
        assert path.exists(), f"골든 예시 파일 없음: {path}"

    @pytest.mark.parametrize("bundle_id", BUNDLE_IDS)
    def test_md_file_min_length(self, bundle_id: str):
        path = _get_golden_md(bundle_id)
        content = path.read_text(encoding="utf-8")
        assert len(content) >= MIN_MD_CHARS, (
            f"{path.name} 내용 {len(content)}자 — 최소 {MIN_MD_CHARS}자 필요"
        )

    @pytest.mark.parametrize("bundle_id", BUNDLE_IDS)
    def test_md_file_has_section_headings(self, bundle_id: str):
        path = _get_golden_md(bundle_id)
        content = path.read_text(encoding="utf-8")
        assert "##" in content, f"{path.name}에 섹션 헤딩(##)이 없습니다"


# ── 핵심 키워드 포함 여부 테스트 ──────────────────────────────────────────────

class TestFewShotExampleContent:
    """각 번들의 few_shot_example에 핵심 키워드가 포함됐는지 확인."""

    def test_proposal_kr_contains_welfare_keywords(self):
        spec = _load_bundle_spec("proposal_kr")
        text = spec.few_shot_example
        assert "보건복지부" in text, "proposal_kr에 '보건복지부' 없음"
        assert "복지급여" in text or "자동심사" in text, (
            "proposal_kr에 '복지급여' 또는 '자동심사' 없음"
        )

    def test_rfp_analysis_kr_contains_procurement_keywords(self):
        spec = _load_bundle_spec("rfp_analysis_kr")
        text = spec.few_shot_example
        assert "국토교통부" in text, "rfp_analysis_kr에 '국토교통부' 없음"
        assert "2,200,000,000" in text or "22억" in text, (
            "rfp_analysis_kr에 예산 정보 없음"
        )

    def test_performance_plan_kr_contains_nafis_keywords(self):
        spec = _load_bundle_spec("performance_plan_kr")
        text = spec.few_shot_example
        assert "기획재정부" in text or "NAFIS" in text, (
            "performance_plan_kr에 '기획재정부' 또는 'NAFIS' 없음"
        )
        assert "3,500,000,000" in text or "35억" in text, (
            "performance_plan_kr에 예산 정보 없음"
        )

    def test_completion_report_kr_contains_seoul_chatbot_keywords(self):
        spec = _load_bundle_spec("completion_report_kr")
        text = spec.few_shot_example
        assert "서울" in text, "completion_report_kr에 '서울' 없음"
        assert "챗봇" in text or "하자보수" in text, (
            "completion_report_kr에 '챗봇' 또는 '하자보수' 없음"
        )

    def test_interim_report_kr_contains_gyeonggi_keywords(self):
        spec = _load_bundle_spec("interim_report_kr")
        text = spec.few_shot_example
        assert "경기도" in text, "interim_report_kr에 '경기도' 없음"
        assert "진척" in text or "이슈" in text, (
            "interim_report_kr에 '진척' 또는 '이슈' 없음"
        )

    def test_task_order_kr_contains_koneps_keywords(self):
        spec = _load_bundle_spec("task_order_kr")
        text = spec.few_shot_example
        assert "조달청" in text, "task_order_kr에 '조달청' 없음"
        assert "SHALL" in text, "task_order_kr에 'SHALL' 요구사항 표현 없음"

    def test_project_report_kr_contains_nia_keywords(self):
        spec = _load_bundle_spec("project_report_kr")
        text = spec.few_shot_example
        assert "NIA" in text or "지능정보사회진흥원" in text, (
            "project_report_kr에 'NIA' 또는 '지능정보사회진흥원' 없음"
        )
        assert "학습 데이터" in text or "데이터 구축" in text, (
            "project_report_kr에 '학습 데이터' 없음"
        )

    def test_meeting_minutes_kr_contains_mois_kickoff_keywords(self):
        spec = _load_bundle_spec("meeting_minutes_kr")
        text = spec.few_shot_example
        assert "행정안전부" in text or "행안부" in text, (
            "meeting_minutes_kr에 '행정안전부' 또는 '행안부' 없음"
        )
        assert "액션 아이템" in text or "의사결정" in text, (
            "meeting_minutes_kr에 '액션 아이템' 또는 '의사결정' 없음"
        )


# ── 골든 .md 파일 키워드 테스트 ───────────────────────────────────────────────

class TestGoldenMdContent:
    """각 골든 예시 .md 파일에 핵심 수치·기관명이 포함됐는지 확인."""

    def test_proposal_kr_md_has_welfare_figures(self):
        content = _get_golden_md("proposal_kr").read_text(encoding="utf-8")
        assert "840만" in content or "복지급여" in content, (
            "proposal_kr_example.md에 '840만' 또는 '복지급여' 없음"
        )

    def test_rfp_analysis_kr_md_has_evaluation_table(self):
        content = _get_golden_md("rfp_analysis_kr").read_text(encoding="utf-8")
        assert "평가항목" in content, "rfp_analysis_kr_example.md에 '평가항목' 없음"

    def test_performance_plan_kr_md_has_wbs(self):
        content = _get_golden_md("performance_plan_kr").read_text(encoding="utf-8")
        assert "WBS" in content, "performance_plan_kr_example.md에 'WBS' 없음"

    def test_completion_report_kr_md_has_performance_table(self):
        content = _get_golden_md("completion_report_kr").read_text(encoding="utf-8")
        assert "성과 측정" in content or "달성률" in content, (
            "completion_report_kr_example.md에 '성과 측정' 없음"
        )

    def test_interim_report_kr_md_has_progress_table(self):
        content = _get_golden_md("interim_report_kr").read_text(encoding="utf-8")
        assert "진척" in content, "interim_report_kr_example.md에 '진척' 없음"

    def test_task_order_kr_md_has_deliverables(self):
        content = _get_golden_md("task_order_kr").read_text(encoding="utf-8")
        assert "납품물" in content, "task_order_kr_example.md에 '납품물' 없음"

    def test_project_report_kr_md_has_lessons_learned(self):
        content = _get_golden_md("project_report_kr").read_text(encoding="utf-8")
        assert "교훈" in content or "개선" in content, (
            "project_report_kr_example.md에 '교훈' 없음"
        )

    def test_meeting_minutes_kr_md_has_action_items(self):
        content = _get_golden_md("meeting_minutes_kr").read_text(encoding="utf-8")
        assert "액션 아이템" in content, (
            "meeting_minutes_kr_example.md에 '액션 아이템' 없음"
        )
