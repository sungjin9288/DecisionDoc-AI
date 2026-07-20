"""Tenant-scoped custom tone and style profile storage."""

from __future__ import annotations

import copy
import json
import logging
import os
import secrets
import threading
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, TypeVar

from app.storage.conditional_state import persist_text_if_current
from app.storage.state_backend import StateBackend, StateBackendError, get_state_backend
from app.storage.style_store_validation import (
    INCARNATION_FIELD as _INCARNATION_FIELD,
    MAX_TRACKED_MUTATIONS as _MAX_TRACKED_MUTATIONS,
    MUTATION_IDS_FIELD as _MUTATION_IDS_FIELD,
    STATE_METADATA_KEY as _STATE_METADATA_KEY,
    StyleStoreError,
    StyleStoreValidationMixin,
)
from app.tenant import require_tenant_id

_log = logging.getLogger(__name__)

_style_locks: dict[tuple[Any, ...], threading.RLock] = {}
_style_locks_guard = threading.Lock()
_style_stores: dict[tuple[Any, ...], "StyleStore"] = {}
_style_stores_guard = threading.Lock()
_MAX_MUTATION_ATTEMPTS = 32
_MutationResult = TypeVar("_MutationResult")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class ToneGuide:
    """User-written tone instructions for document generation."""

    formality: str = ""
    density: str = ""
    perspective: str = ""
    custom_rules: list[str] = field(default_factory=list)
    forbidden_words: list[str] = field(default_factory=list)
    preferred_words: list[str] = field(default_factory=list)


@dataclass
class StyleExample:
    """Style patterns extracted from an uploaded document."""

    example_id: str
    source_filename: str
    bundle_id: str | None
    extracted_patterns: list[str]
    sample_sentences: list[str]
    uploaded_at: str
    uploaded_by: str


@dataclass
class StyleProfile:
    """A named collection of tone preferences and style examples."""

    profile_id: str
    tenant_id: str
    name: str
    description: str
    tone_guide: ToneGuide
    examples: list[StyleExample]
    bundle_overrides: dict[str, ToneGuide]
    is_default: bool
    created_by: str
    created_at: str
    updated_at: str
    is_system: bool = False
    few_shot_example: str = ""
    avatar_color: str = ""


def _tone_from_dict(data: dict[str, Any]) -> ToneGuide:
    return ToneGuide(
        formality=data["formality"],
        density=data["density"],
        perspective=data["perspective"],
        custom_rules=list(data["custom_rules"]),
        forbidden_words=list(data["forbidden_words"]),
        preferred_words=list(data["preferred_words"]),
    )


def _example_from_dict(data: dict[str, Any]) -> StyleExample:
    return StyleExample(
        example_id=data["example_id"],
        source_filename=data["source_filename"],
        bundle_id=data["bundle_id"],
        extracted_patterns=list(data["extracted_patterns"]),
        sample_sentences=list(data["sample_sentences"]),
        uploaded_at=data["uploaded_at"],
        uploaded_by=data["uploaded_by"],
    )


def _profile_from_dict(data: dict[str, Any]) -> StyleProfile:
    return StyleProfile(
        profile_id=data["profile_id"],
        tenant_id=data["tenant_id"],
        name=data["name"],
        description=data["description"],
        tone_guide=_tone_from_dict(data["tone_guide"]),
        examples=[_example_from_dict(item) for item in data["examples"]],
        bundle_overrides={
            bundle_id: _tone_from_dict(tone)
            for bundle_id, tone in data["bundle_overrides"].items()
        },
        is_default=data["is_default"],
        created_by=data["created_by"],
        created_at=data["created_at"],
        updated_at=data["updated_at"],
        is_system=data.get("is_system", False),
        few_shot_example=data.get("few_shot_example", ""),
        avatar_color=data.get("avatar_color", ""),
    )


def _profile_to_dict(profile: StyleProfile) -> dict[str, Any]:
    return {
        "profile_id": profile.profile_id,
        "tenant_id": profile.tenant_id,
        "name": profile.name,
        "description": profile.description,
        "tone_guide": asdict(profile.tone_guide),
        "examples": [asdict(example) for example in profile.examples],
        "bundle_overrides": {
            bundle_id: asdict(tone)
            for bundle_id, tone in profile.bundle_overrides.items()
        },
        "is_default": profile.is_default,
        "created_by": profile.created_by,
        "created_at": profile.created_at,
        "updated_at": profile.updated_at,
    }


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise StyleStoreError(f"Duplicate key in style profile state: {key!r}")
        result[key] = value
    return result


def _lock_for_state(
    backend: StateBackend,
    *,
    path: Path,
    relative_path: str,
) -> threading.RLock:
    if backend.kind == "local":
        backend_root = getattr(backend, "root", None)
        state_path = (
            Path(backend_root).resolve() / relative_path
            if backend_root is not None
            else path.resolve()
        )
        key: tuple[Any, ...] = ("local", state_path)
    elif backend.kind == "s3":
        key = (
            "s3",
            getattr(backend, "bucket", ""),
            getattr(backend, "prefix", ""),
            relative_path,
        )
    else:
        key = (backend.kind, id(backend), relative_path)
    with _style_locks_guard:
        return _style_locks.setdefault(key, threading.RLock())


def _backend_cache_key(
    backend: StateBackend,
    *,
    data_dir: Path,
    explicit_backend: bool,
) -> tuple[Any, ...]:
    if explicit_backend:
        return (backend.kind, id(backend))
    if backend.kind == "s3":
        return (
            "s3",
            getattr(backend, "bucket", ""),
            getattr(backend, "prefix", ""),
        )
    return ("local", data_dir.resolve())


class StyleStore(StyleStoreValidationMixin):
    """Read and update one tenant's style profiles."""

    def __init__(
        self,
        tenant_id: str,
        data_dir: str | Path | None = None,
        *,
        backend: StateBackend | None = None,
    ) -> None:
        self._tenant_id = require_tenant_id(tenant_id)
        self._data_dir = Path(data_dir or os.getenv("DATA_DIR", "data"))
        self._relative_path = str(
            Path("tenants") / self._tenant_id / "style_profiles.json"
        )
        self._path = self._data_dir / self._relative_path
        self._backend = backend or get_state_backend(data_dir=self._data_dir)
        self._lock = _lock_for_state(
            self._backend,
            path=self._path,
            relative_path=self._relative_path,
        )

    def _read_state(self) -> tuple[str | None, dict[str, Any]]:
        try:
            raw = self._backend.read_text(self._relative_path)
        except (StateBackendError, UnicodeError) as exc:
            raise StyleStoreError("Invalid style profile state document") from exc
        if raw is None:
            return None, {}
        if not raw.strip():
            raise StyleStoreError("Invalid style profile state document")
        try:
            state = json.loads(raw, object_pairs_hook=_unique_object)
        except (json.JSONDecodeError, TypeError, StyleStoreError) as exc:
            raise StyleStoreError("Invalid style profile state document") from exc
        return raw, self._validate_state(state)

    def _load(self) -> dict[str, Any]:
        state = self._read_state()[1]
        return {
            profile_id: profile
            for profile_id, profile in state.items()
            if profile_id != _STATE_METADATA_KEY
        }

    def _persist_if_current(
        self,
        *,
        expected: str | None,
        state: dict[str, Any],
        mutation_id: str,
    ) -> bool:
        validated = self._validate_state(state)
        payload = json.dumps(validated, ensure_ascii=False, indent=2)

        def decode(raw: str) -> dict[str, Any]:
            if not raw.strip():
                raise StyleStoreError("Invalid style profile state document")
            try:
                observed = json.loads(raw, object_pairs_hook=_unique_object)
            except (json.JSONDecodeError, TypeError, StyleStoreError) as exc:
                raise StyleStoreError("Invalid style profile state document") from exc
            return self._validate_state(observed)

        try:
            return persist_text_if_current(
                backend=self._backend,
                relative_path=self._relative_path,
                expected=expected,
                replacement=payload,
                decode=decode,
                committed=lambda observed: mutation_id in self._mutation_ids(observed),
                decode_errors=(StyleStoreError,),
            )
        except StateBackendError as exc:
            raise StyleStoreError("Failed to persist style profile state") from exc

    def _mutate(
        self,
        mutation_id: str,
        change: Callable[[dict[str, Any]], tuple[_MutationResult, bool]],
    ) -> _MutationResult:
        for _ in range(_MAX_MUTATION_ATTEMPTS):
            expected, state = self._read_state()
            result, changed = change(state)
            if not changed:
                return result

            mutation_ids = self._mutation_ids(state)
            mutation_ids.append(mutation_id)
            state[_STATE_METADATA_KEY] = {
                _MUTATION_IDS_FIELD: mutation_ids[-_MAX_TRACKED_MUTATIONS:]
            }
            if self._persist_if_current(
                expected=expected,
                state=state,
                mutation_id=mutation_id,
            ):
                return result
        raise StyleStoreError(
            "Style profile state changed too many times to persist safely"
        )

    @staticmethod
    def _updated_at(*profiles: dict[str, Any]) -> str:
        now = _now_iso()
        latest = max(
            profiles,
            key=lambda profile: datetime.fromisoformat(profile["updated_at"]),
        )["updated_at"]
        if datetime.fromisoformat(now) < datetime.fromisoformat(latest):
            return latest
        return now

    def _require_owned(
        self,
        state: dict[str, Any],
        profile_id: str,
    ) -> dict[str, Any]:
        profile = state.get(profile_id)
        if not self._owns(profile):
            raise ValueError(f"프로필을 찾을 수 없습니다: {profile_id}")
        return profile

    def create(self, name: str, description: str, created_by: str) -> StyleProfile:
        """Create a new empty style profile."""
        self._input_identifier(name, field_name="style profile name")
        if not isinstance(description, str):
            raise ValueError("Invalid style profile description")
        self._input_identifier(created_by, field_name="style profile creator identity")
        mutation_id = secrets.token_hex(16)
        now = _now_iso()
        profile = StyleProfile(
            profile_id=str(uuid.uuid4()),
            tenant_id=self._tenant_id,
            name=name,
            description=description,
            tone_guide=ToneGuide(),
            examples=[],
            bundle_overrides={},
            is_default=False,
            created_by=created_by,
            created_at=now,
            updated_at=now,
        )
        record = _profile_to_dict(profile)
        record[_INCARNATION_FIELD] = secrets.token_hex(16)
        self._validate_owned_profile(profile.profile_id, record)

        def create_profile(state: dict[str, Any]) -> tuple[StyleProfile, bool]:
            if profile.profile_id in state:
                raise StyleStoreError("Duplicate style profile identity")
            candidate = copy.deepcopy(record)
            candidate["is_default"] = not any(
                self._owns(item) for item in state.values()
            )
            state[profile.profile_id] = candidate
            return _profile_from_dict(candidate), True

        with self._lock:
            return self._mutate(mutation_id, create_profile)

    def get(self, profile_id: str) -> StyleProfile | None:
        with self._lock:
            state = self._load()
        profile = state.get(profile_id)
        return _profile_from_dict(profile) if self._owns(profile) else None

    def get_default(self) -> StyleProfile | None:
        with self._lock:
            state = self._load()
        for profile in state.values():
            if self._owns(profile) and profile["is_default"]:
                return _profile_from_dict(profile)
        return None

    def list_profiles(self) -> list[StyleProfile]:
        with self._lock:
            state = self._load()
        return [
            _profile_from_dict(profile)
            for profile in state.values()
            if self._owns(profile)
        ]

    def set_default(self, profile_id: str) -> None:
        mutation_id = secrets.token_hex(16)
        target_identity: str | None = None

        def set_default_profile(state: dict[str, Any]) -> tuple[None, bool]:
            nonlocal target_identity
            target = self._require_owned(state, profile_id)
            target_identity = self._bind_profile(
                target,
                expected_identity=target_identity,
            )
            owned_profiles = [
                profile for profile in state.values() if self._owns(profile)
            ]
            updated_at = self._updated_at(*owned_profiles)
            for current_id, profile in state.items():
                if not self._owns(profile):
                    continue
                profile["is_default"] = current_id == profile_id
                profile["updated_at"] = updated_at
            return None, True

        with self._lock:
            self._mutate(mutation_id, set_default_profile)

    def update_tone_guide(
        self,
        profile_id: str,
        tone_guide: ToneGuide,
    ) -> StyleProfile:
        tone = asdict(tone_guide)
        self._validate_tone(tone)
        mutation_id = secrets.token_hex(16)
        target_identity: str | None = None

        def update_tone(state: dict[str, Any]) -> tuple[StyleProfile, bool]:
            nonlocal target_identity
            profile = self._require_owned(state, profile_id)
            target_identity = self._bind_profile(
                profile,
                expected_identity=target_identity,
            )
            profile["tone_guide"] = tone
            profile["updated_at"] = self._updated_at(profile)
            return _profile_from_dict(profile), True

        with self._lock:
            return self._mutate(mutation_id, update_tone)

    def set_bundle_override(
        self,
        profile_id: str,
        bundle_id: str,
        tone_guide: ToneGuide,
    ) -> None:
        self._input_identifier(bundle_id, field_name="style bundle identity")
        tone = asdict(tone_guide)
        self._validate_tone(tone)
        mutation_id = secrets.token_hex(16)
        target_identity: str | None = None

        def set_override(state: dict[str, Any]) -> tuple[None, bool]:
            nonlocal target_identity
            profile = self._require_owned(state, profile_id)
            target_identity = self._bind_profile(
                profile,
                expected_identity=target_identity,
            )
            profile["bundle_overrides"][bundle_id] = tone
            profile["updated_at"] = self._updated_at(profile)
            return None, True

        with self._lock:
            self._mutate(mutation_id, set_override)

    def remove_bundle_override(self, profile_id: str, bundle_id: str) -> None:
        self._input_identifier(bundle_id, field_name="style bundle identity")
        mutation_id = secrets.token_hex(16)
        target_identity: str | None = None

        def remove_override(state: dict[str, Any]) -> tuple[None, bool]:
            nonlocal target_identity
            profile = self._require_owned(state, profile_id)
            if bundle_id not in profile["bundle_overrides"]:
                return None, False
            target_identity = self._bind_profile(
                profile,
                expected_identity=target_identity,
            )
            profile["bundle_overrides"].pop(bundle_id)
            profile["updated_at"] = self._updated_at(profile)
            return None, True

        with self._lock:
            self._mutate(mutation_id, remove_override)

    def add_example(self, profile_id: str, example: StyleExample) -> None:
        record = asdict(example)
        self._validate_example(record)
        mutation_id = secrets.token_hex(16)
        target_identity: str | None = None

        def append_example(state: dict[str, Any]) -> tuple[None, bool]:
            nonlocal target_identity
            profile = self._require_owned(state, profile_id)
            target_identity = self._bind_profile(
                profile,
                expected_identity=target_identity,
            )
            if any(
                item["example_id"] == example.example_id for item in profile["examples"]
            ):
                raise StyleStoreError("Duplicate style example identity")
            profile["examples"].append(record)
            profile["updated_at"] = self._updated_at(profile)
            return None, True

        with self._lock:
            self._mutate(mutation_id, append_example)

    def remove_example(self, profile_id: str, example_id: str) -> None:
        self._input_identifier(example_id, field_name="style example identity")
        mutation_id = secrets.token_hex(16)
        target_identity: str | None = None

        def discard_example(state: dict[str, Any]) -> tuple[None, bool]:
            nonlocal target_identity
            profile = self._require_owned(state, profile_id)
            remaining = [
                item for item in profile["examples"] if item["example_id"] != example_id
            ]
            if len(remaining) == len(profile["examples"]):
                return None, False
            target_identity = self._bind_profile(
                profile,
                expected_identity=target_identity,
            )
            profile["examples"] = remaining
            profile["updated_at"] = self._updated_at(profile)
            return None, True

        with self._lock:
            self._mutate(mutation_id, discard_example)

    def delete(self, profile_id: str) -> None:
        mutation_id = secrets.token_hex(16)
        target_identity: str | None = None

        def delete_profile(state: dict[str, Any]) -> tuple[None, bool]:
            nonlocal target_identity
            profile = state.get(profile_id)
            if not self._owns(profile):
                return None, False
            target_identity = self._bind_profile(
                profile,
                expected_identity=target_identity,
            )
            state.pop(profile_id)
            return None, True

        with self._lock:
            self._mutate(mutation_id, delete_profile)

    def is_system(self, profile_id: str) -> bool:
        with self._lock:
            state = self._load()
        profile = state.get(profile_id)
        return bool(self._owns(profile) and profile.get("is_system") is True)

    def initialize_defaults(self) -> None:
        """Add missing built-in profiles without changing existing records."""
        from app.storage.default_styles import DEFAULT_STYLE_PROFILES

        mutation_id = secrets.token_hex(16)
        created_at = _now_iso()
        incarnations = {
            profile["style_id"]: secrets.token_hex(16)
            for profile in DEFAULT_STYLE_PROFILES
        }

        def add_defaults(state: dict[str, Any]) -> tuple[int, bool]:
            has_default = any(
                self._owns(profile) and profile["is_default"]
                for profile in state.values()
            )
            added = 0
            for default_profile in DEFAULT_STYLE_PROFILES:
                profile_id = default_profile["style_id"]
                if profile_id in state:
                    continue
                tone = default_profile.get("tone_guide", {})
                is_default = bool(default_profile.get("is_default") and not has_default)
                entry: dict[str, Any] = {
                    "profile_id": profile_id,
                    "tenant_id": self._tenant_id,
                    "name": default_profile["name"],
                    "description": default_profile["description"],
                    "tone_guide": {
                        "formality": tone.get("formality", ""),
                        "density": tone.get("density", ""),
                        "perspective": tone.get("perspective", ""),
                        "custom_rules": copy.copy(
                            default_profile.get("custom_rules", [])
                        ),
                        "forbidden_words": copy.copy(
                            default_profile.get("forbidden_expressions", [])
                        ),
                        "preferred_words": [],
                    },
                    "examples": [],
                    "bundle_overrides": {},
                    "is_default": is_default,
                    "is_system": True,
                    "few_shot_example": default_profile.get("few_shot_example", ""),
                    "avatar_color": default_profile.get("avatar_color", ""),
                    "created_by": "system",
                    "created_at": created_at,
                    "updated_at": created_at,
                    _INCARNATION_FIELD: incarnations[profile_id],
                }
                self._validate_owned_profile(profile_id, entry)
                state[profile_id] = entry
                has_default = has_default or is_default
                added += 1
            return added, bool(added)

        with self._lock:
            added = self._mutate(mutation_id, add_defaults)
            if added:
                _log.info(
                    "Loaded %d default style profiles for tenant=%s",
                    added,
                    self._tenant_id,
                )


def get_style_store(
    tenant_id: str,
    data_dir: str | Path | None = None,
    *,
    backend: StateBackend | None = None,
) -> StyleStore:
    """Return a cached store for one tenant and one state backend."""
    tenant_id = require_tenant_id(tenant_id)
    root = Path(data_dir or os.getenv("DATA_DIR", "data"))
    explicit_backend = backend is not None
    selected_backend = backend or get_state_backend(data_dir=root)
    key = (
        tenant_id,
        root.resolve(),
        *_backend_cache_key(
            selected_backend,
            data_dir=root,
            explicit_backend=explicit_backend,
        ),
    )
    with _style_stores_guard:
        store = _style_stores.get(key)
        if store is None:
            store = StyleStore(
                tenant_id,
                data_dir=root,
                backend=selected_backend,
            )
            _style_stores[key] = store
        return store
