"""Deterministic review handoff derived from authorized project records."""
from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable
from typing import Any, Literal

from pydantic import ValidationError

from app.schemas.decision_evidence import (
    DecisionEvidenceAuthority,
    DecisionEvidenceMapResponse,
    GuidedDecisionReviewDispositionReceipt,
    GuidedDecisionReviewHandoffResponse,
    GuidedDecisionReviewNextCheck,
    GuidedDecisionReviewRecheckReceipt,
    GuidedDecisionReviewStage,
    require_complete_guided_decision_review_disposition_receipt,
    require_complete_guided_decision_review_handoff,
    require_complete_guided_decision_review_recheck_receipt,
)
from app.services.decision_evidence.common import (
    as_mapping,
    canonical_json,
    mapping_list,
    text,
)


_OVERRIDE_REASON_PATTERN = re.compile(
    r"\[override_reason ts=[^\s\]]+ actor=[^\]]+\]"
    r"[\s\S]*?\[/override_reason\]"
)


class GuidedDecisionReviewService:
    """Build a review-only handoff without adding operational authority."""

    def build(
        self,
        *,
        projection: DecisionEvidenceMapResponse,
        procurement_record: object | None,
        review_summaries: Iterable[object],
        council_session: object | None,
        project_documents: Iterable[object],
    ) -> GuidedDecisionReviewHandoffResponse:
        decision = as_mapping(procurement_record)
        council = as_mapping(council_session)
        reviews = [as_mapping(item) for item in review_summaries]
        documents = [as_mapping(item) for item in project_documents]
        diagnostics = [
            item
            for item in projection.diagnostics
            if not (
                item.code == "export_evidence_not_observed"
                and item.severity == "info"
            )
        ]
        errors = [item for item in diagnostics if item.severity == "error"]
        warnings = [item for item in diagnostics if item.severity == "warning"]
        diagnostic_codes = {item.code for item in diagnostics}

        opportunity = as_mapping(decision.get("opportunity"))
        recommendation = as_mapping(decision.get("recommendation"))
        recommendation_value = text(recommendation.get("value"))
        blocking_filters = sum(
            1
            for item in mapping_list(decision.get("hard_filters"))
            if item.get("blocking") is True and text(item.get("status")) == "fail"
        )
        missing_decision_data = len(decision.get("missing_data") or [])
        no_go_without_override = (
            recommendation_value == "NO_GO"
            and not _OVERRIDE_REASON_PATTERN.search(text(decision.get("notes")))
        )
        council_stale = (
            text(council.get("current_procurement_binding_status")) == "stale"
            or "council_binding_stale" in diagnostic_codes
        )
        council_conflict = (
            self._has_council_conflict(council, recommendation_value)
            or "recommendation_council_conflict" in diagnostic_codes
        )

        coverage = projection.coverage
        latest_review = self._latest_review(reviews)
        latest_review_decision = text(latest_review.get("decision"))
        latest_review_pending = (
            bool(latest_review)
            and text(latest_review.get("review_status")) == "pending"
        )
        latest_document = self._latest_document(
            documents,
            bundle_type=projection.bundle_type,
        )
        document_statuses = self._document_statuses(latest_document)
        document_current = bool(document_statuses) and all(
            status == "current" for status in document_statuses
        )
        document_needs_attention = bool(latest_document) and not document_current

        no_go_observation = (
            "NO_GO not applicable"
            if recommendation_value != "NO_GO"
            else (
                "NO_GO exception record not observed"
                if no_go_without_override
                else "NO_GO exception record observed"
            )
        )
        stages = [
            GuidedDecisionReviewStage(
                name="Decision",
                status=(
                    "not_observed"
                    if not opportunity or not recommendation_value
                    else (
                        "needs_attention"
                        if (
                            blocking_filters
                            or missing_decision_data
                            or coverage.missing
                            or no_go_without_override
                            or council_stale
                            or council_conflict
                        )
                        else "observed"
                    )
                ),
                evidence=(
                    "Opportunity or recommendation not observed."
                    if not opportunity or not recommendation_value
                    else (
                        f"{blocking_filters} blocking filter, "
                        f"{missing_decision_data + coverage.missing} missing item, "
                        f"{no_go_observation}."
                    )
                ),
            ),
            GuidedDecisionReviewStage(
                name="Evidence",
                status=(
                    "needs_attention"
                    if (
                        errors
                        or projection.truncated
                        or coverage.missing
                        or warnings
                        or coverage.candidate
                        or coverage.unverifiable
                    )
                    else ("observed" if projection.nodes else "not_observed")
                ),
                evidence=(
                    f"{len(errors)} error, {len(warnings)} warning, "
                    f"{coverage.missing} missing, {coverage.candidate} candidate, "
                    f"{coverage.unverifiable} unverifiable"
                    f"{', projection truncated' if projection.truncated else ''}."
                ),
            ),
            GuidedDecisionReviewStage(
                name="Review",
                status=(
                    "not_observed"
                    if not latest_review
                    else (
                        "needs_attention"
                        if latest_review_decision in {"rejected", "changes_requested"}
                        else ("in_review" if latest_review_pending else "observed")
                    )
                ),
                evidence=self._review_evidence(
                    latest_review,
                    decision=latest_review_decision,
                    pending=latest_review_pending,
                ),
            ),
            GuidedDecisionReviewStage(
                name="Documents",
                status=(
                    "not_observed"
                    if not latest_document
                    else ("needs_attention" if document_needs_attention else "observed")
                ),
                evidence=self._document_evidence(
                    latest_document,
                    bundle_type=projection.bundle_type,
                    statuses=document_statuses,
                    current=document_current,
                ),
            ),
        ]
        next_check = self._next_check(
            projection=projection,
            has_opportunity=bool(opportunity),
            recommendation_value=recommendation_value,
            blocking_filters=blocking_filters,
            missing_decision_data=missing_decision_data,
            no_go_without_override=no_go_without_override,
            council_stale=council_stale,
            council_conflict=council_conflict,
            latest_review=latest_review,
            latest_review_decision=latest_review_decision,
            latest_review_pending=latest_review_pending,
            latest_document=latest_document,
            document_needs_attention=document_needs_attention,
            error_count=len(errors),
            warning_count=len(warnings),
        )
        overall_state = (
            "Review in progress"
            if next_check.stage == "Review" and latest_review_pending
            else (
                "No blocking signal observed"
                if (
                    next_check.stage == "Evidence"
                    and next_check.instruction == "Inspect the evidence overview."
                )
                else "Needs review"
            )
        )
        return GuidedDecisionReviewHandoffResponse(
            contract_version="guided-decision-review-handoff.v1",
            source_contract_version="decision_evidence_map.v1",
            source_generated_at=projection.generated_at,
            project_id=projection.project_id,
            bundle_type=projection.bundle_type,
            projection_fingerprint=projection.projection_fingerprint,
            read_only=True,
            snapshot_atomic=False,
            requires_recheck_before_reliance=True,
            handoff_persisted=False,
            overall_state=overall_state,
            recommended_next_check=next_check,
            stages=stages,
            authority=self._read_only_authority(),
        )

    @staticmethod
    def serialize(handoff: GuidedDecisionReviewHandoffResponse) -> bytes:
        payload = handoff.model_dump(mode="json")
        return (canonical_json(payload) + "\n").encode("utf-8")

    def recheck(
        self,
        *,
        source_handoff: GuidedDecisionReviewHandoffResponse,
        source_handoff_sha256: str,
        current_handoff: GuidedDecisionReviewHandoffResponse,
        expected_project_id: str,
    ) -> GuidedDecisionReviewRecheckReceipt:
        """Compare one exact source handoff with a fresh read-only observation."""
        require_complete_guided_decision_review_handoff(
            source_handoff,
            "source_handoff",
        )
        require_complete_guided_decision_review_handoff(
            current_handoff,
            "current_handoff",
        )
        expected_source_sha256 = hashlib.sha256(
            self.serialize(source_handoff)
        ).hexdigest()
        if source_handoff_sha256 != expected_source_sha256:
            raise ValueError("source_handoff_sha256 does not match")
        if source_handoff.project_id != expected_project_id:
            raise ValueError("source handoff project does not match")
        if current_handoff.project_id != expected_project_id:
            raise ValueError("current handoff project does not match")
        if source_handoff.bundle_type != current_handoff.bundle_type:
            raise ValueError("source and current handoff bundle types do not match")

        source_fingerprint = self.review_state_fingerprint(source_handoff)
        current_fingerprint = self.review_state_fingerprint(current_handoff)
        return GuidedDecisionReviewRecheckReceipt(
            contract_version="guided-decision-review-recheck-receipt.v1",
            source_handoff=source_handoff,
            source_handoff_sha256=source_handoff_sha256,
            current_handoff=current_handoff,
            current_handoff_sha256=hashlib.sha256(
                self.serialize(current_handoff)
            ).hexdigest(),
            source_review_state_fingerprint_sha256=source_fingerprint,
            current_review_state_fingerprint_sha256=current_fingerprint,
            review_state_status=(
                "unchanged"
                if source_fingerprint == current_fingerprint
                else "changed"
            ),
            fingerprint_algorithm="sha256",
            volatile_fields_excluded=["source_generated_at"],
            review_state_only=True,
            review_only=True,
            read_only=True,
            snapshot_atomic=False,
            requires_recheck_before_reliance=True,
            recheck_persisted=False,
            authority=self._read_only_authority(),
        )

    @staticmethod
    def serialize_recheck(
        receipt: GuidedDecisionReviewRecheckReceipt,
    ) -> bytes:
        payload = receipt.model_dump(mode="json")
        return (canonical_json(payload) + "\n").encode("utf-8")

    def issue_disposition(
        self,
        *,
        source_recheck_receipt: GuidedDecisionReviewRecheckReceipt,
        source_recheck_receipt_sha256: str,
        review_disposition: Literal[
            "acknowledged_unchanged",
            "new_handoff_required",
            "review_deferred",
        ],
        expected_project_id: str,
    ) -> GuidedDecisionReviewDispositionReceipt:
        """Bind one allowlisted review disposition to an exact H127 receipt."""
        receipt = self.validate_recheck_receipt(
            source_recheck_receipt,
            expected_sha256=source_recheck_receipt_sha256,
            expected_project_id=expected_project_id,
        )
        allowed = {
            "unchanged": {"acknowledged_unchanged", "review_deferred"},
            "changed": {"new_handoff_required", "review_deferred"},
        }
        if review_disposition not in allowed[receipt.review_state_status]:
            raise ValueError("review disposition does not match review state")

        current = receipt.current_handoff
        binding = {
            "project_id": expected_project_id,
            "bundle_type": current.bundle_type,
            "source_recheck_receipt_sha256": source_recheck_receipt_sha256,
            "current_handoff_sha256": receipt.current_handoff_sha256,
            "current_review_state_fingerprint_sha256": (
                receipt.current_review_state_fingerprint_sha256
            ),
            "review_state_status": receipt.review_state_status,
            "review_disposition": review_disposition,
        }
        return GuidedDecisionReviewDispositionReceipt(
            project_id=expected_project_id,
            bundle_type=current.bundle_type,
            source_recheck_receipt=receipt,
            source_recheck_receipt_sha256=source_recheck_receipt_sha256,
            current_handoff_sha256=receipt.current_handoff_sha256,
            current_review_state_fingerprint_sha256=(
                receipt.current_review_state_fingerprint_sha256
            ),
            review_state_status=receipt.review_state_status,
            review_disposition=review_disposition,
            disposition_binding_sha256=hashlib.sha256(
                canonical_json(binding).encode("utf-8")
            ).hexdigest(),
        )

    def validate_recheck_receipt(
        self,
        receipt: GuidedDecisionReviewRecheckReceipt,
        *,
        expected_sha256: str,
        expected_project_id: str,
    ) -> GuidedDecisionReviewRecheckReceipt:
        """Revalidate an exact H127 receipt before deriving another artifact."""
        require_complete_guided_decision_review_recheck_receipt(receipt)
        try:
            receipt = GuidedDecisionReviewRecheckReceipt.model_validate(
                receipt.model_dump(mode="json"),
                strict=True,
            )
        except ValidationError as exc:
            raise ValueError("invalid source recheck receipt") from exc

        if (
            hashlib.sha256(self.serialize_recheck(receipt)).hexdigest()
            != expected_sha256
        ):
            raise ValueError("source_recheck_receipt_sha256 does not match")
        source = receipt.source_handoff
        current = receipt.current_handoff
        if (
            source.project_id != expected_project_id
            or current.project_id != expected_project_id
        ):
            raise ValueError("source recheck receipt project does not match")
        if source.bundle_type != current.bundle_type:
            raise ValueError("source and current handoff bundle types do not match")
        if (
            hashlib.sha256(self.serialize(source)).hexdigest()
            != receipt.source_handoff_sha256
        ):
            raise ValueError("source handoff hash does not match")
        if (
            hashlib.sha256(self.serialize(current)).hexdigest()
            != receipt.current_handoff_sha256
        ):
            raise ValueError("current handoff hash does not match")

        source_fingerprint = self.review_state_fingerprint(source)
        current_fingerprint = self.review_state_fingerprint(current)
        if (
            source_fingerprint
            != receipt.source_review_state_fingerprint_sha256
        ):
            raise ValueError("source review state fingerprint does not match")
        if (
            current_fingerprint
            != receipt.current_review_state_fingerprint_sha256
        ):
            raise ValueError("current review state fingerprint does not match")
        expected_status = (
            "unchanged"
            if source_fingerprint == current_fingerprint
            else "changed"
        )
        if receipt.review_state_status != expected_status:
            raise ValueError("review state status does not match")
        return receipt

    def validate_disposition_receipt(
        self,
        receipt: GuidedDecisionReviewDispositionReceipt,
        *,
        expected_sha256: str,
        expected_project_id: str,
        expected_bundle_type: str,
    ) -> GuidedDecisionReviewDispositionReceipt:
        """Revalidate one exact H128 receipt before durable identity binding."""
        require_complete_guided_decision_review_disposition_receipt(receipt)
        try:
            receipt = GuidedDecisionReviewDispositionReceipt.model_validate(
                receipt.model_dump(mode="json"),
                strict=True,
            )
        except ValidationError as exc:
            raise ValueError("invalid source disposition receipt") from exc
        if (
            hashlib.sha256(self.serialize_disposition(receipt)).hexdigest()
            != expected_sha256
        ):
            raise ValueError("source_disposition_receipt_sha256 does not match")
        if (
            receipt.project_id != expected_project_id
            or receipt.bundle_type != expected_bundle_type
        ):
            raise ValueError("source disposition receipt scope does not match")

        recheck = self.validate_recheck_receipt(
            receipt.source_recheck_receipt,
            expected_sha256=receipt.source_recheck_receipt_sha256,
            expected_project_id=expected_project_id,
        )
        if recheck.current_handoff.bundle_type != expected_bundle_type:
            raise ValueError("source disposition receipt bundle does not match")
        if (
            receipt.current_handoff_sha256 != recheck.current_handoff_sha256
            or receipt.current_review_state_fingerprint_sha256
            != recheck.current_review_state_fingerprint_sha256
            or receipt.review_state_status != recheck.review_state_status
        ):
            raise ValueError("source disposition receipt projection does not match")

        allowed = {
            "unchanged": {"acknowledged_unchanged", "review_deferred"},
            "changed": {"new_handoff_required", "review_deferred"},
        }
        if receipt.review_disposition not in allowed[receipt.review_state_status]:
            raise ValueError("review disposition does not match review state")
        binding = {
            "project_id": expected_project_id,
            "bundle_type": expected_bundle_type,
            "source_recheck_receipt_sha256": receipt.source_recheck_receipt_sha256,
            "current_handoff_sha256": receipt.current_handoff_sha256,
            "current_review_state_fingerprint_sha256": (
                receipt.current_review_state_fingerprint_sha256
            ),
            "review_state_status": receipt.review_state_status,
            "review_disposition": receipt.review_disposition,
        }
        if receipt.disposition_binding_sha256 != hashlib.sha256(
            canonical_json(binding).encode("utf-8")
        ).hexdigest():
            raise ValueError("disposition binding does not match")
        return receipt

    @staticmethod
    def _read_only_authority() -> DecisionEvidenceAuthority:
        return DecisionEvidenceAuthority(
            mutation=False,
            approval=False,
            export_execution=False,
            provider_call=False,
            bid_submission=False,
            legal_contractual_commitment=False,
        )

    @staticmethod
    def serialize_disposition(
        receipt: GuidedDecisionReviewDispositionReceipt,
    ) -> bytes:
        payload = receipt.model_dump(mode="json")
        return (canonical_json(payload) + "\n").encode("utf-8")

    @staticmethod
    def review_state_fingerprint(
        handoff: GuidedDecisionReviewHandoffResponse,
    ) -> str:
        payload = handoff.model_dump(mode="json")
        payload.pop("source_generated_at")
        return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()

    @staticmethod
    def _latest_review(reviews: list[dict[str, Any]]) -> dict[str, Any]:
        if not reviews:
            return {}
        return max(
            reviews,
            key=lambda item: (
                text(item.get("prepared_at")),
                text(item.get("packet_sha256")),
            ),
        )

    @staticmethod
    def _latest_document(
        documents: list[dict[str, Any]],
        *,
        bundle_type: str,
    ) -> dict[str, Any]:
        matching = [
            item for item in documents if text(item.get("bundle_id")) == bundle_type
        ]
        if not matching:
            return {}
        return max(
            matching,
            key=lambda item: (
                text(item.get("generated_at")),
                text(item.get("doc_id")),
            ),
        )

    @staticmethod
    def _document_statuses(document: dict[str, Any]) -> list[str]:
        if not document:
            return []
        return [
            value
            for value in (
                text(document.get("procurement_review_document_status")),
                text(document.get("decision_council_document_status")),
                text(document.get("provenance_status")),
                text(document.get("source_provenance_status")),
            )
            if value
        ]

    @staticmethod
    def _has_council_conflict(
        council: dict[str, Any],
        recommendation_value: str,
    ) -> bool:
        consensus = as_mapping(council.get("consensus"))
        alignment = text(consensus.get("alignment"))
        source_recommendation = text(
            council.get("source_procurement_recommendation_value")
        )
        current_recommendation = (
            text(council.get("current_procurement_recommendation_value"))
            or recommendation_value
        )
        return (
            alignment in {"mixed", "contested"}
            or (
                bool(source_recommendation)
                and bool(current_recommendation)
                and source_recommendation != current_recommendation
            )
        )

    @staticmethod
    def _review_evidence(
        review: dict[str, Any],
        *,
        decision: str,
        pending: bool,
    ) -> str:
        if not review:
            return "No authorized review record observed."
        observation = (
            "pending"
            if pending
            else (
                "acceptance record observed; current freshness not established"
                if decision == "accepted"
                else decision or text(review.get("review_status")) or "observed"
            )
        )
        prepared_at = text(review.get("prepared_at")) or "not recorded"
        return f"Latest record: {observation} · prepared {prepared_at}."

    @staticmethod
    def _document_evidence(
        document: dict[str, Any],
        *,
        bundle_type: str,
        statuses: list[str],
        current: bool,
    ) -> str:
        if not document:
            return f"No {bundle_type} document observed."
        title = text(document.get("title")) or text(document.get("doc_id")) or bundle_type
        if current:
            return f"{title} · current document provenance observed."
        status = (
            f"document status requires review: {', '.join(statuses)}"
            if statuses
            else "current document provenance not observed"
        )
        return f"{title} · {status}."

    @staticmethod
    def _next_check(
        *,
        projection: DecisionEvidenceMapResponse,
        has_opportunity: bool,
        recommendation_value: str,
        blocking_filters: int,
        missing_decision_data: int,
        no_go_without_override: bool,
        council_stale: bool,
        council_conflict: bool,
        latest_review: dict[str, Any],
        latest_review_decision: str,
        latest_review_pending: bool,
        latest_document: dict[str, Any],
        document_needs_attention: bool,
        error_count: int,
        warning_count: int,
    ) -> GuidedDecisionReviewNextCheck:
        if projection.truncated or error_count:
            return GuidedDecisionReviewNextCheck(
                stage="Evidence",
                instruction="Inspect the bounded projection or error diagnostics.",
            )
        if not has_opportunity or not recommendation_value:
            return GuidedDecisionReviewNextCheck(
                stage="Decision",
                instruction="Inspect the missing opportunity or recommendation.",
            )
        if (
            blocking_filters
            or missing_decision_data
            or projection.coverage.missing
            or no_go_without_override
        ):
            return GuidedDecisionReviewNextCheck(
                stage="Decision",
                instruction="Inspect the decision blockers and missing evidence.",
            )
        if council_stale or council_conflict:
            return GuidedDecisionReviewNextCheck(
                stage="Decision",
                instruction="Inspect the Council binding or recommendation conflict.",
            )
        if latest_review_decision in {"rejected", "changes_requested"}:
            return GuidedDecisionReviewNextCheck(
                stage="Review",
                instruction="Inspect the latest review outcome.",
            )
        if latest_review_pending:
            return GuidedDecisionReviewNextCheck(
                stage="Review",
                instruction="Inspect the pending review record.",
            )
        if not latest_review:
            return GuidedDecisionReviewNextCheck(
                stage="Review",
                instruction="Inspect the missing review record.",
            )
        if not latest_document or document_needs_attention:
            return GuidedDecisionReviewNextCheck(
                stage="Documents",
                instruction="Inspect the target bundle document and its provenance.",
            )
        if (
            warning_count
            or projection.coverage.candidate
            or projection.coverage.unverifiable
        ):
            return GuidedDecisionReviewNextCheck(
                stage="Evidence",
                instruction="Inspect warning diagnostics and non-explicit coverage.",
            )
        return GuidedDecisionReviewNextCheck(
            stage="Evidence",
            instruction="Inspect the evidence overview.",
        )
