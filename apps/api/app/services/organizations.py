from __future__ import annotations

import uuid

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.exceptions.errors import ConflictError, ForbiddenError, NotFoundError
from app.models import Organization, OrganizationMembership, User
from app.models.enums import MembershipStatus, OrganizationRole
from app.repositories.data import Repository
from app.security.rbac import (
    Capability,
    ensure_actor_can_manage_membership,
    role_has_capability,
)
from app.services.common import now_utc, record_audit, slugify


class OrganizationService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repo = Repository(db)

    def require_member(
        self, organization_id: uuid.UUID, user_id: uuid.UUID
    ) -> OrganizationMembership:
        membership = self.repo.active_membership(organization_id, user_id)
        if not membership:
            raise NotFoundError("organization_not_found", "Organization was not found.")
        return membership

    def require_capability(
        self, organization_id: uuid.UUID, user_id: uuid.UUID, capability: Capability
    ) -> OrganizationMembership:
        membership = self.require_member(organization_id, user_id)
        if not role_has_capability(membership.role, capability):
            raise ForbiddenError()
        return membership

    def create(
        self, user: User, name: str, slug: str | None
    ) -> tuple[Organization, OrganizationMembership]:
        value = slug or slugify(name)
        if not value or self.repo.organization_by_slug(value):
            raise ConflictError("slug_in_use", "Organization slug is already in use.")
        org = Organization(name=name.strip(), slug=value, created_by_user_id=user.id)
        self.db.add(org)
        self.db.flush()
        member = OrganizationMembership(
            organization_id=org.id,
            user_id=user.id,
            role=OrganizationRole.OWNER,
            status=MembershipStatus.ACTIVE,
            joined_at=now_utc(),
        )
        self.db.add(member)
        record_audit(
            self.db,
            "organization.created",
            "organization",
            organization_id=org.id,
            actor_user_id=user.id,
            resource_id=org.id,
        )
        try:
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            raise ConflictError(
                "organization_conflict", "Organization could not be created."
            ) from exc
        self.db.refresh(org)
        self.db.refresh(member)
        return org, member

    def list_for_user(
        self, user_id: uuid.UUID
    ) -> list[tuple[Organization, OrganizationMembership]]:
        return self.repo.user_organizations(user_id)

    def get(
        self, organization_id: uuid.UUID, user_id: uuid.UUID
    ) -> tuple[Organization, OrganizationMembership]:
        member = self.require_member(organization_id, user_id)
        organization = self.repo.organization(organization_id)
        if not organization:
            raise NotFoundError()
        return organization, member

    def update(
        self, organization_id: uuid.UUID, actor: User, name: str | None, slug: str | None
    ) -> Organization:
        self.require_capability(organization_id, actor.id, Capability.ORGANIZATION_UPDATE)
        organization = self.repo.organization(organization_id)
        if not organization:
            raise NotFoundError()
        if name is not None:
            organization.name = name.strip()
        if slug is not None and slug != organization.slug:
            if self.repo.organization_by_slug(slug):
                raise ConflictError("slug_in_use", "Organization slug is already in use.")
            organization.slug = slug
        self.db.commit()
        self.db.refresh(organization)
        return organization

    def members(
        self, organization_id: uuid.UUID, actor_id: uuid.UUID
    ) -> list[tuple[OrganizationMembership, User]]:
        self.require_capability(organization_id, actor_id, Capability.MEMBERS_READ)
        return self.repo.members(organization_id)

    def change_role(
        self,
        organization_id: uuid.UUID,
        membership_id: uuid.UUID,
        actor: User,
        role: OrganizationRole,
    ) -> OrganizationMembership:
        actor_member = self.require_capability(organization_id, actor.id, Capability.MEMBERS_MANAGE)
        target = self.repo.membership_by_id(organization_id, membership_id)
        if not target or target.status == MembershipStatus.REMOVED:
            raise NotFoundError("membership_not_found", "Membership was not found.")
        ensure_actor_can_manage_membership(
            actor_role=actor_member.role,
            target_role=target.role,
            requested_role=role,
        )
        if target.role == OrganizationRole.OWNER and role != OrganizationRole.OWNER:
            self._protect_last_owner(organization_id)
        target.role = role
        record_audit(
            self.db,
            "membership.role_changed",
            "membership",
            organization_id=organization_id,
            actor_user_id=actor.id,
            resource_id=target.id,
            metadata={"role": role.value},
        )
        self.db.commit()
        self.db.refresh(target)
        return target

    def change_status(
        self,
        organization_id: uuid.UUID,
        membership_id: uuid.UUID,
        actor: User,
        status: MembershipStatus,
    ) -> OrganizationMembership:
        actor_member = self.require_capability(organization_id, actor.id, Capability.MEMBERS_MANAGE)
        target = self.repo.membership_by_id(organization_id, membership_id)
        if not target or target.status == MembershipStatus.REMOVED:
            raise NotFoundError("membership_not_found", "Membership was not found.")
        ensure_actor_can_manage_membership(
            actor_role=actor_member.role,
            target_role=target.role,
        )
        if target.role == OrganizationRole.OWNER and status == MembershipStatus.SUSPENDED:
            self._protect_last_owner(organization_id)
        target.status = status
        event = (
            "membership.suspended"
            if status == MembershipStatus.SUSPENDED
            else "membership.reactivated"
        )
        record_audit(
            self.db,
            event,
            "membership",
            organization_id=organization_id,
            actor_user_id=actor.id,
            resource_id=target.id,
        )
        self.db.commit()
        self.db.refresh(target)
        return target

    def remove(self, organization_id: uuid.UUID, membership_id: uuid.UUID, actor: User) -> None:
        actor_member = self.require_capability(organization_id, actor.id, Capability.MEMBERS_MANAGE)
        target = self.repo.membership_by_id(organization_id, membership_id)
        if not target or target.status == MembershipStatus.REMOVED:
            return
        ensure_actor_can_manage_membership(
            actor_role=actor_member.role,
            target_role=target.role,
        )
        if target.role == OrganizationRole.OWNER:
            self._protect_last_owner(organization_id)
        target.status = MembershipStatus.REMOVED
        record_audit(
            self.db,
            "membership.removed",
            "membership",
            organization_id=organization_id,
            actor_user_id=actor.id,
            resource_id=target.id,
        )
        self.db.commit()

    def _protect_last_owner(self, organization_id: uuid.UUID) -> None:
        if self.repo.active_owner_count(organization_id) <= 1:
            raise ConflictError(
                "last_owner", "The final active owner cannot be changed or removed."
            )
