from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from app.services.decision_council_service import DecisionCouncilService
from app.storage.audit_store import AuditStore
from app.storage.decision_council_store import DecisionCouncilStore
from app.storage.procurement_store import ProcurementDecisionStore
from app.storage.project_store import ProjectStore
from app.storage.share_store import ShareStore
from app.storage.state_backend import get_state_backend
from app.storage.tenant_store import TenantStore
from app.storage.user_store import UserStore


def test_seed_procurement_stale_share_demo_creates_local_manual_verification_state(
    tmp_path: Path,
    monkeypatch,
) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    data_dir = tmp_path / "demo-data"
    base_url = "http://127.0.0.1:8765"
    env = os.environ.copy()
    env["DATA_DIR"] = str(data_dir)

    result = subprocess.run(
        [
            sys.executable,
            "scripts/seed_procurement_stale_share_demo.py",
            "--data-dir",
            str(data_dir),
            "--base-url",
            base_url,
        ],
        cwd=repo_root,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )

    assert "Seeded procurement stale-share demo." in result.stdout
    assert "username: stale_demo_admin" in result.stdout
    assert "internal focused review:" in result.stdout
    assert "/shared/" in result.stdout
    assert "shared_bundle_id: proposal_kr" in result.stdout

    monkeypatch.setenv("DATA_DIR", str(data_dir))
    backend = get_state_backend(data_dir=data_dir)

    tenant_store = TenantStore(data_dir, backend=backend)
    assert tenant_store.get_tenant("system") is not None
    assert tenant_store.get_tenant("t-clean-location") is not None

    user_store = UserStore(data_dir / "tenants" / "system", backend=backend)
    user = user_store.get_by_username("system", "stale_demo_admin")
    assert user is not None
    assert user_store.verify_password(user.user_id, "DemoPass123!")

    project_store = ProjectStore(base_dir=str(data_dir), backend=backend)
    projects = project_store.list_by_tenant("system")
    project = next((item for item in projects if item.name == "거점 stale share 데모 프로젝트"), None)
    assert project is not None
    assert len(project.documents) >= 2
    decision_document = next((doc for doc in project.documents if doc.bundle_id == "bid_decision_kr"), None)
    proposal_document = next((doc for doc in project.documents if doc.bundle_id == "proposal_kr"), None)
    assert decision_document is not None
    assert proposal_document is not None
    assert decision_document.title == "입찰 의사결정 문서"
    assert proposal_document.title == "입찰 제안서"
    assert decision_document.source_decision_council_session_id
    assert proposal_document.source_decision_council_session_id
    assert decision_document.source_decision_council_session_id == proposal_document.source_decision_council_session_id
    assert decision_document.source_decision_council_session_revision == 1
    assert proposal_document.source_decision_council_session_revision == 1
    assert decision_document.source_decision_council_direction
    assert proposal_document.source_decision_council_direction

    procurement_store = ProcurementDecisionStore(base_dir=str(data_dir), backend=backend)
    procurement_record = procurement_store.get(project.project_id, tenant_id="system")
    assert procurement_record is not None
    assert procurement_record.recommendation is not None
    assert procurement_record.recommendation.value.value == "NO_GO"

    decision_council_store = DecisionCouncilStore(base_dir=str(data_dir), backend=backend)
    decision_council_service = DecisionCouncilService(
        decision_council_store=decision_council_store,
    )
    latest_session = decision_council_service.get_latest_procurement_council(
        tenant_id="system",
        project_id=project.project_id,
    )
    assert latest_session is not None
    bound_session = decision_council_service.attach_procurement_binding(
        session=latest_session,
        procurement_record=procurement_record,
    )
    assert bound_session.current_procurement_binding_status == "stale"
    assert bound_session.current_procurement_binding_reason_code == "procurement_updated"

    share_store = ShareStore("system", data_dir=data_dir, backend=backend)
    shares = share_store.list_by_user(user.user_id)
    assert len(shares) == 1
    share = shares[0]
    assert share["request_id"] == "demo-procurement-stale-share-proposal"
    assert share["bundle_id"] == "proposal_kr"
    assert share["decision_council_document_status"] == "stale_procurement"
    assert share["is_active"] is True
    assert share["access_count"] == 1
    assert share["last_accessed_at"]

    audit_store = AuditStore("system")
    latest_share_audit = audit_store.find_latest_entry(
        "system",
        actions=("share.create",),
        resource_ids=(share["share_id"],),
    )
    assert latest_share_audit is not None
    assert latest_share_audit["detail"]["project_id"] == project.project_id
    assert latest_share_audit["detail"]["share_project_document_id"] == proposal_document.doc_id
    assert latest_share_audit["detail"]["bundle_type"] == "proposal_kr"
    assert latest_share_audit["detail"]["share_decision_council_document_status"] == "stale_procurement"
