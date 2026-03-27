"""report.py — 평가 결과 집계 리포트 생성."""
from __future__ import annotations

from typing import Any

from app.eval.eval_store import EvalStore


def generate_report(eval_store: EvalStore) -> dict[str, Any]:
    """평가 결과 집계 리포트 생성.

    Returns:
        status, total_evaluated, avg_heuristic_score, quality_grade,
        by_bundle, needs_improvement, high_quality_bundles, recommendations 포함 딕셔너리
    """
    summary = eval_store.summary()

    if summary["total"] == 0:
        return {
            "status": "데이터 없음",
            "message": "아직 평가된 문서가 없습니다. 문서를 생성하면 자동으로 평가됩니다.",
            "total_evaluated": 0,
        }

    by_bundle = summary.get("by_bundle", {})

    # 개선 필요 번들 (평균 0.7 미만)
    needs_improvement = [
        {"bundle_id": bid, **stats}
        for bid, stats in by_bundle.items()
        if stats["avg"] < 0.7
    ]
    needs_improvement.sort(key=lambda x: x["avg"])

    # 우수 번들 (평균 0.85 이상)
    high_quality = [
        {"bundle_id": bid, **stats}
        for bid, stats in by_bundle.items()
        if stats["avg"] >= 0.85
    ]

    return {
        "status": "정상",
        "total_evaluated": summary["total"],
        "avg_heuristic_score": summary["avg_heuristic"],
        "quality_grade": _grade(summary["avg_heuristic"]),
        "by_bundle": by_bundle,
        "needs_improvement": needs_improvement,
        "high_quality_bundles": high_quality,
        "recent_10": summary.get("recent", []),
        "recommendations": _make_recommendations(needs_improvement),
    }


def _grade(score: float | None) -> str:
    """품질 점수를 등급 문자열로 변환."""
    if score is None:
        return "N/A"
    if score >= 0.9:
        return "A (우수)"
    if score >= 0.8:
        return "B (양호)"
    if score >= 0.7:
        return "C (보통)"
    if score >= 0.6:
        return "D (개선 필요)"
    return "F (불량)"


def _make_recommendations(needs_improvement: list[dict]) -> list[str]:
    """개선 권고사항 생성."""
    if not needs_improvement:
        return ["모든 번들이 기준 품질(0.7 이상)을 충족하고 있습니다."]
    recs = []
    for item in needs_improvement[:3]:
        bid = item["bundle_id"]
        avg = item["avg"]
        recs.append(
            f"'{bid}' 번들 평균 점수 {avg:.0%} — "
            "프롬프트 힌트 강화 또는 골든 예시 추가를 권장합니다."
        )
    return recs
