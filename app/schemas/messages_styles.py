"""Messaging, style profile, and knowledge metadata schemas."""

from pydantic import BaseModel, ConfigDict, Field, field_validator


# ── Message schemas ────────────────────────────────────────────────────────────

class PostMessageRequest(BaseModel):
    content: str
    context_type: str = "general"
    context_id: str = "global"


class EditMessageRequest(BaseModel):
    content: str


class CreateStyleProfileRequest(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    name: str = Field(min_length=1)
    description: str = ""

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        if value != value.strip() or any(
            ord(character) < 32 or ord(character) == 127 for character in value
        ):
            raise ValueError("name must be a canonical non-empty string")
        return value


class CreateManualStyleExampleRequest(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    label: str = Field(min_length=1, max_length=120)
    sample_sentences: list[str] = Field(min_length=1, max_length=8)
    bundle_id: str | None = Field(default=None, min_length=1, max_length=120)

    @field_validator("label", "bundle_id")
    @classmethod
    def validate_identifier(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if value != value.strip() or any(
            ord(character) < 32 or ord(character) == 127 for character in value
        ):
            raise ValueError("value must be a canonical non-empty string")
        return value

    @field_validator("sample_sentences")
    @classmethod
    def validate_sample_sentences(cls, value: list[str]) -> list[str]:
        for sentence in value:
            if (
                not sentence
                or len(sentence) > 1000
                or sentence != sentence.strip()
                or any(
                    ord(character) < 32 or ord(character) == 127
                    for character in sentence
                )
            ):
                raise ValueError(
                    "sample sentences must be canonical strings up to 1000 characters"
                )
        return value


class UpdateToneGuideRequest(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    formality: str = ""
    density: str = ""
    perspective: str = ""
    custom_rules: list[str] = Field(default_factory=list)
    forbidden_words: list[str] = Field(default_factory=list)
    preferred_words: list[str] = Field(default_factory=list)


class UpdateKnowledgeMetadataRequest(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    tags: list[str] | None = None
    learning_mode: str | None = None
    quality_tier: str | None = None
    applicable_bundles: list[str] | None = None
    source_organization: str | None = None
    reference_year: int | None = None
    success_state: str | None = None
    notes: str | None = None
