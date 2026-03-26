"""Tests for Knowledge Store and Knowledge API endpoints."""
from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


# ── KnowledgeStore unit tests ─────────────────────────────────────────────────

class TestKnowledgeStore:
    def test_add_and_list(self, tmp_path):
        from app.storage.knowledge_store import KnowledgeStore
        store = KnowledgeStore("proj1", data_dir=str(tmp_path))
        entry = store.add_document("report.pdf", "분기 실적 보고서 내용입니다.")
        docs = store.list_documents()
        assert len(docs) == 1
        assert docs[0]["filename"] == "report.pdf"
        assert docs[0]["doc_id"] == entry.doc_id

    def test_get_document(self, tmp_path):
        from app.storage.knowledge_store import KnowledgeStore
        store = KnowledgeStore("proj1", data_dir=str(tmp_path))
        entry = store.add_document("spec.docx", "제품 스펙 문서", tags=["spec"])
        fetched = store.get_document(entry.doc_id)
        assert fetched is not None
        assert fetched.text == "제품 스펙 문서"
        assert fetched.tags == ["spec"]

    def test_delete_document(self, tmp_path):
        from app.storage.knowledge_store import KnowledgeStore
        store = KnowledgeStore("proj1", data_dir=str(tmp_path))
        entry = store.add_document("old.txt", "오래된 문서")
        assert store.delete_document(entry.doc_id) is True
        assert store.get_document(entry.doc_id) is None
        assert len(store.list_documents()) == 0

    def test_delete_nonexistent(self, tmp_path):
        from app.storage.knowledge_store import KnowledgeStore
        store = KnowledgeStore("proj1", data_dir=str(tmp_path))
        assert store.delete_document("nonexistent") is False

    def test_build_context_empty(self, tmp_path):
        from app.storage.knowledge_store import KnowledgeStore
        store = KnowledgeStore("empty_proj", data_dir=str(tmp_path))
        assert store.build_context() == ""

    def test_build_context_with_docs(self, tmp_path):
        from app.storage.knowledge_store import KnowledgeStore
        store = KnowledgeStore("proj2", data_dir=str(tmp_path))
        store.add_document("guide.md", "개발 가이드라인 문서")
        store.add_document("arch.md", "아키텍처 설계서")
        ctx = store.build_context()
        assert "프로젝트 지식" in ctx
        assert "guide.md" in ctx
        assert "arch.md" in ctx

    def test_update_style(self, tmp_path):
        from app.storage.knowledge_store import KnowledgeStore
        store = KnowledgeStore("proj3", data_dir=str(tmp_path))
        entry = store.add_document("report.txt", "보고서")
        style = {"formality": "합쇼체", "density": "간결", "sentence_endings": ["입니다", "합니다"]}
        result = store.update_style(entry.doc_id, style)
        assert result is True
        fetched = store.get_document(entry.doc_id)
        assert fetched.style_profile["formality"] == "합쇼체"

    def test_build_style_context_no_styles(self, tmp_path):
        from app.storage.knowledge_store import KnowledgeStore
        store = KnowledgeStore("proj4", data_dir=str(tmp_path))
        store.add_document("doc.txt", "내용")
        assert store.build_style_context() == ""

    def test_build_style_context_with_styles(self, tmp_path):
        from app.storage.knowledge_store import KnowledgeStore
        store = KnowledgeStore("proj5", data_dir=str(tmp_path))
        entry = store.add_document("doc.txt", "내용")
        store.update_style(entry.doc_id, {
            "formality": "합쇼체",
            "density": "상세",
            "sentence_endings": ["입니다", "합니다", "습니다"],
            "summary": "격식체 상세 문서",
        })
        ctx = store.build_style_context()
        assert "스타일 가이드" in ctx
        assert "합쇼체" in ctx

    def test_max_docs_eviction(self, tmp_path):
        from app.storage.knowledge_store import KnowledgeStore, MAX_DOCS_PER_PROJECT
        store = KnowledgeStore("proj_evict", data_dir=str(tmp_path))
        for i in range(MAX_DOCS_PER_PROJECT + 2):
            store.add_document(f"doc{i}.txt", f"내용 {i}")
        docs = store.list_documents()
        assert len(docs) == MAX_DOCS_PER_PROJECT

    def test_context_respects_max_chars(self, tmp_path):
        from app.storage.knowledge_store import KnowledgeStore
        store = KnowledgeStore("proj_big", data_dir=str(tmp_path))
        # 대용량 텍스트
        big_text = "가" * 5000
        store.add_document("big1.txt", big_text)
        store.add_document("big2.txt", big_text)
        ctx = store.build_context(max_chars=3000)
        assert len(ctx) <= 3200  # 약간의 헤더 여유


# ── attachment_service PPTX 테스트 ────────────────────────────────────────────

class TestPptxExtraction:
    def _make_pptx(self, slides: list[list[str]]) -> bytes:
        """Helper: Create minimal PPTX bytes with given slide texts."""
        from pptx import Presentation
        from pptx.util import Inches
        buf = io.BytesIO()
        prs = Presentation()
        blank_layout = prs.slide_layouts[5]
        for texts in slides:
            slide = prs.slides.add_slide(blank_layout)
            for i, text in enumerate(texts):
                txBox = slide.shapes.add_textbox(
                    Inches(1 + i * 0.1), Inches(1), Inches(4), Inches(1)
                )
                txBox.text_frame.text = text
        prs.save(buf)
        return buf.getvalue()

    def test_extract_pptx_basic(self):
        from app.services.attachment_service import extract_text
        raw = self._make_pptx([["슬라이드 1 제목", "내용 1"], ["슬라이드 2 제목"]])
        result = extract_text("test.pptx", raw)
        assert "슬라이드 1" in result
        assert "슬라이드 1 제목" in result
        assert "슬라이드 2 제목" in result

    def test_extract_pptx_in_allowed_extensions(self):
        from app.services.attachment_service import ALLOWED_EXTENSIONS
        assert ".pptx" in ALLOWED_EXTENSIONS

    def test_extract_pptx_empty_raises(self):
        from app.services.attachment_service import extract_text, AttachmentError
        from pptx import Presentation
        buf = io.BytesIO()
        Presentation().save(buf)
        with pytest.raises(AttachmentError, match="텍스트를 추출할 수 없습니다"):
            extract_text("empty.pptx", buf.getvalue())


# ── Knowledge API endpoint 테스트 ─────────────────────────────────────────────

@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DECISIONDOC_PROVIDER", "mock")
    monkeypatch.setenv("DECISIONDOC_API_KEYS", "test-key")
    from app.main import create_app
    return TestClient(create_app())


HEADERS = {"X-DecisionDoc-Api-Key": "test-key"}


class TestKnowledgeAPI:
    def test_upload_txt_document(self, client, tmp_path):
        content = b"This is a test knowledge document."
        resp = client.post(
            "/knowledge/proj-api/documents",
            headers=HEADERS,
            files={"file": ("guide.txt", content, "text/plain")},
            data={"tags": "guide,test"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["filename"] == "guide.txt"
        assert "doc_id" in body
        assert body["text_len"] > 0
        assert "guide" in body["tags"]

    def test_list_documents(self, client, tmp_path):
        content = b"Document content"
        client.post(
            "/knowledge/proj-list/documents",
            headers=HEADERS,
            files={"file": ("doc.txt", content, "text/plain")},
        )
        resp = client.get("/knowledge/proj-list/documents", headers=HEADERS)
        assert resp.status_code == 200
        body = resp.json()
        assert body["count"] == 1
        assert body["documents"][0]["filename"] == "doc.txt"

    def test_get_document(self, client, tmp_path):
        content = b"Detailed content here."
        upload = client.post(
            "/knowledge/proj-get/documents",
            headers=HEADERS,
            files={"file": ("detail.txt", content, "text/plain")},
        )
        doc_id = upload.json()["doc_id"]
        resp = client.get(f"/knowledge/proj-get/documents/{doc_id}", headers=HEADERS)
        assert resp.status_code == 200
        assert resp.json()["text"] == "Detailed content here."

    def test_get_nonexistent_document(self, client):
        resp = client.get("/knowledge/proj-x/documents/nonexistent", headers=HEADERS)
        assert resp.status_code == 404

    def test_delete_document(self, client, tmp_path):
        content = b"To be deleted"
        upload = client.post(
            "/knowledge/proj-del/documents",
            headers=HEADERS,
            files={"file": ("delete_me.txt", content, "text/plain")},
        )
        doc_id = upload.json()["doc_id"]
        resp = client.delete(f"/knowledge/proj-del/documents/{doc_id}", headers=HEADERS)
        assert resp.status_code == 200
        assert resp.json()["deleted"] is True
        # 삭제 후 조회 시 404
        resp2 = client.get(f"/knowledge/proj-del/documents/{doc_id}", headers=HEADERS)
        assert resp2.status_code == 404

    def test_context_preview(self, client, tmp_path):
        content = b"Important project knowledge"
        client.post(
            "/knowledge/proj-ctx/documents",
            headers=HEADERS,
            files={"file": ("knowledge.txt", content, "text/plain")},
        )
        resp = client.get("/knowledge/proj-ctx/context", headers=HEADERS)
        assert resp.status_code == 200
        body = resp.json()
        assert "context" in body
        assert "Important project knowledge" in body["context"]

    def test_upload_requires_auth(self, client):
        resp = client.post(
            "/knowledge/proj/documents",
            files={"file": ("doc.txt", b"content", "text/plain")},
        )
        assert resp.status_code in (401, 403)

    def test_upload_unsupported_format(self, client):
        resp = client.post(
            "/knowledge/proj/documents",
            headers=HEADERS,
            files={"file": ("doc.exe", b"\x00\x01", "application/octet-stream")},
        )
        assert resp.status_code == 422
