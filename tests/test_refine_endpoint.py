"""Tests for POST /generate/refine endpoint."""
import pytest
from fastapi.testclient import TestClient


def _create_client(tmp_path, monkeypatch):
    monkeypatch.setenv("DECISIONDOC_PROVIDER", "mock")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DECISIONDOC_ENV", "dev")
    monkeypatch.setenv("DECISIONDOC_MAINTENANCE", "0")
    monkeypatch.delenv("DECISIONDOC_API_KEY", raising=False)
    monkeypatch.delenv("DECISIONDOC_API_KEYS", raising=False)
    from app.main import create_app
    return TestClient(create_app())


_SAMPLE_SECTION = """## 기술 결정 배경

현재 모놀리식 아키텍처는 유지보수가 어렵고 배포 속도가 느립니다.
MSA 전환을 통해 팀별 독립 배포가 가능해집니다.
"""


def test_refine_returns_200(tmp_path, monkeypatch):
    client = _create_client(tmp_path, monkeypatch)
    res = client.post("/generate/refine", json={
        "section_content": _SAMPLE_SECTION,
        "instruction": "더 간결하게 작성해주세요.",
    })
    assert res.status_code == 200


def test_refine_has_refined_content(tmp_path, monkeypatch):
    client = _create_client(tmp_path, monkeypatch)
    data = client.post("/generate/refine", json={
        "section_content": _SAMPLE_SECTION,
        "instruction": "핵심만 남기고 간결하게",
    }).json()
    assert "refined_content" in data
    assert isinstance(data["refined_content"], str)
    assert len(data["refined_content"]) > 0


def test_refine_has_request_id(tmp_path, monkeypatch):
    client = _create_client(tmp_path, monkeypatch)
    data = client.post("/generate/refine", json={
        "section_content": _SAMPLE_SECTION,
        "instruction": "영어로 번역해주세요",
    }).json()
    assert "request_id" in data
    assert data["request_id"]


def test_refine_has_length_info(tmp_path, monkeypatch):
    client = _create_client(tmp_path, monkeypatch)
    data = client.post("/generate/refine", json={
        "section_content": _SAMPLE_SECTION,
        "instruction": "더 상세하게",
    }).json()
    assert "original_length" in data
    assert "refined_length" in data
    assert data["original_length"] == len(_SAMPLE_SECTION.strip())


def test_refine_missing_section_content(tmp_path, monkeypatch):
    client = _create_client(tmp_path, monkeypatch)
    res = client.post("/generate/refine", json={"instruction": "더 간결하게"})
    assert res.status_code == 422


def test_refine_missing_instruction(tmp_path, monkeypatch):
    client = _create_client(tmp_path, monkeypatch)
    res = client.post("/generate/refine", json={"section_content": _SAMPLE_SECTION})
    assert res.status_code == 422


def test_refine_empty_section_content(tmp_path, monkeypatch):
    client = _create_client(tmp_path, monkeypatch)
    res = client.post("/generate/refine", json={
        "section_content": "",
        "instruction": "개선해주세요",
    })
    assert res.status_code == 422


def test_refine_with_context(tmp_path, monkeypatch):
    client = _create_client(tmp_path, monkeypatch)
    res = client.post("/generate/refine", json={
        "section_content": _SAMPLE_SECTION,
        "instruction": "더 기술적으로 상세하게",
        "context": "이 문서는 결제 시스템 MSA 전환에 관한 ADR입니다.",
        "bundle_type": "tech_decision",
    })
    assert res.status_code == 200


def test_refine_too_long_content(tmp_path, monkeypatch):
    client = _create_client(tmp_path, monkeypatch)
    huge = "A" * 9000
    res = client.post("/generate/refine", json={
        "section_content": huge,
        "instruction": "개선해주세요",
    })
    assert res.status_code == 422
