"""Strict request contracts for generated-document review handoffs."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class CreateGeneratedDocumentReviewRequest(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    reviewer: str = Field(min_length=1, max_length=254)
    formats: list[str] = Field(min_length=1, max_length=5)


class CompleteGeneratedDocumentReviewRequest(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    operation_id: str = Field(
        pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
    )
    decision: Literal["accepted", "changes_requested", "rejected"]
    rationale: str = Field(min_length=1, max_length=4000)

    @field_validator("rationale")
    @classmethod
    def normalize_rationale(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized or any(
            ord(character) < 32 and character not in {"\n", "\r", "\t"}
            for character in normalized
        ) or any(ord(character) == 127 for character in normalized):
            raise ValueError("rationale is invalid")
        return normalized
