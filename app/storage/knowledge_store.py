"""app/storage/knowledge_store.py — 프로젝트별 문서 지식 저장소.

업로드된 파일에서 추출한 텍스트·스타일 프로필을 프로젝트 단위로 저장.
이후 문서 생성 시 컨텍스트로 자동 주입된다.

저장 구조 (로컬):
    data/tenants/{tenant_id}/knowledge/{project_id}/
        index.json          — 문서 목록 및 메타데이터
        {doc_id}.txt        — 추출된 원본 텍스트
        {doc_id}_style.json — 스타일 프로필 (선택)

컨텍스트 주입 형식:
    [프로젝트 지식: {project_id}]
    문서1: {filename} ...
    ---
    문서2: {filename} ...

구현은 ``app.storage.knowledge`` 패키지로 분리되었다 (constants,
normalizers, scoring, entry 헬퍼 모듈 + store_core_mixin/
store_ranking_mixin 두 mixin). 이 모듈은 기존
``from app.storage.knowledge_store import X`` import 경로를 그대로
유지하기 위한 backward-compatible facade로, 전체 공개·내부 API를
재노출한다.
"""
from __future__ import annotations

from app.storage.knowledge import (
    MAX_CONTEXT_CHARS,
    MAX_DOCS_PER_PROJECT,
    _GRAPH_RELATION_LABELS,
    _GRAPH_RELATION_SCORE_CAP,
    _GRAPH_RELATION_WEIGHTS,
    _LEARNING_MODE_DEFAULT,
    _LEARNING_MODE_LABELS,
    _LEARNING_MODE_WEIGHTS,
    _ORGANIZATION_MATCH_SCORE,
    _QUALITY_TIER_DEFAULT,
    _QUALITY_TIER_LABELS,
    _QUALITY_TIER_WEIGHTS,
    _REFERENCE_SUCCESS_LABELS,
    _REFERENCE_SUCCESS_WEIGHTS,
    _REPORT_WORKFLOW_MATCH_SCORE,
    _REPORT_WORKFLOW_SOURCE_SCORE,
    _build_graph_relationship_index,
    _build_reference_score_breakdown,
    _extract_report_workflow_id,
    _format_graph_relationship_summary,
    _format_reference_ranking_reason,
    _graph_relationship_score,
    _is_report_workflow_source,
    _log,
    _matches_report_workflow_id,
    _matches_text_scope,
    _normalize_learning_mode,
    _normalize_list,
    _normalize_quality_tier,
    _normalize_reference_year,
    _normalize_string,
    _normalize_success_state,
    _reference_recency_score,
    KnowledgeEntry,
    KnowledgeStore,
)

__all__ = ["KnowledgeEntry", "KnowledgeStore"]
