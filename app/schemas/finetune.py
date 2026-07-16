"""Fine-tune dataset and model lifecycle request schemas."""

from pydantic import BaseModel, ConfigDict, Field


class FineTuneExportRequest(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    bundle_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=120,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]*$",
    )
    min_records: int = Field(default=10, ge=1, le=100_000)


class FineTuneTrainingTriggerRequest(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    bundle_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=120,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]*$",
    )
