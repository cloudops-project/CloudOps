from __future__ import annotations

import uuid

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models import (
    AuditEvent,
    AWSAccount,
    AWSExternalIDReservation,
    JiraIntegration,
    JiraIssueLink,
    Organization,
    OrganizationInvitation,
    OrganizationMembership,
    RefreshTokenSession,
    User,
)
from app.models.enums import (
    InvitationStatus,
    JiraIntegrationStatus,
    MembershipStatus,
    OrganizationRole,
)


class Repository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def user_by_email(self, email: str) -> User | None:
        return self.db.scalar(select(User).where(User.normalized_email == email))

    def user(self, user_id: uuid.UUID) -> User | None:
        return self.db.get(User, user_id)

    def organization(self, organization_id: uuid.UUID) -> Organization | None:
        return self.db.get(Organization, organization_id)

    def organization_by_slug(self, slug: str) -> Organization | None:
        return self.db.scalar(select(Organization).where(Organization.slug == slug))

    def membership(
        self, organization_id: uuid.UUID, user_id: uuid.UUID
    ) -> OrganizationMembership | None:
        return self.db.scalar(
            select(OrganizationMembership).where(
                OrganizationMembership.organization_id == organization_id,
                OrganizationMembership.user_id == user_id,
            )
        )

    def membership_by_id(
        self, organization_id: uuid.UUID, membership_id: uuid.UUID
    ) -> OrganizationMembership | None:
        return self.db.scalar(
            select(OrganizationMembership).where(
                OrganizationMembership.organization_id == organization_id,
                OrganizationMembership.id == membership_id,
            )
        )

    def active_membership(
        self, organization_id: uuid.UUID, user_id: uuid.UUID
    ) -> OrganizationMembership | None:
        return self.db.scalar(
            select(OrganizationMembership).where(
                OrganizationMembership.organization_id == organization_id,
                OrganizationMembership.user_id == user_id,
                OrganizationMembership.status == MembershipStatus.ACTIVE,
            )
        )

    def user_organizations(
        self, user_id: uuid.UUID
    ) -> list[tuple[Organization, OrganizationMembership]]:
        return list(
            self.db.execute(
                select(Organization, OrganizationMembership)
                .join(OrganizationMembership)
                .where(
                    OrganizationMembership.user_id == user_id,
                    OrganizationMembership.status == MembershipStatus.ACTIVE,
                )
                .order_by(Organization.name)
            )
            .tuples()
            .all()
        )

    def members(self, organization_id: uuid.UUID) -> list[tuple[OrganizationMembership, User]]:
        return list(
            self.db.execute(
                select(OrganizationMembership, User)
                .join(User, User.id == OrganizationMembership.user_id)
                .where(
                    OrganizationMembership.organization_id == organization_id,
                    OrganizationMembership.status != MembershipStatus.REMOVED,
                )
                .order_by(User.full_name)
            )
            .tuples()
            .all()
        )

    def active_owner_count(self, organization_id: uuid.UUID) -> int:
        owners = self.db.scalars(
            select(OrganizationMembership.id)
            .where(
                OrganizationMembership.organization_id == organization_id,
                OrganizationMembership.role == OrganizationRole.OWNER,
                OrganizationMembership.status == MembershipStatus.ACTIVE,
            )
            .with_for_update()
        ).all()
        return len(owners)

    def invitation_by_hash(self, token_hash: str) -> OrganizationInvitation | None:
        return self.db.scalar(
            select(OrganizationInvitation).where(OrganizationInvitation.token_hash == token_hash)
        )

    def invitation_by_hash_for_update(self, token_hash: str) -> OrganizationInvitation | None:
        """Serialize invitation acceptance for a single opaque token."""
        return self.db.scalar(
            select(OrganizationInvitation)
            .where(OrganizationInvitation.token_hash == token_hash)
            .with_for_update()
        )

    def invitation_for_update(
        self, organization_id: uuid.UUID, invitation_id: uuid.UUID
    ) -> OrganizationInvitation | None:
        """Lock one tenant-scoped invitation for resend or cancel.

        Filtering on organization_id inside the query means a cross-tenant
        identifier returns None rather than another organization's row, so the
        caller raises a non-disclosing not-found. FOR UPDATE serializes
        concurrent resend/cancel on the same invitation.
        """
        return self.db.scalar(
            select(OrganizationInvitation)
            .where(
                OrganizationInvitation.id == invitation_id,
                OrganizationInvitation.organization_id == organization_id,
            )
            .with_for_update()
        )

    def pending_invitation(
        self, organization_id: uuid.UUID, normalized_email: str
    ) -> OrganizationInvitation | None:
        return self.db.scalar(
            select(OrganizationInvitation).where(
                OrganizationInvitation.organization_id == organization_id,
                OrganizationInvitation.normalized_email == normalized_email,
                OrganizationInvitation.status == InvitationStatus.PENDING,
            )
        )

    def invitations(self, organization_id: uuid.UUID) -> list[OrganizationInvitation]:
        return list(
            self.db.scalars(
                select(OrganizationInvitation)
                .where(OrganizationInvitation.organization_id == organization_id)
                .order_by(OrganizationInvitation.created_at.desc())
            ).all()
        )

    def refresh_session(self, token_hash: str) -> RefreshTokenSession | None:
        return self.db.scalar(
            select(RefreshTokenSession).where(RefreshTokenSession.token_hash == token_hash)
        )

    def refresh_session_for_update(self, token_hash: str) -> RefreshTokenSession | None:
        """Lock a refresh session until its rotation transaction completes."""
        return self.db.scalar(
            select(RefreshTokenSession)
            .where(RefreshTokenSession.token_hash == token_hash)
            .with_for_update()
        )

    def revoke_family(self, family_id: uuid.UUID, revoked_at: object) -> None:
        self.db.execute(
            update(RefreshTokenSession)
            .where(
                RefreshTokenSession.family_id == family_id,
                RefreshTokenSession.revoked_at.is_(None),
            )
            .values(revoked_at=revoked_at)
        )

    def audit_events(self, organization_id: uuid.UUID, limit: int = 20) -> list[AuditEvent]:
        return list(
            self.db.scalars(
                select(AuditEvent)
                .where(AuditEvent.organization_id == organization_id)
                .order_by(AuditEvent.created_at.desc())
                .limit(limit)
            ).all()
        )

    def aws_accounts(self, organization_id: uuid.UUID) -> list[AWSAccount]:
        return list(
            self.db.scalars(
                select(AWSAccount)
                .where(AWSAccount.organization_id == organization_id)
                .order_by(AWSAccount.name)
            ).all()
        )

    def aws_account_for_user(
        self, account_id: uuid.UUID, user_id: uuid.UUID
    ) -> tuple[AWSAccount, OrganizationMembership] | None:
        return (
            self.db.execute(
                select(AWSAccount, OrganizationMembership)
                .join(
                    OrganizationMembership,
                    OrganizationMembership.organization_id == AWSAccount.organization_id,
                )
                .where(
                    AWSAccount.id == account_id,
                    OrganizationMembership.user_id == user_id,
                    OrganizationMembership.status == MembershipStatus.ACTIVE,
                )
            )
            .tuples()
            .one_or_none()
        )

    def aws_account_for_user_for_update(
        self, account_id: uuid.UUID, user_id: uuid.UUID, *, nowait: bool = False
    ) -> tuple[AWSAccount, OrganizationMembership] | None:
        """Lock one tenant-authorized AWS account lifecycle row."""
        return (
            self.db.execute(
                select(AWSAccount, OrganizationMembership)
                .join(
                    OrganizationMembership,
                    OrganizationMembership.organization_id == AWSAccount.organization_id,
                )
                .where(
                    AWSAccount.id == account_id,
                    OrganizationMembership.user_id == user_id,
                    OrganizationMembership.status == MembershipStatus.ACTIVE,
                )
                .execution_options(populate_existing=True)
                .with_for_update(of=AWSAccount, nowait=nowait)
            )
            .tuples()
            .one_or_none()
        )

    def aws_account_by_provider_id(
        self, organization_id: uuid.UUID, account_id: str
    ) -> AWSAccount | None:
        return self.db.scalar(
            select(AWSAccount).where(
                AWSAccount.organization_id == organization_id,
                AWSAccount.account_id == account_id,
            )
        )

    def aws_account_by_role_arn(
        self, organization_id: uuid.UUID, role_arn: str, exclude_id: uuid.UUID | None = None
    ) -> AWSAccount | None:
        statement = select(AWSAccount).where(
            AWSAccount.organization_id == organization_id,
            AWSAccount.role_arn == role_arn,
        )
        if exclude_id is not None:
            statement = statement.where(AWSAccount.id != exclude_id)
        return self.db.scalar(statement)

    def aws_account_by_external_id(self, external_id: str) -> AWSAccount | None:
        return self.db.scalar(select(AWSAccount).where(AWSAccount.external_id == external_id))

    def external_id_reservation(self, external_id: str) -> AWSExternalIDReservation | None:
        return self.db.scalar(
            select(AWSExternalIDReservation).where(
                AWSExternalIDReservation.external_id == external_id
            )
        )

    def external_id_reservation_for_account(
        self, account_id: uuid.UUID
    ) -> AWSExternalIDReservation | None:
        return self.db.scalar(
            select(AWSExternalIDReservation)
            .where(AWSExternalIDReservation.aws_account_id == account_id)
            .with_for_update()
        )

    def jira_integration_for_organization(
        self, organization_id: uuid.UUID
    ) -> JiraIntegration | None:
        return self.db.scalar(
            select(JiraIntegration)
            .where(
                JiraIntegration.organization_id == organization_id,
                JiraIntegration.status != JiraIntegrationStatus.DISCONNECTED,
            )
            .order_by(JiraIntegration.created_at.desc())
        )

    def jira_integration_for_organization_for_update(
        self, organization_id: uuid.UUID
    ) -> JiraIntegration | None:
        return self.db.scalar(
            select(JiraIntegration)
            .where(
                JiraIntegration.organization_id == organization_id,
                JiraIntegration.status != JiraIntegrationStatus.DISCONNECTED,
            )
            .order_by(JiraIntegration.created_at.desc())
            .with_for_update()
        )

    def jira_issue_link_by_idempotency_key(
        self, organization_id: uuid.UUID, idempotency_key: str
    ) -> JiraIssueLink | None:
        return self.db.scalar(
            select(JiraIssueLink).where(
                JiraIssueLink.organization_id == organization_id,
                JiraIssueLink.idempotency_key == idempotency_key,
            )
        )

    def jira_issue_links_for_finding(
        self, organization_id: uuid.UUID, finding_id: uuid.UUID
    ) -> list[JiraIssueLink]:
        return list(
            self.db.scalars(
                select(JiraIssueLink)
                .where(
                    JiraIssueLink.organization_id == organization_id,
                    JiraIssueLink.finding_id == finding_id,
                )
                .order_by(JiraIssueLink.created_at.desc())
            ).all()
        )
