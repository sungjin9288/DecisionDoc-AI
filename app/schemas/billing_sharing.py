"""Billing checkout, plan override, withdrawal, share, and invite schemas."""

from pydantic import BaseModel, Field


class CheckoutRequest(BaseModel):
    plan_id: str


class PlanOverrideRequest(BaseModel):
    plan_id: str
    reason: str = ""


class WithdrawRequest(BaseModel):
    password: str
    reason: str = ""


class CreateShareRequest(BaseModel):
    request_id: str
    title: str
    bundle_id: str = ""
    expires_days: int = 7
    project_id: str = ""
    project_document_id: str = ""
    decision_council_document_status: str = ""
    decision_council_document_status_tone: str = ""
    decision_council_document_status_copy: str = ""
    decision_council_document_status_summary: str = ""


class InviteUserRequest(BaseModel):
    tenant_id: str | None = None
    email: str = ""
    role: str = "member"
    send_email: bool = False
    job_title: str = ""
    assigned_ai_profiles: list[str] = Field(default_factory=list)


class AcceptInviteRequest(BaseModel):
    username: str
    display_name: str
    password: str
