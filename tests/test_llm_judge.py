"""Tests for app/eval/llm_judge.py — mocked to avoid real API calls."""
import pytest
from unittest.mock import patch, MagicMock
from app.eval.llm_judge import (
    _call_openai_judge,
    judge_document,
    judge_bundle_docs,
    LLMJudgeResult,
)


_SAMPLE_DOC = "# 제목\n\n## 배경\n이 문서는 테스트 문서입니다. " * 5


def test_judge_document_no_api_key():
    """Without API key, returns error result (no exception)."""
    with patch.dict("os.environ", {}, clear=True):
        # Ensure OPENAI_API_KEY is not set
        import os
        os.environ.pop("OPENAI_API_KEY", None)
        result = judge_document("adr", _SAMPLE_DOC)
    assert isinstance(result, LLMJudgeResult)
    assert result.error is not None
    assert result.average_score == 0.0


def test_judge_document_with_mocked_api():
    """With mocked API, returns proper scores."""
    mock_response = {
        "context_alignment": 4,
        "specificity": 3,
        "coherence": 5,
        "actionability": 4,
        "brief_feedback": "전반적으로 잘 작성된 문서입니다. 구체성을 높이면 더 좋겠습니다.",
    }
    with patch("app.eval.llm_judge._call_openai_judge", return_value=mock_response):
        result = judge_document(
            doc_type="adr",
            markdown=_SAMPLE_DOC,
            title="테스트 ADR",
            goal="테스트 목표",
            api_key="sk-test-key",
        )
    assert isinstance(result, LLMJudgeResult)
    assert result.context_alignment == 4.0
    assert result.specificity == 3.0
    assert result.coherence == 5.0
    assert result.actionability == 4.0
    assert result.average_score == 4.0
    assert result.error is None
    assert "전반적으로" in result.brief_feedback


def test_judge_document_api_error():
    """API error returns error result without raising."""
    with patch("app.eval.llm_judge._call_openai_judge", side_effect=Exception("네트워크 오류")):
        result = judge_document("adr", _SAMPLE_DOC, api_key="sk-test")
    assert result.error is not None
    assert "네트워크 오류" in result.error


def test_judge_bundle_docs():
    """judge_bundle_docs returns one result per doc."""
    docs = [
        {"doc_type": "adr", "markdown": _SAMPLE_DOC},
        {"doc_type": "onepager", "markdown": _SAMPLE_DOC},
    ]
    mock_response = {
        "context_alignment": 4, "specificity": 4, "coherence": 4,
        "actionability": 4, "brief_feedback": "좋습니다.",
    }
    with patch("app.eval.llm_judge._call_openai_judge", return_value=mock_response):
        results = judge_bundle_docs(docs, title="t", api_key="sk-test")
    assert len(results) == 2
    assert all(isinstance(r, LLMJudgeResult) for r in results)
    assert results[0].doc_type == "adr"
    assert results[1].doc_type == "onepager"


def test_judge_bundle_docs_empty():
    """Empty docs returns empty list."""
    results = judge_bundle_docs([], api_key="sk-test")
    assert results == []


def test_call_openai_judge_uses_httpx_client():
    response = MagicMock()
    response.json.return_value = {
        "choices": [
            {
                "message": {
                    "content": '{"context_alignment": 4, "specificity": 4, "coherence": 4, "actionability": 4, "brief_feedback": "ok"}'
                }
            }
        ]
    }
    response.raise_for_status = MagicMock()

    client = MagicMock()
    client.__enter__.return_value = client
    client.__exit__.return_value = False
    client.post.return_value = response

    with patch("app.eval.llm_judge.httpx.Client", return_value=client):
        result = _call_openai_judge("prompt", "gpt-4o-mini", "sk-test")

    assert result["context_alignment"] == 4
    client.post.assert_called_once()
