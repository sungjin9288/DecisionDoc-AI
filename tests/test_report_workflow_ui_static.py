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
    assert "reportWorkflowNextAction" in html
    assert "renderReportWorkflowListSignals" in html
    assert "다음: 프로젝트 산출물 저장" in html
    assert "완료: 승인본 저장됨" in html
    assert "Project 저장" in html
    assert "Knowledge 저장" in html
    assert "학습 opt-in" in html
    assert "final/pm-approve" in html
    assert "final/executive-approve" in html
    assert "final/request-changes" in html
    assert "Visual Asset Workspace" in html
    assert "asset metadata 저장" in html
    assert "editReportWorkflowSlideVisualAssets" in html
    assert "시각자료 후보 생성" in html
    assert "generateReportWorkflowVisualAssets" in html
    assert "reportWorkflowVisualAssetDataUri" in html
    assert "선택 asset 다운로드" in html
    assert "reportWorkflowVisualAssetsForSlide" in html
    assert "selectReportWorkflowSlideVisualAsset" in html
    assert "Snapshot Export" in html
    assert "downloadReportWorkflowSnapshot" in html
    assert "Report Workflow snapshot artifact" in html
    assert "Report Workflow smoke" in html
    assert "report_workflow_smoke_results" in html
    assert "getPostDeployReportWorkflowSmokeResults" in html
    assert "buildPostDeployReportWorkflowSmokeResultsSummary" in html
    assert "buildOpsPostDeployReportWorkflowSmokeResultDiffRows" in html


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
    assert "/export/snapshot" in html
    assert "visual-assets" in html
    assert "method: 'PUT'" in html
    assert "visual-assets/generate" in html
    assert "select_first" in html
    assert "content_base64" in html
    assert "visual-assets/select" in html
