import re
from typing import Any

from app.eval.config import (
    BANNED_TOKENS,
    EVAL_DOC_TYPES,
    EVAL_REQUIRED_HEADINGS,
    MIN_COVERAGE_PER_DOC,
    MIN_TOTAL_CHARS,
)
from app.eval.lints import lint_docs
from app.services.validator import DocumentValidationError, validate_docs


def validator_result(docs: list[dict[str, str]]) -> tuple[bool, list[str]]:
    try:
        validate_docs(docs)
        return True, []
    except DocumentValidationError:
        return False, ["validator_failed"]


def lint_result(rendered: dict[str, str]) -> tuple[bool, list[str]]:
    errors = lint_docs(rendered)
    return len(errors) == 0, errors


def required_sections_coverage(rendered: dict[str, str]) -> dict[str, float]:
    coverage: dict[str, float] = {}
    for doc_type in EVAL_DOC_TYPES:
        headings = EVAL_REQUIRED_HEADINGS[doc_type]
        text = rendered.get(doc_type, "")
        matched = sum(1 for heading in headings if heading in text)
        ratio = matched / len(headings) if headings else 1.0
        coverage[doc_type] = round(ratio, 4)
    return coverage


def banned_token_violations(rendered: dict[str, str]) -> int:
    total = 0
    for text in rendered.values():
        for token in BANNED_TOKENS:
            total += len(re.findall(rf"\b{re.escape(token)}\b", text))
    return total


def length_stats(rendered: dict[str, str]) -> dict[str, int]:
    lengths: dict[str, int] = {}
    total = 0
    for doc_type in EVAL_DOC_TYPES:
        value = len(rendered.get(doc_type, ""))
        lengths[doc_type] = value
        total += value
    lengths["total"] = total
    return lengths


def evaluate_fixture(docs: list[dict[str, str]]) -> dict[str, Any]:
    rendered = {doc["doc_type"]: doc["markdown"] for doc in docs}
    validator_pass, validator_errors = validator_result(docs)
    lint_pass, lint_errors = lint_result(rendered)
    coverage = required_sections_coverage(rendered)
    banned_count = banned_token_violations(rendered)
    lengths = length_stats(rendered)

    errors: list[str] = []
    errors.extend(validator_errors)
    if not lint_pass:
        errors.append("lint_failed")
    if banned_count > 0:
        errors.append("banned_tokens_present")
    for doc_type, ratio in coverage.items():
        if ratio < MIN_COVERAGE_PER_DOC:
            errors.append(f"coverage_lt_{MIN_COVERAGE_PER_DOC}:{doc_type}")
    if lengths["total"] < MIN_TOTAL_CHARS:
        errors.append(f"total_chars_lt_{MIN_TOTAL_CHARS}")

    return {
        "validator_pass": validator_pass,
        "lint_pass": lint_pass,
        "lint_errors": lint_errors,
        "required_sections_coverage": coverage,
        "banned_token_violations": banned_count,
        "length_chars": lengths,
        "pass": len(errors) == 0,
        "errors": errors,
    }
