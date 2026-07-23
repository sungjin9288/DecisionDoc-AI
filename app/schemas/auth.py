"""Authentication and user management schemas."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.auth.session_label import normalize_auth_session_label


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


class UpdateAuthSessionLabelRequest(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    session_id: str = Field(
        ...,
        min_length=32,
        max_length=32,
        pattern=r"^[0-9a-f]{32}$",
    )
    label: str | None

    @field_validator("label")
    @classmethod
    def normalize_label(cls, value: str | None) -> str | None:
        return normalize_auth_session_label(value)


class RevokeOtherAuthSessionsRequest(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    confirm: Literal[True]


class RevokeAllAuthSessionsRequest(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    confirm: Literal[True]


class AuthSessionRetentionRecheckRequest(BaseModel):
    """A browser-held v2 retention handoff submitted for fresh comparison."""

    model_config = ConfigDict(strict=True, extra="forbid")

    contract_version: Literal["auth-session-retention-recheck-request.v1"]
    source_handoff: dict[str, Any]
    source_handoff_sha256: str = Field(
        ...,
        min_length=64,
        max_length=64,
        pattern=r"^[a-f0-9]{64}$",
    )


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
