from dataclasses import dataclass

from app.domain.headings import VALIDATOR_HEADINGS


@dataclass
class DocumentValidationError(Exception):
    doc_type: str
    missing: list[str]


def _extract_section(markdown: str, heading: str) -> str:
    start = markdown.find(heading)
    if start == -1:
        return ""
    section_start = start + len(heading)
    next_heading = markdown.find("\n## ", section_start)
    if next_heading == -1:
        return markdown[section_start:]
    return markdown[section_start:next_heading]


def validate_doc(
    doc_type: str,
    markdown: str,
    headings_override: dict[str, list[str]] | None = None,
) -> None:
    """Validate a single rendered document.

    Args:
        doc_type:          The document key (e.g. ``"adr"``, ``"business_understanding"``).
        markdown:          The fully rendered markdown string.
        headings_override: When provided, used instead of ``VALIDATOR_HEADINGS``.
                           Pass ``bundle_spec.validator_headings_map()`` for non-tech_decision bundles.
    """
    effective = headings_override if headings_override is not None else VALIDATOR_HEADINGS
    missing: list[str] = []
    headings = effective.get(doc_type, [])
    for heading in headings:
        if heading not in markdown:
            missing.append(f"missing_heading:{heading}")

    if doc_type == "adr" and "## Options" in markdown:
        options_section = _extract_section(markdown, "## Options")
        options_count = sum(1 for line in options_section.splitlines() if line.strip().startswith("- "))
        if options_count < 2:
            missing.append("adr_options_lt_2")

    if missing:
        raise DocumentValidationError(doc_type=doc_type, missing=missing)


def validate_docs(
    docs: list[dict[str, str]],
    headings_override: dict[str, list[str]] | None = None,
) -> None:
    """Validate all rendered documents in a bundle.

    Args:
        docs:              List of ``{"doc_type": ..., "markdown": ...}`` dicts.
        headings_override: Forwarded to each :func:`validate_doc` call.
    """
    for doc in docs:
        validate_doc(
            doc_type=doc["doc_type"],
            markdown=doc["markdown"],
            headings_override=headings_override,
        )
