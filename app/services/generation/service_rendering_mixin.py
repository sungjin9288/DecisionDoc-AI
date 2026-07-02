"""Document rendering (Jinja2) and provider-bundle schema validation mixin."""
from __future__ import annotations

from typing import Any

from app.bundle_catalog.spec import BundleSpec
from app.services.generation.errors import ProviderFailedError


class GenerationRenderingMixin:
    """Renders bundle docs to markdown and validates provider bundle shape."""

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
