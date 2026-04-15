"""Tests for POST /generate/pptx endpoint."""
from io import BytesIO

from fastapi.testclient import TestClient

_PPTX_MAGIC = b"PK\x03\x04"  # ZIP/OOXML magic bytes — all .pptx files start with this


def _create_client(tmp_path, monkeypatch):
    monkeypatch.setenv("DECISIONDOC_PROVIDER", "mock")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DECISIONDOC_ENV", "dev")
    monkeypatch.setenv("DECISIONDOC_MAINTENANCE", "0")
    monkeypatch.delenv("DECISIONDOC_API_KEY", raising=False)
    monkeypatch.delenv("DECISIONDOC_API_KEYS", raising=False)

    from app.main import create_app

    return TestClient(create_app())


def test_pptx_returns_binary_for_presentation_kr(tmp_path, monkeypatch):
    """Endpoint returns a valid PPTX binary for presentation_kr bundles."""
    client = _create_client(tmp_path, monkeypatch)
    res = client.post(
        "/generate/pptx",
        json={"title": "AI 발표", "goal": "핵심 전달", "bundle_type": "presentation_kr"},
    )
    assert res.status_code == 200
    assert "presentation" in res.headers["content-type"]
    assert "attachment" in res.headers.get("content-disposition", "")
    assert res.content[:4] == _PPTX_MAGIC


def test_pptx_returns_binary_for_general_bundle(tmp_path, monkeypatch):
    """Non-presentation bundles also export as PPTX via markdown-doc conversion."""
    client = _create_client(tmp_path, monkeypatch)
    res = client.post(
        "/generate/pptx",
        json={"title": "기술 결정", "goal": "아키텍처 선택", "bundle_type": "tech_decision"},
    )
    assert res.status_code == 200
    assert "presentation" in res.headers["content-type"]
    assert res.content[:4] == _PPTX_MAGIC


def test_pptx_default_bundle_exports_successfully(tmp_path, monkeypatch):
    """Omitting bundle_type falls back to tech_decision and still exports a deck."""
    client = _create_client(tmp_path, monkeypatch)
    res = client.post(
        "/generate/pptx",
        json={"title": "테스트 결정", "goal": "테스트 목표"},
    )
    assert res.status_code == 200
    assert res.content[:4] == _PPTX_MAGIC


def test_pptx_slide_count(tmp_path, monkeypatch):
    """Mock builder returns 5 slides → cover(1) + 5 content = 6 slides total."""
    from pptx import Presentation

    client = _create_client(tmp_path, monkeypatch)
    res = client.post(
        "/generate/pptx",
        json={"title": "슬라이드 카운트 테스트", "goal": "슬라이드 수 확인", "bundle_type": "presentation_kr"},
    )
    assert res.status_code == 200
    prs = Presentation(BytesIO(res.content))
    assert len(prs.slides) == 6  # 1 cover + 5 from mock outline


def test_pptx_general_bundle_has_multiple_slides(tmp_path, monkeypatch):
    """Structured proposal bundles should include overview slides before content."""
    from pptx import Presentation

    client = _create_client(tmp_path, monkeypatch)
    res = client.post(
        "/generate/pptx",
        json={"title": "제안서 PPT", "goal": "완성형 문서 변환", "bundle_type": "proposal_kr"},
    )
    assert res.status_code == 200
    prs = Presentation(BytesIO(res.content))
    assert len(prs.slides) >= 4
    titles = [slide.shapes.title.text for slide in prs.slides if getattr(slide.shapes, "title", None)]
    assert "발표 구성" in titles
    assert "핵심 검토 포인트" in titles
    assert not any("PPT 구성 가이드" in title for title in titles)


def test_pptx_general_bundle_uses_summary_slide_content(tmp_path, monkeypatch):
    """Structured proposal PPT export should include summary-driven review text."""
    from pptx import Presentation

    client = _create_client(tmp_path, monkeypatch)
    res = client.post(
        "/generate/pptx",
        json={"title": "제안서 PPT", "goal": "완성형 문서 변환", "bundle_type": "proposal_kr"},
    )
    assert res.status_code == 200
    prs = Presentation(BytesIO(res.content))
    slide_texts = []
    for slide in prs.slides:
        text = []
        for shape in slide.shapes:
            if hasattr(shape, "text") and shape.text:
                text.append(shape.text)
        slide_texts.append("\n".join(text))

    joined = "\n".join(slide_texts)
    assert "핵심 검토 포인트" in joined
    assert "사업 추진 배경" in joined
    assert "핵심 섹션:" in joined


def test_pptx_performance_bundle_uses_structured_slide_outline(tmp_path, monkeypatch):
    """performance_plan_kr should prefer structured slide metadata over markdown fallback."""
    from pptx import Presentation

    client = _create_client(tmp_path, monkeypatch)
    res = client.post(
        "/generate/pptx",
        json={"title": "수행계획 발표", "goal": "표 중심 발표자료", "bundle_type": "performance_plan_kr"},
    )
    assert res.status_code == 200
    prs = Presentation(BytesIO(res.content))
    assert len(prs.slides) >= 10
    titles = [slide.shapes.title.text for slide in prs.slides if getattr(slide.shapes, "title", None)]
    assert "발표 구성" in titles
    assert "핵심 검토 포인트" in titles
    assert "WBS 및 마일스톤" in titles
    assert "리스크 매트릭스" in titles
    assert not any("PPT 구성 가이드" in title for title in titles)


def test_pptx_summary_slide_prefers_short_presentation_lead(tmp_path, monkeypatch):
    """Summary slides should use shorter PPT-oriented lead text instead of full prose blocks."""
    from pptx import Presentation

    client = _create_client(tmp_path, monkeypatch)
    res = client.post(
        "/generate/pptx",
        json={"title": "제안서 PPT", "goal": "완성형 문서 변환", "bundle_type": "proposal_kr"},
    )
    assert res.status_code == 200
    prs = Presentation(BytesIO(res.content))
    summary_slide = next(slide for slide in prs.slides if getattr(slide.shapes, "title", None) and slide.shapes.title.text == "핵심 검토 포인트")
    summary_text = "\n".join(shape.text for shape in summary_slide.shapes if hasattr(shape, "text") and shape.text)
    assert "핵심 섹션:" in summary_text
    assert "구성 특징" not in summary_text
    assert "하나의 사업 범위로 묶은 안입니다. 사업 배경과 현황 문제를 정책 목표와 연결해 설명하고" not in summary_text
