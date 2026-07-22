"""Authentication and user management schemas."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


# ── Auth schemas ───────────────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    username: str
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str


class RevokeAuthSessionRequest(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    session_id: str = Field(
        ...,
        min_length=32,
        max_length=32,
        pattern=r"^[0-9a-f]{32}$",
    )


class RevokeOtherAuthSessionsRequest(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    confirm: Literal[True]


class RevokeAllAuthSessionsRequest(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    confirm: Literal[True]


class UpdateMyProfileRequest(BaseModel):
    display_name: str | None = None
    email: str | None = None


class CreateUserRequest(BaseModel):
    username: str
    display_name: str
    email: str
    password: str
    role: str = "member"
    job_title: str = ""
    assigned_ai_profiles: list[str] = Field(default_factory=list)


class UpdateUserRequest(BaseModel):
    display_name: str | None = None
    email: str | None = None
    role: str | None = None
    is_active: bool | None = None
    job_title: str | None = None
    assigned_ai_profiles: list[str] | None = None
