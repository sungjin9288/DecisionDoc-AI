"""Validation and private identity rules for tenant style profile state."""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any


INCARNATION_FIELD = "_incarnation"
STATE_METADATA_KEY = ""  # Public profile identifiers reject the empty string.
MUTATION_IDS_FIELD = "_mutation_ids"
MAX_TRACKED_MUTATIONS = 64


class StyleStoreError(RuntimeError):
    """Raised when persisted style profile state cannot be trusted."""


class StyleStoreValidationMixin:
    _tenant_id: str

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
            return StyleStoreValidationMixin._input_identifier(
                value,
                field_name=field_name,
            )
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
        if not isinstance(value, list) or any(
            not isinstance(item, str) for item in value
        ):
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
        self._persisted_identifier(
            value.get("example_id"),
            field_name="example identity",
        )
        self._persisted_identifier(
            value.get("source_filename"),
            field_name="example source filename",
        )
        bundle_id = value.get("bundle_id")
        if bundle_id is not None:
            self._persisted_identifier(
                bundle_id,
                field_name="example bundle identity",
            )
        self._string_list(
            value.get("extracted_patterns"),
            field_name="example extracted patterns",
        )
        self._string_list(
            value.get("sample_sentences"),
            field_name="example sample sentences",
        )
        self._timestamp(
            value.get("uploaded_at"),
            field_name="example upload timestamp",
        )
        self._persisted_identifier(
            value.get("uploaded_by"),
            field_name="example uploader identity",
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
        expected_fields = self._PROFILE_FIELDS | (
            self._SYSTEM_FIELDS if is_system else set()
        )
        private_fields = set(profile) - expected_fields
        if not expected_fields <= set(profile) or private_fields not in (
            set(),
            {INCARNATION_FIELD},
        ):
            raise StyleStoreError("Invalid style profile fields")

        profile_id = self._persisted_identifier(
            profile.get("profile_id"),
            field_name="style profile identity",
        )
        if storage_key != profile_id:
            raise StyleStoreError("Style profile storage identity mismatch")
        if profile.get("tenant_id") != self._tenant_id:
            raise StyleStoreError("Style profile tenant ownership mismatch")
        incarnation = profile.get(INCARNATION_FIELD)
        if incarnation is not None:
            self._persisted_identifier(
                incarnation,
                field_name="style profile incarnation",
            )
        self._persisted_identifier(
            profile.get("name"),
            field_name="style profile name",
        )
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
            self._persisted_identifier(
                bundle_id,
                field_name="style bundle identity",
            )
            self._validate_tone(tone)

        if not isinstance(profile.get("is_default"), bool):
            raise StyleStoreError("Invalid default style flag")
        self._persisted_identifier(
            profile.get("created_by"),
            field_name="style profile creator identity",
        )
        created_at = self._timestamp(
            profile.get("created_at"),
            field_name="style profile created timestamp",
        )
        updated_at = self._timestamp(
            profile.get("updated_at"),
            field_name="style profile updated timestamp",
        )
        if datetime.fromisoformat(updated_at) < datetime.fromisoformat(created_at):
            raise StyleStoreError("Invalid style profile update timestamp")

        if is_system:
            if not isinstance(profile.get("few_shot_example"), str):
                raise StyleStoreError("Invalid system style example")
            avatar_color = profile.get("avatar_color")
            if (
                not isinstance(avatar_color, str)
                or len(avatar_color) != 7
                or not avatar_color.startswith("#")
                or any(
                    character not in "0123456789abcdefABCDEF"
                    for character in avatar_color[1:]
                )
            ):
                raise StyleStoreError("Invalid system style avatar color")
        return profile

    @staticmethod
    def _mutation_ids(state: dict[str, Any]) -> list[str]:
        if STATE_METADATA_KEY not in state:
            return []
        metadata = state[STATE_METADATA_KEY]
        if not isinstance(metadata, dict) or set(metadata) != {MUTATION_IDS_FIELD}:
            raise StyleStoreError("Invalid style mutation history")
        mutation_ids = metadata.get(MUTATION_IDS_FIELD)
        if (
            not isinstance(mutation_ids, list)
            or len(mutation_ids) > MAX_TRACKED_MUTATIONS
            or any(
                not isinstance(mutation_id, str) or not mutation_id
                for mutation_id in mutation_ids
            )
            or len(mutation_ids) != len(set(mutation_ids))
        ):
            raise StyleStoreError("Invalid style mutation history")
        return list(mutation_ids)

    def _validate_state(self, state: object) -> dict[str, Any]:
        if not isinstance(state, dict):
            raise StyleStoreError("Invalid style profile state")

        self._mutation_ids(state)
        default_count = 0
        for storage_key, profile in state.items():
            if storage_key == STATE_METADATA_KEY:
                continue
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

    def _profile_identity(self, profile: dict[str, Any]) -> str:
        incarnation = profile.get(INCARNATION_FIELD)
        if isinstance(incarnation, str) and incarnation:
            return incarnation
        identity = {
            "tenant_id": profile.get("tenant_id"),
            "profile_id": profile.get("profile_id"),
            "created_by": profile.get("created_by"),
            "created_at": profile.get("created_at"),
        }
        payload = json.dumps(identity, sort_keys=True, separators=(",", ":"))
        return f"legacy:{uuid.uuid5(uuid.NAMESPACE_URL, payload)}"

    def _bind_profile(
        self,
        profile: dict[str, Any],
        *,
        expected_identity: str | None,
    ) -> str:
        identity = self._profile_identity(profile)
        if expected_identity is not None and identity != expected_identity:
            raise StyleStoreError("Style profile identity changed during mutation")
        profile.setdefault(INCARNATION_FIELD, identity)
        return identity
