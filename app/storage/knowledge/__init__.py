"""app/storage/knowledge/ — 프로젝트별 문서 지식 저장소 패키지.

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

이 패키지는 constants/normalizers/scoring/entry 헬퍼 모듈과
store_core_mixin(초기화·CRUD)/store_ranking_mixin(랭킹·컨텍스트 조립)
두 mixin으로 구현을 분리하고, 이를 합성한 단일 공개 클래스
``KnowledgeStore``를 제공한다. ``app.storage.knowledge_store``는
기존 import 경로(``from app.storage.knowledge_store import X``)를
유지하기 위한 facade로 이 패키지의 심볼을 그대로 재노출한다.
"""
from __future__ import annotations

from app.storage.knowledge.constants import (
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
)
from app.storage.knowledge.normalizers import (
    _extract_report_workflow_id,
    _is_report_workflow_source,
    _matches_report_workflow_id,
    _matches_text_scope,
    _normalize_learning_mode,
    _normalize_list,
    _normalize_quality_tier,
    _normalize_reference_year,
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
from app.storage.knowledge.entry import KnowledgeEntry
from app.storage.knowledge.store_core_mixin import KnowledgeStoreCoreMixin, _log
from app.storage.knowledge.store_ranking_mixin import KnowledgeStoreRankingMixin

__all__ = ["KnowledgeEntry", "KnowledgeStore"]


class KnowledgeStore(KnowledgeStoreCoreMixin, KnowledgeStoreRankingMixin):
    """프로젝트별 문서 지식을 로컬 파일로 저장/조회."""
