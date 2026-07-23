from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import EmailStr, Field

from app.models.enums import InvitationStatus, OrganizationRole
from app.schemas.common import ApiModel


class InvitationCreate(ApiModel):
    email: EmailStr
    role: OrganizationRole


class InvitationAccept(ApiModel):
    token: str = Field(min_length=32, max_length=256)


class InvitationResponse(ApiModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    email: EmailStr
    role: OrganizationRole
    status: InvitationStatus
    expires_at: datetime
    accepted_at: datetime | None
    created_at: datetime
    updated_at: datetime
    development_token: str | None = None
