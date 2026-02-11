import re


REQUIRED_HEADINGS: dict[str, list[str]] = {
    "adr": ["# ADR:", "## Goal", "## Context", "## Constraints", "## Decision", "## Options"],
    "onepager": ["# Onepager:", "## Problem", "## Recommendation", "## Impact"],
    "eval_plan": ["# Eval Plan:", "## Metrics", "## Test cases", "## Failure criteria"],
    "ops_checklist": ["# Ops Checklist:", "## Security", "## Reliability", "## Cost", "## Operations"],
}

BANNED_TOKENS = ["TODO", "TBD", "FIXME"]

CRITICAL_NON_EMPTY_HEADINGS: dict[str, list[str]] = {
    "adr": ["## Goal", "## Decision", "## Options"],
    "onepager": ["## Problem", "## Recommendation", "## Impact"],
    "eval_plan": ["## Metrics", "## Test cases", "## Failure criteria", "## Monitoring"],
    "ops_checklist": ["## Security", "## Reliability", "## Cost", "## Operations"],
}


def _section_content(markdown: str, heading: str) -> str:
    start = markdown.find(heading)
    if start == -1:
        return ""
    from_idx = start + len(heading)
    next_idx = markdown.find("\n## ", from_idx)
    if next_idx == -1:
        next_idx = len(markdown)
    return markdown[from_idx:next_idx]


def lint_docs(rendered: dict[str, str]) -> list[str]:
    errors: list[str] = []
    for doc_type, markdown in rendered.items():
        for required in REQUIRED_HEADINGS.get(doc_type, []):
            if required not in markdown:
                errors.append(f"{doc_type}:missing:{required}")

        for token in BANNED_TOKENS:
            if re.search(rf"\b{re.escape(token)}\b", markdown):
                errors.append(f"{doc_type}:banned_token:{token}")

        for heading in CRITICAL_NON_EMPTY_HEADINGS.get(doc_type, []):
            section = _section_content(markdown, heading)
            if not section.strip():
                errors.append(f"{doc_type}:empty_section:{heading}")

    return errors
