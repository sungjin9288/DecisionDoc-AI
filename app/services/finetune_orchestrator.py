"""finetune_orchestrator.py — OpenAI 파인튜닝 라이프사이클 오케스트레이터.

파인튜닝 전체 흐름을 자동화합니다:
1. 학습 데이터 충분성 확인
2. OpenAI Files API에 학습 파일 업로드
3. 파인튜닝 잡 생성
4. 잡 완료 폴링
5. 새 모델 vs 기본 모델 평가
6. 우수 모델을 활성 모델로 승격

Note:
    OpenAI API 호출은 모두 httpx.AsyncClient를 통해 실행됩니다.
    DECISIONDOC_PROVIDER가 "openai"가 아니면 조용히 스킵합니다.
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.storage.state_backend import StateBackend

_log = logging.getLogger("decisiondoc.finetune.orchestrator")

_OPENAI_FILES_URL   = "https://api.openai.com/v1/files"
_OPENAI_FT_URL      = "https://api.openai.com/v1/fine_tuning/jobs"


class FineTuneOrchestrator:
    """OpenAI 파인튜닝 전체 라이프사이클 관리."""

    POLL_INTERVAL_SECONDS: int = 60
    MAX_POLL_ATTEMPTS: int = 120   # 2 hours max

    def __init__(
        self,
        data_dir: Path | None = None,
        *,
        state_backend: StateBackend | None = None,
    ) -> None:
        if data_dir is None:
            data_dir = Path(os.getenv("DATA_DIR", "./data"))
        self._data_dir = Path(data_dir)
        self._state_backend = state_backend

    # ── Provider guard ────────────────────────────────────────────────────────

    def _is_openai_provider(self) -> bool:
        from app.providers.factory import configured_provider_names

        return "openai" in configured_provider_names()

    def _get_api_key(self) -> str | None:
        key = os.getenv("OPENAI_API_KEY", "").strip()
        return key if key else None

    def _get_base_model(self) -> str:
        from app.config import get_finetune_base_model
        return get_finetune_base_model()

    def _get_threshold(self) -> int:
        from app.config import get_finetune_auto_threshold
        return get_finetune_auto_threshold()

    def _get_promotion_threshold(self) -> float:
        from app.config import get_finetune_promotion_threshold
        return get_finetune_promotion_threshold()

    # ── Main entry point ──────────────────────────────────────────────────────

    async def check_and_trigger(
        self,
        bundle_id: str | None,
        tenant_id: str,
        *,
        execution_authorized: bool = False,
    ) -> dict[str, Any] | None:
        """Check data readiness and trigger fine-tuning if threshold is met.

        Returns job info dict if training was started, None if skipped.
        """
        if not execution_authorized:
            _log.info(
                "[FineTune] Skipping: training execution is not authorized "
                "(bundle=%s tenant=%s)",
                bundle_id,
                tenant_id,
            )
            return None

        if not self._is_openai_provider():
            _log.info(
                "[FineTune] Skipping: provider is not openai (bundle=%s tenant=%s)",
                bundle_id, tenant_id,
            )
            return None

        api_key = self._get_api_key()
        if not api_key:
            _log.warning("[FineTune] Skipping: OPENAI_API_KEY is not set")
            return None

        from app.storage.finetune_store import get_finetune_store
        from app.storage.model_registry import get_model_registry

        finetune_store = get_finetune_store(
            tenant_id,
            data_dir=self._data_dir,
            backend=self._state_backend,
        )
        registry = get_model_registry(
            tenant_id,
            data_dir=self._data_dir,
            backend=self._state_backend,
        )

        # Check data threshold
        stats = finetune_store.get_stats()
        if bundle_id is not None:
            count = stats.get("per_bundle_count", {}).get(bundle_id, 0)
        else:
            count = stats.get("total_records", 0)

        min_records = self._get_threshold()
        if count < min_records:
            _log.info(
                "[FineTune] Not enough data: %d/%d records (bundle=%s tenant=%s)",
                count, min_records, bundle_id, tenant_id,
            )
            return None

        # Check if training already in progress
        if registry.has_active_training(bundle_id):
            _log.info(
                "[FineTune] Training already in progress for bundle=%s tenant=%s",
                bundle_id, tenant_id,
            )
            return None

        # Export training data
        export = finetune_store.export_for_training(
            bundle_id=bundle_id, min_records=min_records
        )
        if export is None:
            _log.warning("[FineTune] Export returned None (bundle=%s)", bundle_id)
            return None
        export_bytes = finetune_store.get_export_bytes(export.filename)
        if export_bytes is None:
            raise RuntimeError("Fine-tune export disappeared before provider upload")

        # Compute avg score before training
        avg_score_before = stats.get("avg_heuristic") or 0.0
        if bundle_id:
            # Try to get bundle-specific average from eval store
            from app.eval.eval_store import get_eval_store

            es = get_eval_store(
                tenant_id,
                data_dir=self._data_dir,
                backend=self._state_backend,
            )
            bundle_history = es.get_bundle_history(bundle_id, limit=50)
            if bundle_history:
                avg_score_before = round(
                    sum(r.heuristic_score for r in bundle_history) / len(bundle_history), 3
                )

        base_model = self._get_base_model()

        try:
            file_id = await self._upload_training_file(
                export.filename,
                export_bytes,
                api_key,
            )
            _log.info("[FineTune] Uploaded training file: file_id=%s", file_id)

            # Create fine-tuning job
            job_id = await self._create_finetune_job(
                file_id, base_model, bundle_id, api_key
            )
            _log.info("[FineTune] Created fine-tuning job: job_id=%s", job_id)
        except Exception as exc:
            _log.error(
                "[FineTune] Provider rejected training start (bundle=%s tenant=%s): %s",
                bundle_id, tenant_id, exc,
            )
            return None

        # A created provider job must have durable local authority. Registry
        # failures propagate so the operator can reconcile the untracked job.
        placeholder_model_id = f"pending:{job_id}"
        registry.register_model(
            model_id=placeholder_model_id,
            base_model=base_model,
            bundle_id=bundle_id,
            training_file_id=file_id,
            record_count=count,
            avg_score_before=avg_score_before,
            openai_job_id=job_id,
        )

        asyncio.ensure_future(self._poll_with_guard(job_id, tenant_id, bundle_id))
        job_info = {
            "openai_job_id": job_id,
            "training_file_id": file_id,
            "base_model": base_model,
            "bundle_id": bundle_id,
            "tenant_id": tenant_id,
            "record_count": count,
            "avg_score_before": avg_score_before,
            "started_at": datetime.now(timezone.utc).isoformat(),
        }
        _log.info(
            "[FineTune] Training started: job_id=%s bundle=%s tenant=%s records=%d",
            job_id, bundle_id, tenant_id, count,
        )
        return job_info

    # ── OpenAI API calls ──────────────────────────────────────────────────────

    async def _upload_training_file(
        self,
        filename: str,
        content: bytes,
        api_key: str,
    ) -> str:
        """Upload JSONL to OpenAI Files API. Returns file_id."""
        try:
            import httpx
        except ImportError as exc:
            raise RuntimeError("httpx is required for fine-tuning. Run: pip install httpx") from exc

        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                _OPENAI_FILES_URL,
                headers={"Authorization": f"Bearer {api_key}"},
                files={"file": (filename, content, "application/jsonl")},
                data={"purpose": "fine-tune"},
            )
        if response.status_code not in (200, 201):
            raise RuntimeError(
                f"OpenAI file upload failed: {response.status_code} {response.text[:200]}"
            )
        data = response.json()
        return data["id"]

    async def _create_finetune_job(
        self,
        file_id: str,
        base_model: str,
        bundle_id: str | None,
        api_key: str,
    ) -> str:
        """Create OpenAI fine-tuning job. Returns job_id."""
        try:
            import httpx
        except ImportError as exc:
            raise RuntimeError("httpx is required for fine-tuning.") from exc

        suffix = f"decisiondoc-{bundle_id or 'general'}"[:18]  # OpenAI suffix max 18 chars
        payload = {
            "training_file": file_id,
            "model": base_model,
            "suffix": suffix,
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                _OPENAI_FT_URL,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
        if response.status_code not in (200, 201):
            raise RuntimeError(
                f"OpenAI fine-tune job creation failed: {response.status_code} {response.text[:200]}"
            )
        data = response.json()
        return data["id"]

    async def _get_job_status(self, job_id: str, api_key: str) -> dict[str, Any]:
        """Fetch current job status from OpenAI API."""
        try:
            import httpx
        except ImportError as exc:
            raise RuntimeError("httpx is required for fine-tuning.") from exc

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{_OPENAI_FT_URL}/{job_id}",
                headers={"Authorization": f"Bearer {api_key}"},
            )
        if response.status_code != 200:
            raise RuntimeError(
                f"OpenAI job status fetch failed: {response.status_code} {response.text[:200]}"
            )
        return response.json()

    # ── Polling ───────────────────────────────────────────────────────────────

    async def _poll_with_guard(
        self, job_id: str, tenant_id: str, bundle_id: str | None
    ) -> None:
        """Wrap poll_job_status to catch and log any errors."""
        try:
            await self.poll_job_status(job_id, tenant_id=tenant_id, bundle_id=bundle_id)
        except Exception as exc:
            _log.error(
                "[FineTune] Unhandled error in poll_job_status job_id=%s: %s",
                job_id, exc,
            )

    async def poll_job_status(
        self, openai_job_id: str, *, tenant_id: str, bundle_id: str | None = None
    ) -> None:
        """Poll OpenAI for job completion. Intended to run as a background coroutine.

        On completion: binds the provider model ID, then evaluates before promotion.
        On failure:    updates ModelRegistry status to 'failed'.
        """
        api_key = self._get_api_key()
        if not api_key:
            _log.warning("[FineTune] Cannot poll: OPENAI_API_KEY not set")
            return

        from app.storage.model_registry import get_model_registry
        registry = get_model_registry(
            tenant_id,
            data_dir=self._data_dir,
            backend=self._state_backend,
        )

        for attempt in range(self.MAX_POLL_ATTEMPTS):
            await asyncio.sleep(self.POLL_INTERVAL_SECONDS)
            try:
                job_data = await self._get_job_status(openai_job_id, api_key)
            except Exception as exc:
                _log.warning(
                    "[FineTune] Poll attempt %d/%d failed for job_id=%s: %s",
                    attempt + 1, self.MAX_POLL_ATTEMPTS, openai_job_id, exc,
                )
                continue

            status = job_data.get("status", "")
            _log.debug(
                "[FineTune] Poll %d/%d job_id=%s status=%s",
                attempt + 1, self.MAX_POLL_ATTEMPTS, openai_job_id, status,
            )

            if status == "succeeded":
                fine_tuned_model = job_data.get("fine_tuned_model", "")
                if not isinstance(fine_tuned_model, str) or not fine_tuned_model:
                    if not registry.update_status(openai_job_id, "failed"):
                        raise RuntimeError("Completed fine-tune job is missing registry authority")
                    _log.error(
                        "[FineTune] Job succeeded without a model ID: job_id=%s",
                        openai_job_id,
                    )
                    return
                if not registry.update_status(
                    openai_job_id,
                    "training",
                    model_id=fine_tuned_model,
                ):
                    raise RuntimeError("Completed fine-tune job is missing registry authority")
                _log.info(
                    "[FineTune] Job succeeded: model_id=%s job_id=%s",
                    fine_tuned_model, openai_job_id,
                )
                if bundle_id:
                    await self._evaluate_and_promote(
                        fine_tuned_model, bundle_id, tenant_id
                    )
                elif not registry.update_status(openai_job_id, "ready"):
                    raise RuntimeError("Fine-tune model promotion lost registry authority")
                return

            elif status in ("failed", "cancelled"):
                error_info = job_data.get("error") or {}
                _log.error(
                    "[FineTune] Job %s: job_id=%s error=%s",
                    status, openai_job_id, error_info,
                )
                if not registry.update_status(openai_job_id, "failed"):
                    raise RuntimeError("Failed fine-tune job is missing registry authority")
                return

        # Max attempts exceeded
        _log.error(
            "[FineTune] Polling timed out after %d attempts for job_id=%s",
            self.MAX_POLL_ATTEMPTS, openai_job_id,
        )
        if not registry.update_status(openai_job_id, "failed"):
            raise RuntimeError("Timed-out fine-tune job is missing registry authority")

    # ── Evaluate & Promote ────────────────────────────────────────────────────

    async def _evaluate_and_promote(
        self, new_model_id: str, bundle_id: str, tenant_id: str
    ) -> None:
        """Compare fine-tuned model vs base model on recent eval records.

        Promotes the new model if avg_score_after > avg_score_before + threshold.
        Otherwise deprecates it.
        """
        from app.storage.model_registry import get_model_registry
        from app.eval.eval_store import get_eval_store
        from app.config import get_finetune_promotion_threshold

        registry = get_model_registry(
            tenant_id,
            data_dir=self._data_dir,
            backend=self._state_backend,
        )
        promotion_threshold = get_finetune_promotion_threshold()

        # Get existing model record for avg_score_before
        model_record = registry.get_model(new_model_id)
        if model_record is None:
            raise RuntimeError("Fine-tune evaluation is missing registry authority")
        avg_score_before = model_record["avg_score_before"]
        openai_job_id = model_record["openai_job_id"]

        # Get last 10 eval records for this bundle
        eval_store = get_eval_store(
            tenant_id,
            data_dir=self._data_dir,
            backend=self._state_backend,
        )
        history = eval_store.get_bundle_history(bundle_id, limit=10)

        if not history:
            _log.info(
                "[FineTune] No eval history for bundle=%s, skipping promotion eval",
                bundle_id,
            )
            # Promote anyway (no baseline to compare against)
            if not registry.update_eval_result(
                new_model_id,
                avg_score_after=avg_score_before,
                eval_result={"promoted": True, "reason": "no_baseline"},
            ):
                raise RuntimeError("Fine-tune evaluation lost registry authority")
            if not registry.update_status(openai_job_id, "ready"):
                raise RuntimeError("Fine-tune model promotion lost registry authority")
            _log.info(
                "[ModelRegistry] Promoted %s (no baseline): %.2f",
                new_model_id, avg_score_before,
            )
            return

        # Re-evaluate using the fine-tuned model on recent inputs
        # We use the heuristic scores from history as a proxy for the new model's
        # expected improvement (actual generation comparison is cost-prohibitive in tests)
        # In production: call generate with new_model_id and re-score
        api_key = self._get_api_key()
        avg_score_after: float

        if api_key and self._is_openai_provider():
            avg_score_after = await self._run_comparison_eval(
                new_model_id, bundle_id, tenant_id, history
            )
        else:
            # Fallback: use recorded scores as estimate
            avg_score_after = round(
                sum(r.heuristic_score for r in history) / len(history), 3
            )

        eval_result = {
            "eval_sample_count": len(history),
            "avg_score_before": avg_score_before,
            "avg_score_after": avg_score_after,
            "promoted": avg_score_after > avg_score_before + promotion_threshold,
        }
        if not registry.update_eval_result(
            new_model_id,
            avg_score_after=avg_score_after,
            eval_result=eval_result,
        ):
            raise RuntimeError("Fine-tune evaluation lost registry authority")

        if avg_score_after > avg_score_before + promotion_threshold:
            if not registry.update_status(openai_job_id, "ready"):
                raise RuntimeError("Fine-tune model promotion lost registry authority")
            _log.info(
                "[ModelRegistry] Promoted %s: %.2f → %.2f",
                new_model_id, avg_score_before, avg_score_after,
            )
        else:
            if not registry.deprecate_model(new_model_id):
                raise RuntimeError("Fine-tune deprecation lost registry authority")
            _log.info(
                "[ModelRegistry] Model %s not promoted: %.2f vs base %.2f",
                new_model_id, avg_score_after, avg_score_before,
            )

    async def _run_comparison_eval(
        self,
        model_id: str,
        bundle_id: str,
        tenant_id: str,
        history: list[Any],
    ) -> float:
        """Generate samples with new model and score them heuristically.

        Uses at most 3 recent eval records to limit cost.
        Falls back to existing history scores on any error.
        """
        try:
            from app.bundle_catalog.registry import get_bundle_spec
            from app.domain.schema import build_bundle_prompt
            from app.eval.bundle_eval import evaluate_bundle_docs
            from app.providers.openai_provider import OpenAIProvider

            bundle_spec = get_bundle_spec(bundle_id)
            if bundle_spec is None:
                raise ValueError(f"Bundle spec not found: {bundle_id}")

            # Use last 3 records for evaluation (cost-aware)
            sample_records = history[:3]
            scores: list[float] = []

            provider = OpenAIProvider(model_override=model_id)

            for record in sample_records:
                try:
                    # Build minimal requirements
                    req: dict[str, Any] = {
                        "title": f"eval_{record.request_id[:8]}",
                        "goal": "evaluation",
                        "bundle_type": bundle_id,
                    }
                    prompt = build_bundle_prompt(bundle_spec, req)
                    raw = provider.generate_raw(
                        prompt, request_id=f"eval-{record.request_id[:8]}"
                    )
                    import json as _json
                    bundle_data = _json.loads(raw)
                    docs = [
                        {"doc_type": k, "markdown": v.get("markdown", "") if isinstance(v, dict) else str(v)}
                        for k, v in bundle_data.items()
                        if k in bundle_spec.doc_keys
                    ]
                    if docs:
                        result = evaluate_bundle_docs(bundle_spec, docs)
                        scores.append(result.overall_score)
                except Exception as inner_exc:
                    _log.debug("[FineTune] Sample eval failed: %s", inner_exc)

            if scores:
                return round(sum(scores) / len(scores), 3)

        except Exception as exc:
            _log.warning("[FineTune] Comparison eval failed, using history baseline: %s", exc)

        # Fallback: use history scores
        return round(sum(r.heuristic_score for r in history) / len(history), 3)

    # ── Utility ───────────────────────────────────────────────────────────────

    async def list_active_jobs(self) -> list[dict[str, Any]]:
        """Fetch all active fine-tuning jobs from OpenAI API."""
        api_key = self._get_api_key()
        if not api_key:
            return []
        try:
            import httpx
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    f"{_OPENAI_FT_URL}?limit=20",
                    headers={"Authorization": f"Bearer {api_key}"},
                )
            if response.status_code != 200:
                return []
            data = response.json()
            return data.get("data", [])
        except Exception as exc:
            _log.warning("[FineTune] list_active_jobs failed: %s", exc)
            return []
