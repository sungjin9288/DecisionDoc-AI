from copy import deepcopy
import json
from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from app.providers.base import ProviderError
from app.providers.factory import get_provider
from app.providers.mock_provider import MockProvider
from app.services.auth_service import create_access_token
from app.services.generation_service import _apply_finished_doc_quality_guard
from app.services.validator import validate_docs


def _create_client(tmp_path, monkeypatch, provider="mock"):
    monkeypatch.setenv("DECISIONDOC_PROVIDER", provider)
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DECISIONDOC_ENV", "dev")
    monkeypatch.setenv("DECISIONDOC_MAINTENANCE", "0")
    monkeypatch.delenv("DECISIONDOC_API_KEY", raising=False)
    monkeypatch.delenv("DECISIONDOC_API_KEYS", raising=False)

    from app.main import create_app

    app = create_app()
    return TestClient(app)


def _auth_headers(user_id: str = "testuser") -> dict[str, str]:
    token = create_access_token(
        user_id=user_id,
        tenant_id="system",
        role="admin",
        username=user_id,
    )
    return {"Authorization": f"Bearer {token}"}


def test_generate_minimal_payload_returns_all_docs(tmp_path, monkeypatch):
    client = _create_client(tmp_path, monkeypatch)

    response = client.post(
        "/generate",
        json={
            "title": "DecisionDoc MVP",
            "goal": "Generate baseline decision docs",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert "request_id" in body
    assert "bundle_id" in body
    assert body["provider"] == "mock"
    assert body["schema_version"] == "v1"
    assert len(body["docs"]) == 4

    for doc in body["docs"]:
        assert isinstance(doc["markdown"], str)
        assert doc["markdown"].strip()

    saved = Path(tmp_path) / f"{body['bundle_id']}.json"
    assert saved.exists()
    saved_body = json.loads(saved.read_text(encoding="utf-8"))
    assert {"adr", "onepager", "eval_plan", "ops_checklist"} <= set(saved_body.keys())


def test_generate_with_mock_provider_ok(tmp_path, monkeypatch):
    client = _create_client(tmp_path, monkeypatch, provider="mock")
    response = client.post("/generate", json={"title": "mock ok", "goal": "smoke"})
    assert response.status_code == 200
    body = response.json()
    assert body["provider"] == "mock"
    assert len(body["docs"]) == 4
    validate_docs(body["docs"])


def test_generate_accepts_optional_style_profile_id(tmp_path, monkeypatch):
    client = _create_client(tmp_path, monkeypatch, provider="mock")
    response = client.post(
        "/generate",
        json={
            "title": "style profile payload",
            "goal": "web ui compatibility",
            "style_profile_id": "default-consulting",
        },
    )
    assert response.status_code == 200
    assert response.json()["provider"] == "mock"


def test_generate_history_detail_preserves_slide_outline_metadata(tmp_path, monkeypatch):
    client = _create_client(tmp_path, monkeypatch, provider="mock")
    bundle_id = "history-slide-outline-001"

    register = client.post(
        "/auth/register",
        json={
            "username": "historyadmin",
            "display_name": "History Admin",
            "email": "history@example.com",
            "password": "HistoryPass1!",
        },
    )
    assert register.status_code == 200
    auth_headers = {"Authorization": f"Bearer {register.json()['access_token']}"}

    def _fake_generate_documents(req, *, request_id: str, tenant_id: str):  # noqa: ANN001
        assert req.bundle_type == "presentation_kr"
        assert tenant_id == "system"
        return {
            "docs": [
                {
                    "doc_type": "slide_structure",
                    "markdown": "# 발표 구조\n\n본문",
                },
                {
                    "doc_type": "slide_script",
                    "markdown": "# 스크립트\n\n본문",
                },
            ],
            "raw_bundle": {
                "slide_structure": {
                    "total_slides": 2,
                    "slide_outline": [
                        {
                            "title": "오프닝 질문",
                            "core_message": "청중의 문제 인식을 연다.",
                            "visual_type": "현장 사진",
                        },
                        {
                            "title": "핵심 제안",
                            "core_message": "제안의 차별성을 요약한다.",
                            "visual_type": "타임라인",
                        },
                    ],
                }
            },
            "metadata": {
                "bundle_id": bundle_id,
                "provider": "mock",
                "schema_version": "v1",
                "cache_hit": False,
                "bundle_type": "presentation_kr",
                "doc_count": 2,
                "applied_references": [],
                "timings_ms": {},
            },
        }

    client.app.state.service.generate_documents = _fake_generate_documents

    response = client.post(
        "/generate",
        json={
            "title": "히스토리 metadata 보존 검증",
            "goal": "history detail에 slide outline metadata가 남아야 한다.",
            "bundle_type": "presentation_kr",
        },
        headers=auth_headers,
    )

    assert response.status_code == 200
    body = response.json()
    entry_id = body["request_id"]
    assert body["bundle_id"] == bundle_id
    assert body["docs"][0]["total_slides"] == 2
    assert body["docs"][0]["slide_outline"][0]["title"] == "오프닝 질문"

    detail = client.get(f"/history/{entry_id}", headers=auth_headers)
    assert detail.status_code == 200
    detail_body = detail.json()
    assert detail_body["docs"][0]["total_slides"] == 2
    assert detail_body["docs"][0]["slide_outline"][0]["title"] == "오프닝 질문"
    assert detail_body["docs"][0]["slide_outline"][1]["visual_type"] == "타임라인"


def test_missing_required_fields_return_422(tmp_path, monkeypatch):
    client = _create_client(tmp_path, monkeypatch)

    no_title = client.post("/generate", json={"goal": "x"})
    no_goal = client.post("/generate", json={"title": "x"})

    assert no_title.status_code == 422
    assert no_goal.status_code == 422


def test_empty_title_or_goal_returns_422(tmp_path, monkeypatch):
    client = _create_client(tmp_path, monkeypatch)

    empty_title = client.post("/generate", json={"title": "", "goal": "valid goal"})
    empty_goal = client.post("/generate", json={"title": "valid title", "goal": ""})

    assert empty_title.status_code == 422
    assert empty_goal.status_code == 422


def test_invalid_doc_type_returns_422(tmp_path, monkeypatch):
    client = _create_client(tmp_path, monkeypatch)
    response = client.post(
        "/generate",
        json={"title": "x", "goal": "y", "doc_types": ["bad_type"]},
    )
    assert response.status_code == 422


def test_empty_doc_types_returns_422(tmp_path, monkeypatch):
    client = _create_client(tmp_path, monkeypatch)
    response = client.post(
        "/generate",
        json={"title": "x", "goal": "y", "doc_types": []},
    )
    assert response.status_code == 422


def test_extremely_long_title_is_accepted(tmp_path, monkeypatch):
    client = _create_client(tmp_path, monkeypatch)
    long_title = "A" * 5000
    response = client.post(
        "/generate",
        json={"title": long_title, "goal": "validate long title behavior"},
    )
    assert response.status_code == 200
    assert response.json()["title"] == long_title


def test_doc_validation_failure_returns_stable_500_payload(tmp_path, monkeypatch):
    import app.main as main_module
    from app.providers.mock_provider import MockProvider

    class BrokenMockProvider(MockProvider):
        def generate_bundle(self, requirements, *, schema_version, request_id, bundle_spec=None, feedback_hints=""):  # noqa: ANN001
            bundle = super().generate_bundle(requirements, schema_version=schema_version, request_id=request_id, bundle_spec=bundle_spec, feedback_hints=feedback_hints)
            bundle["adr"]["options"] = ["only one option"]
            return bundle

    monkeypatch.setattr(main_module, "get_provider", lambda: BrokenMockProvider())
    client = _create_client(tmp_path, monkeypatch)

    response = client.post("/generate", json={"title": "x", "goal": "y"})
    assert response.status_code == 500
    body = response.json()
    assert body["code"] == "DOC_VALIDATION_FAILED"
    assert body["message"] == "Document validation failed."
    assert isinstance(body["request_id"], str)


def test_provider_factory_default_is_mock(monkeypatch):
    monkeypatch.delenv("DECISIONDOC_PROVIDER", raising=False)
    provider = get_provider()
    assert provider.name == "mock"


def test_bundle_schema_required_keys_exist_for_mock_provider():
    provider = MockProvider()
    bundle = provider.generate_bundle(
        {"title": "x", "goal": "y", "doc_types": ["adr", "onepager", "eval_plan", "ops_checklist"]},
        schema_version="v1",
        request_id="req-1",
    )
    assert set(bundle.keys()) == {"adr", "onepager", "eval_plan", "ops_checklist"}


def test_provider_missing_key_raises_at_startup(tmp_path, monkeypatch):
    # Startup fail-fast: missing API key is now caught during create_app(), not at
    # first request. This guards against silent misconfiguration before serving traffic.
    # Patch load_dotenv to prevent the real .env file from overwriting monkeypatched vars.
    monkeypatch.setattr("app.main.load_dotenv", lambda *a, **kw: None)
    monkeypatch.setenv("DECISIONDOC_PROVIDER", "openai")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DECISIONDOC_ENV", "dev")
    monkeypatch.setenv("DECISIONDOC_MAINTENANCE", "0")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    from app.main import create_app

    with pytest.raises(RuntimeError, match="OPENAI_API_KEY is required"):
        create_app()


def test_claude_provider_missing_key_raises_at_startup(tmp_path, monkeypatch):
    monkeypatch.setattr("app.main.load_dotenv", lambda *a, **kw: None)
    monkeypatch.setenv("DECISIONDOC_PROVIDER", "claude")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DECISIONDOC_ENV", "dev")
    monkeypatch.setenv("DECISIONDOC_MAINTENANCE", "0")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    from app.main import create_app

    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY is required"):
        create_app()


def test_visual_provider_missing_key_raises_at_startup(tmp_path, monkeypatch):
    monkeypatch.setattr("app.main.load_dotenv", lambda *a, **kw: None)
    monkeypatch.setenv("DECISIONDOC_PROVIDER", "mock")
    monkeypatch.setenv("DECISIONDOC_PROVIDER_VISUAL", "claude")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DECISIONDOC_ENV", "dev")
    monkeypatch.setenv("DECISIONDOC_MAINTENANCE", "0")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    from app.main import create_app

    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY is required"):
        create_app()


def test_bundle_schema_validation_missing_required_key_returns_provider_failed(tmp_path, monkeypatch):
    import app.main as main_module
    from app.providers.mock_provider import MockProvider

    class InvalidTypedProvider(MockProvider):
        def generate_bundle(self, requirements, *, schema_version, request_id, bundle_spec=None, feedback_hints=""):  # noqa: ANN001
            raise RuntimeError("provider internal error")

    monkeypatch.setattr(main_module, "get_provider", lambda: InvalidTypedProvider())
    client = _create_client(tmp_path, monkeypatch)
    response = client.post("/generate", json={"title": "x", "goal": "y"})
    assert response.status_code == 500
    body = response.json()
    assert body["code"] == "PROVIDER_FAILED"
    assert body["message"] == "Provider request failed."
    assert isinstance(body["request_id"], str)


def test_provider_rate_limit_returns_503_with_retry_guidance(tmp_path, monkeypatch):
    import app.main as main_module

    class FakeRateLimitError(Exception):
        status_code = 429

        def __init__(self) -> None:
            super().__init__("429 Too Many Requests")
            self.response = type(
                "FakeResponse",
                (),
                {"status_code": 429, "headers": {"retry-after": "12"}},
            )()

    class RateLimitedProvider(MockProvider):
        def generate_bundle(self, requirements, *, schema_version, request_id, bundle_spec=None, feedback_hints=""):  # noqa: ANN001
            try:
                raise FakeRateLimitError()
            except Exception as exc:
                raise ProviderError("Provider request failed.") from exc

    monkeypatch.setattr(main_module, "get_provider", lambda: RateLimitedProvider())
    client = _create_client(tmp_path, monkeypatch)

    response = client.post("/generate", json={"title": "x", "goal": "y"})
    assert response.status_code == 503
    body = response.json()
    assert body["code"] == "PROVIDER_FAILED"
    assert body["message"] == "AI provider is temporarily rate limited. 잠시 후 다시 시도하세요."
    assert body["errors"] == ["retry_after_seconds=12"]


def test_provider_quota_exhausted_returns_503_with_quota_guidance(tmp_path, monkeypatch):
    import app.main as main_module

    class FakeQuotaError(Exception):
        status_code = 429

        def __init__(self) -> None:
            super().__init__("insufficient_quota")
            self.body = {"error": {"code": "insufficient_quota", "message": "quota exhausted"}}
            self.response = type(
                "FakeResponse",
                (),
                {"status_code": 429, "headers": {}},
            )()

    class QuotaLimitedProvider(MockProvider):
        def generate_bundle(self, requirements, *, schema_version, request_id, bundle_spec=None, feedback_hints=""):  # noqa: ANN001
            try:
                raise FakeQuotaError()
            except Exception as exc:
                raise ProviderError("Provider request failed.") from exc

    monkeypatch.setattr(main_module, "get_provider", lambda: QuotaLimitedProvider())
    client = _create_client(tmp_path, monkeypatch)

    response = client.post("/generate", json={"title": "x", "goal": "y"})
    assert response.status_code == 503
    body = response.json()
    assert body["code"] == "PROVIDER_FAILED"
    assert body["message"] == "AI provider quota is exhausted. 운영 키 또는 과금 한도를 확인하세요."
    assert body["errors"] == ["provider_error_code=insufficient_quota"]


def _proposal_bundle_with_hallucinated_attachment_fields() -> dict:
    return {
        "business_understanding": {
            "executive_summary": "원문에 없는 20% 사고 감소와 3억원 예산 절감을 약속합니다.",
            "project_background": "원문에 없는 2027년 완료 계획과 정량 KPI를 제시합니다.",
            "current_issues": ["사고율 20% 증가", "AWS 도입 필요"],
            "project_objectives": ["사고율 30% 절감 | 3억원 예산 확보 | ROI 180%"],
            "evaluation_alignment": ["정량 KPI 중심 설명"],
            "scope_summary": "2027년 1분기까지 전면 구축합니다.",
            "total_slides": 7,
            "slide_outline": [{"page": 1, "title": "기존 슬라이드"}],
        },
        "tech_proposal": {
            "technical_summary": "AWS Lambda와 Vertex AI를 사용해 즉시 구축합니다.",
            "tech_stack": ["AWS Lambda | 서버리스", "Vertex AI | 분석"],
            "architecture_overview": "2027년까지 확장 가능한 구조입니다.",
            "ai_approach": "Claude Opus와 Gemini를 혼합 적용합니다.",
            "implementation_principles": ["원문 없는 구현 원칙"],
            "security_measures": ["원문 없는 보안 조치"],
            "differentiation": ["원문 없는 차별화 포인트"],
            "total_slides": 8,
            "slide_outline": [{"page": 1, "title": "기존 기술 슬라이드"}],
        },
        "execution_plan": {
            "delivery_summary": "12개월 내 3억원 예산으로 완료합니다.",
            "team_structure": ["PM 4명 | 12개월 투입"],
            "milestones": ["2027-01 완료"],
            "methodology": "애자일 12스프린트 방식",
            "governance_plan": "월간 운영위원회",
            "risk_management": ["ROI 180% 미달 리스크"],
            "deliverables": ["최종 보고서"],
            "total_slides": 9,
            "slide_outline": [{"page": 1, "title": "기존 수행 슬라이드"}],
        },
        "expected_impact": {
            "impact_summary": "ROI 180%와 연간 3억원 절감을 달성합니다.",
            "quantitative_effects": ["사고율 20% 감소"],
            "qualitative_effects": ["원문 없는 기대효과"],
            "social_value": "원문 없는 사회적 가치",
            "kpi_commitments": ["KPI 달성률 95%"],
            "roi_estimate": "3년 ROI 180%",
            "monitoring_plan": ["월별 KPI 점검"],
            "total_slides": 6,
            "slide_outline": [{"page": 1, "title": "기존 효과 슬라이드"}],
        },
    }


def test_proposal_quality_guard_rewrites_sparse_attachment_hallucinations():
    sparse_context = (
        "=== RFP 원문 (참고용) ===\n"
        "[첨부파일: uat-attachment.txt]\n"
        "국토교통 제안의 핵심 요구사항은 교차로 안전 강화와 장애인 보호 강화이다.\n"
        "=== RFP 원문 끝 ==="
    )

    guarded = _apply_finished_doc_quality_guard(
        deepcopy(_proposal_bundle_with_hallucinated_attachment_fields()),
        bundle_type="proposal_kr",
        title="국토교통 교차로 안전 제안",
        goal="국토교통 분야 교차로 안전 사업 제안서 초안을 작성한다.",
        context_text=sparse_context,
    )

    business = guarded["business_understanding"]
    tech = guarded["tech_proposal"]
    execution = guarded["execution_plan"]
    impact = guarded["expected_impact"]

    assert business["current_issues"] == [
        "교차로 안전 강화 요구에 비해 현장 대응 체계가 분산되어 있음",
        "장애인 보호 관점의 운영 기준과 현장 실행 절차가 일관되지 않음",
        "안전 관련 현황을 통합적으로 확인하고 점검할 수 있는 운영 체계가 부족함",
    ]
    assert tech["tech_stack"][0].startswith("데이터 수집·연계 |")
    assert tech["technical_summary"]
    assert "AWS Lambda" not in tech["technical_summary"]
    assert "초안을 작성한다." not in tech["ai_approach"]
    assert tech["ai_approach"].startswith("AI 기능은 현장 위험 징후를 분석하고 대응 우선순위를 정리해")
    assert execution["milestones"][0].startswith("착수 및 요구사항 정리 |")
    assert impact["roi_estimate"] == "투자 대비 효과는 시범 운영 이후 실제 운영 데이터와 검수 결과를 바탕으로 산정합니다."
    assert "180%" not in impact["impact_summary"]
    assert impact["monitoring_plan"][0].startswith("안전 관련 운영 로그 |")
    assert business["total_slides"] == 2
    assert tech["total_slides"] == 2
    assert execution["total_slides"] == 2
    assert impact["total_slides"] == 2


def test_proposal_quality_guard_keeps_non_sparse_attachment_fields():
    dense_context = (
        "=== RFP 원문 (참고용) ===\n"
        "[첨부파일: uat-attachment.txt]\n"
        "국토교통 제안의 핵심 요구사항은 교차로 안전 강화와 장애인 보호 강화이며, "
        "2026년 시범 운영과 2027년 본사업 전환, 12개월 단계 운영 검토, 현장 점검 지표 정리를 포함합니다.\n"
        "=== RFP 원문 끝 ==="
    )

    guarded = _apply_finished_doc_quality_guard(
        deepcopy(_proposal_bundle_with_hallucinated_attachment_fields()),
        bundle_type="proposal_kr",
        title="국토교통 교차로 안전 제안",
        goal="국토교통 분야 교차로 안전 사업 제안서 초안을 작성한다.",
        context_text=dense_context,
    )

    business = guarded["business_understanding"]
    tech = guarded["tech_proposal"]
    impact = guarded["expected_impact"]

    assert business["current_issues"] == ["사고율 20% 증가", "AWS 도입 필요"]
    assert tech["tech_stack"] == ["AWS Lambda | 서버리스", "Vertex AI | 분석"]
    assert impact["roi_estimate"] == "3년 ROI 180%"
    assert business["total_slides"] == 7
    assert tech["total_slides"] == 8


def test_proposal_quality_guard_rewrites_sparse_non_attachment_hallucinations():
    sparse_context = "첨부 없이도 교차로 안전 강화와 교통약자 보호를 위한 기본 제안 구조를 확인한다."

    guarded = _apply_finished_doc_quality_guard(
        deepcopy(_proposal_bundle_with_hallucinated_attachment_fields()),
        bundle_type="proposal_kr",
        title="국토교통 교차로 안전 제안",
        goal="국토교통 분야 교차로 안전 사업 제안서 초안을 작성한다.",
        context_text=sparse_context,
    )

    business = guarded["business_understanding"]
    execution = guarded["execution_plan"]
    impact = guarded["expected_impact"]

    assert "20%" not in business["executive_summary"]
    assert "2027" not in business["project_background"]
    assert business["project_objectives"][0] == "현장 위험 징후를 조기에 식별하고 대응 기준을 정리한다."
    assert "2027" not in execution["delivery_summary"]
    assert execution["milestones"][0].startswith("착수 및 요구사항 정리 |")
    assert "180%" not in impact["impact_summary"]
    assert impact["roi_estimate"] == "투자 대비 효과는 시범 운영 이후 실제 운영 데이터와 검수 결과를 바탕으로 산정합니다."
    assert impact["monitoring_plan"][0].startswith("안전 관련 운영 로그 |")


def test_proposal_quality_guard_keeps_dense_non_attachment_fields():
    dense_context = (
        "2026년 시범 운영과 2027년 확대 적용 검토를 포함해 일정과 검증 지표를 함께 제시하는 "
        "교차로 안전 강화 사업 제안서 초안을 작성한다."
    )

    guarded = _apply_finished_doc_quality_guard(
        deepcopy(_proposal_bundle_with_hallucinated_attachment_fields()),
        bundle_type="proposal_kr",
        title="국토교통 교차로 안전 제안",
        goal="국토교통 분야 교차로 안전 사업 제안서 초안을 작성한다.",
        context_text=dense_context,
    )

    business = guarded["business_understanding"]
    impact = guarded["expected_impact"]

    assert business["project_objectives"] == ["사고율 30% 절감 | 3억원 예산 확보 | ROI 180%"]
    assert impact["roi_estimate"] == "3년 ROI 180%"


@pytest.mark.parametrize("fixture_path", sorted(Path(__file__).parent.joinpath("fixtures").glob("*.json")))
def test_regression_fixtures_generate_valid_docs(tmp_path, monkeypatch, fixture_path):
    client = _create_client(tmp_path, monkeypatch)
    payload = json.loads(fixture_path.read_text(encoding="utf-8"))
    response = client.post("/generate", json=payload)

    assert response.status_code == 200, fixture_path.name
    body = response.json()
    expected_len = len(payload.get("doc_types", ["adr", "onepager", "eval_plan", "ops_checklist"]))
    assert len(body["docs"]) == expected_len

    validate_docs(body["docs"])


def test_corrupt_cache_file_is_removed_and_regenerated(tmp_path, monkeypatch):
    """If the cache file is corrupt, it should be deleted and re-generated on the next call."""
    monkeypatch.setenv("DECISIONDOC_CACHE_ENABLED", "1")
    client = _create_client(tmp_path, monkeypatch)

    # First call: populate cache
    response1 = client.post("/generate", json={"title": "cache test", "goal": "test"})
    assert response1.status_code == 200

    # Find the cache file and corrupt it
    cache_dir = tmp_path / "cache"
    cache_files = list(cache_dir.glob("*.json"))
    assert len(cache_files) >= 1
    cache_file = cache_files[0]
    cache_file.write_text("{corrupted-json-content", encoding="utf-8")

    # Second call: should detect corruption, remove file, and regenerate
    response2 = client.post("/generate", json={"title": "cache test", "goal": "test"})
    assert response2.status_code == 200
    assert response2.json()["provider"] == "mock"

    # The corrupt file should have been replaced with a valid cache
    new_content = cache_file.read_text(encoding="utf-8")
    parsed = json.loads(new_content)
    assert isinstance(parsed, dict)
    assert "adr" in parsed


def test_generate_export_returns_files_and_writes_markdown(tmp_path, monkeypatch):
    client = _create_client(tmp_path, monkeypatch)
    response = client.post(
        "/generate/export",
        json={"title": "Export Smoke", "goal": "Verify export endpoint"},
    )

    assert response.status_code == 200
    body = response.json()
    assert "request_id" in body
    assert "bundle_id" in body
    assert "export_dir" in body
    assert len(body["files"]) == 4

    export_dir = Path(body["export_dir"])
    assert export_dir.exists()
    assert export_dir.is_dir()

    for item in body["files"]:
        md_path = Path(item["path"])
        assert md_path.exists()
        assert md_path.suffix == ".md"
        assert md_path.read_text(encoding="utf-8").strip()


def test_generate_injects_ranked_knowledge_context(tmp_path, monkeypatch):
    import app.main as main_module
    from app.providers.mock_provider import MockProvider
    from app.storage.knowledge_store import KnowledgeStore

    captured: dict[str, object] = {}

    class InspectingMockProvider(MockProvider):
        def generate_bundle(self, requirements, *, schema_version, request_id, bundle_spec=None, feedback_hints=""):  # noqa: ANN001
            captured["requirements"] = dict(requirements)
            return super().generate_bundle(
                requirements,
                schema_version=schema_version,
                request_id=request_id,
                bundle_spec=bundle_spec,
                feedback_hints=feedback_hints,
            )

    monkeypatch.setattr(main_module, "get_provider", lambda: InspectingMockProvider())
    client = _create_client(tmp_path, monkeypatch)

    store = KnowledgeStore("proj-knowledge", data_dir=str(tmp_path))
    store.add_document(
        "generic-guide.txt",
        "일반 참고문서 내용",
        learning_mode="reference",
        quality_tier="working",
    )
    store.add_document(
        "winning-proposal.docx",
        "파주시 모빌리티 제안 승인본 구조",
        learning_mode="approved_output",
        quality_tier="gold",
        applicable_bundles=["proposal_kr"],
        source_organization="파주시",
        reference_year=2025,
        success_state="approved",
        notes="제안서 구조와 표 구성이 우수함",
    )

    response = client.post(
        "/generate",
        json={
            "title": "파주시 모빌리티 제안",
            "goal": "승인 가능한 제안서 작성",
            "bundle_type": "proposal_kr",
            "project_id": "proj-knowledge",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert "applied_references" in body
    assert len(body["applied_references"]) >= 1
    top_ref = body["applied_references"][0]
    assert top_ref["filename"] == "winning-proposal.docx"
    assert top_ref["selection_reason"]
    assert top_ref["bundle_match"] is True
    assert isinstance(top_ref["score_breakdown"], list)
    injected = str(captured["requirements"])
    assert "_knowledge_context" in injected
    assert "winning-proposal.docx" in injected
    assert "우선 적용 문서: proposal_kr" in injected
    assert "품질 등급: gold" in injected


def test_generate_succeeds_when_eval_executor_is_unavailable(tmp_path, monkeypatch):
    client = _create_client(tmp_path, monkeypatch)

    def _raise_executor_shutdown(*args, **kwargs):  # noqa: ANN001, ARG001
        raise RuntimeError("cannot schedule new futures after shutdown")

    monkeypatch.setattr("app.services.generation_service._eval_executor.submit", _raise_executor_shutdown)

    response = client.post(
        "/generate",
        json={"title": "executor shutdown", "goal": "skip background eval safely"},
    )

    assert response.status_code == 200
    assert response.json()["provider"] == "mock"


def test_generate_export_validation_failure_returns_500_and_no_export_dir(tmp_path, monkeypatch):
    import app.main as main_module
    from app.providers.mock_provider import MockProvider

    class BrokenMockProvider(MockProvider):
        def generate_bundle(self, requirements, *, schema_version, request_id, bundle_spec=None, feedback_hints=""):  # noqa: ANN001
            bundle = super().generate_bundle(requirements, schema_version=schema_version, request_id=request_id, bundle_spec=bundle_spec, feedback_hints=feedback_hints)
            bundle["adr"]["options"] = ["only one option"]
            return bundle

    monkeypatch.setattr(main_module, "get_provider", lambda: BrokenMockProvider())
    client = _create_client(tmp_path, monkeypatch)

    response = client.post("/generate/export", json={"title": "x", "goal": "y"})
    assert response.status_code == 500
    body = response.json()
    assert body["code"] == "DOC_VALIDATION_FAILED"
    assert body["message"] == "Document validation failed."
    assert isinstance(body["request_id"], str)

    assert not any(Path(tmp_path).glob("*/*.md"))
