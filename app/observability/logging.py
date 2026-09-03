import json
import logging
import os
import re
import traceback
from datetime import datetime, timezone
from typing import Any


REDACTED = "[REDACTED]"
_QUERY_PARAMETER = re.compile(r"([?&])([^=&#\s]+)=([^&#\s\"']*)")
_SENSITIVE_ASSIGNMENT_PREFIX = re.compile(
    r"(?<![a-z0-9_])(?P<key_quote>[\\]*[\"']|)"
    r"(?P<key>authorization|service[_-]?key|(?:[a-z0-9]+[_-])*"
    r"(?:api[_-]?key|password|secret|signature|token))"
    r"(?P=key_quote)\s*[:=]\s*",
    re.IGNORECASE,
)
_AUTHORIZATION_SCHEMES = frozenset(
    {"apikey", "basic", "bearer", "digest", "negotiate", "oauth", "token"}
)
_UNQUOTED_VALUE_STOPS = frozenset(" \t\r\n,;&?#}]\"'")


def _is_sensitive_field(name: object) -> bool:
    normalized = re.sub(r"[^a-z0-9]", "", str(name).lower())
    return normalized in {"authorization", "servicekey"} or normalized.endswith(
        ("apikey", "password", "secret", "signature", "token")
    )


def _quoted_value_end(value: str, start: int, delimiter: str) -> int:
    quote = delimiter[-1]
    expected_backslashes = len(delimiter) - 1
    cursor = start + len(delimiter)
    while True:
        quote_index = value.find(quote, cursor)
        if quote_index < 0:
            return len(value)
        backslashes = 0
        probe = quote_index - 1
        while probe >= start and value[probe] == "\\":
            backslashes += 1
            probe -= 1
        if (
            backslashes == expected_backslashes
            or (expected_backslashes == 0 and backslashes % 2 == 0)
        ):
            return quote_index + 1
        cursor = quote_index + 1


def _consume_sensitive_value(
    value: str,
    start: int,
    *,
    authorization: bool,
    preserve_quotes: bool,
) -> tuple[int, str] | None:
    if start >= len(value) or value[start] in ",;&?#}]":
        return None

    delimiter_end = start
    while delimiter_end < len(value) and value[delimiter_end] == "\\":
        delimiter_end += 1
    if delimiter_end < len(value) and value[delimiter_end] in "\"'":
        delimiter = value[start : delimiter_end + 1]
        end = _quoted_value_end(value, start, delimiter)
        replacement = f"{delimiter}{REDACTED}{delimiter}" if preserve_quotes else REDACTED
        return end, replacement

    token_end = start
    while token_end < len(value) and value[token_end] not in _UNQUOTED_VALUE_STOPS:
        token_end += 1
    if token_end == start:
        return None

    token = value[start:token_end]
    if authorization and token.casefold() in _AUTHORIZATION_SCHEMES:
        secret_start = token_end
        while secret_start < len(value) and value[secret_start] in " \t":
            secret_start += 1
        secret_end = secret_start
        while secret_end < len(value) and value[secret_end] not in _UNQUOTED_VALUE_STOPS:
            secret_end += 1
        if secret_end > secret_start:
            return secret_end, f"{token}{value[token_end:secret_start]}{REDACTED}"
    return token_end, REDACTED


def _redact_sensitive_assignments(value: str) -> str:
    parts: list[str] = []
    cursor = 0
    while match := _SENSITIVE_ASSIGNMENT_PREFIX.search(value, cursor):
        parts.append(value[cursor:match.end()])
        consumed = _consume_sensitive_value(
            value,
            match.end(),
            authorization=match.group("key").casefold() == "authorization",
            preserve_quotes=bool(match.group("key_quote")),
        )
        if consumed is None:
            cursor = match.end()
            continue
        cursor, replacement = consumed
        parts.append(replacement)
    parts.append(value[cursor:])
    return "".join(parts)


def _redact_sensitive_text(value: str) -> str:
    def replace_query_parameter(match: re.Match[str]) -> str:
        separator, name, raw_value = match.groups()
        if not _is_sensitive_field(name):
            return match.group(0)
        return f"{separator}{name}={REDACTED}" if raw_value else match.group(0)

    value = _QUERY_PARAMETER.sub(replace_query_parameter, value)
    return _redact_sensitive_assignments(value)


def _redact_sensitive_values(value: Any, *, field_name: object = "") -> Any:
    if field_name and _is_sensitive_field(field_name):
        return REDACTED
    if isinstance(value, dict):
        return {
            key: _redact_sensitive_values(item, field_name=key)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_redact_sensitive_values(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_redact_sensitive_values(item) for item in value)
    if isinstance(value, str):
        return _redact_sensitive_text(value)
    return value


class JsonLineFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        if isinstance(record.msg, dict):
            payload = dict(record.msg)
        else:
            payload = {"message": record.getMessage()}

        if record.exc_info:
            payload.setdefault(
                "traceback",
                "".join(traceback.format_exception(*record.exc_info)).strip(),
            )

        payload = _redact_sensitive_values(payload)
        payload.setdefault("ts", datetime.now(timezone.utc).isoformat())
        payload.setdefault("level", record.levelname)
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def setup_logging() -> None:
    level_name = os.getenv("DECISIONDOC_LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    root = logging.getLogger()
    root.setLevel(level)

    for handler in root.handlers:
        if getattr(handler, "_decisiondoc_json", False):
            handler.setLevel(level)
            break
    else:
        handler = logging.StreamHandler()
        handler.setLevel(level)
        handler.setFormatter(JsonLineFormatter())
        handler._decisiondoc_json = True  # type: ignore[attr-defined]
        root.handlers = [handler]

    access_logger = logging.getLogger("uvicorn.access")
    for handler in access_logger.handlers:
        handler.setLevel(level)
        handler.setFormatter(JsonLineFormatter())
        handler._decisiondoc_json = True  # type: ignore[attr-defined]


def log_event(logger: logging.Logger, event: dict[str, Any]) -> None:
    safe_event = dict(event)
    safe_event.setdefault("ts", datetime.now(timezone.utc).isoformat())
    safe_event.setdefault("level", "INFO")
    logger.info(safe_event)
