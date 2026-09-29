"""Read-only resolution of the style profile bound to one generation request."""
from __future__ import annotations

from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import string
from typing import TYPE_CHECKING

from app.services.generation.errors import (
    StyleProfileNotFoundError,
    StyleSnapshotInvalidError,
)
from app.tenant import require_tenant_id

if TYPE_CHECKING:
    from app.storage.state_backend import StateBackend


STYLE_SNAPSHOT_KEY = "_style_snapshot"
_EMPTY_STYLE_VERSION = "style-snapshot-v1:none"


def resolve_style_snapshot(
    *,
    style_profile_id: str | None,
    bundle_id: str | None,
    tenant_id: str | None,
    data_dir: str | Path | None = None,
    state_backend: "StateBackend | None" = None,
) -> dict[str, str | None]:
    """Resolve one style once, returning only cache- and prompt-safe data.

    An explicit selection is fail-closed. Omitting the selection uses the active
    tenant default when present, otherwise it records a stable no-style snapshot.
    """
    try:
        resolved_tenant_id = require_tenant_id(tenant_id)
    except ValueError:
        if style_profile_id is not None:
            raise StyleProfileNotFoundError from None
        return {"version": _EMPTY_STYLE_VERSION, "id": None, "prompt": ""}

    from app.services.style_analyzer import build_style_prompt
    from app.storage.style_store import get_style_store

    store = get_style_store(
        resolved_tenant_id,
        data_dir=data_dir,
        backend=state_backend,
    )
    profile = (
        store.get(style_profile_id)
        if style_profile_id is not None
        else store.get_default()
    )
    if profile is None:
        if style_profile_id is not None:
            raise StyleProfileNotFoundError
        return {"version": _EMPTY_STYLE_VERSION, "id": None, "prompt": ""}

    serialized_profile = json.dumps(
        asdict(profile),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    profile_version = hashlib.sha256(serialized_profile.encode("utf-8")).hexdigest()
    return {
        "version": f"style-snapshot-v1:{profile_version}",
        "id": profile.profile_id,
        "prompt": build_style_prompt(profile, bundle_id=bundle_id),
    }


def style_prompt_from_snapshot(snapshot: object) -> str:
    """Return the immutable prompt block from a previously resolved snapshot."""
    if not isinstance(snapshot, dict):
        raise StyleSnapshotInvalidError
    version = snapshot.get("version")
    profile_id = snapshot.get("id")
    prompt = snapshot.get("prompt")
    is_empty_snapshot = version == _EMPTY_STYLE_VERSION
    is_profile_snapshot = (
        isinstance(version, str)
        and version.startswith("style-snapshot-v1:")
        and len(version.removeprefix("style-snapshot-v1:")) == 64
        and all(character in string.hexdigits for character in version.removeprefix("style-snapshot-v1:"))
    )
    if (
        set(snapshot) != {"version", "id", "prompt"}
        or not (is_empty_snapshot or is_profile_snapshot)
        or (is_empty_snapshot and (profile_id is not None or prompt != ""))
        or (is_profile_snapshot and (not isinstance(profile_id, str) or not profile_id))
        or not isinstance(prompt, str)
    ):
        raise StyleSnapshotInvalidError
    return prompt
