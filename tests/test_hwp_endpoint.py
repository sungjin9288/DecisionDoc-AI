"""Tests for POST /generate/hwp endpoint and hwp_service."""
import zipfile
from io import BytesIO


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


def test_build_hwp_returns_zip():
    from app.services.hwp_service import build_hwp
    docs = [{"doc_type": "adr", "markdown": "# 제목\n\n내용입니다."}]
    result = build_hwp(docs, title="테스트")
    assert zipfile.is_zipfile(BytesIO(result))


def test_build_hwp_contains_mimetype():
    from app.services.hwp_service import build_hwp
    docs = [{"doc_type": "adr", "markdown": "# 테스트"}]
    result = build_hwp(docs, title="테스트")
    with zipfile.ZipFile(BytesIO(result)) as zf:
        names = zf.namelist()
        assert "mimetype" in names
        assert zf.read("mimetype") == b"application/hwp+zip"


def test_build_hwp_contains_required_files():
    from app.services.hwp_service import build_hwp
    docs = [{"doc_type": "adr", "markdown": "# 테스트"}]
    result = build_hwp(docs, title="테스트")
    with zipfile.ZipFile(BytesIO(result)) as zf:
        names = set(zf.namelist())
        assert "META-INF/container.xml" in names
        assert "Contents/header.xml" in names
        assert "Contents/section0.xml" in names


def test_build_hwp_renders_markdown_table_as_readable_rows():
    from app.services.hwp_service import build_hwp

    docs = [{
        "doc_type": "proposal",
        "markdown": (
            "# 사업 개요\n\n"
            "| 항목 | 내용 |\n"
            "| --- | --- |\n"
            "| 계약 기간 | 24개월 |\n"
            "| 계약 금액 | 65억 원 |\n"
        ),
    }]
    result = build_hwp(docs, title="테스트")
    with zipfile.ZipFile(BytesIO(result)) as zf:
        section_xml = zf.read("Contents/section0.xml").decode("utf-8")
    assert "표: 항목 | 내용" in section_xml
    assert "항목: 계약 기간 / 내용: 24개월" in section_xml
    assert "항목: 계약 금액 / 내용: 65억 원" in section_xml


def test_build_hwp_adds_export_cover_and_section_intro():
    from app.services.hwp_service import build_hwp

    docs = [
        {"doc_type": "business_understanding", "markdown": "# 제목\n\n본문 A"},
        {"doc_type": "tech_proposal", "markdown": "# 제목\n\n본문 B"},
    ]
    result = build_hwp(docs, title="완성형 패키지 테스트")
    with zipfile.ZipFile(BytesIO(result)) as zf:
        section_xml = zf.read("Contents/section0.xml").decode("utf-8")

    assert "완성형 문서 패키지" in section_xml
    assert "패키지 지표" in section_xml
    assert "문서 구성" in section_xml
    assert "핵심 검토 포인트" in section_xml
    assert "문서 수: 2" in section_xml
    assert "표 수: " in section_xml
    assert "목록 수: " in section_xml
    assert "주요 섹션 수: " in section_xml
    assert "주요 구성:" in section_xml
    assert "사업 이해" in section_xml
    assert "문서 01 / 02" in section_xml
    assert "검토 초점:" in section_xml
    assert "핵심 섹션:" in section_xml
    assert "구성 지표:" in section_xml
    assert " / 구성 특징:" not in section_xml
    assert " / 표 수:" not in section_xml


def test_hwp_endpoint_returns_200(tmp_path, monkeypatch):
    client = _create_client(tmp_path, monkeypatch)
    res = client.post("/generate/hwp", json={"title": "HWP 테스트", "goal": "검증"})
    assert res.status_code == 200


def test_hwp_content_type(tmp_path, monkeypatch):
    client = _create_client(tmp_path, monkeypatch)
    res = client.post("/generate/hwp", json={"title": "t", "goal": "g"})
    assert "hwp" in res.headers["content-type"]


def test_hwp_content_disposition(tmp_path, monkeypatch):
    client = _create_client(tmp_path, monkeypatch)
    res = client.post("/generate/hwp", json={"title": "한글제목", "goal": "g"})
    assert "attachment" in res.headers.get("content-disposition", "")


def test_hwp_endpoint_returns_valid_zip(tmp_path, monkeypatch):
    client = _create_client(tmp_path, monkeypatch)
    res = client.post("/generate/hwp", json={"title": "t", "goal": "g"})
    assert zipfile.is_zipfile(BytesIO(res.content))
