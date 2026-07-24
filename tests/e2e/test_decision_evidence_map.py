from __future__ import annotations


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
        {
            "edge_id": f"edge-{index}",
            "source_node_id": source,
            "target_node_id": target,
        }
        for index, (source, target) in enumerate(
            (
                ("source:decision-1", "requirement:security"),
                ("source:decision-1", "recommendation:decision-1"),
                ("recommendation:decision-1", "document:proposal-1"),
                ("approval:approval-1", "document:proposal-1"),
                ("document:proposal-1", "export:workflow-1:pptx:1"),
            )
        )
    ]
    return {
        "contract_version": "decision_evidence_map.v1",
        "project_id": "evidence-ui-project",
        "bundle_type": "proposal_kr",
        "read_only": True,
        "snapshot_atomic": False,
        "projection_fingerprint": "a" * 64,
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
        "truncated": False,
    }


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
    assert root.locator(".decision-evidence-node").count() == 6
    assert root.locator(".decision-evidence-table tbody tr").count() == 6
    assert "RFP source" in root.locator(".decision-evidence-detail").inner_text()
    assert "1" in root.locator(".decision-evidence-metric", has_text="Missing").inner_text()

    root.locator("#decision-evidence-status-filter").select_option("missing")
    assert root.locator(".decision-evidence-table tbody tr").count() == 1
    assert "Security owner" in root.locator(".decision-evidence-detail").inner_text()

    root.locator("#decision-evidence-status-filter").select_option("all")
    recommendation = root.locator(
        '[data-decision-evidence-node-id="recommendation:decision-1"]',
    ).first
    recommendation.focus()
    page.keyboard.press("Enter")
    assert "Proceed after evidence is attached." in root.locator(
        ".decision-evidence-detail",
    ).inner_text()

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
