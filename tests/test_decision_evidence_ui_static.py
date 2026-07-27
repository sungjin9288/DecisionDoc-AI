from pathlib import Path


def test_decision_evidence_map_static_contract_is_read_only_and_accessible():
    html = Path("app/static/index.html").read_text(encoding="utf-8")
    svg_builder = html[
        html.index("function buildDecisionEvidenceSvg"):
        html.index("function renderDecisionEvidenceRelation")
    ]

    assert "/decision-evidence-map?bundle_type=proposal_kr" in html
    assert "renderDecisionEvidenceMapPanel" in html
    assert "buildDecisionEvidenceSvg" in html
    assert "buildDecisionEvidenceIndex" in html
    assert "deriveDecisionEvidenceView" in html
    assert "getDecisionEvidenceScopeKey" in html
    assert "wireDecisionEvidenceMapActions" in html
    assert 'aria-hidden="true"' in svg_builder
    assert 'focusable="false"' in svg_builder
    assert 'role="img"' not in svg_builder
    assert 'role="button"' not in svg_builder
    assert 'tabindex="0"' not in svg_builder
    assert "aria-selected" not in svg_builder
    assert 'class="decision-evidence-table"' in html
    assert 'aria-pressed="${nodeId === view.selectedNodeId ? \'true\' : \'false\'}"' in html
    assert "READ ONLY · NON-ATOMIC SNAPSHOT" in html
    assert "기존 문서의 추정 일치는 검증된 coverage로 승격하지 않습니다." in html
    assert "Referenced slides" in html
    assert "Provenance level (not proof or approval)" in html
    assert "does not establish external authenticity" in html
    assert 'id="decision-evidence-provenance-note"' in html
    assert 'aria-describedby="decision-evidence-provenance-note"' in html
    assert "Visible / projection relations" in html
    assert "projectionRelationCountById" in html
    assert "Content SHA-256" in html
    assert "Gaps only" in html
    assert "Lineage only" in html
    assert "Show sources" in html
    assert "Target omitted from current projection" in html
    assert "diagnostic target included" in html
    assert "diagnostic source target hidden; enable Show sources" in html
    assert "forcedVisibleNodeId" in html
    assert 'data-provenance-level="${escapeHtml(evidenceLevel)}"' in html
    assert "Authoritative · solid" in html
    assert "Record binding · dashed" in html
    assert "Derived · dotted" in html
    assert '@media (prefers-reduced-motion: reduce)' in html
    assert "handleDecisionEvidencePresentationEscape" in html
    assert (
        "document.addEventListener("
        "'keydown', handleDecisionEvidencePresentationEscape, true"
    ) in html
    assert (
        ".decision-evidence-map.presentation-mode .decision-evidence-layout {\n"
        "        grid-template-columns: minmax(0, 1fr);"
    ) in html
    assert "presentation-mode" in html
    assert "Fullscreen" not in html
    assert "three.js" not in html.lower()
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
