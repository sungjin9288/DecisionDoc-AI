"""Authentication and user management schemas."""

from pydantic import BaseModel, Field


# ── Auth schemas ───────────────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    username: str
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str


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
