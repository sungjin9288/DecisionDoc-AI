#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.schemas import (
    NormalizedProcurementOpportunity,
    ProcurementChecklistItem,
    ProcurementChecklistSeverity,
    ProcurementChecklistStatus,
    ProcurementDecisionUpsert,
    ProcurementHardFilterResult,
    ProcurementHardFilterStatus,
    ProcurementRecommendation,
    ProcurementRecommendationValue,
    ProcurementScoreStatus,
)
from app.services.decision_council_service import (
    DecisionCouncilService,
    describe_procurement_council_document_status,
)
from app.storage.audit_store import AuditLog, AuditStore
from app.storage.decision_council_store import DecisionCouncilStore
from app.storage.local import LocalStorage
from app.storage.procurement_store import ProcurementDecisionStore
from app.storage.project_store import ProjectStore
from app.storage.share_store import ShareStore
from app.storage.state_backend import get_state_backend
from app.storage.tenant_store import TenantStore
from app.storage.user_store import UserRole, UserStore


DEMO_USERNAME = "stale_demo_admin"
DEMO_PASSWORD = "DemoPass123!"
DEMO_EMAIL = "stale-demo-admin@example.invalid"
DEMO_DISPLAY_NAME = "Stale Share Demo Admin"
DEMO_PROJECT_NAME = "거점 stale share 데모 프로젝트"
DEMO_PROJECT_DESCRIPTION = "locations overview와 stale-share review를 직접 확인하는 로컬 데모"
DEMO_PROJECT_CLIENT = "DecisionDoc Demo"
DEMO_CONTRACT_NUMBER = "DEMO-STALE-SHARE-001"
DEMO_DECISION_REQUEST_ID = "demo-procurement-stale-share-bid-decision"
DEMO_DECISION_DOCUMENT_TITLE = "입찰 의사결정 문서"
DEMO_DECISION_BUNDLE_ID = "bid_decision_kr"
DEMO_PROPOSAL_REQUEST_ID = "demo-procurement-stale-share-proposal"
DEMO_PROPOSAL_DOCUMENT_TITLE = "입찰 제안서"
DEMO_PROPOSAL_BUNDLE_ID = "proposal_kr"
DEMO_SHARED_BUNDLE_ID = DEMO_PROPOSAL_BUNDLE_ID
DEMO_TENANT_ID = "system"
CONTRAST_TENANT_ID = "t-clean-location"
CONTRAST_TENANT_NAME = "정상 거점"
DEFAULT_BASE_URL = "http://127.0.0.1:8765"


@dataclass
class DemoSeedResult:
    data_dir: Path
    base_url: str
    username: str
    password: str
    project_id: str
    project_name: str
    shared_bundle_id: str
    shared_project_document_id: str
    decision_project_document_id: str
    proposal_project_document_id: str
    decision_council_session_id: str
    decision_council_session_revision: int
    internal_tenant_review_url: str
    internal_focused_review_url: str
    public_share_url: str
    share_id: str


def _fresh_data_guard(data_dir: Path) -> Path | None:
    tenants_path = data_dir / "tenants.json"
    if tenants_path.exists() and tenants_path.stat().st_size > 0:
        try:
            tenants_payload = json.loads(tenants_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError):
            return tenants_path
        tenant_ids = {str(key) for key in tenants_payload.keys()} if isinstance(tenants_payload, dict) else set()
        if tenant_ids - {DEMO_TENANT_ID}:
            return tenants_path

    candidates = [
        data_dir / "tenants" / DEMO_TENANT_ID / "users.json",
        data_dir / "tenants" / DEMO_TENANT_ID / "projects.json",
        data_dir / "tenants" / DEMO_TENANT_ID / "procurement_decisions.json",
        data_dir / "tenants" / DEMO_TENANT_ID / "decision_council_sessions.json",
        data_dir / "tenants" / DEMO_TENANT_ID / "shares.json",
        data_dir / "tenants" / DEMO_TENANT_ID / "audit_logs.jsonl",
    ]
    for path in candidates:
        if path.exists() and path.is_file() and path.stat().st_size > 0:
            return path
    return None


def _build_internal_review_url(base_url: str, *, focus_project_id: str = "") -> str:
    from urllib.parse import urlencode

    params = {
        "location_procurement_tenant": DEMO_TENANT_ID,
        "location_procurement_activity_actions": "share.create",
    }
    if focus_project_id:
        params["location_procurement_focus_project"] = focus_project_id
    return f"{base_url.rstrip('/')}/?{urlencode(params)}"


def _build_public_share_url(base_url: str, share_id: str) -> str:
    return f"{base_url.rstrip('/')}/shared/{share_id}"


def _seed_initial_procurement_state(
    procurement_store: ProcurementDecisionStore,
    *,
    project_id: str,
) -> object:
    return procurement_store.upsert(
        ProcurementDecisionUpsert(
            project_id=project_id,
            tenant_id=DEMO_TENANT_ID,
            opportunity=NormalizedProcurementOpportunity(
                source_kind="g2b",
                source_id="DEMO-G2B-STALE-SHARE-001",
                source_url="https://www.g2b.go.kr",
                title=DEMO_PROJECT_NAME,
                issuer="조달청",
                budget="12억원",
                deadline="2026-04-30",
                bid_type="제한경쟁",
                category="AI 서비스",
                region="전국",
                raw_text_preview="초기 council 생성 시점에는 참여 가능성이 높았던 데모 공고입니다.",
            ),
            hard_filters=[
                ProcurementHardFilterResult(
                    code="mandatory_license",
                    label="필수 자격 보유",
                    status=ProcurementHardFilterStatus.PASS,
                    blocking=True,
                    reason="필수 자격 보유로 참여 제한 없음",
                    evidence=["공고 기본 자격 요건 충족"],
                ),
            ],
            soft_fit_score=84.0,
            soft_fit_status=ProcurementScoreStatus.SCORED,
            checklist_items=[
                ProcurementChecklistItem(
                    category="domain capability fit",
                    title="공공 AI 구축 레퍼런스 제출 가능",
                    status=ProcurementChecklistStatus.READY,
                    severity=ProcurementChecklistSeverity.MEDIUM,
                    evidence="최근 2년 공공 AI 구축 사례 3건 확보",
                    remediation_note="",
                ),
                ProcurementChecklistItem(
                    category="schedule and deadline readiness",
                    title="제안 일정 수립 가능",
                    status=ProcurementChecklistStatus.READY,
                    severity=ProcurementChecklistSeverity.MEDIUM,
                    evidence="내부 PM과 제안 인력이 즉시 투입 가능",
                    remediation_note="",
                ),
            ],
            recommendation=ProcurementRecommendation(
                value=ProcurementRecommendationValue.GO,
                summary="초기 기준에서는 참여 가능한 공고로 판단됩니다.",
                evidence=[
                    "핵심 자격 조건 충족",
                    "공공 AI 수행 레퍼런스 확보",
                ],
            ),
            notes="demo initial procurement state",
        )
    )


def _seed_stale_procurement_state(
    procurement_store: ProcurementDecisionStore,
    *,
    project_id: str,
) -> object:
    return procurement_store.upsert(
        ProcurementDecisionUpsert(
            project_id=project_id,
            tenant_id=DEMO_TENANT_ID,
            opportunity=NormalizedProcurementOpportunity(
                source_kind="g2b",
                source_id="DEMO-G2B-STALE-SHARE-001",
                source_url="https://www.g2b.go.kr",
                title=DEMO_PROJECT_NAME,
                issuer="조달청",
                budget="12억원",
                deadline="2026-04-30",
                bid_type="제한경쟁",
                category="AI 서비스",
                region="전국",
                raw_text_preview="추가 공고 정정과 내부 확인 결과로 stale council 재검토가 필요한 상태입니다.",
            ),
            hard_filters=[
                ProcurementHardFilterResult(
                    code="recent_public_reference",
                    label="최근 공공 레퍼런스 증빙",
                    status=ProcurementHardFilterStatus.FAIL,
                    blocking=True,
                    reason="공고 정정 후 요구된 최신 공공 구축 실적 증빙이 아직 준비되지 않았습니다.",
                    evidence=["정정 공고에서 최근 1년 내 공공 유사 실적 제출 요구"],
                ),
            ],
            soft_fit_score=56.0,
            soft_fit_status=ProcurementScoreStatus.SCORED,
            missing_data=[
                "최근 1년 공공 유사 실적 증빙",
                "최신 제안 인력 CV 확정본",
            ],
            checklist_items=[
                ProcurementChecklistItem(
                    category="reference cases and proof points",
                    title="최신 공공 실적 증빙 업데이트",
                    status=ProcurementChecklistStatus.BLOCKED,
                    severity=ProcurementChecklistSeverity.CRITICAL,
                    evidence="요구되는 최신 실적 증빙 문서가 아직 확보되지 않음",
                    remediation_note="최신 공공 레퍼런스 증빙 확보 후 council rerun",
                ),
                ProcurementChecklistItem(
                    category="staffing and partner readiness",
                    title="핵심 제안 인력 확정",
                    status=ProcurementChecklistStatus.ACTION_NEEDED,
                    severity=ProcurementChecklistSeverity.HIGH,
                    evidence="주요 인력 CV 최신본 확인 필요",
                    remediation_note="인력 CV 최신화 후 proposal handoff 재검토",
                ),
            ],
            recommendation=ProcurementRecommendation(
                value=ProcurementRecommendationValue.NO_GO,
                summary="최신 정정 공고 기준으로는 stale council을 재검토하기 전 외부 공유와 진행이 안전하지 않습니다.",
                evidence=[
                    "최신 공공 실적 증빙 미확보",
                    "핵심 제안 인력 확정 지연",
                ],
                missing_data=[
                    "최근 1년 공공 유사 실적 증빙",
                    "최신 제안 인력 CV 확정본",
                ],
                remediation_notes=[
                    "최신 실적 증빙 확보 후 Decision Council 다시 실행",
                    "최신 기준으로 bid_decision_kr 재생성",
                ],
            ),
            notes="demo stale procurement state",
        )
    )


def _build_decision_demo_markdown() -> str:
    return "\n".join(
        [
            "# 입찰 의사결정 문서",
            "",
            "## 요약",
            "- 초기 Decision Council 기준으로는 참여 가능성이 있었습니다.",
            "- 이후 procurement recommendation이 `NO_GO`로 바뀌어 stale council 기반 문서가 되었습니다.",
            "",
            "## 즉시 확인 포인트",
            "- 외부 공유 링크가 아직 활성 상태인지",
            "- 최근 public 열람이 있었는지",
            "- Decision Council을 다시 실행해야 하는지",
            "",
            "## 운영 메모",
            "이 문서는 Decision Council v1 stale external share triage 로컬 데모를 위한 seed 데이터입니다.",
        ]
    )


def _build_proposal_demo_markdown() -> str:
    return "\n".join(
        [
            "# 입찰 제안서",
            "",
            "## 제안 전략 요약",
            "- 이 제안서는 같은 Decision Council session을 재사용해 작성된 proposal_kr 예시입니다.",
            "- 이후 procurement recommendation이 `NO_GO`로 바뀌어 stale council 기반 proposal 문서가 되었습니다.",
            "",
            "## 즉시 확인 포인트",
            "- proposal row가 stale council 경고를 유지하는지",
            "- stale proposal share가 locations overview와 public shared page에 동시에 보이는지",
            "- council rerun 전에는 proposal_kr follow-up이 guarded 되는지",
            "",
            "## 운영 메모",
            "이 문서는 Decision Council v1 proposal-first 로컬 데모를 위한 seed 데이터입니다.",
        ]
    )


def seed_procurement_stale_share_demo(
    *,
    data_dir: Path,
    base_url: str,
) -> DemoSeedResult:
    data_dir = Path(data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    os.environ["DATA_DIR"] = str(data_dir)

    dirty_path = _fresh_data_guard(data_dir)
    if dirty_path is not None:
        raise SystemExit(
            "seed_procurement_stale_share_demo.py expects a fresh DATA_DIR for deterministic output. "
            f"Found existing state at: {dirty_path}. "
            "Use a new empty directory such as /tmp/decisiondoc-stale-share-demo."
        )

    backend = get_state_backend(data_dir=data_dir)
    tenant_store = TenantStore(data_dir, backend=backend)
    tenant_store.ensure_system_tenant()
    if tenant_store.get_tenant(CONTRAST_TENANT_ID) is None:
        tenant_store.create_tenant(CONTRAST_TENANT_ID, CONTRAST_TENANT_NAME)

    user_store = UserStore(data_dir / "tenants" / DEMO_TENANT_ID, backend=backend)
    user = user_store.create(
        tenant_id=DEMO_TENANT_ID,
        username=DEMO_USERNAME,
        display_name=DEMO_DISPLAY_NAME,
        email=DEMO_EMAIL,
        password=DEMO_PASSWORD,
        role=UserRole.ADMIN,
    )

    project_store = ProjectStore(base_dir=str(data_dir), backend=backend)
    procurement_store = ProcurementDecisionStore(base_dir=str(data_dir), backend=backend)
    decision_council_store = DecisionCouncilStore(base_dir=str(data_dir), backend=backend)
    decision_council_service = DecisionCouncilService(decision_council_store=decision_council_store)
    share_store = ShareStore(DEMO_TENANT_ID, data_dir=data_dir, backend=backend)
    storage = LocalStorage(data_dir=data_dir, exports_dir=data_dir)

    project = project_store.create(
        DEMO_TENANT_ID,
        DEMO_PROJECT_NAME,
        description=DEMO_PROJECT_DESCRIPTION,
        client=DEMO_PROJECT_CLIENT,
        contract_number=DEMO_CONTRACT_NUMBER,
    )

    initial_procurement = _seed_initial_procurement_state(procurement_store, project_id=project.project_id)
    council_session = decision_council_service.run_procurement_council(
        tenant_id=DEMO_TENANT_ID,
        project_id=project.project_id,
        goal="이 입찰에 참여할지 판단하고 외부 공유 전 review 포인트까지 정리해줘.",
        context="로컬 stale-share triage 데모를 위해 실제 운영자가 보는 council/risk/handoff 흐름을 재현한다.",
        constraints="provider debate 없이 deterministic council 결과만 사용한다.",
        procurement_record=initial_procurement,
    )

    decision_markdown = _build_decision_demo_markdown()
    storage.save_bundle(
        DEMO_DECISION_REQUEST_ID,
        {
            "request_id": DEMO_DECISION_REQUEST_ID,
            "bundle_id": DEMO_DECISION_BUNDLE_ID,
            "title": DEMO_DECISION_DOCUMENT_TITLE,
            "documents": {
                DEMO_DECISION_BUNDLE_ID: decision_markdown,
            },
        },
    )
    decision_project_document = project_store.add_document(
        project.project_id,
        request_id=DEMO_DECISION_REQUEST_ID,
        bundle_id=DEMO_DECISION_BUNDLE_ID,
        title=DEMO_DECISION_DOCUMENT_TITLE,
        docs=[{"doc_type": DEMO_DECISION_BUNDLE_ID, "markdown": decision_markdown}],
        tenant_id=DEMO_TENANT_ID,
        source_decision_council_session_id=council_session.session_id,
        source_decision_council_session_revision=council_session.session_revision,
        source_decision_council_direction=council_session.consensus.recommended_direction,
    )

    proposal_markdown = _build_proposal_demo_markdown()
    storage.save_bundle(
        DEMO_PROPOSAL_REQUEST_ID,
        {
            "request_id": DEMO_PROPOSAL_REQUEST_ID,
            "bundle_id": DEMO_PROPOSAL_BUNDLE_ID,
            "title": DEMO_PROPOSAL_DOCUMENT_TITLE,
            "documents": {
                DEMO_PROPOSAL_BUNDLE_ID: proposal_markdown,
            },
        },
    )
    proposal_project_document = project_store.add_document(
        project.project_id,
        request_id=DEMO_PROPOSAL_REQUEST_ID,
        bundle_id=DEMO_PROPOSAL_BUNDLE_ID,
        title=DEMO_PROPOSAL_DOCUMENT_TITLE,
        docs=[{"doc_type": DEMO_PROPOSAL_BUNDLE_ID, "markdown": proposal_markdown}],
        tenant_id=DEMO_TENANT_ID,
        source_decision_council_session_id=council_session.session_id,
        source_decision_council_session_revision=council_session.session_revision,
        source_decision_council_direction=council_session.consensus.recommended_direction,
    )

    current_procurement = _seed_stale_procurement_state(procurement_store, project_id=project.project_id)
    latest_session = decision_council_service.get_latest_procurement_council(
        tenant_id=DEMO_TENANT_ID,
        project_id=project.project_id,
    )
    if latest_session is None:
        raise SystemExit("Decision Council session was not persisted.")
    bound_session = decision_council_service.attach_procurement_binding(
        session=latest_session,
        procurement_record=current_procurement,
    )
    document_status = describe_procurement_council_document_status(
        bundle_id=DEMO_SHARED_BUNDLE_ID,
        source_session_id=proposal_project_document.source_decision_council_session_id,
        source_session_revision=proposal_project_document.source_decision_council_session_revision,
        latest_session=bound_session,
    )
    if not document_status or document_status["status"] != "stale_procurement":
        raise SystemExit("Demo seed expected a stale_procurement council-backed document status.")

    share_link = share_store.create(
        tenant_id=DEMO_TENANT_ID,
        request_id=DEMO_PROPOSAL_REQUEST_ID,
        title=DEMO_PROPOSAL_DOCUMENT_TITLE,
        created_by=user.user_id,
        bundle_id=DEMO_SHARED_BUNDLE_ID,
        decision_council_document_status=document_status["status"],
        decision_council_document_status_tone=document_status["tone"],
        decision_council_document_status_copy=document_status["copy"],
        decision_council_document_status_summary=document_status["summary"],
    )
    share_store.increment_access(share_link.share_id)

    audit_store = AuditStore(DEMO_TENANT_ID)
    audit_store.append(
        AuditLog(
            log_id=f"demo-share-{share_link.share_id}",
            tenant_id=DEMO_TENANT_ID,
            timestamp=datetime.now(timezone.utc).isoformat(timespec="microseconds"),
            user_id=user.user_id,
            username=user.username,
            user_role=user.role.value,
            ip_address="127.0.0.1",
            user_agent="seed_procurement_stale_share_demo.py",
            action="share.create",
            resource_type="share",
            resource_id=share_link.share_id,
            resource_name=DEMO_PROPOSAL_DOCUMENT_TITLE,
            result="success",
            detail={
                "project_id": project.project_id,
                "share_project_document_id": proposal_project_document.doc_id,
                "bundle_type": DEMO_SHARED_BUNDLE_ID,
                "share_decision_council_document_status": document_status["status"],
                "share_decision_council_document_status_tone": document_status["tone"],
                "share_decision_council_document_status_copy": document_status["copy"],
                "share_decision_council_document_status_summary": document_status["summary"],
            },
            session_id="demo-procurement-stale-share-seed",
        )
    )

    return DemoSeedResult(
        data_dir=data_dir,
        base_url=base_url.rstrip("/"),
        username=DEMO_USERNAME,
        password=DEMO_PASSWORD,
        project_id=project.project_id,
        project_name=project.name,
        shared_bundle_id=DEMO_SHARED_BUNDLE_ID,
        shared_project_document_id=proposal_project_document.doc_id,
        decision_project_document_id=decision_project_document.doc_id,
        proposal_project_document_id=proposal_project_document.doc_id,
        decision_council_session_id=council_session.session_id,
        decision_council_session_revision=council_session.session_revision,
        internal_tenant_review_url=_build_internal_review_url(base_url),
        internal_focused_review_url=_build_internal_review_url(
            base_url,
            focus_project_id=project.project_id,
        ),
        public_share_url=_build_public_share_url(base_url, share_link.share_id),
        share_id=share_link.share_id,
    )


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Seed a deterministic local procurement stale-share demo.",
    )
    parser.add_argument(
        "--data-dir",
        default=os.getenv("DATA_DIR", "/tmp/decisiondoc-stale-share-demo"),
        help="Fresh DATA_DIR to seed. Existing state is rejected for deterministic output.",
    )
    parser.add_argument(
        "--base-url",
        default=DEFAULT_BASE_URL,
        help="Base URL printed for manual verification links.",
    )
    return parser.parse_args(argv)


def _print_result(result: DemoSeedResult) -> None:
    print("Seeded procurement stale-share demo.")
    print("")
    print(f"DATA_DIR: {result.data_dir}")
    print(f"Base URL: {result.base_url}")
    print("")
    print("Login")
    print(f"  username: {result.username}")
    print(f"  password: {result.password}")
    print("")
    print("Seeded project")
    print(f"  project_id: {result.project_id}")
    print(f"  project_name: {result.project_name}")
    print(f"  shared_bundle_id: {result.shared_bundle_id}")
    print(f"  shared_project_document_id: {result.shared_project_document_id}")
    print(f"  decision_project_document_id: {result.decision_project_document_id}")
    print(f"  proposal_project_document_id: {result.proposal_project_document_id}")
    print(f"  decision_council_session_id: {result.decision_council_session_id}")
    print(f"  decision_council_session_revision: {result.decision_council_session_revision}")
    print(f"  share_id: {result.share_id}")
    print("")
    print("Links")
    print(f"  internal tenant review: {result.internal_tenant_review_url}")
    print(f"  internal focused review: {result.internal_focused_review_url}")
    print(f"  public share: {result.public_share_url}")
    print("")
    print("Manual check")
    print("  1. Start the app with the same DATA_DIR and DECISIONDOC_PROCUREMENT_COPILOT_ENABLED=1.")
    print("  2. Sign in with the seeded admin account above.")
    print("  3. Open the focused review URL to land directly on the stale-share review state.")
    print("  4. Confirm the same Decision Council session is linked to both bid_decision_kr and proposal_kr rows.")
    print("  5. Confirm the proposal_kr share is stale, publicly reachable, and visible in locations stale-share triage.")
    print("  6. Open the public share URL, then revoke it from the UI and verify the same URL becomes 404.")


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv or sys.argv[1:])
    result = seed_procurement_stale_share_demo(
        data_dir=Path(args.data_dir).expanduser(),
        base_url=str(args.base_url).strip() or DEFAULT_BASE_URL,
    )
    _print_result(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
