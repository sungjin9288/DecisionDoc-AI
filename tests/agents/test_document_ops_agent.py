import hashlib
import json

import pytest

from app.agents.document_ops_agent import (
    DocumentOpsAgent,
    SkillBindingMismatchError,
)
from app.agents.schemas import DocumentOpsRequest
from app.agents.skill_registry import SkillNotFoundError
from app.providers.base import Provider, ProviderError
from app.providers.mock_provider import MockProvider
from app.schemas.document_ops import (
    DocumentOpsComparisonChangeSetRequest,
    DocumentOpsComparisonChangeSetResponse,
)
from app.services.document_ops_comparison import build_document_ops_comparison_change_set
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


class ProviderTrackingAgent(DocumentOpsAgent):
    def __init__(self) -> None:
        super().__init__()
        self.provider_accesses = 0

    @property
    def provider(self) -> Provider:
        self.provider_accesses += 1
        return FailingProvider()


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
    assert result.skill_version == result.skill_binding.skill_version
    assert result.skill_name == result.skill_binding.skill_name
    assert result.skill_binding.code_execution_authorized is False
    assert result.skill_binding.external_runtime_authorized is False
    assert result.plan
    assert "보행자 안전 정책 기획 사업" in result.draft
    assert result.qa["hard_gate_pass"] is True
    assert result.trajectory is not None
    assert result.trajectory["skill"]["name"] == "policy-planning"
    assert result.trajectory["skill_binding"] == result.skill_binding.model_dump()


def test_document_ops_agent_selects_source_grounded_skill_and_includes_governed_instructions() -> None:
    prompts: list[str] = []

    class PromptProvider(StaticJsonProvider):
        def generate_raw(self, prompt: str, *, request_id: str, max_output_tokens: int | None = None) -> str:
            prompts.append(prompt)
            return self.raw

    raw = json.dumps(
        {
            "plan": ["의사결정 의도와 source mapping을 확인합니다."],
            "draft": "확인된 근거와 TODO를 구분한 검토 초안입니다.",
            "evidence_status": {
                "confirmed": ["source-1"],
                "assumptions": ["운영 범위는 확인 필요"],
                "gaps": ["추가 원문 확인 필요"],
                "source_references": ["source-1"],
            },
            "qa": {"hard_gate_pass": False, "warnings": ["review required"]},
        },
        ensure_ascii=False,
    )
    result = DocumentOpsAgent(provider=PromptProvider(raw)).run(
        DocumentOpsRequest(
            task_type="source_grounded_document",
            requirements={"title": "근거 기반 의사결정", "decision_intent": "검토 범위 결정"},
            source_references=[{"id": "source-1", "title": "확인된 원문"}],
        ),
        request_id="agent-source-grounded",
        tenant_id="system",
    )

    assert result.skill_name == "source-grounded-document"
    binding_json = json.dumps(
        result.skill_binding.model_dump(),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    assert prompts and prompts[0].count(binding_json) == 1
    assert "decision intent" in prompts[0]
    assert "source reference" in prompts[0]
    assert "Non-authorization" in prompts[0]
    assert "do not grant or change provider, tenant, approval" in prompts[0]
    assert "training, publication, code-execution, or external-runtime authority" in prompts[0]


@pytest.mark.parametrize(
    "requirements",
    [
        {},
        {"baseline_document_text": "", "candidate_document_text": "candidate"},
        {"baseline_document_text": "baseline", "candidate_document_text": "   "},
        {"baseline_document_text": 1, "candidate_document_text": "candidate"},
        {"baseline_document_text": "baseline", "candidate_document_text": ["candidate"]},
        {"baseline_document_text": "x" * 20_001, "candidate_document_text": "candidate"},
        {"baseline_document_text": "baseline", "candidate_document_text": "candidate", "comparison_criteria": "not-a-list"},
        {"baseline_document_text": "baseline", "candidate_document_text": "candidate", "comparison_criteria": ["same", " same "]},
        {"baseline_document_text": "baseline", "candidate_document_text": "candidate", "comparison_criteria": ["x"] * 9},
        {"baseline_document_text": "baseline", "candidate_document_text": "candidate", "comparison_criteria": ["x" * 121]},
    ],
)
def test_document_comparison_request_validation_rejects_before_skill_or_provider(requirements: dict) -> None:
    agent = ProviderTrackingAgent()

    with pytest.raises(ValueError):
        request = DocumentOpsRequest(
            task_type="document_comparison_review",
            requirements=requirements,
        )
        agent.resolve_skill_binding(request)

    assert agent.provider_accesses == 0


def test_document_ops_agent_runs_grounded_document_comparison_with_redacted_trajectory() -> None:
    baseline = "목적: 운영 범위 확인\n담당: PM"
    candidate = "목적: 운영 범위와 보안 검토 확인\n담당: PM\n검토: 보안 담당"
    request = DocumentOpsRequest(
        task_type="document_comparison_review",
        requirements={
            "title": "운영 변경 비교",
            "baseline_document_text": baseline,
            "candidate_document_text": candidate,
            "comparison_criteria": [" 관찰된 변경 ", "결정 영향"],
        },
        capture_trajectory=True,
    )

    result = DocumentOpsAgent(provider=MockProvider()).run(
        request,
        request_id="agent-document-comparison",
        tenant_id="system",
    )

    expected_context = {
        "schema_version": "document_ops_comparison_context_v1",
        "baseline_sha256": hashlib.sha256(baseline.encode("utf-8")).hexdigest(),
        "candidate_sha256": hashlib.sha256(candidate.encode("utf-8")).hexdigest(),
        "documents_identical": False,
        "comparison_criteria": ["관찰된 변경", "결정 영향"],
        "raw_content_included": False,
    }
    assert result.skill_name == "document-comparison-review"
    assert result.qa["hard_gate_pass"] is False
    assert "missing_comparison_sections" not in {issue["code"] for issue in result.qa["gate_issues"]}
    assert result.comparison_context is not None
    assert result.comparison_context.model_dump() == expected_context
    assert result.trajectory is not None
    assert result.trajectory["comparison_context"] == expected_context
    assert result.trajectory["input"]["requirements"]["baseline_document_text"] == "[redacted]"
    assert result.trajectory["input"]["requirements"]["candidate_document_text"] == "[redacted]"
    assert baseline not in json.dumps(result.trajectory, ensure_ascii=False)
    assert candidate not in json.dumps(result.trajectory, ensure_ascii=False)
    for heading in (
        "관찰된 변경",
        "근거와 가정 변화",
        "결정 및 트레이드오프 영향",
        "권한·거버넌스 경계",
        "권고",
        "사람 재확인 질문",
    ):
        assert heading in result.draft


def test_document_ops_agent_compares_identical_documents_without_inventing_a_change() -> None:
    document = "동일 문서\n검토 대기"
    result = DocumentOpsAgent(provider=MockProvider()).run(
        DocumentOpsRequest(
            task_type="document_comparison_review",
            requirements={
                "baseline_document_text": document,
                "candidate_document_text": document,
            },
        ),
        request_id="agent-document-comparison-identical",
        tenant_id="system",
    )

    assert result.comparison_context is not None
    assert result.comparison_context.documents_identical is True
    assert "텍스트 변경은 관찰되지 않았습니다" in result.draft


def test_document_comparison_request_omits_criteria_as_an_empty_normalized_list() -> None:
    request = DocumentOpsRequest(
        task_type="document_comparison_review",
        requirements={
            "baseline_document_text": "baseline",
            "candidate_document_text": "candidate",
        },
    )

    assert request.comparison_context is not None
    assert request.comparison_context.comparison_criteria == []


def test_document_comparison_change_set_keeps_complete_long_identical_counts_with_bounded_hunks() -> None:
    document = "\n".join(f"repeated-{index % 5}" for index in range(500))

    result = build_document_ops_comparison_change_set(
        DocumentOpsComparisonChangeSetRequest(
            baseline_document_text=document,
            candidate_document_text=document,
        )
    )

    assert result.documents_identical is True
    assert result.baseline_line_count == result.candidate_line_count == 500
    assert result.equal_line_count == 500
    assert result.added_line_count == result.removed_line_count == result.replaced_line_count == 0
    assert result.total_hunk_count == 1
    assert result.hunks_truncated is True
    assert len(result.hunks) == 1
    assert result.hunks[0].opcode == "equal"
    assert len(result.hunks[0].baseline_lines) + len(result.hunks[0].candidate_lines) == 200
    assert result.hunks[0].baseline_end == result.hunks[0].candidate_end == 100


def test_document_comparison_change_set_aggregates_asymmetric_replace_sides_before_max() -> None:
    baseline = "same\nA1\nA2\nA3\nanchor\nB1\ntail"
    candidate = "same\nX1\nanchor\nY1\nY2\nY3\ntail"

    result = build_document_ops_comparison_change_set(
        DocumentOpsComparisonChangeSetRequest(
            baseline_document_text=baseline,
            candidate_document_text=candidate,
            comparison_criteria=[" replacement balance "],
        )
    )

    replace_hunks = [hunk for hunk in result.hunks if hunk.opcode == "replace"]
    assert [
        (hunk.baseline_end - hunk.baseline_start, hunk.candidate_end - hunk.candidate_start)
        for hunk in replace_hunks
    ] == [(3, 1), (1, 3)]
    assert result.baseline_replaced_line_count == 4
    assert result.candidate_replaced_line_count == 4
    assert result.replaced_line_count == 4
    assert result.comparison_criteria == ["replacement balance"]


def test_document_comparison_change_set_applies_one_global_contiguous_hunk_budget() -> None:
    baseline = "\n".join(f"line-{index}" for index in range(150))
    candidate = "\n".join(
        value
        for index in range(150)
        for value in (f"line-{index}", f"add-{index}")
    )

    result = build_document_ops_comparison_change_set(
        DocumentOpsComparisonChangeSetRequest(
            baseline_document_text=baseline,
            candidate_document_text=candidate,
        )
    )

    assert result.total_hunk_count == 300
    assert result.hunks_truncated is True
    assert len(result.hunks) < result.total_hunk_count
    assert sum(
        len(hunk.baseline_lines) + len(hunk.candidate_lines)
        for hunk in result.hunks
    ) == 200
    baseline_cursor = candidate_cursor = 0
    for hunk in result.hunks:
        assert hunk.baseline_start == baseline_cursor
        assert hunk.candidate_start == candidate_cursor
        assert hunk.baseline_end - hunk.baseline_start == len(hunk.baseline_lines)
        assert hunk.candidate_end - hunk.candidate_start == len(hunk.candidate_lines)
        baseline_cursor = hunk.baseline_end
        candidate_cursor = hunk.candidate_end
    assert result.baseline_line_count == 150
    assert result.candidate_line_count == 300
    assert result.equal_line_count == 150
    assert result.added_line_count == 150


def test_document_comparison_change_set_models_reject_invalid_request_and_response_contracts() -> None:
    with pytest.raises(ValueError):
        DocumentOpsComparisonChangeSetRequest(
            baseline_document_text="invalid-\ud800",
            candidate_document_text="candidate",
        )
    with pytest.raises(ValueError):
        DocumentOpsComparisonChangeSetRequest(
            baseline_document_text="baseline",
            candidate_document_text="candidate",
            comparison_criteria=["same", " same "],
        )
    with pytest.raises(ValueError):
        DocumentOpsComparisonChangeSetRequest.model_validate(
            {
                "baseline_document_text": "baseline",
                "candidate_document_text": "candidate",
                "unknown": True,
            }
        )

    valid = build_document_ops_comparison_change_set(
        DocumentOpsComparisonChangeSetRequest(
            baseline_document_text="same\nold\ntail",
            candidate_document_text="same\nnew\ntail",
        )
    ).model_dump()
    invalid_payloads: list[dict] = []

    impossible_counts = json.loads(json.dumps(valid))
    impossible_counts["baseline_line_count"] += 1
    invalid_payloads.append(impossible_counts)

    inconsistent_identical = json.loads(json.dumps(valid))
    inconsistent_identical["documents_identical"] = True
    invalid_payloads.append(inconsistent_identical)

    incoherent_truncation = json.loads(json.dumps(valid))
    incoherent_truncation["hunks_truncated"] = True
    invalid_payloads.append(incoherent_truncation)

    invalid_opcode_sides = json.loads(json.dumps(valid))
    replace_index = next(
        index for index, hunk in enumerate(invalid_opcode_sides["hunks"])
        if hunk["opcode"] == "replace"
    )
    invalid_opcode_sides["hunks"][replace_index]["opcode"] = "insert"
    invalid_payloads.append(invalid_opcode_sides)

    discontinuous = json.loads(json.dumps(valid))
    discontinuous["hunks"][1]["baseline_start"] += 1
    invalid_payloads.append(discontinuous)

    incomplete = json.loads(json.dumps(valid))
    incomplete["hunks"] = incomplete["hunks"][:-1]
    invalid_payloads.append(incomplete)

    unknown_response = json.loads(json.dumps(valid))
    unknown_response["unknown"] = True
    invalid_payloads.append(unknown_response)

    invalid_utf8_criterion = json.loads(json.dumps(valid))
    invalid_utf8_criterion["comparison_criteria"] = ["invalid-\ud800"]
    invalid_payloads.append(invalid_utf8_criterion)

    invalid_utf8_source_line = json.loads(json.dumps(valid))
    invalid_utf8_source_line["hunks"][0]["baseline_lines"][0] = "invalid-\ud800"
    invalid_utf8_source_line["hunks"][0]["candidate_lines"][0] = "invalid-\ud800"
    invalid_payloads.append(invalid_utf8_source_line)

    for payload in invalid_payloads:
        with pytest.raises(ValueError):
            DocumentOpsComparisonChangeSetResponse.model_validate(payload)


def test_document_ops_agent_rejects_skill_resolution_and_binding_drift_before_provider() -> None:
    unknown_agent = ProviderTrackingAgent()
    with pytest.raises(SkillNotFoundError, match="unknown skill"):
        unknown_agent.run(
            DocumentOpsRequest(
                task_type="decision_brief",
                skill_name="unknown-skill",
            ),
            request_id="agent-unknown-skill",
            tenant_id="system",
        )
    assert unknown_agent.provider_accesses == 0

    unsupported_agent = ProviderTrackingAgent()
    with pytest.raises(SkillNotFoundError, match="does not support"):
        unsupported_agent.run(
            DocumentOpsRequest(
                task_type="decision_brief",
                skill_name="policy-planning",
            ),
            request_id="agent-unsupported-skill",
            tenant_id="system",
        )
    assert unsupported_agent.provider_accesses == 0

    drift_agent = ProviderTrackingAgent()
    request = DocumentOpsRequest(task_type="decision_brief")
    binding = drift_agent.resolve_skill_binding(request)
    drifted_binding = binding.model_copy(
        update={"catalog_fingerprint": "0" * 64}
    )
    with pytest.raises(SkillBindingMismatchError, match="binding changed"):
        drift_agent.run(
            request,
            request_id="agent-binding-drift",
            tenant_id="system",
            expected_skill_binding=drifted_binding,
        )
    assert drift_agent.provider_accesses == 0


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
