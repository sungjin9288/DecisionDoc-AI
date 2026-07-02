"""Core init and top-level ``generate_documents`` orchestration mixin."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable
from uuid import uuid4

from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.bundle_catalog.registry import get_bundle_spec
from app.config import env_is_enabled
from app.domain.schema import SCHEMA_VERSION
from app.eval.lints import lint_docs
from app.observability.timing import Timer
from app.providers.base import Provider
from app.schemas import GenerateRequest
from app.services.generation.context_store import (
    _eval_done_callback,
    _eval_executor,
    _generation_context,
    _log,
    _record_usage_sync,
    _store_generation_context,
)
from app.services.generation.errors import EvalLintFailedError
from app.services.markdown_utils import (
    build_markdown_kv_table,
    build_markdown_table,
    build_slide_outline_table,
)
from app.services.validator import validate_docs
from app.storage.base import Storage

if TYPE_CHECKING:
    from app.storage.feedback_store import FeedbackStore
    from app.storage.finetune_store import FineTuneStore


class GenerationCoreMixin:
    """``__init__`` plus the ``generate_documents`` pipeline entrypoint."""

    def __init__(
        self,
        provider_factory: Callable[[], Provider],
        template_dir: Path,
        data_dir: Path,
        storage: Storage | None = None,
        procurement_store: Any | None = None,
        decision_council_store: Any | None = None,
        procurement_copilot_enabled: bool = False,
        feedback_store: FeedbackStore | None = None,
        eval_store: Any | None = None,
        search_service: Any | None = None,
        finetune_store: "FineTuneStore | None" = None,
    ) -> None:
        self.provider_factory = provider_factory
        self.feedback_store = feedback_store
        self._eval_store = eval_store
        self._search_service = search_service
        self._procurement_store = procurement_store
        self._decision_council_store = decision_council_store
        self._procurement_copilot_enabled = procurement_copilot_enabled
        self._finetune_store = finetune_store
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.cache_dir = self.data_dir / "cache"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.storage = storage
        self.env = Environment(
            loader=FileSystemLoader(str(template_dir)),
            autoescape=select_autoescape(
                enabled_extensions=("html", "htm", "xml"),
                default_for_string=False,
                default=False,
            ),
            trim_blocks=True,
            lstrip_blocks=True,
        )
        self.env.filters["markdown_table"] = build_markdown_table
        self.env.filters["markdown_kv_table"] = build_markdown_kv_table
        self.env.filters["slide_outline_table"] = build_slide_outline_table

    def generate_documents(self, requirements: GenerateRequest, *, request_id: str, tenant_id: str = "system") -> dict[str, Any]:
        bundle_id = str(uuid4())
        payload = requirements.model_dump(mode="json")

        # Seed thread-local context so it's available after generation.
        _generation_context.request_id = request_id
        _generation_context.title = payload.get("title", "")
        _generation_context.goal = payload.get("goal", "")
        _generation_context.context_text = payload.get("context", "")
        _generation_context.bundle_type = payload.get("bundle_type", "tech_decision") or "tech_decision"
        _generation_context.system_prompt = ""
        _generation_context.output = ""

        # Set current tenant for multi-tenant store isolation
        try:
            from app.domain.schema import _current_tenant_id
            _current_tenant_id.value = tenant_id
        except Exception:
            pass

        # Resolve bundle spec (defaults to tech_decision for backward compatibility).
        bundle_type = payload.get("bundle_type", "tech_decision") or "tech_decision"
        bundle_spec = get_bundle_spec(bundle_type)

        variant_key = os.getenv("DECISIONDOC_PROMPT_VARIANT", "")
        if variant_key:
            bundle_spec = self._apply_prompt_variant(bundle_spec, variant_key)

        self._inject_project_contexts(
            payload,
            bundle_type=bundle_type,
            tenant_id=tenant_id,
            request_id=request_id,
        )
        procurement_handoff_used = bool(payload.get("_procurement_context"))
        decision_council_handoff_used = bool(payload.get("_decision_council_context"))
        decision_council_handoff_skipped_reason = (
            str(payload.get("_decision_council_handoff_skipped_reason") or "").strip() or None
        )
        decision_council_session_id = str(payload.get("_decision_council_session_id") or "").strip() or None
        decision_council_session_revision = payload.get("_decision_council_session_revision")
        decision_council_direction = str(payload.get("_decision_council_direction") or "").strip() or None
        decision_council_use_case = str(payload.get("_decision_council_use_case") or "").strip() or None
        decision_council_target_bundle = str(payload.get("_decision_council_target_bundle") or "").strip() or None
        decision_council_applied_bundle = str(payload.get("_decision_council_applied_bundle") or "").strip() or None

        provider = self._safe_get_provider(bundle_type=bundle_type, tenant_id=tenant_id)
        timer = Timer()
        cache_enabled = env_is_enabled("DECISIONDOC_CACHE_ENABLED")
        cache_hit = False

        bundle: dict[str, Any]
        cache_path = self._cache_path(provider.name, SCHEMA_VERSION, payload)
        if cache_enabled and cache_path.exists() and self._is_cache_fresh(cache_path):
            cached = self._try_read_cache(cache_path)
            if cached is not None:
                bundle = cached
                cache_hit = True
                self._validate_bundle_schema(bundle, bundle_spec)
            else:
                # Cache file is corrupt or unreadable — remove it before re-generating.
                try:
                    cache_path.unlink()
                except OSError:
                    pass
                bundle = self._call_and_prepare_bundle(provider, payload, request_id, timer, bundle_spec)
                self._write_cache_atomic(cache_path, bundle)
        else:
            # Inject web search context if available
            if self._search_service is not None and self._search_service.is_available():
                query_parts = [
                    str(payload.get("title", "")),
                    str(payload.get("goal", "")),
                    str(payload.get("industry", "")),
                ]
                query = " ".join(p for p in query_parts if p).strip()
                if query:
                    search_results = self._search_service.search(query, num=5)
                    if search_results:
                        snippets = "\n".join(
                            f"{i+1}. [{r.title}] {r.snippet}"
                            for i, r in enumerate(search_results[:5])
                        )
                        payload["_search_context"] = snippets

            bundle = self._call_and_prepare_bundle(provider, payload, request_id, timer, bundle_spec)
            if cache_enabled:
                self._write_cache_atomic(cache_path, bundle)

        if self.storage is not None:
            self.storage.save_bundle(bundle_id, bundle)
        with timer.measure("render_ms"):
            docs = self._render_docs(payload, bundle, bundle_spec)
        with timer.measure("lints_ms"):
            lint_errors = lint_docs(
                {doc["doc_type"]: doc["markdown"] for doc in docs},
                lint_headings_override=bundle_spec.lint_headings_map(),
                critical_headings_override=bundle_spec.critical_non_empty_headings_map(),
            )
        if lint_errors:
            raise EvalLintFailedError(lint_errors)
        with timer.measure("validator_ms"):
            validate_docs(docs, headings_override=bundle_spec.validator_headings_map())
        usage_tokens = provider.consume_usage_tokens() if not cache_hit else None

        # ── Capture generation context for fine-tune collection ──────────────
        # system_prompt was captured in thread-local by build_bundle_prompt().
        # Collect it now (before spawning background thread) to avoid data races.
        ft_system_prompt = ""
        if not cache_hit:
            try:
                from app.domain.schema import _ft_last_prompt
                ft_system_prompt = getattr(_ft_last_prompt, "prompt", "") or ""
            except Exception:
                pass
        ft_output = "\n\n".join(doc.get("markdown", "") for doc in docs).strip()

        # Store cross-request context snapshot (used by /feedback → Trigger A).
        _store_generation_context(request_id, {
            "request_id": request_id,
            "bundle_type": bundle_type,
            "title": payload.get("title", ""),
            "goal": payload.get("goal", ""),
            "context_text": payload.get("context", ""),
            "system_prompt": ft_system_prompt,
            "output": ft_output,
        })

        # 백그라운드 품질 평가 (EvalStore가 연결된 경우)
        if self._eval_store is not None:
            # A/B variant selected during prompt building (set by _inject_prompt_override)
            # Only available on cache miss (cache hits don't call build_bundle_prompt)
            ab_variant: str | None = None
            ab_store_instance: Any | None = None
            if not cache_hit:
                try:
                    from app.domain.schema import _ab_selected
                    sel_variant = getattr(_ab_selected, "variant", None)
                    sel_bundle_id = getattr(_ab_selected, "bundle_id", None)
                    if sel_variant and sel_bundle_id == bundle_type:
                        ab_variant = sel_variant
                        from app.storage.ab_test_store import ABTestStore
                        ab_store_instance = ABTestStore(self.data_dir)
                except Exception:
                    pass

            # Use tenant-scoped eval store for isolation
            try:
                from app.eval.eval_store import get_eval_store
                active_eval_store = get_eval_store(tenant_id)
            except Exception:
                active_eval_store = self._eval_store

            from app.eval.pipeline import run_eval_pipeline
            try:
                _future = _eval_executor.submit(
                    run_eval_pipeline,
                    request_id,
                    bundle_type,
                    docs,
                    active_eval_store,
                    title=payload.get("title", ""),
                    goal=payload.get("goal", ""),
                    context=payload.get("context", ""),
                    ab_store=ab_store_instance,
                    ab_variant=ab_variant,
                    finetune_store=self._finetune_store,
                    ft_system_prompt=ft_system_prompt,
                    ft_output=ft_output,
                    tenant_id=tenant_id,
                )
                _future.add_done_callback(_eval_done_callback)
            except RuntimeError as exc:
                _log.warning(
                    "[Eval] Background eval skipped because executor is unavailable: %s",
                    exc,
                )

        # Record usage (fire-and-forget — don't fail generation on billing errors)
        try:
            _tokens = usage_tokens or {}
            _user_id = payload.get("user_id", "") or ""
            _record_usage_sync(
                tenant_id=tenant_id,
                user_id=_user_id,
                bundle_id=bundle_type,
                request_id=request_id,
                model=provider.name,
                tokens_input=_tokens.get("prompt_tokens", 0) or 0,
                tokens_output=_tokens.get("output_tokens", 0) or 0,
            )
        except Exception:
            pass

        return {
            "docs": docs,
            "raw_bundle": bundle,
            "metadata": {
                "provider": provider.name,
                "schema_version": SCHEMA_VERSION,
                "cache_hit": cache_hit if cache_enabled else None,
                "request_id": request_id,
                "bundle_id": bundle_id,
                "bundle_type": bundle_type,
                "project_id": payload.get("project_id"),
                "doc_count": len(docs),
                "procurement_handoff_used": procurement_handoff_used,
                "decision_council_handoff_used": decision_council_handoff_used,
                "decision_council_handoff_skipped_reason": decision_council_handoff_skipped_reason,
                "decision_council_session_id": decision_council_session_id,
                "decision_council_session_revision": decision_council_session_revision,
                "decision_council_direction": decision_council_direction,
                "decision_council_use_case": decision_council_use_case,
                "decision_council_target_bundle": decision_council_target_bundle,
                "decision_council_applied_bundle": decision_council_applied_bundle,
                "timings_ms": timer.durations_ms,
                "llm_prompt_tokens": (usage_tokens or {}).get("prompt_tokens"),
                "llm_output_tokens": (usage_tokens or {}).get("output_tokens"),
                "llm_total_tokens": (usage_tokens or {}).get("total_tokens"),
                "applied_references": payload.get("_knowledge_ranked_documents", [])[:3],
            },
        }
