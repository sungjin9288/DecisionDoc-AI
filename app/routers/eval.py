"""app/routers/eval.py — Eval report, A/B test, and ab-test management endpoints.

Extracted from app/main.py to keep the main module lean.
"""
from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Depends, Request

from app.auth.api_key import require_api_key
from app.dependencies import get_tenant_id, require_admin

router = APIRouter(tags=["eval"])


# ---------------------------------------------------------------------------
# Eval
# ---------------------------------------------------------------------------

@router.get("/eval/report", dependencies=[Depends(require_api_key)])
def get_eval_report(request: Request) -> dict:
    """평가 결과 집계 리포트 반환."""
    require_admin(request)
    from app.eval.report import generate_report
    from app.eval.eval_store import get_eval_store

    return generate_report(get_eval_store(get_tenant_id(request)))


@router.post("/eval/run", dependencies=[Depends(require_api_key)])
def run_eval_now(payload: dict, request: Request) -> dict:
    """request_id + docs를 받아 즉시 평가 실행 후 결과 반환."""
    require_admin(request)
    tenant_id = get_tenant_id(request)
    from app.eval.eval_store import get_eval_store
    from app.eval.pipeline import run_eval_pipeline
    record = run_eval_pipeline(
        request_id=payload.get("request_id", "manual"),
        bundle_id=payload.get("bundle_id", "tech_decision"),
        docs=payload.get("docs", []),
        eval_store=get_eval_store(tenant_id),
        tenant_id=tenant_id,
    )
    return asdict(record)


# ---------------------------------------------------------------------------
# A/B Tests
# ---------------------------------------------------------------------------

@router.get("/ab-tests/active", dependencies=[Depends(require_api_key)])
def list_active_ab_tests(request: Request) -> list[dict]:
    """Return all active A/B prompt variant tests."""
    require_admin(request)
    from app.storage.ab_test_store import get_ab_test_store
    ab_store = get_ab_test_store(get_tenant_id(request))
    return ab_store.list_active_tests()


@router.get("/ab-tests/concluded", dependencies=[Depends(require_api_key)])
def list_concluded_ab_tests(request: Request) -> list[dict]:
    """Return all concluded A/B prompt variant tests."""
    require_admin(request)
    from app.storage.ab_test_store import get_ab_test_store
    ab_store = get_ab_test_store(get_tenant_id(request))
    return ab_store.list_concluded_tests()


@router.post("/ab-tests/{bundle_id}/reset", dependencies=[Depends(require_api_key)])
def reset_ab_test(bundle_id: str, request: Request) -> dict:
    """Delete the A/B test for a bundle (reset for fresh start)."""
    require_admin(request)
    from app.storage.ab_test_store import get_ab_test_store
    ab_store = get_ab_test_store(get_tenant_id(request))
    ab_store.delete_test(bundle_id)
    return {"deleted": True, "bundle_id": bundle_id}
