from pathlib import Path


def test_decision_evidence_map_static_contract_is_read_only_and_accessible():
    html = Path("app/static/index.html").read_text(encoding="utf-8")

    assert "/decision-evidence-map?bundle_type=proposal_kr" in html
    assert "renderDecisionEvidenceMapPanel" in html
    assert "buildDecisionEvidenceSvg" in html
    assert "wireDecisionEvidenceMapActions" in html
    assert 'role="img"' in html
    assert 'role="button"' in html
    assert 'tabindex="0"' in html
    assert 'class="decision-evidence-table"' in html
    assert "READ ONLY · NON-ATOMIC SNAPSHOT" in html
    assert "기존 문서의 추정 일치는 검증된 coverage로 승격하지 않습니다." in html
    assert "Referenced slides" in html
    assert "Evidence-linked" not in html
    assert "actual_export_observed" not in html
    assert "d3." not in html
    assert "cytoscape" not in html.lower()
    assert "THREE." not in html


def test_decision_evidence_map_keeps_late_project_responses_guarded():
    html = Path("app/static/index.html").read_text(encoding="utf-8")
    load_project_detail = html[
        html.index("async function loadProjectDetail"):
        html.index("window.hideProjectDetail")
    ]

    evidence_fetch = load_project_detail.index("/decision-evidence-map?bundle_type=proposal_kr")
    evidence_current_guard = load_project_detail.index(
        "if (!requestIsCurrent()) return;",
        evidence_fetch,
    )
    render_call = load_project_detail.index("renderProjectDetail", evidence_fetch)
    assert evidence_fetch < evidence_current_guard < render_call
