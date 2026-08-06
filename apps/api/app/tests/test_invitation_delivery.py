"""Transaction-ordering and delivery-generation tests for invitation email.

The invariants under test are the ones that are expensive to get wrong:

* the provider is never called before the invitation is durably committed, so
  a recipient can never hold a link to a row that does not exist;
* no database transaction or row lock is held while the provider is called;
* a slow in-flight send cannot overwrite newer state produced by a later
  resend or by a cancel;
* no raw token, acceptance URL, body or provider exception reaches the
  database, the audit log, or an API response.
"""

from __future__ import annotations

import os
import re
import uuid
from collections.abc import Callable, Generator
from dataclasses import dataclass
from datetime import timedelta

import pytest
from pydantic import SecretStr
from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import URL, Engine
from sqlalchemy.engine.url import make_url
from sqlalchemy.orm import Session, sessionmaker

from alembic import command
from app.core.config import Settings, get_settings
from app.exceptions.errors import ConflictError, ForbiddenError, NotFoundError
from app.models import (
    AuditEvent,
    Organization,
    OrganizationInvitation,
    OrganizationMembership,
    User,
)
from app.models.enums import (
    InvitationStatus,
    MembershipStatus,
    NotificationChannel,
    OrganizationRole,
    OrganizationStatus,
    UserStatus,
)
from app.security.passwords import hash_password
from app.security.tokens import hash_opaque_token
from app.services import invitations as invitations_module
from app.services.common import normalize_email, now_utc
from app.services.invitations import (
    DELIVERY_DELIVERED,
    DELIVERY_FAILED,
    DELIVERY_SENDING,
    InvitationService,
)
from app.services.notification_provider import (
    NotificationDeliveryOutcome,
    NotificationDeliveryResult,
)
from app.tests.test_zzz_stage5_migration import _config, _database

# ---------------------------------------------------------------------------
# PostgreSQL fixture infrastructure.
#
# This suite owns its own disposable database rather than connecting to
# whatever POSTGRES_TEST_DATABASE_URL already points at. CI runs
# `pytest app/tests -ra` before its later standalone Alembic steps, so the
# base cloudops_test database is empty at collection time; asserting that
# migrated tables already exist there (the earlier approach) failed on a
# clean CI database. Instead this reuses the same _database()/_config()
# helpers app/tests/test_zzz_stage5_migration.py already uses to create a
# uniquely named cloudops_e2e_* database, run `alembic upgrade head` inside
# it, and drop it again on teardown -- never SQLite, never
# Base.metadata.create_all.
# ---------------------------------------------------------------------------

POSTGRES_TEST_DATABASE_URL = os.getenv("POSTGRES_TEST_DATABASE_URL")
if POSTGRES_TEST_DATABASE_URL:
    _postgres_database_name = make_url(POSTGRES_TEST_DATABASE_URL).database or ""
else:
    _postgres_database_name = ""

if POSTGRES_TEST_DATABASE_URL and not (
    _postgres_database_name == "cloudops_test"
    or _postgres_database_name.startswith("cloudops_e2e_")
):
    raise RuntimeError(
        "POSTGRES_TEST_DATABASE_URL must target cloudops_test or a cloudops_e2e_* database"
    )


@pytest.fixture(scope="module")
def postgres_database_url() -> Generator[URL, None, None]:
    assert POSTGRES_TEST_DATABASE_URL is not None
    with _database("invitation_delivery") as url:
        config = _config(url)
        command.upgrade(config, "head")
        yield url


@pytest.fixture(scope="module")
def postgres_engine(postgres_database_url: URL) -> Generator[Engine, None, None]:
    engine = create_engine(postgres_database_url, pool_pre_ping=True)
    with engine.connect() as connection:
        tables = set(
            connection.execute(
                text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
            ).scalars()
        )
    assert {"users", "organizations", "organization_invitations"} <= tables, (
        "alembic upgrade head did not create the expected tables in the "
        "disposable invitation-delivery test database"
    )
    yield engine
    engine.dispose()


@pytest.fixture(scope="module")
def postgres_sessions(postgres_engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=postgres_engine, expire_on_commit=False)


@pytest.fixture(scope="module")
def postgres_settings(postgres_database_url: URL) -> Settings:
    return Settings(
        app_env="testing",
        database_url=SecretStr(postgres_database_url.render_as_string(hide_password=False)),
        jwt_secret_key=SecretStr("postgres-invitation-delivery-test-secret-at-least-32-characters"),
    )


# ---------------------------------------------------------------------------
# Doubles
# ---------------------------------------------------------------------------


@dataclass
class _Call:
    subject: str
    text_body: str
    recipients: list[str]


class RecordingProvider:
    """Captures what was sent and lets a test observe DB state mid-send."""

    key = "mock"

    def __init__(
        self,
        outcome: NotificationDeliveryOutcome = NotificationDeliveryOutcome.SUCCESS,
        error_code: str | None = None,
        retryable: bool = False,
        on_deliver: Callable[[], None] | None = None,
        raises: Exception | None = None,
    ) -> None:
        self.calls: list[_Call] = []
        self.outcome = outcome
        self.error_code = error_code
        self.retryable = retryable
        self.on_deliver = on_deliver
        self.raises = raises

    def deliver(
        self,
        *,
        channel: NotificationChannel,
        destination_reference: str | None,
        recipients: list[str],
        subject: str,
        text_body: str,
        template_key: str,
        context: dict[str, object],
    ) -> NotificationDeliveryResult:
        self.calls.append(_Call(subject=subject, text_body=text_body, recipients=list(recipients)))
        if self.on_deliver is not None:
            self.on_deliver()
        if self.raises is not None:
            raise self.raises
        return NotificationDeliveryResult(
            outcome=self.outcome,
            sanitized_error=None
            if self.outcome == NotificationDeliveryOutcome.SUCCESS
            else "The invitation email could not be sent.",
            error_code=self.error_code,
            retryable=self.retryable,
            provider_message_id="msg-1"
            if self.outcome == NotificationDeliveryOutcome.SUCCESS
            else None,
        )


@pytest.fixture
def provider(monkeypatch: pytest.MonkeyPatch) -> RecordingProvider:
    recorder = RecordingProvider()
    monkeypatch.setattr(
        invitations_module, "notification_provider_from_settings", lambda _s: recorder
    )
    return recorder


def _install(monkeypatch: pytest.MonkeyPatch, recorder: RecordingProvider) -> None:
    monkeypatch.setattr(
        invitations_module, "notification_provider_from_settings", lambda _s: recorder
    )


# ---------------------------------------------------------------------------
# Fixtures for a minimal organization + owner
# ---------------------------------------------------------------------------


@pytest.fixture
def settings() -> Settings:
    return get_settings()


@pytest.fixture
def service(db: Session, settings: Settings) -> InvitationService:
    return InvitationService(db, settings)


def _make_org_and_owner(
    db: Session, *, org_name: str = "Acme", owner_email: str = "owner@example.com"
) -> tuple[uuid.UUID, User]:
    """Create a committed organization with an ACTIVE owner membership."""
    from app.models import Organization, OrganizationMembership
    from app.models.enums import MembershipStatus, OrganizationStatus, UserStatus
    from app.security.passwords import hash_password
    from app.services.common import normalize_email, now_utc

    owner = User(
        email=owner_email,
        normalized_email=normalize_email(owner_email),
        password_hash=hash_password("Sup3r-Secret-Passw0rd!"),
        full_name=f"{org_name} Owner",
        status=UserStatus.ACTIVE,
    )
    db.add(owner)
    db.flush()
    org = Organization(
        name=org_name,
        slug=org_name.lower(),
        status=OrganizationStatus.ACTIVE,
        created_by_user_id=owner.id,
    )
    db.add(org)
    db.flush()
    db.add(
        OrganizationMembership(
            organization_id=org.id,
            user_id=owner.id,
            role=OrganizationRole.OWNER,
            status=MembershipStatus.ACTIVE,
            joined_at=now_utc(),
        )
    )
    db.commit()
    return org.id, owner


@pytest.fixture
def org_and_owner(db: Session) -> tuple[uuid.UUID, User]:
    return _make_org_and_owner(db)


@pytest.fixture
def organization_id(org_and_owner: tuple[uuid.UUID, User]) -> uuid.UUID:
    return org_and_owner[0]


@pytest.fixture
def owner(org_and_owner: tuple[uuid.UUID, User]) -> User:
    return org_and_owner[1]


@pytest.fixture
def other_organization_id(db: Session) -> uuid.UUID:
    org_id, _ = _make_org_and_owner(db, org_name="Other", owner_email="other-owner@example.com")
    return org_id


@pytest.fixture
def invitee(db: Session) -> User:
    from app.models.enums import UserStatus
    from app.security.passwords import hash_password
    from app.services.common import normalize_email

    user = User(
        email="invitee@example.com",
        normalized_email=normalize_email("invitee@example.com"),
        password_hash=hash_password("An0ther-Secret-Passw0rd!"),
        full_name="Invitation Test User",
        status=UserStatus.ACTIVE,
    )
    db.add(user)
    db.commit()
    return user


def _audit_types(db: Session, invitation_id: uuid.UUID) -> list[str]:
    return [
        row[0]
        for row in db.execute(
            select(AuditEvent.event_type).where(AuditEvent.resource_id == invitation_id)
        ).all()
    ]


def _audit_metadata_blob(db: Session, invitation_id: uuid.UUID) -> str:
    rows = db.execute(
        select(AuditEvent.metadata_json).where(AuditEvent.resource_id == invitation_id)
    ).all()
    return " ".join(str(row[0]) for row in rows)


# ---------------------------------------------------------------------------
# 1-3. Ordering: commit strictly before provider I/O
# ---------------------------------------------------------------------------


def test_provider_is_not_called_before_invitation_is_committed(
    db: Session,
    service: InvitationService,
    owner: User,
    organization_id: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The row must be visible in the database at the moment the provider runs."""
    seen: dict[str, object] = {}

    def observe() -> None:
        # A fresh read through the same session must already see a committed row.
        row = db.execute(
            select(OrganizationInvitation).where(
                OrganizationInvitation.normalized_email == "invitee@example.com"
            )
        ).scalar_one_or_none()
        seen["row_exists_during_send"] = row is not None
        seen["in_transaction_during_send"] = db.in_transaction()

    recorder = RecordingProvider(on_deliver=observe)
    _install(monkeypatch, recorder)

    service.create(organization_id, owner, "invitee@example.com", OrganizationRole.VIEWER)

    assert len(recorder.calls) == 1
    assert seen["row_exists_during_send"] is True


@pytest.mark.postgres_only
def test_no_row_lock_is_held_during_provider_call(
    postgres_sessions: sessionmaker[Session],
    postgres_settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A second, independent PostgreSQL session must be able to lock the row
    while the send is running.

    This exercises real PostgreSQL row locking end to end, not the SQLite
    ``db``/``service``/``owner``/``organization_id`` fixtures: SQLite ignores
    ``FOR UPDATE`` entirely, which would make a NOWAIT-lock assertion pass
    vacuously and hide the very regression it is meant to catch. All rows
    (owner, organization, membership, invitation) are created through
    PostgreSQL-backed sessions built from ``postgres_sessions``, and
    ``InvitationService`` is constructed on its own PostgreSQL session
    (Session A). If Transaction A leaked a FOR UPDATE lock across the
    provider call, the NOWAIT attempt from the independent Session B would
    raise ``OperationalError: could not obtain lock`` instead of succeeding.

    Session B uses a short PostgreSQL ``statement_timeout`` in addition to
    NOWAIT so a real regression fails fast with a clear error rather than
    hanging the test suite.
    """
    email = f"lock-check-{uuid.uuid4()}@example.com"

    with postgres_sessions.begin() as setup_db:
        owner_email = f"lock-owner-{uuid.uuid4()}@example.com"
        owner = User(
            email=owner_email,
            normalized_email=normalize_email(owner_email),
            password_hash=hash_password("Sup3r-Secret-Passw0rd!"),
            full_name="Lock Check Owner",
            status=UserStatus.ACTIVE,
        )
        setup_db.add(owner)
        setup_db.flush()
        organization = Organization(
            name="Lock Check Org",
            slug=f"lock-check-{uuid.uuid4()}",
            status=OrganizationStatus.ACTIVE,
            created_by_user_id=owner.id,
        )
        setup_db.add(organization)
        setup_db.flush()
        setup_db.add(
            OrganizationMembership(
                organization_id=organization.id,
                user_id=owner.id,
                role=OrganizationRole.OWNER,
                status=MembershipStatus.ACTIVE,
                joined_at=now_utc(),
            )
        )
        owner_id = owner.id
        organization_id = organization.id

    outcome: dict[str, object] = {}

    def observe() -> None:
        # Session B: fully independent connection/session/transaction from
        # Session A (the InvitationService session below). A short
        # statement_timeout bounds how long a real regression can hang this
        # test, and NOWAIT means a held lock raises immediately instead of
        # blocking.
        with postgres_sessions() as other:
            try:
                other.execute(text("SET LOCAL statement_timeout = '2000ms'"))
                other.execute(
                    text(
                        "SELECT id FROM organization_invitations "
                        "WHERE normalized_email = :e FOR UPDATE NOWAIT"
                    ),
                    {"e": email},
                )
                outcome["lockable"] = True
            except Exception as exc:  # pragma: no cover - failure path is the assertion
                outcome["lockable"] = False
                outcome["error"] = repr(exc)
            finally:
                other.rollback()

    recorder = RecordingProvider(on_deliver=observe)
    monkeypatch.setattr(
        invitations_module, "notification_provider_from_settings", lambda _s: recorder
    )

    with postgres_sessions() as service_db:
        service = InvitationService(service_db, postgres_settings)
        owner_row = service_db.get(User, owner_id)
        assert owner_row is not None
        service.create(organization_id, owner_row, email, OrganizationRole.VIEWER)

    try:
        assert len(recorder.calls) == 1
        assert outcome.get("lockable") is True, outcome.get("error")
    finally:
        # Clean up this test's own rows; membership/invitation cascade off
        # the organization's foreign keys.
        with postgres_sessions.begin() as cleanup_db:
            cleanup_db.execute(
                text("DELETE FROM organizations WHERE id = :id"), {"id": organization_id}
            )
            cleanup_db.execute(text("DELETE FROM users WHERE id = :id"), {"id": owner_id})
            invitee = cleanup_db.scalar(
                select(User).where(User.normalized_email == normalize_email(email))
            )
            if invitee is not None:
                cleanup_db.delete(invitee)


def test_commit_failure_in_transaction_a_causes_zero_provider_calls(
    db: Session,
    service: InvitationService,
    owner: User,
    organization_id: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorder = RecordingProvider()
    _install(monkeypatch, recorder)
    service.create(organization_id, owner, "dupe@example.com", OrganizationRole.VIEWER)
    recorder.calls.clear()

    # A duplicate pending invitation must be rejected and must not send.
    with pytest.raises(ConflictError):
        service.create(organization_id, owner, "dupe@example.com", OrganizationRole.VIEWER)
    assert recorder.calls == []


# ---------------------------------------------------------------------------
# 4-6, 9. Delivery generation and races
# ---------------------------------------------------------------------------


def test_resend_increments_delivery_generation(
    db: Session,
    service: InvitationService,
    owner: User,
    organization_id: uuid.UUID,
    provider: RecordingProvider,
) -> None:
    invitation, _ = service.create(
        organization_id, owner, "gen@example.com", OrganizationRole.VIEWER
    )
    assert invitation.delivery_generation == 0
    resent, _ = service.resend(organization_id, invitation.id, owner)
    assert resent.delivery_generation == 1


def test_stale_provider_result_does_not_regress_newer_state(
    db: Session,
    service: InvitationService,
    owner: User,
    organization_id: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Resend A finishing after Resend B must not overwrite B's result."""
    recorder = RecordingProvider()
    _install(monkeypatch, recorder)
    invitation, _ = service.create(
        organization_id, owner, "race@example.com", OrganizationRole.VIEWER
    )

    # Simulate a slow send whose generation is already behind.
    stale = invitations_module._DeliverySnapshot(
        invitation_id=invitation.id,
        organization_id=organization_id,
        organization_name="Org",
        email="race@example.com",
        role=OrganizationRole.VIEWER,
        expires_at=invitation.expires_at,
        generation=invitation.delivery_generation,
    )
    service.resend(organization_id, invitation.id, owner)  # generation -> 1
    db.expire_all()
    current = db.get(OrganizationInvitation, invitation.id)
    assert current is not None
    before_status = current.last_delivery_status

    service._send_and_record(stale, owner.id, "stale-raw-token")

    db.expire_all()
    after = db.get(OrganizationInvitation, invitation.id)
    assert after is not None
    assert after.delivery_generation == 1
    assert after.last_delivery_status == before_status
    assert "invitation.delivery_result_discarded" in _audit_types(db, invitation.id)


def test_cancel_during_in_flight_send_keeps_cancelled_state(
    db: Session,
    service: InvitationService,
    owner: User,
    organization_id: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A cancel that lands while a send is in flight must win.

    The provider callback fires from inside ``_send_and_record``'s provider
    call, i.e. after Transaction A (the ``create()`` commit) has already
    released its lock but before Transaction B re-locks the row to apply the
    result. At that point the invitation is genuinely PENDING/SENDING in the
    database. The callback cancels it there, which bumps
    ``delivery_generation``; when the provider returns success, Transaction B
    must observe a generation mismatch and discard the now-stale success
    instead of overwriting the cancellation.
    """

    def cancel_during_provider_call() -> None:
        invitation = db.scalar(
            select(OrganizationInvitation).where(
                OrganizationInvitation.organization_id == organization_id,
                OrganizationInvitation.normalized_email == "cancelme@example.com",
            )
        )
        assert invitation is not None
        assert invitation.status == InvitationStatus.PENDING
        assert invitation.last_delivery_status == DELIVERY_SENDING
        service.cancel(organization_id, invitation.id, owner)

    recorder = RecordingProvider(on_deliver=cancel_during_provider_call)
    _install(monkeypatch, recorder)

    invitation, raw_token = service.create(
        organization_id, owner, "cancelme@example.com", OrganizationRole.VIEWER
    )

    assert len(recorder.calls) == 1  # the provider genuinely ran once

    db.expire_all()
    after = db.get(OrganizationInvitation, invitation.id)
    assert after is not None
    assert after.status == InvitationStatus.CANCELLED
    assert after.delivery_generation > 0
    assert after.last_delivery_status != DELIVERY_DELIVERED

    assert "invitation.delivery_result_discarded" in _audit_types(db, invitation.id)
    blob = _audit_metadata_blob(db, invitation.id)
    assert "stale_delivery_generation" in blob
    if raw_token is not None:
        assert raw_token not in blob
        assert "cancelme@example.com" not in blob
        # Cancelled: the token hash still resolves, but status is no longer
        # PENDING, so acceptance is rejected.
        with pytest.raises(ConflictError):
            service.accept(raw_token, owner)


# ---------------------------------------------------------------------------
# 7-8. Token rotation
# ---------------------------------------------------------------------------


def test_old_token_invalid_and_new_token_valid_after_resend(
    db: Session,
    service: InvitationService,
    owner: User,
    organization_id: uuid.UUID,
    invitee: User,
    provider: RecordingProvider,
) -> None:
    invitation, first = service.create(
        organization_id, owner, invitee.email, OrganizationRole.VIEWER
    )
    assert first is not None
    _, second = service.resend(organization_id, invitation.id, owner)
    assert second is not None and second != first

    db.expire_all()
    row = db.get(OrganizationInvitation, invitation.id)
    assert row is not None
    assert row.token_hash == hash_opaque_token(second)
    assert row.token_hash != hash_opaque_token(first)

    with pytest.raises(NotFoundError):
        service.accept(first, invitee)
    member = service.accept(second, invitee)
    assert member.organization_id == organization_id


# ---------------------------------------------------------------------------
# 10-12. Failure handling and leakage
# ---------------------------------------------------------------------------


def test_provider_failure_leaves_invitation_pending_and_resendable(
    db: Session,
    service: InvitationService,
    owner: User,
    organization_id: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorder = RecordingProvider(
        outcome=NotificationDeliveryOutcome.FAILURE, error_code="ses_timeout", retryable=True
    )
    _install(monkeypatch, recorder)
    invitation, _ = service.create(
        organization_id, owner, "fails@example.com", OrganizationRole.VIEWER
    )
    assert invitation.status == InvitationStatus.PENDING
    assert invitation.last_delivery_status == DELIVERY_FAILED
    assert invitation.last_delivery_error_code == "ses_timeout"
    assert invitation.last_delivered_at is None
    assert "invitation.delivery_failed" in _audit_types(db, invitation.id)

    recorder.outcome = NotificationDeliveryOutcome.SUCCESS
    recorder.error_code = None
    resent, _ = service.resend(organization_id, invitation.id, owner)
    assert resent.last_delivery_status == DELIVERY_DELIVERED


def test_provider_exception_is_sanitized(
    db: Session,
    service: InvitationService,
    owner: User,
    organization_id: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    boom = RuntimeError("arn:aws:ses:ap-south-1:123456789012:identity/secret.example")
    recorder = RecordingProvider(raises=boom)
    _install(monkeypatch, recorder)
    invitation, _ = service.create(
        organization_id, owner, "boom@example.com", OrganizationRole.VIEWER
    )
    assert invitation.last_delivery_status == DELIVERY_FAILED
    assert invitation.last_delivery_error_code == "provider_unavailable"
    blob = _audit_metadata_blob(db, invitation.id)
    assert "123456789012" not in blob
    assert "arn:aws" not in blob


def test_no_token_or_url_reaches_database_or_audit(
    db: Session,
    service: InvitationService,
    owner: User,
    organization_id: uuid.UUID,
    provider: RecordingProvider,
) -> None:
    invitation, raw = service.create(
        organization_id, owner, "leak@example.com", OrganizationRole.VIEWER
    )
    assert raw is not None
    # The provider genuinely received the acceptance URL...
    assert raw in provider.calls[0].text_body
    # ...but nothing persisted may contain it.
    db.expire_all()
    row = db.get(OrganizationInvitation, invitation.id)
    assert row is not None
    persisted = " ".join(
        str(v)
        for v in (
            row.token_hash,
            row.last_delivery_status,
            row.last_delivery_error_code,
            row.email,
            row.normalized_email,
        )
    )
    assert raw not in persisted
    assert "/invitations/accept" not in persisted
    blob = _audit_metadata_blob(db, invitation.id)
    assert raw not in blob
    assert "/invitations/accept" not in blob
    assert row.token_hash not in blob


# ---------------------------------------------------------------------------
# 13. Tenant isolation
# ---------------------------------------------------------------------------


def test_cross_tenant_resend_and_cancel_are_non_disclosing(
    service: InvitationService,
    owner: User,
    organization_id: uuid.UUID,
    other_organization_id: uuid.UUID,
    provider: RecordingProvider,
) -> None:
    invitation, _ = service.create(
        organization_id, owner, "iso@example.com", OrganizationRole.VIEWER
    )
    with pytest.raises((NotFoundError, ForbiddenError)):
        service.resend(other_organization_id, invitation.id, owner)
    with pytest.raises((NotFoundError, ForbiddenError)):
        service.cancel(other_organization_id, invitation.id, owner)


# ---------------------------------------------------------------------------
# Acceptance is independent of delivery evidence
# ---------------------------------------------------------------------------


def test_acceptance_works_even_when_delivery_failed(
    db: Session,
    service: InvitationService,
    owner: User,
    organization_id: uuid.UUID,
    invitee: User,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorder = RecordingProvider(
        outcome=NotificationDeliveryOutcome.FAILURE, error_code="ses_timeout", retryable=True
    )
    _install(monkeypatch, recorder)
    invitation, raw = service.create(organization_id, owner, invitee.email, OrganizationRole.VIEWER)
    assert raw is not None
    assert invitation.last_delivery_status == DELIVERY_FAILED
    member = service.accept(raw, invitee)
    assert member.organization_id == organization_id


def test_sending_state_is_set_before_delivery_resolves(
    db: Session,
    service: InvitationService,
    owner: User,
    organization_id: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed: dict[str, object] = {}

    def observe() -> None:
        row = db.execute(
            select(OrganizationInvitation).where(
                OrganizationInvitation.normalized_email == "sending@example.com"
            )
        ).scalar_one_or_none()
        observed["status"] = row.last_delivery_status if row else None
        observed["attempt_at_set"] = bool(row and row.last_delivery_attempt_at)

    recorder = RecordingProvider(on_deliver=observe)
    _install(monkeypatch, recorder)
    service.create(organization_id, owner, "sending@example.com", OrganizationRole.VIEWER)
    assert observed["status"] == DELIVERY_SENDING
    assert observed["attempt_at_set"] is True


# ---------------------------------------------------------------------------
# 14. Local-demo marker is scoped to development SMTP only
# ---------------------------------------------------------------------------


def test_ses_invitation_has_no_local_demo_marker(
    db: Session,
    settings: Settings,
    owner: User,
    organization_id: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A non-development SES send must use the plain subject and body.

    The local-demo marker is guarded on both ``app_env == "development"`` and
    ``notification_provider == "smtp"``; this proves the SES/production path
    (app_env=production, provider=ses) never sees the marker even though the
    provider is a synthetic double, not real SES or SMTP.
    """
    recorder = RecordingProvider()
    _install(monkeypatch, recorder)
    monkeypatch.setattr(settings, "app_env", "production")
    monkeypatch.setattr(settings, "notification_provider", "ses")
    monkeypatch.setattr(settings, "aws_ses_enabled", True)

    service = InvitationService(db, settings)
    service.create(organization_id, owner, "ses-recipient@example.com", OrganizationRole.VIEWER)

    assert len(recorder.calls) == 1
    call = recorder.calls[0]
    assert call.subject == "CloudOps organization invitation"
    assert "LOCAL DEMO ONLY" not in call.subject
    assert "LOCAL DEMO ONLY" not in call.text_body


# ---------------------------------------------------------------------------
# 15-16. Acceptance invalidates any in-flight send
# ---------------------------------------------------------------------------


def _token_from_body(text_body: str) -> str:
    match = re.search(r"[?&]token=([^\s&]+)", text_body)
    assert match is not None, text_body
    return match.group(1)


def test_accept_during_in_flight_send_discards_stale_result(
    db: Session,
    service: InvitationService,
    owner: User,
    organization_id: uuid.UUID,
    invitee: User,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Acceptance racing an in-flight send must win, exactly like cancel().

    The provider callback fires after Transaction A (the ``create()``
    commit) has released its lock but before Transaction B re-locks to apply
    the result. The callback reads the real acceptance token out of the
    email body the provider actually received (not a shortcut return value)
    and calls the real ``service.accept()`` there, then the provider reports
    a late failure. ``accept()`` must have bumped ``delivery_generation`` so
    that late failure is discarded rather than overwriting the now-accepted
    invitation's delivery evidence.
    """
    membership_id: dict[str, object] = {}

    def accept_during_provider_call() -> None:
        token = _token_from_body(recorder.calls[-1].text_body)
        member = service.accept(token, invitee)
        membership_id["id"] = member.id

    recorder = RecordingProvider(
        outcome=NotificationDeliveryOutcome.FAILURE,
        error_code="late_provider_failure",
        on_deliver=accept_during_provider_call,
    )
    _install(monkeypatch, recorder)

    invitation, _ = service.create(organization_id, owner, invitee.email, OrganizationRole.VIEWER)

    assert len(recorder.calls) == 1  # the provider genuinely ran once
    assert membership_id.get("id") is not None  # accept() genuinely succeeded mid-send

    db.expire_all()
    after = db.get(OrganizationInvitation, invitation.id)
    assert after is not None
    assert after.status == InvitationStatus.ACCEPTED
    assert after.delivery_generation > 0
    assert after.last_delivery_status != DELIVERY_FAILED
    assert after.last_delivery_error_code != "late_provider_failure"

    membership = db.scalar(
        select(OrganizationMembership).where(
            OrganizationMembership.organization_id == organization_id,
            OrganizationMembership.user_id == invitee.id,
        )
    )
    assert membership is not None

    assert "invitation.delivery_result_discarded" in _audit_types(db, invitation.id)
    blob = _audit_metadata_blob(db, invitation.id)
    assert "stale_delivery_generation" in blob
    token = _token_from_body(recorder.calls[0].text_body)
    assert token not in blob
    assert "/invitations/accept" not in blob


def test_accept_time_expiry_invalidates_generation(
    db: Session,
    service: InvitationService,
    owner: User,
    organization_id: uuid.UUID,
    invitee: User,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An expired invitation discovered at accept-time must also fence off
    any in-flight send, the same way a live cancel or acceptance does."""
    recorder = RecordingProvider()
    _install(monkeypatch, recorder)
    invitation, raw = service.create(organization_id, owner, invitee.email, OrganizationRole.VIEWER)
    assert raw is not None
    before_generation = invitation.delivery_generation

    db.expire_all()
    row = db.get(OrganizationInvitation, invitation.id)
    assert row is not None
    row.expires_at = now_utc() - timedelta(minutes=1)
    db.commit()

    with pytest.raises(ConflictError):
        service.accept(raw, invitee)

    db.expire_all()
    after = db.get(OrganizationInvitation, invitation.id)
    assert after is not None
    assert after.status == InvitationStatus.EXPIRED
    assert after.delivery_generation == before_generation + 1
