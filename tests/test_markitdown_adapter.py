from __future__ import annotations

import sys
import types

import pytest

from app.services.attachment_service import AttachmentError, extract_text_with_ai_fallback
from app.services.markitdown_adapter import (
    MarkItDownAdapterError,
    convert_upload_to_markdown,
    should_try_markitdown,
)


class _FakeResult:
    def __init__(self, text: str) -> None:
        self.text_content = text


class _FakeStreamInfo:
    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs


def _install_fake_markitdown(monkeypatch, *, text: str = "# Converted\n\n본문") -> list[dict]:
    calls: list[dict] = []

    class _FakeMarkItDown:
        def __init__(self, *, enable_plugins: bool = False) -> None:
            calls.append({"event": "init", "enable_plugins": enable_plugins})

        def convert_stream(self, stream, *, stream_info):
            calls.append(
                {
                    "event": "convert_stream",
                    "raw": stream.read(),
                    "stream_info": stream_info.kwargs,
                }
            )
            return _FakeResult(text)

    fake_module = types.SimpleNamespace(MarkItDown=_FakeMarkItDown, StreamInfo=_FakeStreamInfo)
    monkeypatch.setitem(sys.modules, "markitdown", fake_module)
    return calls


def test_should_try_markitdown_requires_feature_flag(monkeypatch):
    monkeypatch.delenv("DECISIONDOC_MARKITDOWN_ENABLED", raising=False)

    assert should_try_markitdown("proposal.docx") is False

    monkeypatch.setenv("DECISIONDOC_MARKITDOWN_ENABLED", "1")
    assert should_try_markitdown("proposal.docx") is True


def test_should_try_markitdown_rejects_url_like_names(monkeypatch):
    monkeypatch.setenv("DECISIONDOC_MARKITDOWN_ENABLED", "1")

    assert should_try_markitdown("https://example.com/proposal.docx") is False
    assert should_try_markitdown("file:///tmp/proposal.docx") is False


def test_convert_upload_to_markdown_uses_stream_only(monkeypatch):
    monkeypatch.setenv("DECISIONDOC_MARKITDOWN_ENABLED", "1")
    monkeypatch.setenv("DECISIONDOC_MARKITDOWN_PLUGINS_ENABLED", "0")
    calls = _install_fake_markitdown(monkeypatch, text="# Converted")

    result = convert_upload_to_markdown("../proposal.docx", b"doc bytes")

    assert result == "# Converted"
    assert calls[0] == {"event": "init", "enable_plugins": False}
    assert calls[1]["event"] == "convert_stream"
    assert calls[1]["raw"] == b"doc bytes"
    assert calls[1]["stream_info"]["filename"] == "proposal.docx"
    assert calls[1]["stream_info"]["extension"] == ".docx"
    assert "local_path" not in calls[1]["stream_info"]
    assert "url" not in calls[1]["stream_info"]


def test_convert_upload_to_markdown_honors_plugin_and_char_flags(monkeypatch):
    monkeypatch.setenv("DECISIONDOC_MARKITDOWN_ENABLED", "1")
    monkeypatch.setenv("DECISIONDOC_MARKITDOWN_PLUGINS_ENABLED", "1")
    monkeypatch.setenv("DECISIONDOC_MARKITDOWN_MAX_CHARS", "4")
    calls = _install_fake_markitdown(monkeypatch, text="abcdef")

    assert convert_upload_to_markdown("deck.pptx", b"pptx") == "abcd"
    assert calls[0] == {"event": "init", "enable_plugins": True}


def test_convert_upload_to_markdown_disabled(monkeypatch):
    monkeypatch.setenv("DECISIONDOC_MARKITDOWN_ENABLED", "0")

    with pytest.raises(MarkItDownAdapterError, match="disabled"):
        convert_upload_to_markdown("proposal.docx", b"doc bytes")


def test_attachment_service_falls_back_to_markitdown(monkeypatch):
    monkeypatch.setenv("DECISIONDOC_MARKITDOWN_ENABLED", "1")
    _install_fake_markitdown(monkeypatch, text="# MarkItDown fallback")

    def _raise_docx(raw: bytes, filename: str) -> str:
        raise AttachmentError(f"{filename}: DOCX parser failed")

    monkeypatch.setattr("app.services.attachment_service._extract_docx", _raise_docx)

    assert extract_text_with_ai_fallback("proposal.docx", b"doc bytes") == "# MarkItDown fallback"


def test_attachment_service_keeps_original_error_when_markitdown_disabled(monkeypatch):
    monkeypatch.setenv("DECISIONDOC_MARKITDOWN_ENABLED", "0")

    def _raise_docx(raw: bytes, filename: str) -> str:
        raise AttachmentError(f"{filename}: DOCX parser failed")

    monkeypatch.setattr("app.services.attachment_service._extract_docx", _raise_docx)

    with pytest.raises(AttachmentError, match="DOCX parser failed"):
        extract_text_with_ai_fallback("proposal.docx", b"doc bytes")
