from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Query
from sqlalchemy import func, select

from app.dependencies.auth import CurrentUser, DbSession
from app.exceptions.errors import NotFoundError
from app.models import RemediationRequest
from app.models.enums import RemediationStatus
from app.schemas.remediation import (
    RemediationRejectRequest,
    RemediationRequestListResponse,
    RemediationRequestResponse,
)
from app.security.rbac import Capability
from app.services.organizations import OrganizationService
from app.services.remediation import RemediationService

router = APIRouter()


def _require(
    db: DbSession, user: CurrentUser, organization_id: uuid.UUID, capability: Capability
) -> None:
    OrganizationService(db).require_capability(organization_id, user.id, capability)


@router.get("/remediations", response_model=RemediationRequestListResponse)
def list_remediations(
    user: CurrentUser,
    db: DbSession,
    organization_id: Annotated[uuid.UUID, Query()],
    status_filter: Annotated[RemediationStatus | None, Query(alias="status")] = None,
    finding_id: uuid.UUID | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
) -> RemediationRequestListResponse:
    _require(db, user, organization_id, Capability.REMEDIATION_READ)
    statement = select(RemediationRequest).where(
        RemediationRequest.organization_id == organization_id
    )
    if status_filter:
        statement = statement.where(RemediationRequest.status == status_filter)
    if finding_id:
        statement = statement.where(RemediationRequest.finding_id == finding_id)
    total = int(db.scalar(select(func.count()).select_from(statement.subquery())) or 0)
    items = db.scalars(
        statement.order_by(RemediationRequest.created_at.desc(), RemediationRequest.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return RemediationRequestListResponse(
        items=[RemediationRequestResponse.model_validate(item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/remediations/{request_id}", response_model=RemediationRequestResponse)
def remediation_detail(
    request_id: uuid.UUID,
    user: CurrentUser,
    db: DbSession,
    organization_id: Annotated[uuid.UUID, Query()],
) -> RemediationRequest:
    _require(db, user, organization_id, Capability.REMEDIATION_READ)
    item = db.scalar(
        select(RemediationRequest).where(
            RemediationRequest.id == request_id,
            RemediationRequest.organization_id == organization_id,
        )
    )
    if item is None:
        raise NotFoundError(
            "remediation_request_not_found", "Remediation request was not found."
        )
    return item


@router.post(
    "/findings/{finding_id}/remediations",
    response_model=RemediationRequestResponse,
    status_code=201,
)
def propose_remediation(
    finding_id: uuid.UUID,
    user: CurrentUser,
    db: DbSession,
    organization_id: Annotated[uuid.UUID, Query()],
) -> RemediationRequest:
    _require(db, user, organization_id, Capability.REMEDIATION_REQUEST)
    request = RemediationService(db).propose_for_finding(organization_id, finding_id, user)
    db.commit()
    return request


@router.post("/remediations/{request_id}/approve", response_model=RemediationRequestResponse)
def approve_remediation(
    request_id: uuid.UUID,
    user: CurrentUser,
    db: DbSession,
    organization_id: Annotated[uuid.UUID, Query()],
) -> RemediationRequest:
    _require(db, user, organization_id, Capability.REMEDIATION_APPROVE)
    request = RemediationService(db).approve(organization_id, request_id, user)
    db.commit()
    return request


@router.post("/remediations/{request_id}/reject", response_model=RemediationRequestResponse)
def reject_remediation(
    request_id: uuid.UUID,
    payload: RemediationRejectRequest,
    user: CurrentUser,
    db: DbSession,
    organization_id: Annotated[uuid.UUID, Query()],
) -> RemediationRequest:
    _require(db, user, organization_id, Capability.REMEDIATION_REJECT)
    request = RemediationService(db).reject(organization_id, request_id, user, payload.reason)
    db.commit()
    return request


@router.post("/remediations/{request_id}/cancel", response_model=RemediationRequestResponse)
def cancel_remediation(
    request_id: uuid.UUID,
    user: CurrentUser,
    db: DbSession,
    organization_id: Annotated[uuid.UUID, Query()],
) -> RemediationRequest:
    _require(db, user, organization_id, Capability.REMEDIATION_REQUEST)
    request = RemediationService(db).cancel(organization_id, request_id, user)
    db.commit()
    return request


@router.post("/remediations/{request_id}/execute", response_model=RemediationRequestResponse)
def execute_remediation(
    request_id: uuid.UUID,
    user: CurrentUser,
    db: DbSession,
    organization_id: Annotated[uuid.UUID, Query()],
) -> RemediationRequest:
    _require(db, user, organization_id, Capability.REMEDIATION_EXECUTE)
    request = RemediationService(db).execute(organization_id, request_id)
    db.commit()
    return request
