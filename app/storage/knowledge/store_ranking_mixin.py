"""app/storage/knowledge/store_ranking_mixin.py — reference 랭킹·컨텍스트·스타일 조립.

KnowledgeStore의 컨텍스트 주입용 랭킹(rank_documents_for_context),
temporal graph 조회(build_temporal_graph), 프롬프트 컨텍스트 문자열 조립
(build_context, build_style_context)을 담당한다.
"""
from __future__ import annotations

from typing import Any

from app.storage.knowledge.constants import (
    MAX_CONTEXT_CHARS,
    _LEARNING_MODE_LABELS,
    _LEARNING_MODE_WEIGHTS,
    _ORGANIZATION_MATCH_SCORE,
    _QUALITY_TIER_WEIGHTS,
    _REFERENCE_SUCCESS_WEIGHTS,
    _REPORT_WORKFLOW_MATCH_SCORE,
    _REPORT_WORKFLOW_SOURCE_SCORE,
)
from app.storage.knowledge.normalizers import (
    _is_report_workflow_source,
    _matches_report_workflow_id,
    _matches_text_scope,
    _normalize_learning_mode,
    _normalize_list,
    _normalize_quality_tier,
    _normalize_string,
    _normalize_success_state,
)
from app.storage.knowledge.scoring import (
    _build_graph_relationship_index,
    _build_reference_score_breakdown,
    _format_graph_relationship_summary,
    _format_reference_ranking_reason,
    _graph_relationship_score,
    _reference_recency_score,
)
from app.storage.knowledge_search import KnowledgeSearchQuery
from app.storage.knowledge_temporal_graph import build_knowledge_temporal_graph


class KnowledgeStoreRankingMixin:
    """참고문서 랭킹, temporal graph, 프롬프트 컨텍스트 조립."""

    def rank_documents_for_context(
        self,
        *,
        bundle_type: str | None = None,
        title: str = "",
        goal: str = "",
        source_organization: str = "",
        report_workflow_id: str = "",
    ) -> list[dict[str, Any]]:
        query = KnowledgeSearchQuery(
            title=title,
            goal=goal,
            bundle_type=bundle_type or "",
            source_organization=source_organization,
        )
        graph_relationship_index = _build_graph_relationship_index(
            self.build_temporal_graph(
                source_organization=source_organization,
                report_workflow_id=report_workflow_id,
                bundle_type=bundle_type or "",
            )
        )
        ranked: list[dict[str, Any]] = []
        for meta in self._load_index():
            tags = _normalize_list(meta.get("tags"))
            search_match = self._search_backend.match(query, meta)
            overlap = search_match.overlap
            learning_mode = _normalize_learning_mode(meta.get("learning_mode"))
            quality_tier = _normalize_quality_tier(meta.get("quality_tier"))
            success_state = _normalize_success_state(meta.get("success_state"))
            applicable_bundles = _normalize_list(meta.get("applicable_bundles"))
            bundle_match = bool(bundle_type) and bundle_type in applicable_bundles
            organization_match = _matches_text_scope(meta.get("source_organization"), source_organization)
            knowledge_scope = meta.get("knowledge_scope") if isinstance(meta.get("knowledge_scope"), dict) else {}
            scope_report_workflow_id = knowledge_scope.get("report_workflow_id", "")
            report_workflow_match = (
                _matches_report_workflow_id(scope_report_workflow_id, report_workflow_id)
                or _matches_report_workflow_id(meta.get("source_request_id"), report_workflow_id)
                or _matches_report_workflow_id(meta.get("source_bundle_id"), report_workflow_id)
            )
            workflow_source = _is_report_workflow_source(meta.get("source_bundle_id")) or bool(scope_report_workflow_id)
            recency_score = _reference_recency_score(meta.get("created_at"))
            tag_bonus = min(len(tags), 4) * 4
            score = (
                _LEARNING_MODE_WEIGHTS[learning_mode]
                + _QUALITY_TIER_WEIGHTS[quality_tier]
                + _REFERENCE_SUCCESS_WEIGHTS[success_state]
                + overlap * 28
                + (140 if bundle_match else 0)
                + (_ORGANIZATION_MATCH_SCORE if organization_match else 0)
                + (_REPORT_WORKFLOW_MATCH_SCORE if report_workflow_match else 0)
                + (_REPORT_WORKFLOW_SOURCE_SCORE if workflow_source and not report_workflow_match else 0)
                + recency_score
                + tag_bonus
            )
            if bundle_type and applicable_bundles and not bundle_match:
                score -= 20
            graph_relationships = graph_relationship_index.get(
                _normalize_string(meta.get("doc_id")),
                {"relation_count": 0, "relation_types": [], "relationship_reasons": []},
            )
            graph_relationship_summary = _format_graph_relationship_summary(graph_relationships)
            graph_score = _graph_relationship_score(graph_relationships)
            score += graph_score
            score_breakdown = _build_reference_score_breakdown(
                learning_mode=learning_mode,
                quality_tier=quality_tier,
                success_state=success_state,
                overlap=overlap,
                bundle_type=bundle_type,
                bundle_match=bundle_match,
                applicable_bundles=applicable_bundles,
                tag_count=len(tags),
                organization_match=organization_match,
                report_workflow_match=report_workflow_match,
                workflow_source=workflow_source,
                recency_score=recency_score,
            )
            if graph_relationships.get("relation_count"):
                score_breakdown.append(
                    {
                        "label": "관계 그래프",
                        "detail": graph_relationship_summary or f"{graph_relationships['relation_count']}개 relation",
                        "score": graph_score,
                    }
                )
            scope_summary = _format_reference_ranking_reason(
                bundle_type=bundle_type,
                bundle_match=bundle_match,
                applicable_bundles=applicable_bundles,
                success_state=success_state,
                quality_tier=quality_tier,
                overlap=overlap,
                organization_match=organization_match,
                report_workflow_match=report_workflow_match,
                workflow_source=workflow_source,
                recency_score=recency_score,
            )
            selection_reason = scope_summary
            if graph_relationship_summary:
                selection_reason = f"{selection_reason} · graph {graph_relationship_summary}"
            ranked.append({
                **meta,
                "tags": tags,
                "learning_mode": learning_mode,
                "quality_tier": quality_tier,
                "success_state": success_state,
                "applicable_bundles": applicable_bundles,
                "score": score,
                "query_overlap": overlap,
                "query_terms": search_match.query_terms,
                "matched_query_terms": search_match.matched_terms,
                "search_backend": self._search_backend.name,
                "bundle_match": bundle_match,
                "organization_match": organization_match,
                "report_workflow_match": report_workflow_match,
                "workflow_source": workflow_source,
                "recency_score": recency_score,
                "scope_summary": scope_summary,
                "graph_relationships": graph_relationships,
                "graph_relationship_summary": graph_relationship_summary,
                "graph_relationship_score": graph_score,
                "learning_mode_label": _LEARNING_MODE_LABELS[learning_mode],
                "selection_reason": selection_reason,
                "score_breakdown": score_breakdown,
                "knowledge_scope": knowledge_scope,
            })
        ranked.sort(
            key=lambda item: (item.get("score", 0), item.get("created_at", 0)),
            reverse=True,
        )
        return ranked

    def build_temporal_graph(
        self,
        *,
        source_organization: str = "",
        report_workflow_id: str = "",
        bundle_type: str = "",
    ) -> dict[str, Any]:
        """Build a read-only temporal relationship graph from knowledge metadata."""
        graph = build_knowledge_temporal_graph(
            project_id=self.project_id,
            documents=self._load_index(),
            source_organization=source_organization,
            report_workflow_id=report_workflow_id,
            bundle_type=bundle_type,
        )
        return graph.to_dict()

    def build_context(
        self,
        max_chars: int = MAX_CONTEXT_CHARS,
        *,
        bundle_type: str | None = None,
        title: str = "",
        goal: str = "",
        source_organization: str = "",
        report_workflow_id: str = "",
    ) -> str:
        """생성 프롬프트에 주입할 컨텍스트 문자열 반환.

        최신 문서 순으로 max_chars 이내에서 최대한 포함.
        """
        with self._lock:
            index = self.rank_documents_for_context(
                bundle_type=bundle_type,
                title=title,
                goal=goal,
                source_organization=source_organization,
                report_workflow_id=report_workflow_id,
            )
            if not index:
                return ""

            parts: list[str] = []
            total = 0
            for meta in index:
                text = self._read_document_text(meta)
                snippet = text[:2_000]
                header_lines = [f"[참고문서: {meta['filename']}]"]
                header_lines.append(
                    f"- 학습 분류: {meta['learning_mode_label']} | 품질 등급: {meta['quality_tier']} | 활용 상태: {meta['success_state']}"
                )
                if meta.get("bundle_match") and bundle_type:
                    header_lines.append(f"- 우선 적용 문서: {bundle_type}")
                elif meta.get("applicable_bundles"):
                    header_lines.append(f"- 적용 문서: {', '.join(meta['applicable_bundles'])}")
                if meta.get("selection_reason"):
                    header_lines.append(f"- 선정 이유: {meta['selection_reason']}")
                if meta.get("source_organization") or meta.get("reference_year"):
                    org_bits = [meta.get("source_organization", "")]
                    if meta.get("reference_year"):
                        org_bits.append(str(meta["reference_year"]))
                    header_lines.append(f"- 출처: {' / '.join(bit for bit in org_bits if bit)}")
                if meta.get("notes"):
                    header_lines.append(f"- 활용 메모: {meta['notes']}")
                block = "\n".join(header_lines) + f"\n{snippet}"
                if total + len(block) > max_chars:
                    remaining = max_chars - total
                    if remaining > 200:
                        parts.append(block[:remaining] + "\n...(생략)")
                    break
                parts.append(block)
                total += len(block)

        if not parts:
            return ""
        return (
            f"[프로젝트 지식 학습 컨텍스트: {self.project_id}]\n"
            + "\n\n---\n\n".join(parts)
        )

    def build_style_context(self) -> str:
        """누적 스타일 프로필을 합산해 프롬프트용 문자열 반환."""
        with self._lock:
            index = self._load_index()
            styles = [
                self._read_style(meta)
                for meta in index
                if meta.get("has_style")
            ]

        if not styles:
            return ""

        # 가장 최신 스타일을 우선 적용, 공통 패턴 수집
        latest = styles[-1]
        formality = latest.get("formality", "")
        density = latest.get("density", "")
        endings: list[str] = []
        for s in styles:
            endings.extend(s.get("sentence_endings", []))
        # 빈도 기준 상위 3개
        from collections import Counter
        top_endings = [e for e, _ in Counter(endings).most_common(3)]

        lines = ["[스타일 가이드 (학습된 문서 기반)]"]
        if formality:
            lines.append(f"- 문체: {formality}")
        if density:
            lines.append(f"- 밀도: {density}")
        if top_endings:
            lines.append(f"- 자주 쓰는 문장 종결: {', '.join(top_endings)}")
        if latest.get("summary"):
            lines.append(f"- 스타일 요약: {latest['summary']}")

        return "\n".join(lines)
