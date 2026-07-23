from __future__ import annotations

import re
import uuid
from datetime import datetime

from pydantic import Field, field_validator

from app.models.enums import MembershipStatus, OrganizationRole, OrganizationStatus, UserStatus
from app.schemas.common import ApiModel

SLUG_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def validate_slug(value: str) -> str:
    value = value.strip().lower()
    if not SLUG_PATTERN.fullmatch(value) or len(value) > 100:
        raise ValueError("Slug must use lowercase letters, numbers, and single hyphens")
    return value


class OrganizationCreate(ApiModel):
    name: str = Field(min_length=2, max_length=160)
    slug: str | None = Field(default=None, min_length=2, max_length=100)

    @field_validator("slug")
    @classmethod
    def slug_format(cls, value: str | None) -> str | None:
        return validate_slug(value) if value is not None else None


class OrganizationUpdate(ApiModel):
    name: str | None = Field(default=None, min_length=2, max_length=160)
    slug: str | None = Field(default=None, min_length=2, max_length=100)

    @field_validator("slug")
    @classmethod
    def slug_format(cls, value: str | None) -> str | None:
        return validate_slug(value) if value is not None else None


class OrganizationResponse(ApiModel):
    id: uuid.UUID
    name: str
    slug: str
    status: OrganizationStatus
    created_by_user_id: uuid.UUID
    created_at: datetime
    updated_at: datetime
    current_user_role: OrganizationRole | None = None


class MemberResponse(ApiModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    user_id: uuid.UUID
    email: str
    full_name: str
    user_status: UserStatus
    role: OrganizationRole
    status: MembershipStatus
    joined_at: datetime | None
    created_at: datetime
    updated_at: datetime


class RoleUpdate(ApiModel):
    role: OrganizationRole


class StatusUpdate(ApiModel):
    status: MembershipStatus

    @field_validator("status")
    @classmethod
    def active_or_suspended(cls, value: MembershipStatus) -> MembershipStatus:
        if value not in {MembershipStatus.ACTIVE, MembershipStatus.SUSPENDED}:
            raise ValueError("Status must be active or suspended")
        return value


class AdminSummaryResponse(ApiModel):
    organization: OrganizationResponse
    current_user_role: OrganizationRole
    total_members: int
    active_members: int
    suspended_members: int
    pending_invitations: int
    recent_activity: list[dict[str, object]]
