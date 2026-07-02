"""Messaging, style profile, and knowledge metadata schemas."""

from pydantic import BaseModel, ConfigDict


# ── Message schemas ────────────────────────────────────────────────────────────

class PostMessageRequest(BaseModel):
    content: str
    context_type: str = "general"
    context_id: str = "global"


class EditMessageRequest(BaseModel):
    content: str


class CreateStyleProfileRequest(BaseModel):
    name: str
    description: str = ""


class UpdateToneGuideRequest(BaseModel):
    formality: str = ""
    density: str = ""
    perspective: str = ""
    custom_rules: list[str] = []
    forbidden_words: list[str] = []
    preferred_words: list[str] = []


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
