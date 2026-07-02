"""app/storage/knowledge/constants.py — knowledge store 상수 정의."""
from __future__ import annotations

MAX_CONTEXT_CHARS = 8_000   # 생성 프롬프트에 주입할 최대 글자 수
MAX_DOCS_PER_PROJECT = 20   # 프로젝트당 최대 보관 문서 수

_LEARNING_MODE_DEFAULT = "reference"
_QUALITY_TIER_DEFAULT = "working"
_LEARNING_MODE_LABELS = {
    "reference": "참고문서",
    "approved_output": "승인본",
    "capability_profile": "역량 프로필",
    "policy": "가이드/기준",
    "template": "우수 템플릿",
}
_QUALITY_TIER_LABELS = {
    "working": "working",
    "silver": "silver",
    "gold": "gold",
}
_LEARNING_MODE_WEIGHTS = {
    "reference": 120,
    "approved_output": 360,
    "capability_profile": 260,
    "policy": 200,
    "template": 220,
}
_QUALITY_TIER_WEIGHTS = {
    "working": 20,
    "silver": 80,
    "gold": 140,
}
_REFERENCE_SUCCESS_WEIGHTS = {
    "draft": 0,
    "reference": 20,
    "approved": 90,
    "awarded": 120,
}
_REFERENCE_SUCCESS_LABELS = {
    "draft": "초안",
    "reference": "참고",
    "approved": "승인",
    "awarded": "수주",
}
_ORGANIZATION_MATCH_SCORE = 80
_REPORT_WORKFLOW_MATCH_SCORE = 110
_REPORT_WORKFLOW_SOURCE_SCORE = 45
_GRAPH_RELATION_LABELS = {
    "contains_artifact": "프로젝트 산출물",
    "scoped_to_organization": "기관 관계",
    "produced_by_workflow": "workflow 관계",
    "applies_to_bundle": "bundle 관계",
    "tagged_as": "topic 관계",
    "approved_for_reuse": "승인 재사용 관계",
    "awarded_for_reuse": "수주 재사용 관계",
}
_GRAPH_RELATION_WEIGHTS = {
    "contains_artifact": 0,
    "scoped_to_organization": 14,
    "produced_by_workflow": 24,
    "applies_to_bundle": 18,
    "tagged_as": 6,
    "approved_for_reuse": 20,
    "awarded_for_reuse": 28,
}
_GRAPH_RELATION_SCORE_CAP = 72
