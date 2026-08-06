from __future__ import annotations

import uuid

from fastapi import APIRouter, status

from app.dependencies.auth import AppSettings, CurrentUser, DbSession
from app.models import Organization, OrganizationMembership, User
from app.schemas.audit import AuditEventResponse
from app.schemas.invitation import InvitationCreate, InvitationResponse
from app.schemas.organization import (
    MemberResponse,
    OrganizationCreate,
    OrganizationResponse,
    OrganizationUpdate,
    RoleUpdate,
    StatusUpdate,
)
from app.security.rbac import Capability
from app.services.invitations import InvitationService
from app.services.organizations import OrganizationService

router = APIRouter()


def org_response(org: Organization, role: object | None = None) -> OrganizationResponse:
    return OrganizationResponse.model_validate(org).model_copy(update={"current_user_role": role})


def member_response(member: OrganizationMembership, user: User) -> MemberResponse:
    return MemberResponse(
        id=member.id,
        organization_id=member.organization_id,
        user_id=user.id,
        email=user.email,
        full_name=user.full_name,
        user_status=user.status,
        role=member.role,
        status=member.status,
        joined_at=member.joined_at,
        created_at=member.created_at,
        updated_at=member.updated_at,
    )


@router.post("", response_model=OrganizationResponse, status_code=status.HTTP_201_CREATED)
def create(payload: OrganizationCreate, user: CurrentUser, db: DbSession) -> OrganizationResponse:
    org, member = OrganizationService(db).create(user, payload.name, payload.slug)
    return org_response(org, member.role)


@router.get("", response_model=list[OrganizationResponse])
def list_organizations(user: CurrentUser, db: DbSession) -> list[OrganizationResponse]:
    return [
        org_response(org, member.role)
        for org, member in OrganizationService(db).list_for_user(user.id)
    ]


@router.get("/{organization_id}", response_model=OrganizationResponse)
def get(organization_id: uuid.UUID, user: CurrentUser, db: DbSession) -> OrganizationResponse:
    org, member = OrganizationService(db).get(organization_id, user.id)
    return org_response(org, member.role)


@router.patch("/{organization_id}", response_model=OrganizationResponse)
def update(
    organization_id: uuid.UUID, payload: OrganizationUpdate, user: CurrentUser, db: DbSession
) -> OrganizationResponse:
    org = OrganizationService(db).update(organization_id, user, payload.name, payload.slug)
    member = OrganizationService(db).require_member(organization_id, user.id)
    return org_response(org, member.role)


@router.get("/{organization_id}/members", response_model=list[MemberResponse])
def members(organization_id: uuid.UUID, user: CurrentUser, db: DbSession) -> list[MemberResponse]:
    return [
        member_response(member, target)
        for member, target in OrganizationService(db).members(organization_id, user.id)
    ]


@router.patch("/{organization_id}/members/{membership_id}/role", response_model=MemberResponse)
def role(
    organization_id: uuid.UUID,
    membership_id: uuid.UUID,
    payload: RoleUpdate,
    user: CurrentUser,
    db: DbSession,
) -> MemberResponse:
    member = OrganizationService(db).change_role(organization_id, membership_id, user, payload.role)
    return member_response(member, OrganizationService(db).repo.user(member.user_id))  # type: ignore[arg-type]


@router.patch("/{organization_id}/members/{membership_id}/status", response_model=MemberResponse)
def member_status(
    organization_id: uuid.UUID,
    membership_id: uuid.UUID,
    payload: StatusUpdate,
    user: CurrentUser,
    db: DbSession,
) -> MemberResponse:
    member = OrganizationService(db).change_status(
        organization_id, membership_id, user, payload.status
    )
    return member_response(member, OrganizationService(db).repo.user(member.user_id))  # type: ignore[arg-type]


@router.delete("/{organization_id}/members/{membership_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove(
    organization_id: uuid.UUID, membership_id: uuid.UUID, user: CurrentUser, db: DbSession
) -> None:
    OrganizationService(db).remove(organization_id, membership_id, user)


@router.post(
    "/{organization_id}/invitations",
    response_model=InvitationResponse,
    response_model_exclude_none=True,
    status_code=status.HTTP_201_CREATED,
)
def invite(
    organization_id: uuid.UUID,
    payload: InvitationCreate,
    user: CurrentUser,
    db: DbSession,
    settings: AppSettings,
) -> InvitationResponse:
    invitation, raw = InvitationService(db, settings).create(
        organization_id, user, str(payload.email), payload.role
    )
    development_token = raw if settings.app_env in {"development", "testing"} else None
    return InvitationResponse.model_validate(invitation).model_copy(
        update={"development_token": development_token}
    )


@router.get(
    "/{organization_id}/invitations",
    response_model=list[InvitationResponse],
    response_model_exclude_none=True,
)
def invitations(
    organization_id: uuid.UUID, user: CurrentUser, db: DbSession, settings: AppSettings
) -> list[InvitationResponse]:
    return [
        InvitationResponse.model_validate(item)
        for item in InvitationService(db, settings).list(organization_id, user)
    ]


@router.post(
    "/{organization_id}/invitations/{invitation_id}/resend",
    response_model=InvitationResponse,
    response_model_exclude_none=True,
)
def resend_invitation(
    organization_id: uuid.UUID,
    invitation_id: uuid.UUID,
    user: CurrentUser,
    db: DbSession,
    settings: AppSettings,
) -> InvitationResponse:
    invitation, raw = InvitationService(db, settings).resend(organization_id, invitation_id, user)
    development_token = raw if settings.app_env in {"development", "testing"} else None
    return InvitationResponse.model_validate(invitation).model_copy(
        update={"development_token": development_token}
    )


@router.delete(
    "/{organization_id}/invitations/{invitation_id}", status_code=status.HTTP_204_NO_CONTENT
)
def cancel_invitation(
    organization_id: uuid.UUID,
    invitation_id: uuid.UUID,
    user: CurrentUser,
    db: DbSession,
    settings: AppSettings,
) -> None:
    InvitationService(db, settings).cancel(organization_id, invitation_id, user)


@router.get("/{organization_id}/audit-events", response_model=list[AuditEventResponse])
def audit_events(
    organization_id: uuid.UUID, user: CurrentUser, db: DbSession
) -> list[AuditEventResponse]:
    service = OrganizationService(db)
    service.require_capability(organization_id, user.id, Capability.AUDIT_READ)
    return [
        AuditEventResponse.model_validate(item)
        for item in service.repo.audit_events(organization_id)
    ]
