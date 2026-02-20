from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator


class DocType(str, Enum):
    adr = "adr"
    onepager = "onepager"
    eval_plan = "eval_plan"
    ops_checklist = "ops_checklist"


def default_doc_types() -> list[DocType]:
    return [
        DocType.adr,
        DocType.onepager,
        DocType.eval_plan,
        DocType.ops_checklist,
    ]


class GenerateRequest(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    title: str = Field(..., min_length=1)
    goal: str = Field(..., min_length=1)
    context: str = ""
    constraints: str = ""
    priority: str = "maintainability > security > cost > performance > speed"
    doc_types: list[DocType] = Field(default_factory=default_doc_types, min_length=1)
    audience: str = "mixed"
    assumptions: list[str] = Field(default_factory=list)

    @field_validator("doc_types", mode="before")
    @classmethod
    def parse_doc_types(cls, value):
        if value is None:
            return value
        if not isinstance(value, list):
            return value
        return [DocType(item) if isinstance(item, str) else item for item in value]


class HealthResponse(BaseModel):
    status: str
    provider: str
    maintenance: bool | None = None


class GeneratedDoc(BaseModel):
    doc_type: DocType
    markdown: str


class GenerateResponse(BaseModel):
    request_id: str
    bundle_id: str
    title: str
    provider: str
    schema_version: str
    cache_hit: bool | None = None
    docs: list[GeneratedDoc]


class ExportedFile(BaseModel):
    doc_type: DocType
    path: str


class GenerateExportResponse(BaseModel):
    request_id: str
    bundle_id: str
    title: str
    provider: str
    schema_version: str
    cache_hit: bool | None = None
    export_dir: str
    files: list[ExportedFile]


class ErrorResponse(BaseModel):
    code: str
    message: str
    request_id: str
