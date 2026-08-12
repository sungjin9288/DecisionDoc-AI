import json
import logging
import os
import re
import traceback
from datetime import datetime, timezone
from typing import Any


REDACTED = "[REDACTED]"
_QUERY_PARAMETER = re.compile(r"([?&])([^=&#\s]+)=([^&#\s\"']*)")
_AUTHORIZATION_VALUE = re.compile(
    r"(?P<prefix>\bauthorization\s*[:=]\s*(?:[a-z][a-z0-9_-]*\s+)?)"
    r"(?P<value>\"[^\"]*\"|'[^']*'|[^\s,;&?#]+)",
    re.IGNORECASE,
)
_SENSITIVE_ASSIGNMENT = re.compile(
    r"(?P<prefix>\b(?:service[_-]?key|(?:[a-z0-9]+[_-])*"
    r"(?:api[_-]?key|password|secret|signature|token))\s*[:=]\s*)"
    r"(?P<value>\"[^\"]*\"|'[^']*'|[^\s,;&?#]+)",
    re.IGNORECASE,
)


def _is_sensitive_field(name: object) -> bool:
    normalized = re.sub(r"[^a-z0-9]", "", str(name).lower())
    return normalized in {"authorization", "servicekey"} or normalized.endswith(
        ("apikey", "password", "secret", "signature", "token")
    )


def _redact_sensitive_text(value: str) -> str:
    def replace_query_parameter(match: re.Match[str]) -> str:
        separator, name, raw_value = match.groups()
        if not _is_sensitive_field(name):
            return match.group(0)
        return f"{separator}{name}={REDACTED}" if raw_value else match.group(0)

    value = _QUERY_PARAMETER.sub(replace_query_parameter, value)
    value = _AUTHORIZATION_VALUE.sub(
        lambda match: f"{match.group('prefix')}{REDACTED}",
        value,
    )
    return _SENSITIVE_ASSIGNMENT.sub(
        lambda match: f"{match.group('prefix')}{REDACTED}",
        value,
    )


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
            return

    handler = logging.StreamHandler()
    handler.setLevel(level)
    handler.setFormatter(JsonLineFormatter())
    handler._decisiondoc_json = True  # type: ignore[attr-defined]
    root.handlers = [handler]


def log_event(logger: logging.Logger, event: dict[str, Any]) -> None:
    safe_event = dict(event)
    safe_event.setdefault("ts", datetime.now(timezone.utc).isoformat())
    safe_event.setdefault("level", "INFO")
    logger.info(safe_event)
