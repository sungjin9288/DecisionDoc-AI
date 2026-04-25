from pathlib import Path


def test_report_workflow_tab_and_stepper_present():
    html = Path("app/static/index.html").read_text(encoding="utf-8")

    assert 'data-page="report-workflow-page"' in html
    assert "보고서 워크플로우" in html
    assert "1. 기획" in html
    assert "2. 장표 제작" in html
    assert "3. 최종 승인" in html


def test_report_workflow_ui_calls_expected_api_endpoints():
    html = Path("app/static/index.html").read_text(encoding="utf-8")

    assert "fetch('/report-workflows'" in html
    assert "planning/generate" in html
    assert "planning/request-changes" in html
    assert "slides/generate" in html
    assert "final/approve" in html
    assert "/export/pptx" in html
