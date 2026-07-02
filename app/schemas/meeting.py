"""Meeting recording import/transcription/document-generation schemas."""

from pydantic import BaseModel, ConfigDict, Field


class ImportVoiceBriefDocumentRequest(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    recording_id: str = Field(..., min_length=1)
    revision_id: str | None = Field(default=None, min_length=1)


class TranscribeMeetingRecordingRequest(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    language: str | None = Field(default=None, min_length=2, max_length=16)


class GenerateMeetingRecordingDocumentsRequest(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    bundle_types: list[str] = Field(
        default_factory=lambda: ["meeting_minutes_kr", "project_report_kr"],
        min_length=1,
    )
    context_note: str = ""
