"""auto_registry.py — Dynamic loader for auto-generated bundle specs.

Auto-generated bundles are stored in data/auto_bundles/registry.json
and are loaded at registry startup to extend BUNDLE_REGISTRY.

Each auto bundle uses the shared template: auto_bundle/section.md.j2
Schema per section:
    {
        "section_title": str,   # Korean heading filled by LLM
        "summary":       str,   # 2-3 sentence overview
        "items":         list[str],  # specific detail points
    }
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

from app.bundle_catalog.spec import BundleSpec, DocumentSpec

_log = logging.getLogger("decisiondoc.bundle.auto_registry")

# Generic template shared by all auto-generated sections
_AUTO_SECTION_TEMPLATE = "auto_bundle/section.md.j2"

# Fixed headings used by the shared template (must stay in sync with the .j2)
_SECTION_LINT_HEADINGS = ["## 개요", "## 세부 내용"]
_SECTION_VALIDATOR_HEADINGS = ["## 개요", "## 세부 내용"]
_SECTION_CRITICAL_HEADINGS = ["## 개요"]


def _make_auto_bundle_spec(record: dict[str, Any]) -> BundleSpec:
    """Convert an auto-bundle registry record into a BundleSpec.

    Args:
        record: Registry entry loaded from data/auto_bundles/registry.json

    Returns:
        A fully-formed BundleSpec ready for use in the generation pipeline.

    Raises:
        ValueError: If the record has no sections.
    """
    bundle_id = record["bundle_id"]
    name_ko = record.get("name_ko", record.get("bundle_name", bundle_id))
    sections = record.get("sections", [])

    if not sections:
        raise ValueError(f"Auto bundle '{bundle_id}' has no sections.")

    docs: list[DocumentSpec] = []
    for section in sections:
        section_id = section["id"]
        section_title = section.get("title", section_id)
        docs.append(DocumentSpec(
            key=section_id,
            template_file=_AUTO_SECTION_TEMPLATE,
            json_schema={
                "type": "object",
                "required": ["section_title", "summary", "items"],
                "properties": {
                    "section_title": {"type": "string"},
                    "summary": {"type": "string"},
                    "items": {"type": "array", "items": {"type": "string"}},
                },
            },
            stabilizer_defaults={
                "section_title": section_title,
                "summary": "",
                "items": [],
            },
            lint_headings=_SECTION_LINT_HEADINGS,
            validator_headings=_SECTION_VALIDATOR_HEADINGS,
            critical_non_empty_headings=_SECTION_CRITICAL_HEADINGS,
        ))

    return BundleSpec(
        id=bundle_id,
        name_ko=name_ko,
        name_en=record.get("name_en", bundle_id.replace("_", " ").title()),
        description_ko=record.get("description_ko", record.get("description", "")),
        icon=record.get("icon", "📄"),
        prompt_language="ko",
        prompt_hint=(
            f"당신은 {name_ko} 문서 작성 전문가입니다.\n"
            "각 섹션의 section_title 필드에 한국어 섹션명을 명확히 작성하세요.\n"
            "summary는 해당 섹션의 핵심 내용을 2-3문장으로 작성하세요.\n"
            "items는 구체적인 세부 사항을 5개 이상 작성하세요.\n"
            "모든 내용을 한국어로 작성하세요."
        ),
        docs=docs,
        category="work",
    )


def load_auto_bundles() -> dict[str, BundleSpec]:
    """Load all auto-generated bundles from data/auto_bundles/registry.json.

    Uses DATA_DIR env var at call time (not import time) for testability.

    Returns:
        Dict of bundle_id → BundleSpec. Empty dict on any failure.
    """
    data_dir = Path(os.getenv("DATA_DIR", "./data"))
    registry_path = data_dir / "auto_bundles" / "registry.json"

    if not registry_path.exists():
        return {}

    try:
        data = json.loads(registry_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        _log.warning("[AutoBundle] registry.json 읽기 실패: %s", exc)
        return {}

    result: dict[str, BundleSpec] = {}
    for bundle_id, record in data.items():
        try:
            spec = _make_auto_bundle_spec(record)
            result[bundle_id] = spec
        except Exception as exc:
            _log.warning("[AutoBundle] '%s' 로드 실패 (무시): %s", bundle_id, exc)

    if result:
        _log.info(
            "[AutoBundle] %d개 자동 생성 번들 로드됨: %s",
            len(result),
            list(result),
        )
    return result
