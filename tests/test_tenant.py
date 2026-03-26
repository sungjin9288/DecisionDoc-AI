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
from pathlib import Path
from unittest.mock import patch

import pytest


# ─── helpers ──────────────────────────────────────────────────────────────────

_OPS_KEY = "test-tenant-ops-key"


def _make_client(tmp_path: Path, monkeypatch):
    """Create a FastAPI TestClient with a temp DATA_DIR and mock provider."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DECISIONDOC_PROVIDER", "mock")
    monkeypatch.setenv("DECISIONDOC_ENV", "dev")
    monkeypatch.setenv("DECISIONDOC_SEARCH_ENABLED", "0")
    monkeypatch.setenv("DECISIONDOC_OPS_KEY", _OPS_KEY)
    import app.main as main_module
    from fastapi.testclient import TestClient
    return TestClient(main_module.create_app())


def _ops_headers(extra: dict | None = None) -> dict:
    """Return headers that include the ops key."""
    h = {"X-DecisionDoc-Ops-Key": _OPS_KEY}
    if extra:
        h.update(extra)
    return h


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
