"""Conservative numeric-claim coverage checks for generated documents."""
from __future__ import annotations

import re
from decimal import Decimal
from typing import Any, Mapping


_NUMERIC_CLAIM_PATTERN = re.compile(
    r"(?<![\w.])"
    r"(?P<number>\d+(?:,\d{3})*(?:\.\d+)?)"
    r"\s*"
    r"(?P<unit>억\s*원|만\s*원|천\s*원|원|%|퍼센트|개월|년|월|일|시간|분|초|명|건|회|배)"
    r"(?!할)"
)
_CURRENCY_MULTIPLIERS = {
    "억원": Decimal("100000000"),
    "만원": Decimal("10000"),
    "천원": Decimal("1000"),
    "원": Decimal("1"),
}


def _canonical_number(raw: str) -> str:
    value = Decimal(raw.replace(",", ""))
    if value == value.to_integral():
        return str(value.quantize(Decimal("1")))
    return format(value.normalize(), "f")


def _canonical_token(number: str, unit: str) -> str:
    compact_unit = unit.replace(" ", "")
    if compact_unit in _CURRENCY_MULTIPLIERS:
        won = Decimal(number.replace(",", "")) * _CURRENCY_MULTIPLIERS[compact_unit]
        return f"{_canonical_number(str(won))}원"
    if compact_unit == "퍼센트":
        compact_unit = "%"
    return f"{_canonical_number(number)}{compact_unit}"


def _text_values(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, Mapping):
        result: list[str] = []
        for nested in value.values():
            result.extend(_text_values(nested))
        return result
    if isinstance(value, (list, tuple, set)):
        result = []
        for nested in value:
            result.extend(_text_values(nested))
        return result
    return []


def _tokens(texts: list[str]) -> set[str]:
    return {
        _canonical_token(match.group("number"), match.group("unit"))
        for text in texts
        for match in _NUMERIC_CLAIM_PATTERN.finditer(text)
    }


def _excerpt(text: str, start: int, end: int, limit: int = 220) -> str:
    line_start = text.rfind("\n", 0, start) + 1
    line_end = text.find("\n", end)
    if line_end == -1:
        line_end = len(text)
    compact = " ".join(text[line_start:line_end].split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 3] + "..."


def review_numeric_grounding(
    source: Mapping[str, Any],
    documents: Mapping[str, str],
) -> dict[str, Any]:
    """Report output unit-bearing numbers that are absent from the source.

    This check only establishes literal numeric coverage. It does not prove that
    a supported number is true, current, or used in the correct context.
    """

    source_tokens = _tokens(_text_values(source))
    output_tokens: set[str] = set()
    unsupported_claims: list[dict[str, str]] = []
    seen_claims: set[tuple[str, str, str]] = set()

    for document_type, markdown in documents.items():
        for match in _NUMERIC_CLAIM_PATTERN.finditer(markdown):
            token = _canonical_token(match.group("number"), match.group("unit"))
            output_tokens.add(token)
            if token in source_tokens:
                continue
            excerpt = _excerpt(markdown, match.start(), match.end())
            claim_key = (document_type, token, excerpt)
            if claim_key in seen_claims:
                continue
            seen_claims.add(claim_key)
            unsupported_claims.append(
                {
                    "document_type": document_type,
                    "token": token,
                    "excerpt": excerpt,
                }
            )

    unsupported_claims.sort(
        key=lambda claim: (claim["document_type"], claim["token"], claim["excerpt"])
    )
    return {
        "status": "review_required" if unsupported_claims else "passed",
        "scope": "literal_unit_bearing_numeric_coverage",
        "proves_factual_truth": False,
        "source_tokens": sorted(source_tokens),
        "output_tokens": sorted(output_tokens),
        "unsupported_count": len(unsupported_claims),
        "unsupported_claims": unsupported_claims,
    }
