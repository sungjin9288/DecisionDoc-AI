from dataclasses import dataclass


@dataclass
class DocumentValidationError(Exception):
    doc_type: str
    missing: list[str]


REQUIRED_HEADINGS: dict[str, list[str]] = {
    "adr": [
        "## Goal",
        "## Context",
        "## Constraints",
        "## Decision",
        "## Options",
        "## Risks",
        "## Assumptions",
        "## Checks",
        "## Next actions",
    ],
    "onepager": [
        "## Problem",
        "## Recommendation",
        "## Impact",
        "## Constraints",
        "## Checks",
    ],
    "eval_plan": [
        "## Metrics",
        "## Test cases",
        "## Failure criteria",
        "## Monitoring",
    ],
    "ops_checklist": [
        "## Security",
        "## Reliability",
        "## Cost",
        "## Operations",
    ],
}


def _extract_section(markdown: str, heading: str) -> str:
    start = markdown.find(heading)
    if start == -1:
        return ""
    section_start = start + len(heading)
    next_heading = markdown.find("\n## ", section_start)
    if next_heading == -1:
        return markdown[section_start:]
    return markdown[section_start:next_heading]


def validate_doc(doc_type: str, markdown: str) -> None:
    missing: list[str] = []
    headings = REQUIRED_HEADINGS.get(doc_type, [])
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


def validate_docs(docs: list[dict]) -> None:
    for doc in docs:
        validate_doc(doc_type=doc["doc_type"], markdown=doc["markdown"])
