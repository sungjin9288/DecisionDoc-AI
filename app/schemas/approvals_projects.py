"""Approval workflow and project management schemas."""

from pydantic import BaseModel, Field


class CreateApprovalRequest(BaseModel):
    """Payload for POST /approvals — start an approval workflow."""
    request_id: str = ""
    bundle_id: str = ""
    title: str
    drafter: str
    docs: list[dict] = Field(default_factory=list)
    gov_options: dict | None = None


class ApprovalActionRequest(BaseModel):
    """Payload for approval action endpoints (submit, review, approve, reject)."""
    username: str
    comment: str = ""
    reviewer: str | None = None   # used in submit_for_review
    approver: str | None = None   # used in approve_review → sets approver


class UpdateApprovalDocsRequest(BaseModel):
    """Payload for PUT /approvals/{id}/docs — update docs after revision."""
    username: str
    docs: list[dict] = Field(default_factory=list)


class CreateProjectRequest(BaseModel):
    name: str = Field(..., min_length=1)
    description: str = ""
    client: str = ""
    contract_number: str = ""
    fiscal_year: int = Field(default_factory=lambda: __import__('datetime').datetime.now().year)

class UpdateProjectRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    client: str | None = None
    contract_number: str | None = None
    status: str | None = None
    tags: list[str] | None = None
    fiscal_year: int | None = None

class AddDocumentToProjectRequest(BaseModel):
    request_id: str = ""
    bundle_id: str = ""
    title: str = ""
    docs: list[dict] = Field(default_factory=list)
    approval_id: str | None = None
    tags: list[str] = Field(default_factory=list)
