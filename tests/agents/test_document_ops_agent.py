import json

import pytest

from app.agents.document_ops_agent import DocumentOpsAgent
from app.agents.schemas import DocumentOpsRequest
from app.providers.base import Provider, ProviderError
from app.providers.mock_provider import MockProvider
from app.storage.trajectory_store import TrajectoryStore


class RawTextProvider(Provider):
    name = "raw-text"

    def generate_raw(self, prompt: str, *, request_id: str, max_output_tokens: int | None = None) -> str:
        return "not-json"

    def generate_bundle(self, *args, **kwargs):
        return {}


class FailingProvider(Provider):
    name = "failing"

    def generate_raw(self, prompt: str, *, request_id: str, max_output_tokens: int | None = None) -> str:
        raise ProviderError("provider unavailable")

    def generate_bundle(self, *args, **kwargs):
        return {}


class StaticJsonProvider(Provider):
    name = "static-json"

    def __init__(self, raw: str) -> None:
        self.raw = raw

    def generate_raw(self, prompt: str, *, request_id: str, max_output_tokens: int | None = None) -> str:
        return self.raw

    def generate_bundle(self, *args, **kwargs):
        return {}


class NamedRawProvider(RawTextProvider):
    def __init__(self, name: str) -> None:
        self.name = name


def test_document_ops_agent_runs_policy_planning_with_mock_provider() -> None:
    agent = DocumentOpsAgent(provider=MockProvider())
    result = agent.run(
        DocumentOpsRequest(
            task_type="policy_planning_brief",
            requirements={
                "title": "보행자 안전 정책 기획 사업",
                "goal": "반복 위험을 운영 가능한 공공 안전서비스로 전환",
            },
            source_references=[{"id": "research-report", "title": "보행자 사고 분석"}],
            capture_trajectory=True,
        ),
        request_id="agent-test-001",
        tenant_id="system",
    )

    assert result.provider_name == "mock"
    assert result.skill_name == "policy-planning"
    assert result.plan
    assert "보행자 안전 정책 기획 사업" in result.draft
    assert result.qa["hard_gate_pass"] is True
    assert result.trajectory is not None
    assert result.trajectory["skill"]["name"] == "policy-planning"


def test_document_ops_agent_records_provider_attempt_before_propagating_failure() -> None:
    provider = FailingProvider()
    recorded: list[str] = []
    agent = DocumentOpsAgent(provider=provider)

    with pytest.raises(ProviderError, match="provider unavailable"):
        agent.run(
            DocumentOpsRequest(
                task_type="decision_brief",
                requirements={"title": "Provider failure metering"},
            ),
            request_id="agent-provider-failure",
            tenant_id="system",
            record_provider_usage=lambda used_provider: recorded.append(used_provider.name),
        )

    assert recorded == ["failing"]


def test_document_ops_agent_resolves_lazy_provider_for_each_run(monkeypatch) -> None:
    providers = [NamedRawProvider("provider-one"), NamedRawProvider("provider-two")]

    def _next_provider(capability: str) -> Provider:
        assert capability == "generation"
        return providers.pop(0)

    monkeypatch.setattr(
        "app.providers.factory.get_provider_for_capability",
        _next_provider,
    )
    agent = DocumentOpsAgent()
    request = DocumentOpsRequest(
        task_type="decision_brief",
        requirements={"title": "Per-run provider isolation"},
    )

    first = agent.run(
        request,
        request_id="agent-provider-one",
        tenant_id="tenant-one",
    )
    second = agent.run(
        request,
        request_id="agent-provider-two",
        tenant_id="tenant-two",
    )

    assert first.provider_name == "provider-one"
    assert second.provider_name == "provider-two"
    assert providers == []


def test_document_ops_agent_persists_trajectory_when_store_is_configured(tmp_path) -> None:
    store = TrajectoryStore(tmp_path)
    agent = DocumentOpsAgent(provider=MockProvider(), trajectory_store=store)

    result = agent.run(
        DocumentOpsRequest(
            task_type="policy_planning_brief",
            requirements={
                "title": "민감자료 레드액션 정책",
                "raw_attachment": "binary-like-data",
            },
            source_references=[{"id": "source-1"}],
            capture_trajectory=True,
        ),
        request_id="agent-test-store",
        tenant_id="tenant-a",
    )

    assert result.trajectory is not None
    assert result.trajectory["persisted"] is True
    records = store.get_records(tenant_id="tenant-a")
    assert len(records) == 1
    assert records[0]["request_id"] == "agent-test-store"
    assert records[0]["input"]["requirements"]["raw_attachment"] == "[redacted]"
    assert records[0]["draft_output"] == result.draft


def test_document_ops_agent_runs_evidence_gap_review_with_mock_provider() -> None:
    agent = DocumentOpsAgent(provider=MockProvider())
    result = agent.run(
        DocumentOpsRequest(
            task_type="evidence_gap_review",
            requirements={
                "title": "실증 KPI 검토",
                "draft": "소요기간과 KPI는 확인 전입니다.",
            },
        ),
        request_id="agent-test-002",
        tenant_id="system",
    )

    assert result.skill_name == "evidence-gap-checker"
    assert result.evidence_status.gaps
    assert "TODO" in result.draft
    assert "evidence_gap:no_confirmed_sources" in result.quality_warnings


def test_document_ops_agent_runs_decision_brief_with_preferred_skill() -> None:
    agent = DocumentOpsAgent(provider=MockProvider())
    result = agent.run(
        DocumentOpsRequest(
            task_type="decision_brief",
            skill_name="decision-brief-builder",
            requirements={
                "title": "Part 02 복원 방향 결정",
                "decision_needed": "v6 기준 상세 도식을 기준본으로 채택할지 결정",
            },
            source_references=[{"id": "part02-v6"}],
        ),
        request_id="agent-test-003",
        tenant_id="system",
    )

    assert result.skill_name == "decision-brief-builder"
    assert "결정 필요" in result.draft
    assert not result.qa["forbidden_terms"]


def test_document_ops_agent_runs_develop_quality_improvement_with_mock_provider() -> None:
    agent = DocumentOpsAgent(provider=MockProvider())
    result = agent.run(
        DocumentOpsRequest(
            task_type="develop_quality_improvement",
            requirements={
                "title": "대표 보고 초안 품질 개선",
                "draft": "현재 초안은 정책 목표와 승인 질문이 뒤섞여 있고 근거 구분이 약합니다.",
                "goal": "대표가 승인 가능한 개선본으로 정리",
            },
            source_references=[{"id": "reviewed-draft", "title": "검토된 초안"}],
            capture_trajectory=True,
        ),
        request_id="agent-test-develop",
        tenant_id="system",
    )

    assert result.skill_name == "develop-document-improver"
    assert result.critique
    assert result.revision_tasks
    assert "개선안" in result.draft
    assert result.qa["hard_gate_pass"] is True
    assert result.trajectory is not None
    assert result.trajectory["critique"] == result.critique
    assert result.trajectory["revision_tasks"] == result.revision_tasks


def test_document_ops_agent_marks_local_fallback_when_provider_output_is_invalid() -> None:
    agent = DocumentOpsAgent(provider=RawTextProvider())
    result = agent.run(
        DocumentOpsRequest(
            task_type="policy_planning_brief",
            requirements={"title": "Fallback 검증"},
            source_references=[{"id": "source-1"}],
        ),
        request_id="agent-test-004",
        tenant_id="system",
    )

    assert result.qa["fallback_used"] is True
    assert result.qa["hard_gate_pass"] is False
    assert "agent_fallback:JSONDecodeError" in result.quality_warnings
    assert result.qa["gate_issues"]
    assert all(issue["affected_field"] for issue in result.qa["gate_issues"])
    assert all(issue["remediation_hint"] for issue in result.qa["gate_issues"])


def test_document_ops_agent_normalizes_live_provider_payload_variants() -> None:
    raw = json.dumps(
        {
            "draft_output": (
                "# 보행자 안전서비스 기획안\n\n"
                "## 문제와 결정\n"
                "교차로 보행자 안전서비스 파일럿은 사고 위험을 낮추기 위한 정책 판단 문서입니다. "
                "확인된 교통 안전 근거와 아직 검증이 필요한 가정을 구분하고, 승인자는 운영 전제와 "
                "보안 리스크를 함께 검토해야 합니다.\n\n"
                "## 운영 및 거버넌스\n"
                "개인정보 최소 수집, 접근 권한 통제, 로그/감사 기록, 운영책임자를 명확히 두어 "
                "공공 안전서비스의 거버넌스와 리스크 대응을 승인 가능한 수준으로 관리합니다."
            ),
            "plan": "근거 확인, 운영책임 정의, 승인 조건 정리를 순서대로 수행합니다.",
            "evidence_status": {
                "confirmed": [{"id": "traffic-source", "title": "교차로 사고 분석"}],
                "assumed": ["파일럿 대상 교차로는 운영 부서가 지정한다고 가정"],
                "open_questions": [{"message": "개인정보 영향평가 범위 확인 필요"}],
                "sources": [{"id": "traffic-source", "title": "교차로 사고 분석"}],
            },
            "quality_critique": {"message": "승인 질문이 앞부분에 더 명확해야 합니다."},
            "action_items": ["권한 정책을 검토 항목으로 추가합니다."],
            "qa": {"hard_gate_pass": True, "warnings": "권한 정책은 배포 전 재확인"},
            "extra_model_note": "ignored",
        },
        ensure_ascii=False,
    )
    agent = DocumentOpsAgent(provider=StaticJsonProvider(raw))

    result = agent.run(
        DocumentOpsRequest(
            task_type="policy_planning_brief",
            requirements={"title": "보행자 안전서비스"},
        ),
        request_id="agent-test-normalize",
        tenant_id="system",
    )

    assert result.provider_name == "static-json"
    assert result.qa["hard_gate_pass"] is True
    assert "fallback_used" not in result.qa
    assert result.plan == ["근거 확인, 운영책임 정의, 승인 조건 정리를 순서대로 수행합니다."]
    assert result.critique == ["승인 질문이 앞부분에 더 명확해야 합니다."]
    assert result.revision_tasks == ["권한 정책을 검토 항목으로 추가합니다."]
    assert result.evidence_status.confirmed == ["traffic-source"]
    assert result.evidence_status.source_references == ["traffic-source"]
    assert "권한 정책은 배포 전 재확인" in result.quality_warnings


def test_document_ops_agent_parses_fenced_json_without_fallback() -> None:
    raw = (
        "```json\n"
        + json.dumps(
            {
                "result": {
                    "plan": ["현황 정리", "운영책임 정의", "승인 조건 정리"],
                    "content": (
                        "# 정책 기획안\n\n"
                        "## 승인 판단\n"
                        "이 문서는 공공 AI 서비스의 문제, 근거, 실행 조건을 검토합니다. "
                        "개인정보와 보안, 운영책임, 리스크, 로그/감사 체계를 승인 전에 점검합니다."
                    ),
                    "evidence_status": {
                        "facts": ["source-a"],
                        "assumptions": ["운영 부서가 지정됨"],
                        "gaps": [],
                        "source_refs": ["source-a"],
                    },
                    "qa": {"hard_gate_pass": True, "warnings": []},
                }
            },
            ensure_ascii=False,
        )
        + "\n```"
    )
    agent = DocumentOpsAgent(provider=StaticJsonProvider(raw))

    result = agent.run(
        DocumentOpsRequest(task_type="policy_planning_brief", requirements={"title": "Fenced JSON"}),
        request_id="agent-test-fenced",
        tenant_id="system",
    )

    assert result.qa["hard_gate_pass"] is True
    assert "fallback_used" not in result.qa
    assert result.evidence_status.confirmed == ["source-a"]


def test_document_ops_agent_does_not_hide_provider_errors() -> None:
    agent = DocumentOpsAgent(provider=FailingProvider())

    with pytest.raises(ProviderError):
        agent.run(
            DocumentOpsRequest(
                task_type="policy_planning_brief",
                requirements={"title": "Provider failure"},
            ),
            request_id="agent-test-005",
            tenant_id="system",
        )


@pytest.mark.parametrize("tenant_id", ["", " tenant", "tenant ", ".", "..", "a/b", "a\\b"])
def test_document_ops_agent_rejects_invalid_tenant_before_provider_call(tenant_id: str) -> None:
    agent = DocumentOpsAgent(provider=FailingProvider())

    with pytest.raises(ValueError, match="Invalid tenant_id"):
        agent.run(
            DocumentOpsRequest(
                task_type="policy_planning_brief",
                requirements={"title": "Invalid tenant"},
            ),
            request_id="agent-invalid-tenant",
            tenant_id=tenant_id,
        )
