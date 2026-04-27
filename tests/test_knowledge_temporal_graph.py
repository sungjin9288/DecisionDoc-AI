from __future__ import annotations


def test_knowledge_store_builds_temporal_graph_from_metadata(tmp_path):
    from app.storage.knowledge_store import KnowledgeStore

    store = KnowledgeStore("proj-graph", data_dir=str(tmp_path))
    approved = store.add_document(
        "approved-slide.md",
        "승인된 장표 산출물",
        tags=["교통", "안전"],
        learning_mode="approved_output",
        quality_tier="gold",
        applicable_bundles=["proposal_kr", "report_workflow"],
        source_organization="국토교통부",
        success_state="approved",
        source_bundle_id="report_workflow",
        source_request_id="report_workflow:rw-safe-001:slides:4",
    )
    store.add_document(
        "generic-reference.md",
        "일반 참고문서",
        tags=["일반"],
        applicable_bundles=["onepager"],
        source_organization="타기관",
        success_state="draft",
    )

    graph = store.build_temporal_graph(
        source_organization="국토교통부",
        report_workflow_id="rw-safe-001",
        bundle_type="proposal_kr",
    )

    assert graph["graph_version"] == "knowledge_temporal_graph.v1"
    assert graph["summary"]["node_counts"]["project"] == 1
    assert graph["summary"]["node_counts"]["artifact"] == 1
    assert graph["summary"]["node_counts"]["organization"] == 1
    assert graph["summary"]["node_counts"]["report_workflow"] == 1
    assert graph["summary"]["relation_counts"]["contains_artifact"] == 1
    assert graph["summary"]["relation_counts"]["scoped_to_organization"] == 1
    assert graph["summary"]["relation_counts"]["produced_by_workflow"] == 1
    assert graph["summary"]["relation_counts"]["approved_for_reuse"] == 1

    artifact = next(node for node in graph["nodes"] if node["node_type"] == "artifact")
    assert artifact["properties"]["doc_id"] == approved.doc_id
    assert artifact["properties"]["success_state"] == "approved"
    assert all(edge["evidence_doc_id"] == approved.doc_id for edge in graph["edges"])


def test_knowledge_temporal_graph_preserves_awarded_and_topic_relationships(tmp_path):
    from app.storage.knowledge_store import KnowledgeStore

    store = KnowledgeStore("proj-awarded", data_dir=str(tmp_path))
    entry = store.add_document(
        "awarded-proposal.md",
        "수주 제안서",
        tags=["스마트시티", "수주"],
        learning_mode="approved_output",
        quality_tier="gold",
        applicable_bundles=["proposal_kr"],
        source_organization="서울시",
        success_state="awarded",
        source_bundle_id="bundle-001",
        source_request_id="req-001",
    )

    graph = store.build_temporal_graph(bundle_type="proposal_kr")

    topic_labels = {node["label"] for node in graph["nodes"] if node["node_type"] == "topic"}
    relation_types = {edge["relation_type"] for edge in graph["edges"]}

    assert topic_labels == {"스마트시티", "수주"}
    assert "tagged_as" in relation_types
    assert "awarded_for_reuse" in relation_types
    awarded_edge = next(edge for edge in graph["edges"] if edge["relation_type"] == "awarded_for_reuse")
    assert awarded_edge["evidence_doc_id"] == entry.doc_id
    assert awarded_edge["properties"]["success_state"] == "awarded"
