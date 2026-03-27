"""BundleSpec — single source of truth for each document bundle type.

Each BundleSpec fully describes one bundle type (e.g. tech_decision, proposal_kr)
and carries every piece of information needed across the generation pipeline:
- LLM prompt construction (json_schema, stability_checklist, prompt_hint)
- Schema validation (_validate_bundle_schema)
- Stabilizer defaults (missing-field patching)
- Jinja2 template selection (template_file per doc)
- Lint headings (eval/lints.py)
- Validator headings (services/validator.py)
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class DocumentSpec:
    """Specification for a single document within a bundle.

    Attributes:
        key: Top-level key in the LLM JSON response (e.g. "adr", "business_understanding").
        template_file: Jinja2 template filename, relative to the bundle's template directory.
        json_schema: JSON Schema dict for this document's fields (used in LLM prompt + validation).
        stabilizer_defaults: Default values for each field when the LLM omits them.
            str fields → "", list fields → [].
        lint_headings: Markdown headings that must be present after rendering (lint stage).
        validator_headings: Headings checked in the final validation stage (stricter).
        critical_non_empty_headings: Headings whose content must be non-empty.
    """

    key: str
    template_file: str
    json_schema: dict[str, Any]
    stabilizer_defaults: dict[str, Any]
    lint_headings: list[str]
    validator_headings: list[str]
    critical_non_empty_headings: list[str]


@dataclass(frozen=True)
class BundleSpec:
    """Full specification for one bundle type.

    A bundle type is a named collection of documents targeting a specific
    use case (e.g. technical decision-making, government AI proposals).

    Attributes:
        id: Unique bundle identifier used in API requests (bundle_type field).
        name_ko: Korean display name shown in the UI.
        name_en: English display name.
        description_ko: Short Korean description for the UI selection card.
        icon: Emoji/icon string for the UI card.
        prompt_language: Language instruction for the LLM ("ko" | "en").
        prompt_hint: Additional LLM instructions appended to the stability checklist.
        docs: Ordered list of DocumentSpecs. The rendering order follows this list.
    """

    id: str
    name_ko: str
    name_en: str
    description_ko: str
    icon: str
    prompt_language: str  # "ko" | "en"
    prompt_hint: str
    docs: list[DocumentSpec]
    category: str = field(default="work")  # "work" | "student" | "both"
    prompt_variants: dict[str, str] = field(default_factory=dict)
    # 키: variant 이름("v1", "v2", ...), 값: 해당 variant의 prompt_hint
    # 비어 있으면 기본 prompt_hint 사용
    max_output_tokens: int | None = field(default=None)  # None = use ENV default
    few_shot_example: str = field(default="")  # Few-shot 골든 예시 — build_bundle_prompt()에서 LLM에 주입

    # ------------------------------------------------------------------
    # Computed properties — derived from the docs list
    # ------------------------------------------------------------------

    @property
    def doc_keys(self) -> list[str]:
        """Ordered list of doc keys in this bundle."""
        return [d.key for d in self.docs]

    @property
    def json_schema(self) -> dict[str, Any]:
        """Top-level JSON Schema for the entire bundle (used in LLM prompt)."""
        return {
            "type": "object",
            "required": self.doc_keys,
            "properties": {d.key: d.json_schema for d in self.docs},
        }

    @property
    def stability_checklist(self) -> str:
        """Dynamically generated stability checklist for the LLM prompt."""
        keys_str = ", ".join(self.doc_keys)
        lang_instruction = (
            "- 모든 내용을 한국어로 작성하세요.\n" if self.prompt_language == "ko" else ""
        )
        hint = f"{self.prompt_hint}\n" if self.prompt_hint else ""
        return (
            "Stability checklist:\n"
            "- Return one JSON bundle object only.\n"
            f"- Include top-level keys: {keys_str}.\n"
            "- Include required fields for each doc section per schema.\n"
            "- Do not include TODO/TBD/FIXME.\n"
            "- Keep each doc section sufficiently detailed (target >= 600 chars per doc after rendering).\n"
            "- Output JSON only, no markdown.\n"
            f"{lang_instruction}"
            f"{hint}"
        ).rstrip()

    def get_doc(self, key: str) -> DocumentSpec | None:
        """Return the DocumentSpec for the given key, or None if not found."""
        for d in self.docs:
            if d.key == key:
                return d
        return None

    def lint_headings_map(self) -> dict[str, list[str]]:
        """Map of doc_key → lint_headings for all docs in this bundle."""
        return {d.key: d.lint_headings for d in self.docs}

    def validator_headings_map(self) -> dict[str, list[str]]:
        """Map of doc_key → validator_headings for all docs in this bundle."""
        return {d.key: d.validator_headings for d in self.docs}

    def critical_non_empty_headings_map(self) -> dict[str, list[str]]:
        """Map of doc_key → critical_non_empty_headings for all docs."""
        return {d.key: d.critical_non_empty_headings for d in self.docs}

    def stabilizer_structure(self) -> dict[str, dict[str, Any]]:
        """Map of doc_key → stabilizer_defaults, used by stabilize_bundle()."""
        return {d.key: d.stabilizer_defaults for d in self.docs}

    def build_json_schema_str(self) -> str:
        """JSON-serialized schema for embedding in LLM prompts."""
        return json.dumps(self.json_schema, ensure_ascii=False)

    def ui_metadata(self) -> dict[str, Any]:
        """Metadata dict for the GET /bundles API response."""
        return {
            "id": self.id,
            "name_ko": self.name_ko,
            "name_en": self.name_en,
            "description_ko": self.description_ko,
            "icon": self.icon,
            "doc_count": len(self.docs),
            "doc_keys": self.doc_keys,
            "prompt_language": self.prompt_language,
            "category": self.category,
            "prompt_variants": list(self.prompt_variants.keys()),
        }
