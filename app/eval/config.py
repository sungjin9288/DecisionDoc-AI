EVAL_VERSION = "v1"

EVAL_REQUIRED_HEADINGS: dict[str, list[str]] = {
    "adr": ["## Context", "## Decision", "## Options"],
    "onepager": ["## Problem", "## Recommendation", "## Impact"],
    "eval_plan": ["## Metrics", "## Test cases", "## Monitoring"],
    "ops_checklist": ["## Security", "## Reliability", "## Operations"],
}

EVAL_DOC_TYPES = ["adr", "onepager", "eval_plan", "ops_checklist"]
BANNED_TOKENS = ["TODO", "TBD", "FIXME"]
MIN_COVERAGE_PER_DOC = 0.8
MIN_TOTAL_CHARS = 2000
