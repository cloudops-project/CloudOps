from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import func, select

from app.dependencies.auth import CurrentUser, DbSession, UserRateLimiter
from app.exceptions.errors import NotFoundError
from app.models import NotificationDeliveryAttempt, NotificationEvent
from app.models.enums import NotificationChannel, NotificationStatus
from app.schemas.notification import (
    NotificationDeliveryAttemptResponse,
    NotificationEventListResponse,
    NotificationEventResponse,
)
from app.schemas.platform_job import PlatformJobResponse
from app.security.rbac import Capability
from app.services.notifications import NotificationService
from app.services.organizations import OrganizationService

router = APIRouter()
_delivery_rate_limit = UserRateLimiter("notification_delivery", limit=10, window_seconds=60)


def _require_read(db: DbSession, user: CurrentUser, organization_id: uuid.UUID) -> None:
    OrganizationService(db).require_capability(
        organization_id, user.id, Capability.NOTIFICATIONS_READ
    )


def _require_approve(db: DbSession, user: CurrentUser, organization_id: uuid.UUID) -> None:
    OrganizationService(db).require_capability(
        organization_id, user.id, Capability.NOTIFICATIONS_APPROVE
    )


@router.get("/notifications", response_model=NotificationEventListResponse)
def list_notifications(
    user: CurrentUser,
    db: DbSession,
    organization_id: Annotated[uuid.UUID, Query()],
    status_filter: Annotated[NotificationStatus | None, Query(alias="status")] = None,
    channel: NotificationChannel | None = None,
    source_resource_id: uuid.UUID | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
) -> NotificationEventListResponse:
    _require_read(db, user, organization_id)
    statement = select(NotificationEvent).where(
        NotificationEvent.organization_id == organization_id
    )
    if status_filter:
        statement = statement.where(NotificationEvent.status == status_filter)
    if channel:
        statement = statement.where(NotificationEvent.channel == channel)
    if source_resource_id:
        statement = statement.where(NotificationEvent.source_resource_id == source_resource_id)
    total = int(db.scalar(select(func.count()).select_from(statement.subquery())) or 0)
    items = db.scalars(
        statement.order_by(NotificationEvent.created_at.desc(), NotificationEvent.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return NotificationEventListResponse(
        items=[NotificationEventResponse.model_validate(item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/notifications/{event_id}", response_model=NotificationEventResponse)
def notification_detail(
    event_id: uuid.UUID,
    user: CurrentUser,
    db: DbSession,
    organization_id: Annotated[uuid.UUID, Query()],
) -> NotificationEvent:
    _require_read(db, user, organization_id)
    item = db.scalar(
        select(NotificationEvent).where(
            NotificationEvent.id == event_id,
            NotificationEvent.organization_id == organization_id,
        )
    )
    if item is None:
        raise NotFoundError("notification_event_not_found", "Notification event was not found.")
    return item


@router.get(
    "/notifications/{event_id}/attempts",
    response_model=list[NotificationDeliveryAttemptResponse],
)
def notification_delivery_attempts(
    event_id: uuid.UUID,
    user: CurrentUser,
    db: DbSession,
    organization_id: Annotated[uuid.UUID, Query()],
) -> list[NotificationDeliveryAttempt]:
    _require_read(db, user, organization_id)
    event = db.scalar(
        select(NotificationEvent.id).where(
            NotificationEvent.id == event_id,
            NotificationEvent.organization_id == organization_id,
        )
    )
    if event is None:
        raise NotFoundError("notification_event_not_found", "Notification event was not found.")
    return list(
        db.scalars(
            select(NotificationDeliveryAttempt)
            .where(
                NotificationDeliveryAttempt.notification_event_id == event_id,
                NotificationDeliveryAttempt.organization_id == organization_id,
            )
            .order_by(NotificationDeliveryAttempt.attempt_number)
            .limit(20)
        ).all()
    )


@router.post("/notifications/{event_id}/approve", response_model=NotificationEventResponse)
def approve_notification(
    event_id: uuid.UUID,
    user: CurrentUser,
    db: DbSession,
    organization_id: Annotated[uuid.UUID, Query()],
) -> NotificationEvent:
    _require_approve(db, user, organization_id)
    event = NotificationService(db).approve(organization_id, event_id, user)
    db.commit()
    return event


@router.post(
    "/notifications/{event_id}/revoke-approval",
    response_model=NotificationEventResponse,
)
def revoke_notification_approval(
    event_id: uuid.UUID,
    user: CurrentUser,
    db: DbSession,
    organization_id: Annotated[uuid.UUID, Query()],
) -> NotificationEvent:
    _require_approve(db, user, organization_id)
    event = NotificationService(db).revoke_approval(organization_id, event_id, user)
    db.commit()
    return event


@router.post(
    "/notifications/{event_id}/deliver",
    response_model=PlatformJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(_delivery_rate_limit)],
)
def deliver_notification(
    event_id: uuid.UUID,
    user: CurrentUser,
    db: DbSession,
    organization_id: Annotated[uuid.UUID, Query()],
) -> PlatformJobResponse:
    _require_approve(db, user, organization_id)
    job = NotificationService(db).enqueue_delivery(organization_id, event_id, user)
    db.commit()
    return PlatformJobResponse.model_validate(job)
