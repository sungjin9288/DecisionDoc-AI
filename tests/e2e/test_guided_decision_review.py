from __future__ import annotations


def _project() -> dict:
    return {
        "project_id": "guided-review-project",
        "name": "Guided review fixture",
        "description": "",
        "client": "DecisionDoc",
        "contract_number": "",
        "fiscal_year": 2026,
        "status": "active",
        "created_at": "2026-07-27T00:00:00Z",
        "documents": [],
        "meeting_recordings": [],
    }


def _diagnostic(code: str, severity: str = "warning") -> dict:
    return {
        "code": code,
        "severity": severity,
        "message": f"{code} requires review.",
        "node_ids": ["recommendation:1"],
        "next_action": "Inspect the current project evidence.",
    }


def _map(**overrides: object) -> dict:
    result = {
        "contract_version": "decision_evidence_map.v1",
        "generated_at": "2026-07-27T09:00:00Z",
        "project_id": "guided-review-project",
        "bundle_type": "proposal_kr",
        "read_only": True,
        "snapshot_atomic": False,
        "projection_fingerprint": "a" * 64,
        "source_revisions": [],
        "nodes": [
            {
                "node_id": "requirement:1",
                "node_type": "requirement",
                "label": "Required capability",
                "status": "current",
                "summary": "",
                "updated_at": "2026-07-27T09:00:00Z",
                "relation_count": 0,
                "evidence_level": "authoritative",
                "coverage_status": "explicit",
                "diagnostic_codes": [],
                "actual_export_observed": False,
            },
            {
                "node_id": "recommendation:1",
                "node_type": "recommendation",
                "label": "GO",
                "status": "current",
                "summary": "",
                "updated_at": "2026-07-27T09:00:00Z",
                "relation_count": 0,
                "evidence_level": "authoritative",
                "coverage_status": None,
                "diagnostic_codes": [],
                "actual_export_observed": False,
            },
        ],
        "edges": [],
        "coverage": {
            "total": 1,
            "explicit": 1,
            "candidate": 0,
            "missing": 0,
            "unverifiable": 0,
            "items": [
                {
                    "requirement_node_id": "requirement:1",
                    "status": "explicit",
                    "summary": "",
                    "evidence_refs": ["document:proposal-a"],
                }
            ],
        },
        "diagnostics": [],
        "limits": {"max_nodes": 200, "max_edges": 400},
        "truncated": False,
        "proposal_blueprint": {
            "status": "not_observed",
            "report_workflow_id": None,
            "workflow_status": "",
            "narrative_arc": [],
            "source_refs": [],
            "slides": [],
            "open_questions": [],
            "risk_notes": [],
            "actual_export_observed": False,
        },
        "authority": {
            "mutation": False,
            "approval": False,
            "export_execution": False,
            "provider_call": False,
            "bid_submission": False,
            "legal_contractual_commitment": False,
        },
    }
    coverage = overrides.pop("coverage", None)
    result.update(overrides)
    if isinstance(coverage, dict):
        result["coverage"].update(coverage)
    return result


def _decision(**overrides: object) -> dict:
    result = {
        "opportunity": {"title": "Opportunity"},
        "recommendation": {"value": "GO"},
        "hard_filters": [],
        "missing_data": [],
        "checklist_items": [],
        "notes": "",
    }
    result.update(overrides)
    return result


def _review(prepared_at: str, packet_sha256: str, *, status: str = "completed", decision: str = "accepted") -> dict:
    return {
        "prepared_at": prepared_at,
        "packet_sha256": packet_sha256,
        "review_status": status,
        "decision": decision,
    }


def _document(doc_id: str, generated_at: str, **overrides: object) -> dict:
    result = {
        "doc_id": doc_id,
        "bundle_id": "proposal_kr",
        "title": "Proposal",
        "generated_at": generated_at,
        "procurement_review_document_status": "current",
        "decision_council_document_status": "current",
    }
    result.update(overrides)
    return result


def _render(page, *, decision=None, reviews=None, council=None, docs=None, evidence_map="default"):
    project = _project()
    project["documents"] = docs or []
    page.evaluate(
        """({ project, decision, reviews, council, map }) => {
          renderProjectDetail(project, decision, {
            procurementEnabled: true,
            procurementReviews: reviews,
            decisionCouncilSession: council,
            decisionEvidenceMap: map,
          });
          document.getElementById('project-list').style.display = 'none';
          document.getElementById('project-detail').style.display = 'block';
        }""",
        {
            "project": project,
            "decision": decision if decision is not None else _decision(),
            "reviews": reviews or [],
            "council": council,
            "map": _map() if evidence_map == "default" else evidence_map,
        },
    )


def _stage(root, name: str):
    return root.locator(f'[data-guided-review-stage="{name}"]')


def test_guided_review_precedence_matrix_and_latest_tie_break(page):
    page.evaluate("switchPage('project-page')")
    base_docs = [_document("proposal-a", "2026-07-26T10:00:00Z")]
    scenarios = [
        ({"truncated": True}, _decision(), [], base_docs, "Evidence", "Needs review"),
        ({"diagnostics": [_diagnostic("projection_error", "error")]}, _decision(), [], base_docs, "Evidence", "Needs review"),
        (
            {"diagnostics": [_diagnostic("projection_error", "error")]},
            _decision(),
            [_review("2026-07-27T09:00:00Z", "a" * 64, status="pending", decision="")],
            base_docs,
            "Evidence",
            "Needs review",
        ),
        ({}, _decision(opportunity=None), [], base_docs, "Decision", "Needs review"),
        ({}, _decision(hard_filters=[{"blocking": True, "status": "fail"}]), [], base_docs, "Decision", "Needs review"),
        (
            {
                "coverage": {
                    "explicit": 0,
                    "missing": 1,
                    "items": [
                        {
                            "requirement_node_id": "requirement:1",
                            "status": "missing",
                            "summary": "",
                            "evidence_refs": [],
                        }
                    ],
                }
            },
            _decision(),
            [],
            base_docs,
            "Decision",
            "Needs review",
        ),
        ({}, _decision(recommendation={"value": "NO_GO"}), [], base_docs, "Decision", "Needs review"),
        ({}, _decision(), [_review("2026-07-27T09:00:00Z", "a" * 64, status="pending", decision="")], base_docs, "Review", "Review in progress"),
        ({}, _decision(), [_review("2026-07-27T09:00:00Z", "a" * 64, decision="changes_requested")], base_docs, "Review", "Needs review"),
        ({}, _decision(), [], base_docs, "Review", "Needs review"),
        ({}, _decision(), [_review("2026-07-27T09:00:00Z", "a" * 64)], [], "Documents", "Needs review"),
        ({}, _decision(), [_review("2026-07-27T09:00:00Z", "a" * 64)], [_document("proposal-a", "2026-07-26T10:00:00Z", provenance_status="stale")], "Documents", "Needs review"),
        ({"diagnostics": [_diagnostic("coverage_warning")]}, _decision(), [_review("2026-07-27T09:00:00Z", "a" * 64)], base_docs, "Evidence", "Needs review"),
        ({"diagnostics": [_diagnostic("export_evidence_not_observed", "error")]}, _decision(), [_review("2026-07-27T09:00:00Z", "a" * 64)], base_docs, "Evidence", "Needs review"),
        ({}, _decision(), [_review("2026-07-27T09:00:00Z", "a" * 64)], base_docs, "Evidence", "No blocking signal observed"),
    ]

    for map_changes, decision, reviews, docs, expected_stage, expected_state in scenarios:
        evidence_map = _map(**map_changes)
        _render(page, decision=decision, reviews=reviews, docs=docs, evidence_map=evidence_map)
        root = page.locator("#guided-decision-review")
        assert root.locator("strong", has_text="Overall state:").locator("xpath=..").inner_text().endswith(expected_state)
        assert root.locator("strong", has_text="Recommended next check:").locator("xpath=..").inner_text().startswith(
            f"Recommended next check: {expected_stage}"
        )
        assert "_" not in _stage(root, expected_stage).locator(
            ".guided-decision-review-status"
        ).inner_text()

    evidence_map = _map()
    evidence_map["truncated"] = True
    _render(
        page,
        reviews=[
            _review(
                "2026-07-27T09:00:00Z",
                "a" * 64,
                status="pending",
                decision="",
            )
        ],
        docs=base_docs,
        evidence_map=evidence_map,
    )
    root = page.locator("#guided-decision-review")
    assert "Overall state: Needs review" in root.inner_text()

    _render(
        page,
        reviews=[_review("2026-07-27T09:00:00Z", "a" * 64)],
        docs=base_docs,
        council={"current_procurement_binding_status": "stale"},
    )
    root = page.locator("#guided-decision-review")
    assert _stage(root, "Decision").get_attribute("data-guided-review-status") == "needs_attention"
    assert "Council binding" in root.inner_text()

    _render(
        page,
        reviews=[_review("2026-07-27T09:00:00Z", "a" * 64)],
        docs=base_docs,
        council={
            "source_procurement_recommendation_value": "GO",
            "current_procurement_recommendation_value": "NO_GO",
        },
    )
    root = page.locator("#guided-decision-review")
    assert _stage(root, "Decision").get_attribute("data-guided-review-status") == "needs_attention"
    assert "recommendation conflict" in root.inner_text()

    _render(
        page,
        reviews=[_review("2026-07-27T09:00:00Z", "a" * 64)],
        docs=base_docs,
        evidence_map=_map(diagnostics=[_diagnostic("council_binding_stale")]),
    )
    root = page.locator("#guided-decision-review")
    assert "Recommended next check: Decision" in root.inner_text()
    assert "Council binding" in root.inner_text()

    _render(
        page,
        decision=_decision(
            recommendation={"value": "NO_GO"},
            notes=(
                "[override_reason ts=2026-07-27T09:00:00Z actor=reviewer]\n"
                "Documented exception context\n"
                "[/override_reason]"
            ),
        ),
        reviews=[_review("2026-07-27T09:00:00Z", "a" * 64)],
        docs=base_docs,
    )
    root = page.locator("#guided-decision-review")
    assert "NO_GO exception record observed" in _stage(root, "Decision").inner_text()

    tied_reviews = [
        _review("2026-07-27T09:00:00Z", "a" * 64, decision="accepted"),
        _review("2026-07-27T09:00:00Z", "b" * 64, decision="rejected"),
    ]
    _render(page, reviews=tied_reviews, docs=base_docs)
    root = page.locator("#guided-decision-review")
    assert _stage(root, "Review").get_attribute("data-guided-review-status") == "needs_attention"
    assert "latest review outcome" in root.inner_text()

    _render(
        page,
        reviews=[_review("2026-07-27T09:00:00Z", "a" * 64)],
        docs=[
            _document("proposal-a", "2026-07-26T10:00:00Z"),
            _document("proposal-b", "2026-07-26T10:00:00Z", provenance_status="invalid"),
        ],
    )
    root = page.locator("#guided-decision-review")
    assert _stage(root, "Documents").get_attribute("data-guided-review-status") == "needs_attention"
    assert "document status requires review" in root.inner_text()

    _render(
        page,
        reviews=[_review("2026-07-27T09:00:00Z", "a" * 64)],
        docs=[
            _document(
                "proposal-a",
                "2026-07-26T10:00:00Z",
                procurement_review_document_status="review_evidence_missing",
            )
        ],
    )
    root = page.locator("#guided-decision-review")
    assert _stage(root, "Documents").get_attribute("data-guided-review-status") == "needs_attention"
    assert "review_evidence_missing" in root.inner_text()

    _render(
        page,
        reviews=[_review("2026-07-27T09:00:00Z", "a" * 64)],
        docs=[
            _document(
                "proposal-a",
                "2026-07-26T10:00:00Z",
                procurement_review_document_status="",
                decision_council_document_status="",
            )
        ],
    )
    root = page.locator("#guided-decision-review")
    assert _stage(root, "Documents").get_attribute("data-guided-review-status") == "needs_attention"
    assert "current document provenance not observed" in root.inner_text()


def test_guided_review_fails_closed_and_navigation_stays_local(page):
    page.evaluate("switchPage('project-page')")
    invalid_map = _map()
    invalid_map["authority"]["approval"] = True
    _render(page, evidence_map=invalid_map)
    assert page.locator("#guided-decision-review").count() == 0

    invalid_map = _map()
    invalid_map["authority"]["future_execution"] = False
    _render(page, evidence_map=invalid_map)
    assert page.locator("#guided-decision-review").count() == 0

    invalid_map = _map()
    invalid_map.pop("coverage")
    _render(page, evidence_map=invalid_map)
    assert page.locator("#guided-decision-review").count() == 0

    invalid_map = _map()
    invalid_map.pop("truncated")
    _render(page, evidence_map=invalid_map)
    assert page.locator("#guided-decision-review").count() == 0

    invalid_map = _map()
    invalid_map.pop("generated_at")
    _render(page, evidence_map=invalid_map)
    assert page.locator("#guided-decision-review").count() == 0

    invalid_map = _map()
    invalid_map["nodes"][0].pop("summary")
    _render(page, evidence_map=invalid_map)
    assert page.locator("#guided-decision-review").count() == 0

    invalid_map = _map()
    invalid_map["coverage"]["total"] = 2
    _render(page, evidence_map=invalid_map)
    assert page.locator("#guided-decision-review").count() == 0

    _render(page, evidence_map=None)
    assert page.locator("#guided-decision-review").count() == 0

    _render(page, reviews=[_review("2026-07-27T09:00:00Z", "a" * 64)], docs=[_document("proposal-a", "2026-07-26T10:00:00Z")])
    root = page.locator("#guided-decision-review")
    requests = []
    page.on("request", lambda request: requests.append(request.url))
    root.get_by_role("button", name="Inspect Documents").click()
    target = page.locator("#project-documents-heading")
    assert target.evaluate("element => document.activeElement === element")
    assert "Moved to Documents." in root.locator("#guided-decision-review-announcement").inner_text()
    assert requests == []


def test_guided_review_uses_the_session_bound_project_loading_path(page):
    page.evaluate("switchPage('project-page')")
    project = _project()
    project["documents"] = [_document("proposal-a", "2026-07-26T10:00:00Z")]
    responses = {
        f"/projects/{project['project_id']}": project,
        f"/projects/{project['project_id']}/procurement": {"decision": _decision()},
        f"/projects/{project['project_id']}/procurement/reviews": {
            "reviews": [_review("2026-07-27T09:00:00Z", "a" * 64)]
        },
        f"/projects/{project['project_id']}/decision-council": None,
        (
            f"/projects/{project['project_id']}/decision-evidence-map"
            "?bundle_type=proposal_kr"
        ): _map(),
    }
    page.evaluate(
        """responses => {
          window.__guidedReviewOriginalFetch = window.fetch;
          window.__guidedReviewObservedRequests = [];
          window.fetch = async (input, init = {}) => {
            const url = String(input);
            if (!Object.prototype.hasOwnProperty.call(responses, url)) {
              throw new Error(`Unexpected Guided Review request: ${url}`);
            }
            const headers = new Headers(init.headers || {});
            window.__guidedReviewObservedRequests.push({
              url,
              authorization: headers.get('Authorization') || '',
            });
            return new Response(JSON.stringify(responses[url]), {
              status: 200,
              headers: { 'Content-Type': 'application/json' },
            });
          };
        }""",
        responses,
    )

    page.evaluate(
        """async projectId => {
          try {
            await loadProjectDetail(projectId);
          } finally {
            window.fetch = window.__guidedReviewOriginalFetch;
            delete window.__guidedReviewOriginalFetch;
          }
        }""",
        project["project_id"],
    )

    root = page.locator("#guided-decision-review")
    root.wait_for()
    assert "Overall state: No blocking signal observed" in root.inner_text()
    observed_requests = page.evaluate("window.__guidedReviewObservedRequests")
    assert [item["url"] for item in observed_requests] == list(responses)
    assert all(
        item["authorization"].startswith("Bearer ")
        for item in observed_requests
    )


def test_guided_review_accepts_the_real_decision_evidence_response(page):
    page.evaluate("switchPage('project-page')")
    result = page.evaluate(
        """async () => {
          const headers = { ...getAuthHeaders(), 'Content-Type': 'application/json' };
          const projectResponse = await fetch('/projects', {
            method: 'POST',
            headers,
            body: JSON.stringify({
              name: 'Guided review contract fixture',
              fiscal_year: 2026,
            }),
          });
          if (!projectResponse.ok) {
            throw new Error(`project create failed: ${projectResponse.status}`);
          }
          const project = await projectResponse.json();
          const evidenceResponse = await fetch(
            `/projects/${project.project_id}/decision-evidence-map?bundle_type=proposal_kr`,
            { headers: getAuthHeaders() },
          );
          if (!evidenceResponse.ok) {
            throw new Error(`evidence map failed: ${evidenceResponse.status}`);
          }
          const map = await evidenceResponse.json();
          renderProjectDetail(project, null, {
            procurementEnabled: true,
            procurementReviews: [],
            decisionCouncilSession: null,
            decisionEvidenceMap: map,
          });
          document.getElementById('project-list').style.display = 'none';
          document.getElementById('project-detail').style.display = 'block';
          return {
            contractVersion: map.contract_version,
            projectId: map.project_id,
            rendered: Boolean(document.getElementById('guided-decision-review')),
          };
        }"""
    )

    assert result["contractVersion"] == "decision_evidence_map.v1"
    assert result["projectId"]
    assert result["rendered"] is True
    assert "Recommended next check: Decision" in page.locator(
        "#guided-decision-review"
    ).inner_text()


def test_guided_review_reduced_motion_and_mobile_layout(page):
    page.emulate_media(reduced_motion="reduce")
    page.evaluate("switchPage('project-page')")
    _render(page, reviews=[_review("2026-07-27T09:00:00Z", "a" * 64)], docs=[_document("proposal-a", "2026-07-26T10:00:00Z")])
    root = page.locator("#guided-decision-review")
    page.evaluate(
        """() => {
          window.__guidedScrollBehavior = '';
          const original = Element.prototype.scrollIntoView;
          Element.prototype.scrollIntoView = function(options) {
            window.__guidedScrollBehavior = options.behavior;
            return original.call(this, options);
          };
        }"""
    )
    root.get_by_role("button", name="Inspect Evidence").click()
    assert page.evaluate("window.__guidedScrollBehavior") == "auto"
    assert page.locator("#decision-evidence-map").evaluate(
        "element => document.activeElement === element",
    )

    page.set_viewport_size({"width": 390, "height": 844})
    assert page.evaluate("document.body.scrollWidth <= window.innerWidth")
    assert len(root.locator(".guided-decision-review-steps").evaluate(
        "element => getComputedStyle(element).gridTemplateColumns.split(' ')",
    )) == 1
    assert root.locator(".guided-decision-review-steps button").evaluate_all(
        "buttons => buttons.every(button => button.offsetWidth === button.parentElement.clientWidth - 24)",
    )
