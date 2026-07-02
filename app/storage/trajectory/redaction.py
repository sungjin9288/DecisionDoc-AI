"""Generic value helpers: redaction, hashing, dedupe, and safe filename checks."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.storage.trajectory.constants import (
    _EXPORT_FILENAME_RE,
    _FREEZE_FILENAME_RE,
    _MANIFEST_ID_RE,
    _SENSITIVE_KEY_PARTS,
    _TRAINING_APPROVAL_FILENAME_RE,
    _TRAINING_AUDIT_FILENAME_RE,
    _TRAINING_EXECUTION_REQUEST_FILENAME_RE,
)


def _redact_input(value: Any) -> Any:
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, item in value.items():
            lowered = str(key).lower()
            if any(part in lowered for part in _SENSITIVE_KEY_PARTS):
                redacted[key] = "[redacted]"
            else:
                redacted[key] = _redact_input(item)
        return redacted
    if isinstance(value, list):
        return [_redact_input(item) for item in value]
    if isinstance(value, str) and len(value) > 2000:
        digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]
        return f"{value[:300]}...[redacted_long_text sha256={digest}]"
    return value


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_label(value: str | None) -> str:
    raw = str(value or "").strip().lower()
    return "".join(ch if ch.isalnum() or ch in {"-", "_"} else "-" for ch in raw).strip("-") or "all"


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value).strip()
    return [text] if text else []


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value and value not in result:
            result.append(value)
    return result


def _json_sha256(value: dict[str, Any]) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _is_safe_export_filename(filename: str) -> bool:
    if Path(filename).name != filename:
        return False
    return bool(_EXPORT_FILENAME_RE.fullmatch(filename))


def _is_safe_freeze_filename(filename: str) -> bool:
    if Path(filename).name != filename:
        return False
    return bool(_FREEZE_FILENAME_RE.fullmatch(filename))


def _is_safe_manifest_id(manifest_id: str) -> bool:
    return bool(_MANIFEST_ID_RE.fullmatch(str(manifest_id or "")))


def _is_safe_training_approval_filename(filename: str) -> bool:
    if Path(filename).name != filename:
        return False
    return bool(_TRAINING_APPROVAL_FILENAME_RE.fullmatch(filename))


def _is_safe_training_execution_request_filename(filename: str) -> bool:
    if Path(filename).name != filename:
        return False
    return bool(_TRAINING_EXECUTION_REQUEST_FILENAME_RE.fullmatch(filename))


def _is_safe_training_audit_filename(filename: str) -> bool:
    if Path(filename).name != filename:
        return False
    return bool(_TRAINING_AUDIT_FILENAME_RE.fullmatch(filename))
