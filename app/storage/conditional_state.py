"""Shared conditional-write and bounded-retry primitives for state stores."""

from __future__ import annotations

from typing import Callable, TypeVar

from app.storage.state_backend import StateBackend, StateBackendError


_State = TypeVar("_State")
_Result = TypeVar("_Result")


def persist_text_if_current(
    *,
    backend: StateBackend,
    relative_path: str,
    expected: str | None,
    replacement: str,
    decode: Callable[[str], _State],
    committed: Callable[[_State], bool],
    decode_errors: tuple[type[Exception], ...],
    content_type: str = "application/json; charset=utf-8",
) -> bool:
    """Conditionally persist text and reconcile a lost success response."""
    try:
        if expected is None:
            return backend.write_text_if_absent(
                relative_path,
                replacement,
                content_type=content_type,
            )
        return backend.replace_text_if_equal(
            relative_path,
            expected=expected,
            replacement=replacement,
            content_type=content_type,
        )
    except StateBackendError:
        try:
            observed = backend.read_text(relative_path)
        except (StateBackendError, UnicodeError):
            observed = None
        if observed == replacement:
            return True
        if observed is not None:
            try:
                observed_state = decode(observed)
            except decode_errors:
                pass
            else:
                if committed(observed_state):
                    return True
        raise


def mutate_with_retry(
    *,
    read: Callable[[], tuple[str | None, _State]],
    change: Callable[[_State], tuple[_Result, bool]],
    persist: Callable[
        [str | None, _State, Callable[[_State], bool]],
        bool,
    ],
    committed: Callable[[_State], bool],
    max_attempts: int,
    conflict_error: Callable[[], Exception],
) -> _Result:
    """Apply one state mutation with a finite compare-and-swap retry loop."""
    for _ in range(max_attempts):
        expected, state = read()
        result, changed = change(state)
        if not changed:
            return result
        if persist(expected, state, committed):
            return result
    raise conflict_error()
