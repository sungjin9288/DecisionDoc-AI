"""Low-level JSON/mapping validation primitives shared across the
procurement decision package modules.

This module is intentionally local and deterministic. It does not call providers,
AWS, training, model promotion, or service-resume paths.
"""
from __future__ import annotations

import json
import string
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

def load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as file_obj:
        data = json.load(file_obj)
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return data


def _require_mapping(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{path} must be an object")
    return value


def _require_non_empty_string(value: Any, path: str) -> str:
    if not _is_non_empty_string(value):
        raise ValueError(f"{path} must be a non-empty string")
    return value


def _is_non_empty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value)


def _require_keys(mapping: dict[str, Any], keys: set[str], path: str) -> None:
    missing_keys = _missing_values(keys, mapping)
    if missing_keys:
        raise ValueError(
            f"{path} missing required keys: {', '.join(missing_keys)}"
        )


def _require_exact_mapping_fields(
    mapping: dict[str, Any],
    expected: Sequence[str],
    path: str,
) -> None:
    actual_field_order = list(mapping)
    expected_field_order = list(expected)
    missing_fields = _missing_values(expected, mapping)
    if missing_fields:
        raise ValueError(f"{path} missing fields: {', '.join(missing_fields)}")
    unknown_fields = _unknown_values(mapping, expected)
    if unknown_fields:
        raise ValueError(
            f"{path} includes unknown fields: {', '.join(unknown_fields)}"
        )
    if actual_field_order != expected_field_order:
        raise ValueError(f"{path} fields must match the expected order")


def _require_non_empty_list(value: Any, path: str) -> list[Any]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"{path} must be a non-empty list")
    return value


def _require_non_empty_string_list(value: Any, path: str) -> list[str]:
    return _require_string_items(_require_non_empty_list(value, path), path)


def _require_string_items(items: Sequence[Any], path: str) -> list[str]:
    strings: list[str] = []
    for index, item in enumerate(items):
        if not _is_non_empty_string(item):
            raise ValueError(
                f"{_list_item_path(path, index)} must be a non-empty string"
            )
        strings.append(item)
    return strings


def _exception_fields(exc: Exception) -> dict[str, str]:
    return {
        "error_type": exc.__class__.__name__,
        "error": str(exc),
    }


def _optional_path(value: object | None) -> str | None:
    return str(value) if value is not None else None


def _bool_label(value: object) -> str:
    return str(value).lower()


def _project_fields(mapping: dict[str, Any], fields: Sequence[str]) -> dict[str, Any]:
    return {field: mapping[field] for field in fields}


def _project_optional_fields(
    mapping: dict[str, Any],
    fields: Sequence[str],
) -> dict[str, Any]:
    return {field: mapping.get(field) for field in fields}


def _field_path(path: str, field: str) -> str:
    return f"{path}.{field}"


def _list_item_path(path: str, index: int) -> str:
    return f"{path}[{index}]"


def _is_sha256_hex(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(char in string.hexdigits for char in value)
    )


def _is_non_negative_int(value: Any) -> bool:
    return not isinstance(value, bool) and isinstance(value, int) and value >= 0


def _require_path_string(path_value: Any, path_name: str) -> str:
    if not _is_non_empty_string(path_value):
        raise ValueError(f"{path_name} must be a non-empty string")
    return path_value


def _require_matching_field(
    left: dict[str, Any],
    right: dict[str, Any],
    field: str,
    *,
    left_label: str = "demo_smoke_result",
    right_label: str,
) -> None:
    left_field_value = left.get(field)
    right_field_value = right.get(field)
    if left_field_value != right_field_value:
        left_field_path = _field_path(left_label, field)
        right_field_path = _field_path(right_label, field)
        raise ValueError(f"{left_field_path} must match {right_field_path}")


def _require_matching_fields(
    left: dict[str, Any],
    right: dict[str, Any],
    fields: Sequence[str],
    *,
    left_label: str = "demo_smoke_result",
    right_label: str,
) -> None:
    for field in fields:
        _require_matching_field(
            left,
            right,
            field,
            left_label=left_label,
            right_label=right_label,
        )


def _require_boolean_fields(
    mapping: dict[str, Any],
    fields: Sequence[str],
    *,
    expected: bool,
    path: str,
) -> None:
    expected_label = _bool_label(expected)

    for field in fields:
        field_value = mapping.get(field)
        field_path = _field_path(path, field)
        if field_value is not expected:
            raise ValueError(f"{field_path} must be {expected_label}")


def _require_unique_values(
    items: Sequence[str],
    path: str,
    *,
    message: str | None = None,
) -> None:
    unique_items = set(items)
    if len(unique_items) != len(items):
        raise ValueError(message or f"{path} must not contain duplicate values")


def _missing_values(
    expected_values: Iterable[str],
    actual_values: Iterable[str],
) -> list[str]:
    expected_value_set = set(expected_values)
    actual_value_set = set(actual_values)
    return sorted(expected_value_set - actual_value_set)


def _unknown_values(
    actual_values: Iterable[str],
    expected_values: Iterable[str],
) -> list[str]:
    actual_value_set = set(actual_values)
    expected_value_set = set(expected_values)
    return sorted(actual_value_set - expected_value_set)


def _shared_values(
    left_values: Iterable[str],
    right_values: Iterable[str],
) -> list[str]:
    left_value_set = set(left_values)
    right_value_set = set(right_values)
    return sorted(left_value_set & right_value_set)


def _require_exact_ordered_values(
    recorded_values: list[str],
    expected: Sequence[str],
    *,
    path: str,
    missing_label: str = "values",
    unknown_label: str = "values",
) -> None:
    expected_order = list(expected)
    missing_values = _missing_values(expected_order, recorded_values)
    if missing_values:
        raise ValueError(
            f"{path} missing {missing_label}: {', '.join(missing_values)}"
        )
    unknown_values = _unknown_values(recorded_values, expected_order)
    if unknown_values:
        raise ValueError(
            f"{path} includes unknown {unknown_label}: "
            f"{', '.join(unknown_values)}"
        )
    if recorded_values != expected_order:
        raise ValueError(f"{path} must match the expected order")
