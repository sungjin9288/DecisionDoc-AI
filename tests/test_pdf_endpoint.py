"""Tests for POST /generate/pdf endpoint and pdf_service."""
import pytest

from tests.async_helper import run_async

_DOCX_MAGIC = b"%PDF"  # PDF starts with %PDF


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


def test_build_pdf_service_returns_pdf_bytes():
    """build_pdf should return valid PDF bytes (async function, run via asyncio)."""
    from app.services.pdf_service import build_pdf
    docs = [{"doc_type": "adr", "markdown": "# 제목\n\n내용입니다."}]
    pdf_bytes = run_async(build_pdf(docs, title="테스트"))
    assert pdf_bytes[:4] == b"%PDF"


def test_markdown_to_html_renders_table_markup():
    from app.services.pdf_service import _markdown_to_html

    html = _markdown_to_html(
        "| 단계 | 기간 |\n"
        "| --- | --- |\n"
        "| 착수 | 1개월 |\n"
    )

    assert "<table class='markdown-table'>" in html
    assert "<th>단계</th>" in html
    assert "<td>착수</td>" in html


def test_render_html_adds_export_cover_and_section_cards():
    from app.services.pdf_service import _render_html

    html = _render_html(
        [
            {"doc_type": "business_understanding", "markdown": "# 제목\n\n본문 A"},
            {"doc_type": "tech_proposal", "markdown": "# 제목\n\n본문 B"},
        ],
        title="완성형 패키지 테스트",
        opts=None,
    )

    assert "export-cover" in html
    assert "완성형 문서 패키지" in html
    assert "metric-strip" in html
    assert "summary-card" in html
    assert "문서 수" in html
    assert "표 수" in html
    assert "사업 이해" in html
    assert "문서 01 / 02" in html
    assert "검토 초점:" in html
    assert "핵심 섹션:" in html
    assert "구성 지표:" in html
    assert " / 구성 특징:" not in html


def test_render_html_includes_generated_visual_asset_cards():
    from app.services.pdf_service import _render_html

    html = _render_html(
        [{"doc_type": "business_understanding", "markdown": "# 제목\n\n본문 A"}],
        title="시각자료 테스트",
        opts=None,
        visual_assets=[
            {
                "asset_id": "asset-1",
                "doc_type": "business_understanding",
                "slide_title": "사업 추진 배경",
                "visual_type": "현장 사진",
                "visual_brief": "운영 현장을 보여주는 생성 이미지",
                "media_type": "image/png",
                "content_base64": "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO5tm8sAAAAASUVORK5CYII=",
            }
        ],
    )

    assert "visual-asset-stack" in html
    assert "생성 시각자료" in html
    assert "사업 추진 배경" in html
    assert "data:image/png;base64," in html


def test_pdf_endpoint_returns_200(tmp_path, monkeypatch):
    client = _create_client(tmp_path, monkeypatch)
    res = client.post("/generate/pdf", json={"title": "PDF 테스트", "goal": "검증"})
    assert res.status_code == 200


def test_pdf_endpoint_content_type(tmp_path, monkeypatch):
    client = _create_client(tmp_path, monkeypatch)
    res = client.post("/generate/pdf", json={"title": "t", "goal": "g"})
    assert "application/pdf" in res.headers["content-type"]


def test_pdf_endpoint_content_disposition(tmp_path, monkeypatch):
    client = _create_client(tmp_path, monkeypatch)
    res = client.post("/generate/pdf", json={"title": "한글제목", "goal": "g"})
    assert "attachment" in res.headers.get("content-disposition", "")


def test_pdf_endpoint_returns_pdf_bytes(tmp_path, monkeypatch):
    client = _create_client(tmp_path, monkeypatch)
    res = client.post("/generate/pdf", json={"title": "t", "goal": "g"})
    assert res.content[:4] == b"%PDF"
