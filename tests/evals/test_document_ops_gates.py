from app.evals.document_ops.gates import evaluate_document_ops_output


def _good_policy_draft() -> str:
    return """# 보행자 보호 통합 안전서비스

## 문제와 근거
보행자 사고 위험이 반복되는 교차로에서 교통약자 안전을 높이기 위해 확인된 사고 분석 자료와 운영 로그를 근거로 문제를 정의합니다.

## 실행 및 운영
AI 감지, 현장 알림, 운영책임, 로그관리, 변경관리 절차를 연결하고 개인정보와 보안 검토를 포함합니다.

## 승인 요청
PM과 대표가 결정할 승인 범위, 리스크, 다음 실행 일정을 분리합니다.
"""


def test_document_ops_gate_passes_grounded_policy_brief() -> None:
    result = evaluate_document_ops_output(
        task_type="policy_planning_brief",
        draft=_good_policy_draft(),
        plan=["요구사항 분리", "근거 검토", "장표 구조 확정"],
        evidence_status={
            "confirmed": ["사고 분석 자료"],
            "assumptions": ["운영 로그 연동 가능"],
            "gaps": [],
            "source_references": ["accident-report"],
        },
    )

    assert result.hard_gate_pass is True
    assert result.recommended_next_action == "approve"
    assert result.forbidden_terms == []
    assert result.overall_score >= 0.72


def test_document_ops_gate_blocks_forbidden_terms() -> None:
    result = evaluate_document_ops_output(
        task_type="decision_brief",
        draft="## 승인 요청\n평가기준과 배점 기준에 맞춰 제안서를 구성합니다.",
        plan=["검토"],
        evidence_status={"confirmed": ["RFP"], "source_references": ["rfp"]},
    )

    assert result.hard_gate_pass is False
    assert result.recommended_next_action == "request_changes"
    assert "평가기준" in result.forbidden_terms
    assert any(issue.code == "forbidden_terms" for issue in result.issues)


def test_document_ops_gate_blocks_confirmed_claims_without_sources() -> None:
    result = evaluate_document_ops_output(
        task_type="decision_brief",
        draft="## 근거\n공식 통계에 따라 사고가 증가했습니다.\n## 권고\n승인 후 실행합니다.",
        plan=["근거 확인", "승인 요청"],
        evidence_status={"confirmed": ["공식 통계상 사고 증가"], "source_references": []},
    )

    assert result.hard_gate_pass is False
    assert any(issue.code == "unsupported_confirmed_claims" for issue in result.issues)


def test_document_ops_gate_blocks_certainty_when_open_gaps_exist() -> None:
    result = evaluate_document_ops_output(
        task_type="decision_brief",
        draft="## 효과\n비용 절감 확정 및 100% 성과 보장을 전제로 승인합니다.\n## 다음\n실행합니다.",
        plan=["효과 검토", "승인 요청"],
        evidence_status={"gaps": ["비용 산정 근거 필요"], "source_references": ["draft"]},
    )

    assert result.hard_gate_pass is False
    assert any(issue.code == "certainty_with_open_gaps" for issue in result.issues)


def test_document_ops_gate_blocks_policy_brief_without_governance_security_review() -> None:
    result = evaluate_document_ops_output(
        task_type="policy_planning_brief",
        draft="## 문제\n교차로 사고를 줄이기 위한 AI 시스템을 도입합니다.\n## 실행\n센서를 설치하고 알림을 보냅니다.",
        plan=["문제 정의", "실행안"],
        evidence_status={"confirmed": ["현장 조사"], "source_references": ["field"]},
    )

    assert result.hard_gate_pass is False
    assert any(issue.code == "missing_governance_privacy_security" for issue in result.issues)


def test_document_ops_gate_collects_more_evidence_when_only_warning_remains() -> None:
    result = evaluate_document_ops_output(
        task_type="evidence_gap_review",
        draft=(
            "## 근거 점검 결과\n"
            "현재 입력에서 공식 근거로 확정 가능한 항목은 제한적입니다. "
            "사용자 초안의 방향성은 유지하되 수치, 일정, 기관명은 TODO로 분리해 추가 확인합니다.\n"
            "## 후속 조치\n"
            "PM 검토 전 공식 통계와 출처 문서를 수집합니다."
        ),
        plan=["근거 분리", "TODO 확인", "수정 요청"],
        evidence_status={"confirmed": [], "assumptions": ["방향성은 유효"], "gaps": ["공식 통계 필요"], "source_references": []},
    )

    assert result.hard_gate_pass is True
    assert result.recommended_next_action == "collect_more_evidence"
    assert "evidence_gap:no_confirmed_sources" in result.warnings
