from __future__ import annotations

import hashlib
import json


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


def _handoff(**overrides: object) -> dict:
    result = {
        "contract_version": "guided-decision-review-handoff.v1",
        "source_contract_version": "decision_evidence_map.v1",
        "source_generated_at": "2026-07-28T00:00:00Z",
        "project_id": "guided-review-project",
        "bundle_type": "proposal_kr",
        "projection_fingerprint": "a" * 64,
        "read_only": True,
        "snapshot_atomic": False,
        "requires_recheck_before_reliance": True,
        "handoff_persisted": False,
        "overall_state": "No blocking signal observed",
        "recommended_next_check": {
            "stage": "Evidence",
            "instruction": "Inspect the evidence overview.",
        },
        "stages": [
            {"name": "Decision", "status": "observed", "evidence": "Decision observed."},
            {"name": "Evidence", "status": "observed", "evidence": "Evidence observed."},
            {"name": "Review", "status": "observed", "evidence": "Review observed."},
            {"name": "Documents", "status": "observed", "evidence": "Document observed."},
        ],
        "authority": {
            "mutation": False,
            "approval": False,
            "export_execution": False,
            "provider_call": False,
            "bid_submission": False,
            "legal_contractual_commitment": False,
        },
    }
    result.update(overrides)
    return result


def _handoff_body(payload: dict) -> bytes:
    return (
        json.dumps(
            payload,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        + b"\n"
    )


def _review_state_fingerprint(payload: dict) -> str:
    stable = json.loads(json.dumps(payload))
    stable.pop("source_generated_at")
    return hashlib.sha256(
        json.dumps(
            stable,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _recheck_receipt(
    source: dict,
    current: dict,
    *,
    status: str | None = None,
) -> dict:
    source_body = _handoff_body(source)
    current_body = _handoff_body(current)
    source_fingerprint = _review_state_fingerprint(source)
    current_fingerprint = _review_state_fingerprint(current)
    return {
        "contract_version": "guided-decision-review-recheck-receipt.v1",
        "source_handoff": source,
        "source_handoff_sha256": hashlib.sha256(source_body).hexdigest(),
        "current_handoff": current,
        "current_handoff_sha256": hashlib.sha256(current_body).hexdigest(),
        "source_review_state_fingerprint_sha256": source_fingerprint,
        "current_review_state_fingerprint_sha256": current_fingerprint,
        "review_state_status": status or (
            "unchanged" if source_fingerprint == current_fingerprint else "changed"
        ),
        "fingerprint_algorithm": "sha256",
        "volatile_fields_excluded": ["source_generated_at"],
        "review_state_only": True,
        "review_only": True,
        "read_only": True,
        "snapshot_atomic": False,
        "requires_recheck_before_reliance": True,
        "recheck_persisted": False,
        "authority": source["authority"],
    }


def _disposition_receipt(
    source_recheck_receipt: dict,
    review_disposition: str,
) -> dict:
    source_body = _handoff_body(source_recheck_receipt)
    current = source_recheck_receipt["current_handoff"]
    binding = {
        "project_id": current["project_id"],
        "bundle_type": current["bundle_type"],
        "source_recheck_receipt_sha256": hashlib.sha256(source_body).hexdigest(),
        "current_handoff_sha256": source_recheck_receipt[
            "current_handoff_sha256"
        ],
        "current_review_state_fingerprint_sha256": source_recheck_receipt[
            "current_review_state_fingerprint_sha256"
        ],
        "review_state_status": source_recheck_receipt["review_state_status"],
        "review_disposition": review_disposition,
    }
    binding_sha256 = hashlib.sha256(
        json.dumps(
            binding,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    return {
        "contract_version": "guided-decision-review-disposition-receipt.v1",
        "project_id": current["project_id"],
        "bundle_type": current["bundle_type"],
        "source_recheck_receipt": source_recheck_receipt,
        "source_recheck_receipt_sha256": hashlib.sha256(source_body).hexdigest(),
        "current_handoff_sha256": source_recheck_receipt[
            "current_handoff_sha256"
        ],
        "current_review_state_fingerprint_sha256": source_recheck_receipt[
            "current_review_state_fingerprint_sha256"
        ],
        "review_state_status": source_recheck_receipt["review_state_status"],
        "review_disposition": review_disposition,
        "disposition_binding_sha256": binding_sha256,
        "receipt_status": "issued",
        "review_state_only": True,
        "review_only": True,
        "read_only": True,
        "reviewer_identity_bound": False,
        "snapshot_atomic": False,
        "requires_recheck_before_reliance": True,
        "disposition_receipt_persisted": False,
        "authority": current["authority"],
    }


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
    with page.expect_download() as download_info:
        page.get_by_role(
            "button",
            name="Download guided decision review handoff JSON",
        ).click()
    assert download_info.value.suggested_filename.startswith(
        "guided-decision-review-handoff-"
    )
    assert "Verified review handoff download started." in page.locator(
        "#guided-decision-review-announcement"
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


def test_guided_review_handoff_downloads_only_after_exact_verification(page):
    page.evaluate("switchPage('project-page')")
    payload = _handoff()
    body = _handoff_body(payload)
    page.evaluate(
        """({ body, bodySha256 }) => {
          window.__guidedReviewOriginalFetch = window.fetch;
          window.__guidedReviewObservedHeaders = [];
          window.fetch = async (input, init = {}) => {
            const url = String(input);
            if (!url.includes('/guided-decision-review-handoff?')) {
              return window.__guidedReviewOriginalFetch(input, init);
            }
            const requestHeaders = new Headers(init.headers || {});
            window.__guidedReviewObservedHeaders.push({
              authorization: requestHeaders.get('Authorization') || '',
            });
            return new Response(body, {
              status: 200,
              headers: {
                'Cache-Control': 'no-store',
                'Content-Type': 'application/json; charset=utf-8',
                'Content-Disposition': 'attachment; filename="guided-decision-review-handoff-aaaaaaaaaaaa.json"',
                'X-Content-Type-Options': 'nosniff',
                'X-DecisionDoc-Guided-Review-Handoff-SHA256': bodySha256,
                'X-DecisionDoc-Projection-Fingerprint': 'a'.repeat(64),
                'X-DecisionDoc-Operational-Approval': 'false',
              },
            });
          };
        }""",
        {
            "body": body.decode("utf-8"),
            "bodySha256": hashlib.sha256(body).hexdigest(),
        },
    )
    _render(
        page,
        reviews=[_review("2026-07-27T09:00:00Z", "a" * 64)],
        docs=[_document("proposal-a", "2026-07-26T10:00:00Z")],
    )
    root = page.locator("#guided-decision-review")
    with page.expect_download() as download_info:
        root.get_by_role(
            "button",
            name="Download guided decision review handoff JSON",
        ).click()
    download = download_info.value

    assert download.suggested_filename == (
        "guided-decision-review-handoff-aaaaaaaaaaaa.json"
    )
    observed_headers = page.evaluate("window.__guidedReviewObservedHeaders")
    assert observed_headers
    assert observed_headers[0]["authorization"].startswith("Bearer ")
    assert "Verified review handoff download started." in root.locator(
        "#guided-decision-review-announcement"
    ).inner_text()


def test_guided_review_handoff_rejects_payload_fingerprint_drift(page):
    page.evaluate("switchPage('project-page')")
    payload = _handoff(projection_fingerprint="b" * 64)
    body = _handoff_body(payload)
    page.evaluate(
        """({ body, bodySha256 }) => {
          window.__guidedReviewOriginalFetch = window.fetch;
          window.fetch = async (input, init = {}) => {
            const url = String(input);
            if (!url.includes('/guided-decision-review-handoff?')) {
              return window.__guidedReviewOriginalFetch(input, init);
            }
            return new Response(body, {
              status: 200,
              headers: {
                'Cache-Control': 'no-store',
                'Content-Type': 'application/json; charset=utf-8',
                'Content-Disposition': 'attachment; filename="guided-decision-review-handoff-aaaaaaaaaaaa.json"',
                'X-Content-Type-Options': 'nosniff',
                'X-DecisionDoc-Guided-Review-Handoff-SHA256': bodySha256,
                'X-DecisionDoc-Projection-Fingerprint': 'a'.repeat(64),
                'X-DecisionDoc-Operational-Approval': 'false',
              },
            });
          };
        }""",
        {
            "body": body.decode("utf-8"),
            "bodySha256": hashlib.sha256(body).hexdigest(),
        },
    )
    _render(
        page,
        reviews=[_review("2026-07-27T09:00:00Z", "a" * 64)],
        docs=[_document("proposal-a", "2026-07-26T10:00:00Z")],
    )
    page.evaluate(
        """() => {
          window.__guidedReviewDownloadCalls = 0;
          window.__guidedReviewOriginalDownload = window._triggerBrowserDownload;
          window._triggerBrowserDownload = () => {
            window.__guidedReviewDownloadCalls += 1;
          };
        }"""
    )
    root = page.locator("#guided-decision-review")
    root.get_by_role(
        "button",
        name="Download guided decision review handoff JSON",
    ).click()
    root.locator("#guided-decision-review-announcement").filter(
        has_text="contract verification failed"
    ).wait_for()

    assert page.evaluate("window.__guidedReviewDownloadCalls") == 0


def test_guided_review_recheck_downloads_verified_unchanged_receipt(page):
    page.evaluate("switchPage('project-page')")
    source = _handoff()
    current = _handoff(source_generated_at="2026-07-28T01:00:00Z")
    changed_current = _handoff(
        source_generated_at="2026-07-28T02:00:00Z",
        projection_fingerprint="b" * 64,
    )
    for handoff in (source, current, changed_current):
        handoff["stages"][0]["evidence"] = "검토 필요 😀"
    source_body = _handoff_body(source)
    receipt = _recheck_receipt(source, current)
    receipt_body = _handoff_body(receipt)
    changed_receipt = _recheck_receipt(source, changed_current)
    changed_receipt_body = _handoff_body(changed_receipt)
    page.evaluate(
        """({
          sourceBody, sourceSha256, receiptBody, receiptSha256,
          changedReceiptBody, changedReceiptSha256,
        }) => {
          window.__guidedReviewOriginalFetch = window.fetch;
          window.__guidedReviewRecheckRequests = [];
          window.__guidedReviewUseChangedReceipt = false;
          window.fetch = async (input, init = {}) => {
            const url = String(input);
            if (url.includes('/guided-decision-review-handoff/recheck')) {
              window.__guidedReviewRecheckRequests.push(JSON.parse(init.body));
              const changed = window.__guidedReviewUseChangedReceipt;
              return new Response(changed ? changedReceiptBody : receiptBody, {
                status: 200,
                headers: {
                  'Cache-Control': 'no-store',
                  'Content-Type': 'application/json; charset=utf-8',
                  'Content-Disposition': changed
                    ? 'attachment; filename="guided-decision-review-recheck-receipt-bbbbbbbbbbbb.json"'
                    : 'attachment; filename="guided-decision-review-recheck-receipt-aaaaaaaaaaaa.json"',
                  'X-Content-Type-Options': 'nosniff',
                  'X-DecisionDoc-Guided-Review-Recheck-Receipt-SHA256': changed
                    ? changedReceiptSha256
                    : receiptSha256,
                  'X-DecisionDoc-Projection-Fingerprint': changed
                    ? 'b'.repeat(64)
                    : 'a'.repeat(64),
                  'X-DecisionDoc-Review-State-Status': changed
                    ? 'changed'
                    : 'unchanged',
                  'X-DecisionDoc-Operational-Approval': 'false',
                },
              });
            }
            if (url.includes('/guided-decision-review-handoff?')) {
              return new Response(sourceBody, {
                status: 200,
                headers: {
                  'Cache-Control': 'no-store',
                  'Content-Type': 'application/json; charset=utf-8',
                  'Content-Disposition': 'attachment; filename="guided-decision-review-handoff-aaaaaaaaaaaa.json"',
                  'X-Content-Type-Options': 'nosniff',
                  'X-DecisionDoc-Guided-Review-Handoff-SHA256': sourceSha256,
                  'X-DecisionDoc-Projection-Fingerprint': 'a'.repeat(64),
                  'X-DecisionDoc-Operational-Approval': 'false',
                },
              });
            }
            return window.__guidedReviewOriginalFetch(input, init);
          };
        }""",
        {
            "sourceBody": source_body.decode("utf-8"),
            "sourceSha256": hashlib.sha256(source_body).hexdigest(),
            "receiptBody": receipt_body.decode("utf-8"),
            "receiptSha256": hashlib.sha256(receipt_body).hexdigest(),
            "changedReceiptBody": changed_receipt_body.decode("utf-8"),
            "changedReceiptSha256": hashlib.sha256(
                changed_receipt_body
            ).hexdigest(),
        },
    )
    _render(
        page,
        reviews=[_review("2026-07-27T09:00:00Z", "a" * 64)],
        docs=[_document("proposal-a", "2026-07-26T10:00:00Z")],
    )
    root = page.locator("#guided-decision-review")
    with page.expect_download():
        root.get_by_role(
            "button",
            name="Download guided decision review handoff JSON",
        ).click()
    recheck = root.get_by_role(
        "button",
        name="Recheck guided decision review handoff",
    )
    assert recheck.is_enabled()

    with page.expect_download() as download_info:
        recheck.click()

    assert download_info.value.suggested_filename == (
        "guided-decision-review-recheck-receipt-aaaaaaaaaaaa.json"
    )
    request_payload = page.evaluate("window.__guidedReviewRecheckRequests[0]")
    assert request_payload["contract_version"] == (
        "guided-decision-review-recheck-request.v1"
    )
    assert request_payload["source_handoff"] == source
    assert request_payload["source_handoff_sha256"] == hashlib.sha256(
        source_body
    ).hexdigest()
    assert "Review state unchanged." in root.locator(
        "#guided-decision-review-announcement"
    ).inner_text()
    assert recheck.is_enabled()

    page.evaluate("window.__guidedReviewUseChangedReceipt = true")
    with page.expect_download() as changed_download:
        recheck.click()

    assert changed_download.value.suggested_filename == (
        "guided-decision-review-recheck-receipt-bbbbbbbbbbbb.json"
    )
    assert "Review state changed." in root.locator(
        "#guided-decision-review-announcement"
    ).inner_text()
    assert recheck.is_disabled()
    assert page.evaluate("_guidedDecisionReviewVerifiedHandoff === null")
    disposition = root.get_by_role(
        "button",
        name="Download guided decision review disposition receipt JSON",
    )
    assert disposition.is_enabled()
    assert root.locator(
        "[data-guided-decision-review-disposition]"
    ).input_value() == "new_handoff_required"


def test_guided_review_recheck_rejects_fingerprint_drift(page):
    page.evaluate("switchPage('project-page')")
    source = _handoff()
    current = _handoff(source_generated_at="2026-07-28T01:00:00Z")
    source_body = _handoff_body(source)
    receipt = _recheck_receipt(source, current)
    receipt["current_review_state_fingerprint_sha256"] = "0" * 64
    receipt_body = _handoff_body(receipt)
    page.evaluate(
        """({ sourceBody, sourceSha256, receiptBody, receiptSha256 }) => {
          window.__guidedReviewOriginalFetch = window.fetch;
          window.fetch = async (input, init = {}) => {
            const url = String(input);
            const isRecheck = url.includes('/guided-decision-review-handoff/recheck');
            if (!isRecheck && !url.includes('/guided-decision-review-handoff?')) {
              return window.__guidedReviewOriginalFetch(input, init);
            }
            return new Response(isRecheck ? receiptBody : sourceBody, {
              status: 200,
              headers: {
                'Cache-Control': 'no-store',
                'Content-Type': 'application/json; charset=utf-8',
                'Content-Disposition': isRecheck
                  ? 'attachment; filename="guided-decision-review-recheck-receipt-aaaaaaaaaaaa.json"'
                  : 'attachment; filename="guided-decision-review-handoff-aaaaaaaaaaaa.json"',
                'X-Content-Type-Options': 'nosniff',
                [isRecheck
                  ? 'X-DecisionDoc-Guided-Review-Recheck-Receipt-SHA256'
                  : 'X-DecisionDoc-Guided-Review-Handoff-SHA256']: isRecheck
                    ? receiptSha256
                    : sourceSha256,
                'X-DecisionDoc-Projection-Fingerprint': 'a'.repeat(64),
                'X-DecisionDoc-Review-State-Status': 'unchanged',
                'X-DecisionDoc-Operational-Approval': 'false',
              },
            });
          };
          window.__guidedReviewDownloadCalls = 0;
          window._triggerBrowserDownload = () => {
            window.__guidedReviewDownloadCalls += 1;
          };
        }""",
        {
            "sourceBody": source_body.decode("utf-8"),
            "sourceSha256": hashlib.sha256(source_body).hexdigest(),
            "receiptBody": receipt_body.decode("utf-8"),
            "receiptSha256": hashlib.sha256(receipt_body).hexdigest(),
        },
    )
    _render(
        page,
        reviews=[_review("2026-07-27T09:00:00Z", "a" * 64)],
        docs=[_document("proposal-a", "2026-07-26T10:00:00Z")],
    )
    root = page.locator("#guided-decision-review")
    root.get_by_role(
        "button",
        name="Download guided decision review handoff JSON",
    ).click()
    root.locator("#guided-decision-review-announcement").filter(
        has_text="Verified review handoff download started."
    ).wait_for()
    root.get_by_role(
        "button",
        name="Recheck guided decision review handoff",
    ).click()
    root.locator("#guided-decision-review-announcement").filter(
        has_text="recheck receipt verification failed"
    ).wait_for()

    assert page.evaluate("window.__guidedReviewDownloadCalls") == 1


def test_guided_review_disposition_downloads_verified_receipt(page):
    page.evaluate("switchPage('project-page')")
    source = _handoff()
    current = _handoff(source_generated_at="2026-07-28T01:00:00Z")
    source_body = _handoff_body(source)
    recheck = _recheck_receipt(source, current)
    recheck_body = _handoff_body(recheck)
    disposition = _disposition_receipt(
        recheck,
        "acknowledged_unchanged",
    )
    disposition_body = _handoff_body(disposition)
    page.evaluate(
        """({
          sourceBody, sourceSha256, recheckBody, recheckSha256,
          dispositionBody, dispositionSha256,
        }) => {
          window.__guidedReviewOriginalFetch = window.fetch;
          window.__guidedReviewDispositionRequests = [];
          window.fetch = async (input, init = {}) => {
            const url = String(input);
            if (url.includes('/guided-decision-review-handoff/review-disposition')) {
              window.__guidedReviewDispositionRequests.push(JSON.parse(init.body));
              return new Response(dispositionBody, {
                status: 200,
                headers: {
                  'Cache-Control': 'no-store',
                  'Content-Type': 'application/json; charset=utf-8',
                  'Content-Disposition': 'attachment; filename="guided-decision-review-disposition-receipt-aaaaaaaaaaaa.json"',
                  'X-Content-Type-Options': 'nosniff',
                  'X-DecisionDoc-Guided-Review-Disposition-Receipt-SHA256': dispositionSha256,
                  'X-DecisionDoc-Projection-Fingerprint': 'a'.repeat(64),
                  'X-DecisionDoc-Review-State-Status': 'unchanged',
                  'X-DecisionDoc-Operational-Approval': 'false',
                },
              });
            }
            if (url.includes('/guided-decision-review-handoff/recheck')) {
              return new Response(recheckBody, {
                status: 200,
                headers: {
                  'Cache-Control': 'no-store',
                  'Content-Type': 'application/json; charset=utf-8',
                  'Content-Disposition': 'attachment; filename="guided-decision-review-recheck-receipt-aaaaaaaaaaaa.json"',
                  'X-Content-Type-Options': 'nosniff',
                  'X-DecisionDoc-Guided-Review-Recheck-Receipt-SHA256': recheckSha256,
                  'X-DecisionDoc-Projection-Fingerprint': 'a'.repeat(64),
                  'X-DecisionDoc-Review-State-Status': 'unchanged',
                  'X-DecisionDoc-Operational-Approval': 'false',
                },
              });
            }
            if (url.includes('/guided-decision-review-handoff?')) {
              return new Response(sourceBody, {
                status: 200,
                headers: {
                  'Cache-Control': 'no-store',
                  'Content-Type': 'application/json; charset=utf-8',
                  'Content-Disposition': 'attachment; filename="guided-decision-review-handoff-aaaaaaaaaaaa.json"',
                  'X-Content-Type-Options': 'nosniff',
                  'X-DecisionDoc-Guided-Review-Handoff-SHA256': sourceSha256,
                  'X-DecisionDoc-Projection-Fingerprint': 'a'.repeat(64),
                  'X-DecisionDoc-Operational-Approval': 'false',
                },
              });
            }
            return window.__guidedReviewOriginalFetch(input, init);
          };
        }""",
        {
            "sourceBody": source_body.decode("utf-8"),
            "sourceSha256": hashlib.sha256(source_body).hexdigest(),
            "recheckBody": recheck_body.decode("utf-8"),
            "recheckSha256": hashlib.sha256(recheck_body).hexdigest(),
            "dispositionBody": disposition_body.decode("utf-8"),
            "dispositionSha256": hashlib.sha256(
                disposition_body
            ).hexdigest(),
        },
    )
    _render(
        page,
        reviews=[_review("2026-07-27T09:00:00Z", "a" * 64)],
        docs=[_document("proposal-a", "2026-07-26T10:00:00Z")],
    )
    root = page.locator("#guided-decision-review")
    with page.expect_download():
        root.get_by_role(
            "button",
            name="Download guided decision review handoff JSON",
        ).click()
    with page.expect_download():
        root.get_by_role(
            "button",
            name="Recheck guided decision review handoff",
        ).click()
    disposition_button = root.get_by_role(
        "button",
        name="Download guided decision review disposition receipt JSON",
    )
    assert disposition_button.is_enabled()

    with page.expect_download() as download_info:
        disposition_button.click()

    assert download_info.value.suggested_filename == (
        "guided-decision-review-disposition-receipt-aaaaaaaaaaaa.json"
    )
    request_payload = page.evaluate(
        "window.__guidedReviewDispositionRequests[0]"
    )
    assert request_payload == {
        "contract_version": "guided-decision-review-disposition-request.v1",
        "source_recheck_receipt": recheck,
        "source_recheck_receipt_sha256": hashlib.sha256(
            recheck_body
        ).hexdigest(),
        "review_disposition": "acknowledged_unchanged",
    }
    assert "Review disposition receipt downloaded." in root.locator(
        "#guided-decision-review-announcement"
    ).inner_text()


def test_guided_review_disposition_rejects_binding_drift(page):
    page.evaluate("switchPage('project-page')")
    source = _handoff()
    current = _handoff(source_generated_at="2026-07-28T01:00:00Z")
    source_body = _handoff_body(source)
    recheck = _recheck_receipt(source, current)
    recheck_body = _handoff_body(recheck)
    disposition = _disposition_receipt(
        recheck,
        "acknowledged_unchanged",
    )
    disposition["disposition_binding_sha256"] = "0" * 64
    disposition_body = _handoff_body(disposition)
    page.evaluate(
        """({
          sourceBody, sourceSha256, recheckBody, recheckSha256,
          dispositionBody, dispositionSha256,
        }) => {
          window.__guidedReviewOriginalFetch = window.fetch;
          window.fetch = async (input, init = {}) => {
            const url = String(input);
            const isDisposition = url.includes(
              '/guided-decision-review-handoff/review-disposition'
            );
            const isRecheck = url.includes(
              '/guided-decision-review-handoff/recheck'
            );
            if (!isDisposition && !isRecheck
                && !url.includes('/guided-decision-review-handoff?')) {
              return window.__guidedReviewOriginalFetch(input, init);
            }
            const body = isDisposition
              ? dispositionBody
              : (isRecheck ? recheckBody : sourceBody);
            return new Response(body, {
              status: 200,
              headers: {
                'Cache-Control': 'no-store',
                'Content-Type': 'application/json; charset=utf-8',
                'Content-Disposition': isDisposition
                  ? 'attachment; filename="guided-decision-review-disposition-receipt-aaaaaaaaaaaa.json"'
                  : (isRecheck
                    ? 'attachment; filename="guided-decision-review-recheck-receipt-aaaaaaaaaaaa.json"'
                    : 'attachment; filename="guided-decision-review-handoff-aaaaaaaaaaaa.json"'),
                'X-Content-Type-Options': 'nosniff',
                [isDisposition
                  ? 'X-DecisionDoc-Guided-Review-Disposition-Receipt-SHA256'
                  : (isRecheck
                    ? 'X-DecisionDoc-Guided-Review-Recheck-Receipt-SHA256'
                    : 'X-DecisionDoc-Guided-Review-Handoff-SHA256')]:
                      isDisposition
                        ? dispositionSha256
                        : (isRecheck ? recheckSha256 : sourceSha256),
                'X-DecisionDoc-Projection-Fingerprint': 'a'.repeat(64),
                'X-DecisionDoc-Review-State-Status': 'unchanged',
                'X-DecisionDoc-Operational-Approval': 'false',
              },
            });
          };
        }""",
        {
            "sourceBody": source_body.decode("utf-8"),
            "sourceSha256": hashlib.sha256(source_body).hexdigest(),
            "recheckBody": recheck_body.decode("utf-8"),
            "recheckSha256": hashlib.sha256(recheck_body).hexdigest(),
            "dispositionBody": disposition_body.decode("utf-8"),
            "dispositionSha256": hashlib.sha256(
                disposition_body
            ).hexdigest(),
        },
    )
    _render(
        page,
        reviews=[_review("2026-07-27T09:00:00Z", "a" * 64)],
        docs=[_document("proposal-a", "2026-07-26T10:00:00Z")],
    )
    root = page.locator("#guided-decision-review")
    with page.expect_download():
        root.get_by_role(
            "button",
            name="Download guided decision review handoff JSON",
        ).click()
    with page.expect_download():
        root.get_by_role(
            "button",
            name="Recheck guided decision review handoff",
        ).click()
    page.evaluate(
        """() => {
          window.__guidedReviewDownloadCalls = 0;
          window._triggerBrowserDownload = () => {
            window.__guidedReviewDownloadCalls += 1;
          };
        }"""
    )
    root.get_by_role(
        "button",
        name="Download guided decision review disposition receipt JSON",
    ).click()
    root.locator("#guided-decision-review-announcement").filter(
        has_text="disposition receipt verification failed"
    ).wait_for()

    assert page.evaluate("window.__guidedReviewDownloadCalls") == 0


def test_guided_review_auth_invalidation_discards_page_memory_sources(page):
    page.evaluate("switchPage('project-page')")
    _render(
        page,
        reviews=[_review("2026-07-27T09:00:00Z", "a" * 64)],
        docs=[_document("proposal-a", "2026-07-26T10:00:00Z")],
    )

    result = page.evaluate(
        """() => {
          _guidedDecisionReviewVerifiedHandoff = { bodySha256: 'a'.repeat(64) };
          _guidedDecisionReviewVerifiedRecheck = { bodySha256: 'b'.repeat(64) };
          _guidedDecisionReviewVerifiedDisposition = { bodySha256: 'c'.repeat(64) };
          _guidedDecisionReviewRegistryPending = { requestId: 1 };
          const before = {
            handoffRequestId: _guidedDecisionReviewHandoffRequestId,
            recheckRequestId: _guidedDecisionReviewRecheckRequestId,
            dispositionRequestId: _guidedDecisionReviewDispositionRequestId,
            registryRequestId: _guidedDecisionReviewRegistryRequestId,
          };
          invalidateProcurementReviewViews();
          return {
            handoff: _guidedDecisionReviewVerifiedHandoff,
            recheck: _guidedDecisionReviewVerifiedRecheck,
            disposition: _guidedDecisionReviewVerifiedDisposition,
            registryPending: _guidedDecisionReviewRegistryPending,
            handoffRequestId: _guidedDecisionReviewHandoffRequestId,
            recheckRequestId: _guidedDecisionReviewRecheckRequestId,
            dispositionRequestId: _guidedDecisionReviewDispositionRequestId,
            registryRequestId: _guidedDecisionReviewRegistryRequestId,
            before,
          };
        }"""
    )

    assert result["handoff"] is None
    assert result["recheck"] is None
    assert result["disposition"] is None
    assert result["registryPending"] is None
    assert result["handoffRequestId"] > result["before"]["handoffRequestId"]
    assert result["recheckRequestId"] > result["before"]["recheckRequestId"]
    assert result["dispositionRequestId"] > result["before"]["dispositionRequestId"]
    assert result["registryRequestId"] > result["before"]["registryRequestId"]


def test_guided_review_cross_tab_auth_change_discards_page_memory_before_reload(page):
    page.evaluate("switchPage('project-page')")
    _render(
        page,
        reviews=[_review("2026-07-27T09:00:00Z", "a" * 64)],
        docs=[_document("proposal-a", "2026-07-26T10:00:00Z")],
    )

    result = page.evaluate(
        """() => {
          const revoked = [];
          const originalRevoke = URL.revokeObjectURL;
          URL.revokeObjectURL = url => revoked.push(url);
          try {
            _guidedDecisionReviewVerifiedHandoff = { bodySha256: 'a'.repeat(64) };
            _guidedDecisionReviewVerifiedRecheck = { bodySha256: 'b'.repeat(64) };
            _guidedDecisionReviewVerifiedDisposition = { bodySha256: 'c'.repeat(64) };
            _guidedDecisionReviewRegistryPending = { requestId: 1 };
            _exportDownloadUrls.push(
              { url: 'blob:handoff', scope: GUIDED_DECISION_REVIEW_HANDOFF_DOWNLOAD_SCOPE },
              { url: 'blob:recheck', scope: GUIDED_DECISION_REVIEW_RECHECK_DOWNLOAD_SCOPE },
              { url: 'blob:disposition', scope: GUIDED_DECISION_REVIEW_DISPOSITION_DOWNLOAD_SCOPE },
            );
            const before = {
              handoffRequestId: _guidedDecisionReviewHandoffRequestId,
              recheckRequestId: _guidedDecisionReviewRecheckRequestId,
              dispositionRequestId: _guidedDecisionReviewDispositionRequestId,
              registryRequestId: _guidedDecisionReviewRegistryRequestId,
            };
            _crossTabAuthReloadRequested = true;
            handleCrossTabAuthStorageChange({
              storageArea: localStorage,
              key: 'dd_access_token',
            });
            return {
              handoff: _guidedDecisionReviewVerifiedHandoff,
              recheck: _guidedDecisionReviewVerifiedRecheck,
              disposition: _guidedDecisionReviewVerifiedDisposition,
              registryPending: _guidedDecisionReviewRegistryPending,
              handoffRequestId: _guidedDecisionReviewHandoffRequestId,
              recheckRequestId: _guidedDecisionReviewRecheckRequestId,
              dispositionRequestId: _guidedDecisionReviewDispositionRequestId,
              registryRequestId: _guidedDecisionReviewRegistryRequestId,
              revoked,
              before,
            };
          } finally {
            URL.revokeObjectURL = originalRevoke;
          }
        }"""
    )

    assert result["handoff"] is None
    assert result["recheck"] is None
    assert result["disposition"] is None
    assert result["registryPending"] is None
    assert result["handoffRequestId"] > result["before"]["handoffRequestId"]
    assert result["recheckRequestId"] > result["before"]["recheckRequestId"]
    assert result["dispositionRequestId"] > result["before"]["dispositionRequestId"]
    assert result["registryRequestId"] > result["before"]["registryRequestId"]
    assert result["revoked"] == [
        "blob:handoff",
        "blob:recheck",
        "blob:disposition",
    ]


def test_guided_review_disposition_registry_request_token_prevents_stale_clear_and_third_post(page):
    page.evaluate("switchPage('project-page')")
    source = _handoff()
    current = _handoff(source_generated_at="2026-07-28T01:00:00Z")
    source_body = _handoff_body(source)
    recheck = _recheck_receipt(source, current)
    recheck_body = _handoff_body(recheck)
    disposition = _disposition_receipt(recheck, "acknowledged_unchanged")
    disposition_body = _handoff_body(disposition)
    page.evaluate(
        """({
          sourceBody, sourceSha256, recheckBody, recheckSha256,
          dispositionBody, dispositionSha256,
        }) => {
          window.__guidedReviewOriginalFetch = window.fetch;
          window.fetch = async (input, init = {}) => {
            const url = String(input);
            if (url.includes('/guided-decision-review-handoff/review-disposition')) {
              return new Response(dispositionBody, {
                status: 200,
                headers: {
                  'Cache-Control': 'no-store',
                  'Content-Type': 'application/json; charset=utf-8',
                  'Content-Disposition': 'attachment; filename="guided-decision-review-disposition-receipt-aaaaaaaaaaaa.json"',
                  'X-Content-Type-Options': 'nosniff',
                  'X-DecisionDoc-Guided-Review-Disposition-Receipt-SHA256': dispositionSha256,
                  'X-DecisionDoc-Projection-Fingerprint': 'a'.repeat(64),
                  'X-DecisionDoc-Review-State-Status': 'unchanged',
                  'X-DecisionDoc-Operational-Approval': 'false',
                },
              });
            }
            if (url.includes('/guided-decision-review-handoff/recheck')) {
              return new Response(recheckBody, {
                status: 200,
                headers: {
                  'Cache-Control': 'no-store',
                  'Content-Type': 'application/json; charset=utf-8',
                  'Content-Disposition': 'attachment; filename="guided-decision-review-recheck-receipt-aaaaaaaaaaaa.json"',
                  'X-Content-Type-Options': 'nosniff',
                  'X-DecisionDoc-Guided-Review-Recheck-Receipt-SHA256': recheckSha256,
                  'X-DecisionDoc-Projection-Fingerprint': 'a'.repeat(64),
                  'X-DecisionDoc-Review-State-Status': 'unchanged',
                  'X-DecisionDoc-Operational-Approval': 'false',
                },
              });
            }
            if (url.includes('/guided-decision-review-handoff?')) {
              return new Response(sourceBody, {
                status: 200,
                headers: {
                  'Cache-Control': 'no-store',
                  'Content-Type': 'application/json; charset=utf-8',
                  'Content-Disposition': 'attachment; filename="guided-decision-review-handoff-aaaaaaaaaaaa.json"',
                  'X-Content-Type-Options': 'nosniff',
                  'X-DecisionDoc-Guided-Review-Handoff-SHA256': sourceSha256,
                  'X-DecisionDoc-Projection-Fingerprint': 'a'.repeat(64),
                  'X-DecisionDoc-Operational-Approval': 'false',
                },
              });
            }
            return window.__guidedReviewOriginalFetch(input, init);
          };
        }""",
        {
            "sourceBody": source_body.decode("utf-8"),
            "sourceSha256": hashlib.sha256(source_body).hexdigest(),
            "recheckBody": recheck_body.decode("utf-8"),
            "recheckSha256": hashlib.sha256(recheck_body).hexdigest(),
            "dispositionBody": disposition_body.decode("utf-8"),
            "dispositionSha256": hashlib.sha256(disposition_body).hexdigest(),
        },
    )
    _render(
        page,
        reviews=[_review("2026-07-27T09:00:00Z", "a" * 64)],
        docs=[_document("proposal-a", "2026-07-26T10:00:00Z")],
    )
    root = page.locator("#guided-decision-review")
    with page.expect_download():
        root.get_by_role(
            "button",
            name="Download guided decision review handoff JSON",
        ).click()
    with page.expect_download():
        root.get_by_role(
            "button",
            name="Recheck guided decision review handoff",
        ).click()
    with page.expect_download():
        root.get_by_role(
            "button",
            name="Download guided decision review disposition receipt JSON",
        ).click()

    page.evaluate(
        """() => {
          const priorFetch = window.fetch;
          window.__guidedReviewRegistryPosts = [];
          window.__guidedReviewRegistryResolvers = [];
          window.fetch = (input, init = {}) => {
            const url = String(input);
            if (
              url.includes('/guided-decision-review-dispositions?')
              && init.method === 'POST'
            ) {
              window.__guidedReviewRegistryPosts.push(JSON.parse(init.body));
              return new Promise(resolve => {
                window.__guidedReviewRegistryResolvers.push(resolve);
              });
            }
            return priorFetch(input, init);
          };
        }"""
    )
    create_button = root.get_by_role(
        "button",
        name="Record the verified guided decision review disposition",
    )
    assert create_button.is_enabled()
    create_button.click()
    page.wait_for_function("window.__guidedReviewRegistryPosts.length === 1")
    first_operation = page.evaluate(
        "window.__guidedReviewRegistryPosts[0].operation_id"
    )

    race_state = page.evaluate(
        """() => {
          const source = _guidedDecisionReviewVerifiedDisposition;
          const firstToken = _guidedDecisionReviewRegistryPending;
          clearGuidedDecisionReviewDispositionRegistrySource();
          _guidedDecisionReviewVerifiedDisposition = source;
          syncGuidedDecisionReviewRegistryControls();
          createGuidedDecisionReviewRegistryRecord();
          return { firstToken };
        }"""
    )
    assert race_state["firstToken"]["operationId"] == first_operation
    page.wait_for_function("window.__guidedReviewRegistryPosts.length === 2")
    second_token = page.evaluate("_guidedDecisionReviewRegistryPending")

    page.evaluate(
        """() => {
          window.__guidedReviewRegistryResolvers[0](
            new Response('', { status: 503 }),
          );
        }"""
    )
    page.wait_for_timeout(50)
    assert page.evaluate(
        "_guidedDecisionReviewRegistryPending?.requestId"
    ) == second_token["requestId"]

    page.evaluate("createGuidedDecisionReviewRegistryRecord()")
    page.wait_for_timeout(50)
    assert page.evaluate("window.__guidedReviewRegistryPosts.length") == 2
