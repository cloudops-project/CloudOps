from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime
from typing import Any, cast

from sqlalchemy.orm import Session

from app.models import AuditEvent
from app.models.enums import AuditResult
from app.services.ai_safety import redact_text, sanitize


def now_utc() -> datetime:
    return datetime.now(UTC)


def normalize_email(email: str) -> str:
    return email.strip().casefold()


def slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")
    return slug[:100]


def is_expired(value: datetime, now: datetime | None = None) -> bool:
    current = now or now_utc()
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value <= current


def record_audit(
    db: Session,
    event_type: str,
    resource_type: str,
    *,
    result: AuditResult = AuditResult.SUCCEEDED,
    organization_id: uuid.UUID | None = None,
    actor_user_id: uuid.UUID | None = None,
    resource_id: uuid.UUID | None = None,
    metadata: dict[str, Any] | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> AuditEvent:
    event = AuditEvent(
        event_type=event_type,
        resource_type=resource_type,
        result=result,
        organization_id=organization_id,
        actor_user_id=actor_user_id,
        resource_id=resource_id,
        metadata_json=cast(dict[str, Any], sanitize(metadata or {})),
        ip_address=ip_address,
        user_agent=redact_text(user_agent)[:512] if user_agent else None,
    )
    db.add(event)
    return event
