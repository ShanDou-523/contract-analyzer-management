"""Authentication and user API schemas."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=256)


class BootstrapRequest(BaseModel):
    organization_name: str = Field(min_length=1, max_length=200)
    organization_code: str = Field(min_length=2, max_length=100, pattern=r"^[a-zA-Z0-9_-]+$")
    username: str = Field(min_length=3, max_length=100)
    password: str = Field(min_length=10, max_length=256)
    display_name: str = Field(min_length=1, max_length=200)


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=20, max_length=256)


class PasswordChange(BaseModel):
    password: str = Field(min_length=10, max_length=256)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    username: str
    display_name: str
    email: str | None = None
    organization_id: str
    status: str
    roles: list[str]


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_at: datetime
    user: UserOut


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=100)
    password: str = Field(min_length=10, max_length=256)
    display_name: str = Field(min_length=1, max_length=200)
    email: str | None = Field(default=None, max_length=320)
    roles: list[str] = Field(default_factory=lambda: ["viewer"])


class UserUpdate(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=200)
    email: str | None = Field(default=None, max_length=320)
    status: str | None = Field(default=None, pattern=r"^(active|disabled)$")
    password: str | None = Field(default=None, min_length=10, max_length=256)
    roles: list[str] | None = None


class RoleOut(BaseModel):
    id: str
    name: str
    description: str
    organization_id: str | None
