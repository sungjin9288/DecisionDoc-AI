from __future__ import annotations

import io
from unittest.mock import patch

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


def test_generate_from_documents_success(tmp_path, monkeypatch):
    client = _create_client(tmp_path, monkeypatch)

    response = client.post(
        "/generate/from-documents",
        data={
            "doc_types": "adr,onepager",
            "goal": "업로드 문서를 기반으로 초안을 생성한다.",
        },
        files={"files": ("notes.txt", io.BytesIO(b"decision context"), "text/plain")},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["title"] == "notes"
    assert [doc["doc_type"] for doc in body["docs"]] == ["adr", "onepager"]


def test_generate_from_documents_accepts_image_via_ai_fallback(tmp_path, monkeypatch):
    client = _create_client(tmp_path, monkeypatch)

    response = client.post(
        "/generate/from-documents",
        data={
            "doc_types": "adr",
            "goal": "이미지 첨부를 기반으로 초안을 생성한다.",
        },
        files={"files": ("capture.png", io.BytesIO(b"\x89PNG\r\n\x1a\nfake"), "image/png")},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["title"] == "capture"
    assert [doc["doc_type"] for doc in body["docs"]] == ["adr"]


def test_generate_from_documents_accepts_scanned_pdf_via_ai_fallback(tmp_path, monkeypatch):
    def _raise_scanned_pdf(raw: bytes, filename: str) -> str:
        from app.services.attachment_service import AttachmentError

        raise AttachmentError(f"{filename}: 텍스트를 추출할 수 없습니다 (스캔 이미지 PDF일 수 있습니다)")

    monkeypatch.setattr("app.services.attachment_service._extract_pdf", _raise_scanned_pdf)
    client = _create_client(tmp_path, monkeypatch)

    response = client.post(
        "/generate/from-documents",
        data={
            "doc_types": "adr",
            "goal": "스캔 PDF 첨부를 기반으로 초안을 생성한다.",
        },
        files={"files": ("scan.pdf", io.BytesIO(b"%PDF-1.4 fake"), "application/pdf")},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["title"] == "scan"
    assert [doc["doc_type"] for doc in body["docs"]] == ["adr"]


def test_generate_from_documents_prepends_procurement_pdf_context(tmp_path, monkeypatch):
    client = _create_client(tmp_path, monkeypatch)

    structured = {
        "title": "착수보고 자료",
        "sections": [
            {"heading": "Ⅰ. 평가 개요", "content": "경영평가 추진 배경을 설명한다."},
            {"heading": "Ⅱ. 추진 일정", "content": "착수와 중간 보고 일정을 제시한다."},
        ],
        "raw_text": "착수보고 자료\n경영평가 추진 배경",
        "page_count": 10,
        "has_tables": True,
    }
    captured: dict[str, str] = {}

    def _fake_run_generate(req, request):
        captured["context"] = req.context or ""
        return {
            "request_id": "req-docs",
            "bundle_id": "bundle-docs",
            "title": req.title,
            "provider": "mock",
            "schema_version": "v1",
            "cache_hit": False,
            "docs": [{"doc_type": "adr", "markdown": "# ok", "warnings": []}],
        }

    with patch("app.routers.generate.extract_pdf_structured", return_value=structured), patch(
        "app.routers.generate.extract_text_with_ai_fallback",
        return_value="착수보고 자료\n경영평가 추진 배경",
    ), patch(
        "app.routers.generate._run_generate",
        side_effect=_fake_run_generate,
    ):
        response = client.post(
            "/generate/from-documents",
            data={
                "doc_types": "adr",
                "goal": "PDF 첨부를 기반으로 초안을 생성한다.",
            },
            files={"files": ("rfp.pdf", io.BytesIO(b"%PDF-1.4 fake"), "application/pdf")},
        )

    assert response.status_code == 200
    assert "공공조달 PDF 정규화 요약" in captured["context"]
    assert "핵심 섹션:" in captured["context"]
    assert "[첨부파일: rfp.pdf]" in captured["context"]


def test_generate_from_documents_proposal_bundle_reflects_procurement_slide_hints(tmp_path, monkeypatch):
    client = _create_client(tmp_path, monkeypatch)

    structured = {
        "title": "착수보고 자료",
        "sections": [
            {"heading": "Ⅰ. 평가 지표 체계", "content": "평가기준과 배점을 설명한다."},
            {"heading": "Ⅱ. 세부 추진 일정", "content": "착수와 중간, 완료 일정을 제시한다."},
        ],
        "raw_text": "착수보고 자료\n평가 지표 체계\n세부 추진 일정",
        "page_count": 10,
        "has_tables": True,
        "pages": [
            {"page": 3, "headings": ["평가 지표 체계"], "preview": "평가 기준 배점 지표 설명", "has_tables": True},
            {"page": 7, "headings": ["세부 추진 일정"], "preview": "착수 중간 완료 일정", "has_tables": False},
        ],
    }

    with patch("app.routers.generate.extract_pdf_structured", return_value=structured), patch(
        "app.routers.generate.extract_text_with_ai_fallback",
        return_value="착수보고 자료\n평가 지표 체계\n세부 추진 일정",
    ):
        response = client.post(
            "/generate/from-documents",
            data={
                "bundle_type": "proposal_kr",
                "goal": "착수보고 PDF를 바탕으로 제안서와 PPT 설계를 만든다.",
            },
            files={"files": ("rfp.pdf", io.BytesIO(b"%PDF-1.4 fake"), "application/pdf")},
        )

    assert response.status_code == 200
    docs = {doc["doc_type"]: doc["markdown"] for doc in response.json()["docs"]}
    business = docs["business_understanding"]

    assert "평가 대응 전략 — 평가 지표 체계" in business
    assert "일정 및 마일스톤 — 세부 추진 일정" in business
    assert "평가기준 표" in business
    assert "타임라인" in business


def test_generate_from_documents_rejects_invalid_extension(tmp_path, monkeypatch):
    client = _create_client(tmp_path, monkeypatch)

    response = client.post(
        "/generate/from-documents",
        data={"doc_types": "adr"},
        files={"files": ("malware.exe", io.BytesIO(b"not allowed"), "application/octet-stream")},
    )

    assert response.status_code == 422
    assert "지원하지 않는 파일 형식" in response.json()["detail"]


def test_generate_from_documents_requires_api_key_when_enabled(tmp_path, monkeypatch):
    monkeypatch.setenv("DECISIONDOC_PROVIDER", "mock")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DECISIONDOC_ENV", "dev")
    monkeypatch.setenv("DECISIONDOC_MAINTENANCE", "0")
    monkeypatch.setenv("DECISIONDOC_API_KEYS", "valid-key-abc")

    from app.main import create_app

    client = TestClient(create_app(), raise_server_exceptions=False)
    response = client.post(
        "/generate/from-documents",
        data={"doc_types": "adr"},
        files={"files": ("notes.txt", io.BytesIO(b"hello"), "text/plain")},
    )

    assert response.status_code == 401


def test_generate_from_documents_allows_bearer_auth_without_api_key(tmp_path, monkeypatch):
    monkeypatch.setenv("DECISIONDOC_PROVIDER", "mock")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DECISIONDOC_ENV", "dev")
    monkeypatch.setenv("DECISIONDOC_MAINTENANCE", "0")
    monkeypatch.setenv("DECISIONDOC_API_KEYS", "valid-key-abc")

    from app.main import create_app

    client = TestClient(create_app(), raise_server_exceptions=False)
    register = client.post(
        "/auth/register",
        json={
            "username": "upload-admin",
            "display_name": "Upload Admin",
            "email": "upload-admin@example.com",
            "password": "UploadAdmin1!",
        },
    )

    assert register.status_code == 200
    token = register.json()["access_token"]

    response = client.post(
        "/generate/from-documents",
        headers={"Authorization": f"Bearer {token}"},
        data={"doc_types": "adr,onepager"},
        files={"files": ("notes.txt", io.BytesIO(b"hello"), "text/plain")},
    )

    assert response.status_code == 200
    assert [doc["doc_type"] for doc in response.json()["docs"]] == ["adr", "onepager"]
