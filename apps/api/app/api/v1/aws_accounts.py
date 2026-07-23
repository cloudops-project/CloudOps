from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status

from app.dependencies.auth import AppSettings, CurrentUser, DbSession
from app.models import AWSAccount
from app.schemas.aws_account import (
    AWSAccountCreate,
    AWSAccountDetailResponse,
    AWSAccountResponse,
    AWSAccountUpdate,
)
from app.services.aws_onboarding import AWSOnboardingService

router = APIRouter()


def _detail(service: AWSOnboardingService, account: AWSAccount) -> AWSAccountDetailResponse:
    return AWSAccountDetailResponse(
        account=AWSAccountResponse.model_validate(account),
        trust_policy=service.trust_policy(account),
        permission_policy=service.permission_policy(),
        onboarding_instructions=service.onboarding_instructions(),
    )


@router.post(
    "/accounts",
    response_model=AWSAccountDetailResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_account(
    payload: AWSAccountCreate, user: CurrentUser, db: DbSession, settings: AppSettings
) -> AWSAccountDetailResponse:
    service = AWSOnboardingService(db, settings)
    account = service.create_account(
        payload.organization_id, user, payload.name, payload.account_id
    )
    return _detail(service, account)


@router.get("/accounts", response_model=list[AWSAccountResponse])
def list_accounts(
    user: CurrentUser,
    db: DbSession,
    settings: AppSettings,
    organization_id: Annotated[uuid.UUID, Query()],
) -> list[AWSAccountResponse]:
    return [
        AWSAccountResponse.model_validate(account)
        for account in AWSOnboardingService(db, settings).list_accounts(organization_id, user)
    ]


@router.get("/accounts/{account_id}", response_model=AWSAccountDetailResponse)
def get_account(
    account_id: uuid.UUID, user: CurrentUser, db: DbSession, settings: AppSettings
) -> AWSAccountDetailResponse:
    service = AWSOnboardingService(db, settings)
    return _detail(service, service.get_account(account_id, user))


@router.patch("/accounts/{account_id}", response_model=AWSAccountDetailResponse)
def update_account(
    account_id: uuid.UUID,
    payload: AWSAccountUpdate,
    user: CurrentUser,
    db: DbSession,
    settings: AppSettings,
) -> AWSAccountDetailResponse:
    service = AWSOnboardingService(db, settings)
    account = service.update_account(account_id, user, name=payload.name, role_arn=payload.role_arn)
    return _detail(service, account)


@router.post("/accounts/{account_id}/validate", response_model=AWSAccountDetailResponse)
def validate_connection(
    account_id: uuid.UUID, user: CurrentUser, db: DbSession, settings: AppSettings
) -> AWSAccountDetailResponse:
    service = AWSOnboardingService(db, settings)
    return _detail(service, service.validate_connection(account_id, user))


@router.post("/accounts/{account_id}/disconnect", response_model=AWSAccountDetailResponse)
def disconnect_account(
    account_id: uuid.UUID, user: CurrentUser, db: DbSession, settings: AppSettings
) -> AWSAccountDetailResponse:
    service = AWSOnboardingService(db, settings)
    return _detail(service, service.disconnect_account(account_id, user))


@router.delete("/accounts/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_account(
    account_id: uuid.UUID, user: CurrentUser, db: DbSession, settings: AppSettings
) -> None:
    AWSOnboardingService(db, settings).delete_account(account_id, user)
