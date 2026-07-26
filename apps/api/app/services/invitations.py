from __future__ import annotations

import uuid
from datetime import timedelta

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.exceptions.errors import ConflictError, ForbiddenError, NotFoundError
from app.models import OrganizationInvitation, OrganizationMembership, User
from app.models.enums import (
    InvitationStatus,
    MembershipStatus,
    NotificationChannel,
    OrganizationRole,
)
from app.repositories.data import Repository
from app.security.rbac import Capability, can_assign_role
from app.security.tokens import generate_opaque_token, hash_opaque_token
from app.services.common import is_expired, normalize_email, now_utc, record_audit
from app.services.notification_provider import notification_provider_from_settings
from app.services.organizations import OrganizationService


class InvitationService:
    def __init__(self, db: Session, settings: Settings) -> None:
        self.db = db
        self.settings = settings
        self.repo = Repository(db)
        self.organizations = OrganizationService(db)

    def create(
        self, organization_id: uuid.UUID, actor: User, email: str, role: OrganizationRole
    ) -> tuple[OrganizationInvitation, str | None]:
        actor_member = self.organizations.require_capability(
            organization_id, actor.id, Capability.INVITATIONS_MANAGE
        )
        if not can_assign_role(actor_member.role, role):
            raise ForbiddenError(
                "unsafe_role_assignment", "This role cannot be invited by an admin."
            )
        normalized = normalize_email(email)
        existing_user = self.repo.user_by_email(normalized)
        if existing_user and self.repo.membership(organization_id, existing_user.id):
            raise ConflictError(
                "already_member", "This user already has an organization membership."
            )
        if self.repo.pending_invitation(organization_id, normalized):
            raise ConflictError("active_invitation_exists", "A pending invitation already exists.")
        raw = generate_opaque_token()
        invitation = OrganizationInvitation(
            organization_id=organization_id,
            email=email.strip(),
            normalized_email=normalized,
            role=role,
            token_hash=hash_opaque_token(raw),
            status=InvitationStatus.PENDING,
            invited_by_user_id=actor.id,
            expires_at=now_utc() + timedelta(hours=self.settings.invitation_token_expire_hours),
        )
        self.db.add(invitation)
        self.db.flush()
        record_audit(
            self.db,
            "invitation.created",
            "invitation",
            organization_id=organization_id,
            actor_user_id=actor.id,
            resource_id=invitation.id,
            metadata={"role": role.value},
        )
        self._send_development_invitation_email(invitation, raw)
        try:
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            raise ConflictError(
                "active_invitation_exists", "A pending invitation already exists."
            ) from exc
        self.db.refresh(invitation)
        return invitation, raw if self.settings.app_env in {"development", "testing"} else None

    def _send_development_invitation_email(
        self, invitation: OrganizationInvitation, raw_token: str
    ) -> None:
        """Best-effort Mailpit invitation email for the local demo only."""

        if self.settings.app_env != "development" or self.settings.notification_provider != "smtp":
            return
        accept_url = (
            f"{self.settings.frontend_url.rstrip('/')}/invitations/accept?token={raw_token}"
        )
        provider = notification_provider_from_settings(self.settings)
        provider.deliver(
            channel=NotificationChannel.EMAIL,
            destination_reference=invitation.email,
            recipients=[invitation.email],
            subject="CloudOps demo invitation",
            text_body=(
                "You have been invited to join the CloudOps local demo organization.\n\n"
                f"Role: {invitation.role.value}\n"
                f"Accept invitation: {accept_url}\n\n"
                "LOCAL DEMO ONLY — do not reuse this token in production."
            ),
            template_key="development_invitation",
            context={
                "organization_id": str(invitation.organization_id),
                "invitation_id": str(invitation.id),
            },
        )

    def list(self, organization_id: uuid.UUID, actor: User) -> list[OrganizationInvitation]:
        self.organizations.require_capability(
            organization_id, actor.id, Capability.INVITATIONS_MANAGE
        )
        return self.repo.invitations(organization_id)

    def accept(self, raw: str, user: User) -> OrganizationMembership:
        # Keep the invitation locked through membership creation and acceptance commit.
        invitation = self.repo.invitation_by_hash_for_update(hash_opaque_token(raw))
        if not invitation:
            raise NotFoundError("invitation_not_found", "Invitation is invalid or unavailable.")
        existing = self.repo.membership(invitation.organization_id, user.id)
        if invitation.status == InvitationStatus.ACCEPTED and existing:
            return existing
        if invitation.status != InvitationStatus.PENDING:
            raise ConflictError("invitation_unavailable", "Invitation is no longer available.")
        if is_expired(invitation.expires_at):
            invitation.status = InvitationStatus.EXPIRED
            self.db.commit()
            raise ConflictError("invitation_expired", "Invitation has expired.")
        if invitation.normalized_email != user.normalized_email:
            raise ForbiddenError(
                "invitation_email_mismatch", "Invitation does not match this account."
            )
        if existing:
            if existing.status == MembershipStatus.REMOVED:
                existing.status = MembershipStatus.ACTIVE
                existing.role = invitation.role
                existing.joined_at = now_utc()
            else:
                raise ConflictError(
                    "already_member", "This account already belongs to the organization."
                )
            member = existing
        else:
            member = OrganizationMembership(
                organization_id=invitation.organization_id,
                user_id=user.id,
                role=invitation.role,
                status=MembershipStatus.ACTIVE,
                invited_by_user_id=invitation.invited_by_user_id,
                joined_at=now_utc(),
            )
            self.db.add(member)
        invitation.status = InvitationStatus.ACCEPTED
        invitation.accepted_at = now_utc()
        self.db.flush()
        record_audit(
            self.db,
            "invitation.accepted",
            "invitation",
            organization_id=invitation.organization_id,
            actor_user_id=user.id,
            resource_id=invitation.id,
        )
        self.db.commit()
        self.db.refresh(member)
        return member

    def cancel(self, organization_id: uuid.UUID, invitation_id: uuid.UUID, actor: User) -> None:
        self.organizations.require_capability(
            organization_id, actor.id, Capability.INVITATIONS_MANAGE
        )
        invitation = self.db.get(OrganizationInvitation, invitation_id)
        if not invitation or invitation.organization_id != organization_id:
            raise NotFoundError("invitation_not_found", "Invitation was not found.")
        if invitation.status == InvitationStatus.PENDING:
            invitation.status = InvitationStatus.CANCELLED
            self.db.commit()
