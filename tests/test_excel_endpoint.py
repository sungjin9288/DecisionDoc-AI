"""Tests for POST /generate/excel endpoint and excel_service."""

_XLSX_MAGIC = b"PK\x03\x04"  # ZIP/XLSX starts with PK


def _create_client(tmp_path, monkeypatch):
    monkeypatch.setenv("DECISIONDOC_PROVIDER", "mock")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DECISIONDOC_ENV", "dev")
    monkeypatch.setenv("DECISIONDOC_MAINTENANCE", "0")
    monkeypatch.delenv("DECISIONDOC_API_KEY", raising=False)
    monkeypatch.delenv("DECISIONDOC_API_KEYS", raising=False)
    from fastapi.testclient import TestClient
    from app.main import create_app
    return TestClient(create_app())


def test_build_excel_returns_valid_bytes():
    from app.services.excel_service import build_excel
    docs = [{"doc_type": "adr", "markdown": "# 제목\n\n내용\n- 항목1\n- 항목2"}]
    result = build_excel(docs, title="테스트")
    assert result[:4] == _XLSX_MAGIC


def test_build_excel_multiple_docs():
    from app.services.excel_service import build_excel
    docs = [
        {"doc_type": "adr", "markdown": "# ADR\n내용"},
        {"doc_type": "onepager", "markdown": "# 원페이저\n## 요약\n내용"},
    ]
    result = build_excel(docs, title="멀티 문서")
    assert result[:4] == _XLSX_MAGIC


def test_excel_endpoint_returns_200(tmp_path, monkeypatch):
    client = _create_client(tmp_path, monkeypatch)
    res = client.post("/generate/excel", json={"title": "Excel 테스트", "goal": "검증"})
    assert res.status_code == 200


def test_excel_content_type(tmp_path, monkeypatch):
    client = _create_client(tmp_path, monkeypatch)
    res = client.post("/generate/excel", json={"title": "t", "goal": "g"})
    assert "spreadsheetml" in res.headers["content-type"]


def test_excel_content_disposition(tmp_path, monkeypatch):
    client = _create_client(tmp_path, monkeypatch)
    res = client.post("/generate/excel", json={"title": "한글제목", "goal": "g"})
    assert "attachment" in res.headers.get("content-disposition", "")


def test_excel_endpoint_returns_xlsx_magic(tmp_path, monkeypatch):
    client = _create_client(tmp_path, monkeypatch)
    res = client.post("/generate/excel", json={"title": "t", "goal": "g"})
    assert res.content[:4] == _XLSX_MAGIC
