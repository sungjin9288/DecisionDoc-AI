"""Strict request contracts for generated-document review handoffs."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class CreateGeneratedDocumentReviewRequest(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    reviewer: str = Field(min_length=1, max_length=254)
    formats: list[str] = Field(min_length=1, max_length=5)
