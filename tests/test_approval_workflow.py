"""tests/test_approval_workflow.py — Approval workflow system tests.

Covers:
  A. ApprovalStore.create — record creation & defaults
  B. ApprovalStore.get / list_by_tenant / list_by_user
  C. Status transitions: valid paths
  D. Status transitions: invalid paths (ValueError)
  E. Full happy-path flow: draft → in_review → reviewer_approved → approved
  F. Rejection flow: draft → in_review → rejected
  G. Change-request → resubmit flow
  H. update_docs / add_comment
  I. Tenant isolation
  J. Thread safety
  K. API endpoints — CRUD + actions
  L. API: download endpoint (approved only)
  M. API: list with status / role filters
"""
from __future__ import annotations

import json
import tempfile
import threading
import time
from dataclasses import asdict
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.storage.approval_store import (
    ApprovalRecord,
    ApprovalStatus,
    ApprovalStore,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

DOCS = [{"doc_type": "report", "markdown": "# 보고서\n내용"}]
GOV_OPTS = {"org_name": "행정안전부", "is_government_format": True}


def _store(tmp_path: Path) -> ApprovalStore:
    return ApprovalStore(base_dir=str(tmp_path))


def _create_rec(store: ApprovalStore, tenant: str = "t1", **kwargs) -> ApprovalRecord:
    defaults = dict(
        tenant_id=tenant,
        request_id="req-1",
        bundle_id="business_plan_kr",
        title="테스트 문서",
        drafter="홍길동",
        docs=DOCS,
    )
    defaults.update(kwargs)
    return store.create(**defaults)


# ---------------------------------------------------------------------------
# A. create
# ---------------------------------------------------------------------------

class TestApprovalStoreCreate:
    def test_returns_approval_record(self, tmp_path):
        store = _store(tmp_path)
        rec = _create_rec(store)
        assert isinstance(rec, ApprovalRecord)

    def test_status_is_draft(self, tmp_path):
        rec = _create_rec(_store(tmp_path))
        assert rec.status == ApprovalStatus.DRAFT.value

    def test_approval_id_assigned(self, tmp_path):
        rec = _create_rec(_store(tmp_path))
        assert rec.approval_id and len(rec.approval_id) == 36  # UUID4

    def test_drafter_stored(self, tmp_path):
        rec = _create_rec(_store(tmp_path), drafter="김철수")
        assert rec.drafter == "김철수"

    def test_title_stored(self, tmp_path):
        rec = _create_rec(_store(tmp_path), title="2026 사업계획서")
        assert rec.title == "2026 사업계획서"

    def test_doc_snapshot_set_to_docs_json(self, tmp_path):
        rec = _create_rec(_store(tmp_path))
        assert json.loads(rec.doc_snapshot) == DOCS

    def test_current_docs_equals_snapshot_on_create(self, tmp_path):
        rec = _create_rec(_store(tmp_path))
        assert rec.doc_snapshot == rec.current_docs

    def test_reviewer_none_on_create(self, tmp_path):
        rec = _create_rec(_store(tmp_path))
        assert rec.reviewer is None

    def test_approver_none_on_create(self, tmp_path):
        rec = _create_rec(_store(tmp_path))
        assert rec.approver is None

    def test_reviewer_approved_false_on_create(self, tmp_path):
        rec = _create_rec(_store(tmp_path))
        assert rec.reviewer_approved is False

    def test_comments_empty_on_create(self, tmp_path):
        rec = _create_rec(_store(tmp_path))
        assert rec.comments == []

    def test_gov_options_stored(self, tmp_path):
        rec = _create_rec(_store(tmp_path), gov_options=GOV_OPTS)
        assert rec.gov_options == GOV_OPTS

    def test_persisted_to_disk(self, tmp_path):
        store = _store(tmp_path)
        rec = _create_rec(store)
        # fresh store, same dir
        store2 = _store(tmp_path)
        rec2 = store2.get(rec.approval_id)
        assert rec2 is not None
        assert rec2.title == rec.title


# ---------------------------------------------------------------------------
# B. get / list_by_tenant / list_by_user
# ---------------------------------------------------------------------------

class TestApprovalStoreRead:
    def test_get_existing(self, tmp_path):
        store = _store(tmp_path)
        rec = _create_rec(store)
        got = store.get(rec.approval_id)
        assert got is not None
        assert got.approval_id == rec.approval_id

    def test_get_nonexistent_returns_none(self, tmp_path):
        assert _store(tmp_path).get("nonexistent-id") is None

    def test_list_by_tenant_returns_all(self, tmp_path):
        store = _store(tmp_path)
        for _ in range(3):
            _create_rec(store)
        recs = store.list_by_tenant("t1")
        assert len(recs) == 3

    def test_list_by_tenant_empty_other_tenant(self, tmp_path):
        store = _store(tmp_path)
        _create_rec(store, tenant="t1")
        assert store.list_by_tenant("t2") == []

    def test_list_by_tenant_status_filter(self, tmp_path):
        store = _store(tmp_path)
        r1 = _create_rec(store)
        store.submit_for_review(r1.approval_id, reviewer="검토자")
        _create_rec(store)  # stays draft
        in_review = store.list_by_tenant("t1", status="in_review")
        assert len(in_review) == 1

    def test_list_by_user_drafter(self, tmp_path):
        store = _store(tmp_path)
        _create_rec(store, drafter="홍길동")
        _create_rec(store, drafter="이영희")
        recs = store.list_by_user("t1", "홍길동", "drafter")
        assert len(recs) == 1
        assert recs[0].drafter == "홍길동"

    def test_list_sorted_newest_first(self, tmp_path):
        store = _store(tmp_path)
        r1 = _create_rec(store, title="첫째")
        time.sleep(0.01)
        r2 = _create_rec(store, title="둘째")
        recs = store.list_by_tenant("t1")
        assert recs[0].approval_id == r2.approval_id  # newest first


# ---------------------------------------------------------------------------
# C. Valid status transitions
# ---------------------------------------------------------------------------

class TestValidTransitions:
    def test_draft_to_in_review(self, tmp_path):
        store = _store(tmp_path)
        rec = _create_rec(store)
        updated = store.submit_for_review(rec.approval_id, reviewer="검토자A")
        assert updated.status == ApprovalStatus.IN_REVIEW.value

    def test_submit_sets_reviewer(self, tmp_path):
        store = _store(tmp_path)
        rec = _create_rec(store)
        updated = store.submit_for_review(rec.approval_id, reviewer="검토자A")
        assert updated.reviewer == "검토자A"

    def test_submit_sets_submitted_at(self, tmp_path):
        store = _store(tmp_path)
        rec = _create_rec(store)
        updated = store.submit_for_review(rec.approval_id, reviewer="검토자A")
        assert updated.submitted_at is not None

    def test_in_review_to_changes_requested(self, tmp_path):
        store = _store(tmp_path)
        rec = _create_rec(store)
        store.submit_for_review(rec.approval_id, reviewer="검토자A")
        updated = store.request_changes(rec.approval_id, author="검토자A", comment="수정 필요")
        assert updated.status == ApprovalStatus.CHANGES_REQUESTED.value

    def test_request_changes_adds_comment(self, tmp_path):
        store = _store(tmp_path)
        rec = _create_rec(store)
        store.submit_for_review(rec.approval_id, reviewer="검토자A")
        updated = store.request_changes(rec.approval_id, author="검토자A", comment="수정 필요")
        assert len(updated.comments) == 1
        assert updated.comments[0].is_change_request is True

    def test_changes_requested_to_in_review_again(self, tmp_path):
        store = _store(tmp_path)
        rec = _create_rec(store)
        store.submit_for_review(rec.approval_id, reviewer="검토자A")
        store.request_changes(rec.approval_id, author="검토자A", comment="수정 필요")
        updated = store.submit_for_review(rec.approval_id, reviewer="검토자A")
        assert updated.status == ApprovalStatus.IN_REVIEW.value

    def test_resubmit_resets_reviewer_approved(self, tmp_path):
        store = _store(tmp_path)
        rec = _create_rec(store)
        store.submit_for_review(rec.approval_id, reviewer="검토자A")
        store.approve_review(rec.approval_id, author="검토자A")
        store.request_changes(rec.approval_id, author="검토자A", comment="재수정")
        updated = store.submit_for_review(rec.approval_id, reviewer="검토자A")
        assert updated.reviewer_approved is False

    def test_approve_review_sets_flag(self, tmp_path):
        store = _store(tmp_path)
        rec = _create_rec(store)
        store.submit_for_review(rec.approval_id, reviewer="검토자A")
        updated = store.approve_review(rec.approval_id, author="검토자A")
        assert updated.reviewer_approved is True

    def test_approve_review_status_stays_in_review(self, tmp_path):
        store = _store(tmp_path)
        rec = _create_rec(store)
        store.submit_for_review(rec.approval_id, reviewer="검토자A")
        updated = store.approve_review(rec.approval_id, author="검토자A")
        assert updated.status == ApprovalStatus.IN_REVIEW.value

    def test_approve_review_sets_reviewed_at(self, tmp_path):
        store = _store(tmp_path)
        rec = _create_rec(store)
        store.submit_for_review(rec.approval_id, reviewer="검토자A")
        updated = store.approve_review(rec.approval_id, author="검토자A")
        assert updated.reviewed_at is not None

    def test_approve_final_sets_approved(self, tmp_path):
        store = _store(tmp_path)
        rec = _create_rec(store)
        store.submit_for_review(rec.approval_id, reviewer="검토자A")
        store.approve_review(rec.approval_id, author="검토자A")
        updated = store.approve_final(rec.approval_id, author="결재자B")
        assert updated.status == ApprovalStatus.APPROVED.value

    def test_approve_final_sets_approved_at(self, tmp_path):
        store = _store(tmp_path)
        rec = _create_rec(store)
        store.submit_for_review(rec.approval_id, reviewer="검토자A")
        store.approve_review(rec.approval_id, author="검토자A")
        updated = store.approve_final(rec.approval_id, author="결재자B")
        assert updated.approved_at is not None

    def test_reject_from_in_review(self, tmp_path):
        store = _store(tmp_path)
        rec = _create_rec(store)
        store.submit_for_review(rec.approval_id, reviewer="검토자A")
        updated = store.reject(rec.approval_id, author="결재자B", comment="반려")
        assert updated.status == ApprovalStatus.REJECTED.value

    def test_reject_sets_rejected_at(self, tmp_path):
        store = _store(tmp_path)
        rec = _create_rec(store)
        store.submit_for_review(rec.approval_id, reviewer="검토자A")
        updated = store.reject(rec.approval_id, author="결재자B", comment="반려")
        assert updated.rejected_at is not None

    def test_reject_adds_comment(self, tmp_path):
        store = _store(tmp_path)
        rec = _create_rec(store)
        store.submit_for_review(rec.approval_id, reviewer="검토자A")
        updated = store.reject(rec.approval_id, author="결재자B", comment="사유 있음")
        assert any(c.content == "사유 있음" for c in updated.comments)


# ---------------------------------------------------------------------------
# D. Invalid transitions (ValueError)
# ---------------------------------------------------------------------------

class TestInvalidTransitions:
    def test_submit_from_in_review_raises(self, tmp_path):
        store = _store(tmp_path)
        rec = _create_rec(store)
        store.submit_for_review(rec.approval_id, reviewer="검토자A")
        with pytest.raises(ValueError, match="상태 전환 오류"):
            store.submit_for_review(rec.approval_id, reviewer="검토자A")

    def test_request_changes_from_draft_raises(self, tmp_path):
        store = _store(tmp_path)
        rec = _create_rec(store)
        with pytest.raises(ValueError, match="상태 전환 오류"):
            store.request_changes(rec.approval_id, author="검토자A", comment="X")

    def test_approve_final_without_reviewer_approved_raises(self, tmp_path):
        store = _store(tmp_path)
        rec = _create_rec(store)
        store.submit_for_review(rec.approval_id, reviewer="검토자A")
        with pytest.raises(ValueError, match="검토자 승인"):
            store.approve_final(rec.approval_id, author="결재자B")

    def test_approve_final_from_draft_raises(self, tmp_path):
        store = _store(tmp_path)
        rec = _create_rec(store)
        with pytest.raises(ValueError, match="상태 전환 오류"):
            store.approve_final(rec.approval_id, author="결재자B")

    def test_reject_from_draft_raises(self, tmp_path):
        store = _store(tmp_path)
        rec = _create_rec(store)
        with pytest.raises(ValueError, match="상태 전환 오류"):
            store.reject(rec.approval_id, author="결재자B", comment="X")

    def test_reject_approved_raises(self, tmp_path):
        store = _store(tmp_path)
        rec = _create_rec(store)
        store.submit_for_review(rec.approval_id, reviewer="검토자A")
        store.approve_review(rec.approval_id, author="검토자A")
        store.approve_final(rec.approval_id, author="결재자B")
        with pytest.raises(ValueError, match="상태 전환 오류"):
            store.reject(rec.approval_id, author="결재자B", comment="너무 늦음")

    def test_approve_review_from_draft_raises(self, tmp_path):
        store = _store(tmp_path)
        rec = _create_rec(store)
        with pytest.raises(ValueError, match="상태 전환 오류"):
            store.approve_review(rec.approval_id, author="검토자A")

    def test_get_nonexistent_raises_key_error(self, tmp_path):
        store = _store(tmp_path)
        with pytest.raises(KeyError):
            store.submit_for_review("nonexistent", reviewer="X")


# ---------------------------------------------------------------------------
# E. Full happy-path flow
# ---------------------------------------------------------------------------

class TestHappyPathFlow:
    def test_full_flow_status_sequence(self, tmp_path):
        store = _store(tmp_path)

        # 1. Create (기안)
        rec = _create_rec(store, drafter="기안자", title="완전한 보고서")
        assert rec.status == "draft"

        # 2. Submit for review (검토 요청)
        rec = store.submit_for_review(rec.approval_id, reviewer="검토자A")
        assert rec.status == "in_review"
        assert rec.reviewer == "검토자A"

        # 3. Reviewer approves (검토 승인)
        rec = store.approve_review(rec.approval_id, author="검토자A", comment="검토 완료")
        assert rec.status == "in_review"  # status unchanged
        assert rec.reviewer_approved is True
        assert len(rec.comments) == 1

        # 4. Final approval (최종 결재)
        rec = store.approve_final(rec.approval_id, author="결재자B", comment="승인합니다")
        assert rec.status == "approved"
        assert rec.approved_at is not None
        assert len(rec.comments) == 2  # reviewer + approver comments

    def test_full_flow_all_timestamps_set(self, tmp_path):
        store = _store(tmp_path)
        rec = _create_rec(store)
        assert rec.created_at is not None

        rec = store.submit_for_review(rec.approval_id, reviewer="검토자A")
        assert rec.submitted_at is not None

        rec = store.approve_review(rec.approval_id, author="검토자A")
        assert rec.reviewed_at is not None

        rec = store.approve_final(rec.approval_id, author="결재자B")
        assert rec.approved_at is not None


# ---------------------------------------------------------------------------
# F. Rejection flow
# ---------------------------------------------------------------------------

class TestRejectionFlow:
    def test_rejection_flow(self, tmp_path):
        store = _store(tmp_path)
        rec = _create_rec(store)
        store.submit_for_review(rec.approval_id, reviewer="검토자A")
        rec = store.reject(rec.approval_id, author="결재자B", comment="재작성 필요")
        assert rec.status == "rejected"
        assert rec.rejected_at is not None

    def test_rejection_comment_stored(self, tmp_path):
        store = _store(tmp_path)
        rec = _create_rec(store)
        store.submit_for_review(rec.approval_id, reviewer="검토자A")
        rec = store.reject(rec.approval_id, author="결재자B", comment="재작성 필요")
        assert rec.comments[0].content == "재작성 필요"
        assert rec.comments[0].author == "결재자B"

    def test_rejection_comment_stage_is_approval(self, tmp_path):
        store = _store(tmp_path)
        rec = _create_rec(store)
        store.submit_for_review(rec.approval_id, reviewer="검토자A")
        rec = store.reject(rec.approval_id, author="결재자B", comment="X")
        assert rec.comments[0].stage == "approval"


# ---------------------------------------------------------------------------
# G. Change-request → resubmit flow
# ---------------------------------------------------------------------------

class TestChangeRequestFlow:
    def test_change_request_resubmit_full_cycle(self, tmp_path):
        store = _store(tmp_path)
        rec = _create_rec(store)

        # 1. Submit
        rec = store.submit_for_review(rec.approval_id, reviewer="검토자A")
        assert rec.status == "in_review"

        # 2. Request changes
        rec = store.request_changes(rec.approval_id, author="검토자A", comment="3절 보완")
        assert rec.status == "changes_requested"
        assert rec.reviewer_approved is False

        # 3. Update docs
        new_docs = [{"doc_type": "report", "markdown": "# 수정된 보고서\n내용"}]
        rec = store.update_docs(rec.approval_id, new_docs)
        assert json.loads(rec.current_docs) == new_docs

        # 4. Re-submit
        rec = store.submit_for_review(rec.approval_id, reviewer="검토자A")
        assert rec.status == "in_review"

        # 5. Reviewer approves → final approve
        store.approve_review(rec.approval_id, author="검토자A")
        rec = store.approve_final(rec.approval_id, author="결재자B")
        assert rec.status == "approved"

    def test_doc_snapshot_immutable_after_update(self, tmp_path):
        """doc_snapshot should remain the original submission version."""
        store = _store(tmp_path)
        rec = _create_rec(store)
        original_snapshot = rec.doc_snapshot

        store.submit_for_review(rec.approval_id, reviewer="검토자A")
        store.request_changes(rec.approval_id, author="검토자A", comment="X")
        new_docs = [{"doc_type": "report", "markdown": "# 새 내용"}]
        rec = store.update_docs(rec.approval_id, new_docs)

        # current_docs updated, snapshot unchanged
        assert rec.current_docs != original_snapshot
        assert rec.doc_snapshot == original_snapshot


# ---------------------------------------------------------------------------
# H. update_docs / add_comment
# ---------------------------------------------------------------------------

class TestUpdateDocsAndComments:
    def test_update_docs_changes_current_docs(self, tmp_path):
        store = _store(tmp_path)
        rec = _create_rec(store)
        new_docs = [{"doc_type": "x", "markdown": "새 내용"}]
        updated = store.update_docs(rec.approval_id, new_docs)
        assert json.loads(updated.current_docs) == new_docs

    def test_update_docs_does_not_change_snapshot(self, tmp_path):
        store = _store(tmp_path)
        rec = _create_rec(store)
        snapshot_before = rec.doc_snapshot
        store.update_docs(rec.approval_id, [{"doc_type": "x", "markdown": "X"}])
        rec2 = store.get(rec.approval_id)
        assert rec2.doc_snapshot == snapshot_before

    def test_add_comment_increases_count(self, tmp_path):
        store = _store(tmp_path)
        rec = _create_rec(store)
        store.add_comment(rec.approval_id, author="검토자A", content="좋습니다", stage="review")
        rec2 = store.get(rec.approval_id)
        assert len(rec2.comments) == 1

    def test_add_comment_fields(self, tmp_path):
        store = _store(tmp_path)
        rec = _create_rec(store)
        store.add_comment(rec.approval_id, author="검토자A", content="의견", stage="review", is_change_request=True)
        rec2 = store.get(rec.approval_id)
        c = rec2.comments[0]
        assert c.author == "검토자A"
        assert c.content == "의견"
        assert c.stage == "review"
        assert c.is_change_request is True


# ---------------------------------------------------------------------------
# I. Tenant isolation
# ---------------------------------------------------------------------------

class TestTenantIsolation:
    def test_tenants_see_only_own_records(self, tmp_path):
        store = _store(tmp_path)
        _create_rec(store, tenant="tenant_a")
        _create_rec(store, tenant="tenant_b")
        a_recs = store.list_by_tenant("tenant_a")
        b_recs = store.list_by_tenant("tenant_b")
        assert len(a_recs) == 1
        assert len(b_recs) == 1

    def test_same_approval_id_not_in_other_tenant(self, tmp_path):
        store = _store(tmp_path)
        rec_a = _create_rec(store, tenant="tenant_a")
        b_recs = store.list_by_tenant("tenant_b")
        assert all(r.approval_id != rec_a.approval_id for r in b_recs)

    def test_separate_json_files_per_tenant(self, tmp_path):
        store = _store(tmp_path)
        _create_rec(store, tenant="alpha")
        _create_rec(store, tenant="beta")
        assert (tmp_path / "tenants" / "alpha" / "approvals.json").exists()
        assert (tmp_path / "tenants" / "beta" / "approvals.json").exists()


# ---------------------------------------------------------------------------
# J. Thread safety
# ---------------------------------------------------------------------------

class TestThreadSafety:
    def test_concurrent_creates_all_succeed(self, tmp_path):
        store = _store(tmp_path)
        results: list[ApprovalRecord] = []
        errors: list[Exception] = []

        def worker():
            try:
                r = _create_rec(store, tenant="shared")
                results.append(r)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == []
        assert len(results) == 10
        # All approval_ids are unique
        ids = {r.approval_id for r in results}
        assert len(ids) == 10

    def test_concurrent_state_transitions_no_data_loss(self, tmp_path):
        store = _store(tmp_path)
        rec = _create_rec(store, tenant="shared2")

        # Only one submit should succeed; the others should raise
        successes = []
        failures = []

        def try_submit():
            try:
                store.submit_for_review(rec.approval_id, reviewer="검토자")
                successes.append(True)
            except ValueError:
                failures.append(True)

        # After 1 submit, remaining attempts from IN_REVIEW should fail
        try_submit()  # first succeeds
        threads = [threading.Thread(target=try_submit) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(successes) == 1
        final = store.get(rec.approval_id)
        assert final.status == "in_review"


# ---------------------------------------------------------------------------
# K. API endpoints — fixture + basic CRUD
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def client(tmp_path_factory):
    """TestClient with an isolated temp DATA_DIR (no users → auth middleware passes).

    Uses tmp_path_factory (module-scoped compatible) so the auth_middleware
    finds an empty users.json and allows unauthenticated requests through.
    Clears API key env vars so require_api_key is also a no-op.
    """
    import os
    tmp_dir = tmp_path_factory.mktemp("approval_workflow_data")
    _saved = {k: os.environ.pop(k, None)
              for k in (
                  "DECISIONDOC_API_KEY",
                  "DECISIONDOC_API_KEYS",
                  "DECISIONDOC_PROVIDER_GENERATION",
                  "DECISIONDOC_PROVIDER_ATTACHMENT",
                  "DECISIONDOC_PROVIDER_VISUAL",
              )}
    old_data_dir = os.environ.get("DATA_DIR")
    os.environ["DATA_DIR"] = str(tmp_dir)
    os.environ["DECISIONDOC_ENV"] = "dev"
    os.environ["DECISIONDOC_PROVIDER"] = "mock"
    os.environ["DECISIONDOC_PROVIDER_GENERATION"] = ""
    os.environ["DECISIONDOC_PROVIDER_ATTACHMENT"] = ""
    os.environ["DECISIONDOC_PROVIDER_VISUAL"] = ""
    _client = TestClient(create_app())
    yield _client
    # Restore env
    for k, v in _saved.items():
        if v is not None:
            os.environ[k] = v
    if old_data_dir is not None:
        os.environ["DATA_DIR"] = old_data_dir
    elif "DATA_DIR" in os.environ:
        del os.environ["DATA_DIR"]


HEADERS = {"X-API-KEY": "test-key"}


class TestApprovalApiCrud:
    def test_create_approval_returns_200(self, client):
        res = client.post("/approvals", json={
            "title": "API 테스트 문서", "drafter": "홍길동",
            "bundle_id": "business_plan_kr", "docs": DOCS
        }, headers=HEADERS)
        assert res.status_code == 200

    def test_create_approval_has_approval_id(self, client):
        res = client.post("/approvals", json={
            "title": "테스트", "drafter": "기안자", "docs": DOCS
        }, headers=HEADERS)
        data = res.json()
        assert "approval_id" in data
        assert data["status"] == "draft"

    def test_get_approval_returns_record(self, client):
        created = client.post("/approvals", json={
            "title": "조회 테스트", "drafter": "기안자", "docs": DOCS
        }, headers=HEADERS).json()
        aid = created["approval_id"]
        res = client.get(f"/approvals/{aid}", headers=HEADERS)
        assert res.status_code == 200
        assert res.json()["approval_id"] == aid

    def test_get_nonexistent_returns_404(self, client):
        res = client.get("/approvals/nonexistent-id", headers=HEADERS)
        assert res.status_code == 404

    def test_list_approvals_returns_list(self, client):
        res = client.get("/approvals", headers=HEADERS)
        assert res.status_code == 200
        assert "approvals" in res.json()

    def test_update_docs_endpoint(self, client):
        created = client.post("/approvals", json={
            "title": "업데이트 테스트", "drafter": "기안자", "docs": DOCS
        }, headers=HEADERS).json()
        aid = created["approval_id"]
        new_docs = [{"doc_type": "x", "markdown": "새 내용"}]
        res = client.put(f"/approvals/{aid}/docs", json={"username": "기안자", "docs": new_docs}, headers=HEADERS)
        assert res.status_code == 200
        assert json.loads(res.json()["current_docs"]) == new_docs


class TestApprovalApiActions:
    def _create(self, client) -> dict:
        return client.post("/approvals", json={
            "title": "액션 테스트", "drafter": "기안자", "docs": DOCS
        }, headers=HEADERS).json()

    def test_submit_for_review_endpoint(self, client):
        rec = self._create(client)
        res = client.post(f"/approvals/{rec['approval_id']}/submit",
                          json={"username": "검토자A", "reviewer": "검토자A"}, headers=HEADERS)
        assert res.status_code == 200
        assert res.json()["status"] == "in_review"

    def test_approve_review_endpoint(self, client):
        rec = self._create(client)
        aid = rec["approval_id"]
        client.post(f"/approvals/{aid}/submit", json={"username": "검토자A", "reviewer": "검토자A"}, headers=HEADERS)
        res = client.post(f"/approvals/{aid}/review/approve", json={"username": "검토자A"}, headers=HEADERS)
        assert res.status_code == 200
        assert res.json()["reviewer_approved"] is True

    def test_request_changes_endpoint(self, client):
        rec = self._create(client)
        aid = rec["approval_id"]
        client.post(f"/approvals/{aid}/submit", json={"username": "검토자A", "reviewer": "검토자A"}, headers=HEADERS)
        res = client.post(f"/approvals/{aid}/review/request-changes",
                          json={"username": "검토자A", "comment": "수정 요청"}, headers=HEADERS)
        assert res.status_code == 200
        assert res.json()["status"] == "changes_requested"

    def test_final_approve_endpoint_full_flow(self, client):
        rec = self._create(client)
        aid = rec["approval_id"]
        client.post(f"/approvals/{aid}/submit", json={"username": "검토자A", "reviewer": "검토자A"}, headers=HEADERS)
        client.post(f"/approvals/{aid}/review/approve", json={"username": "검토자A"}, headers=HEADERS)
        res = client.post(f"/approvals/{aid}/approve",
                          json={"username": "결재자B", "approver": "결재자B"}, headers=HEADERS)
        assert res.status_code == 200
        assert res.json()["status"] == "approved"

    def test_reject_endpoint(self, client):
        rec = self._create(client)
        aid = rec["approval_id"]
        client.post(f"/approvals/{aid}/submit", json={"username": "검토자A", "reviewer": "검토자A"}, headers=HEADERS)
        res = client.post(f"/approvals/{aid}/reject",
                          json={"username": "결재자B", "comment": "반려"}, headers=HEADERS)
        assert res.status_code == 200
        assert res.json()["status"] == "rejected"

    def test_invalid_transition_returns_400(self, client):
        """Approving without reviewer_approved should return 400."""
        rec = self._create(client)
        aid = rec["approval_id"]
        client.post(f"/approvals/{aid}/submit", json={"username": "검토자A", "reviewer": "검토자A"}, headers=HEADERS)
        # Attempt final approve without reviewer approving first
        res = client.post(f"/approvals/{aid}/approve",
                          json={"username": "결재자B"}, headers=HEADERS)
        assert res.status_code == 400

    def test_action_on_nonexistent_returns_404(self, client):
        res = client.post("/approvals/no-such-id/submit",
                          json={"username": "기안자", "reviewer": "검토자"}, headers=HEADERS)
        assert res.status_code == 404


# ---------------------------------------------------------------------------
# L. Download endpoint
# ---------------------------------------------------------------------------

class TestDownloadEndpoint:
    def _approved_id(self, client) -> str:
        rec = client.post("/approvals", json={
            "title": "다운로드 테스트", "drafter": "기안자", "docs": DOCS
        }, headers=HEADERS).json()
        aid = rec["approval_id"]
        client.post(f"/approvals/{aid}/submit", json={"username": "검토자A", "reviewer": "검토자A"}, headers=HEADERS)
        client.post(f"/approvals/{aid}/review/approve", json={"username": "검토자A"}, headers=HEADERS)
        client.post(f"/approvals/{aid}/approve", json={"username": "결재자B"}, headers=HEADERS)
        return aid

    def test_download_approved_docx(self, client):
        aid = self._approved_id(client)
        res = client.get(f"/approvals/{aid}/download/docx", headers=HEADERS)
        assert res.status_code == 200
        # DOCX MIME type is wordprocessingml; also check content-disposition contains .docx
        ct = res.headers.get("content-type", "")
        cd = res.headers.get("content-disposition", "")
        assert "wordprocessingml" in ct or ".docx" in cd

    def test_download_approved_hwpx(self, client):
        aid = self._approved_id(client)
        res = client.get(f"/approvals/{aid}/download/hwpx", headers=HEADERS)
        assert res.status_code == 200

    def test_download_draft_returns_400(self, client):
        """Download should fail if document is not approved."""
        rec = client.post("/approvals", json={
            "title": "미승인 문서", "drafter": "기안자", "docs": DOCS
        }, headers=HEADERS).json()
        aid = rec["approval_id"]
        res = client.get(f"/approvals/{aid}/download/docx", headers=HEADERS)
        assert res.status_code == 400

    def test_download_in_review_returns_400(self, client):
        rec = client.post("/approvals", json={
            "title": "검토중 문서", "drafter": "기안자", "docs": DOCS
        }, headers=HEADERS).json()
        aid = rec["approval_id"]
        client.post(f"/approvals/{aid}/submit", json={"username": "검토자A", "reviewer": "검토자A"}, headers=HEADERS)
        res = client.get(f"/approvals/{aid}/download/docx", headers=HEADERS)
        assert res.status_code == 400

    def test_download_nonexistent_returns_404(self, client):
        res = client.get("/approvals/no-such/download/docx", headers=HEADERS)
        assert res.status_code == 404


# ---------------------------------------------------------------------------
# M. List with status / role filters
# ---------------------------------------------------------------------------

class TestListFilters:
    def test_list_with_status_filter(self, client):
        # Create one and submit it; another stays draft
        r1 = client.post("/approvals", json={
            "title": "필터 테스트1", "drafter": "기안자", "docs": DOCS
        }, headers=HEADERS).json()
        client.post(f"/approvals/{r1['approval_id']}/submit",
                    json={"username": "검토자A", "reviewer": "검토자A"}, headers=HEADERS)
        client.post("/approvals", json={
            "title": "필터 테스트2", "drafter": "기안자", "docs": DOCS
        }, headers=HEADERS)

        res = client.get("/approvals?status=in_review", headers=HEADERS)
        assert res.status_code == 200
        in_review = res.json()["approvals"]
        assert all(a["status"] == "in_review" for a in in_review)

    def test_list_with_role_filter(self, client):
        r = client.post("/approvals", json={
            "title": "역할 테스트", "drafter": "특별기안자", "docs": DOCS
        }, headers=HEADERS).json()
        res = client.get("/approvals?username=특별기안자&role=drafter", headers=HEADERS)
        assert res.status_code == 200
        recs = res.json()["approvals"]
        assert any(a["drafter"] == "특별기안자" for a in recs)
