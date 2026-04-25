"""tests/test_project_management.py — Project management system tests.

Covers:
  A. ProjectStore.create — record creation & defaults
  B. get / list_by_tenant (status + fiscal_year filters, sort order)
  C. update / archive
  D. add_document / remove_document
  E. update_document_approval
  F. search — by name, client, doc title, tags
  G. get_yearly_archive
  H. get_stats
  I. Tenant isolation
  J. Thread safety
  K. GenerateRequest schema — project_id field
  L. API endpoints — CRUD
  M. API — procurement opportunity attachment
  N. API — document management + download
  O. API — search / archive / stats
  P. Auto-link: generation auto-adds doc to project
"""
from __future__ import annotations

import json
import threading
import time
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.schemas import (
    GenerateRequest,
    NormalizedProcurementOpportunity,
    ProcurementDecisionUpsert,
    ProcurementRecommendation,
    ProcurementRecommendationValue,
)
from app.storage.project_store import Project, ProjectDocument, ProjectStore


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

DOCS = [{"doc_type": "report", "markdown": "# 사업계획서\n내용입니다."}]
YEAR = datetime.now().year


def _store(tmp_path: Path) -> ProjectStore:
    return ProjectStore(base_dir=str(tmp_path))


def _create(store: ProjectStore, tenant: str = "t1", **kwargs) -> Project:
    defaults = dict(
        tenant_id=tenant,
        name="테스트 프로젝트",
        description="설명",
        client="발주처A",
        contract_number="2026-001",
        fiscal_year=YEAR,
    )
    defaults.update(kwargs)
    return store.create(**defaults)


# ---------------------------------------------------------------------------
# A. create
# ---------------------------------------------------------------------------

class TestProjectStoreCreate:
    def test_returns_project(self, tmp_path):
        p = _create(_store(tmp_path))
        assert isinstance(p, Project)

    def test_project_id_is_uuid(self, tmp_path):
        p = _create(_store(tmp_path))
        assert p.project_id and len(p.project_id) == 36

    def test_status_default_active(self, tmp_path):
        p = _create(_store(tmp_path))
        assert p.status == "active"

    def test_name_stored(self, tmp_path):
        p = _create(_store(tmp_path), name="계획서 프로젝트")
        assert p.name == "계획서 프로젝트"

    def test_client_stored(self, tmp_path):
        p = _create(_store(tmp_path), client="삼성전자")
        assert p.client == "삼성전자"

    def test_contract_number_stored(self, tmp_path):
        p = _create(_store(tmp_path), contract_number="2026-XYZ")
        assert p.contract_number == "2026-XYZ"

    def test_fiscal_year_stored(self, tmp_path):
        p = _create(_store(tmp_path), fiscal_year=2025)
        assert p.fiscal_year == 2025

    def test_documents_empty_on_create(self, tmp_path):
        p = _create(_store(tmp_path))
        assert p.documents == []

    def test_tags_empty_on_create(self, tmp_path):
        p = _create(_store(tmp_path))
        assert p.tags == []

    def test_tenant_id_stored(self, tmp_path):
        p = _create(_store(tmp_path), tenant="tenant_xyz")
        assert p.tenant_id == "tenant_xyz"

    def test_created_at_set(self, tmp_path):
        p = _create(_store(tmp_path))
        assert p.created_at

    def test_persisted_to_disk(self, tmp_path):
        store = _store(tmp_path)
        p = _create(store)
        # Fresh store, same dir
        p2 = _store(tmp_path).get(p.project_id)
        assert p2 is not None
        assert p2.name == p.name


# ---------------------------------------------------------------------------
# B. get / list_by_tenant
# ---------------------------------------------------------------------------

class TestProjectStoreRead:
    def test_get_existing(self, tmp_path):
        store = _store(tmp_path)
        p = _create(store)
        got = store.get(p.project_id)
        assert got is not None
        assert got.project_id == p.project_id

    def test_get_nonexistent_returns_none(self, tmp_path):
        assert _store(tmp_path).get("no-such-id") is None

    def test_list_returns_all(self, tmp_path):
        store = _store(tmp_path)
        for _ in range(4):
            _create(store)
        assert len(store.list_by_tenant("t1")) == 4

    def test_list_status_filter(self, tmp_path):
        store = _store(tmp_path)
        p = _create(store)
        store.archive(p.project_id)
        _create(store)  # stays active
        archived = store.list_by_tenant("t1", status="archived")
        assert len(archived) == 1

    def test_list_fiscal_year_filter(self, tmp_path):
        store = _store(tmp_path)
        _create(store, fiscal_year=2024)
        _create(store, fiscal_year=2025)
        _create(store, fiscal_year=2025)
        assert len(store.list_by_tenant("t1", fiscal_year=2025)) == 2
        assert len(store.list_by_tenant("t1", fiscal_year=2024)) == 1

    def test_list_sorted_newest_first(self, tmp_path):
        store = _store(tmp_path)
        p1 = _create(store, name="첫째")
        time.sleep(0.01)
        p2 = _create(store, name="둘째")
        recs = store.list_by_tenant("t1")
        assert recs[0].project_id == p2.project_id


# ---------------------------------------------------------------------------
# C. update / archive
# ---------------------------------------------------------------------------

class TestProjectStoreUpdate:
    def test_update_name(self, tmp_path):
        store = _store(tmp_path)
        p = _create(store)
        updated = store.update(p.project_id, name="새 이름")
        assert updated.name == "새 이름"

    def test_update_description(self, tmp_path):
        store = _store(tmp_path)
        p = _create(store)
        updated = store.update(p.project_id, description="새 설명")
        assert updated.description == "새 설명"

    def test_update_status_to_completed(self, tmp_path):
        store = _store(tmp_path)
        p = _create(store)
        updated = store.update(p.project_id, status="completed")
        assert updated.status == "completed"

    def test_update_tags(self, tmp_path):
        store = _store(tmp_path)
        p = _create(store)
        updated = store.update(p.project_id, tags=["AI", "2026"])
        assert updated.tags == ["AI", "2026"]

    def test_update_sets_updated_at(self, tmp_path):
        store = _store(tmp_path)
        p = _create(store)
        old_updated = p.updated_at
        time.sleep(0.01)
        updated = store.update(p.project_id, name="변경됨")
        assert updated.updated_at >= old_updated

    def test_update_nonexistent_raises(self, tmp_path):
        with pytest.raises(KeyError):
            _store(tmp_path).update("no-such-id", name="X")

    def test_archive_sets_archived_status(self, tmp_path):
        store = _store(tmp_path)
        p = _create(store)
        archived = store.archive(p.project_id)
        assert archived.status == "archived"

    def test_persisted_after_update(self, tmp_path):
        store = _store(tmp_path)
        p = _create(store)
        store.update(p.project_id, name="영속화 확인")
        reloaded = _store(tmp_path).get(p.project_id)
        assert reloaded.name == "영속화 확인"


# ---------------------------------------------------------------------------
# D. add_document / remove_document
# ---------------------------------------------------------------------------

class TestDocumentManagement:
    def test_add_document_increases_count(self, tmp_path):
        store = _store(tmp_path)
        p = _create(store)
        store.add_document(p.project_id, "req-1", "business_plan_kr", "사업계획서", DOCS)
        updated = store.get(p.project_id)
        assert len(updated.documents) == 1

    def test_add_document_returns_project_document(self, tmp_path):
        store = _store(tmp_path)
        p = _create(store)
        doc = store.add_document(p.project_id, "req-1", "business_plan_kr", "사업계획서", DOCS)
        assert isinstance(doc, ProjectDocument)
        assert doc.doc_id and len(doc.doc_id) == 36

    def test_add_document_stores_fields(self, tmp_path):
        store = _store(tmp_path)
        p = _create(store)
        doc = store.add_document(
            p.project_id, "req-42", "meeting_minutes_kr", "회의록",
            DOCS, tags=["중요"]
        )
        assert doc.request_id == "req-42"
        assert doc.bundle_id == "meeting_minutes_kr"
        assert doc.title == "회의록"
        assert doc.tags == ["중요"]

    def test_add_document_snapshot_is_docs_json(self, tmp_path):
        store = _store(tmp_path)
        p = _create(store)
        doc = store.add_document(p.project_id, "req-1", "b", "t", DOCS)
        assert json.loads(doc.doc_snapshot) == DOCS

    def test_add_document_file_size_chars(self, tmp_path):
        store = _store(tmp_path)
        p = _create(store)
        doc = store.add_document(p.project_id, "req-1", "b", "t", DOCS)
        expected_size = sum(len(d.get("markdown", "")) for d in DOCS)
        assert doc.file_size_chars == expected_size

    def test_remove_document_decreases_count(self, tmp_path):
        store = _store(tmp_path)
        p = _create(store)
        doc = store.add_document(p.project_id, "req-1", "b", "t", DOCS)
        store.remove_document(p.project_id, doc.doc_id)
        updated = store.get(p.project_id)
        assert len(updated.documents) == 0

    def test_remove_nonexistent_project_raises(self, tmp_path):
        with pytest.raises(KeyError):
            _store(tmp_path).remove_document("no-such-project", "doc-id")

    def test_add_multiple_documents(self, tmp_path):
        store = _store(tmp_path)
        p = _create(store)
        for i in range(3):
            store.add_document(p.project_id, f"req-{i}", "b", f"문서{i}", DOCS)
        updated = store.get(p.project_id)
        assert len(updated.documents) == 3


# ---------------------------------------------------------------------------
# E. update_document_approval
# ---------------------------------------------------------------------------

class TestUpdateDocumentApproval:
    def test_updates_approval_status(self, tmp_path):
        store = _store(tmp_path)
        p = _create(store)
        store.add_document(p.project_id, "req-777", "b", "제목", DOCS)
        store.update_document_approval(p.project_id, "req-777", "approval-abc", "approved")
        updated = store.get(p.project_id)
        assert updated.documents[0].approval_status == "approved"
        assert updated.documents[0].approval_id == "approval-abc"

    def test_update_nonexistent_request_id_is_noop(self, tmp_path):
        store = _store(tmp_path)
        p = _create(store)
        store.add_document(p.project_id, "req-1", "b", "t", DOCS)
        # request_id "req-999" doesn't exist — should not raise
        store.update_document_approval(p.project_id, "req-999", "approval-x", "approved")
        updated = store.get(p.project_id)
        assert updated.documents[0].approval_status is None  # unchanged

    def test_update_nonexistent_project_is_noop(self, tmp_path):
        # Should silently skip missing projects (used in bulk approval loops)
        _store(tmp_path).update_document_approval("no-such-project", "req-1", "a", "approved")
        # No exception = pass


# ---------------------------------------------------------------------------
# F. search
# ---------------------------------------------------------------------------

class TestProjectSearch:
    def test_search_by_project_name(self, tmp_path):
        store = _store(tmp_path)
        _create(store, name="인공지능 연구 프로젝트")
        _create(store, name="마케팅 기획")
        results = store.search("t1", "인공지능")
        assert len(results) == 1
        assert results[0]["project_name"] == "인공지능 연구 프로젝트"

    def test_search_by_client(self, tmp_path):
        store = _store(tmp_path)
        _create(store, name="프로젝트A", client="카카오")
        _create(store, name="프로젝트B", client="네이버")
        results = store.search("t1", "카카오")
        assert len(results) == 1

    def test_search_by_doc_title(self, tmp_path):
        store = _store(tmp_path)
        p = _create(store, name="일반 프로젝트")
        store.add_document(p.project_id, "req-1", "b", "블록체인 보안 문서", DOCS)
        results = store.search("t1", "블록체인")
        assert len(results) == 1
        assert results[0]["matched_docs"][0]["title"] == "블록체인 보안 문서"

    def test_search_by_tag(self, tmp_path):
        store = _store(tmp_path)
        p = _create(store, name="태그 프로젝트")
        store.update(p.project_id, tags=["공공기관", "2026"])
        results = store.search("t1", "공공기관")
        assert len(results) == 1

    def test_search_empty_query_returns_empty(self, tmp_path):
        store = _store(tmp_path)
        _create(store)
        results = store.search("t1", "")
        assert results == []

    def test_search_no_match_returns_empty(self, tmp_path):
        store = _store(tmp_path)
        _create(store, name="일반 프로젝트")
        results = store.search("t1", "존재하지않는검색어XYZ")
        assert results == []

    def test_search_with_fiscal_year_filter(self, tmp_path):
        store = _store(tmp_path)
        _create(store, name="2025 프로젝트", fiscal_year=2025)
        _create(store, name="2026 프로젝트", fiscal_year=2026)
        results = store.search("t1", "프로젝트", fiscal_year=2025)
        assert len(results) == 1
        assert results[0]["project_name"] == "2025 프로젝트"


# ---------------------------------------------------------------------------
# G. get_yearly_archive
# ---------------------------------------------------------------------------

class TestYearlyArchive:
    def test_archive_returns_correct_year(self, tmp_path):
        store = _store(tmp_path)
        _create(store, fiscal_year=2025)
        result = store.get_yearly_archive("t1", 2025)
        assert result["fiscal_year"] == 2025

    def test_archive_counts_docs(self, tmp_path):
        store = _store(tmp_path)
        p = _create(store, fiscal_year=2025)
        store.add_document(p.project_id, "r1", "business_plan_kr", "문서1", DOCS)
        store.add_document(p.project_id, "r2", "meeting_minutes_kr", "문서2", DOCS)
        result = store.get_yearly_archive("t1", 2025)
        assert result["total_docs"] == 2

    def test_archive_bundle_breakdown(self, tmp_path):
        store = _store(tmp_path)
        p = _create(store, fiscal_year=2025)
        store.add_document(p.project_id, "r1", "business_plan_kr", "문서1", DOCS)
        store.add_document(p.project_id, "r2", "business_plan_kr", "문서2", DOCS)
        store.add_document(p.project_id, "r3", "meeting_minutes_kr", "문서3", DOCS)
        result = store.get_yearly_archive("t1", 2025)
        assert result["bundle_breakdown"]["business_plan_kr"] == 2
        assert result["bundle_breakdown"]["meeting_minutes_kr"] == 1

    def test_archive_empty_year_has_zero_docs(self, tmp_path):
        store = _store(tmp_path)
        _create(store, fiscal_year=2024)
        result = store.get_yearly_archive("t1", 2025)
        assert result["total_docs"] == 0
        assert result["projects"] == []


# ---------------------------------------------------------------------------
# H. get_stats
# ---------------------------------------------------------------------------

class TestProjectStats:
    def test_stats_total_projects(self, tmp_path):
        store = _store(tmp_path)
        for _ in range(3):
            _create(store)
        stats = store.get_stats("t1")
        assert stats["total_projects"] == 3

    def test_stats_active_projects(self, tmp_path):
        store = _store(tmp_path)
        p1 = _create(store)
        _create(store)
        store.archive(p1.project_id)
        stats = store.get_stats("t1")
        assert stats["active_projects"] == 1

    def test_stats_total_docs(self, tmp_path):
        store = _store(tmp_path)
        p = _create(store)
        store.add_document(p.project_id, "r1", "b", "문서1", DOCS)
        store.add_document(p.project_id, "r2", "b", "문서2", DOCS)
        stats = store.get_stats("t1")
        assert stats["total_docs"] == 2

    def test_stats_by_year(self, tmp_path):
        store = _store(tmp_path)
        p1 = _create(store, fiscal_year=2025)
        p2 = _create(store, fiscal_year=2026)
        store.add_document(p1.project_id, "r1", "b", "t", DOCS)
        store.add_document(p2.project_id, "r2", "b", "t", DOCS)
        store.add_document(p2.project_id, "r3", "b", "t", DOCS)
        stats = store.get_stats("t1")
        assert stats["by_year"][2025] == 1
        assert stats["by_year"][2026] == 2

    def test_stats_by_bundle(self, tmp_path):
        store = _store(tmp_path)
        p = _create(store)
        store.add_document(p.project_id, "r1", "business_plan_kr", "t", DOCS)
        store.add_document(p.project_id, "r2", "meeting_minutes_kr", "t", DOCS)
        stats = store.get_stats("t1")
        assert stats["by_bundle"]["business_plan_kr"] == 1
        assert stats["by_bundle"]["meeting_minutes_kr"] == 1

    def test_stats_by_status(self, tmp_path):
        store = _store(tmp_path)
        p = _create(store)
        _create(store)
        store.archive(p.project_id)
        stats = store.get_stats("t1")
        assert stats["by_status"]["active"] == 1
        assert stats["by_status"]["archived"] == 1

    def test_stats_empty_tenant(self, tmp_path):
        stats = _store(tmp_path).get_stats("empty_tenant")
        assert stats["total_projects"] == 0
        assert stats["total_docs"] == 0


# ---------------------------------------------------------------------------
# I. Tenant isolation
# ---------------------------------------------------------------------------

class TestTenantIsolation:
    def test_tenants_have_separate_lists(self, tmp_path):
        store = _store(tmp_path)
        _create(store, tenant="org_a")
        _create(store, tenant="org_b")
        assert len(store.list_by_tenant("org_a")) == 1
        assert len(store.list_by_tenant("org_b")) == 1

    def test_separate_json_files(self, tmp_path):
        store = _store(tmp_path)
        _create(store, tenant="alpha")
        _create(store, tenant="beta")
        assert (tmp_path / "tenants" / "alpha" / "projects.json").exists()
        assert (tmp_path / "tenants" / "beta" / "projects.json").exists()

    def test_stats_isolated_by_tenant(self, tmp_path):
        store = _store(tmp_path)
        _create(store, tenant="a")
        _create(store, tenant="a")
        _create(store, tenant="b")
        assert store.get_stats("a")["total_projects"] == 2
        assert store.get_stats("b")["total_projects"] == 1


# ---------------------------------------------------------------------------
# J. Thread safety
# ---------------------------------------------------------------------------

class TestThreadSafety:
    def test_concurrent_creates_no_data_loss(self, tmp_path):
        store = _store(tmp_path)
        results = []
        errors = []

        def worker():
            try:
                results.append(_create(store, tenant="shared"))
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == []
        assert len(results) == 10
        # All IDs unique
        ids = {p.project_id for p in results}
        assert len(ids) == 10


# ---------------------------------------------------------------------------
# K. GenerateRequest schema
# ---------------------------------------------------------------------------

class TestGenerateRequestSchema:
    def test_project_id_field_exists(self):
        """GenerateRequest accepts project_id."""
        req = GenerateRequest(
            title="테스트",
            goal="목표",
            project_id="proj-123",
        )
        assert req.project_id == "proj-123"

    def test_project_id_defaults_to_none(self):
        req = GenerateRequest(title="테스트", goal="목표")
        assert req.project_id is None


# ---------------------------------------------------------------------------
# L. API endpoints — fixture + CRUD
# ---------------------------------------------------------------------------

@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DECISIONDOC_PROVIDER", "mock")
    monkeypatch.setenv("DECISIONDOC_PROVIDER_GENERATION", "")
    monkeypatch.setenv("DECISIONDOC_PROVIDER_ATTACHMENT", "")
    monkeypatch.setenv("DECISIONDOC_PROVIDER_VISUAL", "")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DECISIONDOC_ENV", "dev")
    monkeypatch.setenv("DECISIONDOC_MAINTENANCE", "0")
    monkeypatch.setenv("DECISIONDOC_API_KEY", "test-key")
    monkeypatch.setenv("DECISIONDOC_PROCUREMENT_COPILOT_ENABLED", "1")
    monkeypatch.delenv("DECISIONDOC_API_KEYS", raising=False)
    return TestClient(create_app())


HEADERS = {"X-DecisionDoc-Api-Key": "test-key"}
PROJ_PAYLOAD = {"name": "API 테스트 프로젝트", "fiscal_year": YEAR}


def _auth_headers(client: TestClient, username: str = "project-user") -> dict[str, str]:
    client.post(
        "/auth/register",
        json={
            "username": username,
            "display_name": username,
            "email": f"{username}@example.com",
            "password": "Password123!",
        },
    )
    login = client.post(
        "/auth/login",
        json={"username": username, "password": "Password123!"},
    )
    token = login.json()["access_token"]
    return {**HEADERS, "Authorization": f"Bearer {token}"}


def _disabled_procurement_client(tmp_path, monkeypatch) -> TestClient:
    monkeypatch.setenv("DECISIONDOC_PROVIDER", "mock")
    monkeypatch.setenv("DECISIONDOC_PROVIDER_GENERATION", "")
    monkeypatch.setenv("DECISIONDOC_PROVIDER_ATTACHMENT", "")
    monkeypatch.setenv("DECISIONDOC_PROVIDER_VISUAL", "")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DECISIONDOC_ENV", "dev")
    monkeypatch.setenv("DECISIONDOC_MAINTENANCE", "0")
    monkeypatch.setenv("DECISIONDOC_API_KEY", "test-key")
    monkeypatch.setenv("DECISIONDOC_PROCUREMENT_COPILOT_ENABLED", "0")
    monkeypatch.delenv("DECISIONDOC_API_KEYS", raising=False)
    return TestClient(create_app())


class TestProjectApiCrud:
    def test_create_project_returns_200(self, client):
        res = client.post("/projects", json=PROJ_PAYLOAD, headers=HEADERS)
        assert res.status_code == 200

    def test_create_project_has_project_id(self, client):
        data = client.post("/projects", json=PROJ_PAYLOAD, headers=HEADERS).json()
        assert "project_id" in data
        assert data["status"] == "active"

    def test_get_project_returns_record(self, client):
        pid = client.post("/projects", json=PROJ_PAYLOAD, headers=HEADERS).json()["project_id"]
        res = client.get(f"/projects/{pid}", headers=HEADERS)
        assert res.status_code == 200
        assert res.json()["project_id"] == pid

    def test_get_nonexistent_returns_404(self, client):
        assert client.get("/projects/no-such-id", headers=HEADERS).status_code == 404

    def test_list_projects_returns_list(self, client):
        res = client.get("/projects", headers=HEADERS)
        assert res.status_code == 200
        assert "projects" in res.json()

    def test_list_with_status_filter(self, client):
        # Create and archive one
        pid = client.post("/projects", json=PROJ_PAYLOAD, headers=HEADERS).json()["project_id"]
        client.post(f"/projects/{pid}/archive", headers=HEADERS)
        res = client.get("/projects?status=archived", headers=HEADERS)
        archived = res.json()["projects"]
        assert all(p["status"] == "archived" for p in archived)

    def test_patch_project(self, client):
        pid = client.post("/projects", json=PROJ_PAYLOAD, headers=HEADERS).json()["project_id"]
        res = client.patch(f"/projects/{pid}", json={"name": "새 이름"}, headers=HEADERS)
        assert res.status_code == 200
        assert res.json()["name"] == "새 이름"

    def test_patch_nonexistent_returns_404(self, client):
        assert client.patch("/projects/no-such-id", json={"name": "X"}, headers=HEADERS).status_code == 404

    def test_archive_endpoint(self, client):
        pid = client.post("/projects", json=PROJ_PAYLOAD, headers=HEADERS).json()["project_id"]
        res = client.post(f"/projects/{pid}/archive", headers=HEADERS)
        assert res.status_code == 200
        assert res.json()["status"] == "archived"

    def test_archive_nonexistent_returns_404(self, client):
        assert client.post("/projects/no-such/archive", headers=HEADERS).status_code == 404


# ---------------------------------------------------------------------------
# M. Procurement opportunity attachment API
# ---------------------------------------------------------------------------

class TestProjectProcurementApi:
    def _pid(self, client) -> str:
        return client.post("/projects", json=PROJ_PAYLOAD, headers=HEADERS).json()["project_id"]

    def test_get_procurement_returns_none_before_attachment(self, client):
        pid = self._pid(client)
        res = client.get(f"/projects/{pid}/procurement", headers=HEADERS)
        assert res.status_code == 200
        assert res.json()["decision"] is None

    def test_import_g2b_opportunity_persists_normalized_state(self, client):
        from app.services.g2b_collector import G2BAnnouncement

        pid = self._pid(client)
        fake = G2BAnnouncement(
            bid_number="20260325001-00",
            title="AI 기반 민원 서비스 고도화 사업",
            issuer="행정안전부",
            budget="5억원",
            announcement_date="2026-03-25",
            deadline="2026-04-25 18:00",
            bid_type="일반경쟁",
            category="용역",
            detail_url="https://www.g2b.go.kr/notice/20260325001-00",
            attachments=[],
            raw_text="공고 전문 텍스트입니다.",
            source="scrape",
        )

        with patch(
            "app.services.g2b_collector.fetch_announcement_detail",
            new=AsyncMock(return_value=fake),
        ):
            res = client.post(
                f"/projects/{pid}/imports/g2b-opportunity",
                json={"url_or_number": "20260325001-00"},
                headers=HEADERS,
            )

        assert res.status_code == 200
        data = res.json()
        assert data["operation"] == "created"
        assert data["opportunity"]["source_kind"] == "g2b"
        assert data["opportunity"]["source_id"] == "20260325001-00"
        assert data["decision"]["source_snapshots"]

        snapshot_id = data["source_snapshot"]["snapshot_id"]
        snapshot = client.app.state.procurement_store.load_source_snapshot(
            tenant_id="system",
            project_id=pid,
            snapshot_id=snapshot_id,
        )
        assert snapshot is not None
        assert snapshot["announcement"]["title"] == "AI 기반 민원 서비스 고도화 사업"
        assert "행정안전부" in snapshot["structured_context"]

        retrieval = client.get(f"/projects/{pid}/procurement", headers=HEADERS)
        assert retrieval.status_code == 200
        decision = retrieval.json()["decision"]
        assert decision["opportunity"]["title"] == "AI 기반 민원 서비스 고도화 사업"
        assert decision["source_snapshots"][0]["snapshot_id"] == snapshot_id

    def test_import_g2b_opportunity_preserves_existing_decision_fields(self, client):
        from app.services.g2b_collector import G2BAnnouncement

        pid = self._pid(client)
        client.app.state.procurement_store.upsert(
            ProcurementDecisionUpsert(
                project_id=pid,
                tenant_id="system",
                recommendation=ProcurementRecommendation(
                    value=ProcurementRecommendationValue.GO,
                    summary="기존 판단 유지",
                    evidence=["기존 레퍼런스 충분"],
                ),
                notes="existing procurement note",
            )
        )
        fake = G2BAnnouncement(
            bid_number="20260325002-00",
            title="클라우드 전환 컨설팅",
            issuer="조달청",
            budget="3억원",
            announcement_date="2026-03-25",
            deadline="2026-04-10 17:00",
            bid_type="제한경쟁",
            category="용역",
            detail_url="https://www.g2b.go.kr/notice/20260325002-00",
            attachments=[],
            raw_text="클라우드 전환 사업 공고문",
            source="scrape",
        )

        with patch(
            "app.services.g2b_collector.fetch_announcement_detail",
            new=AsyncMock(return_value=fake),
        ):
            res = client.post(
                f"/projects/{pid}/imports/g2b-opportunity",
                json={"url_or_number": "20260325002-00"},
                headers=HEADERS,
            )

        assert res.status_code == 200
        decision = res.json()["decision"]
        assert decision["recommendation"]["value"] == "GO"
        assert decision["notes"] == "existing procurement note"
        assert decision["opportunity"]["source_id"] == "20260325002-00"

    def test_import_g2b_opportunity_reuses_preparsed_rfp_signals(self, client):
        from app.services.g2b_collector import G2BAnnouncement

        pid = self._pid(client)
        fake = G2BAnnouncement(
            bid_number="20260325003-00",
            title="공공 데이터 플랫폼 구축",
            issuer="서울특별시",
            budget="7억원",
            announcement_date="2026-03-25",
            deadline="2026-04-30 17:00",
            bid_type="일반경쟁",
            category="용역",
            detail_url="https://www.g2b.go.kr/notice/20260325003-00",
            attachments=[],
            raw_text="이 raw_text 는 재파싱되면 안 됩니다.",
            source="scrape",
        )

        with patch(
            "app.services.g2b_collector.fetch_announcement_detail",
            new=AsyncMock(return_value=fake),
        ), patch(
            "app.services.rfp_parser.parse_rfp_fields",
            side_effect=AssertionError("pre-parsed RFP fields should be reused"),
        ):
            res = client.post(
                f"/projects/{pid}/imports/g2b-opportunity",
                json={
                    "url_or_number": "20260325003-00",
                    "parsed_rfp_fields": {
                        "issuer": "서울특별시",
                        "project_title": "공공 데이터 플랫폼 구축",
                    },
                    "structured_context": "prebuilt structured context",
                },
                headers=HEADERS,
            )

        assert res.status_code == 200
        snapshot_id = res.json()["source_snapshot"]["snapshot_id"]
        snapshot = client.app.state.procurement_store.load_source_snapshot(
            tenant_id="system",
            project_id=pid,
            snapshot_id=snapshot_id,
        )
        assert snapshot is not None
        assert snapshot["extracted_fields"]["project_title"] == "공공 데이터 플랫폼 구축"
        assert snapshot["structured_context"] == "prebuilt structured context"

    def test_import_g2b_opportunity_missing_project_returns_404(self, client):
        res = client.post(
            "/projects/no-such-id/imports/g2b-opportunity",
            json={"url_or_number": "20260325001-00"},
            headers=HEADERS,
        )
        assert res.status_code == 404

    def test_import_g2b_opportunity_not_found_returns_404(self, client):
        pid = self._pid(client)
        with patch(
            "app.services.g2b_collector.fetch_announcement_detail",
            new=AsyncMock(return_value=None),
        ):
            res = client.post(
                f"/projects/{pid}/imports/g2b-opportunity",
                json={"url_or_number": "20260325099-00"},
                headers=HEADERS,
            )
        assert res.status_code == 404

    def test_evaluate_procurement_without_opportunity_returns_409(self, client):
        pid = self._pid(client)
        res = client.post(f"/projects/{pid}/procurement/evaluate", headers=HEADERS)
        assert res.status_code == 409
        assert res.json()["detail"]["code"] == "procurement_opportunity_not_attached"

    def test_evaluate_procurement_persists_hard_filters_and_score(self, client):
        from app.services.g2b_collector import G2BAnnouncement
        from app.storage.knowledge_store import KnowledgeStore

        pid = self._pid(client)
        fake = G2BAnnouncement(
            bid_number="20260325004-00",
            title="AI 기반 공공 서비스 혁신 사업",
            issuer="행정안전부",
            budget="5억원",
            announcement_date="2026-03-25",
            deadline="2026-05-30 17:00",
            bid_type="일반경쟁",
            category="용역",
            detail_url="https://www.g2b.go.kr/notice/20260325004-00",
            attachments=[],
            raw_text="입찰참가자격: 소프트웨어사업자, ISMS 보유. 유사사업 수행실적 필요.",
            source="scrape",
        )
        with patch(
            "app.services.g2b_collector.fetch_announcement_detail",
            new=AsyncMock(return_value=fake),
        ):
            imported = client.post(
                f"/projects/{pid}/imports/g2b-opportunity",
                json={"url_or_number": "20260325004-00"},
                headers=HEADERS,
            )
        assert imported.status_code == 200

        KnowledgeStore(pid, data_dir=str(client.app.state.data_dir)).add_document(
            "capability.txt",
            (
                "공공 AI 서비스 구축 레퍼런스 2건, 클라우드 전환 경험, "
                "소프트웨어사업자 등록, ISMS 인증, PM/개발자/컨설턴트 인력 보유."
            ),
        )

        res = client.post(f"/projects/{pid}/procurement/evaluate", headers=HEADERS)
        assert res.status_code == 200
        data = res.json()
        assert data["decision"]["soft_fit_status"] == "scored"
        assert data["decision"]["soft_fit_score"] is not None
        assert any(item["code"] == "mandatory_certification_or_license" for item in data["decision"]["hard_filters"])

        retrieval = client.get(f"/projects/{pid}/procurement", headers=HEADERS)
        assert retrieval.status_code == 200
        assert retrieval.json()["decision"]["soft_fit_score"] == data["decision"]["soft_fit_score"]

    def test_recommend_procurement_persists_recommendation_and_checklist(self, client):
        from app.services.g2b_collector import G2BAnnouncement
        from app.storage.knowledge_store import KnowledgeStore

        pid = self._pid(client)
        fake = G2BAnnouncement(
            bid_number="20260325005-00",
            title="AI 기반 공공 서비스 혁신 사업",
            issuer="행정안전부",
            budget="5억원",
            announcement_date="2026-03-25",
            deadline="2026-05-30 17:00",
            bid_type="일반경쟁",
            category="용역",
            detail_url="https://www.g2b.go.kr/notice/20260325005-00",
            attachments=[],
            raw_text="입찰참가자격: 소프트웨어사업자, ISMS 보유. 유사사업 수행실적 필요.",
            source="scrape",
        )
        with patch(
            "app.services.g2b_collector.fetch_announcement_detail",
            new=AsyncMock(return_value=fake),
        ):
            imported = client.post(
                f"/projects/{pid}/imports/g2b-opportunity",
                json={"url_or_number": "20260325005-00"},
                headers=HEADERS,
            )
        assert imported.status_code == 200

        KnowledgeStore(pid, data_dir=str(client.app.state.data_dir)).add_document(
            "capability.txt",
            (
                "공공 AI 서비스 구축 레퍼런스 2건, 클라우드 전환 경험, "
                "소프트웨어사업자 등록, ISMS 인증, PM/개발자/컨설턴트 인력 보유."
            ),
        )

        res = client.post(f"/projects/{pid}/procurement/recommend", headers=HEADERS)
        assert res.status_code == 200
        data = res.json()
        assert data["recommendation"] is not None
        assert data["recommendation"]["value"] in {"GO", "CONDITIONAL_GO", "NO_GO"}
        assert data["checklist_items"]
        assert any(item["category"] == "eligibility_and_compliance" for item in data["checklist_items"])

        retrieval = client.get(f"/projects/{pid}/procurement", headers=HEADERS)
        assert retrieval.status_code == 200
        assert retrieval.json()["decision"]["recommendation"]["value"] == data["recommendation"]["value"]
        assert retrieval.json()["decision"]["checklist_items"]

    def test_decision_council_run_requires_procurement_recommendation(self, client):
        pid = self._pid(client)
        client.app.state.procurement_store.upsert(
            ProcurementDecisionUpsert(
                project_id=pid,
                tenant_id="system",
                opportunity=NormalizedProcurementOpportunity(
                    source_kind="g2b",
                    source_id="R26-COUNCIL-REQ-001",
                    title="조달 council 추천 전 상태",
                    issuer="행정안전부",
                ),
            )
        )

        res = client.post(
            f"/projects/{pid}/decision-council/run",
            json={"goal": "입찰 참여 여부를 정리한다."},
            headers=HEADERS,
        )

        assert res.status_code == 409
        detail = res.json()["detail"]
        assert detail["code"] == "decision_council_procurement_context_required"
        assert detail["project_id"] == pid
        assert detail["required_steps"] == [
            "imports/g2b-opportunity",
            "procurement/evaluate",
            "procurement/recommend",
        ]

    def test_decision_council_run_and_get_latest_return_canonical_session(self, client):
        pid = self._pid(client)
        client.app.state.procurement_store.upsert(
            ProcurementDecisionUpsert(
                project_id=pid,
                tenant_id="system",
                opportunity=NormalizedProcurementOpportunity(
                    source_kind="g2b",
                    source_id="R26-COUNCIL-001",
                    title="조건부 진행 council 테스트",
                    issuer="행정안전부",
                    budget="4억원",
                    deadline="2026-05-30 18:00",
                ),
                missing_data=["핵심 레퍼런스 최신본"],
                recommendation=ProcurementRecommendation(
                    value="CONDITIONAL_GO",
                    summary="보완 항목 정리 후 진행 가능",
                    evidence=["공공 레퍼런스 존재", "증빙 최신화 필요"],
                ),
            )
        )

        created = client.post(
            f"/projects/{pid}/decision-council/run",
            json={
                "goal": "bid_decision_kr 작성 전 방향을 정리한다.",
                "context": "대외 proposal로 바로 확장하지 않는다.",
                "constraints": "근거 없는 GO 표현 금지",
            },
            headers=HEADERS,
        )
        assert created.status_code == 200
        created_session = created.json()
        assert created_session["operation"] == "created"
        assert created_session["project_id"] == pid
        assert created_session["target_bundle_type"] == "bid_decision_kr"
        assert created_session["current_procurement_binding_status"] == "current"
        assert created_session["current_procurement_binding_reason_code"] == ""
        assert created_session["source_procurement_recommendation_value"] == "CONDITIONAL_GO"
        assert created_session["source_procurement_missing_data_count"] == 1
        assert created_session["consensus"]["recommended_direction"] == "proceed_with_conditions"
        assert len(created_session["role_opinions"]) == 5

        retrieved = client.get(f"/projects/{pid}/decision-council", headers=HEADERS)
        assert retrieved.status_code == 200
        latest_session = retrieved.json()
        assert latest_session["operation"] is None
        assert latest_session["session_id"] == created_session["session_id"]
        assert latest_session["session_revision"] == 1
        assert latest_session["current_procurement_binding_status"] == "current"
        assert latest_session["current_procurement_binding_reason_code"] == ""
        assert latest_session["handoff"]["target_bundle_type"] == "bid_decision_kr"
        assert latest_session["handoff"]["recommended_direction"] == "proceed_with_conditions"

    def test_override_reason_appends_structured_note(self, client):
        from app.services.g2b_collector import G2BAnnouncement

        pid = self._pid(client)
        fake = G2BAnnouncement(
            bid_number="20260325006-00",
            title="보안 관제 고도화",
            issuer="행정안전부",
            budget="5억원",
            announcement_date="2026-03-25",
            deadline="2026-05-30 17:00",
            bid_type="일반경쟁",
            category="용역",
            detail_url="https://www.g2b.go.kr/notice/20260325006-00",
            attachments=[],
            raw_text="필수 인증 보유 필요.",
            source="scrape",
        )
        with patch(
            "app.services.g2b_collector.fetch_announcement_detail",
            new=AsyncMock(return_value=fake),
        ):
            imported = client.post(
                f"/projects/{pid}/imports/g2b-opportunity",
                json={"url_or_number": "20260325006-00"},
                headers=HEADERS,
            )
        assert imported.status_code == 200

        res = client.post(
            f"/projects/{pid}/procurement/override-reason",
            json={"reason": "기존 전략 고객 확보 목적상 예외적으로 proposal 작성 진행"},
            headers=HEADERS,
        )
        assert res.status_code == 200
        decision = res.json()["decision"]
        assert "[override_reason ts=" in decision["notes"]
        assert "actor=api_key_client" in decision["notes"]
        assert "기존 전략 고객 확보 목적상 예외적으로 proposal 작성 진행" in decision["notes"]

        retrieval = client.get(f"/projects/{pid}/procurement", headers=HEADERS)
        assert retrieval.status_code == 200
        assert "기존 전략 고객 확보 목적상 예외적으로 proposal 작성 진행" in retrieval.json()["decision"]["notes"]

    def test_override_reason_without_opportunity_returns_409(self, client):
        pid = self._pid(client)
        res = client.post(
            f"/projects/{pid}/procurement/override-reason",
            json={"reason": "추가 메모"},
            headers=HEADERS,
        )
        assert res.status_code == 409
        assert res.json()["detail"]["code"] == "procurement_opportunity_not_attached"


class TestProjectProcurementFeatureFlag:
    def test_procurement_routes_return_feature_disabled_when_flag_is_off(self, tmp_path, monkeypatch):
        client = _disabled_procurement_client(tmp_path, monkeypatch)
        pid = client.post("/projects", json=PROJ_PAYLOAD, headers=HEADERS).json()["project_id"]

        responses = [
            client.get(f"/projects/{pid}/procurement", headers=HEADERS),
            client.post(
                f"/projects/{pid}/imports/g2b-opportunity",
                json={"url_or_number": "20260325001-00"},
                headers=HEADERS,
            ),
            client.post(f"/projects/{pid}/procurement/evaluate", headers=HEADERS),
            client.post(f"/projects/{pid}/procurement/recommend", headers=HEADERS),
        ]

        for response in responses:
            assert response.status_code == 403
            assert response.json()["detail"]["code"] == "FEATURE_DISABLED"


# ---------------------------------------------------------------------------
# N. Document management API + download
# ---------------------------------------------------------------------------

class TestProjectDocumentApi:
    def _pid(self, client) -> str:
        return client.post("/projects", json=PROJ_PAYLOAD, headers=HEADERS).json()["project_id"]

    def test_add_document_endpoint(self, client):
        pid = self._pid(client)
        res = client.post(f"/projects/{pid}/documents", json={
            "request_id": "req-1",
            "bundle_id": "business_plan_kr",
            "title": "사업계획서",
            "docs": [{"doc_type": "report", "markdown": "# 내용"}],
        }, headers=HEADERS)
        assert res.status_code == 200
        assert "doc_id" in res.json()

    def test_add_document_increments_project_docs(self, client):
        pid = self._pid(client)
        client.post(f"/projects/{pid}/documents", json={
            "request_id": "r2", "bundle_id": "b", "title": "문서", "docs": []
        }, headers=HEADERS)
        proj = client.get(f"/projects/{pid}", headers=HEADERS).json()
        assert len(proj["documents"]) >= 1

    def test_remove_document_endpoint(self, client):
        pid = self._pid(client)
        doc_id = client.post(f"/projects/{pid}/documents", json={
            "request_id": "r3", "bundle_id": "b", "title": "삭제할 문서", "docs": []
        }, headers=HEADERS).json()["doc_id"]
        res = client.delete(f"/projects/{pid}/documents/{doc_id}", headers=HEADERS)
        assert res.status_code == 200
        assert res.json().get("ok") is True

    def test_download_project_doc_docx(self, client):
        pid = self._pid(client)
        doc_id = client.post(f"/projects/{pid}/documents", json={
            "request_id": "r4", "bundle_id": "b", "title": "다운로드 테스트",
            "docs": [{"doc_type": "report", "markdown": "# 내용"}],
        }, headers=HEADERS).json()["doc_id"]
        res = client.get(f"/projects/{pid}/documents/{doc_id}/download/docx", headers=HEADERS)
        assert res.status_code == 200
        ct = res.headers.get("content-type", "")
        cd = res.headers.get("content-disposition", "")
        assert "wordprocessingml" in ct or ".docx" in cd

    def test_download_project_doc_hwpx(self, client):
        pid = self._pid(client)
        doc_id = client.post(f"/projects/{pid}/documents", json={
            "request_id": "r5", "bundle_id": "b", "title": "HWP 테스트",
            "docs": [{"doc_type": "report", "markdown": "# 내용"}],
        }, headers=HEADERS).json()["doc_id"]
        res = client.get(f"/projects/{pid}/documents/{doc_id}/download/hwpx", headers=HEADERS)
        assert res.status_code == 200

    def test_download_unknown_format_returns_400(self, client):
        pid = self._pid(client)
        doc_id = client.post(f"/projects/{pid}/documents", json={
            "request_id": "r6", "bundle_id": "b", "title": "포맷 테스트", "docs": []
        }, headers=HEADERS).json()["doc_id"]
        res = client.get(f"/projects/{pid}/documents/{doc_id}/download/odt", headers=HEADERS)
        assert res.status_code == 400

    def test_download_nonexistent_project_returns_404(self, client):
        res = client.get("/projects/no-such/documents/no-doc/download/docx", headers=HEADERS)
        assert res.status_code == 404


# ---------------------------------------------------------------------------
# O. Search / archive / stats API
# ---------------------------------------------------------------------------

class TestProjectSearchAndStats:
    def _create_and_return_pid(self, client, name: str) -> str:
        return client.post("/projects", json={
            "name": name, "fiscal_year": YEAR
        }, headers=HEADERS).json()["project_id"]

    def test_search_returns_results(self, client):
        self._create_and_return_pid(client, "검색용 스마트팩토리 프로젝트")
        res = client.get("/projects/search?q=스마트팩토리", headers=HEADERS)
        assert res.status_code == 200
        data = res.json()
        assert "results" in data
        assert any("스마트팩토리" in r["project_name"] for r in data["results"])

    def test_search_empty_query_returns_empty(self, client):
        res = client.get("/projects/search?q=", headers=HEADERS)
        assert res.status_code == 200
        assert res.json()["results"] == []

    def test_stats_endpoint(self, client):
        res = client.get("/projects/stats", headers=HEADERS)
        assert res.status_code == 200
        data = res.json()
        assert "total_projects" in data
        assert "active_projects" in data
        assert "total_docs" in data

    def test_archive_endpoint_returns_fiscal_year(self, client):
        res = client.get(f"/projects/archive/{YEAR}", headers=HEADERS)
        assert res.status_code == 200
        data = res.json()
        assert data["fiscal_year"] == YEAR
        assert "projects" in data
        assert "total_docs" in data
        assert "bundle_breakdown" in data

    def test_list_with_fiscal_year_filter(self, client):
        client.post("/projects", json={"name": "연도필터테스트", "fiscal_year": 2020}, headers=HEADERS)
        res = client.get("/projects?fiscal_year=2020", headers=HEADERS)
        assert res.status_code == 200
        projs = res.json()["projects"]
        assert all(p["fiscal_year"] == 2020 for p in projs)


# ---------------------------------------------------------------------------
# P. Auto-link: generation auto-adds doc to project
# ---------------------------------------------------------------------------

class TestAutoLink:
    def test_generate_stream_with_project_id_adds_document(self, client):
        """After SSE generation with project_id, the project should have a document."""
        # Create a project first
        pid = client.post("/projects", json={
            "name": "자동 연결 테스트", "fiscal_year": YEAR
        }, headers=HEADERS).json()["project_id"]

        # Trigger generation with project_id (uses mock provider)
        gen_payload = {
            "title": "자동연결 테스트 문서",
            "goal": "프로젝트 자동 연결 확인",
            "bundle_type": "tech_decision",
            "project_id": pid,
        }
        with client.stream("POST", "/generate/stream", json=gen_payload, headers=HEADERS) as resp:
            events = [line for line in resp.iter_lines() if line.startswith("event: complete")]
            assert len(events) == 1

        # Project should now have the generated document
        proj = client.get(f"/projects/{pid}", headers=HEADERS).json()
        assert len(proj["documents"]) >= 1
        assert proj["documents"][0]["title"] == "자동연결 테스트 문서"

    def test_generate_stream_without_project_id_no_error(self, client):
        """Generation without project_id should work fine (no auto-link)."""
        gen_payload = {
            "title": "링크없는 문서",
            "goal": "프로젝트 없이 생성",
            "bundle_type": "tech_decision",
        }
        with client.stream("POST", "/generate/stream", json=gen_payload, headers=HEADERS) as resp:
            events = [line for line in resp.iter_lines() if line.startswith("event: complete")]
            assert len(events) == 1

    def test_generate_stream_blocks_no_go_downstream_without_override_reason(self, client):
        pid = client.post("/projects", json={
            "name": "NO_GO 하류 생성 차단", "fiscal_year": YEAR
        }, headers=HEADERS).json()["project_id"]
        client.app.state.procurement_store.upsert(
            ProcurementDecisionUpsert(
                project_id=pid,
                tenant_id="system",
                opportunity=NormalizedProcurementOpportunity(
                    source_kind="g2b",
                    source_id="R26-BLOCK-001",
                    title="보안 운영 고도화",
                    issuer="행정안전부",
                ),
                recommendation=ProcurementRecommendation(
                    value="NO_GO",
                    summary="필수 capability gap으로 downstream 진행 전 override 검토 필요",
                ),
            )
        )

        gen_payload = {
            "title": "차단 대상 proposal",
            "goal": "NO_GO downstream policy 확인",
            "bundle_type": "proposal_kr",
            "project_id": pid,
        }
        resp = client.post("/generate/stream", json=gen_payload, headers=HEADERS)

        assert resp.status_code == 409
        detail = resp.json()["detail"]
        assert detail["code"] == "procurement_override_reason_required"
        assert detail["project_id"] == pid
        assert detail["bundle_type"] == "proposal_kr"
        assert detail["recommendation"] == "NO_GO"
        assert detail["required_action"] == "save_override_reason"
        assert detail["focus_field"] == "project-procurement-override-reason"

    def test_generate_stream_allows_no_go_downstream_after_override_reason_saved(self, client):
        pid = client.post("/projects", json={
            "name": "NO_GO override 이후 진행", "fiscal_year": YEAR
        }, headers=HEADERS).json()["project_id"]
        client.app.state.procurement_store.upsert(
            ProcurementDecisionUpsert(
                project_id=pid,
                tenant_id="system",
                opportunity=NormalizedProcurementOpportunity(
                    source_kind="g2b",
                    source_id="R26-ALLOW-001",
                    title="데이터 통합 운영",
                    issuer="조달청",
                ),
                recommendation=ProcurementRecommendation(
                    value="NO_GO",
                    summary="예외 승인 없이는 downstream 진행 불가",
                ),
            )
        )

        council = client.post(
            f"/projects/{pid}/decision-council/run",
            json={"goal": "override 이후에도 proposal_kr handoff provenance를 유지한다."},
            headers=HEADERS,
        )
        assert council.status_code == 200
        council_session = council.json()
        assert council_session["current_procurement_binding_status"] == "current"

        override_res = client.post(
            f"/projects/{pid}/procurement/override-reason",
            json={"reason": "기존 전략 고객 유지 목적상 proposal 선행 검토"},
            headers=HEADERS,
        )
        assert override_res.status_code == 200
        updated_decision = override_res.json()["decision"]
        assert updated_decision["updated_at"] == council_session["source_procurement_updated_at"]

        latest_session = client.get(f"/projects/{pid}/decision-council", headers=HEADERS)
        assert latest_session.status_code == 200
        latest_body = latest_session.json()
        assert latest_body["current_procurement_binding_status"] == "current"
        assert latest_body["current_procurement_binding_reason_code"] == ""

        gen_payload = {
            "title": "override 이후 proposal",
            "goal": "override 저장 후 downstream 허용 확인",
            "bundle_type": "proposal_kr",
            "project_id": pid,
        }
        with client.stream("POST", "/generate/stream", json=gen_payload, headers=HEADERS) as resp:
            assert resp.status_code == 200
            events = [line for line in resp.iter_lines() if line.startswith("event: complete")]
            assert len(events) == 1

        project = client.get(f"/projects/{pid}", headers=HEADERS).json()
        proposal_docs = [doc for doc in project["documents"] if doc["bundle_id"] == "proposal_kr"]
        assert proposal_docs
        latest_doc = proposal_docs[-1]
        assert latest_doc["source_decision_council_session_id"] == council_session["session_id"]
        assert latest_doc["source_decision_council_session_revision"] == council_session["session_revision"]
        assert latest_doc["source_decision_council_direction"] == "do_not_proceed"

    def test_bid_decision_generation_uses_decision_council_handoff_and_project_provenance(self, client):
        pid = client.post("/projects", json={
            "name": "Decision Council 자동 연결", "fiscal_year": YEAR
        }, headers=HEADERS).json()["project_id"]
        client.app.state.procurement_store.upsert(
            ProcurementDecisionUpsert(
                project_id=pid,
                tenant_id="system",
                opportunity=NormalizedProcurementOpportunity(
                    source_kind="g2b",
                    source_id="R26-COUNCIL-HANDOFF-001",
                    title="입찰 참여 검토 대상 사업",
                    issuer="조달청",
                    budget="3억원",
                    deadline="2026-06-10 17:00",
                ),
                recommendation=ProcurementRecommendation(
                    value="GO",
                    summary="즉시 진행 가능한 기회",
                    evidence=["필수 자격 충족", "유사 실적 확보"],
                ),
            )
        )

        council = client.post(
            f"/projects/{pid}/decision-council/run",
            json={"goal": "bid_decision_kr에 사용할 Go 판단 근거를 정리한다."},
            headers=HEADERS,
        )
        assert council.status_code == 200
        council_session = council.json()

        result = client.app.state.service.generate_documents(
            GenerateRequest(
                title="Council handoff metadata",
                goal="Council handoff metadata 확인",
                bundle_type="bid_decision_kr",
                project_id=pid,
            ),
            request_id="req-decision-council-metadata",
            tenant_id="system",
        )
        assert result["metadata"]["decision_council_handoff_used"] is True
        assert result["metadata"]["decision_council_handoff_skipped_reason"] is None
        assert result["metadata"]["decision_council_session_id"] == council_session["session_id"]
        assert result["metadata"]["decision_council_direction"] == "proceed"
        assert result["metadata"]["decision_council_target_bundle"] == "bid_decision_kr"
        assert result["metadata"]["decision_council_applied_bundle"] == "bid_decision_kr"

        with client.stream(
            "POST",
            "/generate/stream",
            json={
                "title": "Decision Council 적용 문서",
                "goal": "Council provenance project auto-link 확인",
                "bundle_type": "bid_decision_kr",
                "project_id": pid,
            },
            headers=HEADERS,
        ) as resp:
            assert resp.status_code == 200
            events = [line for line in resp.iter_lines() if line.startswith("event: complete")]
            assert len(events) == 1

        project = client.get(f"/projects/{pid}", headers=HEADERS).json()
        latest_doc = project["documents"][-1]
        assert latest_doc["bundle_id"] == "bid_decision_kr"
        assert latest_doc["source_decision_council_session_id"] == council_session["session_id"]
        assert latest_doc["source_decision_council_session_revision"] == council_session["session_revision"]
        assert latest_doc["source_decision_council_direction"] == "proceed"
        assert latest_doc["decision_council_document_status"] == "current"
        assert latest_doc["decision_council_document_status_tone"] == "success"
        assert latest_doc["decision_council_document_status_copy"] == "현재 council 기준"

    def test_proposal_generation_uses_decision_council_handoff_and_project_provenance(self, client):
        pid = client.post("/projects", json={
            "name": "Decision Council proposal 자동 연결", "fiscal_year": YEAR
        }, headers=HEADERS).json()["project_id"]
        client.app.state.procurement_store.upsert(
            ProcurementDecisionUpsert(
                project_id=pid,
                tenant_id="system",
                opportunity=NormalizedProcurementOpportunity(
                    source_kind="g2b",
                    source_id="R26-COUNCIL-PROPOSAL-001",
                    title="제안서 handoff 대상 사업",
                    issuer="조달청",
                    budget="7억원",
                    deadline="2026-07-10 17:00",
                ),
                recommendation=ProcurementRecommendation(
                    value="CONDITIONAL_GO",
                    summary="조건부 진행 가능한 기회",
                    evidence=["핵심 역량은 충분", "제안서에서 조건/리스크 명시 필요"],
                ),
            )
        )

        council = client.post(
            f"/projects/{pid}/decision-council/run",
            json={"goal": "proposal_kr에 사용할 전략 방향과 리스크를 정리한다."},
            headers=HEADERS,
        )
        assert council.status_code == 200
        council_session = council.json()
        assert council_session["supported_bundle_types"] == ["bid_decision_kr", "proposal_kr"]

        result = client.app.state.service.generate_documents(
            GenerateRequest(
                title="Council proposal metadata",
                goal="Council handoff proposal metadata 확인",
                bundle_type="proposal_kr",
                project_id=pid,
            ),
            request_id="req-decision-council-proposal-metadata",
            tenant_id="system",
        )
        assert result["metadata"]["decision_council_handoff_used"] is True
        assert result["metadata"]["decision_council_handoff_skipped_reason"] is None
        assert result["metadata"]["decision_council_session_id"] == council_session["session_id"]
        assert result["metadata"]["decision_council_direction"] == "proceed_with_conditions"
        assert result["metadata"]["decision_council_target_bundle"] == "bid_decision_kr"
        assert result["metadata"]["decision_council_applied_bundle"] == "proposal_kr"

        with client.stream(
            "POST",
            "/generate/stream",
            json={
                "title": "Decision Council 적용 제안서",
                "goal": "Council provenance proposal auto-link 확인",
                "bundle_type": "proposal_kr",
                "project_id": pid,
            },
            headers=HEADERS,
        ) as resp:
            assert resp.status_code == 200
            events = [line for line in resp.iter_lines() if line.startswith("event: complete")]
            assert len(events) == 1

        project = client.get(f"/projects/{pid}", headers=HEADERS).json()
        latest_doc = project["documents"][-1]
        assert latest_doc["bundle_id"] == "proposal_kr"
        assert latest_doc["source_decision_council_session_id"] == council_session["session_id"]
        assert latest_doc["source_decision_council_session_revision"] == council_session["session_revision"]
        assert latest_doc["source_decision_council_direction"] == "proceed_with_conditions"
        assert latest_doc["decision_council_document_status"] == "current"
        assert latest_doc["decision_council_document_status_tone"] == "success"
        assert latest_doc["decision_council_document_status_copy"] == "현재 council 기준"

    def test_bid_decision_generation_skips_stale_decision_council_handoff_after_procurement_update(self, client):
        pid = client.post("/projects", json={
            "name": "Decision Council stale guard", "fiscal_year": YEAR
        }, headers=HEADERS).json()["project_id"]
        initial = client.app.state.procurement_store.upsert(
            ProcurementDecisionUpsert(
                project_id=pid,
                tenant_id="system",
                opportunity=NormalizedProcurementOpportunity(
                    source_kind="g2b",
                    source_id="R26-COUNCIL-STALE-001",
                    title="Council stale guard 사업",
                    issuer="조달청",
                ),
                recommendation=ProcurementRecommendation(
                    value="GO",
                    summary="초기 recommendation",
                ),
            )
        )

        council = client.post(
            f"/projects/{pid}/decision-council/run",
            json={"goal": "현재 recommendation을 기준으로 handoff를 만든다."},
            headers=HEADERS,
        )
        assert council.status_code == 200
        council_session = council.json()
        assert council_session["source_procurement_decision_id"] == initial.decision_id
        assert council_session["source_procurement_updated_at"] == initial.updated_at

        with client.stream(
            "POST",
            "/generate/stream",
            json={
                "title": "Council stale baseline",
                "goal": "stale 이전 기준의 bid decision 문서를 만든다.",
                "bundle_type": "bid_decision_kr",
                "project_id": pid,
            },
            headers=HEADERS,
        ) as resp:
            assert resp.status_code == 200
            list(resp.iter_lines())

        updated = client.app.state.procurement_store.upsert(
            ProcurementDecisionUpsert(
                project_id=pid,
                tenant_id="system",
                opportunity=NormalizedProcurementOpportunity(
                    source_kind="g2b",
                    source_id="R26-COUNCIL-STALE-001",
                    title="Council stale guard 사업",
                    issuer="조달청",
                ),
                recommendation=ProcurementRecommendation(
                    value="NO_GO",
                    summary="업데이트 이후 recommendation",
                ),
                missing_data=["필수 reference 재확인"],
            )
        )
        assert updated.decision_id == initial.decision_id
        assert updated.updated_at != initial.updated_at

        latest = client.get(f"/projects/{pid}/decision-council", headers=HEADERS)
        assert latest.status_code == 200
        latest_session = latest.json()
        assert latest_session["session_id"] == council_session["session_id"]
        assert latest_session["current_procurement_binding_status"] == "stale"
        assert latest_session["current_procurement_binding_reason_code"] == "procurement_updated"
        assert latest_session["current_procurement_updated_at"] == updated.updated_at
        assert latest_session["source_procurement_recommendation_value"] == "GO"
        assert latest_session["current_procurement_recommendation_value"] == "NO_GO"
        assert latest_session["current_procurement_missing_data_count"] == 1
        assert "다시 실행해야" in latest_session["current_procurement_binding_summary"]
        assert "GO → NO_GO" in latest_session["current_procurement_binding_summary"]

        result = client.app.state.service.generate_documents(
            GenerateRequest(
                title="Council stale guard",
                goal="stale council handoff가 주입되지 않아야 한다.",
                bundle_type="bid_decision_kr",
                project_id=pid,
            ),
            request_id="req-decision-council-stale",
            tenant_id="system",
        )
        assert result["metadata"]["decision_council_handoff_used"] is False
        assert result["metadata"]["decision_council_handoff_skipped_reason"] == "stale_procurement_context"
        assert result["metadata"]["decision_council_session_id"] is None
        assert result["metadata"]["decision_council_direction"] is None
        assert result["metadata"]["decision_council_applied_bundle"] is None
        project = client.get(f"/projects/{pid}", headers=HEADERS).json()
        latest_doc = project["documents"][-1]
        assert latest_doc["source_decision_council_session_id"] == council_session["session_id"]
        assert latest_doc["decision_council_document_status"] == "stale_procurement"
        assert latest_doc["decision_council_document_status_tone"] == "danger"
        assert latest_doc["decision_council_document_status_copy"] == "현재 procurement 대비 이전 council 기준"

    def test_proposal_generation_skips_stale_decision_council_handoff_after_procurement_update(self, client):
        pid = client.post("/projects", json={
            "name": "Decision Council stale proposal guard", "fiscal_year": YEAR
        }, headers=HEADERS).json()["project_id"]
        initial = client.app.state.procurement_store.upsert(
            ProcurementDecisionUpsert(
                project_id=pid,
                tenant_id="system",
                opportunity=NormalizedProcurementOpportunity(
                    source_kind="g2b",
                    source_id="R26-COUNCIL-STALE-PROPOSAL-001",
                    title="Council stale proposal guard 사업",
                    issuer="조달청",
                ),
                recommendation=ProcurementRecommendation(
                    value="GO",
                    summary="초기 recommendation",
                ),
            )
        )

        council = client.post(
            f"/projects/{pid}/decision-council/run",
            json={"goal": "proposal_kr 기준 handoff를 만든다."},
            headers=HEADERS,
        )
        assert council.status_code == 200
        council_session = council.json()

        with client.stream(
            "POST",
            "/generate/stream",
            json={
                "title": "Council stale proposal baseline",
                "goal": "stale 이전 기준의 proposal 문서를 만든다.",
                "bundle_type": "proposal_kr",
                "project_id": pid,
            },
            headers=HEADERS,
        ) as resp:
            assert resp.status_code == 200
            list(resp.iter_lines())

        updated = client.app.state.procurement_store.upsert(
            ProcurementDecisionUpsert(
                project_id=pid,
                tenant_id="system",
                opportunity=NormalizedProcurementOpportunity(
                    source_kind="g2b",
                    source_id="R26-COUNCIL-STALE-PROPOSAL-001",
                    title="Council stale proposal guard 사업",
                    issuer="조달청",
                ),
                recommendation=ProcurementRecommendation(
                    value="NO_GO",
                    summary="업데이트 이후 recommendation",
                ),
                missing_data=["필수 reference 재확인"],
            )
        )
        assert updated.decision_id == initial.decision_id
        assert updated.updated_at != initial.updated_at

        result = client.app.state.service.generate_documents(
            GenerateRequest(
                title="Council stale proposal guard",
                goal="stale council handoff가 proposal에 주입되지 않아야 한다.",
                bundle_type="proposal_kr",
                project_id=pid,
            ),
            request_id="req-decision-council-stale-proposal",
            tenant_id="system",
        )
        assert result["metadata"]["decision_council_handoff_used"] is False
        assert result["metadata"]["decision_council_handoff_skipped_reason"] == "stale_procurement_context"
        assert result["metadata"]["decision_council_session_id"] is None
        assert result["metadata"]["decision_council_direction"] is None
        assert result["metadata"]["decision_council_applied_bundle"] is None

        project = client.get(f"/projects/{pid}", headers=HEADERS).json()
        latest_doc = project["documents"][-1]
        assert latest_doc["bundle_id"] == "proposal_kr"
        assert latest_doc["source_decision_council_session_id"] == council_session["session_id"]
        assert latest_doc["decision_council_document_status"] == "stale_procurement"
        assert latest_doc["decision_council_document_status_tone"] == "danger"
        assert latest_doc["decision_council_document_status_copy"] == "현재 procurement 대비 이전 council 기준"

    def test_project_detail_marks_older_bid_decision_doc_as_previous_council_revision(self, client):
        pid = client.post("/projects", json={
            "name": "Decision Council revision drift", "fiscal_year": YEAR
        }, headers=HEADERS).json()["project_id"]
        record = client.app.state.procurement_store.upsert(
            ProcurementDecisionUpsert(
                project_id=pid,
                tenant_id="system",
                opportunity=NormalizedProcurementOpportunity(
                    source_kind="g2b",
                    source_id="R26-COUNCIL-REV-001",
                    title="Council revision drift 사업",
                    issuer="조달청",
                ),
                recommendation=ProcurementRecommendation(
                    value="GO",
                    summary="초기 recommendation",
                ),
            )
        )

        first_council = client.post(
            f"/projects/{pid}/decision-council/run",
            json={"goal": "첫 번째 council handoff를 만든다."},
            headers=HEADERS,
        )
        assert first_council.status_code == 200
        first_session = first_council.json()

        client.app.state.service.generate_documents(
            GenerateRequest(
                title="Council revision doc",
                goal="첫 council 기준의 bid decision 문서를 만든다.",
                bundle_type="bid_decision_kr",
                project_id=pid,
            ),
            request_id="req-decision-council-revision-1",
            tenant_id="system",
        )
        with client.stream(
            "POST",
            "/generate/stream",
            json={
                "title": "Council revision doc",
                "goal": "첫 council 기준의 bid decision 문서를 만든다.",
                "bundle_type": "bid_decision_kr",
                "project_id": pid,
            },
            headers=HEADERS,
        ) as resp:
            assert resp.status_code == 200
            list(resp.iter_lines())

        rerun = client.post(
            f"/projects/{pid}/decision-council/run",
            json={"goal": "같은 procurement 기준에서 council revision을 올린다."},
            headers=HEADERS,
        )
        assert rerun.status_code == 200
        latest_session = rerun.json()
        assert latest_session["session_id"] == first_session["session_id"]
        assert latest_session["session_revision"] == 2
        assert latest_session["source_procurement_decision_id"] == record.decision_id

        project = client.get(f"/projects/{pid}", headers=HEADERS).json()
        latest_doc = project["documents"][-1]
        assert latest_doc["source_decision_council_session_id"] == first_session["session_id"]
        assert latest_doc["source_decision_council_session_revision"] == 1
        assert latest_doc["decision_council_document_status"] == "stale_revision"
        assert latest_doc["decision_council_document_status_tone"] == "warning"
        assert latest_doc["decision_council_document_status_copy"] == "이전 council revision (r1)"


class TestProjectDocumentReuseFlows:
    def test_project_document_can_start_existing_approval_flow(self, client):
        pid = client.post("/projects", json=PROJ_PAYLOAD, headers=HEADERS).json()["project_id"]
        created = client.post(
            f"/projects/{pid}/documents",
            json={
                "request_id": "req-project-approval",
                "bundle_id": "bid_decision_kr",
                "title": "입찰 의사결정 문서",
                "docs": [{"doc_type": "go_no_go_memo", "markdown": "# 판단 요약"}],
            },
            headers=HEADERS,
        )
        assert created.status_code == 200

        project = client.get(f"/projects/{pid}", headers=HEADERS).json()
        doc = project["documents"][0]
        approval = client.post(
            "/approvals",
            json={
                "request_id": doc["request_id"],
                "bundle_id": doc["bundle_id"],
                "title": doc["title"],
                "drafter": "홍길동",
                "docs": json.loads(doc["doc_snapshot"]),
                "gov_options": doc.get("gov_options"),
            },
            headers=HEADERS,
        )
        assert approval.status_code == 200

        refreshed = client.get(f"/projects/{pid}", headers=HEADERS).json()
        assert refreshed["documents"][0]["approval_id"] == approval.json()["approval_id"]
        assert refreshed["documents"][0]["approval_status"] == "draft"

    def test_project_document_can_create_share_link(self, client):
        pid = client.post("/projects", json=PROJ_PAYLOAD, headers=HEADERS).json()["project_id"]
        created = client.post(
            f"/projects/{pid}/documents",
            json={
                "request_id": "req-project-share",
                "bundle_id": "bid_decision_kr",
                "title": "공유용 판단 문서",
                "docs": [{"doc_type": "go_no_go_memo", "markdown": "# 공유 테스트"}],
            },
            headers=HEADERS,
        )
        assert created.status_code == 200

        project = client.get(f"/projects/{pid}", headers=HEADERS).json()
        doc = project["documents"][0]
        response = client.post(
            "/share",
            json={
                "request_id": doc["request_id"],
                "title": doc["title"],
                "bundle_id": doc["bundle_id"],
                "expires_days": 7,
            },
            headers=_auth_headers(client),
        )
        assert response.status_code == 200
        assert response.json()["share_url"].startswith("/shared/")
