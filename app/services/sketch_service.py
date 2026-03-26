"""sketch_service — lightweight document sketch generation.

Produces a section outline + PPT slide breakdown in 2-4 seconds using
generate_raw() for a minimal LLM call, optionally augmented with web search.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field

logger = logging.getLogger("decisiondoc.sketch")


@dataclass
class SlideCard:
    page: int
    title: str
    key_content: str


@dataclass
class SketchSection:
    heading: str
    bullets: list[str] = field(default_factory=list)


@dataclass
class SketchResult:
    bundle_id: str
    bundle_name: str
    title: str
    sections: list[SketchSection] = field(default_factory=list)
    ppt_slides: list[SlideCard] | None = None
    search_snippets: list[str] = field(default_factory=list)
    has_search: bool = False


def _format_search_results(results: list) -> str:
    lines = []
    for i, r in enumerate(results[:5], 1):
        lines.append(f"{i}. [{r.title}] {r.snippet}")
    return "\n".join(lines)


def generate_sketch(
    payload: dict,
    provider,
    bundle_spec,
    *,
    search_service=None,
    request_id: str = "sketch",
) -> SketchResult:
    """Generate a lightweight document sketch using generate_raw().

    Args:
        payload:        GenerateRequest as dict.
        provider:       Provider instance (must implement generate_raw()).
        bundle_spec:    BundleSpec for the target bundle.
        search_service: Optional SearchService for web augmentation.
        request_id:     Request ID for logging.

    Returns:
        SketchResult with sections, optional PPT slides, and search snippets.
    """
    from app.domain.schema import build_sketch_prompt

    # 1. Optional web search
    search_results: list = []
    if search_service is not None and search_service.is_available():
        query_parts = [
            payload.get("title", ""),
            payload.get("goal", ""),
            payload.get("industry", ""),
        ]
        query = " ".join(p for p in query_parts if p).strip()
        if query:
            search_results = search_service.search(query, num=5)

    search_context = _format_search_results(search_results) if search_results else ""

    # 2. Build sketch prompt
    prompt = build_sketch_prompt(payload, bundle_spec, search_context=search_context)

    # 3. Call provider via generate_raw (lightweight, no bundle validation)
    try:
        raw = provider.generate_raw(prompt, request_id=request_id)
    except NotImplementedError:
        # Fallback: return minimal sketch if provider doesn't support generate_raw
        logger.warning("provider %s does not support generate_raw(); returning minimal sketch", provider.name)
        raw = json.dumps({"sections": [{"heading": "## 문서 구성", "bullets": ["입력 정보를 기반으로 문서를 구성합니다."]}], "ppt_slides": None})

    # 4. Parse JSON
    try:
        # Strip markdown code fences if present
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            cleaned = "\n".join(cleaned.splitlines()[1:])
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
        data = json.loads(cleaned)
    except (json.JSONDecodeError, ValueError) as exc:
        logger.warning("sketch JSON parse failed: %s — raw=%r", exc, raw[:200])
        data = {"sections": [], "ppt_slides": None}

    # 5. Build SketchResult
    raw_sections = data.get("sections") or []
    sections = [
        SketchSection(
            heading=s.get("heading", ""),
            bullets=s.get("bullets") or [],
        )
        for s in raw_sections
        if isinstance(s, dict) and s.get("heading")
    ]

    raw_slides = data.get("ppt_slides")
    ppt_slides: list[SlideCard] | None = None
    if raw_slides and isinstance(raw_slides, list):
        ppt_slides = [
            SlideCard(
                page=s.get("page", i + 1),
                title=s.get("title", ""),
                key_content=s.get("key_content", ""),
            )
            for i, s in enumerate(raw_slides)
            if isinstance(s, dict)
        ]

    return SketchResult(
        bundle_id=bundle_spec.id,
        bundle_name=bundle_spec.name_ko,
        title=payload.get("title", ""),
        sections=sections,
        ppt_slides=ppt_slides,
        search_snippets=[r.snippet for r in search_results[:3]],
        has_search=bool(search_results),
    )
