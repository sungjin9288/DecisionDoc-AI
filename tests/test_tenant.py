"""tests/test_tenant.py — Multi-tenant support regression tests.

커버 항목:
  1.  TenantStore.create_tenant 성공 + 중복 오류
  2.  TenantStore.get_tenant — 존재/미존재
  3.  TenantStore.list_tenants
  4.  TenantStore.update_tenant — display_name, allowed_bundles, is_active
  5.  TenantStore.deactivate_tenant — SYSTEM_TENANT_ID 비활성화 거부
  6.  TenantStore.ensure_system_tenant 멱등성
  7.  TenantStore.set_custom_hint / get_custom_hint / delete_custom_hint
  8.  migrate_legacy_data — 레거시 파일 복사 + 이미 존재 시 덮어쓰기 안 함
  9.  tenant_middleware — 헤더 없음 → system 테넌트
 10.  tenant_middleware — 유효한 X-Tenant-ID → 테넌트 해석
 11.  tenant_middleware — 알 수 없는 테넌트 → 403
 12.  tenant_middleware — 비활성 테넌트 → 403
 13.  GET /bundles — allowed_bundles 필터링
 14.  POST /generate — 허용되지 않은 번들 → 403
 15.  POST /admin/tenants — 테넌트 생성
 16.  GET /admin/tenants — 목록 반환
 17.  GET /admin/tenants/{id} — 단일 조회 / 미존재 → 404
 18.  PATCH /admin/tenants/{id} — 필드 업데이트
 19.  POST /admin/tenants/{id}/custom-hint — 힌트 설정
 20.  DELETE /admin/tenants/{id}/custom-hint/{bundle} — 힌트 삭제
 21.  GET /admin/tenants/{id}/stats — 통계 반환
 22.  _current_tenant_id 스레드-로컬 주입 (schema.py)
"""
from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest


# ─── helpers ──────────────────────────────────────────────────────────────────

_OPS_KEY = "test-tenant-ops-key"
_JWT_SECRET = "test-tenant-jwt-secret-key-32chars!!"


def _make_client(tmp_path: Path, monkeypatch):
    """Create a FastAPI TestClient with a temp DATA_DIR and mock provider."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DECISIONDOC_PROVIDER", "mock")
    monkeypatch.setenv("DECISIONDOC_ENV", "dev")
    monkeypatch.setenv("DECISIONDOC_SEARCH_ENABLED", "0")
    monkeypatch.setenv("DECISIONDOC_OPS_KEY", _OPS_KEY)
    monkeypatch.setenv("JWT_SECRET_KEY", _JWT_SECRET)
    monkeypatch.delenv("DECISIONDOC_API_KEY", raising=False)
    monkeypatch.delenv("DECISIONDOC_API_KEYS", raising=False)
    import app.main as main_module
    from fastapi.testclient import TestClient
    return TestClient(main_module.create_app())


def _ops_headers(extra: dict | None = None) -> dict:
    """Return headers that include the ops key."""
    h = {"X-DecisionDoc-Ops-Key": _OPS_KEY}
    if extra:
        h.update(extra)
    return h


def _register_and_login(client, username: str = "admin", password: str = "AdminPass1!") -> dict:
    client.post(
        "/auth/register",
        json={
            "username": username,
            "display_name": username.title(),
            "email": f"{username}@test.local",
            "password": password,
        },
    )
    response = client.post(
        "/auth/login",
        json={"username": username, "password": password},
    )
    return response.json()


# ─── 1-7: TenantStore unit tests ──────────────────────────────────────────────

def test_create_tenant_returns_tenant(tmp_path: Path) -> None:
    """create_tenant 성공 시 Tenant 반환."""
    from app.storage.tenant_store import TenantStore
    store = TenantStore(tmp_path)
    tenant = store.create_tenant("acme", "Acme Corp", allowed_bundles=["tech_decision"])
    assert tenant.tenant_id == "acme"
    assert tenant.display_name == "Acme Corp"
    assert tenant.allowed_bundles == ["tech_decision"]
    assert tenant.is_active is True


def test_create_tenant_duplicate_raises(tmp_path: Path) -> None:
    """중복 create_tenant → ValueError."""
    from app.storage.tenant_store import TenantStore
    store = TenantStore(tmp_path)
    store.create_tenant("alpha", "Alpha Team")
    with pytest.raises(ValueError, match="already exists"):
        store.create_tenant("alpha", "Alpha Team 2")


def test_get_tenant_missing_returns_none(tmp_path: Path) -> None:
    """존재하지 않는 tenant_id → None 반환."""
    from app.storage.tenant_store import TenantStore
    store = TenantStore(tmp_path)
    assert store.get_tenant("no-such-tenant") is None


def test_list_tenants(tmp_path: Path) -> None:
    """list_tenants는 생성된 모든 테넌트를 반환."""
    from app.storage.tenant_store import TenantStore
    store = TenantStore(tmp_path)
    store.create_tenant("t1", "Team One")
    store.create_tenant("t2", "Team Two")
    ids = {t.tenant_id for t in store.list_tenants()}
    assert {"t1", "t2"} == ids


def test_update_tenant_fields(tmp_path: Path) -> None:
    """update_tenant — display_name, allowed_bundles, is_active 변경."""
    from app.storage.tenant_store import TenantStore
    store = TenantStore(tmp_path)
    store.create_tenant("beta", "Beta Team")
    updated = store.update_tenant(
        "beta",
        display_name="Beta Corp",
        allowed_bundles=["meeting_minutes_kr"],
        is_active=True,
    )
    assert updated.display_name == "Beta Corp"
    assert updated.allowed_bundles == ["meeting_minutes_kr"]


def test_deactivate_tenant(tmp_path: Path) -> None:
    """deactivate_tenant — is_active=False."""
    from app.storage.tenant_store import TenantStore
    store = TenantStore(tmp_path)
    store.create_tenant("gamma", "Gamma")
    store.deactivate_tenant("gamma")
    tenant = store.get_tenant("gamma")
    assert tenant is not None
    assert tenant.is_active is False


def test_system_tenant_cannot_be_deactivated(tmp_path: Path) -> None:
    """SYSTEM_TENANT_ID는 비활성화 불가 → ValueError."""
    from app.storage.tenant_store import TenantStore
    from app.tenant import SYSTEM_TENANT_ID
    store = TenantStore(tmp_path)
    store.ensure_system_tenant()
    with pytest.raises(ValueError, match="cannot be deactivated"):
        store.deactivate_tenant(SYSTEM_TENANT_ID)


def test_ensure_system_tenant_idempotent(tmp_path: Path) -> None:
    """ensure_system_tenant 두 번 호출해도 하나만 생성."""
    from app.storage.tenant_store import TenantStore
    from app.tenant import SYSTEM_TENANT_ID
    store = TenantStore(tmp_path)
    t1 = store.ensure_system_tenant()
    t2 = store.ensure_system_tenant()
    assert t1.tenant_id == t2.tenant_id == SYSTEM_TENANT_ID
    assert len(store.list_tenants()) == 1


def test_custom_hint_crud(tmp_path: Path) -> None:
    """set_custom_hint / get_custom_hint / delete_custom_hint 라이프사이클."""
    from app.storage.tenant_store import TenantStore
    store = TenantStore(tmp_path)
    store.create_tenant("delta", "Delta")
    store.set_custom_hint("delta", "tech_decision", "구체적인 비용 분석을 포함하세요.")
    assert store.get_custom_hint("delta", "tech_decision") == "구체적인 비용 분석을 포함하세요."
    assert store.get_custom_hint("delta", "other_bundle") is None
    store.delete_custom_hint("delta", "tech_decision")
    assert store.get_custom_hint("delta", "tech_decision") is None


# ─── 8: migrate_legacy_data ────────────────────────────────────────────────────

def test_migrate_legacy_data_copies_files(tmp_path: Path) -> None:
    """migrate_legacy_data — 레거시 파일을 tenants/system/ 으로 복사."""
    from app.storage.tenant_store import migrate_legacy_data

    # 레거시 파일 생성
    legacy_feedback = tmp_path / "feedback.jsonl"
    legacy_feedback.write_text('{"id": "x"}\n', encoding="utf-8")
    legacy_overrides = tmp_path / "prompt_overrides.json"
    legacy_overrides.write_text('{}', encoding="utf-8")

    migrate_legacy_data(tmp_path)

    system_dir = tmp_path / "tenants" / "system"
    assert (system_dir / "feedback.jsonl").exists()
    assert (system_dir / "prompt_overrides.json").exists()


def test_migrate_legacy_data_no_overwrite(tmp_path: Path) -> None:
    """migrate_legacy_data — 대상 파일이 이미 존재하면 덮어쓰지 않음."""
    from app.storage.tenant_store import migrate_legacy_data

    system_dir = tmp_path / "tenants" / "system"
    system_dir.mkdir(parents=True)

    # 이미 존재하는 대상 파일 (다른 내용)
    existing_dst = system_dir / "feedback.jsonl"
    existing_dst.write_text('{"id": "existing"}\n', encoding="utf-8")

    # 레거시 파일 (다른 내용)
    (tmp_path / "feedback.jsonl").write_text('{"id": "legacy"}\n', encoding="utf-8")

    migrate_legacy_data(tmp_path)

    # 대상이 변경되지 않아야 함
    content = existing_dst.read_text(encoding="utf-8")
    assert "existing" in content


# ─── 9-12: Tenant middleware (HTTP) ───────────────────────────────────────────

def test_middleware_no_header_uses_system_tenant(tmp_path: Path, monkeypatch) -> None:
    """X-Tenant-ID 헤더 없음 → system 테넌트 사용 (200 응답)."""
    client = _make_client(tmp_path, monkeypatch)
    resp = client.get("/health")
    assert resp.status_code == 200


def test_middleware_valid_tenant_header_accepted(tmp_path: Path, monkeypatch) -> None:
    """유효한 X-Tenant-ID → 정상 응답."""
    client = _make_client(tmp_path, monkeypatch)
    # Create tenant via admin API first
    client.post(
        "/admin/tenants",
        json={"tenant_id": "valid-team", "display_name": "Valid Team"},
        headers=_ops_headers(),
    )
    resp = client.get("/health", headers={"X-Tenant-ID": "valid-team"})
    assert resp.status_code == 200


def test_middleware_unknown_tenant_returns_403(tmp_path: Path, monkeypatch) -> None:
    """알 수 없는 테넌트 → 403."""
    client = _make_client(tmp_path, monkeypatch)
    resp = client.get("/health", headers={"X-Tenant-ID": "ghost-tenant"})
    assert resp.status_code == 403


def test_middleware_inactive_tenant_returns_403(tmp_path: Path, monkeypatch) -> None:
    """비활성 테넌트 → 403."""
    client = _make_client(tmp_path, monkeypatch)
    client.post(
        "/admin/tenants",
        json={"tenant_id": "inactive-team", "display_name": "Inactive"},
        headers=_ops_headers(),
    )
    client.patch(
        "/admin/tenants/inactive-team",
        json={"is_active": False},
        headers=_ops_headers(),
    )
    resp = client.get("/health", headers={"X-Tenant-ID": "inactive-team"})
    assert resp.status_code == 403


# ─── 13-14: Bundle filtering + access enforcement ─────────────────────────────

def test_bundles_filtered_by_allowed_bundles(tmp_path: Path, monkeypatch) -> None:
    """GET /bundles — allowed_bundles 제한 시 필터링됨."""
    client = _make_client(tmp_path, monkeypatch)
    # Create a tenant that only allows 'tech_decision'
    client.post(
        "/admin/tenants",
        json={
            "tenant_id": "limited",
            "display_name": "Limited",
            "allowed_bundles": ["tech_decision"],
        },
        headers=_ops_headers(),
    )
    resp = client.get("/bundles", headers={"X-Tenant-ID": "limited"})
    assert resp.status_code == 200
    bundle_ids = [b["id"] for b in resp.json()]
    assert bundle_ids == ["tech_decision"]


def test_bundles_not_filtered_when_no_restrictions(tmp_path: Path, monkeypatch) -> None:
    """GET /bundles — allowed_bundles=[] (제한 없음) 시 전체 목록 반환."""
    client = _make_client(tmp_path, monkeypatch)
    client.post(
        "/admin/tenants",
        json={"tenant_id": "open-team", "display_name": "Open Team", "allowed_bundles": []},
        headers=_ops_headers(),
    )
    resp = client.get("/bundles", headers={"X-Tenant-ID": "open-team"})
    assert resp.status_code == 200
    assert len(resp.json()) > 1  # more than one bundle


def test_generate_blocked_for_disallowed_bundle(tmp_path: Path, monkeypatch) -> None:
    """POST /generate — 허용되지 않은 번들 → 403."""
    client = _make_client(tmp_path, monkeypatch)
    client.post(
        "/admin/tenants",
        json={
            "tenant_id": "restricted",
            "display_name": "Restricted",
            "allowed_bundles": ["meeting_minutes_kr"],
        },
        headers=_ops_headers(),
    )
    resp = client.post(
        "/generate",
        json={"title": "T", "goal": "G", "bundle_type": "tech_decision"},
        headers={"X-Tenant-ID": "restricted"},
    )
    assert resp.status_code == 403


# ─── 15-21: Admin API endpoints ───────────────────────────────────────────────

def test_admin_create_tenant(tmp_path: Path, monkeypatch) -> None:
    """POST /admin/tenants — 테넌트 생성."""
    client = _make_client(tmp_path, monkeypatch)
    resp = client.post(
        "/admin/tenants",
        json={"tenant_id": "new-corp", "display_name": "New Corp"},
        headers=_ops_headers(),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["tenant_id"] == "new-corp"
    assert data["display_name"] == "New Corp"
    assert data["is_active"] is True


def test_admin_create_tenant_with_admin_jwt(tmp_path: Path, monkeypatch) -> None:
    """POST /admin/tenants — admin JWT로도 생성 가능."""
    client = _make_client(tmp_path, monkeypatch)
    admin_login = _register_and_login(client)
    headers = {"Authorization": f"Bearer {admin_login['access_token']}"}

    resp = client.post(
        "/admin/tenants",
        json={"tenant_id": "jwt-corp", "display_name": "JWT Corp"},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["tenant_id"] == "jwt-corp"


def test_admin_create_tenant_duplicate_returns_409(tmp_path: Path, monkeypatch) -> None:
    """POST /admin/tenants 중복 → 409."""
    client = _make_client(tmp_path, monkeypatch)
    client.post("/admin/tenants", json={"tenant_id": "dup", "display_name": "Dup"}, headers=_ops_headers())
    resp = client.post("/admin/tenants", json={"tenant_id": "dup", "display_name": "Dup2"}, headers=_ops_headers())
    assert resp.status_code == 409


def test_admin_list_tenants(tmp_path: Path, monkeypatch) -> None:
    """GET /admin/tenants — 목록 반환 (시스템 테넌트 포함)."""
    client = _make_client(tmp_path, monkeypatch)
    client.post("/admin/tenants", json={"tenant_id": "t-list", "display_name": "T List"}, headers=_ops_headers())
    resp = client.get("/admin/tenants", headers=_ops_headers())
    assert resp.status_code == 200
    data = resp.json()
    tenant_list = data["tenants"] if isinstance(data, dict) and "tenants" in data else data
    ids = [t["tenant_id"] for t in tenant_list]
    assert "t-list" in ids
    assert "system" in ids  # ensure_system_tenant() called at startup


def test_admin_get_tenant(tmp_path: Path, monkeypatch) -> None:
    """GET /admin/tenants/{id} — 단일 조회."""
    client = _make_client(tmp_path, monkeypatch)
    client.post("/admin/tenants", json={"tenant_id": "t-get", "display_name": "T Get"}, headers=_ops_headers())
    resp = client.get("/admin/tenants/t-get", headers=_ops_headers())
    assert resp.status_code == 200
    assert resp.json()["tenant_id"] == "t-get"


def test_admin_get_tenant_not_found(tmp_path: Path, monkeypatch) -> None:
    """GET /admin/tenants/{id} — 미존재 → 404."""
    client = _make_client(tmp_path, monkeypatch)
    resp = client.get("/admin/tenants/does-not-exist", headers=_ops_headers())
    assert resp.status_code == 404


def test_admin_update_tenant(tmp_path: Path, monkeypatch) -> None:
    """PATCH /admin/tenants/{id} — 이름 + allowed_bundles 업데이트."""
    client = _make_client(tmp_path, monkeypatch)
    client.post("/admin/tenants", json={"tenant_id": "t-upd", "display_name": "Old Name"}, headers=_ops_headers())
    resp = client.patch(
        "/admin/tenants/t-upd",
        json={"display_name": "New Name", "allowed_bundles": ["tech_decision"]},
        headers=_ops_headers(),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["display_name"] == "New Name"
    assert data["allowed_bundles"] == ["tech_decision"]


def test_admin_set_and_delete_custom_hint(tmp_path: Path, monkeypatch) -> None:
    """POST + DELETE /admin/tenants/{id}/custom-hint lifecycle."""
    client = _make_client(tmp_path, monkeypatch)
    client.post("/admin/tenants", json={"tenant_id": "t-hint", "display_name": "Hint"}, headers=_ops_headers())

    # Set hint
    resp = client.post(
        "/admin/tenants/t-hint/custom-hint",
        json={"bundle_id": "tech_decision", "hint": "비용 절감에 집중하세요."},
        headers=_ops_headers(),
    )
    assert resp.status_code == 200
    assert resp.json()["hint"] == "비용 절감에 집중하세요."

    # Delete hint
    del_resp = client.delete("/admin/tenants/t-hint/custom-hint/tech_decision", headers=_ops_headers())
    assert del_resp.status_code == 200
    assert del_resp.json()["deleted"] is True


def test_admin_tenant_stats(tmp_path: Path, monkeypatch) -> None:
    """GET /admin/tenants/{id}/stats — 통계 반환."""
    client = _make_client(tmp_path, monkeypatch)
    client.post("/admin/tenants", json={"tenant_id": "t-stats", "display_name": "Stats"}, headers=_ops_headers())
    resp = client.get("/admin/tenants/t-stats/stats", headers=_ops_headers())
    assert resp.status_code == 200
    data = resp.json()
    assert "tenant" in data
    assert "eval" in data
    assert "feedback_count" in data
    assert data["tenant"]["tenant_id"] == "t-stats"


def test_admin_tenant_stats_not_found(tmp_path: Path, monkeypatch) -> None:
    """GET /admin/tenants/{id}/stats — 미존재 테넌트 → 404."""
    client = _make_client(tmp_path, monkeypatch)
    resp = client.get("/admin/tenants/ghost/stats", headers=_ops_headers())
    assert resp.status_code == 404


def test_admin_tenant_procurement_quality_summary(tmp_path: Path, monkeypatch) -> None:
    """GET /admin/tenants/{id}/procurement-quality-summary — procurement decision/handoff 통계 반환."""
    from app.schemas import (
        NormalizedProcurementOpportunity,
        ProcurementChecklistItem,
        ProcurementDecisionUpsert,
        ProcurementHardFilterResult,
        ProcurementRecommendation,
    )
    from app.storage.audit_store import AuditLog, AuditStore

    client = _make_client(tmp_path, monkeypatch)
    client.post(
        "/admin/tenants",
        json={"tenant_id": "t-proc", "display_name": "Procurement Team"},
        headers=_ops_headers(),
    )

    project_store = client.app.state.project_store
    procurement_store = client.app.state.procurement_store
    approval_store = client.app.state.approval_store

    project_a = project_store.create("t-proc", "Procurement A")
    project_b = project_store.create("t-proc", "Procurement B")
    project_c = project_store.create("t-proc", "Procurement C")

    procurement_store.upsert(
        ProcurementDecisionUpsert(
            project_id=project_a.project_id,
            tenant_id="t-proc",
            opportunity=NormalizedProcurementOpportunity(
                source_kind="g2b",
                source_id="PROC-001",
                title="AI 플랫폼 구축",
                issuer="조달청",
            ),
            hard_filters=[
                ProcurementHardFilterResult(
                    code="eligible",
                    label="참여 자격",
                    status="pass",
                    blocking=False,
                )
            ],
            soft_fit_score=82.0,
            soft_fit_status="scored",
            checklist_items=[
                ProcurementChecklistItem(
                    category="delivery",
                    title="투입 인력 확정",
                    status="action_needed",
                    severity="medium",
                )
            ],
            recommendation=ProcurementRecommendation(value="GO", summary="참여 가능"),
        )
    )
    procurement_store.upsert(
        ProcurementDecisionUpsert(
            project_id=project_b.project_id,
            tenant_id="t-proc",
            opportunity=NormalizedProcurementOpportunity(
                source_kind="g2b",
                source_id="PROC-002",
                title="보안 관제 고도화",
                issuer="행정기관",
            ),
            hard_filters=[
                ProcurementHardFilterResult(
                    code="certificate_missing",
                    label="필수 인증",
                    status="fail",
                    blocking=True,
                    reason="필수 인증 미보유",
                )
            ],
            soft_fit_score=41.0,
            soft_fit_status="scored",
            missing_data=["상세 인력 투입 계획"],
            checklist_items=[
                ProcurementChecklistItem(
                    category="certification",
                    title="필수 인증 확보",
                    status="blocked",
                    severity="critical",
                ),
                ProcurementChecklistItem(
                    category="staffing",
                    title="보안 인력 검증",
                    status="action_needed",
                    severity="high",
                ),
            ],
            recommendation=ProcurementRecommendation(value="NO_GO", summary="현 상태 참여 곤란"),
            notes=(
                "[override_reason ts=2026-03-31T00:00:00+00:00 actor=bd-lead]\n"
                "전략 고객 유지 차원에서 예외적으로 proposal 검토 진행\n"
                "[/override_reason]"
            ),
        )
    )
    procurement_store.upsert(
        ProcurementDecisionUpsert(
            project_id=project_c.project_id,
            tenant_id="t-proc",
            opportunity=NormalizedProcurementOpportunity(
                source_kind="g2b",
                source_id="PROC-003",
                title="관제 운영 전환",
                issuer="지자체",
            ),
            hard_filters=[
                ProcurementHardFilterResult(
                    code="reference_gap",
                    label="유사 레퍼런스",
                    status="fail",
                    blocking=True,
                    reason="최근 3년 내 유사 수행 실적 부족",
                )
            ],
            soft_fit_score=48.0,
            soft_fit_status="scored",
            missing_data=["운영 이관 상세 계획"],
            checklist_items=[
                ProcurementChecklistItem(
                    category="references",
                    title="유사 실적 확보",
                    status="blocked",
                    severity="high",
                )
            ],
            recommendation=ProcurementRecommendation(value="NO_GO", summary="override 저장 후 retry 대기"),
            notes=(
                "[override_reason ts=2026-03-31T00:10:00+00:00 actor=ops-lead]\n"
                "기존 운영 고객 continuity 대응을 위해 예외 검토를 유지\n"
                "[/override_reason]"
            ),
        )
    )

    project_store.add_document(
        project_a.project_id,
        request_id="req-bid-decision",
        bundle_id="bid_decision_kr",
        title="입찰 참여 판단 메모",
        docs=[{"markdown": "# decision"}],
        tenant_id="t-proc",
    )
    project_store.add_document(
        project_a.project_id,
        request_id="req-proposal",
        bundle_id="proposal_kr",
        title="제안서 초안",
        docs=[{"markdown": "# proposal"}],
        tenant_id="t-proc",
    )
    project_store.add_document(
        project_a.project_id,
        request_id="req-unrelated",
        bundle_id="meeting_minutes_kr",
        title="무관 문서",
        docs=[{"markdown": "# note"}],
        tenant_id="t-proc",
    )
    project_store.add_document(
        project_b.project_id,
        request_id="req-no-go-proposal",
        bundle_id="proposal_kr",
        title="진행된 NO_GO 제안서",
        docs=[{"markdown": "# no go proposal"}],
        tenant_id="t-proc",
    )
    project_store.add_document(
        project_c.project_id,
        request_id="req-no-go-proposal-2",
        bundle_id="proposal_kr",
        title="retry 대기 제안서",
        docs=[{"markdown": "# retry waiting proposal"}],
        tenant_id="t-proc",
    )

    approval = approval_store.create(
        "t-proc",
        request_id="req-bid-decision",
        bundle_id="bid_decision_kr",
        title="입찰 참여 판단 메모",
        drafter="drafter",
        docs=[{"markdown": "# decision"}],
    )
    approval_store.submit_for_review(approval.approval_id, reviewer="reviewer", tenant_id="t-proc")
    approval_store.approve_review(approval.approval_id, author="reviewer", tenant_id="t-proc")
    approval = approval_store.approve_final(approval.approval_id, author="approver", tenant_id="t-proc")
    project_store.update_document_approval(
        project_a.project_id,
        "req-bid-decision",
        approval.approval_id,
        approval.status,
        tenant_id="t-proc",
    )

    audit_store = AuditStore("t-proc")

    def _append_audit(
        action: str,
        resource_type: str,
        resource_id: str,
        *,
        result: str = "success",
        detail: dict | None = None,
        timestamp: str | None = None,
    ) -> None:
        audit_store.append(
            AuditLog(
                log_id=str(uuid.uuid4()),
                tenant_id="t-proc",
                timestamp=timestamp or datetime.now(timezone.utc).isoformat(timespec="microseconds"),
                user_id="u-admin",
                username="admin",
                user_role="admin",
                ip_address="127.0.0.1",
                user_agent="pytest",
                action=action,
                resource_type=resource_type,
                resource_id=resource_id,
                resource_name="",
                result=result,
                detail=detail or {},
                session_id="sess-proc",
            )
        )

    _append_audit("procurement.import", "procurement", project_a.project_id, timestamp="2026-03-31T00:01:00+00:00")
    _append_audit("procurement.recommend", "procurement", project_b.project_id, timestamp="2026-03-31T00:02:00+00:00")
    _append_audit(
        "procurement.downstream_blocked",
        "procurement",
        project_b.project_id,
        result="failure",
        detail={"bundle_type": "proposal_kr", "error_code": "procurement_override_reason_required"},
        timestamp="2026-03-31T00:03:00+00:00",
    )
    _append_audit(
        "procurement.downstream_resolved",
        "procurement",
        project_b.project_id,
        detail={"bundle_type": "proposal_kr", "recommendation": "NO_GO"},
        timestamp="2026-03-31T00:04:00+00:00",
    )
    _append_audit(
        "procurement.downstream_blocked",
        "procurement",
        project_c.project_id,
        result="failure",
        detail={"bundle_type": "proposal_kr", "error_code": "procurement_override_reason_required"},
        timestamp="2026-03-31T00:05:00+00:00",
    )
    _append_audit("approval.approve", "approval", approval.approval_id, timestamp="2026-03-31T00:06:00+00:00")
    for offset in range(10):
        _append_audit(
            "procurement.evaluate",
            "procurement",
            project_b.project_id if offset % 2 == 0 else project_c.project_id,
            timestamp=f"2026-03-31T00:{10 + offset:02d}:00+00:00",
        )

    resp = client.get(
        "/admin/tenants/t-proc/procurement-quality-summary",
        headers=_ops_headers(),
    )
    assert resp.status_code == 200

    data = resp.json()
    summary = data["procurement"]

    assert data["tenant"]["tenant_id"] == "t-proc"
    assert summary["decision"]["total_records"] == 3
    assert summary["decision"]["projects_with_procurement_state"] == 3
    assert summary["decision"]["recommendation_counts"]["GO"] == 1
    assert summary["decision"]["recommendation_counts"]["NO_GO"] == 2
    assert summary["decision"]["score_status_counts"]["scored"] == 3
    assert summary["decision"]["avg_soft_fit_score"] == 57.0
    assert summary["decision"]["records_with_missing_data"] == 2
    assert summary["decision"]["records_with_blocking_failures"] == 2
    assert summary["decision"]["blocking_hard_filter_counts"]["certificate_missing"] == 1
    assert summary["decision"]["blocking_hard_filter_counts"]["reference_gap"] == 1
    assert summary["decision"]["action_needed_total"] == 4
    assert summary["handoff"]["documents_total"] == 4
    assert summary["handoff"]["document_counts"]["bid_decision_kr"] == 1
    assert summary["handoff"]["document_counts"]["proposal_kr"] == 3
    assert summary["handoff"]["documents_with_approval_link"] == 1
    assert summary["handoff"]["project_document_status_counts"]["approved"] == 1
    assert summary["handoff"]["approval_status_counts"]["approved"] == 1
    assert summary["handoff"]["remediation_queue_count"] == 0
    assert summary["handoff"]["remediation_queue_status_counts"] == {}
    assert summary["handoff"]["remediation_queue"] == []
    assert summary["outcomes"]["projects_with_bid_decision_doc"] == 1
    assert summary["outcomes"]["projects_with_downstream_handoff"] == 3
    assert summary["outcomes"]["recommendation_followthrough"]["GO"]["with_downstream"] == 1
    assert summary["outcomes"]["recommendation_followthrough"]["NO_GO"]["with_downstream"] == 2
    assert summary["outcomes"]["override_candidate_count"] == 2
    assert summary["outcomes"]["visible_override_candidate_count"] == 2
    assert summary["outcomes"]["override_candidates_needing_followup"] == 1
    assert summary["outcomes"]["override_candidate_status_counts"]["ready_to_retry"] == 1
    assert summary["outcomes"]["override_candidate_status_counts"]["resolved"] == 1
    assert summary["outcomes"]["oldest_unresolved_followup"]["project_id"] == project_c.project_id
    assert summary["outcomes"]["oldest_unresolved_followup"]["recommendation"] == "NO_GO"
    assert summary["outcomes"]["oldest_unresolved_followup"]["followup_reference_kind"] == "override_saved"
    assert summary["outcomes"]["oldest_unresolved_followup"]["followup_updated_at"] == "2026-03-31T00:10:00+00:00"
    assert summary["outcomes"]["oldest_unresolved_followup"]["latest_blocked_bundle_type"] == "proposal_kr"
    assert summary["outcomes"]["override_candidates"][0]["project_id"] == project_c.project_id
    assert summary["outcomes"]["override_candidates"][0]["remediation_status"] == "ready_to_retry"
    assert summary["outcomes"]["override_candidates"][0]["latest_blocked_bundle_type"] == "proposal_kr"
    assert summary["outcomes"]["override_candidates"][0]["followup_reference_kind"] == "override_saved"
    assert summary["outcomes"]["override_candidates"][0]["followup_updated_at"] == "2026-03-31T00:10:00+00:00"
    assert summary["outcomes"]["override_candidates"][0]["latest_override_reason"]["actor"] == "ops-lead"
    assert summary["outcomes"]["override_candidates"][1]["project_id"] == project_b.project_id
    assert summary["outcomes"]["override_candidates"][1]["remediation_status"] == "resolved"
    assert summary["outcomes"]["override_candidates"][1]["downstream_bundles"] == ["proposal_kr"]
    assert summary["outcomes"]["override_candidates"][1]["blocking_hard_filter_codes"] == ["certificate_missing"]
    assert summary["outcomes"]["override_candidates"][1]["missing_data_count"] == 1
    assert summary["outcomes"]["override_candidates"][1]["action_needed_count"] == 2
    assert summary["outcomes"]["override_candidates"][1]["followup_reference_kind"] == "resolved"
    assert summary["outcomes"]["override_candidates"][1]["followup_updated_at"] == "2026-03-31T00:04:00+00:00"
    assert summary["outcomes"]["override_candidates"][1]["latest_activity"] == [
        "procurement.evaluate",
        "procurement.evaluate",
        "procurement.evaluate",
    ]
    assert summary["outcomes"]["override_candidates"][1]["latest_override_reason"]["actor"] == "bd-lead"
    assert summary["outcomes"]["override_candidates"][1]["latest_override_reason"]["reason"] == "전략 고객 유지 차원에서 예외적으로 proposal 검토 진행"
    assert summary["activity"]["action_counts"]["procurement.import"] == 1
    assert summary["activity"]["action_counts"]["procurement.downstream_blocked"] == 2
    assert summary["activity"]["action_counts"]["procurement.downstream_resolved"] == 1
    assert summary["activity"]["action_counts"]["procurement.evaluate"] == 10
    assert summary["activity"]["action_counts"]["procurement.recommend"] == 1
    assert summary["activity"]["action_counts"]["approval.approve"] == 1
    assert summary["activity"]["scope_recent_event_count"] == 16
    assert summary["activity"]["scope_action_counts"]["procurement.evaluate"] == 10
    assert summary["activity"]["scope_action_counts"]["procurement.downstream_blocked"] == 2
    assert summary["activity"]["scope_action_counts"]["procurement.downstream_resolved"] == 1
    assert summary["activity"]["visible_recent_event_count"] == 10
    assert len(summary["activity"]["recent_events"]) == 10
    recent_actions = [event["action"] for event in summary["activity"]["recent_events"]]
    assert set(recent_actions) == {"procurement.evaluate"}

    login = _register_and_login(client)
    auth_headers = {"Authorization": f"Bearer {login['access_token']}"}
    browser_resp = client.get(
        "/admin/locations/t-proc/procurement-quality-summary",
        headers=auth_headers,
    )
    assert browser_resp.status_code == 200
    browser_data = browser_resp.json()
    assert browser_data["tenant"]["tenant_id"] == "t-proc"
    assert browser_data["procurement"] == summary

    unresolved_only_resp = client.get(
        "/admin/locations/t-proc/procurement-quality-summary?candidate_scope=unresolved_only",
        headers=auth_headers,
    )
    assert unresolved_only_resp.status_code == 200
    unresolved_only_summary = unresolved_only_resp.json()["procurement"]
    unresolved_only_candidates = unresolved_only_summary["outcomes"]["override_candidates"]
    assert unresolved_only_summary["outcomes"]["override_candidate_scope"] == "unresolved_only"
    assert unresolved_only_summary["outcomes"]["override_candidate_count"] == 2
    assert unresolved_only_summary["outcomes"]["visible_override_candidate_count"] == 1
    assert unresolved_only_summary["outcomes"]["override_candidates_needing_followup"] == 1
    assert unresolved_only_summary["outcomes"]["scope_override_candidate_status_counts"] == {
        "ready_to_retry": 1
    }
    assert [candidate["project_id"] for candidate in unresolved_only_candidates] == [project_c.project_id]
    assert unresolved_only_summary["outcomes"]["oldest_unresolved_followup"]["project_id"] == project_c.project_id
    assert unresolved_only_summary["activity"]["visible_recent_event_count"] == len(
        unresolved_only_summary["activity"]["recent_events"]
    )
    assert unresolved_only_summary["activity"]["scope_recent_event_count"] == 6
    assert unresolved_only_summary["activity"]["scope_action_counts"] == {
        "procurement.evaluate": 5,
        "procurement.downstream_blocked": 1,
    }
    assert {
        str(event.get("linked_project_id", ""))
        for event in unresolved_only_summary["activity"]["recent_events"]
        if str(event.get("linked_project_id", "")).strip()
    } == {project_c.project_id}

    resolved_only_resp = client.get(
        "/admin/locations/t-proc/procurement-quality-summary?candidate_scope=resolved_only",
        headers=auth_headers,
    )
    assert resolved_only_resp.status_code == 200
    resolved_only_summary = resolved_only_resp.json()["procurement"]
    resolved_only_candidates = resolved_only_summary["outcomes"]["override_candidates"]
    assert resolved_only_summary["outcomes"]["override_candidate_scope"] == "resolved_only"
    assert resolved_only_summary["outcomes"]["override_candidate_count"] == 2
    assert resolved_only_summary["outcomes"]["visible_override_candidate_count"] == 1
    assert resolved_only_summary["outcomes"]["scope_override_candidate_status_counts"] == {
        "resolved": 1
    }
    assert [candidate["project_id"] for candidate in resolved_only_candidates] == [project_b.project_id]
    assert resolved_only_summary["activity"]["visible_recent_event_count"] == len(
        resolved_only_summary["activity"]["recent_events"]
    )
    assert resolved_only_summary["activity"]["scope_recent_event_count"] == 8
    assert resolved_only_summary["activity"]["scope_action_counts"]["procurement.evaluate"] == 5
    assert resolved_only_summary["activity"]["scope_action_counts"]["procurement.downstream_blocked"] == 1
    assert resolved_only_summary["activity"]["scope_action_counts"]["procurement.downstream_resolved"] == 1
    assert resolved_only_summary["activity"]["scope_action_counts"]["procurement.recommend"] == 1
    assert {
        str(event.get("linked_project_id", ""))
        for event in resolved_only_summary["activity"]["recent_events"]
        if str(event.get("linked_project_id", "")).strip()
    } == {project_b.project_id}

    focus_unresolved_resp = client.get(
        f"/admin/locations/t-proc/procurement-quality-summary?candidate_scope=unresolved_only&focus_project_id={project_b.project_id}",
        headers=auth_headers,
    )
    assert focus_unresolved_resp.status_code == 200
    focus_unresolved_summary = focus_unresolved_resp.json()["procurement"]
    focus_unresolved_project = focus_unresolved_summary["focused_project"]
    assert focus_unresolved_project["project_id"] == project_b.project_id
    assert focus_unresolved_project["visible_in_override_candidates"] is False
    assert focus_unresolved_summary["outcomes"]["visible_override_candidate_count"] == 1
    assert focus_unresolved_summary["activity"]["visible_recent_event_count"] == len(
        focus_unresolved_summary["activity"]["recent_events"]
    )
    assert any(
        event["linked_project_id"] == project_b.project_id
        for event in focus_unresolved_summary["activity"]["recent_events"]
    )

    assert all(
        event["linked_project_id"] != project_a.project_id
        for event in summary["activity"]["recent_events"]
    )

    focus_browser_resp = client.get(
        f"/admin/locations/t-proc/procurement-quality-summary?focus_project_id={project_a.project_id}",
        headers=auth_headers,
    )
    assert focus_browser_resp.status_code == 200
    focus_browser_data = focus_browser_resp.json()
    focus_recent_events = focus_browser_data["procurement"]["activity"]["recent_events"]
    focused_project = focus_browser_data["procurement"]["focused_project"]
    assert focused_project["project_id"] == project_a.project_id
    assert focused_project["project_name"] == "Procurement A"
    assert focused_project["recommendation"] == "GO"
    assert focused_project["visible_in_override_candidates"] is False
    assert len(focus_recent_events) == 10
    assert any(
        event["linked_project_id"] == project_a.project_id
        and event["action"] in {"procurement.import", "approval.approve"}
        for event in focus_recent_events
    )


def test_admin_location_procurement_quality_summary_includes_remediation_link_copy_activity(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from app.schemas import (
        NormalizedProcurementOpportunity,
        ProcurementDecisionUpsert,
        ProcurementRecommendation,
    )
    from app.storage.audit_store import AuditLog, AuditStore

    client = _make_client(tmp_path, monkeypatch)
    client.post(
        "/admin/tenants",
        json={"tenant_id": "t-proc-share", "display_name": "Procurement Share Team"},
        headers=_ops_headers(),
    )

    project_store = client.app.state.project_store
    procurement_store = client.app.state.procurement_store
    project = project_store.create("t-proc-share", "Procurement Share Project")
    procurement_store.upsert(
        ProcurementDecisionUpsert(
            project_id=project.project_id,
            tenant_id="t-proc-share",
            opportunity=NormalizedProcurementOpportunity(
                source_kind="g2b",
                source_id="PROC-SHARE-001",
                title="Procurement Share Project",
                issuer="조달청",
            ),
            recommendation=ProcurementRecommendation(
                value="NO_GO",
                summary="remediation link 공유 activity 확인",
            ),
        )
    )
    project_store.add_document(
        project.project_id,
        request_id="req-share-proposal",
        bundle_id="proposal_kr",
        title="공유 대상 제안서",
        docs=[{"markdown": "# proposal"}],
        tenant_id="t-proc-share",
    )

    audit_store = AuditStore("t-proc-share")
    audit_store.append(
        AuditLog(
            log_id=str(uuid.uuid4()),
            tenant_id="t-proc-share",
            timestamp="2026-03-31T00:20:00+00:00",
            user_id="u-admin",
            username="admin",
            user_role="admin",
            ip_address="127.0.0.1",
            user_agent="pytest",
            action="procurement.remediation_link_copied",
            resource_type="procurement",
            resource_id=project.project_id,
            resource_name="",
            result="success",
            detail={
                "project_id": project.project_id,
                "bundle_type": "proposal_kr",
                "recommendation": "NO_GO",
                "procurement_operation": "location_summary",
                "procurement_context_kind": "blocked_event",
                "error_code": "procurement_override_reason_required",
            },
            session_id="sess-proc-share",
        )
    )

    login = _register_and_login(client)
    auth_headers = {"Authorization": f"Bearer {login['access_token']}"}
    resp = client.get(
        "/admin/locations/t-proc-share/procurement-quality-summary?activity_actions=procurement.remediation_link_copied",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    summary = resp.json()["procurement"]

    assert summary["activity"]["action_counts"]["procurement.remediation_link_copied"] == 1
    assert summary["activity"]["scope_action_counts"]["procurement.remediation_link_copied"] == 1
    assert summary["activity"]["visible_action_counts"]["procurement.remediation_link_copied"] == 1
    assert summary["activity"]["activity_action_filters"] == ["procurement.remediation_link_copied"]
    assert summary["activity"]["visible_recent_event_count"] == 1
    assert [event["action"] for event in summary["activity"]["recent_events"]] == [
        "procurement.remediation_link_copied"
    ]
    recent_event = summary["activity"]["recent_events"][0]
    assert recent_event["linked_project_id"] == project.project_id
    assert recent_event["bundle_type"] == "proposal_kr"
    assert recent_event["recommendation"] == "NO_GO"
    assert recent_event["procurement_operation"] == "location_summary"
    assert recent_event["procurement_context_kind"] == "blocked_event"
    assert recent_event["error_code"] == "procurement_override_reason_required"


def test_admin_location_procurement_quality_summary_includes_remediation_link_open_activity(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from app.schemas import (
        NormalizedProcurementOpportunity,
        ProcurementDecisionUpsert,
        ProcurementRecommendation,
    )
    from app.storage.audit_store import AuditLog, AuditStore
    from app.storage.share_store import ShareStore

    client = _make_client(tmp_path, monkeypatch)
    client.post(
        "/admin/tenants",
        json={"tenant_id": "t-proc-open", "display_name": "Procurement Open Team"},
        headers=_ops_headers(),
    )

    project_store = client.app.state.project_store
    procurement_store = client.app.state.procurement_store
    project = project_store.create("t-proc-open", "Procurement Open Project")
    procurement_store.upsert(
        ProcurementDecisionUpsert(
            project_id=project.project_id,
            tenant_id="t-proc-open",
            opportunity=NormalizedProcurementOpportunity(
                source_kind="g2b",
                source_id="PROC-OPEN-001",
                title="Procurement Open Project",
                issuer="조달청",
            ),
            recommendation=ProcurementRecommendation(
                value="NO_GO",
                summary="remediation link 열람 activity 확인",
            ),
        )
    )
    project_store.add_document(
        project.project_id,
        request_id="req-open-proposal",
        bundle_id="proposal_kr",
        title="열람 대상 제안서",
        docs=[{"markdown": "# proposal"}],
        tenant_id="t-proc-open",
    )

    audit_store = AuditStore("t-proc-open")
    audit_store.append(
        AuditLog(
            log_id=str(uuid.uuid4()),
            tenant_id="t-proc-open",
            timestamp="2026-03-31T00:30:00+00:00",
            user_id="u-admin",
            username="admin",
            user_role="admin",
            ip_address="127.0.0.1",
            user_agent="pytest",
            action="procurement.remediation_link_opened",
            resource_type="procurement",
            resource_id=project.project_id,
            resource_name="",
            result="success",
            detail={
                "project_id": project.project_id,
                "bundle_type": "proposal_kr",
                "recommendation": "NO_GO",
                "procurement_operation": "url_restore",
                "procurement_context_kind": "blocked_event",
                "error_code": "procurement_override_reason_required",
            },
            session_id="sess-proc-open",
        )
    )

    login = _register_and_login(client)
    auth_headers = {"Authorization": f"Bearer {login['access_token']}"}
    resp = client.get(
        "/admin/locations/t-proc-open/procurement-quality-summary?activity_actions=procurement.remediation_link_opened",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    summary = resp.json()["procurement"]

    assert summary["activity"]["action_counts"]["procurement.remediation_link_opened"] == 1
    assert summary["activity"]["scope_action_counts"]["procurement.remediation_link_opened"] == 1
    assert summary["activity"]["visible_action_counts"]["procurement.remediation_link_opened"] == 1
    assert summary["activity"]["activity_action_filters"] == ["procurement.remediation_link_opened"]
    assert summary["activity"]["visible_recent_event_count"] == 1
    assert [event["action"] for event in summary["activity"]["recent_events"]] == [
        "procurement.remediation_link_opened"
    ]
    recent_event = summary["activity"]["recent_events"][0]
    assert recent_event["linked_project_id"] == project.project_id
    assert recent_event["bundle_type"] == "proposal_kr"
    assert recent_event["recommendation"] == "NO_GO"
    assert recent_event["procurement_operation"] == "url_restore"
    assert recent_event["procurement_context_kind"] == "blocked_event"
    assert recent_event["error_code"] == "procurement_override_reason_required"


def test_admin_location_procurement_quality_summary_includes_stale_share_create_activity(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from app.schemas import (
        NormalizedProcurementOpportunity,
        ProcurementDecisionUpsert,
        ProcurementRecommendation,
    )
    from app.storage.audit_store import AuditLog, AuditStore
    from app.storage.share_store import ShareStore

    client = _make_client(tmp_path, monkeypatch)
    client.post(
        "/admin/tenants",
        json={"tenant_id": "t-proc-stale-share", "display_name": "Procurement Stale Share Team"},
        headers=_ops_headers(),
    )

    project_store = client.app.state.project_store
    procurement_store = client.app.state.procurement_store
    project = project_store.create("t-proc-stale-share", "Procurement Stale Share Project")
    procurement_store.upsert(
        ProcurementDecisionUpsert(
            project_id=project.project_id,
            tenant_id="t-proc-stale-share",
            opportunity=NormalizedProcurementOpportunity(
                source_kind="g2b",
                source_id="PROC-STALE-SHARE-001",
                title="Procurement Stale Share Project",
                issuer="조달청",
            ),
            recommendation=ProcurementRecommendation(
                value="NO_GO",
                summary="stale council 공유 activity 확인",
            ),
        )
    )
    share_store = ShareStore(
        "t-proc-stale-share",
        data_dir=client.app.state.data_dir,
        backend=client.app.state.state_backend,
    )
    share_0 = share_store.create(
        tenant_id="t-proc-stale-share",
        request_id="req-stale-share-0",
        title="Stale share 0",
        created_by="analyst",
        bundle_id="bid_decision_kr",
        decision_council_document_status="stale_procurement",
        decision_council_document_status_tone="danger",
        decision_council_document_status_copy="현재 procurement 대비 이전 council 기준",
        decision_council_document_status_summary="현재 procurement recommendation 또는 checklist가 바뀌어 외부 공유 전 재확인이 필요합니다.",
    )
    share_1 = share_store.create(
        tenant_id="t-proc-stale-share",
        request_id="req-stale-share-1",
        title="Stale share 1",
        created_by="admin",
        bundle_id="bid_decision_kr",
        decision_council_document_status="stale_procurement",
        decision_council_document_status_tone="danger",
        decision_council_document_status_copy="현재 procurement 대비 이전 council 기준",
        decision_council_document_status_summary="현재 procurement recommendation 또는 checklist가 바뀌어 외부 공유 전 재확인이 필요합니다.",
    )
    share_2 = share_store.create(
        tenant_id="t-proc-stale-share",
        request_id="req-stale-share-2",
        title="Stale share 2",
        created_by="reviewer",
        bundle_id="bid_decision_kr",
        decision_council_document_status="stale_revision",
        decision_council_document_status_tone="warning",
        decision_council_document_status_copy="이전 council revision (r1)",
        decision_council_document_status_summary="latest council revision 기준으로 다시 생성한 뒤 외부 공유하는 편이 안전합니다.",
    )
    share_store.increment_access(share_2.share_id)
    share_store.increment_access(share_2.share_id)
    latest_share_record = share_store.get(share_2.share_id)
    assert latest_share_record is not None
    assert latest_share_record["last_accessed_at"]

    audit_store = AuditStore("t-proc-stale-share")
    audit_store.append(
        AuditLog(
            log_id=str(uuid.uuid4()),
            tenant_id="t-proc-stale-share",
            timestamp="2026-03-31T00:35:00+00:00",
            user_id="u-analyst",
            username="analyst",
            user_role="member",
            ip_address="127.0.0.1",
            user_agent="pytest",
            action="share.create",
            resource_type="share",
            resource_id=share_0.share_id,
            resource_name="",
            result="success",
            detail={
                "project_id": project.project_id,
                "share_project_document_id": "doc-stale-share-1",
                "bundle_type": "bid_decision_kr",
                "share_decision_council_document_status": "stale_procurement",
                "share_decision_council_document_status_tone": "danger",
                "share_decision_council_document_status_copy": "현재 procurement 대비 이전 council 기준",
                "share_decision_council_document_status_summary": "현재 procurement recommendation 또는 checklist가 바뀌어 외부 공유 전 재확인이 필요합니다.",
            },
            session_id="sess-proc-stale-share-0",
        )
    )
    audit_store.append(
        AuditLog(
            log_id=str(uuid.uuid4()),
            tenant_id="t-proc-stale-share",
            timestamp="2026-03-31T00:40:00+00:00",
            user_id="u-admin",
            username="admin",
            user_role="admin",
            ip_address="127.0.0.1",
            user_agent="pytest",
            action="share.create",
            resource_type="share",
            resource_id=share_1.share_id,
            resource_name="",
            result="success",
            detail={
                "project_id": project.project_id,
                "share_project_document_id": "doc-stale-share-1",
                "bundle_type": "bid_decision_kr",
                "share_decision_council_document_status": "stale_procurement",
                "share_decision_council_document_status_tone": "danger",
                "share_decision_council_document_status_copy": "현재 procurement 대비 이전 council 기준",
                "share_decision_council_document_status_summary": "현재 procurement recommendation 또는 checklist가 바뀌어 외부 공유 전 재확인이 필요합니다.",
            },
            session_id="sess-proc-stale-share",
        )
    )
    audit_store.append(
        AuditLog(
            log_id=str(uuid.uuid4()),
            tenant_id="t-proc-stale-share",
            timestamp="2026-03-31T00:45:00+00:00",
            user_id="u-reviewer",
            username="reviewer",
            user_role="admin",
            ip_address="127.0.0.1",
            user_agent="pytest",
            action="share.create",
            resource_type="share",
            resource_id=share_2.share_id,
            resource_name="",
            result="success",
            detail={
                "project_id": project.project_id,
                "share_project_document_id": "doc-stale-share-1",
                "bundle_type": "bid_decision_kr",
                "share_decision_council_document_status": "stale_revision",
                "share_decision_council_document_status_tone": "warning",
                "share_decision_council_document_status_copy": "이전 council revision (r1)",
                "share_decision_council_document_status_summary": "latest council revision 기준으로 다시 생성한 뒤 외부 공유하는 편이 안전합니다.",
            },
            session_id="sess-proc-stale-share-2",
        )
    )

    login = _register_and_login(client)
    auth_headers = {"Authorization": f"Bearer {login['access_token']}"}
    resp = client.get(
        "/admin/locations/t-proc-stale-share/procurement-quality-summary?activity_actions=share.create",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    summary = resp.json()["procurement"]

    assert summary["activity"]["action_counts"]["share.create"] == 3
    assert summary["activity"]["scope_action_counts"]["share.create"] == 3
    assert summary["activity"]["visible_action_counts"]["share.create"] == 3
    assert summary["activity"]["activity_action_filters"] == ["share.create"]
    assert summary["activity"]["visible_recent_event_count"] == 3
    assert summary["sharing"]["stale_external_share_queue_count"] == 1
    assert summary["sharing"]["active_stale_external_share_queue_count"] == 1
    assert summary["sharing"]["active_accessed_stale_external_share_queue_count"] == 1
    assert summary["sharing"]["active_unaccessed_stale_external_share_queue_count"] == 0
    assert summary["sharing"]["inactive_stale_external_share_queue_count"] == 0
    assert summary["sharing"]["missing_stale_external_share_record_count"] == 0
    assert summary["sharing"]["stale_external_share_status_counts"] == {
        "stale_revision": 1,
    }
    assert [item["project_id"] for item in summary["sharing"]["stale_external_share_queue"]] == [
        project.project_id
    ]
    stale_share_item = summary["sharing"]["stale_external_share_queue"][0]
    assert stale_share_item["project_document_id"] == "doc-stale-share-1"
    assert stale_share_item["decision_council_document_status"] == "stale_revision"
    assert stale_share_item["decision_council_document_status_copy"] == "이전 council revision (r1)"
    assert stale_share_item["bundle_label"] == "의사결정 문서"
    assert stale_share_item["latest_shared_at"] == "2026-03-31T00:45:00+00:00"
    assert stale_share_item["latest_shared_by_username"] == "reviewer"
    assert stale_share_item["stale_share_count"] == 3
    assert stale_share_item["share_id"] == share_2.share_id
    assert stale_share_item["share_url"] == f"/shared/{share_2.share_id}"
    assert stale_share_item["share_record_found"] is True
    assert stale_share_item["share_is_active"] is True
    assert stale_share_item["share_access_count"] == 2
    assert stale_share_item["share_last_accessed_at"] == latest_share_record["last_accessed_at"]
    assert stale_share_item["share_expires_at"] == share_2.expires_at
    assert "latest council revision" in stale_share_item["decision_council_document_status_summary"]
    assert [event["action"] for event in summary["activity"]["recent_events"]] == ["share.create", "share.create", "share.create"]
    recent_event = summary["activity"]["recent_events"][0]
    assert recent_event["linked_project_id"] == project.project_id
    assert recent_event["bundle_type"] == "bid_decision_kr"
    assert recent_event["share_project_document_id"] == "doc-stale-share-1"
    assert recent_event["share_decision_council_document_status"] == "stale_revision"
    assert recent_event["share_decision_council_document_status_copy"] == "이전 council revision (r1)"
    assert "latest council revision" in recent_event["share_decision_council_document_status_summary"]

    focused_resp = client.get(
        f"/admin/locations/t-proc-stale-share/procurement-quality-summary?focus_project_id={project.project_id}&activity_actions=share.create",
        headers=auth_headers,
    )
    assert focused_resp.status_code == 200
    focused_summary = focused_resp.json()["procurement"]
    assert focused_summary["focused_project"]["stale_external_share_item"]["project_document_id"] == "doc-stale-share-1"
    assert focused_summary["focused_project"]["stale_external_share_item"]["decision_council_document_status"] == "stale_revision"
    assert focused_summary["focused_project"]["stale_external_share_item"]["latest_shared_by_username"] == "reviewer"
    assert focused_summary["focused_project"]["stale_external_share_item"]["stale_share_count"] == 3
    assert focused_summary["focused_project"]["stale_external_share_item"]["share_id"] == share_2.share_id
    assert focused_summary["focused_project"]["stale_external_share_item"]["share_is_active"] is True
    assert focused_summary["focused_project"]["stale_external_share_item"]["share_access_count"] == 2
    assert focused_summary["focused_project"]["stale_external_share_item"]["share_last_accessed_at"] == latest_share_record["last_accessed_at"]
    assert focused_summary["focused_project"]["stale_external_share_item"]["bundle_label"] == "의사결정 문서"


def test_admin_procurement_quality_summary_includes_stale_proposal_share_queue(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from app.schemas import (
        NormalizedProcurementOpportunity,
        ProcurementDecisionUpsert,
        ProcurementRecommendation,
    )
    from app.storage.audit_store import AuditLog, AuditStore
    from app.storage.share_store import ShareStore

    client = _make_client(tmp_path, monkeypatch)
    client.post(
        "/admin/tenants",
        json={"tenant_id": "t-proc-stale-proposal", "display_name": "Procurement Stale Proposal Team"},
        headers=_ops_headers(),
    )

    project = client.app.state.project_store.create("t-proc-stale-proposal", "Procurement Stale Proposal Project")
    client.app.state.procurement_store.upsert(
        ProcurementDecisionUpsert(
            project_id=project.project_id,
            tenant_id="t-proc-stale-proposal",
            opportunity=NormalizedProcurementOpportunity(
                source_kind="g2b",
                source_id="PROC-STALE-PROPOSAL-001",
                title="Procurement Stale Proposal Project",
                issuer="조달청",
            ),
            recommendation=ProcurementRecommendation(
                value="CONDITIONAL_GO",
                summary="proposal council 공유 activity 확인",
            ),
        )
    )
    share_store = ShareStore(
        "t-proc-stale-proposal",
        data_dir=client.app.state.data_dir,
        backend=client.app.state.state_backend,
    )
    share = share_store.create(
        tenant_id="t-proc-stale-proposal",
        request_id="req-stale-proposal-share-1",
        title="Stale proposal share",
        created_by="proposal-owner",
        bundle_id="proposal_kr",
        decision_council_document_status="stale_procurement",
        decision_council_document_status_tone="danger",
        decision_council_document_status_copy="현재 procurement 대비 이전 council 기준",
        decision_council_document_status_summary="현재 procurement recommendation 또는 checklist가 바뀌어 외부 공유 전 재확인이 필요합니다.",
    )
    AuditStore("t-proc-stale-proposal").append(
        AuditLog(
            log_id=str(uuid.uuid4()),
            tenant_id="t-proc-stale-proposal",
            timestamp="2026-03-31T01:15:00+00:00",
            user_id="u-proposal",
            username="proposal-owner",
            user_role="member",
            ip_address="127.0.0.1",
            user_agent="pytest",
            action="share.create",
            resource_type="share",
            resource_id=share.share_id,
            resource_name="",
            result="success",
            detail={
                "project_id": project.project_id,
                "share_project_document_id": "doc-stale-proposal-1",
                "bundle_type": "proposal_kr",
                "share_decision_council_document_status": "stale_procurement",
                "share_decision_council_document_status_tone": "danger",
                "share_decision_council_document_status_copy": "현재 procurement 대비 이전 council 기준",
                "share_decision_council_document_status_summary": "현재 procurement recommendation 또는 checklist가 바뀌어 외부 공유 전 재확인이 필요합니다.",
            },
            session_id="sess-proc-stale-proposal",
        )
    )

    login = _register_and_login(client)
    auth_headers = {"Authorization": f"Bearer {login['access_token']}"}
    resp = client.get(
        "/admin/locations/t-proc-stale-proposal/procurement-quality-summary?activity_actions=share.create",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    summary = resp.json()["procurement"]
    assert summary["sharing"]["stale_external_share_queue_count"] == 1
    item = summary["sharing"]["stale_external_share_queue"][0]
    assert item["bundle_type"] == "proposal_kr"
    assert item["bundle_label"] == "제안서"
    assert item["decision_council_document_status"] == "stale_procurement"


def test_admin_locations_can_include_procurement_stale_share_overview(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from app.schemas import (
        NormalizedProcurementOpportunity,
        ProcurementDecisionUpsert,
        ProcurementRecommendation,
    )
    from app.storage.audit_store import AuditLog, AuditStore
    from app.storage.share_store import ShareStore

    client = _make_client(tmp_path, monkeypatch)
    client.post(
        "/admin/tenants",
        json={"tenant_id": "t-loc-stale-card", "display_name": "Location Card Team"},
        headers=_ops_headers(),
    )

    project_store = client.app.state.project_store
    procurement_store = client.app.state.procurement_store
    project = project_store.create("t-loc-stale-card", "Location Card Project")
    procurement_store.upsert(
        ProcurementDecisionUpsert(
            project_id=project.project_id,
            tenant_id="t-loc-stale-card",
            opportunity=NormalizedProcurementOpportunity(
                source_kind="g2b",
                source_id="PROC-LOC-CARD-001",
                title="Location Card Project",
                issuer="조달청",
            ),
            recommendation=ProcurementRecommendation(
                value="NO_GO",
                summary="location card stale share 위험 노출",
            ),
        )
    )
    share_store = ShareStore(
        "t-loc-stale-card",
        data_dir=client.app.state.data_dir,
        backend=client.app.state.state_backend,
    )
    share = share_store.create(
        tenant_id="t-loc-stale-card",
        request_id="req-loc-stale-card",
        title="Location stale share",
        created_by="admin",
        bundle_id="bid_decision_kr",
        decision_council_document_status="stale_procurement",
        decision_council_document_status_tone="danger",
        decision_council_document_status_copy="현재 procurement 대비 이전 council 기준",
        decision_council_document_status_summary="현재 procurement recommendation 또는 checklist가 바뀌어 외부 공유 전 재확인이 필요합니다.",
    )
    share_store.increment_access(share.share_id)
    audit_store = AuditStore("t-loc-stale-card")
    audit_store.append(
        AuditLog(
            log_id=str(uuid.uuid4()),
            tenant_id="t-loc-stale-card",
            timestamp="2026-03-31T00:45:00+00:00",
            user_id="u-admin",
            username="admin",
            user_role="admin",
            ip_address="127.0.0.1",
            user_agent="pytest",
            action="share.create",
            resource_type="share",
            resource_id=share.share_id,
            resource_name="",
            result="success",
            detail={
                "project_id": project.project_id,
                "share_project_document_id": "doc-location-card-share",
                "bundle_type": "bid_decision_kr",
                "share_decision_council_document_status": "stale_procurement",
                "share_decision_council_document_status_tone": "danger",
                "share_decision_council_document_status_copy": "현재 procurement 대비 이전 council 기준",
                "share_decision_council_document_status_summary": "현재 procurement recommendation 또는 checklist가 바뀌어 외부 공유 전 재확인이 필요합니다.",
            },
            session_id="sess-loc-stale-card",
        )
    )

    login = _register_and_login(client)
    auth_headers = {"Authorization": f"Bearer {login['access_token']}"}
    resp = client.get(
        "/admin/locations?include_procurement=1",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    locations = resp.json()
    location = next(item for item in locations if item["tenant_id"] == "t-loc-stale-card")
    assert location["procurement"] == {
        "stale_external_share_queue_count": 1,
        "active_stale_external_share_queue_count": 1,
        "active_accessed_stale_external_share_queue_count": 1,
        "active_unaccessed_stale_external_share_queue_count": 0,
        "inactive_stale_external_share_queue_count": 0,
        "missing_stale_external_share_record_count": 0,
        "has_active_stale_share_exposure": True,
        "top_stale_external_share_item": {
            "project_id": project.project_id,
            "project_name": "Location Card Project",
            "project_document_id": "doc-location-card-share",
            "project_document_title": "",
            "bundle_type": "bid_decision_kr",
            "bundle_label": "의사결정 문서",
            "decision_council_document_status": "stale_procurement",
            "decision_council_document_status_tone": "danger",
            "decision_council_document_status_copy": "현재 procurement 대비 이전 council 기준",
            "decision_council_document_status_summary": "현재 procurement recommendation 또는 checklist가 바뀌어 외부 공유 전 재확인이 필요합니다.",
            "latest_shared_at": "2026-03-31T00:45:00+00:00",
            "latest_shared_by_username": "admin",
            "stale_share_count": 1,
            "share_id": share.share_id,
            "share_url": f"/shared/{share.share_id}",
            "share_record_found": True,
            "share_is_active": True,
            "share_access_count": 1,
            "share_last_accessed_at": share_store.get(share.share_id)["last_accessed_at"],
            "share_expires_at": share.expires_at,
        },
    }


def test_admin_location_procurement_quality_summary_prioritizes_recently_accessed_stale_share_queue(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from app.schemas import (
        NormalizedProcurementOpportunity,
        ProcurementDecisionUpsert,
        ProcurementRecommendation,
    )
    from app.storage.audit_store import AuditLog, AuditStore
    from app.storage.share_store import ShareStore

    client = _make_client(tmp_path, monkeypatch)
    client.post(
        "/admin/tenants",
        json={"tenant_id": "t-proc-stale-share-order", "display_name": "Procurement Stale Share Order Team"},
        headers=_ops_headers(),
    )

    project_store = client.app.state.project_store
    procurement_store = client.app.state.procurement_store
    older_project = project_store.create("t-proc-stale-share-order", "Older Access Project")
    newer_project = project_store.create("t-proc-stale-share-order", "Newer Access Project")
    for project, source_id in (
        (older_project, "PROC-STALE-SHARE-ORDER-001"),
        (newer_project, "PROC-STALE-SHARE-ORDER-002"),
    ):
        procurement_store.upsert(
            ProcurementDecisionUpsert(
                project_id=project.project_id,
                tenant_id="t-proc-stale-share-order",
                opportunity=NormalizedProcurementOpportunity(
                    source_kind="g2b",
                    source_id=source_id,
                    title=project.name,
                    issuer="조달청",
                ),
                recommendation=ProcurementRecommendation(
                    value="NO_GO",
                    summary="stale council 외부 공유 우선순위 정렬 확인",
                ),
            )
        )

    share_store = ShareStore(
        "t-proc-stale-share-order",
        data_dir=client.app.state.data_dir,
        backend=client.app.state.state_backend,
    )
    older_share = share_store.create(
        tenant_id="t-proc-stale-share-order",
        request_id="req-stale-share-order-older",
        title="Older accessed stale share",
        created_by="older",
        bundle_id="bid_decision_kr",
        decision_council_document_status="stale_procurement",
        decision_council_document_status_tone="danger",
        decision_council_document_status_copy="현재 procurement 대비 이전 council 기준",
        decision_council_document_status_summary="public 열람이 있었던 stale share입니다.",
    )
    newer_share = share_store.create(
        tenant_id="t-proc-stale-share-order",
        request_id="req-stale-share-order-newer",
        title="Newer accessed stale share",
        created_by="newer",
        bundle_id="bid_decision_kr",
        decision_council_document_status="stale_procurement",
        decision_council_document_status_tone="danger",
        decision_council_document_status_copy="현재 procurement 대비 이전 council 기준",
        decision_council_document_status_summary="public 열람이 있었던 stale share입니다.",
    )
    share_state = share_store._load()
    share_state[older_share.share_id]["access_count"] = 1
    share_state[older_share.share_id]["last_accessed_at"] = "2026-03-31T00:45:00+00:00"
    share_state[newer_share.share_id]["access_count"] = 1
    share_state[newer_share.share_id]["last_accessed_at"] = "2026-03-31T01:30:00+00:00"
    share_store._save(share_state)

    audit_store = AuditStore("t-proc-stale-share-order")
    audit_store.append(
        AuditLog(
            log_id=str(uuid.uuid4()),
            tenant_id="t-proc-stale-share-order",
            timestamp="2026-03-31T01:00:00+00:00",
            user_id="u-older",
            username="older",
            user_role="admin",
            ip_address="127.0.0.1",
            user_agent="pytest",
            action="share.create",
            resource_type="share",
            resource_id=older_share.share_id,
            resource_name="",
            result="success",
            detail={
                "project_id": older_project.project_id,
                "share_project_document_id": "doc-stale-share-order-older",
                "bundle_type": "bid_decision_kr",
                "share_decision_council_document_status": "stale_procurement",
                "share_decision_council_document_status_tone": "danger",
                "share_decision_council_document_status_copy": "현재 procurement 대비 이전 council 기준",
                "share_decision_council_document_status_summary": "public 열람이 있었던 stale share입니다.",
            },
            session_id="sess-proc-stale-share-order-older",
        )
    )
    audit_store.append(
        AuditLog(
            log_id=str(uuid.uuid4()),
            tenant_id="t-proc-stale-share-order",
            timestamp="2026-03-31T00:40:00+00:00",
            user_id="u-newer",
            username="newer",
            user_role="admin",
            ip_address="127.0.0.1",
            user_agent="pytest",
            action="share.create",
            resource_type="share",
            resource_id=newer_share.share_id,
            resource_name="",
            result="success",
            detail={
                "project_id": newer_project.project_id,
                "share_project_document_id": "doc-stale-share-order-newer",
                "bundle_type": "bid_decision_kr",
                "share_decision_council_document_status": "stale_procurement",
                "share_decision_council_document_status_tone": "danger",
                "share_decision_council_document_status_copy": "현재 procurement 대비 이전 council 기준",
                "share_decision_council_document_status_summary": "public 열람이 있었던 stale share입니다.",
            },
            session_id="sess-proc-stale-share-order-newer",
        )
    )

    login = _register_and_login(client)
    auth_headers = {"Authorization": f"Bearer {login['access_token']}"}
    resp = client.get(
        "/admin/locations/t-proc-stale-share-order/procurement-quality-summary?activity_actions=share.create",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    summary = resp.json()["procurement"]
    queue_project_ids = [
        item["project_id"]
        for item in summary["sharing"]["stale_external_share_queue"]
    ]
    assert queue_project_ids[:2] == [newer_project.project_id, older_project.project_id]
    assert summary["sharing"]["active_accessed_stale_external_share_queue_count"] == 2
    assert summary["sharing"]["active_unaccessed_stale_external_share_queue_count"] == 0


def test_admin_location_procurement_quality_summary_builds_remediation_handoff_queue(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from app.schemas import (
        NormalizedProcurementOpportunity,
        ProcurementDecisionUpsert,
        ProcurementHardFilterResult,
        ProcurementRecommendation,
    )
    from app.storage.audit_store import AuditLog, AuditStore

    client = _make_client(tmp_path, monkeypatch)
    client.post(
        "/admin/tenants",
        json={"tenant_id": "t-proc-handoff", "display_name": "Procurement Handoff Team"},
        headers=_ops_headers(),
    )

    project_store = client.app.state.project_store
    procurement_store = client.app.state.procurement_store
    audit_store = AuditStore("t-proc-handoff")

    shared_project = project_store.create("t-proc-handoff", "Shared Not Opened")
    opened_unresolved_project = project_store.create("t-proc-handoff", "Opened Unresolved")
    opened_resolved_project = project_store.create("t-proc-handoff", "Opened Resolved")

    def _seed_candidate(project, *, source_id: str, notes: str = "") -> None:
        procurement_store.upsert(
            ProcurementDecisionUpsert(
                project_id=project.project_id,
                tenant_id="t-proc-handoff",
                opportunity=NormalizedProcurementOpportunity(
                    source_kind="g2b",
                    source_id=source_id,
                    title=project.name,
                    issuer="조달청",
                ),
                hard_filters=[
                    ProcurementHardFilterResult(
                        code="reference_gap",
                        label="유사 레퍼런스",
                        status="fail",
                        blocking=True,
                        reason="공급 실적 보강 필요",
                    )
                ],
                recommendation=ProcurementRecommendation(
                    value="NO_GO",
                    summary="handoff queue aggregation 확인",
                ),
                notes=notes,
            )
        )
        project_store.add_document(
            project.project_id,
            request_id=f"req-{project.project_id}-proposal",
            bundle_id="proposal_kr",
            title="후속 제안서 초안",
            docs=[{"markdown": "# proposal"}],
            tenant_id="t-proc-handoff",
        )

    _seed_candidate(shared_project, source_id="PROC-HANDOFF-001")
    _seed_candidate(
        opened_unresolved_project,
        source_id="PROC-HANDOFF-002",
        notes=(
            "[override_reason ts=2026-03-31T00:11:00+00:00 actor=ops-lead]\n"
            "예외 검토를 유지하고 retry 준비\n"
            "[/override_reason]"
        ),
    )
    _seed_candidate(opened_resolved_project, source_id="PROC-HANDOFF-003")

    def _append_audit(
        action: str,
        project_id: str,
        timestamp: str,
        *,
        result: str = "success",
        detail: dict | None = None,
    ) -> None:
        audit_store.append(
            AuditLog(
                log_id=str(uuid.uuid4()),
                tenant_id="t-proc-handoff",
                timestamp=timestamp,
                user_id="u-admin",
                username="admin",
                user_role="admin",
                ip_address="127.0.0.1",
                user_agent="pytest",
                action=action,
                resource_type="procurement",
                resource_id=project_id,
                resource_name="",
                result=result,
                detail={"project_id": project_id, **(detail or {})},
                session_id="sess-proc-handoff",
            )
        )

    _append_audit(
        "procurement.downstream_blocked",
        shared_project.project_id,
        "2026-03-31T00:01:00+00:00",
        result="failure",
        detail={
            "bundle_type": "proposal_kr",
            "error_code": "procurement_override_reason_required",
            "recommendation": "NO_GO",
        },
    )
    _append_audit(
        "procurement.remediation_link_opened",
        shared_project.project_id,
        "2026-03-31T00:03:00+00:00",
        detail={
            "bundle_type": "proposal_kr",
            "error_code": "procurement_override_reason_required",
            "recommendation": "NO_GO",
            "procurement_operation": "url_restore",
            "procurement_context_kind": "blocked_event",
        },
    )
    _append_audit(
        "procurement.remediation_link_copied",
        shared_project.project_id,
        "2026-03-31T00:04:00+00:00",
        detail={
            "bundle_type": "proposal_kr",
            "error_code": "procurement_override_reason_required",
            "recommendation": "NO_GO",
            "procurement_operation": "location_summary",
            "procurement_context_kind": "blocked_event",
        },
    )
    _append_audit(
        "procurement.remediation_link_copied",
        shared_project.project_id,
        "2026-03-31T00:05:00+00:00",
        detail={
            "bundle_type": "proposal_kr",
            "error_code": "procurement_override_reason_required",
            "recommendation": "NO_GO",
            "procurement_operation": "project_detail",
            "procurement_context_kind": "blocked_event",
        },
    )

    _append_audit(
        "procurement.downstream_blocked",
        opened_unresolved_project.project_id,
        "2026-03-31T00:10:00+00:00",
        result="failure",
        detail={
            "bundle_type": "proposal_kr",
            "error_code": "procurement_override_reason_required",
            "recommendation": "NO_GO",
        },
    )
    _append_audit(
        "procurement.override_reason",
        opened_unresolved_project.project_id,
        "2026-03-31T00:11:00+00:00",
        detail={"recommendation": "NO_GO"},
    )
    _append_audit(
        "procurement.remediation_link_opened",
        opened_unresolved_project.project_id,
        "2026-03-31T00:12:00+00:00",
        detail={
            "bundle_type": "proposal_kr",
            "error_code": "procurement_override_reason_required",
            "recommendation": "NO_GO",
            "procurement_operation": "url_restore",
            "procurement_context_kind": "override_candidate",
        },
    )

    _append_audit(
        "procurement.downstream_blocked",
        opened_resolved_project.project_id,
        "2026-03-31T00:20:00+00:00",
        result="failure",
        detail={
            "bundle_type": "proposal_kr",
            "error_code": "procurement_override_reason_required",
            "recommendation": "NO_GO",
        },
    )
    _append_audit(
        "procurement.remediation_link_opened",
        opened_resolved_project.project_id,
        "2026-03-31T00:21:00+00:00",
        detail={
            "bundle_type": "proposal_kr",
            "error_code": "procurement_override_reason_required",
            "recommendation": "NO_GO",
            "procurement_operation": "url_restore",
            "procurement_context_kind": "blocked_event",
        },
    )
    _append_audit(
        "procurement.downstream_resolved",
        opened_resolved_project.project_id,
        "2026-03-31T00:22:00+00:00",
        detail={
            "bundle_type": "proposal_kr",
            "recommendation": "NO_GO",
        },
    )

    login = _register_and_login(client)
    auth_headers = {"Authorization": f"Bearer {login['access_token']}"}
    resp = client.get(
        "/admin/locations/t-proc-handoff/procurement-quality-summary",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    summary = resp.json()["procurement"]

    assert summary["handoff"]["remediation_queue_count"] == 3
    assert summary["handoff"]["remediation_queue_status_counts"] == {
        "opened_resolved": 1,
        "opened_unresolved": 1,
        "shared_not_opened": 1,
    }
    queue = summary["handoff"]["remediation_queue"]
    queue_by_project = {item["project_id"]: item for item in queue}
    assert set(queue_by_project) == {
        shared_project.project_id,
        opened_unresolved_project.project_id,
        opened_resolved_project.project_id,
    }

    shared_item = queue_by_project[shared_project.project_id]
    assert shared_item["handoff_status"] == "shared_not_opened"
    assert shared_item["latest_handoff_at"] == "2026-03-31T00:05:00+00:00"
    assert shared_item["latest_copied_at"] == "2026-03-31T00:05:00+00:00"
    assert shared_item["latest_opened_at"] == "2026-03-31T00:03:00+00:00"
    assert shared_item["procurement_operation"] == "project_detail"
    assert shared_item["procurement_context_kind"] == "blocked_event"
    assert shared_item["remediation_status"] == "needs_override_reason"

    opened_unresolved_item = queue_by_project[opened_unresolved_project.project_id]
    assert opened_unresolved_item["handoff_status"] == "opened_unresolved"
    assert opened_unresolved_item["latest_handoff_at"] == "2026-03-31T00:12:00+00:00"
    assert opened_unresolved_item["procurement_context_kind"] == "override_candidate"
    assert opened_unresolved_item["remediation_status"] == "ready_to_retry"

    opened_resolved_item = queue_by_project[opened_resolved_project.project_id]
    assert opened_resolved_item["handoff_status"] == "opened_resolved"
    assert opened_resolved_item["latest_handoff_at"] == "2026-03-31T00:21:00+00:00"
    assert opened_resolved_item["remediation_status"] == "resolved"

    focused_resp = client.get(
        f"/admin/locations/t-proc-handoff/procurement-quality-summary?candidate_scope=unresolved_only&focus_project_id={opened_resolved_project.project_id}",
        headers=auth_headers,
    )
    assert focused_resp.status_code == 200
    focused_summary = focused_resp.json()["procurement"]
    assert focused_summary["focused_project"]["project_id"] == opened_resolved_project.project_id
    assert focused_summary["focused_project"]["visible_in_override_candidates"] is False
    assert focused_summary["focused_project"]["handoff_queue_item"]["handoff_status"] == "opened_resolved"
    assert any(
        item["project_id"] == opened_resolved_project.project_id
        and item["handoff_status"] == "opened_resolved"
        for item in focused_summary["handoff"]["remediation_queue"]
    )


def test_admin_location_procurement_quality_summary_monitor_and_review_scopes(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """candidate_scope=monitor_only/review_only는 monitor 및 review backlog 범위를 올바르게 반환한다."""
    from app.schemas import (
        NormalizedProcurementOpportunity,
        ProcurementDecisionUpsert,
        ProcurementHardFilterResult,
        ProcurementRecommendation,
    )
    from app.storage.audit_store import AuditLog, AuditStore

    client = _make_client(tmp_path, monkeypatch)
    client.post(
        "/admin/tenants",
        json={"tenant_id": "t-proc-monitor", "display_name": "Procurement Monitor Team"},
        headers=_ops_headers(),
    )

    project_store = client.app.state.project_store
    procurement_store = client.app.state.procurement_store

    project_monitor = project_store.create("t-proc-monitor", "Procurement Monitor")
    project_resolved = project_store.create("t-proc-monitor", "Procurement Resolved")

    procurement_store.upsert(
        ProcurementDecisionUpsert(
            project_id=project_monitor.project_id,
            tenant_id="t-proc-monitor",
            opportunity=NormalizedProcurementOpportunity(
                source_kind="g2b",
                source_id="PROC-MONITOR-001",
                title="관제 장비 전환",
                issuer="공공기관",
            ),
            hard_filters=[
                ProcurementHardFilterResult(
                    code="reference_gap",
                    label="유사 레퍼런스",
                    status="fail",
                    blocking=True,
                    reason="추가 검토가 필요한 상태",
                )
            ],
            recommendation=ProcurementRecommendation(value="NO_GO", summary="운영 모니터링 유지"),
        )
    )
    procurement_store.upsert(
        ProcurementDecisionUpsert(
            project_id=project_resolved.project_id,
            tenant_id="t-proc-monitor",
            opportunity=NormalizedProcurementOpportunity(
                source_kind="g2b",
                source_id="PROC-MONITOR-002",
                title="데이터 보안 고도화",
                issuer="행정기관",
            ),
            hard_filters=[
                ProcurementHardFilterResult(
                    code="certificate_missing",
                    label="필수 인증",
                    status="fail",
                    blocking=True,
                    reason="인증 미보유",
                )
            ],
            recommendation=ProcurementRecommendation(
                value="NO_GO",
                summary="override 이후 해결된 상태",
            ),
            notes=(
                "[override_reason ts=2026-03-31T01:00:00+00:00 actor=ops-lead]\n"
                "예외 검토를 거쳐 제안서 초안까지는 진행\n"
                "[/override_reason]"
            ),
        )
    )

    for project, request_id in (
        (project_monitor, "req-monitor-proposal"),
        (project_resolved, "req-resolved-proposal"),
    ):
        project_store.add_document(
            project.project_id,
            request_id=request_id,
            bundle_id="proposal_kr",
            title="제안서 초안",
            docs=[{"markdown": "# proposal"}],
            tenant_id="t-proc-monitor",
        )

    audit_store = AuditStore("t-proc-monitor")

    def _append_audit(
        action: str,
        project_id: str,
        *,
        timestamp: str,
        detail: dict | None = None,
        result: str = "success",
    ) -> None:
        audit_store.append(
            AuditLog(
                log_id=str(uuid.uuid4()),
                tenant_id="t-proc-monitor",
                timestamp=timestamp,
                user_id="u-admin",
                username="admin",
                user_role="admin",
                ip_address="127.0.0.1",
                user_agent="pytest",
                action=action,
                resource_type="procurement",
                resource_id=project_id,
                resource_name="",
                result=result,
                detail=detail or {},
                session_id="sess-proc-monitor",
            )
        )

    _append_audit(
        "procurement.evaluate",
        project_monitor.project_id,
        timestamp="2026-03-31T01:10:00+00:00",
    )
    _append_audit(
        "procurement.downstream_blocked",
        project_resolved.project_id,
        timestamp="2026-03-31T01:11:00+00:00",
        result="failure",
        detail={"bundle_type": "proposal_kr", "error_code": "procurement_override_reason_required"},
    )
    _append_audit(
        "procurement.downstream_resolved",
        project_resolved.project_id,
        timestamp="2026-03-31T01:12:00+00:00",
        detail={"bundle_type": "proposal_kr", "recommendation": "NO_GO"},
    )

    login = _register_and_login(client)
    auth_headers = {"Authorization": f"Bearer {login['access_token']}"}
    resp = client.get(
        "/admin/locations/t-proc-monitor/procurement-quality-summary?candidate_scope=monitor_only",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    summary = resp.json()["procurement"]
    assert summary["outcomes"]["override_candidate_scope"] == "monitor_only"
    assert summary["outcomes"]["override_candidate_count"] == 2
    assert summary["outcomes"]["visible_override_candidate_count"] == 1
    assert summary["outcomes"]["scope_override_candidate_status_counts"] == {"monitor": 1}
    assert [candidate["project_id"] for candidate in summary["outcomes"]["override_candidates"]] == [
        project_monitor.project_id
    ]
    assert summary["activity"]["visible_recent_event_count"] == len(summary["activity"]["recent_events"])
    assert summary["activity"]["scope_recent_event_count"] == 1
    assert summary["activity"]["scope_action_counts"] == {"procurement.evaluate": 1}
    assert {
        str(event.get("linked_project_id", ""))
        for event in summary["activity"]["recent_events"]
        if str(event.get("linked_project_id", "")).strip()
    } == {project_monitor.project_id}

    review_resp = client.get(
        "/admin/locations/t-proc-monitor/procurement-quality-summary?candidate_scope=review_only",
        headers=auth_headers,
    )
    assert review_resp.status_code == 200
    review_summary = review_resp.json()["procurement"]
    assert review_summary["outcomes"]["override_candidate_scope"] == "review_only"
    assert review_summary["outcomes"]["override_candidate_status_filters"] == []
    assert review_summary["outcomes"]["override_candidate_count"] == 2
    assert review_summary["outcomes"]["visible_override_candidate_count"] == 2
    assert review_summary["outcomes"]["scope_override_candidate_status_counts"] == {
        "monitor": 1,
        "resolved": 1,
    }
    assert [candidate["project_id"] for candidate in review_summary["outcomes"]["override_candidates"]] == [
        project_resolved.project_id,
        project_monitor.project_id,
    ]
    assert review_summary["activity"]["visible_recent_event_count"] == len(
        review_summary["activity"]["recent_events"]
    )
    assert review_summary["activity"]["scope_recent_event_count"] == 3
    assert review_summary["activity"]["scope_action_counts"] == {
        "procurement.downstream_blocked": 1,
        "procurement.downstream_resolved": 1,
        "procurement.evaluate": 1,
    }
    assert {
        str(event.get("linked_project_id", ""))
        for event in review_summary["activity"]["recent_events"]
        if str(event.get("linked_project_id", "")).strip()
    } == {project_monitor.project_id, project_resolved.project_id}

    filtered_review_resp = client.get(
        "/admin/locations/t-proc-monitor/procurement-quality-summary?candidate_scope=review_only&candidate_statuses=monitor",
        headers=auth_headers,
    )
    assert filtered_review_resp.status_code == 200
    filtered_review_summary = filtered_review_resp.json()["procurement"]
    assert filtered_review_summary["outcomes"]["override_candidate_scope"] == "review_only"
    assert filtered_review_summary["outcomes"]["override_candidate_status_filters"] == ["monitor"]
    assert filtered_review_summary["outcomes"]["visible_override_candidate_count"] == 1
    assert filtered_review_summary["outcomes"]["scope_override_candidate_status_counts"] == {
        "monitor": 1,
        "resolved": 1,
    }
    assert [candidate["project_id"] for candidate in filtered_review_summary["outcomes"]["override_candidates"]] == [
        project_monitor.project_id
    ]
    assert filtered_review_summary["activity"]["visible_recent_event_count"] == len(
        filtered_review_summary["activity"]["recent_events"]
    )
    assert filtered_review_summary["activity"]["scope_recent_event_count"] == 1
    assert filtered_review_summary["activity"]["scope_action_counts"] == {
        "procurement.evaluate": 1
    }
    assert {
        str(event.get("linked_project_id", ""))
        for event in filtered_review_summary["activity"]["recent_events"]
        if str(event.get("linked_project_id", "")).strip()
    } == {project_monitor.project_id}

    resolved_activity_review_resp = client.get(
        "/admin/locations/t-proc-monitor/procurement-quality-summary?candidate_scope=review_only&activity_actions=procurement.downstream_resolved",
        headers=auth_headers,
    )
    assert resolved_activity_review_resp.status_code == 200
    resolved_activity_review_summary = resolved_activity_review_resp.json()["procurement"]
    assert resolved_activity_review_summary["outcomes"]["override_candidate_scope"] == "review_only"
    assert resolved_activity_review_summary["outcomes"]["visible_override_candidate_count"] == 2
    assert resolved_activity_review_summary["activity"]["activity_action_filters"] == [
        "procurement.downstream_resolved"
    ]
    assert resolved_activity_review_summary["activity"]["scope_recent_event_count"] == 3
    assert resolved_activity_review_summary["activity"]["filtered_recent_event_count"] == 1
    assert resolved_activity_review_summary["activity"]["visible_action_counts"] == {
        "procurement.downstream_resolved": 1
    }
    assert resolved_activity_review_summary["activity"]["visible_recent_event_count"] == 1
    assert [
        event["action"] for event in resolved_activity_review_summary["activity"]["recent_events"]
    ] == ["procurement.downstream_resolved"]


def test_admin_location_procurement_quality_summary_focus_project_recovers_event_beyond_audit_query_cap(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """focus_project_id는 audit query 상위 1000건 밖의 최신 project event도 다시 포함한다."""
    from app.schemas import (
        NormalizedProcurementOpportunity,
        ProcurementDecisionUpsert,
        ProcurementHardFilterResult,
        ProcurementRecommendation,
    )
    from app.storage.audit_store import AuditLog, AuditStore

    client = _make_client(tmp_path, monkeypatch)
    client.post(
        "/admin/tenants",
        json={"tenant_id": "t-proc-cap", "display_name": "Procurement Cap Team"},
        headers=_ops_headers(),
    )

    project_store = client.app.state.project_store
    procurement_store = client.app.state.procurement_store

    project_a = project_store.create("t-proc-cap", "Focused Procurement")
    project_b = project_store.create("t-proc-cap", "Busy Procurement")

    for project, source_id in ((project_a, "PROC-CAP-A"), (project_b, "PROC-CAP-B")):
        procurement_store.upsert(
            ProcurementDecisionUpsert(
                project_id=project.project_id,
                tenant_id="t-proc-cap",
                opportunity=NormalizedProcurementOpportunity(
                    source_kind="g2b",
                    source_id=source_id,
                    title=f"{project.name} 기회",
                    issuer="조달청",
                ),
                hard_filters=[
                    ProcurementHardFilterResult(
                        code="eligible",
                        label="참여 자격",
                        status="pass",
                        blocking=False,
                    )
                ],
                soft_fit_score=75.0,
                soft_fit_status="scored",
                checklist_items=[],
                recommendation=ProcurementRecommendation(value="GO", summary="참여 가능"),
            )
        )

    audit_store = AuditStore("t-proc-cap")

    def _append_audit(action: str, resource_id: str, timestamp: str) -> None:
        audit_store.append(
            AuditLog(
                log_id=str(uuid.uuid4()),
                tenant_id="t-proc-cap",
                timestamp=timestamp,
                user_id="u-admin",
                username="admin",
                user_role="admin",
                ip_address="127.0.0.1",
                user_agent="pytest",
                action=action,
                resource_type="procurement",
                resource_id=resource_id,
                resource_name="",
                result="success",
                detail={},
                session_id="sess-cap",
            )
        )

    _append_audit("procurement.import", project_a.project_id, "2026-03-31T00:00:00+00:00")
    for index in range(1001):
        _append_audit(
            "procurement.evaluate",
            project_b.project_id,
            f"2026-03-31T01:{index // 60:02d}:{index % 60:02d}+00:00",
        )

    login = _register_and_login(client)
    auth_headers = {"Authorization": f"Bearer {login['access_token']}"}

    base_resp = client.get(
        "/admin/locations/t-proc-cap/procurement-quality-summary",
        headers=auth_headers,
    )
    assert base_resp.status_code == 200
    base_events = base_resp.json()["procurement"]["activity"]["recent_events"]
    assert all(event["linked_project_id"] != project_a.project_id for event in base_events)

    focus_resp = client.get(
        f"/admin/locations/t-proc-cap/procurement-quality-summary?focus_project_id={project_a.project_id}",
        headers=auth_headers,
    )
    assert focus_resp.status_code == 200
    focus_data = focus_resp.json()["procurement"]
    focus_events = focus_data["activity"]["recent_events"]
    focused_project = focus_data["focused_project"]

    assert focused_project["project_id"] == project_a.project_id
    assert focused_project["project_name"] == "Focused Procurement"
    assert focused_project["latest_event"]["action"] == "procurement.import"
    assert focused_project["latest_event"]["linked_project_id"] == project_a.project_id
    assert focused_project["visible_in_recent_events"] is True
    assert any(
        event["linked_project_id"] == project_a.project_id
        and event["action"] == "procurement.import"
        for event in focus_events
    )


def test_admin_location_procurement_quality_summary_focus_project_recovers_followup_status_beyond_audit_query_cap(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """focus_project_id는 오래된 blocked/resolved follow-up 상태도 focus card에서 복구한다."""
    from app.schemas import (
        NormalizedProcurementOpportunity,
        ProcurementDecisionUpsert,
        ProcurementHardFilterResult,
        ProcurementRecommendation,
    )
    from app.storage.audit_store import AuditLog, AuditStore

    client = _make_client(tmp_path, monkeypatch)
    client.post(
        "/admin/tenants",
        json={"tenant_id": "t-proc-followup", "display_name": "Procurement Follow-up Team"},
        headers=_ops_headers(),
    )

    project_store = client.app.state.project_store
    procurement_store = client.app.state.procurement_store

    project_a = project_store.create("t-proc-followup", "Legacy NO_GO")
    project_b = project_store.create("t-proc-followup", "Busy Procurement")

    procurement_store.upsert(
        ProcurementDecisionUpsert(
            project_id=project_a.project_id,
            tenant_id="t-proc-followup",
            opportunity=NormalizedProcurementOpportunity(
                source_kind="g2b",
                source_id="PROC-FOLLOWUP-A",
                title="Legacy NO_GO opportunity",
                issuer="조달청",
            ),
            hard_filters=[
                ProcurementHardFilterResult(
                    code="reference_gap",
                    label="유사 레퍼런스",
                    status="fail",
                    blocking=True,
                    reason="과거 실적 부족",
                )
            ],
            soft_fit_score=41.0,
            soft_fit_status="scored",
            checklist_items=[],
            recommendation=ProcurementRecommendation(value="NO_GO", summary="예외 승인 필요"),
            notes=(
                "[override_reason ts=2026-03-31T00:01:00+00:00 actor=ops-lead]\n"
                "기존 고객 운영 연속성을 위해 예외 유지\n"
                "[/override_reason]"
            ),
        )
    )
    procurement_store.upsert(
        ProcurementDecisionUpsert(
            project_id=project_b.project_id,
            tenant_id="t-proc-followup",
            opportunity=NormalizedProcurementOpportunity(
                source_kind="g2b",
                source_id="PROC-FOLLOWUP-B",
                title="Busy procurement opportunity",
                issuer="조달청",
            ),
            hard_filters=[
                ProcurementHardFilterResult(
                    code="eligible",
                    label="참여 자격",
                    status="pass",
                    blocking=False,
                )
            ],
            soft_fit_score=78.0,
            soft_fit_status="scored",
            checklist_items=[],
            recommendation=ProcurementRecommendation(value="GO", summary="참여 가능"),
        )
    )

    project_store.add_document(
        project_a.project_id,
        request_id="req-followup-proposal",
        bundle_id="proposal_kr",
        title="Legacy proposal",
        docs=[{"markdown": "# legacy proposal"}],
        tenant_id="t-proc-followup",
    )

    audit_store = AuditStore("t-proc-followup")

    def _append_audit(
        action: str,
        resource_id: str,
        timestamp: str,
        *,
        result: str = "success",
        detail: dict | None = None,
    ) -> None:
        audit_store.append(
            AuditLog(
                log_id=str(uuid.uuid4()),
                tenant_id="t-proc-followup",
                timestamp=timestamp,
                user_id="u-admin",
                username="admin",
                user_role="admin",
                ip_address="127.0.0.1",
                user_agent="pytest",
                action=action,
                resource_type="procurement",
                resource_id=resource_id,
                resource_name="",
                result=result,
                detail=detail or {},
                session_id="sess-followup",
            )
        )

    _append_audit(
        "procurement.downstream_blocked",
        project_a.project_id,
        "2026-03-31T00:02:00+00:00",
        result="failure",
        detail={"bundle_type": "proposal_kr", "error_code": "procurement_override_reason_required"},
    )
    _append_audit(
        "procurement.downstream_resolved",
        project_a.project_id,
        "2026-03-31T00:03:00+00:00",
        detail={"bundle_type": "proposal_kr", "recommendation": "NO_GO"},
    )
    for index in range(1001):
        _append_audit(
            "procurement.evaluate",
            project_b.project_id,
            f"2026-03-31T01:{index // 60:02d}:{index % 60:02d}+00:00",
        )

    login = _register_and_login(client)
    auth_headers = {"Authorization": f"Bearer {login['access_token']}"}

    base_resp = client.get(
        "/admin/locations/t-proc-followup/procurement-quality-summary",
        headers=auth_headers,
    )
    assert base_resp.status_code == 200
    base_summary = base_resp.json()["procurement"]
    assert base_summary["outcomes"]["override_candidates"][0]["project_id"] == project_a.project_id
    assert base_summary["outcomes"]["override_candidates"][0]["remediation_status"] == "resolved"
    assert base_summary["outcomes"]["override_candidate_status_counts"]["resolved"] == 1
    assert base_summary["outcomes"]["override_candidates_needing_followup"] == 0
    assert base_summary["activity"]["action_counts"]["procurement.downstream_blocked"] == 1
    assert base_summary["activity"]["action_counts"]["procurement.downstream_resolved"] == 1
    assert base_summary["activity"]["action_counts"]["procurement.evaluate"] == 1001

    focus_resp = client.get(
        f"/admin/locations/t-proc-followup/procurement-quality-summary?focus_project_id={project_a.project_id}",
        headers=auth_headers,
    )
    assert focus_resp.status_code == 200
    focused_project = focus_resp.json()["procurement"]["focused_project"]

    assert focused_project["project_id"] == project_a.project_id
    assert focused_project["remediation_status"] == "resolved"
    assert focused_project["latest_event"]["action"] == "procurement.downstream_resolved"
    assert focused_project["latest_activity"][:2] == [
        "procurement.downstream_resolved",
        "procurement.downstream_blocked",
    ]
    assert focused_project["latest_blocked_bundle_type"] == "proposal_kr"
    assert focused_project["latest_resolved_bundle_type"] == "proposal_kr"


def test_admin_tenant_procurement_quality_summary_orders_same_status_candidates_by_followup_time(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """동일 remediation status 후보는 follow-up 기준 시점이 더 최신인 프로젝트가 먼저 온다."""
    from app.schemas import (
        NormalizedProcurementOpportunity,
        ProcurementDecisionUpsert,
        ProcurementHardFilterResult,
        ProcurementRecommendation,
    )
    from app.storage.audit_store import AuditLog, AuditStore

    client = _make_client(tmp_path, monkeypatch)
    client.post(
        "/admin/tenants",
        json={"tenant_id": "t-proc-order", "display_name": "Procurement Ordering Team"},
        headers=_ops_headers(),
    )

    project_store = client.app.state.project_store
    procurement_store = client.app.state.procurement_store
    audit_store = AuditStore("t-proc-order")

    older_project = project_store.create("t-proc-order", "Older Retry")
    newer_project = project_store.create("t-proc-order", "Newer Retry")

    def _append_blocked(project_id: str, timestamp: str) -> None:
        audit_store.append(
            AuditLog(
                log_id=str(uuid.uuid4()),
                tenant_id="t-proc-order",
                timestamp=timestamp,
                user_id="u-admin",
                username="admin",
                user_role="admin",
                ip_address="127.0.0.1",
                user_agent="pytest",
                action="procurement.downstream_blocked",
                resource_type="procurement",
                resource_id=project_id,
                resource_name="",
                result="failure",
                detail={"bundle_type": "proposal_kr", "error_code": "procurement_override_reason_required"},
                session_id="sess-order",
            )
        )

    for project, source_id, blocked_ts, override_ts in (
        (older_project, "PROC-ORDER-A", "2026-03-31T00:00:00+00:00", "2026-03-31T00:01:00+00:00"),
        (newer_project, "PROC-ORDER-B", "2026-03-31T00:01:00+00:00", "2026-03-31T00:02:00+00:00"),
    ):
        procurement_store.upsert(
            ProcurementDecisionUpsert(
                project_id=project.project_id,
                tenant_id="t-proc-order",
                opportunity=NormalizedProcurementOpportunity(
                    source_kind="g2b",
                    source_id=source_id,
                    title=project.name,
                    issuer="조달청",
                ),
                hard_filters=[
                    ProcurementHardFilterResult(
                        code="reference_gap",
                        label="유사 레퍼런스",
                        status="fail",
                        blocking=True,
                        reason="과거 실적 부족",
                    )
                ],
                soft_fit_score=35.0,
                soft_fit_status="scored",
                checklist_items=[],
                recommendation=ProcurementRecommendation(value="NO_GO", summary="override 후 retry 대기"),
                notes=(
                    f"[override_reason ts={override_ts} actor=ops-lead]\n"
                    "예외 검토 유지\n"
                    "[/override_reason]"
                ),
            )
        )
        project_store.add_document(
            project.project_id,
            request_id=f"req-{project.project_id}",
            bundle_id="proposal_kr",
            title=f"{project.name} proposal",
            docs=[{"markdown": "# proposal"}],
            tenant_id="t-proc-order",
        )
        _append_blocked(project.project_id, blocked_ts)

    summary = client.get(
        "/admin/tenants/t-proc-order/procurement-quality-summary",
        headers=_ops_headers(),
    ).json()["procurement"]

    assert summary["outcomes"]["override_candidate_view"] == "latest_followup"
    candidates = summary["outcomes"]["override_candidates"]
    assert [candidate["project_id"] for candidate in candidates[:2]] == [
        newer_project.project_id,
        older_project.project_id,
    ]
    assert summary["outcomes"]["oldest_unresolved_followup"]["project_id"] == older_project.project_id
    assert candidates[0]["followup_updated_at"] == "2026-03-31T00:02:00+00:00"
    assert candidates[1]["followup_updated_at"] == "2026-03-31T00:01:00+00:00"

    login = _register_and_login(client)
    auth_headers = {"Authorization": f"Bearer {login['access_token']}"}
    stale_summary = client.get(
        "/admin/locations/t-proc-order/procurement-quality-summary?candidate_view=stale_unresolved",
        headers=auth_headers,
    ).json()["procurement"]
    stale_candidates = stale_summary["outcomes"]["override_candidates"]
    assert stale_summary["outcomes"]["override_candidate_view"] == "stale_unresolved"
    assert [candidate["project_id"] for candidate in stale_candidates[:2]] == [
        older_project.project_id,
        newer_project.project_id,
    ]


def test_admin_tenant_procurement_quality_summary_not_found(tmp_path: Path, monkeypatch) -> None:
    """GET /admin/tenants/{id}/procurement-quality-summary — 미존재 테넌트 → 404."""
    client = _make_client(tmp_path, monkeypatch)
    resp = client.get(
        "/admin/tenants/ghost/procurement-quality-summary",
        headers=_ops_headers(),
    )
    assert resp.status_code == 404


# ─── 22: _current_tenant_id thread-local in schema.py ────────────────────────

def test_current_tenant_id_thread_local_set_by_generate_documents(tmp_path: Path) -> None:
    """generate_documents() 호출 시 _current_tenant_id 스레드-로컬이 설정됨."""
    from app.domain.schema import _current_tenant_id
    from app.services.generation_service import GenerationService
    from unittest.mock import MagicMock
    from app.bundle_catalog.spec import BundleSpec

    svc, _ = _make_generation_service(tmp_path)

    # Patch _call_and_prepare_bundle to avoid real LLM call
    mock_bundle = {
        "adr": {
            "decision": "d",
            "options": ["a"],
            "risks": ["r"],
            "assumptions": ["a"],
            "checks": ["c"],
            "next_actions": ["n"],
        },
        "onepager": {
            "problem": "p",
            "recommendation": "r",
            "impact": ["i"],
            "checks": ["c"],
        },
        "eval_plan": {
            "metrics": ["m"],
            "test_cases": ["t"],
            "failure_criteria": ["f"],
            "monitoring": ["mo"],
        },
        "ops_checklist": {
            "security": ["s"],
            "reliability": ["r"],
            "cost": ["c"],
            "operations": ["o"],
        },
    }

    captured_tid: list[str] = []

    original_cap = svc._call_and_prepare_bundle

    def _fake_cap(provider, payload, request_id, timer, bundle_spec):
        captured_tid.append(getattr(_current_tenant_id, "value", "NOT_SET"))
        return mock_bundle

    svc._call_and_prepare_bundle = _fake_cap  # type: ignore[method-assign]

    from app.schemas import GenerateRequest
    req = GenerateRequest(title="Test", goal="Goal", bundle_type="tech_decision")
    # Disable cache so _call_and_prepare_bundle is actually invoked
    with patch.dict(os.environ, {"DECISIONDOC_CACHE_ENABLED": "0"}):
        try:
            svc.generate_documents(req, request_id="tid-test", tenant_id="acme-tenant")
        except Exception:
            pass  # lint/validate may fail for mock bundle; we only care about tid capture

    assert captured_tid and captured_tid[0] == "acme-tenant"


def _make_generation_service(tmp_path: Path):
    """Helper shared with test_stability.py pattern."""
    from unittest.mock import MagicMock
    from app.services.generation_service import GenerationService

    provider = MagicMock()
    svc = GenerationService(
        provider_factory=lambda: provider,
        template_dir=tmp_path,
        data_dir=tmp_path,
    )
    return svc, provider
