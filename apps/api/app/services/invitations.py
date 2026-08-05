from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.exceptions.errors import ConflictError, ForbiddenError, NotFoundError
from app.models import OrganizationInvitation, OrganizationMembership, User
from app.models.enums import (
    AuditResult,
    InvitationStatus,
    MembershipStatus,
    NotificationChannel,
    OrganizationRole,
)
from app.repositories.data import Repository
from app.security.rbac import Capability, can_assign_role
from app.security.tokens import generate_opaque_token, hash_opaque_token
from app.services.common import is_expired, normalize_email, now_utc, record_audit
from app.services.notification_provider import (
    NotificationDeliveryOutcome,
    NotificationDeliveryResult,
    notification_provider_from_settings,
)
from app.services.organizations import OrganizationService

#: Delivery lifecycle. ``pending`` is reserved for rows created before this
#: feature (NULL) and for future queue-backed delivery; the synchronous path
#: moves directly from ``sending`` to ``delivered`` or ``failed``.
DELIVERY_PENDING = "pending"
DELIVERY_SENDING = "sending"
DELIVERY_DELIVERED = "delivered"
DELIVERY_FAILED = "failed"

__all__ = [
    "DELIVERY_DELIVERED",
    "DELIVERY_FAILED",
    "DELIVERY_PENDING",
    "DELIVERY_SENDING",
    "InvitationService",
]


@dataclass(frozen=True)
class _DeliverySnapshot:
    """Everything the provider call needs, detached from the ORM Session.

    Passing a frozen snapshot rather than an ORM instance is what guarantees
    the provider call cannot lazily emit SQL and so cannot re-open a
    transaction or hold a row lock while talking to SES/SMTP.
    """

    invitation_id: uuid.UUID
    organization_id: uuid.UUID
    organization_name: str
    email: str
    role: OrganizationRole
    expires_at: datetime
    generation: int


#: Providers that are a supported transport for invitation email. Slack and
#: Teams are webhook channels and cannot deliver a per-recipient invitation, so
#: they fail closed rather than silently dropping the message.
_EMAIL_PROVIDERS = frozenset({"smtp", "ses", "mock"})


class InvitationService:
    def __init__(self, db: Session, settings: Settings) -> None:
        self.db = db
        self.settings = settings
        self.repo = Repository(db)
        self.organizations = OrganizationService(db)

    # ------------------------------------------------------------------
    # Delivery
    # ------------------------------------------------------------------

    def _is_local_demo_delivery(self, provider_key: str) -> bool:
        """True only for a development SMTP/Mailpit send.

        This must never trigger for SES, staging, or production: it decides
        whether the local-only safety marker is added to the subject and
        body, and that marker must never reach a real recipient.
        """
        return self.settings.app_env == "development" and provider_key == "smtp"

    def _invitation_subject(self, provider_key: str) -> str:
        if self._is_local_demo_delivery(provider_key):
            return "[LOCAL DEMO ONLY] CloudOps organization invitation"
        return "CloudOps organization invitation"

    def _acceptance_url(self, raw_token: str) -> str:
        base = self.settings.frontend_url.rstrip("/")
        return f"{base}/invitations/accept?token={raw_token}"

    def _invitation_body(
        self, snapshot: _DeliverySnapshot, raw_token: str, provider_key: str
    ) -> str:
        """Build the invitation body.

        Contains exactly one acceptance URL and no internal identifiers, role
        ARNs, account IDs or provider details. The local-demo marker is
        prepended only for a development SMTP/Mailpit send.
        """
        expires = snapshot.expires_at.strftime("%Y-%m-%d %H:%M UTC")
        body = (
            f"You have been invited to join the {snapshot.organization_name} organization "
            "in CloudOps.\n\n"
            f"Assigned role: {snapshot.role.value}\n"
            f"This invitation expires on {expires}.\n\n"
            "Accept the invitation:\n"
            f"{self._acceptance_url(raw_token)}\n\n"
            "If you did not expect this invitation, ignore this message and the "
            "link will expire on its own."
        )
        if self._is_local_demo_delivery(provider_key):
            body = "LOCAL DEMO ONLY — NEVER USE IN PRODUCTION.\n\n" + body
        return body

    def _deliver(self, snapshot: _DeliverySnapshot, raw_token: str) -> NotificationDeliveryResult:
        """Send one invitation through the configured provider.

        Takes a plain immutable snapshot rather than an ORM object, so this
        method touches no ``Session`` and therefore cannot hold a row lock or
        keep a transaction open across network I/O. The caller must have
        committed and released every lock before calling this.

        Fails closed for unsupported or disabled configuration rather than
        reporting a delivery that never happened. The message body is never
        logged or persisted because it carries the acceptance URL.
        """
        provider_key = self.settings.notification_provider
        if provider_key not in _EMAIL_PROVIDERS:
            return NotificationDeliveryResult(
                outcome=NotificationDeliveryOutcome.FAILURE,
                sanitized_error="The configured notification provider cannot send email.",
                error_code="provider_not_email_capable",
                retryable=False,
            )
        if provider_key == "ses" and not self.settings.aws_ses_enabled:
            return NotificationDeliveryResult(
                outcome=NotificationDeliveryOutcome.FAILURE,
                sanitized_error="SES delivery is not enabled.",
                error_code="ses_disabled",
                retryable=False,
            )
        try:
            provider = notification_provider_from_settings(self.settings)
            return provider.deliver(
                channel=NotificationChannel.EMAIL,
                destination_reference=snapshot.email,
                recipients=[snapshot.email],
                subject=self._invitation_subject(provider_key),
                text_body=self._invitation_body(snapshot, raw_token, provider_key),
                template_key="organization_invitation",
                context={"invitation_id": str(snapshot.invitation_id)},
            )
        except Exception:
            # Deliberately swallow the provider exception: boto3 ClientError and
            # SMTP errors can carry endpoints, identities and request payloads.
            return NotificationDeliveryResult(
                outcome=NotificationDeliveryOutcome.FAILURE,
                sanitized_error="The invitation email could not be sent.",
                error_code="provider_unavailable",
                retryable=True,
            )

    def _snapshot(self, invitation: OrganizationInvitation) -> _DeliverySnapshot:
        """Capture delivery inputs while still inside Transaction A."""
        organization = self.repo.organization(invitation.organization_id)
        return _DeliverySnapshot(
            invitation_id=invitation.id,
            organization_id=invitation.organization_id,
            organization_name=organization.name if organization is not None else "CloudOps",
            email=invitation.email,
            role=invitation.role,
            expires_at=invitation.expires_at,
            generation=invitation.delivery_generation,
        )

    def _send_and_record(
        self, snapshot: _DeliverySnapshot, actor_id: uuid.UUID, raw: str
    ) -> OrganizationInvitation | None:
        """Provider call with no transaction open, then Transaction B.

        Ordering is the whole point of this method:

        1. ``self.db.commit()`` has already run in Transaction A and every lock
           is released before entry.
        2. The provider is called using only ``snapshot`` and ``raw``. No
           Session is touched, so no lock is held and no transaction is open
           during network I/O.
        3. Transaction B re-locks the row, compares ``delivery_generation``,
           and applies the result only if it still matches.

        A mismatch means a newer resend or a cancel happened while this send
        was in flight; the stale result is discarded so it cannot regress newer
        state (for example flipping a cancelled invitation back to delivered).
        """
        result = self._deliver(snapshot, raw)  # no DB transaction open here

        invitation = self.repo.invitation_for_update(
            snapshot.organization_id, snapshot.invitation_id
        )
        if invitation is None:
            self.db.rollback()
            return None
        succeeded = result.outcome == NotificationDeliveryOutcome.SUCCESS
        if invitation.delivery_generation != snapshot.generation:
            # Stale result. Record that it was discarded, without touching any
            # delivery field and without exposing the token or provider body.
            record_audit(
                self.db,
                "invitation.delivery_result_discarded",
                "invitation",
                result=AuditResult.FAILED,
                organization_id=snapshot.organization_id,
                actor_user_id=actor_id,
                resource_id=snapshot.invitation_id,
                metadata={
                    "reason": "stale_delivery_generation",
                    "observed_generation": invitation.delivery_generation,
                    "result_generation": snapshot.generation,
                    "provider": self.settings.notification_provider,
                },
            )
            self.db.commit()
            self.db.refresh(invitation)
            return invitation

        invitation.last_delivery_status = DELIVERY_DELIVERED if succeeded else DELIVERY_FAILED
        invitation.last_delivery_error_code = None if succeeded else result.error_code
        if succeeded:
            invitation.last_delivered_at = now_utc()
        metadata: dict[str, object] = {
            "role": invitation.role.value,
            "provider": self.settings.notification_provider,
            "recipient_count": 1,
            "delivery_generation": snapshot.generation,
        }
        if result.provider_message_id:
            metadata["provider_message_id"] = result.provider_message_id
        if not succeeded:
            metadata["error_code"] = result.error_code
            metadata["retryable"] = result.retryable
        self.db.flush()
        record_audit(
            self.db,
            "invitation.delivery_succeeded" if succeeded else "invitation.delivery_failed",
            "invitation",
            result=AuditResult.SUCCEEDED if succeeded else AuditResult.FAILED,
            organization_id=snapshot.organization_id,
            actor_user_id=actor_id,
            resource_id=snapshot.invitation_id,
            metadata=metadata,
        )
        self.db.commit()
        self.db.refresh(invitation)
        return invitation

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
            last_delivery_status=DELIVERY_SENDING,
            last_delivery_attempt_at=now_utc(),
            delivery_generation=0,
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
        snapshot = self._snapshot(invitation)
        # Transaction A: durably commit the invitation and its token hash
        # BEFORE any provider I/O, then release every lock. If this commit
        # fails, no email was sent, so a recipient can never hold a link to a
        # row that does not exist.
        try:
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            raise ConflictError(
                "active_invitation_exists", "A pending invitation already exists."
            ) from exc
        # Provider call (no transaction open) then Transaction B. The created
        # invitation is preserved and returned with its sanitized delivery
        # status even when delivery fails, so the client is never told the
        # invitation does not exist.
        delivered = self._send_and_record(snapshot, actor.id, raw)
        invitation = delivered if delivered is not None else invitation
        return invitation, raw if self.settings.app_env in {"development", "testing"} else None

    def resend(
        self, organization_id: uuid.UUID, invitation_id: uuid.UUID, actor: User
    ) -> tuple[OrganizationInvitation, str | None]:
        """Rotate the token of a pending invitation and send one new email.

        The previous token is invalidated immediately because the stored hash
        is replaced in the same transaction. Row is locked for update so two
        concurrent resends cannot both rotate the token.
        """
        self.organizations.require_capability(
            organization_id, actor.id, Capability.INVITATIONS_MANAGE
        )
        invitation = self.repo.invitation_for_update(organization_id, invitation_id)
        if invitation is None:
            raise NotFoundError("invitation_not_found", "Invitation was not found.")
        if invitation.status != InvitationStatus.PENDING:
            raise ConflictError("invitation_unavailable", "Invitation is no longer pending.")
        if is_expired(invitation.expires_at):
            invitation.status = InvitationStatus.EXPIRED
            self.db.commit()
            raise ConflictError("invitation_expired", "Invitation has expired.")

        raw = generate_opaque_token()
        invitation.token_hash = hash_opaque_token(raw)
        # Resend grants a fresh full expiry window: a resend normally happens
        # because the first email was missed or the invitation is close to
        # expiring, so preserving the original deadline would make the new link
        # useless. Organization, email and role are deliberately unchanged.
        invitation.expires_at = now_utc() + timedelta(
            hours=self.settings.invitation_token_expire_hours
        )
        invitation.last_delivery_status = DELIVERY_SENDING
        invitation.last_delivery_error_code = None
        invitation.last_delivery_attempt_at = now_utc()
        # Invalidate any in-flight provider result for the previous token.
        invitation.delivery_generation += 1
        self.db.flush()
        record_audit(
            self.db,
            "invitation.resent",
            "invitation",
            organization_id=organization_id,
            actor_user_id=actor.id,
            resource_id=invitation.id,
            metadata={
                "role": invitation.role.value,
                "delivery_generation": invitation.delivery_generation,
            },
        )
        snapshot = self._snapshot(invitation)
        # Transaction A: commit the rotated hash BEFORE sending and release the
        # row lock. The previous token is invalid from this point, and no email
        # can reference a hash that was never durably stored.
        self.db.commit()
        # Provider call (no lock, no open transaction) then Transaction B.
        delivered = self._send_and_record(snapshot, actor.id, raw)
        if delivered is None:
            raise NotFoundError("invitation_not_found", "Invitation was not found.")
        return delivered, raw if self.settings.app_env in {"development", "testing"} else None

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
            # Invalidate any in-flight send the same way cancel() does: bump
            # the generation so a slow provider result cannot later update an
            # invitation that is no longer pending.
            invitation.delivery_generation += 1
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
        # Invalidate any in-flight send the same way cancel() does: bump the
        # generation so a slow provider result cannot later overwrite this
        # invitation's delivery evidence with a stale success or failure.
        invitation.delivery_generation += 1
        self.db.flush()
        record_audit(
            self.db,
            "invitation.accepted",
            "invitation",
            organization_id=invitation.organization_id,
            actor_user_id=user.id,
            resource_id=invitation.id,
            metadata={"delivery_generation": invitation.delivery_generation},
        )
        self.db.commit()
        self.db.refresh(member)
        return member

    def cancel(self, organization_id: uuid.UUID, invitation_id: uuid.UUID, actor: User) -> None:
        self.organizations.require_capability(
            organization_id, actor.id, Capability.INVITATIONS_MANAGE
        )
        invitation = self.repo.invitation_for_update(organization_id, invitation_id)
        if not invitation:
            raise NotFoundError("invitation_not_found", "Invitation was not found.")
        if invitation.status == InvitationStatus.PENDING:
            invitation.status = InvitationStatus.CANCELLED
            # Bump the generation so a send already in flight cannot write a
            # delivered/failed result over the cancelled state. The email may
            # still arrive, but its token hash is no longer acceptable.
            invitation.delivery_generation += 1
            self.db.flush()
            record_audit(
                self.db,
                "invitation.cancelled",
                "invitation",
                organization_id=organization_id,
                actor_user_id=actor.id,
                resource_id=invitation.id,
                metadata={
                    "role": invitation.role.value,
                    "delivery_generation": invitation.delivery_generation,
                },
            )
            self.db.commit()
        else:
            # Idempotent no-op for an already cancelled/accepted/expired
            # invitation; releases the lock without changing state.
            self.db.rollback()
