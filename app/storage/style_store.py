"""Tenant-scoped custom tone and style profile storage."""

from __future__ import annotations

import copy
import json
import logging
import os
import threading
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.storage.state_backend import StateBackend, get_state_backend
from app.tenant import require_tenant_id

_log = logging.getLogger(__name__)

_style_locks: dict[tuple[Any, ...], threading.RLock] = {}
_style_locks_guard = threading.Lock()
_style_stores: dict[tuple[Any, ...], "StyleStore"] = {}
_style_stores_guard = threading.Lock()


class StyleStoreError(RuntimeError):
    """Raised when persisted style profile state cannot be trusted."""


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


class StyleStore:
    """Read and update one tenant's style profiles."""

    _PROFILE_FIELDS = {
        "profile_id",
        "tenant_id",
        "name",
        "description",
        "tone_guide",
        "examples",
        "bundle_overrides",
        "is_default",
        "created_by",
        "created_at",
        "updated_at",
    }
    _SYSTEM_FIELDS = {"is_system", "few_shot_example", "avatar_color"}
    _TONE_FIELDS = {
        "formality",
        "density",
        "perspective",
        "custom_rules",
        "forbidden_words",
        "preferred_words",
    }
    _EXAMPLE_FIELDS = {
        "example_id",
        "source_filename",
        "bundle_id",
        "extracted_patterns",
        "sample_sentences",
        "uploaded_at",
        "uploaded_by",
    }

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

    @staticmethod
    def _input_identifier(value: object, *, field_name: str) -> str:
        if (
            not isinstance(value, str)
            or not value
            or value != value.strip()
            or any(ord(character) < 32 or ord(character) == 127 for character in value)
        ):
            raise ValueError(f"Invalid {field_name}")
        return value

    @staticmethod
    def _persisted_identifier(value: object, *, field_name: str) -> str:
        try:
            return StyleStore._input_identifier(value, field_name=field_name)
        except ValueError as exc:
            raise StyleStoreError(f"Invalid {field_name}") from exc

    @staticmethod
    def _timestamp(value: object, *, field_name: str) -> str:
        if not isinstance(value, str) or not value:
            raise StyleStoreError(f"Invalid {field_name}")
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError as exc:
            raise StyleStoreError(f"Invalid {field_name}") from exc
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise StyleStoreError(f"Invalid {field_name}")
        return value

    @staticmethod
    def _string_list(value: object, *, field_name: str) -> list[str]:
        if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
            raise StyleStoreError(f"Invalid {field_name}")
        return value

    def _validate_tone(self, value: object) -> dict[str, Any]:
        if not isinstance(value, dict) or set(value) != self._TONE_FIELDS:
            raise StyleStoreError("Invalid tone guide")
        for field_name in ("formality", "density", "perspective"):
            if not isinstance(value.get(field_name), str):
                raise StyleStoreError("Invalid tone guide")
        for field_name in ("custom_rules", "forbidden_words", "preferred_words"):
            self._string_list(value.get(field_name), field_name=f"tone {field_name}")
        return value

    def _validate_example(self, value: object) -> dict[str, Any]:
        if not isinstance(value, dict) or set(value) != self._EXAMPLE_FIELDS:
            raise StyleStoreError("Invalid style example")
        self._persisted_identifier(value.get("example_id"), field_name="example identity")
        self._persisted_identifier(
            value.get("source_filename"), field_name="example source filename"
        )
        bundle_id = value.get("bundle_id")
        if bundle_id is not None:
            self._persisted_identifier(bundle_id, field_name="example bundle identity")
        self._string_list(
            value.get("extracted_patterns"), field_name="example extracted patterns"
        )
        self._string_list(
            value.get("sample_sentences"), field_name="example sample sentences"
        )
        self._timestamp(value.get("uploaded_at"), field_name="example upload timestamp")
        self._persisted_identifier(
            value.get("uploaded_by"), field_name="example uploader identity"
        )
        return value

    def _owns(self, record: object) -> bool:
        return isinstance(record, dict) and record.get("tenant_id") == self._tenant_id

    def _validate_owned_profile(
        self,
        storage_key: str,
        profile: dict[str, Any],
    ) -> dict[str, Any]:
        is_system = profile.get("is_system") is True
        expected_fields = self._PROFILE_FIELDS | (self._SYSTEM_FIELDS if is_system else set())
        if set(profile) != expected_fields:
            raise StyleStoreError("Invalid style profile fields")

        profile_id = self._persisted_identifier(
            profile.get("profile_id"), field_name="style profile identity"
        )
        if storage_key != profile_id:
            raise StyleStoreError("Style profile storage identity mismatch")
        if profile.get("tenant_id") != self._tenant_id:
            raise StyleStoreError("Style profile tenant ownership mismatch")
        self._persisted_identifier(profile.get("name"), field_name="style profile name")
        if not isinstance(profile.get("description"), str):
            raise StyleStoreError("Invalid style profile description")
        self._validate_tone(profile.get("tone_guide"))

        examples = profile.get("examples")
        if not isinstance(examples, list):
            raise StyleStoreError("Invalid style profile examples")
        example_ids: set[str] = set()
        for example in examples:
            validated_example = self._validate_example(example)
            example_id = validated_example["example_id"]
            if example_id in example_ids:
                raise StyleStoreError("Duplicate style example identity")
            example_ids.add(example_id)

        overrides = profile.get("bundle_overrides")
        if not isinstance(overrides, dict):
            raise StyleStoreError("Invalid style bundle overrides")
        for bundle_id, tone in overrides.items():
            self._persisted_identifier(bundle_id, field_name="style bundle identity")
            self._validate_tone(tone)

        if not isinstance(profile.get("is_default"), bool):
            raise StyleStoreError("Invalid default style flag")
        self._persisted_identifier(
            profile.get("created_by"), field_name="style profile creator identity"
        )
        created_at = self._timestamp(
            profile.get("created_at"), field_name="style profile created timestamp"
        )
        updated_at = self._timestamp(
            profile.get("updated_at"), field_name="style profile updated timestamp"
        )
        if datetime.fromisoformat(updated_at) < datetime.fromisoformat(created_at):
            raise StyleStoreError("Invalid style profile update timestamp")

        if is_system:
            if profile.get("is_system") is not True:
                raise StyleStoreError("Invalid system style flag")
            if not isinstance(profile.get("few_shot_example"), str):
                raise StyleStoreError("Invalid system style example")
            avatar_color = profile.get("avatar_color")
            if (
                not isinstance(avatar_color, str)
                or len(avatar_color) != 7
                or not avatar_color.startswith("#")
                or any(character not in "0123456789abcdefABCDEF" for character in avatar_color[1:])
            ):
                raise StyleStoreError("Invalid system style avatar color")
        return profile

    def _validate_state(self, state: object) -> dict[str, dict[str, Any]]:
        if not isinstance(state, dict):
            raise StyleStoreError("Invalid style profile state")

        default_count = 0
        for storage_key, profile in state.items():
            if not isinstance(profile, dict):
                raise StyleStoreError("Invalid style profile record")
            stored_tenant_id = profile.get("tenant_id")
            if not isinstance(stored_tenant_id, str) or not stored_tenant_id:
                raise StyleStoreError("Invalid style profile tenant identity")
            if stored_tenant_id != self._tenant_id:
                continue
            self._validate_owned_profile(storage_key, profile)
            if profile["is_default"]:
                default_count += 1
        if default_count > 1:
            raise StyleStoreError("Multiple default style profiles")
        return state

    def _load(self) -> dict[str, dict[str, Any]]:
        raw = self._backend.read_text(self._relative_path)
        if raw is None:
            return {}
        try:
            state = json.loads(raw, object_pairs_hook=_unique_object)
        except (json.JSONDecodeError, TypeError, StyleStoreError) as exc:
            raise StyleStoreError("Invalid style profile state document") from exc
        return self._validate_state(state)

    def _save(self, state: dict[str, dict[str, Any]]) -> None:
        validated = self._validate_state(state)
        self._backend.write_text(
            self._relative_path,
            json.dumps(validated, ensure_ascii=False, indent=2),
        )

    def _require_owned(
        self,
        state: dict[str, dict[str, Any]],
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
        self._validate_owned_profile(profile.profile_id, record)

        with self._lock:
            state = self._load()
            if profile.profile_id in state:
                raise StyleStoreError("Duplicate style profile identity")
            if not any(self._owns(item) for item in state.values()):
                profile.is_default = True
                record["is_default"] = True
            state[profile.profile_id] = record
            self._save(state)
        return profile

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
        with self._lock:
            state = self._load()
            self._require_owned(state, profile_id)
            now = _now_iso()
            for current_id, profile in state.items():
                if not self._owns(profile):
                    continue
                profile["is_default"] = current_id == profile_id
                profile["updated_at"] = now
            self._save(state)

    def update_tone_guide(
        self,
        profile_id: str,
        tone_guide: ToneGuide,
    ) -> StyleProfile:
        tone = asdict(tone_guide)
        self._validate_tone(tone)
        with self._lock:
            state = self._load()
            profile = self._require_owned(state, profile_id)
            profile["tone_guide"] = tone
            profile["updated_at"] = _now_iso()
            self._save(state)
            return _profile_from_dict(profile)

    def set_bundle_override(
        self,
        profile_id: str,
        bundle_id: str,
        tone_guide: ToneGuide,
    ) -> None:
        self._input_identifier(bundle_id, field_name="style bundle identity")
        tone = asdict(tone_guide)
        self._validate_tone(tone)
        with self._lock:
            state = self._load()
            profile = self._require_owned(state, profile_id)
            profile["bundle_overrides"][bundle_id] = tone
            profile["updated_at"] = _now_iso()
            self._save(state)

    def remove_bundle_override(self, profile_id: str, bundle_id: str) -> None:
        self._input_identifier(bundle_id, field_name="style bundle identity")
        with self._lock:
            state = self._load()
            profile = self._require_owned(state, profile_id)
            if bundle_id not in profile["bundle_overrides"]:
                return
            profile["bundle_overrides"].pop(bundle_id)
            profile["updated_at"] = _now_iso()
            self._save(state)

    def add_example(self, profile_id: str, example: StyleExample) -> None:
        record = asdict(example)
        self._validate_example(record)
        with self._lock:
            state = self._load()
            profile = self._require_owned(state, profile_id)
            if any(
                item["example_id"] == example.example_id
                for item in profile["examples"]
            ):
                raise StyleStoreError("Duplicate style example identity")
            profile["examples"].append(record)
            profile["updated_at"] = _now_iso()
            self._save(state)

    def remove_example(self, profile_id: str, example_id: str) -> None:
        self._input_identifier(example_id, field_name="style example identity")
        with self._lock:
            state = self._load()
            profile = self._require_owned(state, profile_id)
            remaining = [
                item
                for item in profile["examples"]
                if item["example_id"] != example_id
            ]
            if len(remaining) == len(profile["examples"]):
                return
            profile["examples"] = remaining
            profile["updated_at"] = _now_iso()
            self._save(state)

    def delete(self, profile_id: str) -> None:
        with self._lock:
            state = self._load()
            if not self._owns(state.get(profile_id)):
                return
            state.pop(profile_id)
            self._save(state)

    def is_system(self, profile_id: str) -> bool:
        with self._lock:
            state = self._load()
        profile = state.get(profile_id)
        return bool(self._owns(profile) and profile.get("is_system") is True)

    def initialize_defaults(self) -> None:
        """Add missing built-in profiles without changing existing records."""
        from app.storage.default_styles import DEFAULT_STYLE_PROFILES

        with self._lock:
            state = self._load()
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
                now = _now_iso()
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
                        "custom_rules": copy.copy(default_profile.get("custom_rules", [])),
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
                    "created_at": now,
                    "updated_at": now,
                }
                self._validate_owned_profile(profile_id, entry)
                state[profile_id] = entry
                has_default = has_default or is_default
                added += 1

            if added:
                self._save(state)
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
