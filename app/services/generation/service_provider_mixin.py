"""Provider invocation, retry, prompt-variant, and post-processing mixin."""
from __future__ import annotations

import time
from typing import Any

from app.bundle_catalog.spec import BundleSpec
from app.domain.schema import SCHEMA_VERSION
from app.observability.timing import Timer
from app.providers.base import Provider
from app.providers.stabilizer import stabilize_bundle, strip_internal_bundle_fields
from app.services.generation.context_store import _log
from app.services.generation.errors import (
    ProviderFailedError,
    is_provider_rate_limited,
    provider_failure_retry_after_seconds,
)
from app.services.generation.procurement_slide_guidance import (
    _apply_procurement_slide_outline_guidance,
    _extract_procurement_context_from_text,
)
from app.services.generation.quality_guard_finish import _apply_finished_doc_quality_guard


class GenerationProviderCallMixin:
    """Calls the LLM provider (with retry), applies quality guards, resolves the active provider."""

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
        bundle = _apply_finished_doc_quality_guard(
            bundle,
            bundle_type=str(payload.get("bundle_type", "tech_decision") or "tech_decision"),
            title=str(payload.get("title", "") or ""),
            goal=str(payload.get("goal", "") or ""),
            context_text=str(payload.get("context", "") or ""),
        )
        procurement_context = str(payload.get("_procurement_context", "") or "").strip()
        if not procurement_context:
            procurement_context = _extract_procurement_context_from_text(payload.get("context", ""))
        if procurement_context:
            bundle = _apply_procurement_slide_outline_guidance(
                bundle,
                procurement_context=procurement_context,
            )
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
                    if is_provider_rate_limited(exc):
                        retry_after = provider_failure_retry_after_seconds(exc)
                        delay = max(delay, retry_after if retry_after is not None else 15)
                    _log.warning(
                        "[LLM Retry] attempt %d/%d failed for request_id=%s, "
                        "retrying in %ds: %s",
                        attempt + 1, attempts, request_id, delay, exc,
                    )
                    time.sleep(delay)
        raise last_exc  # type: ignore[misc]

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
