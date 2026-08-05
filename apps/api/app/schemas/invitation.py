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
    # Sanitized delivery evidence. Never a token, token hash, acceptance URL,
    # provider exception or AWS detail.
    last_delivery_status: str | None = None
    last_delivery_error_code: str | None = None
    last_delivery_attempt_at: datetime | None = None
    last_delivered_at: datetime | None = None
    delivery_generation: int = 0
    development_token: str | None = None
