"""Decision package construction and artifact orchestration.

Builds decision packages (from sample input or a stored decision record),
their handoff/audit/export sub-artifacts, and writes the full artifact set
to disk.

This module is intentionally local and deterministic. It does not call providers,
AWS, training, model promotion, or service-resume paths.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from app.schemas import (
    NormalizedProcurementOpportunity,
    ProcurementChecklistItem,
    ProcurementDecisionRecord,
    ProcurementDecisionUpsert,
    ProcurementHardFilterResult,
    ProcurementRecommendation,
    ProcurementScoreBreakdownItem,
)
from app.storage.procurement_store import ProcurementDecisionStore

from app.services.procurement_decision_package.constants import (
    AUDIT_MANIFEST_ARTIFACT_GROUPS,
    AUDIT_MANIFEST_PACKET_STATUS,
    AUDIT_MANIFEST_SCHEMA_PURPOSE,
    BID_READINESS_CHECKLIST_NAME,
    DECISION_PACKAGE_NAME,
    DECISION_SUMMARY_NAME,
    DEFAULT_DECISION_PACKAGE_OUTPUT_BASE,
    DEMO_PROJECT_ID,
    DEMO_RECOMMENDATION,
    DEMO_TENANT_ID,
    EVIDENCE_SUMMARY_NAME,
    EXCLUDED_ACTION_ORDER,
    EXPECTED_DECISION_PACKAGE_SCHEMA_PURPOSE,
    EXPLICIT_AUTHORIZATION_BOUNDARY,
    INCLUDED_ARTIFACT_ORDER,
    JSON_ARTIFACT_PACKAGE_FIELDS,
    NEXT_REVIEW_ACTION_WITH_GAPS,
    NON_APPROVAL_MARKER,
    NON_AUTHORIZATION_NOTE,
    PROCUREMENT_DECISION_PACKAGE_SCHEMA_PURPOSE,
    PROCUREMENT_REVIEW_NAME,
    PROPOSAL_ALLOWED_NEXT_STEPS,
    PROPOSAL_HANDOFF_SCOPE,
    SIGNOFF_SCOPE,
    SIGNOFF_SUMMARY_NAME,
)
from app.services.procurement_decision_package.artifact_writers import (
    _render_bid_readiness_checklist,
    _render_decision_summary,
    _render_evidence_summary,
    _render_signoff_summary,
    write_json_atomic,
    write_text_atomic,
)
from app.services.procurement_decision_package.field_validators import (
    _proposal_handoff_drafting_status,
)
from app.services.procurement_decision_package.json_helpers import load_json
from app.services.procurement_decision_package.package_document_validation import (
    validate_package_document,
)
from app.services.procurement_decision_package.sample_validation import (
    validate_demo_input,
    validate_expected_package_for_sample,
)
from app.services.procurement_decision_package.review_workspace import (
    render_procurement_review_workspace,
)

def build_decision_package(sample_input: dict[str, Any]) -> dict[str, Any]:
    validate_demo_input(sample_input)

    opportunity = sample_input["opportunity"]
    capability_profile = sample_input["capability_profile"]
    operator_notes = sample_input["operator_notes"]
    scenario_id = sample_input["scenario_id"]
    updated_at = sample_input["updated_at"]
    schema_purpose = EXPECTED_DECISION_PACKAGE_SCHEMA_PURPOSE
    package_id = f"{opportunity['opportunity_id']}-package"
    recommendation = DEMO_RECOMMENDATION
    unresolved_gaps = [
        "security-plan",
        "training-staffing",
        "proposal-reviewer",
    ]
    reviewer = operator_notes["reviewer_owner"]
    requested_decision = "review_conditional_go"
    review_prompt = (
        "Confirm whether proposal drafting may start after listed blockers "
        "receive owners."
    )
    package = {
        "package_id": package_id,
        "recommendation": recommendation,
        "recommendation_reason": (
            "The opportunity fits the team's document workflow "
            "and internal tooling capabilities, "
            "but proposal drafting should wait for security plan ownership, "
            "operator training staffing, "
            "and Korean proposal review confirmation."
        ),
        "opportunity_ref": {
            "opportunity_id": opportunity["opportunity_id"],
            "title": opportunity["title"],
            "source_type": opportunity["source_type"],
        },
        "hard_filters": [
            {
                "filter_id": "mandatory-certification",
                "status": "pass",
                "reason": (
                    "No unavailable mandatory certification is present "
                    "in the local fixture."
                ),
            },
            {
                "filter_id": "deadline-readiness",
                "status": "pass",
                "reason": (
                    "Deadline is 21 days, which does not violate "
                    "the sample excluded risk condition."
                ),
            },
            {
                "filter_id": "security-plan",
                "status": "needs_review",
                "reason": (
                    "A security handling plan is mandatory and currently "
                    "draft-required."
                ),
            },
        ],
        "soft_fit_score": {
            "score": 68,
            "band": "conditional",
            "factors": [
                {
                    "name": "domain_fit",
                    "score": 78,
                    "evidence_ids": ["evidence-service-line-document-workflow"],
                },
                {
                    "name": "reference_project_fit",
                    "score": 64,
                    "evidence_ids": ["evidence-public-sector-reference"],
                },
                {
                    "name": "staffing_readiness",
                    "score": 58,
                    "evidence_ids": ["gap-training-staffing-owner"],
                },
                {
                    "name": "security_readiness",
                    "score": 52,
                    "evidence_ids": ["gap-security-plan-owner"],
                },
                {
                    "name": "budget_fit",
                    "score": 82,
                    "evidence_ids": ["evidence-budget-fit"],
                },
            ],
        },
        "evidence_summary": [
            {
                "evidence_id": "evidence-service-line-document-workflow",
                "type": "source_fact",
                "source": "capability_profile.service_lines",
                "summary": (
                    "Capability profile includes "
                    f"{capability_profile['service_lines'][0]} and internal tooling."
                ),
            },
            {
                "evidence_id": "evidence-public-sector-reference",
                "type": "source_fact",
                "source": "capability_profile.public_sector_references",
                "summary": (
                    "A public-sector style reporting process reference is available, "
                    "but the fit should be reviewed."
                ),
            },
            {
                "evidence_id": "evidence-budget-fit",
                "type": "source_fact",
                "source": (
                    "opportunity.budget_range + "
                    "capability_profile.preferred_budget_range"
                ),
                "summary": (
                    "Opportunity budget range falls inside "
                    "the sample preferred budget range."
                ),
            },
            {
                "evidence_id": "gap-security-plan-owner",
                "type": "missing_evidence",
                "source": "operator_notes.known_uncertainty",
                "summary": "Security handling plan owner is not confirmed.",
            },
            {
                "evidence_id": "gap-training-staffing-owner",
                "type": "missing_evidence",
                "source": "operator_notes.known_uncertainty",
                "summary": operator_notes["known_uncertainty"][1],
            },
        ],
        "bid_readiness_checklist": [
            {
                "item_id": "security-plan",
                "label": "Finalize security handling plan",
                "owner": "unassigned",
                "status": "blocked",
                "required_before": "proposal_drafting",
            },
            {
                "item_id": "training-staffing",
                "label": "Assign operator training staffing owner",
                "owner": "unassigned",
                "status": "blocked",
                "required_before": "proposal_drafting",
            },
            {
                "item_id": "proposal-reviewer",
                "label": "Confirm Korean proposal package reviewer",
                "owner": "unassigned",
                "status": "needs_review",
                "required_before": "proposal_submission",
            },
        ],
        "validation_summary": build_validation_summary(
            schema_status="expected_shape_only",
            recommendation=recommendation,
            unresolved_gaps=unresolved_gaps,
        ),
        **_build_package_handoff_artifacts(
            reviewer=reviewer,
            requested_decision=requested_decision,
            review_prompt=review_prompt,
            package_id=package_id,
            recommendation=recommendation,
            unresolved_gaps=unresolved_gaps,
        ),
    }

    return {
        "scenario_id": scenario_id,
        "schema_purpose": schema_purpose,
        "updated_at": updated_at,
        "package": package,
    }


def seed_demo_decision_record(
    *,
    data_dir: Path,
    tenant_id: str = DEMO_TENANT_ID,
    project_id: str = DEMO_PROJECT_ID,
) -> str:
    store = ProcurementDecisionStore(base_dir=str(data_dir))

    record = store.upsert(
        ProcurementDecisionUpsert(
            project_id=project_id,
            tenant_id=tenant_id,
            opportunity=_demo_decision_opportunity(),
            hard_filters=_demo_decision_hard_filters(),
            score_breakdown=_demo_decision_score_breakdown(),
            soft_fit_score=68.0,
            soft_fit_status="scored",
            missing_data=_demo_decision_missing_data(),
            checklist_items=_demo_decision_checklist_items(),
            recommendation=_demo_decision_recommendation(),
            notes=(
                "Local package demo seed record. "
                "Does not authorize operational action."
            ),
        )
    )

    return record.decision_id


def _demo_decision_opportunity() -> NormalizedProcurementOpportunity:
    return NormalizedProcurementOpportunity(
        source_kind="local_demo",
        source_id="local-procurement-demo-001",
        title="Public Agency Document Workflow Modernization Pilot",
        issuer="Sample Public Agency",
        budget="KRW 80M-120M",
        deadline="21 days",
        bid_type="local_fixture",
        category="document_operations",
        region="sample",
        raw_text_preview="Local deterministic procurement package demo.",
    )


def _demo_decision_hard_filters() -> list[ProcurementHardFilterResult]:
    return [
        ProcurementHardFilterResult(
            code="security_plan",
            label="Security handling plan",
            status="unknown",
            blocking=True,
            reason=(
                "Security handling plan owner must be confirmed "
                "before proposal drafting."
            ),
        ),
    ]


def _demo_decision_score_breakdown() -> list[ProcurementScoreBreakdownItem]:
    return [
        ProcurementScoreBreakdownItem(
            key="domain_fit",
            label="Domain fit",
            score=78.0,
            weight=0.25,
            weighted_score=19.5,
            summary="Document workflow capability is aligned with the opportunity.",
            evidence=["document workflow consulting"],
        ),
        ProcurementScoreBreakdownItem(
            key="security_readiness",
            label="Security readiness",
            score=52.0,
            weight=0.25,
            weighted_score=13.0,
            summary="Security plan requires owner assignment.",
            evidence=["security plan draft required"],
        ),
    ]


def _demo_decision_checklist_items() -> list[ProcurementChecklistItem]:
    return [
        ProcurementChecklistItem(
            category="security_plan",
            title="Finalize security handling plan",
            status="action_needed",
            severity="high",
            remediation_note="Assign owner before proposal drafting.",
        ),
        ProcurementChecklistItem(
            category="training_staffing",
            title="Assign operator training staffing owner",
            status="action_needed",
            severity="medium",
            remediation_note="Confirm trainer availability before kickoff.",
        ),
    ]


def _demo_decision_recommendation() -> ProcurementRecommendation:
    return ProcurementRecommendation(
        value=DEMO_RECOMMENDATION,
        summary=(
            "Conditional go pending security and "
            "training ownership confirmation."
        ),
        evidence=[
            "Weighted fit score: 68.00",
            "Document workflow capability aligns with the opportunity.",
        ],
        missing_data=_demo_decision_missing_data(),
        remediation_notes=[
            "Assign security plan owner.",
            "Assign operator training staffing owner.",
        ],
    )


def _demo_decision_missing_data() -> list[str]:
    return [
        "security plan owner",
        "operator training staffing owner",
    ]


def build_decision_package_from_record(
    record: ProcurementDecisionRecord,
    *,
    reviewer_owner: str = "executive-reviewer",
) -> dict[str, Any]:
    if record.opportunity is None:
        raise ValueError("procurement decision record must include an opportunity")
    if record.recommendation is None:
        raise ValueError("procurement decision record must include a recommendation")

    opportunity = record.opportunity
    recommendation = record.recommendation
    recommendation_value = recommendation.value.value
    score = int(round(record.soft_fit_score or 0))
    package_id = f"{record.decision_id}-package"
    requested_decision = f"review_{recommendation_value.lower()}"
    review_prompt = (
        "Review the procurement decision package before proposal drafting "
        "or downstream handoff."
    )
    checklist = [
        {
            "item_id": item.category,
            "label": item.title,
            "owner": item.owner or "unassigned",
            "status": _package_checklist_status(item.status.value),
            "required_before": "proposal_drafting",
        }
        for item in record.checklist_items
    ]
    unresolved_gaps = [
        *[
            item["item_id"]
            for item in checklist
            if item["status"] in {"blocked", "needs_review"}
        ],
        *record.missing_data,
    ]
    source_evidence = [
        {
            "evidence_id": f"recommendation-evidence-{index + 1}",
            "type": "source_fact",
            "source": "record.recommendation.evidence",
            "summary": evidence,
        }
        for index, evidence in enumerate(recommendation.evidence)
    ]
    score_summary_evidence = []
    if record.score_breakdown:
        score_summary_evidence.append(
            {
                "evidence_id": "score-summary",
                "type": "source_fact",
                "source": "record.score_breakdown",
                "summary": f"Soft-fit score is {score}.",
            }
        )
    evidence_summary = [
        *(source_evidence or score_summary_evidence),
        *[
            {
                "evidence_id": f"missing-data-{index + 1}",
                "type": "missing_evidence",
                "source": "record.missing_data",
                "summary": missing_data,
            }
            for index, missing_data in enumerate(record.missing_data)
        ],
    ]
    package = {
        "package_id": package_id,
        "recommendation": recommendation_value,
        "recommendation_reason": recommendation.summary,
        "opportunity_ref": {
            "opportunity_id": opportunity.source_id,
            "title": opportunity.title,
            "source_type": opportunity.source_kind,
        },
        "hard_filters": [
            {
                "filter_id": item.code,
                "status": item.status.value,
                "reason": item.reason,
            }
            for item in record.hard_filters
        ],
        "soft_fit_score": {
            "score": score,
            "band": _score_band(recommendation_value, score),
            "factors": [
                {
                    "name": item.key,
                    "score": int(round(item.score)),
                    "evidence_ids": [f"score-{item.key}"],
                }
                for item in record.score_breakdown
            ],
        },
        "evidence_summary": evidence_summary,
        "bid_readiness_checklist": checklist,
        "validation_summary": build_validation_summary(
            schema_status="record_shape",
            recommendation=recommendation_value,
            unresolved_gaps=unresolved_gaps,
        ),
        **_build_package_handoff_artifacts(
            reviewer=reviewer_owner,
            requested_decision=requested_decision,
            review_prompt=review_prompt,
            package_id=package_id,
            recommendation=recommendation_value,
            unresolved_gaps=unresolved_gaps,
        ),
    }
    scenario_id = f"procurement-record-{record.project_id}"
    schema_purpose = PROCUREMENT_DECISION_PACKAGE_SCHEMA_PURPOSE
    updated_at = record.updated_at

    return {
        "scenario_id": scenario_id,
        "schema_purpose": schema_purpose,
        "updated_at": updated_at,
        "package": package,
    }


def _build_package_handoff_artifacts(
    *,
    reviewer: str,
    requested_decision: str,
    review_prompt: str,
    package_id: str,
    recommendation: str,
    unresolved_gaps: list[str],
) -> dict[str, Any]:
    return {
        "reviewer_handoff": build_reviewer_handoff(
            reviewer=reviewer,
            requested_decision=requested_decision,
            review_prompt=review_prompt,
        ),
        "proposal_handoff": build_proposal_handoff(
            package_id=package_id,
            recommendation=recommendation,
            unresolved_gaps=unresolved_gaps,
        ),
        "pending_signoff": build_pending_signoff(reviewer=reviewer),
        "audit_manifest": build_audit_manifest(
            package_id=package_id,
            recommendation=recommendation,
        ),
        "export_manifest": build_export_manifest(),
    }


def export_project_decision_package(
    *,
    data_dir: Path,
    tenant_id: str,
    project_id: str,
    out_dir: Path | None = None,
    reviewer_owner: str = "executive-reviewer",
) -> dict[str, object]:
    store = ProcurementDecisionStore(base_dir=str(data_dir))
    record = store.get(project_id, tenant_id=tenant_id)
    if record is None:
        raise KeyError(
            "procurement decision record not found: "
            f"tenant_id={tenant_id} project_id={project_id}"
        )

    package_doc = build_decision_package_from_record(
        record,
        reviewer_owner=reviewer_owner,
    )
    default_output_dir = DEFAULT_DECISION_PACKAGE_OUTPUT_BASE / tenant_id / project_id
    output_dir = out_dir or default_output_dir
    artifact_write_result = write_package_artifacts(package_doc, output_dir)

    return {
        "status": artifact_write_result["status"],
        "schema_purpose": package_doc["schema_purpose"],
        "tenant_id": tenant_id,
        "project_id": project_id,
        "decision_id": record.decision_id,
        "output_dir": artifact_write_result["output_dir"],
        "artifacts": artifact_write_result["artifacts"],
        "recommendation": artifact_write_result["recommendation"],
        "authorization_boundary": artifact_write_result["authorization_boundary"],
    }


def _package_checklist_status(status: str) -> str:
    if status == "blocked":
        return "blocked"
    if status in {"action_needed", "unknown"}:
        return "needs_review"
    return "ready"


def _score_band(recommendation: str, score: int) -> str:
    if recommendation == "GO":
        return "go"
    if recommendation == "NO_GO":
        return "no_go"
    if score < 55:
        return "low_conditional"
    return "conditional"


def build_reviewer_handoff(
    *,
    reviewer: str,
    requested_decision: str,
    review_prompt: str,
) -> dict[str, Any]:
    return {
        "requested_reviewer": reviewer,
        "requested_decision": requested_decision,
        "review_prompt": review_prompt,
        "non_authorization_note": NON_AUTHORIZATION_NOTE,
    }


def build_pending_signoff(*, reviewer: str) -> dict[str, Any]:
    return {
        "status": "pending",
        "reviewer": reviewer,
        "signoff_scope": SIGNOFF_SCOPE,
        "operational_approval": False,
    }


def build_export_manifest() -> dict[str, Any]:
    return {
        "included_artifacts": list(INCLUDED_ARTIFACT_ORDER),
        "excluded_actions": list(EXCLUDED_ACTION_ORDER),
    }


def build_audit_manifest(*, package_id: str, recommendation: str) -> dict[str, Any]:
    return {
        "schema_purpose": AUDIT_MANIFEST_SCHEMA_PURPOSE,
        "packet_status": AUDIT_MANIFEST_PACKET_STATUS,
        "package_id": package_id,
        "recommendation": recommendation,
        "included_artifacts": list(INCLUDED_ARTIFACT_ORDER),
        "decision_artifacts": list(
            AUDIT_MANIFEST_ARTIFACT_GROUPS["decision_artifacts"]
        ),
        "evidence_artifacts": list(
            AUDIT_MANIFEST_ARTIFACT_GROUPS["evidence_artifacts"]
        ),
        "validation_artifacts": list(
            AUDIT_MANIFEST_ARTIFACT_GROUPS["validation_artifacts"]
        ),
        "handoff_artifacts": list(
            AUDIT_MANIFEST_ARTIFACT_GROUPS["handoff_artifacts"]
        ),
        "signoff_artifacts": list(
            AUDIT_MANIFEST_ARTIFACT_GROUPS["signoff_artifacts"]
        ),
        "excluded_actions": list(EXCLUDED_ACTION_ORDER),
        "non_authorization_note": NON_AUTHORIZATION_NOTE,
    }


def build_proposal_handoff(
    *,
    package_id: str,
    recommendation: str,
    unresolved_gaps: list[str],
) -> dict[str, Any]:
    ordered_unresolved_gaps = _unique_strings(unresolved_gaps)

    return {
        "handoff_scope": PROPOSAL_HANDOFF_SCOPE,
        "source_package_id": package_id,
        "recommendation": recommendation,
        "drafting_status": _proposal_handoff_drafting_status(
            ordered_unresolved_gaps
        ),
        "required_inputs": list(ordered_unresolved_gaps),
        "blocked_until": list(ordered_unresolved_gaps),
        "allowed_next_steps": list(PROPOSAL_ALLOWED_NEXT_STEPS),
        "excluded_actions": list(EXCLUDED_ACTION_ORDER),
        "non_authorization_note": NON_AUTHORIZATION_NOTE,
    }


def _unique_strings(items: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for item in items:
        if not item or item in seen:
            continue
        seen.add(item)
        ordered.append(item)
    return ordered


def build_validation_summary(
    *,
    schema_status: str,
    recommendation: str,
    unresolved_gaps: list[str],
) -> dict[str, Any]:
    ordered_unresolved_gaps = _unique_strings(unresolved_gaps)

    return {
        "schema_status": schema_status,
        "boundary_status": "explicit_non_authorization_required",
        "operator_summary": _operator_validation_summary(
            recommendation=recommendation,
            unresolved_gaps=ordered_unresolved_gaps,
        ),
        "next_review_action": NEXT_REVIEW_ACTION_WITH_GAPS,
        "unresolved_gaps": ordered_unresolved_gaps,
    }


def _operator_validation_summary(
    *,
    recommendation: str,
    unresolved_gaps: list[str],
) -> str:
    boundary_sentence = f"This package is evidence for review, {NON_APPROVAL_MARKER}."
    if unresolved_gaps:
        review_sentence = (
            f"{recommendation} can be reviewed, but proposal work should wait "
            "until the listed gaps have owners."
        )
        return f"{review_sentence} {boundary_sentence}"

    review_sentence = (
        f"{recommendation} can move to reviewer sign-off "
        "for the package scope."
    )
    return f"{review_sentence} {boundary_sentence}"


def write_package_artifacts(
    package_doc: dict[str, Any],
    output_dir: Path,
) -> dict[str, Any]:
    package = validate_package_document(package_doc)
    output_dir.mkdir(parents=True, exist_ok=True)

    json_artifacts: dict[str, Any] = {
        DECISION_PACKAGE_NAME: package_doc,
    }
    for artifact_name, package_field in JSON_ARTIFACT_PACKAGE_FIELDS.items():
        json_artifacts[artifact_name] = package[package_field]
    for artifact_name, artifact_data in json_artifacts.items():
        write_json_atomic(output_dir / artifact_name, artifact_data)

    markdown_artifacts = {
        DECISION_SUMMARY_NAME: _render_decision_summary(package),
        EVIDENCE_SUMMARY_NAME: _render_evidence_summary(package),
        BID_READINESS_CHECKLIST_NAME: _render_bid_readiness_checklist(package),
        SIGNOFF_SUMMARY_NAME: _render_signoff_summary(package),
    }
    for artifact_name, artifact_text in markdown_artifacts.items():
        write_text_atomic(output_dir / artifact_name, artifact_text.rstrip() + "\n")

    write_text_atomic(
        output_dir / PROCUREMENT_REVIEW_NAME,
        render_procurement_review_workspace(package_doc),
    )

    return {
        "schema_purpose": package_doc["schema_purpose"],
        "status": "passed",
        "output_dir": str(output_dir),
        "artifacts": list(INCLUDED_ARTIFACT_ORDER),
        "recommendation": package["recommendation"],
        "authorization_boundary": EXPLICIT_AUTHORIZATION_BOUNDARY,
    }


def build_and_write(*, sample_input_path: Path, output_dir: Path) -> dict[str, Any]:
    sample_input = load_json(sample_input_path)
    package_doc = build_decision_package(sample_input)
    validate_expected_package_for_sample(package_doc, sample_input=sample_input)
    return write_package_artifacts(package_doc, output_dir)
