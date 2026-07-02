"""app/storage/knowledge/scoring.py — reference 랭킹 점수·사유·관계 그래프 헬퍼."""
from __future__ import annotations

import time
from typing import Any

from app.storage.knowledge.constants import (
    _GRAPH_RELATION_LABELS,
    _GRAPH_RELATION_SCORE_CAP,
    _GRAPH_RELATION_WEIGHTS,
    _LEARNING_MODE_LABELS,
    _LEARNING_MODE_WEIGHTS,
    _ORGANIZATION_MATCH_SCORE,
    _QUALITY_TIER_LABELS,
    _QUALITY_TIER_WEIGHTS,
    _REFERENCE_SUCCESS_LABELS,
    _REFERENCE_SUCCESS_WEIGHTS,
    _REPORT_WORKFLOW_MATCH_SCORE,
    _REPORT_WORKFLOW_SOURCE_SCORE,
)
from app.storage.knowledge.normalizers import _normalize_list, _normalize_string


def _reference_recency_score(created_at: Any, *, now: float | None = None) -> int:
    try:
        created = float(created_at)
    except (TypeError, ValueError):
        return 0
    age_days = max(0.0, ((time.time() if now is None else now) - created) / 86_400)
    if age_days <= 30:
        return 32
    if age_days <= 180:
        return 18
    if age_days <= 365:
        return 8
    return 0


def _format_reference_ranking_reason(
    *,
    bundle_type: str | None,
    bundle_match: bool,
    applicable_bundles: list[str],
    success_state: str,
    quality_tier: str,
    overlap: int,
    organization_match: bool = False,
    report_workflow_match: bool = False,
    workflow_source: bool = False,
    recency_score: int = 0,
) -> str:
    reasons: list[str] = []
    if report_workflow_match:
        reasons.append("동일 Report Workflow 산출물")
    elif workflow_source:
        reasons.append("Report Workflow 승인본 출처")
    if organization_match:
        reasons.append("기관/고객 scope 일치")
    if bundle_match and bundle_type:
        reasons.append(f"bundle `{bundle_type}` 일치")
    elif bundle_type and applicable_bundles:
        reasons.append(f"적용 bundle {', '.join(applicable_bundles[:2])}")
    if success_state in ("approved", "awarded"):
        reasons.append(f"{_REFERENCE_SUCCESS_LABELS[success_state]} 결과물")
    if quality_tier in ("gold", "silver"):
        reasons.append(f"{_QUALITY_TIER_LABELS[quality_tier]} 등급")
    if overlap > 0:
        reasons.append(f"핵심어 {overlap}개 겹침")
    if recency_score:
        reasons.append("최근 등록 reference")
    if not reasons:
        reasons.append("기본 참고문서 조건 충족")
    return " · ".join(reasons)


def _build_reference_score_breakdown(
    *,
    learning_mode: str,
    quality_tier: str,
    success_state: str,
    overlap: int,
    bundle_type: str | None,
    bundle_match: bool,
    applicable_bundles: list[str],
    tag_count: int,
    organization_match: bool = False,
    report_workflow_match: bool = False,
    workflow_source: bool = False,
    recency_score: int = 0,
) -> list[dict[str, Any]]:
    breakdown: list[dict[str, Any]] = [
        {
            "label": "학습 분류",
            "detail": _LEARNING_MODE_LABELS[learning_mode],
            "score": _LEARNING_MODE_WEIGHTS[learning_mode],
        },
        {
            "label": "품질 등급",
            "detail": _QUALITY_TIER_LABELS[quality_tier],
            "score": _QUALITY_TIER_WEIGHTS[quality_tier],
        },
    ]
    success_score = _REFERENCE_SUCCESS_WEIGHTS[success_state]
    if success_score:
        breakdown.append(
            {
                "label": "활용 상태",
                "detail": _REFERENCE_SUCCESS_LABELS[success_state],
                "score": success_score,
            }
        )
    if overlap:
        breakdown.append(
            {
                "label": "핵심어 겹침",
                "detail": f"{overlap}개",
                "score": overlap * 28,
            }
        )
    if report_workflow_match:
        breakdown.append(
            {
                "label": "동일 workflow",
                "detail": "Report Workflow source_request_id 일치",
                "score": _REPORT_WORKFLOW_MATCH_SCORE,
            }
        )
    elif workflow_source:
        breakdown.append(
            {
                "label": "workflow 출처",
                "detail": "Report Workflow 승인본",
                "score": _REPORT_WORKFLOW_SOURCE_SCORE,
            }
        )
    if organization_match:
        breakdown.append(
            {
                "label": "기관 scope 일치",
                "detail": "source_organization 일치",
                "score": _ORGANIZATION_MATCH_SCORE,
            }
        )
    if bundle_match and bundle_type:
        breakdown.append(
            {
                "label": "bundle 일치",
                "detail": bundle_type,
                "score": 140,
            }
        )
    elif bundle_type and applicable_bundles:
        breakdown.append(
            {
                "label": "bundle 보정",
                "detail": ", ".join(applicable_bundles[:2]),
                "score": -20,
            }
        )
    tag_bonus = min(tag_count, 4) * 4
    if tag_bonus:
        breakdown.append(
            {
                "label": "태그 밀도",
                "detail": f"{min(tag_count, 4)}개 반영",
                "score": tag_bonus,
            }
        )
    if recency_score:
        breakdown.append(
            {
                "label": "최근성",
                "detail": "최근 등록 reference",
                "score": recency_score,
            }
        )
    return breakdown


def _build_graph_relationship_index(graph: dict[str, Any]) -> dict[str, dict[str, Any]]:
    nodes = graph.get("nodes") if isinstance(graph.get("nodes"), list) else []
    edges = graph.get("edges") if isinstance(graph.get("edges"), list) else []
    node_labels = {
        _normalize_string(node.get("node_id")): _normalize_string(node.get("label"))
        for node in nodes
        if isinstance(node, dict)
    }
    by_doc: dict[str, dict[str, Any]] = {}
    for edge in edges:
        if not isinstance(edge, dict):
            continue
        doc_id = _normalize_string(edge.get("evidence_doc_id"))
        relation_type = _normalize_string(edge.get("relation_type"))
        if not doc_id or not relation_type:
            continue
        target_label = node_labels.get(_normalize_string(edge.get("target_node_id")), "")
        entry = by_doc.setdefault(
            doc_id,
            {
                "relation_count": 0,
                "relation_types": [],
                "relationship_reasons": [],
            },
        )
        entry["relation_count"] += 1
        if relation_type not in entry["relation_types"]:
            entry["relation_types"].append(relation_type)
        label = _GRAPH_RELATION_LABELS.get(relation_type, relation_type)
        reason = f"{label}: {target_label}" if target_label else label
        if reason not in entry["relationship_reasons"]:
            entry["relationship_reasons"].append(reason)
    return by_doc


def _format_graph_relationship_summary(graph_relationships: dict[str, Any]) -> str:
    reasons = _normalize_list(graph_relationships.get("relationship_reasons"))
    if not reasons:
        return ""
    return " · ".join(reasons[:4])


def _graph_relationship_score(graph_relationships: dict[str, Any]) -> int:
    relation_types = _normalize_list(graph_relationships.get("relation_types"))
    score = sum(_GRAPH_RELATION_WEIGHTS.get(relation_type, 0) for relation_type in relation_types)
    return min(score, _GRAPH_RELATION_SCORE_CAP)
