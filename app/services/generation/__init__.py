"""Document-generation pipeline: quality guards, provider orchestration, and
the ``GenerationService`` facade.

The implementation lives in this package, split into focused modules:

- ``context_store``: generation-context thread-local capture, cross-request
  context cache, usage recording, and the background eval thread pool.
- ``text_normalization``: shared text/row cleanup helpers.
- ``quality_guard_proposal``: proposal_kr bundle quality guard.
- ``slide_outline_data``: static slide-outline fallback data.
- ``quality_guard_attachment``: attachment-grounded and sparse-context
  proposal quality guards.
- ``quality_guard_finish``: performance_plan_kr quality guard and the
  top-level quality-guard dispatcher.
- ``procurement_slide_guidance``: procurement PDF slide-outline guidance.
- ``errors``: provider/generation exception types and failure inspection
  helpers.
- ``service_core_mixin`` / ``service_rendering_mixin`` /
  ``service_cache_mixin`` / ``service_provider_mixin`` /
  ``service_context_injection_mixin``: the ``GenerationService`` mixins,
  composed below into the single public class.

This package re-exports the full public and internal API so existing
``from app.services.generation_service import X`` imports keep working
unchanged.
"""
from __future__ import annotations

from app.services.generation.context_store import (
    _DECISION_COUNCIL_APPLIED_BUNDLE_IDS,
    _CTX_MAX_SIZE,
    _CTX_TTL_SECONDS,
    _ctx_lock,
    _eval_done_callback,
    _eval_executor,
    _generation_context,
    _log,
    _record_usage_sync,
    _recent_generation_contexts,
    _store_generation_context,
    get_generation_context,
)
from app.services.generation.text_normalization import (
    _ensure_rows,
    _ensure_text,
    _has_meaningful_text,
    _normalize_finished_doc_text,
    _normalize_finished_doc_value,
    _normalized_row_list,
    _project_subject,
    _sanitize_rows,
    _strip_reference_noise,
)
from app.services.generation.quality_guard_proposal import _quality_guard_proposal_bundle
from app.services.generation.slide_outline_data import (
    _attachment_grounded_slide_outline,
    _sparse_proposal_slide_outline,
)
from app.services.generation.quality_guard_attachment import (
    _contains_unanchored_quant_claims,
    _extract_attachment_reference_text,
    _is_sparse_attachment_context,
    _is_sparse_non_attachment_context,
    _quality_guard_attachment_grounded_proposal_bundle,
    _quality_guard_sparse_non_attachment_proposal_bundle,
    _rows_contain_unanchored_quant_claims,
)
from app.services.generation.quality_guard_finish import (
    _apply_finished_doc_quality_guard,
    _quality_guard_performance_bundle,
)
from app.services.generation.procurement_slide_guidance import (
    _apply_procurement_slide_outline_guidance,
    _extract_procurement_context_from_text,
    _is_generic_slide_title,
    _merge_slide_outline_with_hint,
    _procurement_overlap_score,
    _procurement_text_key,
    _synthesize_procurement_slides,
)
from app.services.generation.errors import (
    BundleNotSupportedError,
    EvalLintFailedError,
    ProviderFailedError,
    is_provider_rate_limited,
    iter_exception_chain,
    provider_failure_error_code,
    provider_failure_retry_after_seconds,
)
from app.services.generation.service_cache_mixin import GenerationCacheMixin
from app.services.generation.service_context_injection_mixin import (
    GenerationContextInjectionMixin,
)
from app.services.generation.service_core_mixin import GenerationCoreMixin
from app.services.generation.service_provider_mixin import GenerationProviderCallMixin
from app.services.generation.service_rendering_mixin import GenerationRenderingMixin

__all__ = [
    "GenerationService",
    "ProviderFailedError",
    "EvalLintFailedError",
    "BundleNotSupportedError",
    "get_generation_context",
]


class GenerationService(
    GenerationCoreMixin,
    GenerationRenderingMixin,
    GenerationCacheMixin,
    GenerationProviderCallMixin,
    GenerationContextInjectionMixin,
):
    _PROCUREMENT_HANDOFF_BUNDLE_IDS = {
        "bid_decision_kr",
        "rfp_analysis_kr",
        "proposal_kr",
        "performance_plan_kr",
    }
