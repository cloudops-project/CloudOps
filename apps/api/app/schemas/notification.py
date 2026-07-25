from __future__ import annotations

import uuid
from datetime import datetime

from app.models.enums import NotificationChannel, NotificationStatus
from app.schemas.common import ApiModel


class NotificationEventResponse(ApiModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    source_event_type: str
    source_resource_type: str
    source_resource_id: uuid.UUID
    channel: NotificationChannel
    template_key: str
    destination_reference: str | None
    status: NotificationStatus
    attempt_count: int
    approved_by_user_id: uuid.UUID | None
    approved_at: datetime | None
    scheduled_at: datetime | None
    delivered_at: datetime | None
    failed_at: datetime | None
    failure_reason: str | None
    provider_key: str | None
    provider_message_id: str | None
    created_at: datetime
    updated_at: datetime


class NotificationEventListResponse(ApiModel):
    items: list[NotificationEventResponse]
    total: int
    page: int
    page_size: int
