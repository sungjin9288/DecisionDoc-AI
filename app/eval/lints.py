import re

from app.domain.headings import BANNED_TOKENS, CRITICAL_NON_EMPTY_HEADINGS, LINT_HEADINGS


def _section_content(markdown: str, heading: str) -> str:
    start = markdown.find(heading)
    if start == -1:
        return ""
    from_idx = start + len(heading)
    next_idx = markdown.find("\n## ", from_idx)
    if next_idx == -1:
        next_idx = len(markdown)
    return markdown[from_idx:next_idx]


def lint_docs(
    rendered: dict[str, str],
    *,
    lint_headings_override: dict[str, list[str]] | None = None,
    critical_headings_override: dict[str, list[str]] | None = None,
) -> list[str]:
    """Check rendered markdown for structural and quality issues.

    Args:
        rendered:                  Map of doc_key → rendered markdown string.
        lint_headings_override:    When provided, used instead of ``LINT_HEADINGS``.
                                   Pass ``bundle_spec.lint_headings_map()`` for non-tech_decision bundles.
        critical_headings_override: When provided, used instead of ``CRITICAL_NON_EMPTY_HEADINGS``.
                                    Pass ``bundle_spec.critical_non_empty_headings_map()``.
    """
    effective_lint = lint_headings_override if lint_headings_override is not None else LINT_HEADINGS
    effective_critical = (
        critical_headings_override if critical_headings_override is not None else CRITICAL_NON_EMPTY_HEADINGS
    )

    errors: list[str] = []
    for doc_type, markdown in rendered.items():
        for required in effective_lint.get(doc_type, []):
            if required not in markdown:
                errors.append(f"{doc_type}:missing:{required}")

        for token in BANNED_TOKENS:
            if re.search(rf"\b{re.escape(token)}\b", markdown):
                errors.append(f"{doc_type}:banned_token:{token}")

        for heading in effective_critical.get(doc_type, []):
            section = _section_content(markdown, heading)
            if not section.strip():
                errors.append(f"{doc_type}:empty_section:{heading}")

    return errors
