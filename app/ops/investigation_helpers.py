import os
import re
from datetime import UTC, datetime
from typing import Any


def _to_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(round(value))
    return None


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        parsed = int(raw)
    except ValueError:
        return default
    if parsed <= 0:
        return default
    return parsed


def _tail_lines(text: str, limit: int = 40) -> list[str]:
    if not text:
        return []
    lines = text.splitlines()
    if len(lines) <= limit:
        return lines
    return lines[-limit:]


def _iso_utc(dt: datetime) -> str:
    return dt.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _parse_iso_utc(value: str) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _normalize_reason_for_key(reason: str) -> str:
    text = reason.replace("\r", " ").replace("\n", " ").strip().lower()
    text = re.sub(r"\s+", " ", text)
    if len(text) > 80:
        text = text[:80]
    return text


def _sanitize_reason_for_storage(reason: str) -> str:
    text = _normalize_reason_for_key(reason)
    text = re.sub(r"[^a-z0-9 .,:;!?()/_-]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > 80:
        text = text[:80]
    return text
