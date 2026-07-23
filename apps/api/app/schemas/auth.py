from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import EmailStr, Field, field_validator

from app.models.enums import MembershipStatus, OrganizationRole, UserStatus
from app.schemas.common import ApiModel


class RegisterRequest(ApiModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)
    full_name: str = Field(min_length=1, max_length=200)
    organization_name: str | None = Field(default=None, min_length=2, max_length=160)

    @field_validator("full_name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        value = " ".join(value.split())
        if not value:
            raise ValueError("Full name is required")
        return value


class LoginRequest(ApiModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class ChangePasswordRequest(ApiModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=1, max_length=128)


class UserResponse(ApiModel):
    id: uuid.UUID
    email: EmailStr
    full_name: str
    status: UserStatus
    email_verified_at: datetime | None
    last_login_at: datetime | None
    created_at: datetime
    updated_at: datetime


class OrganizationAccessResponse(ApiModel):
    id: uuid.UUID
    name: str
    slug: str
    role: OrganizationRole
    membership_status: MembershipStatus


class MeResponse(ApiModel):
    user: UserResponse
    organizations: list[OrganizationAccessResponse]


class AccessTokenResponse(ApiModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
