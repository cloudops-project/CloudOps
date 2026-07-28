from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy import func, select

from app.dependencies.auth import AppSettings, CurrentUser, DbSession, UserRateLimiter
from app.exceptions.errors import NotFoundError
from app.models import AIRequest, AIRequestSource
from app.models.enums import AIRequestStatus, AISourceType, AITaskType
from app.schemas.ai import (
    AIGenerateRequest,
    AIRequestListResponse,
    AIRequestResponse,
    AIShortcutRequest,
    AISourceInput,
)
from app.security.rbac import Capability
from app.services.ai import AIService
from app.services.organizations import OrganizationService

_generation_rate_limit = UserRateLimiter("ai_generation", limit=10, window_seconds=60)


def _limit_ai_mutations(request: Request, user: CurrentUser, settings: AppSettings) -> None:
    if request.method == "POST":
        _generation_rate_limit(user, settings)


router = APIRouter(dependencies=[Depends(_limit_ai_mutations)])


def _shortcut(
    *,
    organization_id: uuid.UUID,
    source_id: uuid.UUID,
    source_type: AISourceType,
    task_type: AITaskType,
    idempotency_key: str,
    user: CurrentUser,
    db: DbSession,
) -> AIRequestResponse:
    return generate(
        AIGenerateRequest(
            organization_id=organization_id,
            task_type=task_type,
            sources=[AISourceInput(source_type=source_type, source_id=source_id)],
            idempotency_key=idempotency_key,
        ),
        user,
        db,
    )


@router.post("/ai/generate", response_model=AIRequestResponse, status_code=status.HTTP_201_CREATED)
def generate(
    payload: AIGenerateRequest,
    user: CurrentUser,
    db: DbSession,
) -> AIRequestResponse:
    OrganizationService(db).require_capability(
        payload.organization_id, user.id, Capability.AI_GENERATE
    )
    return AIService(db).generate(payload, user.id)


@router.get("/ai/requests", response_model=AIRequestListResponse)
def requests(
    user: CurrentUser,
    db: DbSession,
    organization_id: Annotated[uuid.UUID, Query()],
    task_type: AITaskType | None = None,
    request_status: AIRequestStatus | None = None,
    source_type: AISourceType | None = None,
    source_id: uuid.UUID | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
) -> AIRequestListResponse:
    OrganizationService(db).require_capability(organization_id, user.id, Capability.AI_READ)
    statement = select(AIRequest).where(AIRequest.organization_id == organization_id)
    if task_type:
        statement = statement.where(AIRequest.task_type == task_type)
    if request_status:
        statement = statement.where(AIRequest.status == request_status)
    if source_type is not None or source_id is not None:
        statement = statement.join(AIRequestSource, AIRequestSource.request_id == AIRequest.id)
    if source_type is not None:
        statement = statement.where(AIRequestSource.source_type == source_type)
    if source_id is not None:
        statement = statement.where(AIRequestSource.source_id == source_id)
    total = int(db.scalar(select(func.count()).select_from(statement.subquery())) or 0)
    items = db.scalars(
        statement.order_by(AIRequest.created_at.desc(), AIRequest.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    service = AIService(db)
    return AIRequestListResponse(
        items=[service.response(item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/ai/requests/{request_id}", response_model=AIRequestResponse)
def request_detail(
    request_id: uuid.UUID,
    user: CurrentUser,
    db: DbSession,
    organization_id: Annotated[uuid.UUID, Query()],
) -> AIRequestResponse:
    OrganizationService(db).require_capability(organization_id, user.id, Capability.AI_READ)
    item = db.scalar(
        select(AIRequest).where(
            AIRequest.id == request_id,
            AIRequest.organization_id == organization_id,
        )
    )
    if item is None:
        raise NotFoundError("ai_request_not_found", "AI request was not found.")
    return AIService(db).response(item)


@router.post("/findings/{finding_id}/ai/explain", response_model=AIRequestResponse)
def explain_finding(
    finding_id: uuid.UUID, payload: AIShortcutRequest, user: CurrentUser, db: DbSession
) -> AIRequestResponse:
    return _shortcut(
        organization_id=payload.organization_id,
        source_id=finding_id,
        source_type=AISourceType.FINDING,
        task_type=AITaskType.EXPLAIN_FINDING,
        idempotency_key=payload.idempotency_key,
        user=user,
        db=db,
    )


@router.post("/findings/{finding_id}/ai/business-impact", response_model=AIRequestResponse)
def business_impact(
    finding_id: uuid.UUID, payload: AIShortcutRequest, user: CurrentUser, db: DbSession
) -> AIRequestResponse:
    return _shortcut(
        organization_id=payload.organization_id,
        source_id=finding_id,
        source_type=AISourceType.FINDING,
        task_type=AITaskType.EXPLAIN_BUSINESS_IMPACT,
        idempotency_key=payload.idempotency_key,
        user=user,
        db=db,
    )


@router.post("/findings/{finding_id}/ai/remediation-draft", response_model=AIRequestResponse)
def remediation_draft(
    finding_id: uuid.UUID, payload: AIShortcutRequest, user: CurrentUser, db: DbSession
) -> AIRequestResponse:
    return _shortcut(
        organization_id=payload.organization_id,
        source_id=finding_id,
        source_type=AISourceType.FINDING,
        task_type=AITaskType.SUGGEST_REMEDIATION,
        idempotency_key=payload.idempotency_key,
        user=user,
        db=db,
    )


@router.post("/findings/{finding_id}/ai/jira-draft", response_model=AIRequestResponse)
def jira_draft(
    finding_id: uuid.UUID, payload: AIShortcutRequest, user: CurrentUser, db: DbSession
) -> AIRequestResponse:
    return _shortcut(
        organization_id=payload.organization_id,
        source_id=finding_id,
        source_type=AISourceType.FINDING,
        task_type=AITaskType.JIRA_DESCRIPTION,
        idempotency_key=payload.idempotency_key,
        user=user,
        db=db,
    )


@router.post("/findings/{finding_id}/ai/email-draft", response_model=AIRequestResponse)
def email_draft(
    finding_id: uuid.UUID, payload: AIShortcutRequest, user: CurrentUser, db: DbSession
) -> AIRequestResponse:
    return _shortcut(
        organization_id=payload.organization_id,
        source_id=finding_id,
        source_type=AISourceType.FINDING,
        task_type=AITaskType.EMAIL_SUMMARY,
        idempotency_key=payload.idempotency_key,
        user=user,
        db=db,
    )


@router.post(
    "/risk/assessments/{assessment_id}/ai/executive-summary",
    response_model=AIRequestResponse,
)
def executive_summary(
    assessment_id: uuid.UUID,
    payload: AIShortcutRequest,
    user: CurrentUser,
    db: DbSession,
) -> AIRequestResponse:
    return _shortcut(
        organization_id=payload.organization_id,
        source_id=assessment_id,
        source_type=AISourceType.RISK_ASSESSMENT,
        task_type=AITaskType.EXECUTIVE_SUMMARY,
        idempotency_key=payload.idempotency_key,
        user=user,
        db=db,
    )


@router.post(
    "/risk/assessments/{assessment_id}/ai/email-draft",
    response_model=AIRequestResponse,
)
def risk_email_summary(
    assessment_id: uuid.UUID,
    payload: AIShortcutRequest,
    user: CurrentUser,
    db: DbSession,
) -> AIRequestResponse:
    return _shortcut(
        organization_id=payload.organization_id,
        source_id=assessment_id,
        source_type=AISourceType.RISK_ASSESSMENT,
        task_type=AITaskType.EMAIL_SUMMARY,
        idempotency_key=payload.idempotency_key,
        user=user,
        db=db,
    )


@router.post(
    "/compliance/assessments/{assessment_id}/ai/executive-summary",
    response_model=AIRequestResponse,
)
def compliance_executive_summary(
    assessment_id: uuid.UUID,
    payload: AIShortcutRequest,
    user: CurrentUser,
    db: DbSession,
) -> AIRequestResponse:
    return _shortcut(
        organization_id=payload.organization_id,
        source_id=assessment_id,
        source_type=AISourceType.COMPLIANCE_ASSESSMENT,
        task_type=AITaskType.EXECUTIVE_SUMMARY,
        idempotency_key=payload.idempotency_key,
        user=user,
        db=db,
    )


@router.post(
    "/compliance/assessments/{assessment_id}/ai/email-draft",
    response_model=AIRequestResponse,
)
def compliance_email_summary(
    assessment_id: uuid.UUID,
    payload: AIShortcutRequest,
    user: CurrentUser,
    db: DbSession,
) -> AIRequestResponse:
    return _shortcut(
        organization_id=payload.organization_id,
        source_id=assessment_id,
        source_type=AISourceType.COMPLIANCE_ASSESSMENT,
        task_type=AITaskType.EMAIL_SUMMARY,
        idempotency_key=payload.idempotency_key,
        user=user,
        db=db,
    )
