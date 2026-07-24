"""Deterministic, read-only projection for project decision evidence."""
from __future__ import annotations

from typing import Any, Iterable

from app.schemas.decision_evidence import (
    DecisionEvidenceAuthority,
    DecisionEvidenceCoverageItem,
    DecisionEvidenceCoverageSummary,
    DecisionEvidenceDiagnostic,
    DecisionEvidenceEdge,
    DecisionEvidenceLimits,
    DecisionEvidenceMapResponse,
    DecisionEvidenceNode,
    DecisionEvidenceProposalBlueprint,
    DecisionEvidenceProposalSlide,
    DecisionEvidenceProvenance,
    DecisionEvidenceSourceRevision,
)
from app.services.decision_evidence.common import (
    MAX_EDGES,
    MAX_NODES,
    NODE_TYPE_ORDER,
    as_mapping as _as_mapping,
    list_of_text as _list_of_text,
    mapping_list as _mapping_list,
    now_iso as _now_iso,
    procurement_requirement_node_ids as procurement_requirement_node_ids,
    sha256 as _sha256,
    text as _text,
)
from app.services.decision_evidence.project_records import (
    ProjectRecordEvidenceMixin,
)


class DecisionEvidenceService:
    """Build a projection from already-authorized, already-loaded records.

    Route authorization and store access intentionally remain outside this service.
    Review inputs must be UI-safe summaries; the allowlist below remains a second
    defensive boundary against accidental identity or receipt disclosure.
    """

    def build(
        self,
        *,
        project_id: str,
        bundle_type: str,
        procurement_record: object | None = None,
        review_summaries: Iterable[object] = (),
        council_session: object | None = None,
        project_documents: Iterable[object] = (),
        approval_records: Iterable[object] = (),
        report_workflows: Iterable[object] = (),
        knowledge_metadata: Iterable[object] = (),
        generated_at: str | None = None,
    ) -> DecisionEvidenceMapResponse:
        if not _text(project_id) or not _text(bundle_type):
            raise ValueError("project_id and bundle_type must be non-empty")

        builder = _ProjectionBuilder(project_id=project_id, bundle_type=bundle_type)
        procurement = _as_mapping(procurement_record)
        council = _as_mapping(council_session)
        documents = [_as_mapping(item) for item in project_documents]
        approvals = [_as_mapping(item) for item in approval_records]
        workflows = [_as_mapping(item) for item in report_workflows]

        builder.add_procurement(procurement)
        builder.add_council(council, procurement)
        builder.add_documents(documents)
        builder.add_reviews(review_summaries)
        builder.add_approvals(approvals)
        builder.add_workflows(workflows)
        builder.add_knowledge(knowledge_metadata)
        return builder.finish(generated_at=generated_at or _now_iso())


class _ProjectionBuilder(ProjectRecordEvidenceMixin):
    def __init__(self, *, project_id: str, bundle_type: str) -> None:
        self.project_id = project_id
        self.bundle_type = bundle_type
        self.nodes: dict[str, DecisionEvidenceNode] = {}
        self.edges: dict[str, DecisionEvidenceEdge] = {}
        self.diagnostics: list[DecisionEvidenceDiagnostic] = []
        self.coverage: list[DecisionEvidenceCoverageItem] = []
        self.source_revisions: dict[tuple[str, str], DecisionEvidenceSourceRevision] = {}
        self.document_ids: set[str] = set()
        self.document_review_packets: dict[str, str] = {}
        self.procurement_id = ""
        self.recommendation_node_id = ""
        self.council_node_id = ""
        self.council_session_id = ""
        self.selected_workflow: dict[str, Any] | None = None

    def _add_source_revision(
        self,
        *,
        source_kind: str,
        source_id: str,
        revision: str,
        content: object,
    ) -> None:
        if not source_kind or not source_id:
            return
        self.source_revisions[(source_kind, source_id)] = DecisionEvidenceSourceRevision(
            source_kind=source_kind,
            source_id=source_id,
            revision=revision,
            content_sha256=_sha256(content),
        )

    def _add_node(
        self,
        *,
        node_id: str,
        node_type: str,
        label: str,
        status: str,
        summary: str,
        updated_at: str,
        evidence_level: str,
        coverage_status: str | None = None,
        diagnostic_codes: Iterable[str] = (),
        actual_export_observed: bool = False,
    ) -> None:
        if node_id in self.nodes:
            return
        self.nodes[node_id] = DecisionEvidenceNode(
            node_id=node_id,
            node_type=node_type,
            label=label or node_id,
            status=status,
            summary=summary,
            updated_at=updated_at,
            evidence_level=evidence_level,
            coverage_status=coverage_status,
            diagnostic_codes=sorted(set(diagnostic_codes)),
            actual_export_observed=actual_export_observed,
        )

    def _add_edge(
        self,
        *,
        relation_type: str,
        source_node_id: str,
        target_node_id: str,
        status: str,
        source_kind: str,
        source_id: str,
        source_revision: str,
        field_path: str,
        content: object,
        evidence_level: str,
    ) -> None:
        evidence_ref = {
            "source_kind": source_kind,
            "source_id": source_id,
            "source_revision": source_revision,
            "field_path": field_path,
            "content_sha256": _sha256(content),
        }
        edge_id = _sha256(
            {
                "relation": relation_type,
                "source": source_node_id,
                "target": target_node_id,
                "evidence_ref": evidence_ref,
            }
        )
        self.edges[edge_id] = DecisionEvidenceEdge(
            edge_id=edge_id,
            relation_type=relation_type,
            source_node_id=source_node_id,
            target_node_id=target_node_id,
            status=status,
            provenance=DecisionEvidenceProvenance(
                **evidence_ref,
                evidence_level=evidence_level,
            ),
        )

    def _diagnose(
        self,
        *,
        code: str,
        severity: str,
        message: str,
        node_ids: Iterable[str] = (),
        next_action: str = "",
    ) -> None:
        diagnostic = DecisionEvidenceDiagnostic(
            code=code,
            severity=severity,
            message=message,
            node_ids=sorted(set(node_ids)),
            next_action=next_action,
        )
        if diagnostic not in self.diagnostics:
            self.diagnostics.append(diagnostic)

    def add_procurement(self, record: dict[str, Any]) -> None:
        decision_id = _text(record.get("decision_id"))
        if not decision_id or _text(record.get("project_id")) != self.project_id:
            return
        self.procurement_id = decision_id
        revision = _text(record.get("updated_at"))
        source_node_id = f"source:procurement:{decision_id}"
        self._add_source_revision(
            source_kind="procurement_decision",
            source_id=decision_id,
            revision=revision,
            content=record,
        )
        opportunity = _as_mapping(record.get("opportunity"))
        self._add_node(
            node_id=source_node_id,
            node_type="source",
            label=_text(opportunity.get("title")) or "Procurement decision",
            status="current",
            summary=_text(opportunity.get("issuer")),
            updated_at=revision,
            evidence_level="authoritative",
        )

        for snapshot in _mapping_list(record.get("source_snapshots")):
            snapshot_id = _text(snapshot.get("snapshot_id"))
            if not snapshot_id:
                continue
            node_id = f"source:procurement_snapshot:{snapshot_id}"
            self._add_source_revision(
                source_kind="procurement_snapshot",
                source_id=snapshot_id,
                revision=_text(snapshot.get("captured_at")),
                content=snapshot,
            )
            self._add_node(
                node_id=node_id,
                node_type="source",
                label=_text(snapshot.get("source_label")) or snapshot_id,
                status="current",
                summary=_text(snapshot.get("source_kind")),
                updated_at=_text(snapshot.get("captured_at")),
                evidence_level="authoritative",
            )
            self._add_edge(
                relation_type="captured_for",
                source_node_id=node_id,
                target_node_id=source_node_id,
                status="current",
                source_kind="procurement_snapshot",
                source_id=snapshot_id,
                source_revision=_text(snapshot.get("captured_at")),
                field_path="source_snapshots",
                content=snapshot,
                evidence_level="authoritative",
            )

        for item in _mapping_list(record.get("hard_filters")):
            code = _text(item.get("code"))
            if not code:
                continue
            status = _text(item.get("status")) or "unknown"
            node_id = f"requirement:{decision_id}:hard_filter:{code}"
            coverage_status = "missing" if status in {"fail", "unknown"} else "unverifiable"
            self._add_requirement(
                node_id=node_id,
                label=_text(item.get("label")) or code,
                summary=_text(item.get("reason")),
                node_status=status,
                coverage_status=coverage_status,
                evidence=_list_of_text(item.get("evidence")),
                source_id=decision_id,
                source_revision=revision,
                field_path=f"hard_filters.{code}",
                source_node_id=source_node_id,
                content=item,
            )

        for index, item in enumerate(_mapping_list(record.get("checklist_items"))):
            title = _text(item.get("title"))
            if not title:
                continue
            node_id = f"requirement:{decision_id}:checklist:{index}:{_sha256(title)[:12]}"
            status = _text(item.get("status")) or "unknown"
            coverage_status = "missing" if status in {"action_needed", "blocked", "unknown"} else "unverifiable"
            self._add_requirement(
                node_id=node_id,
                label=title,
                summary=_text(item.get("remediation_note")) or _text(item.get("evidence")),
                node_status=status,
                coverage_status=coverage_status,
                evidence=[_text(item.get("evidence"))] if _text(item.get("evidence")) else [],
                source_id=decision_id,
                source_revision=revision,
                field_path=f"checklist_items.{index}",
                source_node_id=source_node_id,
                content=item,
            )

        for index, missing in enumerate(_list_of_text(record.get("missing_data"))):
            node_id = f"requirement:{decision_id}:missing_data:{index}:{_sha256(missing)[:12]}"
            self._add_requirement(
                node_id=node_id,
                label=missing,
                summary="Authoritative procurement record marks this evidence as missing.",
                node_status="missing",
                coverage_status="missing",
                evidence=[],
                source_id=decision_id,
                source_revision=revision,
                field_path=f"missing_data.{index}",
                source_node_id=source_node_id,
                content=missing,
            )

        recommendation = _as_mapping(record.get("recommendation"))
        value = _text(recommendation.get("value"))
        if value:
            self.recommendation_node_id = f"recommendation:{decision_id}"
            self._add_node(
                node_id=self.recommendation_node_id,
                node_type="recommendation",
                label=value,
                status="current",
                summary=_text(recommendation.get("summary")),
                updated_at=_text(recommendation.get("decided_at")) or revision,
                evidence_level="authoritative",
            )
            self._add_edge(
                relation_type="recommends",
                source_node_id=source_node_id,
                target_node_id=self.recommendation_node_id,
                status="current",
                source_kind="procurement_decision",
                source_id=decision_id,
                source_revision=revision,
                field_path="recommendation",
                content=recommendation,
                evidence_level="authoritative",
            )

    def _add_requirement(
        self,
        *,
        node_id: str,
        label: str,
        summary: str,
        node_status: str,
        coverage_status: str,
        evidence: list[str],
        source_id: str,
        source_revision: str,
        field_path: str,
        source_node_id: str,
        content: object,
    ) -> None:
        self._add_node(
            node_id=node_id,
            node_type="requirement",
            label=label,
            status=node_status,
            summary=summary,
            updated_at=source_revision,
            evidence_level="authoritative",
            coverage_status=coverage_status,
        )
        self.coverage.append(
            DecisionEvidenceCoverageItem(
                requirement_node_id=node_id,
                status=coverage_status,
                summary=summary,
                evidence_refs=sorted(evidence),
            )
        )
        self._add_edge(
            relation_type="defines_requirement",
            source_node_id=source_node_id,
            target_node_id=node_id,
            status=node_status,
            source_kind="procurement_decision",
            source_id=source_id,
            source_revision=source_revision,
            field_path=field_path,
            content=content,
            evidence_level="authoritative",
        )
        if coverage_status == "missing":
            self._diagnose(
                code="requirement_evidence_missing",
                severity="warning",
                message="A procurement requirement has missing, blocked, failed, or unknown evidence.",
                node_ids=[node_id],
                next_action="Resolve the authoritative requirement evidence before relying on coverage.",
            )

    def add_council(self, session: dict[str, Any], procurement: dict[str, Any]) -> None:
        session_id = _text(session.get("session_id"))
        if not session_id or _text(session.get("project_id")) != self.project_id:
            return
        self.council_session_id = session_id
        revision = str(session.get("session_revision") or "")
        updated_at = _text(session.get("updated_at"))
        self.council_node_id = f"claim:council:{session_id}:r{revision or '0'}"
        binding_status = _text(session.get("current_procurement_binding_status")) or "current"
        consensus = _as_mapping(session.get("consensus"))
        direction = _text(consensus.get("recommended_direction"))
        self._add_source_revision(
            source_kind="decision_council_session",
            source_id=session_id,
            revision=revision or updated_at,
            content=session,
        )
        self._add_node(
            node_id=self.council_node_id,
            node_type="claim",
            label="Decision Council",
            status=binding_status,
            summary=_text(consensus.get("summary")),
            updated_at=updated_at,
            evidence_level="record_binding",
            diagnostic_codes=["council_binding_stale"] if binding_status == "stale" else [],
        )
        if binding_status == "stale":
            self._diagnose(
                code="council_binding_stale",
                severity="warning",
                message="Decision Council is bound to stale procurement evidence.",
                node_ids=[self.council_node_id],
                next_action="Run Decision Council again after reconciling the procurement record.",
            )
        if self.recommendation_node_id:
            self._add_edge(
                relation_type="interprets",
                source_node_id=self.council_node_id,
                target_node_id=self.recommendation_node_id,
                status=binding_status,
                source_kind="decision_council_session",
                source_id=session_id,
                source_revision=revision or updated_at,
                field_path="consensus.recommended_direction",
                content=direction,
                evidence_level="record_binding",
            )
            recommendation = _text(_as_mapping(procurement.get("recommendation")).get("value"))
            expected_direction = {
                "GO": "proceed",
                "CONDITIONAL_GO": "proceed_with_conditions",
                "NO_GO": "do_not_proceed",
            }.get(recommendation)
            if expected_direction and direction and expected_direction != direction:
                self._diagnose(
                    code="recommendation_council_conflict",
                    severity="warning",
                    message="Procurement recommendation and Decision Council direction conflict.",
                    node_ids=[self.recommendation_node_id, self.council_node_id],
                    next_action="Reconcile the authoritative procurement recommendation before drafting.",
                )

        for index, option in enumerate(_list_of_text(consensus.get("strategy_options"))):
            node_id = f"alternative:{session_id}:r{revision or '0'}:{index}:{_sha256(option)[:12]}"
            self._add_node(
                node_id=node_id,
                node_type="alternative",
                label=option,
                status=binding_status,
                summary="",
                updated_at=updated_at,
                evidence_level="record_binding",
            )
            self._add_edge(
                relation_type="offers",
                source_node_id=self.council_node_id,
                target_node_id=node_id,
                status=binding_status,
                source_kind="decision_council_session",
                source_id=session_id,
                source_revision=revision or updated_at,
                field_path=f"consensus.strategy_options.{index}",
                content=option,
                evidence_level="record_binding",
            )
        risks = _list_of_text(session.get("risks")) + _list_of_text(consensus.get("top_risks"))
        for index, risk in enumerate(sorted(set(risks))):
            node_id = f"risk:{session_id}:r{revision or '0'}:{index}:{_sha256(risk)[:12]}"
            self._add_node(
                node_id=node_id,
                node_type="risk",
                label=risk,
                status=binding_status,
                summary="",
                updated_at=updated_at,
                evidence_level="record_binding",
            )
            self._add_edge(
                relation_type="identifies_risk",
                source_node_id=self.council_node_id,
                target_node_id=node_id,
                status=binding_status,
                source_kind="decision_council_session",
                source_id=session_id,
                source_revision=revision or updated_at,
                field_path=f"risks.{index}",
                content=risk,
                evidence_level="record_binding",
            )

    def add_workflows(self, workflows: Iterable[dict[str, Any]]) -> None:
        candidates = []
        for workflow in workflows:
            if _text(workflow.get("project_id")) != self.project_id:
                continue
            if _text(workflow.get("source_bundle_id")) != self.bundle_type:
                continue
            candidates.append(workflow)
        if not candidates:
            return
        self.selected_workflow = max(
            candidates,
            key=lambda item: (_text(item.get("updated_at")), _text(item.get("report_workflow_id"))),
        )
        workflow = self.selected_workflow
        workflow_id = _text(workflow.get("report_workflow_id"))
        if not workflow_id:
            return
        workflow_document_id = _text(workflow.get("project_document_id"))
        slides = _mapping_list(workflow.get("slides"))
        status = "available" if slides else "blocked"
        node_id = f"export:{workflow_id}:pptx:{_text(workflow.get('current_slide_version')) or '0'}"
        self._add_source_revision(
            source_kind="report_workflow",
            source_id=workflow_id,
            revision=_text(workflow.get("updated_at")),
            content={
                "report_workflow_id": workflow_id,
                "status": workflow.get("status"),
                "project_id": workflow.get("project_id"),
                "project_document_id": workflow_document_id,
                "current_slide_version": workflow.get("current_slide_version"),
                "slides": slides,
            },
        )
        self._add_node(
            node_id=node_id,
            node_type="export",
            label="PPTX export readiness",
            status=status,
            summary="Readiness only; no durable export receipt is observed.",
            updated_at=_text(workflow.get("updated_at")),
            evidence_level="derived",
            diagnostic_codes=["export_evidence_not_observed"],
            actual_export_observed=False,
        )
        if workflow_document_id in self.document_ids:
            self._add_edge(
                relation_type="export_ready_for",
                source_node_id=f"document:{workflow_document_id}",
                target_node_id=node_id,
                status=status,
                source_kind="report_workflow",
                source_id=workflow_id,
                source_revision=_text(workflow.get("updated_at")),
                field_path="project_document_id",
                content=workflow_document_id,
                evidence_level="derived",
            )
        self._diagnose(
            code="export_evidence_not_observed",
            severity="info",
            message="PPTX export readiness exists, but no durable export receipt is stored.",
            node_ids=[node_id],
            next_action="Use the existing Report Workflow export path; this map does not execute exports.",
        )

    def add_knowledge(self, metadata_items: Iterable[object]) -> None:
        for raw in metadata_items:
            metadata = _as_mapping(raw)
            document_id = _text(metadata.get("doc_id"))
            if not document_id:
                continue
            node_id = f"source:knowledge:{document_id}"
            updated_at = _text(metadata.get("created_at"))
            self._add_source_revision(
                source_kind="knowledge_metadata",
                source_id=document_id,
                revision=updated_at,
                content={
                    key: metadata.get(key)
                    for key in ("doc_id", "filename", "created_at", "tags", "applicable_bundles")
                },
            )
            self._add_node(
                node_id=node_id,
                node_type="source",
                label=_text(metadata.get("filename")) or document_id,
                status="current",
                summary="Knowledge metadata only",
                updated_at=updated_at,
                evidence_level="authoritative",
            )

    def finish(self, *, generated_at: str) -> DecisionEvidenceMapResponse:
        nodes = sorted(
            self.nodes.values(),
            key=lambda item: (NODE_TYPE_ORDER[item.node_type], item.node_id),
        )
        allowed_node_ids = {item.node_id for item in nodes[:MAX_NODES]}
        edges = [
            edge
            for edge in self.edges.values()
            if edge.source_node_id in allowed_node_ids and edge.target_node_id in allowed_node_ids
        ]
        edges.sort(key=lambda item: item.edge_id)
        truncated = len(nodes) > MAX_NODES or len(edges) > MAX_EDGES
        nodes = nodes[:MAX_NODES]
        edges = edges[:MAX_EDGES]
        relation_counts = {node.node_id: 0 for node in nodes}
        for edge in edges:
            relation_counts[edge.source_node_id] += 1
            relation_counts[edge.target_node_id] += 1
        nodes = [node.model_copy(update={"relation_count": relation_counts[node.node_id]}) for node in nodes]
        diagnostics = sorted(self.diagnostics, key=lambda item: (item.code, item.node_ids))
        if truncated:
            diagnostics.append(
                DecisionEvidenceDiagnostic(
                    code="projection_truncated",
                    severity="warning",
                    message="Projection exceeded the deterministic node or edge limit.",
                    next_action="Narrow the source records before relying on omitted relationships.",
                )
            )
        coverage = sorted(self.coverage, key=lambda item: item.requirement_node_id)
        coverage = [item for item in coverage if item.requirement_node_id in allowed_node_ids]
        coverage_counts = {status: 0 for status in ("explicit", "candidate", "missing", "unverifiable")}
        for item in coverage:
            coverage_counts[item.status] += 1
        source_revisions = sorted(
            self.source_revisions.values(), key=lambda item: (item.source_kind, item.source_id)
        )
        blueprint = self._proposal_blueprint()
        fingerprint_payload = {
            "contract_version": "decision_evidence_map.v1",
            "project_id": self.project_id,
            "bundle_type": self.bundle_type,
            "source_revisions": [item.model_dump(mode="json") for item in source_revisions],
            "nodes": [item.model_dump(mode="json") for item in nodes],
            "edges": [item.model_dump(mode="json") for item in edges],
            "coverage": [item.model_dump(mode="json") for item in coverage],
            "diagnostics": [item.model_dump(mode="json") for item in diagnostics],
            "truncated": truncated,
            "proposal_blueprint": blueprint.model_dump(mode="json"),
        }
        return DecisionEvidenceMapResponse(
            generated_at=generated_at,
            project_id=self.project_id,
            bundle_type=self.bundle_type,
            projection_fingerprint=_sha256(fingerprint_payload),
            source_revisions=source_revisions,
            nodes=nodes,
            edges=edges,
            coverage=DecisionEvidenceCoverageSummary(
                total=len(coverage),
                explicit=coverage_counts["explicit"],
                candidate=coverage_counts["candidate"],
                missing=coverage_counts["missing"],
                unverifiable=coverage_counts["unverifiable"],
                items=coverage,
            ),
            diagnostics=diagnostics,
            limits=DecisionEvidenceLimits(max_nodes=MAX_NODES, max_edges=MAX_EDGES),
            truncated=truncated,
            proposal_blueprint=blueprint,
            authority=DecisionEvidenceAuthority(),
        )

    def _proposal_blueprint(self) -> DecisionEvidenceProposalBlueprint:
        workflow = self.selected_workflow
        if workflow is None:
            return DecisionEvidenceProposalBlueprint(status="not_observed")
        planning = _as_mapping(workflow.get("planning"))
        slides = []
        for slide in _mapping_list(workflow.get("slides")):
            slides.append(
                DecisionEvidenceProposalSlide(
                    slide_id=_text(slide.get("slide_id")) or f"slide-{slide.get('page', 0)}",
                    title=_text(slide.get("title")),
                    status=_text(slide.get("status")),
                    source_refs=sorted(_list_of_text(slide.get("source_refs"))),
                    reference_refs=sorted(_list_of_text(slide.get("reference_refs"))),
                )
            )
        for plan in _mapping_list(planning.get("slide_plans")):
            slide_id = _text(plan.get("slide_id")) or f"slide-{plan.get('page', 0)}"
            matching = next((slide for slide in slides if slide.slide_id == slide_id), None)
            if matching is None:
                slides.append(
                    DecisionEvidenceProposalSlide(
                        slide_id=slide_id,
                        title=_text(plan.get("title")),
                        required_evidence=sorted(_list_of_text(plan.get("required_evidence"))),
                        data_needs=sorted(_list_of_text(plan.get("data_needs"))),
                    )
                )
            else:
                matching.required_evidence = sorted(_list_of_text(plan.get("required_evidence")))
                matching.data_needs = sorted(_list_of_text(plan.get("data_needs")))
        return DecisionEvidenceProposalBlueprint(
            status="available",
            report_workflow_id=_text(workflow.get("report_workflow_id")) or None,
            workflow_status=_text(workflow.get("status")),
            narrative_arc=_list_of_text(planning.get("narrative_arc")),
            source_refs=sorted(_list_of_text(workflow.get("source_refs"))),
            slides=sorted(slides, key=lambda item: item.slide_id),
            open_questions=sorted(_list_of_text(planning.get("open_questions"))),
            risk_notes=sorted(_list_of_text(planning.get("risk_notes"))),
        )
