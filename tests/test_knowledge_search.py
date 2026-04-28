from app.storage.knowledge_search import (
    KnowledgeSearchQuery,
    LocalKeywordBackend,
    SQLiteFtsBackend,
    get_knowledge_search_backend,
    tokenize_knowledge_text,
)


def test_tokenize_knowledge_text_normalizes_korean_english_and_numbers():
    tokens = tokenize_knowledge_text("파주시 모빌리티 Proposal v2", "", None)

    assert {"파주시", "모빌리티", "proposal", "v2"}.issubset(tokens)


def test_knowledge_search_query_tokens_are_sorted_by_backend_match():
    query = KnowledgeSearchQuery(
        title="파주시 모빌리티 제안",
        goal="승인 가능한 제안서",
        bundle_type="proposal_kr",
        source_organization="파주시",
    )
    match = LocalKeywordBackend().match(
        query,
        {
            "filename": "mobility-proposal.docx",
            "tags": ["모빌리티", "제안"],
            "applicable_bundles": ["proposal_kr"],
            "source_organization": "파주시",
            "notes": "승인본",
        },
    )

    assert match.query_terms == sorted(match.query_terms)
    assert match.matched_terms == sorted(match.matched_terms)
    assert {"모빌리티", "제안", "proposal_kr", "파주시"}.issubset(set(match.matched_terms))
    assert match.overlap == len(match.matched_terms)


def test_local_keyword_backend_accepts_comma_separated_metadata_lists():
    query = KnowledgeSearchQuery(title="안전 교통", bundle_type="proposal_kr")
    match = LocalKeywordBackend().match(
        query,
        {
            "filename": "reference.txt",
            "tags": "안전,교통",
            "applicable_bundles": "proposal_kr,report_workflow",
        },
    )

    assert {"안전", "교통", "proposal_kr"}.issubset(set(match.matched_terms))


def test_sqlite_fts_backend_matches_metadata_terms():
    query = KnowledgeSearchQuery(title="스마트 안전", source_organization="국토교통부")
    match = SQLiteFtsBackend().match(
        query,
        {
            "filename": "smart-safety-reference.pdf",
            "tags": ["스마트", "안전"],
            "source_organization": "국토교통부",
            "notes": "스마트 안전 관제 승인본",
        },
    )

    assert match.query_terms == sorted(match.query_terms)
    assert {"스마트", "안전", "국토교통부"}.issubset(set(match.matched_terms))
    assert match.overlap == len(match.matched_terms)


def test_get_knowledge_search_backend_defaults_to_local(monkeypatch):
    monkeypatch.delenv("DECISIONDOC_KNOWLEDGE_SEARCH_BACKEND", raising=False)

    assert get_knowledge_search_backend().name == "local_keyword"


def test_get_knowledge_search_backend_can_select_sqlite_fts(monkeypatch):
    monkeypatch.setenv("DECISIONDOC_KNOWLEDGE_SEARCH_BACKEND", "sqlite_fts")

    assert get_knowledge_search_backend().name == "sqlite_fts"
