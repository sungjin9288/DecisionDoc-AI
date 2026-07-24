"""Project document, review, and approval projection behavior."""
from __future__ import annotations

from typing import Any, Iterable

from app.services.decision_evidence.common import as_mapping, list_of_text, text


class ProjectRecordEvidenceMixin:
    """Project-owned records that attach evidence to the decision projection."""

    def add_documents(self, documents: Iterable[dict[str, Any]]) -> None:
        for document in sorted(documents, key=lambda item: text(item.get("doc_id"))):
            doc_id = text(document.get("doc_id"))
            if not doc_id:
                continue
            self.document_ids.add(doc_id)
            review_packet = text(
                document.get("source_procurement_review_packet_sha256")
            )
            if review_packet:
                self.document_review_packets[doc_id] = review_packet
            node_id = f"document:{doc_id}"
            updated_at = text(document.get("generated_at"))
            status = text(document.get("approval_status")) or "draft"
            self._add_source_revision(
                source_kind="project_document",
                source_id=doc_id,
                revision=updated_at,
                content={
                    key: document.get(key)
                    for key in (
                        "doc_id",
                        "request_id",
                        "bundle_id",
                        "generated_at",
                        "approval_id",
                        "approval_status",
                        "source_decision_council_session_id",
                        "source_decision_council_session_revision",
                        "source_procurement_review_packet_sha256",
                        "source_procurement_review_decision",
                        "source_evidence_refs",
                    )
                },
            )
            self._add_node(
                node_id=node_id,
                node_type="document",
                label=text(document.get("title")) or doc_id,
                status=status,
                summary=text(document.get("bundle_id")),
                updated_at=updated_at,
                evidence_level="record_binding",
            )
            document_council_id = text(
                document.get("source_decision_council_session_id")
            )
            if self.council_node_id and document_council_id == self.council_session_id:
                self._add_edge(
                    relation_type="informed_document",
                    source_node_id=self.council_node_id,
                    target_node_id=node_id,
                    status="current",
                    source_kind="project_document",
                    source_id=doc_id,
                    source_revision=updated_at,
                    field_path="source_decision_council_session_id",
                    content=document_council_id,
                    evidence_level="record_binding",
                )
            for index, requirement_node_id in enumerate(
                list_of_text(document.get("source_evidence_refs"))
            ):
                if requirement_node_id not in self.nodes:
                    self._diagnose(
                        code="evidence_reference_unresolved",
                        severity="warning",
                        message=(
                            "A project document references an unavailable requirement node."
                        ),
                        node_ids=[node_id],
                        next_action=(
                            "Refresh the document against the current procurement revision."
                        ),
                    )
                    continue
                requirement_node = self.nodes[requirement_node_id]
                if requirement_node.node_type != "requirement":
                    continue
                self.nodes[requirement_node_id] = requirement_node.model_copy(
                    update={"coverage_status": "explicit"}
                )
                self._mark_requirement_explicit(
                    requirement_node_id=requirement_node_id,
                    document_node_id=node_id,
                )
                self._add_edge(
                    relation_type="explicitly_referenced_by",
                    source_node_id=requirement_node_id,
                    target_node_id=node_id,
                    status="explicit",
                    source_kind="project_document",
                    source_id=doc_id,
                    source_revision=updated_at,
                    field_path=f"source_evidence_refs.{index}",
                    content=requirement_node_id,
                    evidence_level="record_binding",
                )

    def _mark_requirement_explicit(
        self,
        *,
        requirement_node_id: str,
        document_node_id: str,
    ) -> None:
        for index, coverage_item in enumerate(self.coverage):
            if coverage_item.requirement_node_id != requirement_node_id:
                continue
            evidence_refs = sorted(
                set([*coverage_item.evidence_refs, document_node_id])
            )
            self.coverage[index] = coverage_item.model_copy(
                update={
                    "status": "explicit",
                    "summary": (
                        "The project document stores an explicit canonical "
                        "requirement reference. This does not assert requirement "
                        "satisfaction."
                    ),
                    "evidence_refs": evidence_refs,
                }
            )
            return

    def add_reviews(self, review_summaries: Iterable[object]) -> None:
        safe_keys = {
            "packet_sha256",
            "package_id",
            "recommendation",
            "review_status",
            "decision",
            "prepared_at",
            "reviewed_at",
            "reviewed_package_sha256",
            "operational_approval",
            "project_id",
        }
        for raw_summary in review_summaries:
            raw = as_mapping(raw_summary)
            summary = {key: raw.get(key) for key in safe_keys if key in raw}
            packet_sha = text(summary.get("packet_sha256"))
            if not packet_sha or text(summary.get("project_id")) != self.project_id:
                continue
            node_id = f"review:{packet_sha}"
            decision = text(summary.get("decision")) or "pending"
            reviewed_at = text(summary.get("reviewed_at"))
            self._add_source_revision(
                source_kind="procurement_review",
                source_id=packet_sha,
                revision=reviewed_at or text(summary.get("prepared_at")),
                content=summary,
            )
            self._add_node(
                node_id=node_id,
                node_type="review",
                label="Procurement review",
                status=decision,
                summary=text(summary.get("review_status")),
                updated_at=reviewed_at,
                evidence_level="record_binding",
            )
            if decision == "rejected":
                self._diagnose(
                    code="procurement_review_rejected",
                    severity="error",
                    message="An authorized procurement review rejected its packet.",
                    node_ids=[node_id],
                    next_action=(
                        "Resolve the rejected review before treating the package "
                        "as ready."
                    ),
                )
            for document_id in sorted(self.document_ids):
                if not self._document_packet_matches(document_id, packet_sha):
                    continue
                self._add_edge(
                    relation_type="reviewed_document",
                    source_node_id=node_id,
                    target_node_id=f"document:{document_id}",
                    status=decision,
                    source_kind="procurement_review",
                    source_id=packet_sha,
                    source_revision=reviewed_at,
                    field_path="packet_sha256",
                    content=packet_sha,
                    evidence_level="record_binding",
                )

    def _document_packet_matches(self, doc_id: str, packet_sha: str) -> bool:
        return self.document_review_packets.get(doc_id) == packet_sha

    def add_approvals(self, approvals: Iterable[dict[str, Any]]) -> None:
        for approval in sorted(
            approvals,
            key=lambda item: text(item.get("approval_id")),
        ):
            approval_id = text(approval.get("approval_id"))
            if (
                not approval_id
                or text(approval.get("project_id")) != self.project_id
            ):
                continue
            status = text(approval.get("status")) or "draft"
            document_id = text(approval.get("project_document_id"))
            node_id = f"approval:{approval_id}"
            updated_at = text(approval.get("approved_at")) or text(
                approval.get("reviewed_at")
            )
            self._add_source_revision(
                source_kind="approval_record",
                source_id=approval_id,
                revision=updated_at,
                content={
                    key: approval.get(key)
                    for key in (
                        "approval_id",
                        "status",
                        "project_id",
                        "project_document_id",
                        "approved_at",
                        "approved_source_fingerprint",
                        "source_decision_council_document_status",
                        "source_procurement_review_document_status",
                    )
                },
            )
            self._add_node(
                node_id=node_id,
                node_type="approval",
                label="Approval",
                status="approved" if status == "approved" else status,
                summary="",
                updated_at=updated_at,
                evidence_level="authoritative",
            )
            if document_id in self.document_ids:
                self._add_edge(
                    relation_type="approves_document",
                    source_node_id=node_id,
                    target_node_id=f"document:{document_id}",
                    status=status,
                    source_kind="approval_record",
                    source_id=approval_id,
                    source_revision=updated_at,
                    field_path="project_document_id",
                    content=document_id,
                    evidence_level="authoritative",
                )
            stale_source = any(
                text(approval.get(key)).startswith(("stale", "previous"))
                for key in (
                    "source_decision_council_document_status",
                    "source_procurement_review_document_status",
                )
            )
            if stale_source:
                self._diagnose(
                    code="approval_source_stale",
                    severity="warning",
                    message=(
                        "Approval references stale council or procurement review "
                        "evidence."
                    ),
                    node_ids=[node_id],
                    next_action=(
                        "Refresh source evidence and repeat approval review when "
                        "needed."
                    ),
                )
