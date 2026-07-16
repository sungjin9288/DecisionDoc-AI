"""Project/procurement/decision-council/feedback context injection mixin.

Builds the extra prompt context injected into ``payload`` before a provider
call: knowledge-base references, procurement handoff state, decision-council
consensus context, and few-shot feedback hints.
"""
from __future__ import annotations

import io
import json
import zipfile
from typing import Any

from app.services.decision_council_service import (
    build_procurement_council_generation_context,
    describe_procurement_council_binding,
)
from app.services.generation.context_store import (
    _DECISION_COUNCIL_APPLIED_BUNDLE_IDS,
    _log,
)
from app.services.procurement_review_handoff import (
    PROCUREMENT_REVIEW_HANDOFF_BUNDLE_IDS,
)
from app.tenant import require_tenant_id
from app.services.procurement_decision_package.review_packet import (
    PACKET_MANIFEST_NAME,
    verify_procurement_review_packet,
)


class GenerationContextInjectionMixin:
    """Injects knowledge/procurement/decision-council/feedback context into the payload."""

    def _serialize_applied_reference(self, item: dict[str, Any]) -> dict[str, Any]:
        return {
            "doc_id": str(item.get("doc_id", "") or ""),
            "filename": str(item.get("filename", "") or ""),
            "learning_mode": str(item.get("learning_mode", "") or "reference"),
            "quality_tier": str(item.get("quality_tier", "") or "working"),
            "success_state": str(item.get("success_state", "") or "draft"),
            "applicable_bundles": [
                str(bundle).strip()
                for bundle in (item.get("applicable_bundles") or [])
                if str(bundle).strip()
            ],
            "source_organization": str(item.get("source_organization", "") or ""),
            "reference_year": item.get("reference_year"),
            "tags": [
                str(tag).strip()
                for tag in (item.get("tags") or [])
                if str(tag).strip()
            ],
            "score": int(item.get("score", 0) or 0),
            "query_overlap": int(item.get("query_overlap", 0) or 0),
            "bundle_match": bool(item.get("bundle_match")),
            "graph_relationship_score": int(item.get("graph_relationship_score", 0) or 0),
            "graph_relationship_summary": str(item.get("graph_relationship_summary", "") or ""),
            "selection_reason": str(item.get("selection_reason", "") or ""),
            "score_breakdown": list(item.get("score_breakdown") or []),
        }

    def _inject_project_contexts(
        self,
        payload: dict[str, Any],
        *,
        bundle_type: str,
        tenant_id: str,
        request_id: str,
    ) -> None:
        project_id = payload.get("project_id")
        if not project_id:
            return

        try:
            from app.storage.knowledge_store import KnowledgeStore

            ks = KnowledgeStore(
                project_id,
                data_dir=str(self.data_dir),
                tenant_id=tenant_id,
            )
            ranked_documents = ks.rank_documents_for_context(
                bundle_type=bundle_type,
                title=str(payload.get("title", "") or ""),
                goal=str(payload.get("goal", "") or ""),
            )
            knowledge_ctx = ks.build_context(
                bundle_type=bundle_type,
                title=str(payload.get("title", "") or ""),
                goal=str(payload.get("goal", "") or ""),
            )
            style_ctx = ks.build_style_context()
            if ranked_documents:
                payload["_knowledge_ranked_documents"] = [
                    self._serialize_applied_reference(item)
                    for item in ranked_documents[:5]
                ]
            if knowledge_ctx:
                payload["_knowledge_context"] = knowledge_ctx
                _log.info(
                    "[Knowledge] Injected context for project=%s len=%d request_id=%s",
                    project_id,
                    len(knowledge_ctx),
                    request_id,
                )
            if style_ctx:
                payload["_style_context"] = style_ctx
        except Exception as exc:
            _log.warning("[Knowledge] Failed to load context project=%s: %s", project_id, exc)

        if (
            not self._procurement_copilot_enabled
            or bundle_type not in self._PROCUREMENT_HANDOFF_BUNDLE_IDS
            or self._procurement_store is None
        ):
            procurement_ctx = ""
        else:
            procurement_ctx = self._build_procurement_context(project_id=project_id, tenant_id=tenant_id)
            if procurement_ctx:
                payload["_procurement_context"] = procurement_ctx
                _log.info(
                    "[Procurement] Injected handoff context project=%s bundle=%s len=%d request_id=%s",
                    project_id,
                    bundle_type,
                    len(procurement_ctx),
                    request_id,
                )

        if (
            self._procurement_copilot_enabled
            and bundle_type in PROCUREMENT_REVIEW_HANDOFF_BUNDLE_IDS
            and self._procurement_store is not None
            and self._procurement_review_store is not None
        ):
            review_context, review_metadata, skipped_reason = self._resolve_procurement_review_handoff(
                project_id=project_id,
                tenant_id=tenant_id,
            )
            if review_context:
                payload["_procurement_review_context"] = review_context
                payload.update(review_metadata)
                _log.info(
                    "[ProcurementReview] Injected completed review handoff project=%s bundle=%s packet=%s request_id=%s",
                    project_id,
                    bundle_type,
                    review_metadata["_procurement_review_packet_sha256"],
                    request_id,
                )
            elif skipped_reason:
                payload["_procurement_review_handoff_skipped_reason"] = skipped_reason
                _log.info(
                    "[ProcurementReview] Skipped review handoff project=%s bundle=%s reason=%s request_id=%s",
                    project_id,
                    bundle_type,
                    skipped_reason,
                    request_id,
                )

        if (
            not self._procurement_copilot_enabled
            or bundle_type not in _DECISION_COUNCIL_APPLIED_BUNDLE_IDS
            or self._decision_council_store is None
        ):
            return

        council_session = self._decision_council_store.get_latest(
            tenant_id=tenant_id,
            project_id=project_id,
            use_case="public_procurement",
            target_bundle_type="bid_decision_kr",
        )
        if council_session is None:
            return
        if not self._current_procurement_record_matches_council_session(
            project_id=project_id,
            tenant_id=tenant_id,
            council_session=council_session,
        ):
            payload["_decision_council_handoff_skipped_reason"] = "stale_procurement_context"
            _log.info(
                "[DecisionCouncil] Skipped stale handoff context project=%s bundle=%s session=%s request_id=%s",
                project_id,
                bundle_type,
                council_session.session_id,
                request_id,
            )
            return

        council_context = self._build_decision_council_context(
            council_session,
            bundle_type=bundle_type,
        )
        if not council_context:
            return

        payload["_decision_council_context"] = council_context
        payload["_decision_council_session_id"] = council_session.session_id
        payload["_decision_council_session_revision"] = council_session.session_revision
        payload["_decision_council_direction"] = council_session.consensus.recommended_direction
        payload["_decision_council_use_case"] = council_session.use_case
        payload["_decision_council_target_bundle"] = council_session.target_bundle_type
        payload["_decision_council_applied_bundle"] = bundle_type
        _log.info(
            "[DecisionCouncil] Injected handoff context project=%s bundle=%s session=%s revision=%s request_id=%s",
            project_id,
            bundle_type,
            council_session.session_id,
            council_session.session_revision,
            request_id,
        )

    def _resolve_procurement_review_handoff(
        self,
        *,
        project_id: str,
        tenant_id: str,
    ) -> tuple[str, dict[str, Any], str | None]:
        procurement_record = self._procurement_store.get(project_id, tenant_id=tenant_id)
        if procurement_record is None:
            return "", {}, "procurement_context_missing"

        try:
            reviews = self._procurement_review_store.list_by_project(
                tenant_id=tenant_id,
                project_id=project_id,
            )
        except (KeyError, TypeError, ValueError):
            return "", {}, "invalid_review_evidence"

        completed_reviews = sorted(
            (
                review
                for review in reviews
                if review.review_status == "completed"
            ),
            key=lambda review: (
                str(review.reviewed_at or ""),
                review.prepared_at,
                review.packet_sha256,
            ),
            reverse=True,
        )
        if not completed_reviews:
            return "", {}, "no_completed_review"

        valid_review_found = False
        for review in completed_reviews:
            try:
                packet_content = self._procurement_review_store.read_packet(
                    review,
                    tenant_id=tenant_id,
                    project_id=project_id,
                    packet_sha256=review.packet_sha256,
                )
                verify_procurement_review_packet(packet_content)
                with zipfile.ZipFile(io.BytesIO(packet_content)) as archive:
                    packet_manifest = json.loads(archive.read(PACKET_MANIFEST_NAME))
                source_updated_at = str(packet_manifest.get("source_updated_at") or "").strip()
            except (KeyError, OSError, TypeError, ValueError, zipfile.BadZipFile, json.JSONDecodeError):
                continue

            valid_review_found = True
            if source_updated_at != procurement_record.updated_at:
                continue

            rationale = str(review.receipt.get("rationale") or "").strip()
            context = "\n".join(
                [
                    "완료된 procurement review evidence입니다. 이 결과는 drafting 근거이며 운영 승인이나 입찰 제출 권한이 아닙니다.",
                    f"- packet_sha256: {review.packet_sha256}",
                    f"- reviewer: {review.reviewer}",
                    f"- review_decision: {review.decision}",
                    f"- review_rationale: {rationale}",
                    f"- reviewed_at: {review.reviewed_at}",
                    "- operational_approval: false",
                    "accepted는 검토 증빙만 뜻합니다. changes_requested 또는 rejected는 수정 요구와 남은 위험으로 명시하세요.",
                ]
            )
            return context, {
                "_procurement_review_packet_sha256": review.packet_sha256,
                "_procurement_review_decision": review.decision,
                "_procurement_reviewed_at": review.reviewed_at,
                "_procurement_review_source_updated_at": source_updated_at,
                "_procurement_review_operational_approval": False,
            }, None

        reason = "stale_procurement_review" if valid_review_found else "invalid_review_evidence"
        return "", {}, reason

    def _build_procurement_context(self, *, project_id: str, tenant_id: str) -> str:
        record = self._procurement_store.get(project_id, tenant_id=tenant_id)
        if record is None:
            return ""

        opportunity = record.opportunity
        recommendation = record.recommendation
        lines: list[str] = [
            "프로젝트 공공조달 의사결정 상태입니다. 아래 structured state를 문서 작성의 source of truth로 사용하세요.",
        ]
        if opportunity is not None:
            lines.extend(
                [
                    f"- 공고명: {opportunity.title}",
                    f"- 발주기관: {opportunity.issuer or '미상'}",
                    f"- 예산: {opportunity.budget or '미확인'}",
                    f"- 마감: {opportunity.deadline or '미확인'}",
                    f"- 입찰방식: {opportunity.bid_type or '미확인'}",
                    f"- 카테고리: {opportunity.category or '미확인'}",
                ]
            )
            if opportunity.source_url:
                lines.append(f"- 원문 URL: {opportunity.source_url}")

        if recommendation is not None:
            lines.extend(
                [
                    f"- 현재 추천 결론: {recommendation.value}",
                    f"- 추천 요약: {recommendation.summary or '요약 없음'}",
                ]
            )

        if record.hard_filters:
            lines.append("Hard filter 결과:")
            for item in record.hard_filters[:8]:
                blocking = " / blocking" if item.blocking else ""
                reason = f" / {item.reason}" if item.reason else ""
                lines.append(f"- {item.label}: {item.status}{blocking}{reason}")

        if record.soft_fit_score is not None:
            lines.append(
                f"- Soft-fit score: {record.soft_fit_score:.1f} ({record.soft_fit_status})"
            )
        elif record.soft_fit_status:
            lines.append(f"- Soft-fit score status: {record.soft_fit_status}")

        if record.missing_data:
            lines.append("확인되지 않은 데이터:")
            for item in record.missing_data[:8]:
                lines.append(f"- {item}")

        actionable_checklist = [
            item for item in record.checklist_items if item.status in {"blocked", "action_needed"}
        ]
        if actionable_checklist:
            lines.append("입찰 준비 체크리스트 중 조치 필요 항목:")
            for item in actionable_checklist[:10]:
                owner = f" / owner={item.owner}" if item.owner else ""
                due = f" / due={item.due_date}" if item.due_date else ""
                remediation = f" / {item.remediation_note}" if item.remediation_note else ""
                lines.append(
                    f"- [{item.category}] {item.title}: {item.status}, severity={item.severity}"
                    f"{owner}{due}{remediation}"
                )

        if record.score_breakdown:
            lines.append("Soft-fit factor breakdown:")
            for item in record.score_breakdown[:8]:
                lines.append(
                    f"- {item.label}: score={item.score:.1f}, weight={item.weight:.2f}, "
                    f"weighted={item.weighted_score:.1f}, status={item.status}"
                )

        if record.capability_profile is not None:
            lines.extend(
                [
                    f"- capability_profile.source_ref: {record.capability_profile.source_ref}",
                    f"- capability_profile.summary: {record.capability_profile.summary or '요약 없음'}",
                ]
            )

        latest_snapshot = record.source_snapshots[-1] if record.source_snapshots else None
        if latest_snapshot is not None:
            payload = self._procurement_store.load_source_snapshot(
                tenant_id=tenant_id,
                project_id=project_id,
                snapshot_id=latest_snapshot.snapshot_id,
            )
            if isinstance(payload, dict):
                extracted_fields = payload.get("extracted_fields") or {}
                structured_context = str(payload.get("structured_context") or "").strip()
                if extracted_fields:
                    lines.append("최신 원문 추출 신호:")
                    for key, value in list(extracted_fields.items())[:12]:
                        rendered = json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value)
                        lines.append(f"- {key}: {rendered[:240]}")
                if structured_context:
                    lines.append("최신 원문/구조화 맥락 요약:")
                    lines.append(structured_context[:2000])

        return "\n".join(lines).strip()

    def _current_procurement_record_matches_council_session(
        self,
        *,
        project_id: str,
        tenant_id: str,
        council_session: Any,
    ) -> bool:
        record = None
        if self._procurement_store is not None:
            record = self._procurement_store.get(project_id, tenant_id=tenant_id)
        binding = describe_procurement_council_binding(
            session=council_session,
            procurement_record=record,
        )
        return binding["status"] == "current"

    def _build_decision_council_context(self, session: Any, *, bundle_type: str) -> str:
        return build_procurement_council_generation_context(
            session,
            bundle_type=bundle_type,
        )

    def _build_feedback_hints(
        self,
        bundle_type: str,
        title: str = "",
        *,
        tenant_id: str,
    ) -> str:
        """Build structured few-shot hints from high-rated feedback examples.

        Returns a formatted string injected into the LLM prompt.
        Each example includes: title, rating, user comment, and per-doc
        section heading + first 800 chars for all doc types.
        """
        tenant_id = require_tenant_id(tenant_id)
        from app.storage.feedback_store import get_feedback_store

        feedback_store = get_feedback_store(
            tenant_id,
            data_dir=self.data_dir,
            backend=self.state_backend,
        )
        examples = feedback_store.get_high_rated_examples(
            bundle_type=bundle_type,
            min_rating=4,
            limit=3,
            doc_content_limit=800,
        )

        if not examples:
            return ""

        blocks: list[str] = ["## 참고: 이전 고품질 생성 예시"]
        for i, ex in enumerate(examples, 1):
            ex_title = ex.get("title") or "(제목 없음)"
            rating = ex.get("rating", 0)
            comment = ex.get("comment", "")
            header = f"\n### 예시 {i} — 제목: {ex_title}  (평점: {rating}/5)"
            if comment:
                header += f"\n사용자 피드백: {comment}"
            blocks.append(header)

            docs: dict = ex.get("docs") or {}
            for doc_type, doc_info in docs.items():
                if not isinstance(doc_info, dict):
                    continue
                heading = doc_info.get("heading") or doc_type
                content = doc_info.get("content", "").strip()
                if not content:
                    continue
                blocks.append(
                    f"\n#### [{doc_type}] {heading}\n```\n{content}\n```"
                )

        if len(blocks) == 1:
            return ""
        return "\n".join(blocks)
