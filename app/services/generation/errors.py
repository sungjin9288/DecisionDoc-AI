"""Provider/generation exception types and provider-failure inspection helpers.

``ProviderFailedError`` wraps any exception raised while calling an LLM
provider. The helper functions below walk the ``__cause__``/``__context__``
chain of a caught exception to recover retry-after hints, provider error
codes, and rate-limit signals without depending on any specific provider
SDK's exception hierarchy.
"""
from __future__ import annotations


class ProviderFailedError(Exception):
    pass


def iter_exception_chain(exc: BaseException) -> list[BaseException]:
    """Return the exception chain for *exc* following cause/context links."""
    chain: list[BaseException] = []
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        chain.append(current)
        seen.add(id(current))
        current = getattr(current, "__cause__", None) or getattr(current, "__context__", None)
    return chain


def provider_failure_retry_after_seconds(exc: BaseException) -> int | None:
    """Extract retry-after seconds from a provider exception chain when present."""
    for candidate in iter_exception_chain(exc):
        for headers in (
            getattr(candidate, "headers", None),
            getattr(getattr(candidate, "response", None), "headers", None),
        ):
            if headers is None or not hasattr(headers, "get"):
                continue
            raw = headers.get("retry-after") or headers.get("Retry-After")
            if raw is None:
                continue
            try:
                seconds = int(float(str(raw).strip()))
            except (TypeError, ValueError):
                continue
            if seconds >= 0:
                return seconds
    return None


def provider_failure_error_code(exc: BaseException) -> str | None:
    """Extract a provider-specific error code such as insufficient_quota."""
    for candidate in iter_exception_chain(exc):
        body = getattr(candidate, "body", None)
        if isinstance(body, dict):
            error = body.get("error")
            if isinstance(error, dict):
                for key in ("code", "type"):
                    value = error.get(key)
                    if isinstance(value, str) and value.strip():
                        return value.strip()
        response = getattr(candidate, "response", None)
        headers = getattr(response, "headers", None)
        if headers is not None and hasattr(headers, "get"):
            value = headers.get("x-error-code") or headers.get("X-Error-Code")
            if isinstance(value, str) and value.strip():
                return value.strip()
        message = str(candidate).lower()
        if "insufficient_quota" in message:
            return "insufficient_quota"
        if "rate_limit_exceeded" in message:
            return "rate_limit_exceeded"
    return None


def is_provider_rate_limited(exc: BaseException) -> bool:
    """Return True when the provider exception chain indicates HTTP 429/rate limiting."""
    for candidate in iter_exception_chain(exc):
        if getattr(candidate, "status_code", None) == 429:
            return True
        if getattr(getattr(candidate, "response", None), "status_code", None) == 429:
            return True
        message = str(candidate).lower()
        if "too many requests" in message or "rate limit" in message or "429" in message:
            return True
    return False


class EvalLintFailedError(Exception):
    def __init__(self, errors: list[str]) -> None:
        super().__init__("Eval lint failed.")
        self.errors = errors


class BundleNotSupportedError(Exception):
    """Raised when a requested operation does not support the given bundle_type."""

    def __init__(self, bundle_type: str, operation: str) -> None:
        super().__init__(f"Bundle '{bundle_type}' is not supported for '{operation}'.")
        self.bundle_type = bundle_type
        self.operation = operation
