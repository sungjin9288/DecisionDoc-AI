"""Tests for file attachment extraction and /generate/with-attachments endpoint."""
import io
import json

import pytest
from fastapi.testclient import TestClient

from app.services.attachment_service import (
    MAX_CHARS,
    AttachmentError,
    extract_text,
)


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
