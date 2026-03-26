"""Centralised heading and content-quality constants for all validation stages.

Two validation stages use heading rules:
  - Lint stage   (eval/lints.py):     catches missing section headers early,
                                       before the full validator runs.
  - Validate stage (services/validator.py): stricter check on the fully rendered
                                            markdown, including detail sections.

Keeping these in one place ensures they stay in sync and makes the difference
between the two stages explicit and easy to extend.
"""

# ---------------------------------------------------------------------------
# Lint-stage headings
# Used by eval/lints.py on rendered markdown.
# Checks that the top-level structure and primary sections are present.
# ---------------------------------------------------------------------------
LINT_HEADINGS: dict[str, list[str]] = {
    "adr": [
        "# ADR:",
        "## Goal",
        "## Decision",
        "## Options",
    ],
    "onepager": [
        "# Onepager:",
        "## Problem",
        "## Recommendation",
        "## Impact",
    ],
    "eval_plan": [
        "# Eval Plan:",
        "## Metrics",
        "## Test cases",
        "## Failure criteria",
    ],
    "ops_checklist": [
        "# Ops Checklist:",
        "## Security",
        "## Reliability",
        "## Cost",
        "## Operations",
    ],
}

# ---------------------------------------------------------------------------
# Validate-stage headings
# Used by services/validator.py after full rendering.
# Stricter: includes all detail sections that must appear in the final document.
# ---------------------------------------------------------------------------
VALIDATOR_HEADINGS: dict[str, list[str]] = {
    "adr": [
        "## Goal",
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

# ---------------------------------------------------------------------------
# Content-quality constants (shared)
# ---------------------------------------------------------------------------

# Sections whose content must be non-empty after rendering.
CRITICAL_NON_EMPTY_HEADINGS: dict[str, list[str]] = {
    "adr": ["## Goal", "## Decision", "## Options"],
    "onepager": ["## Problem", "## Recommendation", "## Impact"],
    "eval_plan": ["## Metrics", "## Test cases", "## Failure criteria", "## Monitoring"],
    "ops_checklist": ["## Security", "## Reliability", "## Cost", "## Operations"],
}

# Tokens whose presence in any rendered document is a quality failure.
BANNED_TOKENS: list[str] = ["TODO", "TBD", "FIXME"]
