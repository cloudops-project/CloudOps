from __future__ import annotations

import csv
import io
import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import func, select

from app.dependencies.auth import CurrentUser, DbSession, UserRateLimiter
from app.models import AuditEvent
from app.models.enums import AuditResult
from app.schemas.audit import AuditEventListResponse, AuditEventResponse
from app.security.rbac import Capability
from app.services.organizations import OrganizationService

router = APIRouter()

# Bounds repeated large synchronous exports (each up to EXPORT_MAX_ROWS) per
# user; see UserRateLimiter for the single-process caveat.
_export_rate_limit = UserRateLimiter("audit_export", limit=10, window_seconds=60)

EXPORT_MAX_ROWS = 5_000
EXPORT_COLUMNS = (
    "id",
    "organization_id",
    "actor_user_id",
    "event_type",
    "resource_type",
    "resource_id",
    "result",
    "created_at",
)
_FORMULA_TRIGGER_CHARS = ("=", "+", "-", "@", "\t", "\r")


def _csv_safe(value: str) -> str:
    """Prefix a leading apostrophe if the value could be interpreted as a
    spreadsheet formula when the export is opened in Excel/Sheets."""
    if value and value[0] in _FORMULA_TRIGGER_CHARS:
        return f"'{value}"
    return value


@router.get("/audit-events", response_model=AuditEventListResponse)
def list_audit_events(
    user: CurrentUser,
    db: DbSession,
    organization_id: Annotated[uuid.UUID, Query()],
    event_type: str | None = None,
    resource_type: str | None = None,
    resource_id: uuid.UUID | None = None,
    actor_user_id: uuid.UUID | None = None,
    result_filter: Annotated[AuditResult | None, Query(alias="result")] = None,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
) -> AuditEventListResponse:
    OrganizationService(db).require_capability(organization_id, user.id, Capability.AUDIT_READ)
    statement = select(AuditEvent).where(AuditEvent.organization_id == organization_id)
    if event_type:
        statement = statement.where(AuditEvent.event_type == event_type)
    if resource_type:
        statement = statement.where(AuditEvent.resource_type == resource_type)
    if resource_id:
        statement = statement.where(AuditEvent.resource_id == resource_id)
    if actor_user_id:
        statement = statement.where(AuditEvent.actor_user_id == actor_user_id)
    if result_filter:
        statement = statement.where(AuditEvent.result == result_filter)
    if start_time:
        statement = statement.where(AuditEvent.created_at >= start_time)
    if end_time:
        statement = statement.where(AuditEvent.created_at <= end_time)

    total = int(db.scalar(select(func.count()).select_from(statement.subquery())) or 0)
    items = db.scalars(
        statement.order_by(AuditEvent.created_at.desc(), AuditEvent.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return AuditEventListResponse(
        items=[AuditEventResponse.model_validate(item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/audit-events/export", dependencies=[Depends(_export_rate_limit)])
def export_audit_events(
    user: CurrentUser,
    db: DbSession,
    organization_id: Annotated[uuid.UUID, Query()],
    event_type: str | None = None,
    resource_type: str | None = None,
    resource_id: uuid.UUID | None = None,
    actor_user_id: uuid.UUID | None = None,
    result_filter: Annotated[AuditResult | None, Query(alias="result")] = None,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
) -> Response:
    """Bounded CSV export using the same filters as the list endpoint. Capped
    at EXPORT_MAX_ROWS so this stays a synchronous request; a background
    export job is future work, not part of the Version 1 read-side audit
    query API."""
    OrganizationService(db).require_capability(organization_id, user.id, Capability.AUDIT_READ)
    statement = select(AuditEvent).where(AuditEvent.organization_id == organization_id)
    if event_type:
        statement = statement.where(AuditEvent.event_type == event_type)
    if resource_type:
        statement = statement.where(AuditEvent.resource_type == resource_type)
    if resource_id:
        statement = statement.where(AuditEvent.resource_id == resource_id)
    if actor_user_id:
        statement = statement.where(AuditEvent.actor_user_id == actor_user_id)
    if result_filter:
        statement = statement.where(AuditEvent.result == result_filter)
    if start_time:
        statement = statement.where(AuditEvent.created_at >= start_time)
    if end_time:
        statement = statement.where(AuditEvent.created_at <= end_time)

    items = db.scalars(
        statement.order_by(AuditEvent.created_at.desc(), AuditEvent.id).limit(EXPORT_MAX_ROWS)
    ).all()

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(EXPORT_COLUMNS)
    for item in items:
        writer.writerow(
            [
                str(item.id),
                str(item.organization_id) if item.organization_id else "",
                str(item.actor_user_id) if item.actor_user_id else "",
                _csv_safe(item.event_type),
                _csv_safe(item.resource_type),
                str(item.resource_id) if item.resource_id else "",
                item.result.value,
                item.created_at.isoformat(),
            ]
        )
    return Response(
        content=buffer.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="audit-events.csv"'},
    )
