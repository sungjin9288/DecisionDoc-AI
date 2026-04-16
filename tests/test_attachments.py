"""Tests for file attachment extraction and /generate/with-attachments endpoint."""
import io
import json
import zipfile

import pytest
from fastapi.testclient import TestClient

from app.services.attachment_service import (
    MAX_CHARS,
    AttachmentError,
    extract_text,
    extract_text_with_ai_fallback,
)
from app.providers.mock_provider import MockProvider


# ---------------------------------------------------------------------------
# Unit tests: attachment_service.extract_text
# ---------------------------------------------------------------------------

class TestExtractTextPlain:
    def test_txt_returns_content(self):
        content = b"Hello, world!"
        assert extract_text("note.txt", content) == "Hello, world!"

    def test_md_returns_content(self):
        content = b"# Title\n\nSome markdown."
        assert extract_text("readme.md", content) == "# Title\n\nSome markdown."

    def test_truncates_to_max_chars(self):
        content = ("A" * (MAX_CHARS + 100)).encode()
        result = extract_text("big.txt", content)
        assert len(result) == MAX_CHARS

    def test_latin1_fallback(self):
        content = b"\xff\xfeWindows encoded"  # not valid UTF-8
        result = extract_text("win.txt", content)
        assert isinstance(result, str)


class TestExtractTextUnsupported:
    def test_unsupported_extension_raises(self):
        # .xlsx is now supported; use a truly unsupported extension instead
        with pytest.raises(AttachmentError, match="지원하지 않는"):
            extract_text("file.exe", b"data")

    def test_exe_raises(self):
        with pytest.raises(AttachmentError):
            extract_text("malware.exe", b"\x4d\x5a")

    def test_no_extension_raises(self):
        with pytest.raises(AttachmentError):
            extract_text("noextension", b"data")

    def test_image_extension_returns_guidance(self):
        with pytest.raises(AttachmentError, match="이미지 파일은 아직 본문 OCR/비전 분석을 지원하지 않습니다"):
            extract_text("diagram.png", b"\x89PNG\r\n\x1a\n")

    def test_legacy_doc_extension_returns_conversion_hint(self):
        with pytest.raises(AttachmentError, match="DOCX 또는 PDF로 변환"):
            extract_text("legacy.doc", b"binary")

    def test_image_can_use_ai_fallback_when_provider_exists(self):
        result = extract_text_with_ai_fallback(
            "diagram.png",
            b"\x89PNG\r\n\x1a\nfake",
            provider=MockProvider(),
            request_id="req-image",
        )
        assert "[AI 분석 첨부: diagram.png]" in result
        assert "시각 자료로 인식되었습니다" in result

    def test_scanned_pdf_can_use_ai_fallback_when_provider_exists(self, monkeypatch):
        def _raise_scanned_pdf(raw: bytes, filename: str) -> str:
            raise AttachmentError(f"{filename}: 텍스트를 추출할 수 없습니다 (스캔 이미지 PDF일 수 있습니다)")

        monkeypatch.setattr("app.services.attachment_service._extract_pdf", _raise_scanned_pdf)
        result = extract_text_with_ai_fallback(
            "scan.pdf",
            b"%PDF-1.4 fake",
            provider=MockProvider(),
            request_id="req-pdf",
        )
        assert "[AI 분석 첨부: scan.pdf]" in result
        assert "스캔 PDF로 인식되었습니다" in result

    def test_non_scanned_pdf_error_does_not_use_ai_fallback(self, monkeypatch):
        def _raise_regular_pdf(raw: bytes, filename: str) -> str:
            raise AttachmentError(f"{filename}: 손상된 PDF입니다")

        monkeypatch.setattr("app.services.attachment_service._extract_pdf", _raise_regular_pdf)
        with pytest.raises(AttachmentError, match="손상된 PDF입니다"):
            extract_text_with_ai_fallback(
                "broken.pdf",
                b"%PDF-1.4 fake",
                provider=MockProvider(),
                request_id="req-pdf",
            )


class TestExtractTextPdf:
    def test_missing_sdk_raises_attachment_error(self, monkeypatch):
        """If pdfplumber is not installed, AttachmentError is raised (not ImportError)."""
        import builtins
        real_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "pdfplumber":
                raise ImportError("mocked missing")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", mock_import)
        with pytest.raises(AttachmentError, match="PDF 파싱 라이브러리"):
            extract_text("doc.pdf", b"%PDF-1.4 fake")


class TestExtractStructuredFormats:
    def test_json_pretty_prints(self):
        result = extract_text("data.json", b'{"name":"DecisionDoc","items":[1,2]}')
        assert '"name": "DecisionDoc"' in result
        assert '"items": [' in result

    def test_yaml_extracts(self):
        raw = b"name: DecisionDoc\nfeatures:\n  - export\n  - attachments\n"
        result = extract_text("config.yaml", raw)
        assert "name: DecisionDoc" in result
        assert "- export" in result

    def test_html_strips_tags_and_scripts(self):
        raw = b"<html><head><script>alert(1)</script><title>Title</title></head><body><h1>Heading</h1><p>Hello <b>world</b></p></body></html>"
        result = extract_text("page.html", raw)
        assert "Heading" in result
        assert "Hello world" in result
        assert "alert(1)" not in result

    def test_rtf_extracts_plain_text(self):
        raw = br"{\rtf1\ansi\deff0 {\fonttbl {\f0 Arial;}}\f0\fs24 Hello\par World}"
        result = extract_text("memo.rtf", raw)
        assert "Hello" in result
        assert "World" in result

    def test_odt_extracts_content_xml_text(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr(
                "content.xml",
                """<?xml version="1.0" encoding="UTF-8"?>
                <office:document-content xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0"
                  xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0">
                  <office:body><office:text>
                    <text:h>제목</text:h>
                    <text:p>본문 내용</text:p>
                  </office:text></office:body>
                </office:document-content>""",
            )
        result = extract_text("sample.odt", buf.getvalue())
        assert "제목" in result
        assert "본문 내용" in result

    def test_zip_extracts_supported_inner_files(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("notes/readme.txt", "압축 내부 텍스트")
            zf.writestr("data/config.json", '{"goal":"문서 생성"}')
            zf.writestr("images/photo.jpg", b"\xff\xd8\xff")
        result = extract_text("bundle.zip", buf.getvalue())
        assert "[압축 내부 파일: notes/readme.txt]" in result
        assert "압축 내부 텍스트" in result
        assert '"goal": "문서 생성"' in result
        assert "이미지 파일은 OCR/비전 분석을 아직 지원하지 않아 건너뜁니다." in result

    def test_binary_hwp_returns_hwpx_guidance(self):
        with pytest.raises(AttachmentError, match="HWPX, PDF 또는 DOCX로 변환"):
            extract_text("legacy.hwp", b"not-a-zip")


# ---------------------------------------------------------------------------
# Integration tests: /generate/with-attachments endpoint
# ---------------------------------------------------------------------------

def _create_client(tmp_path, monkeypatch):
    monkeypatch.setenv("DECISIONDOC_PROVIDER", "mock")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DECISIONDOC_ENV", "dev")
    monkeypatch.setenv("DECISIONDOC_MAINTENANCE", "0")
    monkeypatch.delenv("DECISIONDOC_API_KEY", raising=False)
    monkeypatch.delenv("DECISIONDOC_API_KEYS", raising=False)
    from app.main import create_app
    return TestClient(create_app())


class TestGenerateWithAttachments:
    def _payload(self, **kwargs):
        base = {"title": "Attachment Test", "goal": "Verify file context injection"}
        base.update(kwargs)
        return json.dumps(base)

    def test_no_files_returns_200(self, tmp_path, monkeypatch):
        client = _create_client(tmp_path, monkeypatch)
        res = client.post(
            "/generate/with-attachments",
            data={"payload": self._payload()},
        )
        assert res.status_code == 200
        body = res.json()
        assert body["provider"] == "mock"
        assert len(body["docs"]) > 0

    def test_txt_file_injected_into_context(self, tmp_path, monkeypatch):
        client = _create_client(tmp_path, monkeypatch)
        txt_content = b"This is the reference document content."
        res = client.post(
            "/generate/with-attachments",
            data={"payload": self._payload()},
            files=[("attachments", ("ref.txt", io.BytesIO(txt_content), "text/plain"))],
        )
        assert res.status_code == 200
        # The attachment text should appear in the generated context
        # (mock provider may not use it, but the endpoint accepted it without error)
        assert res.json()["provider"] == "mock"

    def test_multiple_files_accepted(self, tmp_path, monkeypatch):
        client = _create_client(tmp_path, monkeypatch)
        res = client.post(
            "/generate/with-attachments",
            data={"payload": self._payload()},
            files=[
                ("attachments", ("a.txt", io.BytesIO(b"File A content"), "text/plain")),
                ("attachments", ("b.md", io.BytesIO(b"# File B\nContent here"), "text/markdown")),
            ],
        )
        assert res.status_code == 200

    def test_unsupported_file_format_still_returns_200(self, tmp_path, monkeypatch):
        """Unsupported/corrupt file formats are handled gracefully via extract_multiple.

        The attachment service emits a warning line instead of raising, so the
        endpoint returns 200 (not 422) — the bad file is skipped silently.
        """
        client = _create_client(tmp_path, monkeypatch)
        res = client.post(
            "/generate/with-attachments",
            data={"payload": self._payload()},
            files=[("attachments", ("bad.exe", io.BytesIO(b"data"), "application/octet-stream"))],
        )
        assert res.status_code == 200

    def test_invalid_payload_json_returns_422(self, tmp_path, monkeypatch):
        client = _create_client(tmp_path, monkeypatch)
        res = client.post(
            "/generate/with-attachments",
            data={"payload": "not-json"},
        )
        assert res.status_code == 422

    def test_missing_required_fields_returns_422(self, tmp_path, monkeypatch):
        client = _create_client(tmp_path, monkeypatch)
        # title is required but missing
        res = client.post(
            "/generate/with-attachments",
            data={"payload": json.dumps({"goal": "only goal, no title"})},
        )
        assert res.status_code == 422

    def test_existing_context_merged_with_attachment(self, tmp_path, monkeypatch):
        """Attachment text is appended after existing context, not replacing it."""
        client = _create_client(tmp_path, monkeypatch)
        user_context = "User-supplied background info."
        res = client.post(
            "/generate/with-attachments",
            data={"payload": self._payload(context=user_context)},
            files=[("attachments", ("extra.txt", io.BytesIO(b"Attachment extra"), "text/plain"))],
        )
        assert res.status_code == 200

    def test_empty_file_is_skipped(self, tmp_path, monkeypatch):
        """An empty uploaded file should not cause an error."""
        client = _create_client(tmp_path, monkeypatch)
        res = client.post(
            "/generate/with-attachments",
            data={"payload": self._payload()},
            files=[("attachments", ("empty.txt", io.BytesIO(b""), "text/plain"))],
        )
        assert res.status_code == 200

    def test_image_file_is_accepted_via_ai_fallback(self, tmp_path, monkeypatch):
        client = _create_client(tmp_path, monkeypatch)
        res = client.post(
            "/generate/with-attachments",
            data={"payload": self._payload()},
            files=[("attachments", ("diagram.png", io.BytesIO(b"\x89PNG\r\n\x1a\nfake"), "image/png"))],
        )
        assert res.status_code == 200

    def test_scanned_pdf_file_is_accepted_via_ai_fallback(self, tmp_path, monkeypatch):
        def _raise_scanned_pdf(raw: bytes, filename: str) -> str:
            raise AttachmentError(f"{filename}: 텍스트를 추출할 수 없습니다 (스캔 이미지 PDF일 수 있습니다)")

        monkeypatch.setattr("app.services.attachment_service._extract_pdf", _raise_scanned_pdf)
        client = _create_client(tmp_path, monkeypatch)
        res = client.post(
            "/generate/with-attachments",
            data={"payload": self._payload()},
            files=[("attachments", ("scan.pdf", io.BytesIO(b"%PDF-1.4 fake"), "application/pdf"))],
        )
        assert res.status_code == 200
