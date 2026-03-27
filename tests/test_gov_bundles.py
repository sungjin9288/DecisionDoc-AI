"""Tests for the 6 나라장터 (government procurement) specialized bundles.

Covers:
- Bundle loading and field validation (5 tests × 6 bundles = 30 structural tests)
- Integration test per bundle: mock generate → validate output structure (6 tests)
- Registry presence and count (3 tests)
- Style-guide override registration check (1 test)

Minimum: 36+ tests total.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.bundle_catalog.registry import BUNDLE_REGISTRY
from app.bundle_catalog.spec import BundleSpec, DocumentSpec

# ── Constants ─────────────────────────────────────────────────────────────────

GOV_BUNDLE_IDS = [
    "bid_decision_kr",
    "rfp_analysis_kr",
    "performance_plan_kr",
    "completion_report_kr",
    "interim_report_kr",
    "task_order_kr",
]

# Expected doc key counts per bundle
_DOC_COUNTS = {
    "bid_decision_kr":      4,
    "rfp_analysis_kr":      2,
    "performance_plan_kr":  2,
    "completion_report_kr": 1,
    "interim_report_kr":    1,
    "task_order_kr":        1,
}

# Expected critical_non_empty_headings per bundle/doc
_CRITICAL_HEADINGS = {
    "bid_decision_kr": {
        "opportunity_brief": ["## 공고 개요", "## 상업 조건 및 일정"],
        "go_no_go_memo": ["## 추천 결론", "## 결정 근거"],
        "bid_readiness_checklist": ["## 즉시 확인 필요 항목", "## 최종 준비도 판단"],
        "proposal_kickoff_summary": ["## 결정 요약", "## 다음 단계"],
    },
    "rfp_analysis_kr": {
        "rfp_summary":  ["## RFP 핵심 요약", "## 평가항목 분석"],
        "win_strategy": ["## SWOT 분석", "## 차별화 포인트"],
    },
    "performance_plan_kr": {
        "performance_overview": ["## 사업 개요", "## WBS"],
        "quality_risk_plan":    ["## 품질 기준", "## 리스크 매트릭스"],
    },
    "completion_report_kr": {
        "completion_summary": ["## 납품물 목록", "## 성과 측정 결과"],
    },
    "interim_report_kr": {
        "progress_report": ["## 전체 진척 현황", "## 주요 이슈"],
    },
    "task_order_kr": {
        "task_definition": ["## 기능 요구사항", "## 납품물 목록"],
    },
}


# ── Test client helper ────────────────────────────────────────────────────────

def _create_client(tmp_path, monkeypatch) -> TestClient:
    monkeypatch.setenv("DECISIONDOC_PROVIDER", "mock")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DECISIONDOC_ENV", "dev")
    monkeypatch.setenv("DECISIONDOC_MAINTENANCE", "0")
    monkeypatch.delenv("DECISIONDOC_API_KEY",  raising=False)
    monkeypatch.delenv("DECISIONDOC_API_KEYS", raising=False)
    from app.main import create_app
    return TestClient(create_app())


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION A — Registry presence (3 tests)
# ═══════════════════════════════════════════════════════════════════════════════

def test_all_gov_bundles_in_registry():
    """All 6 나라장터 bundles must be present in BUNDLE_REGISTRY."""
    for bid in GOV_BUNDLE_IDS:
        assert bid in BUNDLE_REGISTRY, f"Missing bundle: {bid}"


def test_gov_bundles_are_bundle_spec_instances():
    """Each registered government bundle must be a BundleSpec instance."""
    for bid in GOV_BUNDLE_IDS:
        assert isinstance(BUNDLE_REGISTRY[bid], BundleSpec), f"{bid} is not a BundleSpec"


def test_registry_has_at_least_17_bundles():
    """After adding bid_decision_kr, registry must have ≥ 17 built-in bundles."""
    builtin = {
        "tech_decision", "proposal_kr", "business_plan_kr", "edu_plan_kr",
        "meeting_minutes_kr", "project_report_kr", "contract_kr",
        "presentation_kr", "job_description_kr", "okr_plan_kr", "prd_kr",
        "bid_decision_kr", "rfp_analysis_kr", "performance_plan_kr", "completion_report_kr",
        "interim_report_kr", "task_order_kr",
    }
    registered = set(BUNDLE_REGISTRY.keys())
    assert builtin.issubset(registered), f"Missing: {builtin - registered}"


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION B — Structural validation (5 tests × 5 bundles = 25 tests)
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("bundle_id", GOV_BUNDLE_IDS)
def test_gov_bundle_identity_fields(bundle_id):
    """Bundle must have all required identity fields correctly set."""
    spec = BUNDLE_REGISTRY[bundle_id]
    assert spec.id == bundle_id
    assert spec.name_ko, f"{bundle_id}: name_ko is empty"
    assert spec.name_en, f"{bundle_id}: name_en is empty"
    assert spec.description_ko, f"{bundle_id}: description_ko is empty"
    assert spec.icon, f"{bundle_id}: icon is empty"
    assert spec.prompt_language == "ko", f"{bundle_id}: expected 'ko'"
    assert spec.category == "gov", f"{bundle_id}: expected category='gov'"


@pytest.mark.parametrize("bundle_id", GOV_BUNDLE_IDS)
def test_gov_bundle_doc_count(bundle_id):
    """Bundle must have the expected number of DocumentSpecs."""
    spec = BUNDLE_REGISTRY[bundle_id]
    expected = _DOC_COUNTS[bundle_id]
    assert len(spec.docs) == expected, (
        f"{bundle_id}: expected {expected} docs, got {len(spec.docs)}"
    )
    for doc in spec.docs:
        assert isinstance(doc, DocumentSpec)
        assert doc.key
        assert doc.template_file.startswith(f"{bundle_id}/")


@pytest.mark.parametrize("bundle_id", GOV_BUNDLE_IDS)
def test_gov_bundle_json_schema_valid(bundle_id):
    """json_schema must be well-formed: required keys match properties keys."""
    spec = BUNDLE_REGISTRY[bundle_id]
    schema = spec.json_schema
    assert schema["type"] == "object"
    assert "required" in schema
    assert "properties" in schema
    assert set(schema["required"]) == set(schema["properties"].keys()), (
        f"{bundle_id}: schema required/properties mismatch"
    )
    # Each DocumentSpec schema must also be consistent
    for doc in spec.docs:
        doc_schema = doc.json_schema
        assert "required" in doc_schema
        assert "properties" in doc_schema
        assert set(doc_schema["required"]).issubset(set(doc_schema["properties"].keys())), (
            f"{bundle_id}.{doc.key}: required fields not in properties"
        )


@pytest.mark.parametrize("bundle_id", GOV_BUNDLE_IDS)
def test_gov_bundle_lint_and_validator_headings(bundle_id):
    """Both lint_headings and validator_headings must be non-empty for all docs."""
    spec = BUNDLE_REGISTRY[bundle_id]
    for doc in spec.docs:
        assert doc.lint_headings, f"{bundle_id}.{doc.key}: lint_headings is empty"
        assert doc.validator_headings, (
            f"{bundle_id}.{doc.key}: validator_headings is empty"
        )
        # lint_headings[0] should be an H1 title marker
        assert doc.lint_headings[0].startswith("# "), (
            f"{bundle_id}.{doc.key}: first lint_heading should be H1, got {doc.lint_headings[0]!r}"
        )
        # validator_headings must all be H2
        for heading in doc.validator_headings:
            assert heading.startswith("## "), (
                f"{bundle_id}.{doc.key}: validator heading not H2: {heading!r}"
            )


@pytest.mark.parametrize("bundle_id", GOV_BUNDLE_IDS)
def test_gov_bundle_critical_headings_subset_of_validator(bundle_id):
    """critical_non_empty_headings must be a subset of validator_headings for each doc."""
    spec = BUNDLE_REGISTRY[bundle_id]
    for doc in spec.docs:
        critical = set(doc.critical_non_empty_headings)
        validator = set(doc.validator_headings)
        assert critical.issubset(validator), (
            f"{bundle_id}.{doc.key}: critical headings not in validator headings.\n"
            f"  Extra: {critical - validator}"
        )
        # Must have at least 2 critical headings per doc
        assert len(doc.critical_non_empty_headings) >= 1, (
            f"{bundle_id}.{doc.key}: should have ≥1 critical headings"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION C — Exact critical_non_empty_headings values (5 tests)
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("bundle_id", GOV_BUNDLE_IDS)
def test_gov_bundle_exact_critical_headings(bundle_id):
    """critical_non_empty_headings must match the expected values exactly."""
    spec = BUNDLE_REGISTRY[bundle_id]
    expected_by_key = _CRITICAL_HEADINGS[bundle_id]
    for doc in spec.docs:
        if doc.key in expected_by_key:
            assert doc.critical_non_empty_headings == expected_by_key[doc.key], (
                f"{bundle_id}.{doc.key}: critical headings mismatch\n"
                f"  Expected: {expected_by_key[doc.key]}\n"
                f"  Got:      {doc.critical_non_empty_headings}"
            )


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION D — Prompt hint structure (5 tests)
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("bundle_id", GOV_BUNDLE_IDS)
def test_gov_bundle_prompt_hint_structure(bundle_id):
    """prompt_hint must follow the 3-part structure: role → checks → rules."""
    spec = BUNDLE_REGISTRY[bundle_id]
    hint = spec.prompt_hint
    assert hint, f"{bundle_id}: prompt_hint is empty"
    # Part A — role persona
    assert "당신은" in hint, f"{bundle_id}: missing role persona '당신은'"
    # Part B — internal reasoning checks
    assert "(1)" in hint and "(2)" in hint, (
        f"{bundle_id}: missing internal reasoning checks (1)/( 2)"
    )
    # Part C — must end with Korean language instruction
    assert "한국어로 작성하세요" in hint, (
        f"{bundle_id}: missing Korean language instruction"
    )


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION E — Few-shot example content (5 tests)
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("bundle_id", GOV_BUNDLE_IDS)
def test_gov_bundle_few_shot_example(bundle_id):
    """few_shot_example must be non-empty and contain at least one H2 heading."""
    spec = BUNDLE_REGISTRY[bundle_id]
    assert spec.few_shot_example, f"{bundle_id}: few_shot_example is empty"
    assert "## " in spec.few_shot_example, (
        f"{bundle_id}: few_shot_example has no H2 headings"
    )
    # Should contain real Korean government content markers
    assert len(spec.few_shot_example) > 100, (
        f"{bundle_id}: few_shot_example is too short (<100 chars)"
    )


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION F — stabilizer_defaults completeness (5 tests)
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("bundle_id", GOV_BUNDLE_IDS)
def test_gov_bundle_stabilizer_defaults_complete(bundle_id):
    """stabilizer_defaults must cover all required schema keys for each doc."""
    spec = BUNDLE_REGISTRY[bundle_id]
    for doc in spec.docs:
        required_keys = set(doc.json_schema.get("required", []))
        defaults_keys = set(doc.stabilizer_defaults.keys())
        assert required_keys == defaults_keys, (
            f"{bundle_id}.{doc.key}: stabilizer_defaults keys mismatch.\n"
            f"  Required: {required_keys}\n"
            f"  Defaults: {defaults_keys}"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION G — Integration tests: mock generation (5 tests)
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("bundle_id", GOV_BUNDLE_IDS)
def test_gov_bundle_generate_returns_200(tmp_path, monkeypatch, bundle_id):
    """POST /generate must return 200 for each government bundle."""
    client = _create_client(tmp_path, monkeypatch)
    res = client.post("/generate", json={
        "title":    "AI 민원처리 자동화 사업",
        "goal":     "민원 처리 시간을 14일에서 3일로 단축한다.",
        "context":  "행정안전부 발주, 예산 12억원, 기간 9개월",
        "bundle_type": bundle_id,
    })
    assert res.status_code == 200, (
        f"{bundle_id}: expected 200, got {res.status_code}. Body: {res.text[:300]}"
    )


@pytest.mark.parametrize("bundle_id", GOV_BUNDLE_IDS)
def test_gov_bundle_generate_docs_structure(tmp_path, monkeypatch, bundle_id):
    """Generated response must contain docs list with correct doc_type values."""
    client = _create_client(tmp_path, monkeypatch)
    res = client.post("/generate", json={
        "title":    "AI 민원처리 자동화 사업",
        "goal":     "민원 처리 시간을 14일에서 3일로 단축한다.",
        "bundle_type": bundle_id,
    })
    assert res.status_code == 200
    data = res.json()
    assert "docs" in data, f"{bundle_id}: response missing 'docs'"
    assert len(data["docs"]) > 0, f"{bundle_id}: docs list is empty"

    spec = BUNDLE_REGISTRY[bundle_id]
    returned_types = {d["doc_type"] for d in data["docs"]}
    expected_types = set(spec.doc_keys)
    assert returned_types == expected_types, (
        f"{bundle_id}: doc_type mismatch.\n"
        f"  Expected: {expected_types}\n"
        f"  Got:      {returned_types}"
    )


@pytest.mark.parametrize("bundle_id", GOV_BUNDLE_IDS)
def test_gov_bundle_generate_markdown_non_empty(tmp_path, monkeypatch, bundle_id):
    """Each generated doc must have non-empty markdown."""
    client = _create_client(tmp_path, monkeypatch)
    res = client.post("/generate", json={
        "title":    "AI 민원처리 자동화 사업",
        "goal":     "민원 처리 시간을 단축한다.",
        "bundle_type": bundle_id,
    })
    assert res.status_code == 200
    for doc in res.json()["docs"]:
        assert doc.get("markdown"), (
            f"{bundle_id}.{doc['doc_type']}: markdown is empty"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION H — ui_metadata completeness (5 tests)
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("bundle_id", GOV_BUNDLE_IDS)
def test_gov_bundle_ui_metadata(bundle_id):
    """ui_metadata() must return all required API fields."""
    spec = BUNDLE_REGISTRY[bundle_id]
    meta = spec.ui_metadata()
    assert meta["id"] == bundle_id
    assert meta["name_ko"]
    assert meta["name_en"]
    assert meta["description_ko"]
    assert meta["icon"]
    assert meta["category"] == "gov"
    assert meta["doc_count"] == _DOC_COUNTS[bundle_id]
    assert meta["doc_keys"] == spec.doc_keys
    assert meta["prompt_language"] == "ko"


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION I — GET /bundles includes government bundles (1 integration test)
# ═══════════════════════════════════════════════════════════════════════════════

def test_get_bundles_includes_gov_bundles(tmp_path, monkeypatch):
    """GET /bundles API must return all 5 government procurement bundles."""
    client = _create_client(tmp_path, monkeypatch)
    res = client.get("/bundles")
    assert res.status_code == 200
    bundle_ids = {b["id"] for b in res.json()}
    for bid in GOV_BUNDLE_IDS:
        assert bid in bundle_ids, f"GET /bundles missing: {bid}"


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION J — stability_checklist includes bundle doc keys (5 tests)
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("bundle_id", GOV_BUNDLE_IDS)
def test_gov_bundle_stability_checklist(bundle_id):
    """stability_checklist must mention all doc keys and Korean language rule."""
    spec = BUNDLE_REGISTRY[bundle_id]
    checklist = spec.stability_checklist
    for key in spec.doc_keys:
        assert key in checklist, (
            f"{bundle_id}: doc key '{key}' not in stability_checklist"
        )
    assert "한국어" in checklist, (
        f"{bundle_id}: Korean language instruction missing from checklist"
    )
