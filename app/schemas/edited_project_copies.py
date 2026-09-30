"""Strict input for saving a separately identified edited project document."""

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.visual_assets import EditedDocInput


class SaveEditedCopyRequest(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    operation_id: str
    parent_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    title: str = Field(min_length=1, max_length=200)
    docs: list[EditedDocInput] = Field(min_length=1, max_length=100)

    @field_validator("operation_id")
    @classmethod
    def canonical_operation(cls, value: str) -> str:
        if str(UUID(value)) != value:
            raise ValueError("operation_id must be a canonical UUID")
        return value

    @field_validator("title")
    @classmethod
    def nonblank_title(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("title cannot be blank")
        return value

    @field_validator("docs")
    @classmethod
    def valid_documents(cls, docs: list[EditedDocInput]) -> list[EditedDocInput]:
        types = [doc.doc_type for doc in docs]
        if len(set(types)) != len(types) or any(not kind.strip() for kind in types):
            raise ValueError("document types must be nonblank and unique")
        if any(not doc.markdown.strip() for doc in docs):
            raise ValueError("document content cannot be blank")
        if sum(len(doc.markdown.encode("utf-8")) for doc in docs) > 5_000_000:
            raise ValueError("document content exceeds 5 MB")
        return docs


class EditedCopyLineage(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    actor_id: str = Field(min_length=1)
    parent_id: str = Field(min_length=1)
    parent_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    operation_id: str
    request_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    content_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
