from __future__ import annotations


def _edge(
    edge_id: str,
    source: str,
    target: str,
    *,
    relation_type: str = "supports",
    evidence_level: str = "authoritative",
    source_kind: str = "procurement_decision",
    source_id: str = "decision-1",
    source_revision: str = "2026-07-24T00:00:00Z",
    field_path: str = "recommendation.summary",
    content_sha256: str = "a" * 64,
) -> dict:
    return {
        "edge_id": edge_id,
        "relation_type": relation_type,
        "source_node_id": source,
        "target_node_id": target,
        "status": "current",
        "provenance": {
            "source_kind": source_kind,
            "source_id": source_id,
            "source_revision": source_revision,
            "field_path": field_path,
            "content_sha256": content_sha256,
            "evidence_level": evidence_level,
        },
    }

def _project() -> dict:
    return {
        "project_id": "evidence-ui-project",
        "name": "Decision Evidence UI",
        "description": "",
        "client": "DecisionDoc",
        "contract_number": "",
        "fiscal_year": 2026,
        "status": "active",
        "created_at": "2026-07-24T00:00:00Z",
        "documents": [],
        "meeting_recordings": [],
    }


def _map() -> dict:
    nodes = [
        {
            "node_id": "source:decision-1",
            "node_type": "source",
            "label": "RFP source",
            "status": "current",
            "summary": "Authoritative procurement record",
            "evidence_level": "authoritative",
            "relation_count": 2,
        },
        {
            "node_id": "requirement:security",
            "node_type": "requirement",
            "label": "Security owner",
            "status": "missing",
            "summary": "Security owner evidence is missing.",
            "evidence_level": "authoritative",
            "relation_count": 1,
            "diagnostic_codes": ["requirement_evidence_missing"],
        },
        {
            "node_id": "recommendation:decision-1",
            "node_type": "recommendation",
            "label": "CONDITIONAL_GO",
            "status": "current",
            "summary": "Proceed after evidence is attached.",
            "evidence_level": "authoritative",
            "relation_count": 2,
        },
        {
            "node_id": "claim:delivery",
            "node_type": "claim",
            "label": "<Delivery evidence>",
            "status": "pending",
            "summary": "A pending claim needs a source review.",
            "evidence_level": "derived",
            "relation_count": 2,
        },
        {
            "node_id": "document:proposal-1",
            "node_type": "document",
            "label": "Proposal draft",
            "status": "in_review",
            "summary": "proposal_kr",
            "evidence_level": "record_binding",
            "relation_count": 2,
        },
        {
            "node_id": "approval:approval-1",
            "node_type": "approval",
            "label": "Approval",
            "status": "in_review",
            "summary": "",
            "evidence_level": "authoritative",
            "relation_count": 1,
        },
        {
            "node_id": "export:workflow-1:pptx:1",
            "node_type": "export",
            "label": "PPTX export readiness",
            "status": "available",
            "summary": "Readiness only; no durable export receipt is observed.",
            "evidence_level": "derived",
            "relation_count": 1,
        },
    ]
    edges = [
        _edge("edge-0", "source:decision-1", "requirement:security", relation_type="states_requirement"),
        _edge(
            "edge-1",
            "source:decision-1",
            "recommendation:decision-1",
            relation_type="supports",
            evidence_level="record_binding",
        ),
        _edge(
            "edge-2",
            "source:decision-1",
            "claim:delivery",
            relation_type="states_claim",
            evidence_level="derived",
        ),
        _edge(
            "edge-3",
            "claim:delivery",
            "recommendation:decision-1",
            relation_type="supports",
            source_kind="decision_council<summary>",
            source_id="council<1>",
            source_revision="revision<2>",
            field_path="consensus.<summary>",
            content_sha256="b" * 64,
        ),
        _edge(
            "edge-4",
            "recommendation:decision-1",
            "document:proposal-1",
            relation_type="used_by",
            source_kind="project_document",
            source_id="document<1>",
            source_revision="2026-07-25T00:00:00Z",
            field_path="source_evidence_refs.<0>",
            content_sha256="c" * 64,
        ),
        _edge("edge-5", "approval:approval-1", "document:proposal-1", relation_type="approves"),
        _edge("edge-6", "document:proposal-1", "export:workflow-1:pptx:1", relation_type="export_ready_for"),
    ]
    return {
        "contract_version": "decision_evidence_map.v1",
        "generated_at": "2026-07-24T12:00:00Z",
        "project_id": "evidence-ui-project",
        "bundle_type": "proposal_kr",
        "read_only": True,
        "snapshot_atomic": False,
        "projection_fingerprint": "a" * 64,
        "source_revisions": [
            {
                "source_kind": "procurement_decision",
                "source_id": "decision-1",
                "revision": "2026-07-24T00:00:00Z",
                "content_sha256": "a" * 64,
            }
        ],
        "nodes": nodes,
        "edges": edges,
        "coverage": {
            "total": 1,
            "explicit": 0,
            "candidate": 0,
            "missing": 1,
            "unverifiable": 0,
            "items": [],
        },
        "diagnostics": [
            {
                "code": "requirement_evidence_missing",
                "severity": "warning",
                "message": "Security owner evidence is missing.",
                "next_action": "Assign an owner.",
                "node_ids": ["requirement:security", "requirement:omitted"],
            },
            {
                "code": "claim_source_review_needed",
                "severity": "warning",
                "message": "Delivery source needs review.",
                "next_action": "Review the source.",
                "node_ids": ["claim:delivery"],
            },
            {
                "code": "source_metadata_note",
                "severity": "info",
                "message": "Source metadata is available for navigation.",
                "next_action": "",
                "node_ids": ["source:decision-1"],
            }
        ],
        "proposal_blueprint": {
            "status": "available",
            "workflow_status": "slides_approved",
            "narrative_arc": ["Problem", "Recommendation"],
            "slides": [
                {
                    "slide_id": "slide-1",
                    "source_refs": ["procurement:decision-1"],
                    "reference_refs": [],
                    "data_needs": ["Security owner"],
                }
            ],
            "open_questions": ["Confirm owner"],
        },
        "limits": {"max_nodes": 200, "max_edges": 400},
        "truncated": False,
        "authority": {
            "mutation": False,
            "approval": False,
            "export_execution": False,
            "provider_call": False,
            "bid_submission": False,
            "legal_contractual_commitment": False,
        },
    }


def _bounded_map() -> dict:
    result = _map()
    result["nodes"] = [
        {
            "node_id": f"requirement:{index:03d}",
            "node_type": "requirement",
            "label": f"Requirement {index:03d}",
            "status": "current",
            "summary": "Bounded map fixture",
            "evidence_level": "authoritative",
            "relation_count": 2,
            "coverage_status": "explicit",
        }
        for index in range(200)
    ]
    result["edges"] = [
        _edge(
            f"bounded-edge-{index}",
            f"requirement:{index % 200:03d}",
            f"requirement:{(index + 1) % 200:03d}",
            relation_type="related_to",
        )
        for index in range(400)
    ]
    result["nodes"][-1]["label"] = "Requirement 199 selected"
    result["nodes"][-1]["status"] = "missing"
    result["nodes"][-1]["coverage_status"] = "missing"
    result["diagnostics"] = []
    result["coverage"] = {
        "total": 200,
        "explicit": 199,
        "candidate": 0,
        "missing": 1,
        "unverifiable": 0,
        "items": [],
    }
    result["truncated"] = False
    result["projection_fingerprint"] = "b" * 64
    return result


def _surface_node_ids(root, surface: str) -> set[str]:
    return set(
        root.locator(
            f'[data-decision-evidence-node-id][data-decision-evidence-surface="{surface}"]',
        ).evaluate_all(
            "elements => elements.map(element => element.dataset.decisionEvidenceNodeId)",
        )
    )


def test_decision_evidence_map_filter_focus_keyboard_and_mobile_layout(page):
    page.evaluate("switchPage('project-page')")
    page.evaluate(
        """({ project, map }) => {
          renderProjectDetail(project, null, {
            procurementEnabled: true,
            decisionEvidenceMap: map,
          });
          document.getElementById('project-list').style.display = 'none';
          document.getElementById('project-detail').style.display = 'block';
        }""",
        {"project": _project(), "map": _map()},
    )

    root = page.locator("#decision-evidence-map")
    root.wait_for(state="visible")
    assert root.locator(".decision-evidence-node").count() == 7
    assert root.locator(".decision-evidence-table tbody tr").count() == 7
    assert _surface_node_ids(root, "canvas") == _surface_node_ids(root, "table")
    source_row = root.locator(".decision-evidence-table tbody tr", has_text="RFP source")
    assert source_row.locator("td").last.inner_text() == "3 / 3"
    source_detail = root.locator(".decision-evidence-detail")
    assert source_detail.locator(
        "dt",
        has_text="Visible relations",
    ).locator("xpath=following-sibling::dd[1]").inner_text() == "3"
    assert source_detail.locator(
        "dt",
        has_text="Projection relations",
    ).locator("xpath=following-sibling::dd[1]").inner_text() == "3"
    svg = root.locator(".decision-evidence-canvas svg")
    assert svg.get_attribute("aria-hidden") == "true"
    assert svg.get_attribute("focusable") == "false"
    canvas_node = root.locator(
        '[data-decision-evidence-node-id="recommendation:decision-1"]'
        '[data-decision-evidence-surface="canvas"]',
    )
    assert canvas_node.get_attribute("role") is None
    assert canvas_node.get_attribute("tabindex") is None
    assert canvas_node.get_attribute("aria-selected") is None
    assert "RFP source" in root.locator(".decision-evidence-detail").inner_text()
    assert "1" in root.locator(".decision-evidence-metric", has_text="Missing").inner_text()
    assert "Provenance level (not proof or approval)" in root.inner_text()
    assert "does not establish external authenticity" in root.inner_text()
    assert "&lt;Delivery evidence&gt;" in root.locator(
        ".decision-evidence-table",
    ).inner_html()

    line_styles = root.locator(".decision-evidence-edge").evaluate_all(
        """edges => Object.fromEntries(edges.map(edge => [
          edge.dataset.provenanceLevel,
          getComputedStyle(edge).strokeDasharray
            .replaceAll('px', '')
            .replaceAll(',', ' ')
            .trim()
            .replace(/\\s+/g, ' '),
        ]))""",
    )
    assert line_styles == {
        "authoritative": "none",
        "record_binding": "8 4",
        "derived": "2 4",
    }

    root.locator("#decision-evidence-status-filter").select_option("missing")
    assert root.locator(".decision-evidence-table tbody tr").count() == 1
    assert "Security owner" in root.locator(".decision-evidence-detail").inner_text()

    root.locator("#decision-evidence-status-filter").select_option("all")
    recommendation = root.locator(
        '[data-decision-evidence-node-id="recommendation:decision-1"]'
        '[data-decision-evidence-surface="table"]',
    )
    canvas_node.click()
    assert "Proceed after evidence is attached." in root.locator(
        ".decision-evidence-detail",
    ).inner_text()
    assert recommendation.evaluate("element => document.activeElement === element")

    recommendation.focus()
    page.keyboard.press("Enter")
    assert "Proceed after evidence is attached." in root.locator(
        ".decision-evidence-detail",
    ).inner_text()
    assert root.locator('.decision-evidence-node.selected').count() == 1
    assert root.locator('.decision-evidence-node.neighbor').count() >= 1
    assert root.locator('.decision-evidence-node.dimmed').count() >= 1
    assert root.locator('.decision-evidence-edge.focused').count() >= 1
    detail = root.locator(".decision-evidence-detail").inner_text()
    assert "Inbound relations" in detail
    assert "Outbound relations" in detail
    assert "Provenance level" in detail
    assert "Content SHA-256" in detail
    assert "authoritative" in detail
    assert "Source revision" in detail
    assert "council<1>" in detail
    assert "revision<2>" in detail
    assert "consensus.<summary>" in detail
    assert "document<1>" in detail
    inbound_relations = root.locator(
        ".decision-evidence-relations",
        has_text="Inbound relations",
    )
    outbound_relations = root.locator(
        ".decision-evidence-relations",
        has_text="Outbound relations",
    )
    inbound_html = inbound_relations.inner_html()
    outbound_html = outbound_relations.inner_html()
    assert "council&lt;1&gt;" in inbound_html
    assert "consensus.&lt;summary&gt;" in inbound_html
    assert "document&lt;1&gt;" not in inbound_html
    assert "document&lt;1&gt;" in outbound_html
    assert "council&lt;1&gt;" not in outbound_html
    assert recommendation.get_attribute("aria-pressed") == "true"

    claim_button = root.locator(
        '[data-decision-evidence-node-id="claim:delivery"]'
        '[data-decision-evidence-surface="table"]',
    )
    claim_button.focus()
    page.keyboard.press("Space")
    assert "<Delivery evidence>" in root.locator(".decision-evidence-detail").inner_text()
    assert claim_button.get_attribute("aria-pressed") == "true"

    root.locator("#decision-evidence-search").fill("PPTX")
    assert root.locator(".decision-evidence-table tbody tr").count() == 1
    assert "PPTX export readiness" in root.locator(
        ".decision-evidence-detail",
    ).inner_text()

    page.set_viewport_size({"width": 390, "height": 844})
    root_box = root.bounding_box()
    assert root_box is not None
    assert root_box["x"] >= 0
    assert root_box["x"] + root_box["width"] <= 390
    assert root.locator(".decision-evidence-canvas").evaluate(
        "(element) => element.scrollWidth > element.clientWidth",
    )


def test_decision_evidence_map_quick_filters_diagnostic_focus_and_scope_reset(page):
    page.evaluate("switchPage('project-page')")
    page.evaluate(
        """({ project, map }) => {
          renderProjectDetail(project, null, {
            procurementEnabled: true,
            decisionEvidenceMap: map,
          });
          document.getElementById('project-list').style.display = 'none';
          document.getElementById('project-detail').style.display = 'block';
        }""",
        {"project": _project(), "map": _map()},
    )
    root = page.locator("#decision-evidence-map")
    root.locator("#decision-evidence-gaps-filter").check()
    assert "Showing 2 of 7" in root.locator(".decision-evidence-filter-summary").inner_text()
    assert "Security owner" in root.locator(".decision-evidence-table").inner_text()
    assert "<Delivery evidence>" in root.locator(".decision-evidence-table").inner_text()
    assert "Approval" not in root.locator(".decision-evidence-table").inner_text()
    assert "Active filters: gaps only" in root.locator(".decision-evidence-filter-summary").inner_text()

    root.locator("#decision-evidence-gaps-filter").uncheck()
    root.locator("#decision-evidence-status-filter").select_option("missing")
    root.locator('[data-decision-evidence-diagnostic-target="claim:delivery"]').click()
    summary = root.locator(".decision-evidence-filter-summary").inner_text()
    assert "Showing 2 of 7" in summary
    assert "status: missing" in summary
    assert "diagnostic target included" in summary
    assert "<Delivery evidence>" in root.locator(".decision-evidence-detail").inner_text()
    assert "Security owner" in root.locator(".decision-evidence-table").inner_text()
    assert "CONDITIONAL_GO" not in root.locator(".decision-evidence-table").inner_text()
    assert root.locator(
        '[data-decision-evidence-node-id="claim:delivery"]'
        '[data-decision-evidence-surface="table"]',
    ).get_attribute("aria-pressed") == "true"

    root.locator("#decision-evidence-status-filter").select_option("all")
    assert "diagnostic target included" not in root.locator(
        ".decision-evidence-filter-summary",
    ).inner_text()
    root.locator("#decision-evidence-source-filter").uncheck()
    assert "RFP source" not in root.locator(".decision-evidence-table").inner_text()
    assert root.locator('.decision-evidence-edge').count() < 7
    root.locator(
        '[data-decision-evidence-node-id="claim:delivery"]'
        '[data-decision-evidence-surface="table"]',
    ).click()
    source_hidden_detail = root.locator(".decision-evidence-detail").inner_text()
    assert "source:decision-1" not in source_hidden_detail
    assert "states_claim" not in source_hidden_detail
    assert root.locator(
        ".decision-evidence-detail dt",
        has_text="Visible relations",
    ).locator("xpath=following-sibling::dd[1]").inner_text() == "1"
    assert root.locator(
        ".decision-evidence-detail dt",
        has_text="Projection relations",
    ).locator("xpath=following-sibling::dd[1]").inner_text() == "2"
    claim_row = root.locator(".decision-evidence-table tbody tr", has_text="<Delivery evidence>")
    assert claim_row.locator("td").last.inner_text() == "1 / 2"
    assert root.locator(
        '[data-decision-evidence-edge-id="edge-2"]',
    ).count() == 0

    root.locator(
        '[data-decision-evidence-diagnostic-target="source:decision-1"]',
    ).click()
    hidden_source_summary = root.locator(".decision-evidence-filter-summary").inner_text()
    assert "diagnostic source target hidden; enable Show sources" in hidden_source_summary
    assert "RFP source" not in root.locator(".decision-evidence-table").inner_text()
    assert "선택 가능한 evidence node가 없습니다." in root.locator(
        ".decision-evidence-detail",
    ).inner_text()

    root.locator("#decision-evidence-source-filter").check()
    assert "RFP source" in root.locator(".decision-evidence-detail").inner_text()
    assert "diagnostic source target hidden" not in root.locator(
        ".decision-evidence-filter-summary",
    ).inner_text()
    claim_canvas = root.locator(
        '[data-decision-evidence-node-id="claim:delivery"][data-decision-evidence-surface="canvas"]',
    )
    assert claim_canvas.locator("title").text_content() == "<Delivery evidence>"
    assert claim_canvas.get_attribute("aria-label") is None
    root.locator('[data-decision-evidence-diagnostic-target="claim:delivery"]').click()
    assert "<Delivery evidence>" in root.locator(".decision-evidence-detail").inner_text()
    assert "Target omitted from current projection: requirement:omitted" in root.locator(
        ".decision-evidence-diagnostics",
    ).inner_text()

    root.locator("#decision-evidence-lineage-filter").check()
    assert root.locator(".decision-evidence-table tbody tr").count() == 3
    root.locator("[data-decision-evidence-clear-filters]").click()
    assert "Active filters: none" in root.locator(".decision-evidence-filter-summary").inner_text()
    assert root.locator(".decision-evidence-table tbody tr").count() == 7
    root.locator("[data-decision-evidence-presentation-toggle]").click()
    assert root.evaluate("element => element.classList.contains('presentation-mode')")

    page.evaluate(
        """({ project, map }) => {
          map.projection_fingerprint = 'c'.repeat(64);
          renderProjectDetail(project, null, {
            procurementEnabled: true,
            decisionEvidenceMap: map,
          });
        }""",
        {"project": _project(), "map": _map()},
    )
    assert root.locator("#decision-evidence-lineage-filter").is_checked() is False
    assert root.locator("#decision-evidence-source-filter").is_checked() is True
    assert root.locator(".decision-evidence-filter-summary").inner_text().endswith("Active filters: none")
    assert root.evaluate("element => !element.classList.contains('presentation-mode')")

    root.locator("#decision-evidence-search").fill("PPTX")
    page.evaluate(
        """({ project, map }) => {
          _currentTenantId = 'scope-reset-tenant';
          _currentUser = { ..._currentUser, sub: 'scope-reset-user' };
          _authSessionRevision += 1;
          map.bundle_type = 'rfp_analysis_kr';
          renderProjectDetail(project, null, {
            procurementEnabled: true,
            decisionEvidenceMap: map,
          });
        }""",
        {"project": _project(), "map": _map()},
    )
    assert root.locator("#decision-evidence-search").input_value() == ""
    assert root.locator(".decision-evidence-filter-summary").inner_text().endswith("Active filters: none")


def test_decision_evidence_map_bounds_focus_accessibility_and_presentation(page):
    page.evaluate("switchPage('project-page')")
    page.evaluate(
        """({ project, map }) => {
          renderProjectDetail(project, null, {
            procurementEnabled: true,
            decisionEvidenceMap: map,
          });
          document.getElementById('project-list').style.display = 'none';
          document.getElementById('project-detail').style.display = 'block';
        }""",
        {"project": _project(), "map": _bounded_map()},
    )
    root = page.locator("#decision-evidence-map")
    assert root.locator(".decision-evidence-node").count() == 60
    assert root.locator(".decision-evidence-table tbody tr").count() == 200
    assert _surface_node_ids(root, "canvas") <= _surface_node_ids(root, "table")
    assert len(_surface_node_ids(root, "table")) == 200
    assert "Backend projection limit" not in root.inner_text()

    last_row = root.locator(
        '[data-decision-evidence-node-id="requirement:199"]'
        '[data-decision-evidence-surface="table"]',
    )
    last_row.click()
    assert root.locator('[data-decision-evidence-node-id="requirement:199"][data-decision-evidence-surface="canvas"]').count() == 1
    assert last_row.get_attribute("aria-pressed") == "true"
    assert last_row.evaluate(
        "element => document.activeElement === element",
    )

    root.locator("[data-decision-evidence-presentation-toggle]").click()
    assert root.evaluate("element => element.classList.contains('presentation-mode')")
    assert "READ ONLY" in root.inner_text()
    assert "NON-ATOMIC" in root.inner_text()

    page.set_viewport_size({"width": 390, "height": 844})
    assert root.evaluate("element => element.classList.contains('presentation-mode')")
    assert page.evaluate("document.body.scrollWidth <= window.innerWidth")
    root_box = root.bounding_box()
    assert root_box is not None
    assert root_box["x"] >= 0
    assert root_box["x"] + root_box["width"] <= 390
    assert len(
        root.locator(".decision-evidence-layout").evaluate(
            "element => getComputedStyle(element).gridTemplateColumns.split(' ')",
        )
    ) == 1

    page.evaluate(
        """() => {
          const outside = document.createElement('button');
          outside.id = 'decision-evidence-outside-focus';
          outside.textContent = 'Outside';
          document.body.appendChild(outside);
          outside.focus();
        }"""
    )
    assert page.locator("#decision-evidence-outside-focus").evaluate(
        "element => document.activeElement === element",
    )
    page.keyboard.press("Escape")
    assert root.evaluate("element => !element.classList.contains('presentation-mode')")


def test_decision_evidence_map_reduced_motion_uses_computed_media_styles(page):
    page.emulate_media(reduced_motion="no-preference")
    page.evaluate("switchPage('project-page')")
    page.evaluate(
        """({ project, map }) => {
          renderProjectDetail(project, null, {
            procurementEnabled: true,
            decisionEvidenceMap: map,
          });
          document.getElementById('project-list').style.display = 'none';
          document.getElementById('project-detail').style.display = 'block';
        }""",
        {"project": _project(), "map": _map()},
    )
    root = page.locator("#decision-evidence-map")
    node_rect = root.locator(".decision-evidence-node rect").first
    edge = root.locator(".decision-evidence-edge").first
    assert node_rect.evaluate("element => getComputedStyle(element).transitionDuration") != "0s"
    assert edge.evaluate("element => getComputedStyle(element).transitionDuration") != "0s"

    page.emulate_media(reduced_motion="reduce")
    assert node_rect.evaluate("element => getComputedStyle(element).transitionDuration") == "0s"
    assert edge.evaluate("element => getComputedStyle(element).transitionDuration") == "0s"
