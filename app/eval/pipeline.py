"""pipeline.py — 평가 파이프라인 오케스트레이터.

bundle_eval(휴리스틱)과 llm_judge(LLM 기반)를 통합 실행하고
결과를 EvalStore에 저장합니다.
"""
from __future__ import annotations

import asyncio
import logging
import threading
from datetime import datetime, timezone
from typing import Any

from app.eval.eval_store import EvalRecord, EvalStore

_log = logging.getLogger("decisiondoc.eval.pipeline")


def _run_auto_finetune_trigger(bundle_id: str, tenant_id: str) -> None:
    """Background helper: check data threshold and trigger fine-tuning if met."""
    try:
        from app.services.finetune_orchestrator import FineTuneOrchestrator
        orch = FineTuneOrchestrator()
        asyncio.run(orch.check_and_trigger(bundle_id, tenant_id))
    except Exception as exc:
        _log.warning("[AutoFineTune] check_and_trigger failed (bundle=%s): %s", bundle_id, exc)


def run_eval_pipeline(
    request_id: str,
    bundle_id: str,
    docs: list[dict[str, Any]],
    eval_store: EvalStore,
    *,
    run_llm_judge: bool = False,
    title: str = "",
    goal: str = "",
    context: str = "",
    ab_store: Any | None = None,
    ab_variant: str | None = None,
    finetune_store: Any | None = None,
    ft_system_prompt: str = "",
    ft_output: str = "",
    tenant_id: str = "system",
) -> EvalRecord:
    """번들 생성 결과에 대해 평가 파이프라인 실행.

    Args:
        request_id: 생성 요청 ID
        bundle_id: 번들 ID (예: "tech_decision")
        docs: generation_service가 반환한 docs 리스트
              [{"doc_type": str, "markdown": str}, ...]
        eval_store: 결과를 저장할 EvalStore
        run_llm_judge: True이면 LLM-as-Judge도 실행 (API 호출 비용 있음)
        title: 원본 생성 요청의 제목 (LLM judge context_alignment 평가용)
        goal: 원본 생성 요청의 목표
        context: 원본 생성 요청의 배경/상황
        ab_store: ABTestStore instance (None이면 A/B 기록 건너뜀)
        ab_variant: 이번 생성에 사용된 variant ('variant_a'/'variant_b')
        finetune_store: FineTuneStore instance for Trigger B collection (optional)
        ft_system_prompt: System prompt used for this generation (for fine-tune messages)
        ft_output: Full rendered markdown output (for fine-tune messages)

    Returns:
        저장된 EvalRecord
    """
    heuristic_score = 0.0
    issues: list[str] = []
    doc_scores: dict[str, float] = {}

    # 휴리스틱 평가 (bundle_eval)
    try:
        from app.bundle_catalog.registry import get_bundle_spec
        from app.eval.bundle_eval import evaluate_bundle_docs
        bundle_spec = get_bundle_spec(bundle_id)
        if bundle_spec is not None:
            result = evaluate_bundle_docs(bundle_spec, docs)
            heuristic_score = result.overall_score
            for dr in result.doc_results:
                doc_scores[dr.doc_key] = dr.score
                issues.extend(dr.issues)
    except Exception as e:
        _log.warning("휴리스틱 평가 실패 (무시): %s", e)

    # LLM-as-Judge (선택적)
    llm_score: float | None = None
    llm_feedbacks: list[str] = []
    if run_llm_judge:
        try:
            from app.eval.llm_judge import judge_bundle_docs
            judge_results = judge_bundle_docs(
                docs,
                title=title,
                goal=goal,
                context=context,
            )
            valid = [r for r in judge_results if r.error is None and r.average_score > 0]
            if valid:
                llm_score = round(sum(r.average_score for r in valid) / len(valid), 3)
                llm_feedbacks = [r.brief_feedback for r in valid if r.brief_feedback]
        except Exception as e:
            _log.warning("LLM-as-Judge 실행 실패 (무시): %s", e)

    record = EvalRecord(
        request_id=request_id,
        bundle_id=bundle_id,
        timestamp=datetime.now(timezone.utc).isoformat(),
        heuristic_score=round(heuristic_score, 3),
        llm_score=llm_score,
        issues=issues[:20],       # 최대 20개 저장
        doc_scores=doc_scores,
        llm_feedbacks=llm_feedbacks[:5],  # 최대 5개
    )

    eval_store.append(record)
    _log.info(
        "평가 완료 request_id=%s bundle=%s heuristic=%.3f",
        request_id, bundle_id, heuristic_score,
    )

    # ── Trigger B: high eval score → collect fine-tune record ────────────────
    if finetune_store is not None and ft_system_prompt and ft_output:
        try:
            from app.config import get_finetune_min_score
            min_score = get_finetune_min_score()
            if heuristic_score >= min_score:
                user_content = f"{title}\n목표: {goal}\n컨텍스트: {context}".strip()
                messages = [
                    {"role": "system", "content": ft_system_prompt},
                    {"role": "user", "content": user_content},
                    {"role": "assistant", "content": ft_output},
                ]
                finetune_store.save_record(
                    messages=messages,
                    metadata={
                        "bundle_id": bundle_id,
                        "request_id": request_id,
                        "heuristic_score": round(heuristic_score, 3),
                        "llm_score": llm_score,
                        "user_rating": None,
                        "source": "high_eval_score",
                    },
                )
                _log.info(
                    "[FineTune] Trigger B collected request_id=%s score=%.3f",
                    request_id, heuristic_score,
                )
                # Auto-trigger fine-tuning if threshold is reached
                try:
                    from app.config import get_finetune_auto_threshold
                    stats = finetune_store.get_stats()
                    bundle_count = stats.get("per_bundle_count", {}).get(bundle_id, 0)
                    if bundle_count >= get_finetune_auto_threshold():
                        t = threading.Thread(
                            target=_run_auto_finetune_trigger,
                            args=(bundle_id, tenant_id),
                            daemon=True,
                            name=f"finetune-{bundle_id[:20]}",
                        )
                        t.start()
                        _log.info(
                            "[AutoFineTune] Threshold reached for %s, triggering training",
                            bundle_id,
                        )
                except Exception as auto_exc:
                    _log.warning("[AutoFineTune] Trigger check failed (무시): %s", auto_exc)
        except Exception as exc:
            _log.warning("[FineTune] Trigger B 수집 실패 (무시): %s", exc)

    # A/B 테스트 결과 기록 (ab_store가 연결된 경우)
    if ab_store is not None and ab_variant is not None:
        try:
            ab_store.record_result(
                bundle_id, ab_variant, record.heuristic_score, record.llm_score
            )
            winner = ab_store.evaluate_and_conclude(bundle_id)
            if winner:
                _log.info("[ABTest] Concluded %s: winner=%s", bundle_id, winner)
                # ── Trigger C: A/B winner → collect fine-tune record ─────────
                if (
                    finetune_store is not None
                    and winner == ab_variant
                    and ft_system_prompt
                    and ft_output
                ):
                    try:
                        user_content = f"{title}\n목표: {goal}\n컨텍스트: {context}".strip()
                        messages = [
                            {"role": "system", "content": ft_system_prompt},
                            {"role": "user", "content": user_content},
                            {"role": "assistant", "content": ft_output},
                        ]
                        finetune_store.save_record(
                            messages=messages,
                            metadata={
                                "bundle_id": bundle_id,
                                "request_id": request_id,
                                "heuristic_score": round(heuristic_score, 3),
                                "llm_score": llm_score,
                                "user_rating": None,
                                "source": "ab_test_winner",
                            },
                        )
                        _log.info(
                            "[FineTune] Trigger C collected request_id=%s winner=%s",
                            request_id, winner,
                        )
                    except Exception as exc_c:
                        _log.warning("[FineTune] Trigger C 수집 실패 (무시): %s", exc_c)
        except Exception as exc:
            _log.warning("[ABTest] 결과 기록 실패 (무시): %s", exc)

    return record


def run_eval_in_background(
    request_id: str,
    bundle_id: str,
    docs: list[dict[str, Any]],
    eval_store: EvalStore,
    *,
    title: str = "",
    goal: str = "",
    context: str = "",
    ab_store: Any | None = None,
    ab_variant: str | None = None,
    finetune_store: Any | None = None,
    ft_system_prompt: str = "",
    ft_output: str = "",
) -> None:
    """백그라운드 데몬 스레드에서 평가 파이프라인 실행.

    생성 완료 직후 호출 — 응답 시간에 영향 없음.
    LLM-as-Judge를 자동으로 실행합니다 (API 키 미설정 시 graceful 무시).
    """
    t = threading.Thread(
        target=run_eval_pipeline,
        args=(request_id, bundle_id, docs, eval_store),
        kwargs={
            "run_llm_judge": True,
            "title": title,
            "goal": goal,
            "context": context,
            "ab_store": ab_store,
            "ab_variant": ab_variant,
            "finetune_store": finetune_store,
            "ft_system_prompt": ft_system_prompt,
            "ft_output": ft_output,
        },
        daemon=True,
        name=f"eval-{request_id[:8] if len(request_id) >= 8 else request_id}",
    )
    t.start()
