"""Temporal relationship graph for project knowledge metadata.

This module builds a small, dependency-free graph from KnowledgeStore metadata.
It keeps the first phase read-only so retrieval, approval analytics, and future
vector/FTS backends can consume the same relationship facts without changing the
existing document storage format.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


def _normalize_text(value: Any) -> str:
    return str(value or "").strip()


def _normalize_list(values: Any) -> list[str]:
    if not values:
        return []
    if isinstance(values, str):
        values = [item.strip() for item in values.split(",")]
    if not isinstance(values, list):
        return []
    normalized: list[str] = []
    for item in values:
        text = _normalize_text(item)
        if text and text not in normalized:
            normalized.append(text)
    return normalized


def _node_key(prefix: str, value: str) -> str:
    compact = "_".join(_normalize_text(value).lower().split())
    return f"{prefix}:{compact or 'unknown'}"


@dataclass(frozen=True)
class KnowledgeGraphNode:
    node_id: str
    node_type: str
    label: str
    properties: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "node_type": self.node_type,
            "label": self.label,
            "properties": dict(self.properties),
        }


@dataclass(frozen=True)
class KnowledgeGraphEdge:
    edge_id: str
    source_node_id: str
    target_node_id: str
    relation_type: str
    evidence_doc_id: str
    valid_from: float | None = None
    valid_to: float | None = None
    properties: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "edge_id": self.edge_id,
            "source_node_id": self.source_node_id,
            "target_node_id": self.target_node_id,
            "relation_type": self.relation_type,
            "evidence_doc_id": self.evidence_doc_id,
            "valid_from": self.valid_from,
            "valid_to": self.valid_to,
            "properties": dict(self.properties),
        }


class KnowledgeTemporalGraph:
    """In-memory graph representation derived from knowledge metadata."""

    def __init__(self) -> None:
        self._nodes: dict[str, KnowledgeGraphNode] = {}
        self._edges: list[KnowledgeGraphEdge] = []
        self._edge_ids: set[str] = set()

    @property
    def nodes(self) -> list[KnowledgeGraphNode]:
        return list(self._nodes.values())

    @property
    def edges(self) -> list[KnowledgeGraphEdge]:
        return list(self._edges)

    def add_node(
        self,
        *,
        node_id: str,
        node_type: str,
        label: str,
        properties: dict[str, Any] | None = None,
    ) -> None:
        if node_id in self._nodes:
            return
        self._nodes[node_id] = KnowledgeGraphNode(
            node_id=node_id,
            node_type=node_type,
            label=label,
            properties=properties or {},
        )

    def add_edge(
        self,
        *,
        source_node_id: str,
        target_node_id: str,
        relation_type: str,
        evidence_doc_id: str,
        valid_from: float | None = None,
        valid_to: float | None = None,
        properties: dict[str, Any] | None = None,
    ) -> None:
        edge_id = "|".join(
            [
                relation_type,
                source_node_id,
                target_node_id,
                evidence_doc_id,
            ]
        )
        if edge_id in self._edge_ids:
            return
        self._edge_ids.add(edge_id)
        self._edges.append(
            KnowledgeGraphEdge(
                edge_id=edge_id,
                source_node_id=source_node_id,
                target_node_id=target_node_id,
                relation_type=relation_type,
                evidence_doc_id=evidence_doc_id,
                valid_from=valid_from,
                valid_to=valid_to,
                properties=properties or {},
            )
        )

    def summary(self) -> dict[str, Any]:
        node_counts: dict[str, int] = {}
        relation_counts: dict[str, int] = {}
        for node in self._nodes.values():
            node_counts[node.node_type] = node_counts.get(node.node_type, 0) + 1
        for edge in self._edges:
            relation_counts[edge.relation_type] = relation_counts.get(edge.relation_type, 0) + 1
        return {
            "node_count": len(self._nodes),
            "edge_count": len(self._edges),
            "node_counts": node_counts,
            "relation_counts": relation_counts,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "graph_version": "knowledge_temporal_graph.v1",
            "summary": self.summary(),
            "nodes": [node.to_dict() for node in self.nodes],
            "edges": [edge.to_dict() for edge in self.edges],
        }


def build_knowledge_temporal_graph(
    *,
    project_id: str,
    documents: list[dict[str, Any]],
    source_organization: str = "",
    report_workflow_id: str = "",
    bundle_type: str = "",
) -> KnowledgeTemporalGraph:
    """Build a graph from KnowledgeStore index metadata.

    Optional filters mirror the existing context-preview filters and are applied
    before relationship extraction.
    """
    graph = KnowledgeTemporalGraph()
    project_node_id = _node_key("project", project_id)
    graph.add_node(
        node_id=project_node_id,
        node_type="project",
        label=project_id,
        properties={"project_id": project_id},
    )

    expected_org = _normalize_text(source_organization).lower()
    expected_workflow = _normalize_text(report_workflow_id)
    expected_bundle = _normalize_text(bundle_type)

    for meta in documents:
        scope = meta.get("knowledge_scope") if isinstance(meta.get("knowledge_scope"), dict) else {}
        organization = _normalize_text(scope.get("organization") or meta.get("source_organization"))
        workflow_id = _normalize_text(scope.get("report_workflow_id"))
        bundles = _normalize_list(scope.get("bundle_types") or meta.get("applicable_bundles"))
        tags = _normalize_list(scope.get("topic_tags") or meta.get("tags"))

        if expected_org and expected_org not in organization.lower():
            continue
        if expected_workflow and workflow_id != expected_workflow:
            continue
        if expected_bundle and expected_bundle not in bundles:
            continue

        doc_id = _normalize_text(meta.get("doc_id"))
        if not doc_id:
            continue
        created_at = meta.get("created_at") if isinstance(meta.get("created_at"), (int, float)) else None
        artifact_node_id = _node_key("artifact", doc_id)
        graph.add_node(
            node_id=artifact_node_id,
            node_type="artifact",
            label=_normalize_text(meta.get("filename")) or doc_id,
            properties={
                "doc_id": doc_id,
                "learning_mode": _normalize_text(meta.get("learning_mode")),
                "quality_tier": _normalize_text(meta.get("quality_tier")),
                "success_state": _normalize_text(meta.get("success_state")),
                "created_at": created_at,
            },
        )
        graph.add_edge(
            source_node_id=project_node_id,
            target_node_id=artifact_node_id,
            relation_type="contains_artifact",
            evidence_doc_id=doc_id,
            valid_from=created_at,
        )

        if organization:
            org_node_id = _node_key("organization", organization)
            graph.add_node(
                node_id=org_node_id,
                node_type="organization",
                label=organization,
                properties={"organization": organization},
            )
            graph.add_edge(
                source_node_id=artifact_node_id,
                target_node_id=org_node_id,
                relation_type="scoped_to_organization",
                evidence_doc_id=doc_id,
                valid_from=created_at,
            )

        if workflow_id:
            workflow_node_id = _node_key("report_workflow", workflow_id)
            graph.add_node(
                node_id=workflow_node_id,
                node_type="report_workflow",
                label=workflow_id,
                properties={"report_workflow_id": workflow_id},
            )
            graph.add_edge(
                source_node_id=artifact_node_id,
                target_node_id=workflow_node_id,
                relation_type="produced_by_workflow",
                evidence_doc_id=doc_id,
                valid_from=created_at,
            )

        for bundle in bundles:
            bundle_node_id = _node_key("bundle", bundle)
            graph.add_node(
                node_id=bundle_node_id,
                node_type="bundle",
                label=bundle,
                properties={"bundle_type": bundle},
            )
            graph.add_edge(
                source_node_id=artifact_node_id,
                target_node_id=bundle_node_id,
                relation_type="applies_to_bundle",
                evidence_doc_id=doc_id,
                valid_from=created_at,
            )

        for tag in tags:
            tag_node_id = _node_key("topic", tag)
            graph.add_node(
                node_id=tag_node_id,
                node_type="topic",
                label=tag,
                properties={"topic_tag": tag},
            )
            graph.add_edge(
                source_node_id=artifact_node_id,
                target_node_id=tag_node_id,
                relation_type="tagged_as",
                evidence_doc_id=doc_id,
                valid_from=created_at,
            )

        success_state = _normalize_text(meta.get("success_state")).lower()
        if success_state in {"approved", "awarded"}:
            graph.add_edge(
                source_node_id=artifact_node_id,
                target_node_id=project_node_id,
                relation_type="approved_for_reuse" if success_state == "approved" else "awarded_for_reuse",
                evidence_doc_id=doc_id,
                valid_from=created_at,
                properties={"success_state": success_state},
            )

    return graph
