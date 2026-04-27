from pathlib import Path


def test_report_workflow_tab_and_stepper_present():
    html = Path("app/static/index.html").read_text(encoding="utf-8")

    assert 'data-page="report-workflow-page"' in html
    assert "보고서 워크플로우" in html
    assert "1. 기획" in html
    assert "1. 기획 설계서" in html
    assert "기획 브리프" in html
    assert "독자 의사결정 기준" in html
    assert "보고서 스토리라인" in html
    assert "자료/근거 전략" in html
    assert "템플릿/디자인 가이드" in html
    assert "완성 기준" in html
    assert "의사결정 질문" in html
    assert "장표 승인 기준" in html
    assert "2. 장표 제작" in html
    assert "3. 최종 결재" in html
    assert "PM 승인" in html
    assert "대표 승인" in html
    assert "최종 수정 요청" in html
    assert "4. 프로젝트 산출물로 저장" in html
    assert "Project document" in html
    assert "Knowledge 저장" in html
    assert "rw-promote-project" in html
    assert "rw-promote-knowledge" in html
    assert "promoteReportWorkflow" in html
    assert "프로젝트에서 보기" in html
    assert "지식 관리에서 보기" in html
    assert "openReportWorkflowProject" in html
    assert "openReportWorkflowKnowledge" in html
    assert "focusProjectDocument" in html
    assert "data-project-doc-id" in html
    assert "project-doc-focus" in html
    assert "final/pm-approve" in html
    assert "final/executive-approve" in html
    assert "final/request-changes" in html


def test_report_workflow_ui_calls_expected_api_endpoints():
    html = Path("app/static/index.html").read_text(encoding="utf-8")

    assert "fetch('/report-workflows'" in html
    assert "planning/generate" in html
    assert "planning/request-changes" in html
    assert "slides/generate" in html
    assert "final/pm-approve" in html
    assert "final/executive-approve" in html
    assert "final/request-changes" in html
    assert "report-workflows/${encodeURIComponent(id)}/promote" in html
    assert "promote_to_knowledge" in html
    assert "loadReportWorkflowProjectOptions" in html
    assert "switchPage('project-page')" in html
    assert "switchPage('knowledge-page')" in html
    assert "/export/pptx" in html
