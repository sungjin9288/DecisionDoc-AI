"""app/routers/dashboard.py — AI performance dashboard endpoints.

Extracted from app/main.py. All state accessed via request.app.state.
"""
from __future__ import annotations

import json as _json

from fastapi import APIRouter, Request

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/overview")
def dashboard_overview(request: Request) -> dict:
    """AI 성능 대시보드 — 전체 요약 지표."""
    from app.storage.ab_test_store import ABTestStore

    eval_store = request.app.state.eval_store
    feedback_store = request.app.state.feedback_store
    prompt_override_store = request.app.state.prompt_override_store
    data_dir = request.app.state.data_dir

    eval_stats = eval_store.get_all_stats()

    all_feedback = feedback_store.get_all()
    total_feedback = len(all_feedback)
    avg_rating: float | None = None
    if all_feedback:
        avg_rating = round(sum(f.get("rating", 0) for f in all_feedback) / total_feedback, 2)

    ab_store = ABTestStore(data_dir)
    active_ab_tests = len(ab_store.list_active_tests())

    auto_registry_path = data_dir / "auto_bundles" / "registry.json"
    auto_bundles_count = 0
    if auto_registry_path.exists():
        try:
            auto_bundles_count = len(_json.loads(auto_registry_path.read_text(encoding="utf-8")))
        except Exception:
            pass

    active_overrides_count = len(prompt_override_store.list_overrides())

    return {
        "total_generations": eval_stats["total_count"],
        "avg_heuristic_score": eval_stats["avg_heuristic"],
        "avg_llm_score": eval_stats["avg_llm"],
        "total_feedback_count": total_feedback,
        "avg_rating": avg_rating,
        "active_ab_tests": active_ab_tests,
        "auto_bundles_count": auto_bundles_count,
        "active_overrides_count": active_overrides_count,
        "low_quality_retries": eval_stats["low_quality_count"],
    }


@router.get("/bundle-performance")
def dashboard_bundle_performance(request: Request) -> list[dict]:
    """AI 성능 대시보드 — 번들별 성능 지표 (최근 30일)."""
    from app.storage.ab_test_store import ABTestStore

    eval_store = request.app.state.eval_store
    feedback_store = request.app.state.feedback_store
    prompt_override_store = request.app.state.prompt_override_store
    data_dir = request.app.state.data_dir

    per_bundle = eval_store.get_per_bundle_stats()
    ab_store = ABTestStore(data_dir)
    overrides = {o["bundle_id"]: o for o in prompt_override_store.list_overrides()}

    all_feedback = feedback_store.get_all()
    fb_by_bundle: dict = {}
    for fb in all_feedback:
        bid = fb.get("bundle_type", "")
        if bid:
            fb_by_bundle.setdefault(bid, []).append(fb.get("rating", 0))

    result = []
    for bundle_id, stats in per_bundle.items():
        recent = stats["recent_scores"]
        trend = "stable"
        if len(recent) >= 10:
            prev5 = sum(recent[-10:-5]) / 5
            last5 = sum(recent[-5:]) / 5
            diff = last5 - prev5
            if diff > 0.05:
                trend = "improving"
            elif diff < -0.05:
                trend = "declining"
        elif len(recent) >= 6:
            half = len(recent) // 2
            prev = sum(recent[:half]) / half
            last = sum(recent[half:]) / (len(recent) - half)
            diff = last - prev
            if diff > 0.05:
                trend = "improving"
            elif diff < -0.05:
                trend = "declining"

        avg_fb = None
        if bundle_id in fb_by_bundle:
            ratings = fb_by_bundle[bundle_id]
            avg_fb = round(sum(ratings) / len(ratings), 2)

        result.append({
            "bundle_id": bundle_id,
            "generation_count": stats["count"],
            "avg_heuristic_score": stats["avg_heuristic"],
            "avg_llm_score": stats["avg_llm"],
            "avg_rating": avg_fb,
            "score_trend": trend,
            "has_active_ab_test": ab_store.get_active_test(bundle_id) is not None,
            "has_override": bundle_id in overrides,
            "last_generated": stats["last_timestamp"],
        })

    result.sort(key=lambda x: x["avg_heuristic_score"] or 0, reverse=True)
    return result


@router.get("/improvement-history")
def dashboard_improvement_history(request: Request) -> list[dict]:
    """AI 성능 대시보드 — AI 자기개선 이력 (시간순)."""
    prompt_override_store = request.app.state.prompt_override_store
    data_dir = request.app.state.data_dir

    events: list[dict] = []

    for override in prompt_override_store.list_overrides():
        events.append({
            "timestamp": override.get("created_at", ""),
            "event_type": "override_saved",
            "bundle_id": override.get("bundle_id", ""),
            "detail": f"프롬프트 개선 저장 — {override.get('trigger_reason', '')} (적용 {override.get('applied_count', 0)}회)",
            "score_before": override.get("avg_score_before"),
            "score_after": None,
        })

    all_ab: list[dict] = []
    try:
        ab_data = _json.loads((data_dir / "ab_tests.json").read_text(encoding="utf-8")) if (data_dir / "ab_tests.json").exists() else {}
        all_ab = list(ab_data.values())
    except Exception:
        pass

    for test in all_ab:
        events.append({
            "timestamp": test.get("created_at", ""),
            "event_type": "ab_test_started",
            "bundle_id": test.get("bundle_id", ""),
            "detail": "A/B 테스트 시작 (variant_a vs variant_b)",
            "score_before": None,
            "score_after": None,
        })
        if test.get("status") == "concluded" and test.get("concluded_at"):
            events.append({
                "timestamp": test.get("concluded_at", ""),
                "event_type": "ab_test_concluded",
                "bundle_id": test.get("bundle_id", ""),
                "detail": f"A/B 테스트 완료 — 우승: {test.get('winner', '')} (점수: {test.get('winner_avg_score', '')})",
                "score_before": None,
                "score_after": test.get("winner_avg_score"),
            })

    auto_registry_path = data_dir / "auto_bundles" / "registry.json"
    if auto_registry_path.exists():
        try:
            auto_data = _json.loads(auto_registry_path.read_text(encoding="utf-8"))
            for bundle_id, info in auto_data.items():
                events.append({
                    "timestamp": info.get("created_at", ""),
                    "event_type": "auto_bundle_created",
                    "bundle_id": bundle_id,
                    "detail": f"자동 번들 생성 — {info.get('name_ko', bundle_id)} (신뢰도: {info.get('confidence', '')})",
                    "score_before": None,
                    "score_after": None,
                })
        except Exception:
            pass

    events.sort(key=lambda x: x["timestamp"], reverse=True)
    return events


@router.get("/score-history/{bundle_id}")
def dashboard_score_history(bundle_id: str, request: Request) -> list[dict]:
    """AI 성능 대시보드 — 특정 번들의 점수 시계열 (최근 50건)."""
    eval_store = request.app.state.eval_store
    prompt_override_store = request.app.state.prompt_override_store

    records = eval_store.get_bundle_history(bundle_id, limit=50)
    overrides = {o["bundle_id"]: o for o in prompt_override_store.list_overrides()}
    has_override = bundle_id in overrides

    result = []
    for r in reversed(records):
        result.append({
            "timestamp": r.timestamp,
            "heuristic_score": r.heuristic_score,
            "llm_score": r.llm_score,
            "had_override": has_override,
            "ab_variant": None,
        })
    return result
