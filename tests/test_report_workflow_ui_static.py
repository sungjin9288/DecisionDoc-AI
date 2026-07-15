from pathlib import Path


def test_report_workflow_tab_and_stepper_present():
    html = Path("app/static/index.html").read_text(encoding="utf-8")

    assert 'data-page="report-workflow-page"' in html
    assert "보고서 워크플로우" in html
    assert "1. 기획" in html
    assert "Owner" in html
    assert "PM Reviewer" in html
    assert "Executive Approver" in html
    assert "Owner submit → PM Reviewer approval → Executive Approver approval" in html
    assert "rw-owner" in html
    assert "rw-pm-reviewer" in html
    assert "rw-executive-approver" in html
    assert "pm_reviewer" in html
    assert "executive_approver" in html
    assert "renderReportWorkflowRoleLine" in html
    assert "renderReportWorkflowApprovalWarnings" in html
    assert "셀프 최종 승인 경고" in html
    assert "approval_assignee_mismatch" in html
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
    assert "담당:" in html
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
    assert "rw-quality-artifact-summary" in html
    assert "학습 후보 correction artifacts" in html
    assert "Ready JSONL" in html
    assert "renderReportWorkflowQualityArtifactSummary" in html
    assert "loadReportWorkflowQualityArtifacts" in html
    assert "downloadReportWorkflowQualityArtifacts" in html
    assert "검토 패키지 검증" in html
    assert "수신 패키지 검증 완료" in html
    assert "verifyReportWorkflowQualityPilotPackage" in html
    quality_review_markup = html[
        html.index("function renderReportWorkflowQualityScoreInputs"):
        html.index("function reportWorkflowSplitLines")
    ]
    assert 'id="rw-quality-overall"' in html
    assert 'placeholder="0.00 - 1.00"' in html
    assert 'value="0.86"' not in quality_review_markup
    assert "Dimension rationale" in html
    assert "사람 검수로 논리, 근거, 장표 구조, 디자인 품질을 보강함" not in html


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
    assert "`/report-workflows/learning/correction-artifacts?${params}`" in html
    assert "/report-workflows/learning/correction-artifacts/export?ready_only=true&limit=200" in html
    assert "/report-workflows/learning/correction-artifacts/${encodeURIComponent(normalizedId)}" in html
    assert 'data-rw-quality-artifacts-action="inspect"' in html
    assert 'data-rw-quality-artifacts-action="download-one"' in html
    assert 'data-rw-quality-artifacts-action="preview-pilot"' in html
    assert 'data-rw-quality-artifacts-action="download-pilot"' in html
    assert 'data-rw-quality-artifacts-action="download-pilot-package"' in html
    assert 'data-rw-quality-artifacts-action="verify-package"' in html
    assert 'data-rw-quality-artifacts-action="copy-pilot-import-command"' in html
    assert 'id="rw-quality-package-file"' in html
    assert "data-rw-quality-artifact-select" in html
    assert "/report-workflows/learning/correction-artifacts/pilot-export/preview" in html
    assert "/report-workflows/learning/correction-artifacts/pilot-export/package" in html
    assert "/report-workflows/learning/correction-artifacts/pilot-package/verify" in html
    assert "buildReportWorkflowQualityPilotImportCommand" in html
    assert "quotePosixShellArgument" in html
    assert '"$HOME"/Downloads/' in html
    assert "copyReportWorkflowQualityPilotImportCommand" in html
    assert "Local review pack 준비 명령을 복사했습니다." in html
    assert "_reportWorkflowQualityPilotImportCommand = '';" in html
    assert "X-DecisionDoc-Pilot-Package-SHA256" in html
    assert "/report-workflows/learning/correction-artifacts/pilot-export" in html
    assert "artifactIds.length < 3 || artifactIds.length > 5" in html
    assert "X-DecisionDoc-Pilot-SHA256" in html
    assert "X-DecisionDoc-Pilot-Preview-Verified" in html
    assert "X-DecisionDoc-Pilot-Receipt" in html
    assert "X-DecisionDoc-Pilot-Receipt-SHA256" in html
    assert "preview_sha256: _reportWorkflowQualityPilotPreview.export_sha256" in html
    assert "previewReportWorkflowQualityPilotArtifacts" in html
    assert "renderReportWorkflowQualityPilotPreview" in html
    assert "REPORT_WORKFLOW_QUALITY_ARTIFACT_PAGE_SIZE = 5" in html
    assert "data-rw-quality-artifacts-action=\"show-all\"" in html
    assert "data-rw-quality-artifacts-action=\"show-ready\"" in html
    assert "data-rw-quality-artifacts-action=\"previous-page\"" in html
    assert "data-rw-quality-artifacts-action=\"next-page\"" in html
    assert "_reportWorkflowQualityPilotSelection.clear()" in html
    assert "visibleArtifacts" not in html
    assert "Pilot preview 이후 export 내용이 변경되었습니다" in html
    assert "Pilot export의 server preview 검증 증거가 없습니다" in html
    assert "Pilot export receipt가 현재 다운로드와 일치하지 않습니다" in html
    assert "result?.package_sha256 !== browserSha256" in html
    assert "result?.persisted !== false" in html
    assert "artifact_semantics_verified" in html
    assert "result?.review_readiness?.all_ready !== true" in html
    assert "item?.validation_ok === true && item?.ready_for_learning === true" in html
    assert "검증된 correction evidence" in html
    assert "교정 전 기획" in html
    assert "Change requests" in html
    assert "requiredChecks.every(key => result?.validation?.[key] === true)" in html
    assert "blockedActions.every(key => result?.external_action_boundary?.[key] === false)" in html
    assert "#rw-quality-artifact-detail:not(:empty) { padding-bottom: 72px; }" in html
    assert "report_quality_pilot_artifacts_${exportSha256.slice(0, 12)}.jsonl" in html
    assert "report_quality_pilot_receipt_${exportSha256.slice(0, 12)}.json" in html
    assert "report_quality_correction_artifact_${safeId}.json" in html
    assert "visual-assets" in html
    assert "method: 'PUT'" in html
    assert "visual-assets/generate" in html
    assert "select_first" in html
    assert "content_base64" in html
    assert "visual-assets/select" in html
