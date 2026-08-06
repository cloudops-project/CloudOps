"""Record sanitized invitation delivery state without storing token material.

Adds three nullable columns to ``organization_invitations`` so the API and UI
can distinguish "pending and delivered" from "pending but delivery failed".
``InvitationStatus`` is deliberately unchanged: the partial unique index on
``status = 'pending'`` and its CHECK constraint stay exactly as they are, so a
failed delivery still occupies the single active-invitation slot and can be
resent rather than silently duplicated.

Why not reuse NotificationEvent / NotificationDeliveryAttempt (Option A)
-----------------------------------------------------------------------
The existing notification tables model a different, approval-gated workflow and
cannot represent invitation delivery without unsafe coupling. Four concrete
blockers, each verified against the current models and service:

1. Approval gate. ``NotificationService.deliver()`` refuses any event whose
   status is not ``APPROVED``, and ``notification_event_status_lifecycle``
   CHECK requires ``approved_at IS NOT NULL`` for both ``delivered`` and
   ``failed``. An invitation is authorized by the INVITATIONS_MANAGE
   capability at create time; routing it through a second human approval
   would change invitation semantics.

2. Recipient derivation. ``_recipients_for_event()`` derives recipients from
   *active organization members* (owners/admins) plus the evaluation actor.
   An invitee is by definition not yet a member, so the event would raise
   ``notification_invalid_recipient`` or, worse, mail the wrong people.

3. Dedupe constraint blocks resend. ``uq_notification_event_dedupe_key`` is
   unique on (organization_id, source_event_type, source_resource_id, channel,
   template_key). Every resend of one invitation would collide on that key.

4. Attempt ceiling. ``attempt_count <= 3`` CHECK caps an event at three
   attempts; invitation resend is an operator action with no such bound.

Option B is therefore taken. To avoid two conflicting sources of truth, no
NotificationEvent row is created for invitations: these three columns are the
single authoritative delivery state for an invitation, and the notification
tables remain exclusively the finding-alert workflow.

Fields
------
``last_delivery_status``      pending | sending | delivered | failed
``last_delivery_error_code``  short sanitized provider code, never an exception
``last_delivery_attempt_at``  when a send was last *attempted*
``last_delivered_at``         when a send last *succeeded*
``delivery_generation``       monotonic counter, incremented on every resend
                              and on cancel

``delivery_generation`` exists so a slow provider call cannot write a stale
result over a newer one. The generation is captured before the provider call
and re-checked under lock afterwards; a mismatch means a newer resend or a
cancel intervened, and the stale result is discarded rather than applied.

``last_sent_at`` from the first draft of this migration was ambiguous (attempt
or success?) and is deliberately split into the two explicit timestamps above.

No column stores a raw token, a token hash, an acceptance URL, an email body or
a raw provider exception.

Revision ID: 0020_invitation_delivery_state
Revises: 0019_live_remediation_data_model
Create Date: 2026-08-05 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "0020_invitation_delivery_state"
down_revision: str | None = "0019_live_remediation_data_model"
branch_labels: tuple[str, ...] | None = None
depends_on: tuple[str, ...] | None = None


def upgrade() -> None:
    op.add_column(
        "organization_invitations",
        sa.Column("last_delivery_status", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "organization_invitations",
        sa.Column("last_delivery_error_code", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "organization_invitations",
        sa.Column("last_delivery_attempt_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "organization_invitations",
        sa.Column("last_delivered_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "organization_invitations",
        sa.Column(
            "delivery_generation",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.create_check_constraint(
        "ck_invitation_delivery_status",
        "organization_invitations",
        sa.text(
            "last_delivery_status IS NULL OR last_delivery_status IN "
            "('pending', 'sending', 'delivered', 'failed')"
        ),
    )
    op.create_check_constraint(
        "ck_invitation_delivery_generation_nonnegative",
        "organization_invitations",
        sa.text("delivery_generation >= 0"),
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_invitation_delivery_generation_nonnegative",
        "organization_invitations",
        type_="check",
    )
    op.drop_constraint(
        "ck_invitation_delivery_status",
        "organization_invitations",
        type_="check",
    )
    op.drop_column("organization_invitations", "delivery_generation")
    op.drop_column("organization_invitations", "last_delivered_at")
    op.drop_column("organization_invitations", "last_delivery_attempt_at")
    op.drop_column("organization_invitations", "last_delivery_error_code")
    op.drop_column("organization_invitations", "last_delivery_status")
