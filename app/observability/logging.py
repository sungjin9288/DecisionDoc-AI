import json
import logging
import os
from datetime import datetime, timezone
from typing import Any


class JsonLineFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        if isinstance(record.msg, dict):
            payload = dict(record.msg)
        else:
            payload = {"message": record.getMessage()}

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
