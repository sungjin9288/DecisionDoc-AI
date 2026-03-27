from __future__ import annotations

import concurrent.futures
import hashlib
import json
import logging
import os
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable
from uuid import uuid4

from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.bundle_catalog.registry import get_bundle_spec
from app.bundle_catalog.spec import BundleSpec
from app.config import env_is_enabled
from app.domain.schema import SCHEMA_VERSION
from app.eval.lints import lint_docs
from app.observability.timing import Timer
from app.providers.base import Provider
from app.providers.stabilizer import stabilize_bundle, strip_internal_bundle_fields
from app.schemas import GenerateRequest
from app.storage.base import Storage
from app.services.validator import validate_docs

if TYPE_CHECKING:
    from app.storage.feedback_store import FeedbackStore
    from app.storage.finetune_store import FineTuneStore

_log = logging.getLogger("decisiondoc.generate")


def _record_usage_sync(
    tenant_id: str,
    user_id: str,
    bundle_id: str,
    request_id: str,
    model: str,
    tokens_input: int,
    tokens_output: int,
) -> None:
    """Record a usage event to the billing/metering store (fire-and-forget)."""
    from app.storage.usage_store import UsageStore, UsageEvent
    from app.storage.billing_store import get_billing_store
    import uuid as _uuid
    from datetime import datetime as _datetime, timezone as _timezone

    plan = get_billing_store(tenant_id).get_plan(tenant_id)
    tokens_total = tokens_input + tokens_output
    cost = (tokens_total / 1000) * plan.price_per_1k_tokens if tokens_total > 0 else 0.0

    event = UsageEvent(
        event_id=str(_uuid.uuid4()),
        tenant_id=tenant_id,
        user_id=user_id,
        timestamp=_datetime.now(_timezone.utc).isoformat(),
        event_type="doc.generate",
        bundle_id=bundle_id,
        tokens_input=tokens_input,
        tokens_output=tokens_output,
        tokens_total=tokens_total,
        cost_usd=cost,
        model=model,
        request_id=request_id,
    )
    UsageStore().record(event)


# ── Fine-tune context capture ─────────────────────────────────────────────────
# Thread-local for capturing generation context within a single request.
_generation_context: threading.local = threading.local()

# In-memory cross-request context cache: request_id → (context dict, timestamp).
# Used by the /feedback endpoint (a separate request) to find the original
# system_prompt + output for Trigger A fine-tune collection.
_ctx_lock: threading.Lock = threading.Lock()
_recent_generation_contexts: dict[str, tuple[dict, float]] = {}
_CTX_MAX_SIZE = 500   # evict oldest entries beyond this limit
_CTX_TTL_SECONDS = 3600  # 1 hour — stale entries expire regardless of size


def _store_generation_context(request_id: str, ctx: dict) -> None:
    """Store ctx with timestamp; evict expired + oldest-over-limit entries."""
    with _ctx_lock:
        now = time.time()
        # Purge expired entries first
        expired = [k for k, (_, ts) in _recent_generation_contexts.items()
                   if now - ts > _CTX_TTL_SECONDS]
        for k in expired:
            del _recent_generation_contexts[k]
        # Evict oldest if still at capacity
        if len(_recent_generation_contexts) >= _CTX_MAX_SIZE:
            oldest = min(_recent_generation_contexts.items(), key=lambda x: x[1][1])
            del _recent_generation_contexts[oldest[0]]
        _recent_generation_contexts[request_id] = (ctx, now)


def get_generation_context(request_id: str) -> dict | None:
    """Return stored generation context for a request_id, or None if missing/expired."""
    with _ctx_lock:
        entry = _recent_generation_contexts.get(request_id)
        if entry is None:
            return None
        ctx, ts = entry
        if time.time() - ts > _CTX_TTL_SECONDS:
            del _recent_generation_contexts[request_id]
            return None
        return ctx


# ── Background eval executor ──────────────────────────────────────────────────
# Bounded thread pool for background quality eval tasks.
# Use shutdown(wait=True) during FastAPI lifespan to drain in-flight tasks.
_eval_executor: concurrent.futures.ThreadPoolExecutor = (
    concurrent.futures.ThreadPoolExecutor(max_workers=4, thread_name_prefix="eval")
)


def _eval_done_callback(future: concurrent.futures.Future) -> None:  # type: ignore[type-arg]
    """Log any unhandled exception from a background eval task."""
    exc = future.exception()
    if exc is not None:
        _log.error("[Eval] Background eval task raised an exception: %s", exc, exc_info=exc)


class ProviderFailedError(Exception):
    pass


class EvalLintFailedError(Exception):
    def __init__(self, errors: list[str]) -> None:
        super().__init__("Eval lint failed.")
        self.errors = errors


class BundleNotSupportedError(Exception):
    """Raised when a requested operation does not support the given bundle_type."""

    def __init__(self, bundle_type: str, operation: str) -> None:
        super().__init__(f"Bundle '{bundle_type}' is not supported for '{operation}'.")
        self.bundle_type = bundle_type
        self.operation = operation


class GenerationService:
    _PROCUREMENT_HANDOFF_BUNDLE_IDS = {
        "bid_decision_kr",
        "rfp_analysis_kr",
        "proposal_kr",
        "performance_plan_kr",
    }

    def __init__(
        self,
        provider_factory: Callable[[], Provider],
        template_dir: Path,
        data_dir: Path,
        storage: Storage | None = None,
        procurement_store: Any | None = None,
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
                "doc_count": len(docs),
                "timings_ms": timer.durations_ms,
                "llm_prompt_tokens": (usage_tokens or {}).get("prompt_tokens"),
                "llm_output_tokens": (usage_tokens or {}).get("output_tokens"),
                "llm_total_tokens": (usage_tokens or {}).get("total_tokens"),
            },
        }

    def _render_docs(
        self,
        payload: dict[str, Any],
        bundle: dict[str, Any],
        bundle_spec: BundleSpec,
    ) -> list[dict[str, str]]:
        """Render each document in the bundle using its Jinja2 template.

        For the ``tech_decision`` bundle (backward compat), the ``doc_types``
        field in the payload determines which docs to render.  For all other
        bundles every doc in the bundle spec is rendered.
        """
        bundle_type = payload.get("bundle_type", "tech_decision") or "tech_decision"
        if bundle_type == "tech_decision":
            # Honor the legacy doc_types filter.
            doc_keys = [
                dt if isinstance(dt, str) else dt.value
                for dt in payload.get("doc_types", bundle_spec.doc_keys)
            ]
        else:
            doc_keys = bundle_spec.doc_keys

        docs: list[dict[str, str]] = []
        for doc_key in doc_keys:
            doc_spec = bundle_spec.get_doc(doc_key)
            if doc_spec is None:
                continue  # skip unknown keys gracefully
            context = {
                "title": payload["title"],
                "goal": payload["goal"],
                "context": payload.get("context", ""),
                "procurement_context": payload.get("_procurement_context", ""),
                "constraints": payload.get("constraints", ""),
                "priority": payload.get("priority", ""),
                "audience": payload.get("audience", ""),
                **bundle.get(doc_key, {}),
            }
            markdown = self.env.get_template(doc_spec.template_file).render(**context).strip() + "\n"
            docs.append({"doc_type": doc_key, "markdown": markdown})
        return docs

    def _validate_bundle_schema(self, bundle: Any, bundle_spec: BundleSpec) -> None:
        if not isinstance(bundle, dict):
            raise ProviderFailedError(
                f"Provider returned invalid bundle: expected dict, got {type(bundle).__name__}"
            )

        schema = bundle_spec.json_schema
        required_top = schema["required"]
        properties = schema["properties"]
        for key in required_top:
            if key not in bundle:
                raise ProviderFailedError(
                    f"Provider returned invalid bundle: missing top-level key '{key}'"
                )
            if not isinstance(bundle[key], dict):
                raise ProviderFailedError(
                    f"Provider returned invalid bundle: '{key}' must be a dict, got {type(bundle[key]).__name__}"
                )
            required_fields = properties[key]["required"]
            for field in required_fields:
                if field not in bundle[key]:
                    raise ProviderFailedError(
                        f"Provider returned invalid bundle: missing field '{key}.{field}'"
                    )
                value = bundle[key][field]
                field_schema = properties[key]["properties"][field]
                expected_type = field_schema["type"]
                if expected_type == "string" and not isinstance(value, str):
                    raise ProviderFailedError(
                        f"Provider returned invalid bundle: '{key}.{field}' must be a string, got {type(value).__name__}"
                    )
                if expected_type == "integer" and not isinstance(value, int):
                    raise ProviderFailedError(
                        f"Provider returned invalid bundle: '{key}.{field}' must be an integer, got {type(value).__name__}"
                    )
                if expected_type == "array":
                    if not isinstance(value, list):
                        raise ProviderFailedError(
                            f"Provider returned invalid bundle: '{key}.{field}' must be an array, got {type(value).__name__}"
                        )
                    # Only validate items as strings when the schema declares items.type == "string".
                    # Arrays of objects (e.g. slide_outline) are accepted as-is.
                    items_type = field_schema.get("items", {}).get("type")
                    if items_type == "string":
                        for i, item in enumerate(value):
                            if not isinstance(item, str):
                                raise ProviderFailedError(
                                    f"Provider returned invalid bundle: '{key}.{field}[{i}]' must be a string, got {type(item).__name__}"
                                )

    def _is_cache_fresh(self, cache_path: Path) -> bool:
        """Return True if the cache file is within the configured TTL.

        TTL is controlled by DECISIONDOC_CACHE_TTL_HOURS (default 24).
        Set to 0 for permanent cache (no expiry).
        """
        ttl_hours = int(os.getenv("DECISIONDOC_CACHE_TTL_HOURS", "24"))
        if ttl_hours <= 0:
            return True  # 0 → permanent cache
        age_hours = (time.time() - cache_path.stat().st_mtime) / 3600
        return age_hours < ttl_hours

    def _cache_path(self, provider_name: str, schema_version: str, payload: dict[str, Any]) -> Path:
        canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        key = f"{provider_name}:{schema_version}:{canonical}"
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
        return self.cache_dir / f"{digest}.json"

    def _call_and_prepare_bundle(
        self,
        provider: Provider,
        payload: dict[str, Any],
        request_id: str,
        timer: Timer,
        bundle_spec: BundleSpec,
    ) -> dict[str, Any]:
        """Call the provider, stabilize, strip internal fields, and validate schema."""
        with timer.measure("provider_ms"):
            bundle = self._call_provider_with_retry(provider, payload, request_id, bundle_spec)
        bundle = stabilize_bundle(bundle, structure=bundle_spec.stabilizer_structure())
        bundle = strip_internal_bundle_fields(bundle)
        self._validate_bundle_schema(bundle, bundle_spec)
        return bundle

    def _apply_prompt_variant(self, bundle_spec: BundleSpec, variant_key: str | None) -> BundleSpec:
        """Apply a prompt variant if specified. Returns modified BundleSpec or original."""
        if not variant_key:
            return bundle_spec
        variant_prompt = bundle_spec.prompt_variants.get(variant_key)
        if not variant_prompt:
            return bundle_spec
        import dataclasses
        return dataclasses.replace(bundle_spec, prompt_hint=variant_prompt)

    def _inject_project_contexts(
        self,
        payload: dict[str, Any],
        *,
        bundle_type: str,
        tenant_id: str,
        request_id: str,
    ) -> None:
        project_id = payload.get("project_id")
        if not project_id:
            return

        try:
            from app.storage.knowledge_store import KnowledgeStore

            ks = KnowledgeStore(project_id)
            knowledge_ctx = ks.build_context()
            style_ctx = ks.build_style_context()
            if knowledge_ctx:
                payload["_knowledge_context"] = knowledge_ctx
                _log.info(
                    "[Knowledge] Injected context for project=%s len=%d request_id=%s",
                    project_id,
                    len(knowledge_ctx),
                    request_id,
                )
            if style_ctx:
                payload["_style_context"] = style_ctx
        except Exception as exc:
            _log.warning("[Knowledge] Failed to load context project=%s: %s", project_id, exc)

        if (
            not self._procurement_copilot_enabled
            or bundle_type not in self._PROCUREMENT_HANDOFF_BUNDLE_IDS
            or self._procurement_store is None
        ):
            return

        procurement_ctx = self._build_procurement_context(project_id=project_id, tenant_id=tenant_id)
        if procurement_ctx:
            payload["_procurement_context"] = procurement_ctx
            _log.info(
                "[Procurement] Injected handoff context project=%s bundle=%s len=%d request_id=%s",
                project_id,
                bundle_type,
                len(procurement_ctx),
                request_id,
            )

    def _build_procurement_context(self, *, project_id: str, tenant_id: str) -> str:
        record = self._procurement_store.get(project_id, tenant_id=tenant_id)
        if record is None:
            return ""

        opportunity = record.opportunity
        recommendation = record.recommendation
        lines: list[str] = [
            "프로젝트 공공조달 의사결정 상태입니다. 아래 structured state를 문서 작성의 source of truth로 사용하세요.",
        ]
        if opportunity is not None:
            lines.extend(
                [
                    f"- 공고명: {opportunity.title}",
                    f"- 발주기관: {opportunity.issuer or '미상'}",
                    f"- 예산: {opportunity.budget or '미확인'}",
                    f"- 마감: {opportunity.deadline or '미확인'}",
                    f"- 입찰방식: {opportunity.bid_type or '미확인'}",
                    f"- 카테고리: {opportunity.category or '미확인'}",
                ]
            )
            if opportunity.source_url:
                lines.append(f"- 원문 URL: {opportunity.source_url}")

        if recommendation is not None:
            lines.extend(
                [
                    f"- 현재 추천 결론: {recommendation.value}",
                    f"- 추천 요약: {recommendation.summary or '요약 없음'}",
                ]
            )

        if record.hard_filters:
            lines.append("Hard filter 결과:")
            for item in record.hard_filters[:8]:
                blocking = " / blocking" if item.blocking else ""
                reason = f" / {item.reason}" if item.reason else ""
                lines.append(f"- {item.label}: {item.status}{blocking}{reason}")

        if record.soft_fit_score is not None:
            lines.append(
                f"- Soft-fit score: {record.soft_fit_score:.1f} ({record.soft_fit_status})"
            )
        elif record.soft_fit_status:
            lines.append(f"- Soft-fit score status: {record.soft_fit_status}")

        if record.missing_data:
            lines.append("확인되지 않은 데이터:")
            for item in record.missing_data[:8]:
                lines.append(f"- {item}")

        actionable_checklist = [
            item for item in record.checklist_items if item.status in {"blocked", "action_needed"}
        ]
        if actionable_checklist:
            lines.append("입찰 준비 체크리스트 중 조치 필요 항목:")
            for item in actionable_checklist[:10]:
                owner = f" / owner={item.owner}" if item.owner else ""
                due = f" / due={item.due_date}" if item.due_date else ""
                remediation = f" / {item.remediation_note}" if item.remediation_note else ""
                lines.append(
                    f"- [{item.category}] {item.title}: {item.status}, severity={item.severity}"
                    f"{owner}{due}{remediation}"
                )

        if record.score_breakdown:
            lines.append("Soft-fit factor breakdown:")
            for item in record.score_breakdown[:8]:
                lines.append(
                    f"- {item.label}: score={item.score:.1f}, weight={item.weight:.2f}, "
                    f"weighted={item.weighted_score:.1f}, status={item.status}"
                )

        if record.capability_profile is not None:
            lines.extend(
                [
                    f"- capability_profile.source_ref: {record.capability_profile.source_ref}",
                    f"- capability_profile.summary: {record.capability_profile.summary or '요약 없음'}",
                ]
            )

        latest_snapshot = record.source_snapshots[-1] if record.source_snapshots else None
        if latest_snapshot is not None:
            payload = self._procurement_store.load_source_snapshot(
                tenant_id=tenant_id,
                project_id=project_id,
                snapshot_id=latest_snapshot.snapshot_id,
            )
            if isinstance(payload, dict):
                extracted_fields = payload.get("extracted_fields") or {}
                structured_context = str(payload.get("structured_context") or "").strip()
                if extracted_fields:
                    lines.append("최신 원문 추출 신호:")
                    for key, value in list(extracted_fields.items())[:12]:
                        rendered = json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value)
                        lines.append(f"- {key}: {rendered[:240]}")
                if structured_context:
                    lines.append("최신 원문/구조화 맥락 요약:")
                    lines.append(structured_context[:2000])

        return "\n".join(lines).strip()

    def _build_feedback_hints(self, bundle_type: str, title: str = "") -> str:
        """Build structured few-shot hints from high-rated feedback examples.

        Returns a formatted string injected into the LLM prompt.
        Each example includes: title, rating, user comment, and per-doc
        section heading + first 800 chars for all doc types.
        """
        # Resolve tenant-scoped feedback store if available
        try:
            from app.domain.schema import _current_tenant_id
            from app.storage.feedback_store import get_feedback_store
            tid = getattr(_current_tenant_id, "value", "system") or "system"
            feedback_store = get_feedback_store(tid)
        except Exception:
            feedback_store = self.feedback_store
        if not feedback_store:
            return ""
        try:
            examples = feedback_store.get_high_rated_examples(
                bundle_type=bundle_type,
                min_rating=4,
                limit=3,
                doc_content_limit=800,
            )
        except Exception:
            return ""

        if not examples:
            return ""

        blocks: list[str] = ["## 참고: 이전 고품질 생성 예시"]
        for i, ex in enumerate(examples, 1):
            ex_title = ex.get("title") or "(제목 없음)"
            rating = ex.get("rating", 0)
            comment = ex.get("comment", "")
            header = f"\n### 예시 {i} — 제목: {ex_title}  (평점: {rating}/5)"
            if comment:
                header += f"\n사용자 피드백: {comment}"
            blocks.append(header)

            docs: dict = ex.get("docs") or {}
            for doc_type, doc_info in docs.items():
                if not isinstance(doc_info, dict):
                    continue
                heading = doc_info.get("heading") or doc_type
                content = doc_info.get("content", "").strip()
                if not content:
                    continue
                blocks.append(
                    f"\n#### [{doc_type}] {heading}\n```\n{content}\n```"
                )

        if len(blocks) == 1:
            return ""
        return "\n".join(blocks)

    def _call_provider_once(
        self,
        provider: Provider,
        payload: dict[str, Any],
        request_id: str,
        bundle_spec: BundleSpec,
    ) -> dict[str, Any]:
        feedback_hints = self._build_feedback_hints(bundle_spec.id, title=payload.get("title", ""))
        try:
            return provider.generate_bundle(
                payload,
                schema_version=SCHEMA_VERSION,
                request_id=request_id,
                bundle_spec=bundle_spec,
                feedback_hints=feedback_hints,
            )
        except Exception as exc:
            raise ProviderFailedError("Provider failed.") from exc

    def _call_provider_with_retry(
        self,
        provider: Provider,
        payload: dict[str, Any],
        request_id: str,
        bundle_spec: BundleSpec,
    ) -> dict[str, Any]:
        """Call provider with exponential backoff retry on ProviderFailedError."""
        from app.config import get_llm_retry_attempts, get_llm_retry_backoff_seconds
        attempts = get_llm_retry_attempts()
        backoffs = get_llm_retry_backoff_seconds()
        last_exc: ProviderFailedError | None = None
        for attempt in range(attempts):
            try:
                return self._call_provider_once(provider, payload, request_id, bundle_spec)
            except ProviderFailedError as exc:
                last_exc = exc
                if attempt < attempts - 1:
                    delay = backoffs[attempt] if attempt < len(backoffs) else backoffs[-1]
                    _log.warning(
                        "[LLM Retry] attempt %d/%d failed for request_id=%s, "
                        "retrying in %ds: %s",
                        attempt + 1, attempts, request_id, delay, exc,
                    )
                    time.sleep(delay)
        raise last_exc  # type: ignore[misc]

    def _try_read_cache(self, cache_path: Path) -> dict[str, Any] | None:
        try:
            text = cache_path.read_text(encoding="utf-8")
            parsed = json.loads(text)
            if not isinstance(parsed, dict):
                return None
            return parsed
        except (OSError, ValueError, json.JSONDecodeError):
            return None

    def _write_cache_atomic(self, cache_path: Path, bundle: dict[str, Any]) -> None:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(bundle, ensure_ascii=False, indent=2)
        tmp_path = cache_path.with_name(f"{cache_path.name}.tmp.{uuid4().hex}")
        try:
            with tmp_path.open("w", encoding="utf-8") as f:
                f.write(payload)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, cache_path)
        finally:
            if tmp_path.exists():
                try:
                    tmp_path.unlink()
                except OSError:
                    pass

    def clear_cache(self) -> int:
        """Delete all cached bundles. Returns the number of files removed."""
        count = 0
        for f in self.cache_dir.glob("*.json"):
            try:
                f.unlink()
                count += 1
            except OSError:
                pass
        return count

    def _safe_get_provider(
        self, bundle_type: str | None = None, tenant_id: str = "system"
    ) -> Provider:
        """Return the best available provider, preferring fine-tuned model if active.

        Checks ModelRegistry for an active fine-tuned model first.  If found,
        returns an OpenAI provider using that model_id.  Otherwise falls back to
        the injected ``provider_factory`` so that tests keep full DI control.
        """
        try:
            from app.storage.model_registry import ModelRegistry
            registry = ModelRegistry()
            active_model = registry.get_active_model(bundle_type, tenant_id)
            if active_model and active_model.get("status") == "ready":
                model_id = active_model.get("model_id", "")
                if model_id and not model_id.startswith("pending:"):
                    from app.providers.factory import get_provider
                    return get_provider(model_override=model_id)
        except Exception:
            pass  # Fall through to injected factory

        try:
            return self.provider_factory()
        except Exception as exc:
            raise ProviderFailedError("Provider failed.") from exc
