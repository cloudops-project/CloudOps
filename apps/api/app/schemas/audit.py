from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from app.models.enums import AuditResult
from app.schemas.common import ApiModel


class AuditEventResponse(ApiModel):
    id: uuid.UUID
    organization_id: uuid.UUID | None
    actor_user_id: uuid.UUID | None
    event_type: str
    resource_type: str
    resource_id: uuid.UUID | None
    result: AuditResult
    metadata_json: dict[str, Any]
    created_at: datetime


class AuditEventListResponse(ApiModel):
    items: list[AuditEventResponse]
    total: int
    page: int
    page_size: int
