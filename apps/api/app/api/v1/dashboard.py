from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Query

from app.dependencies.auth import CurrentUser, DbSession
from app.schemas.dashboard import DashboardSummaryResponse
from app.security.rbac import Capability
from app.services.dashboard import DashboardService
from app.services.organizations import OrganizationService

router = APIRouter(prefix="/dashboard")


@router.get("/summary", response_model=DashboardSummaryResponse)
def summary(
    user: CurrentUser,
    db: DbSession,
    organization_id: Annotated[uuid.UUID, Query()],
) -> DashboardSummaryResponse:
    OrganizationService(db).require_capability(
        organization_id, user.id, Capability.ORGANIZATION_READ
    )
    return DashboardService(db).summary(organization_id)
