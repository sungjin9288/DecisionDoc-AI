"""app/providers/authored_provider.py — Bundle written by a local agent session.

A Claude Code or Codex session writes the bundle JSON itself from the
authoring brief. This provider hands that JSON to the normal generation
pipeline (stabilizer, schema validation, rendering, lints) without any model
or network call.
"""
from __future__ import annotations

import copy
from typing import Any

from app.providers.base import Provider, ProviderError


class AuthoredBundleProvider(Provider):
    name = "agent_authored"

    def __init__(self, bundle: dict[str, Any]) -> None:
        if not isinstance(bundle, dict):
            raise ProviderError("Authored bundle must be a JSON object.")
        self._bundle = copy.deepcopy(bundle)

    def generate_bundle(
        self,
        requirements: dict[str, Any],
        *,
        schema_version: str,
        request_id: str,
        bundle_spec: Any = None,
        feedback_hints: str = "",
    ) -> dict[str, Any]:
        return copy.deepcopy(self._bundle)

    def generate_raw(self, prompt: str, *, request_id: str, max_output_tokens: int | None = None) -> str:
        raise ProviderError("Authored bundles do not support raw generation.")
