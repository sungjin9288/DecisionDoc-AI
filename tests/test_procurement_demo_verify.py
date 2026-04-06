from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from scripts.check_procurement_stale_share_demo import verify_procurement_stale_share_demo
from scripts.seed_procurement_stale_share_demo import (
    DEMO_TENANT_ID,
    seed_procurement_stale_share_demo,
)


def _make_client(tmp_path: Path, monkeypatch) -> TestClient:
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DECISIONDOC_PROVIDER", "mock")
    monkeypatch.setenv("DECISIONDOC_ENV", "dev")
    monkeypatch.setenv("DECISIONDOC_SEARCH_ENABLED", "0")
    monkeypatch.setenv("DECISIONDOC_PROCUREMENT_COPILOT_ENABLED", "1")
    monkeypatch.setenv("JWT_SECRET_KEY", "test-demo-verify-jwt-secret-key-32chars!!")
    import app.main as main_module

    return TestClient(main_module.create_app())


def test_verify_procurement_stale_share_demo_checks_seeded_state(tmp_path: Path, monkeypatch) -> None:
    client = _make_client(tmp_path, monkeypatch)
    seeded = seed_procurement_stale_share_demo(
        data_dir=tmp_path,
        base_url="http://testserver",
    )

    result = verify_procurement_stale_share_demo(
        base_url="",
        tenant_id=DEMO_TENANT_ID,
        client=client,
    )

    assert result.tenant_id == "system"
    assert result.project_id == seeded.project_id
    assert result.share_id == seeded.share_id
    assert result.bundle_id == "proposal_kr"
    assert result.stale_status_copy == "현재 procurement 대비 이전 council 기준"
    assert result.internal_tenant_review_url.startswith("/?location_procurement_tenant=system")
    assert f"location_procurement_focus_project={seeded.project_id}" in result.internal_focused_review_url
    assert result.public_share_url.endswith(f"/shared/{seeded.share_id}")
