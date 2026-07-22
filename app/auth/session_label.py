"""Validation shared by auth-session API and persisted state."""

from __future__ import annotations

import unicodedata


MAX_AUTH_SESSION_LABEL_LENGTH = 40
_ALLOWED_FORMAT_CHARACTERS = frozenset({"\u200c", "\u200d"})


def _is_display_control(character: str) -> bool:
    category = unicodedata.category(character)
    if category in {"Cc", "Cs", "Zl", "Zp"}:
        return True
    return category == "Cf" and character not in _ALLOWED_FORMAT_CHARACTERS


def normalize_auth_session_label(label: object) -> str | None:
    """Return a trimmed label that is safe to render as one line of text."""
    if label is None:
        return None
    if not isinstance(label, str):
        raise ValueError("label must be a string or null")

    if any(_is_display_control(character) for character in label):
        raise ValueError("label must not contain display control characters")

    normalized = label.strip()
    if not normalized:
        raise ValueError("label must not be empty")
    if len(normalized) > MAX_AUTH_SESSION_LABEL_LENGTH:
        raise ValueError(
            f"label must be at most {MAX_AUTH_SESSION_LABEL_LENGTH} characters"
        )
    return normalized


def require_canonical_auth_session_label(label: object) -> str | None:
    """Validate a persisted label without silently rewriting its bytes."""
    normalized = normalize_auth_session_label(label)
    if normalized != label:
        raise ValueError("label must be a canonical string or null")
    return normalized
