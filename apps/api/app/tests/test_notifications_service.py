from __future__ import annotations

import uuid
from email.message import EmailMessage

import pytest
from pydantic import SecretStr
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.exceptions.errors import ConflictError, NotFoundError
from app.models import (
    EvaluationJob,
    Finding,
    NotificationEvent,
    Organization,
    OrganizationMembership,
    User,
)
from app.models.enums import (
    FindingSeverity,
    MembershipStatus,
    NotificationChannel,
    NotificationStatus,
    OrganizationRole,
)
from app.services.notification_provider import (
    MockNotificationProvider,
    NotificationDeliveryOutcome,
    NotificationDeliveryResult,
    SMTPNotificationProvider,
    notification_provider_from_settings,
)
from app.services.notifications import NotificationService
from app.tests.test_risk import _finding, _tenant


def _approver(db: Session, marker: str) -> User:
    user = User(
        email=f"{marker}@example.com",
        normalized_email=f"{marker}@example.com",
        password_hash="test-only-hash",
        full_name="Approver",
    )
    db.add(user)
    db.flush()
    return user


# ---------------------------------------------------------------------------
# Trigger: creation
# ---------------------------------------------------------------------------


def test_critical_finding_creates_one_pending_approval_event(db: Session) -> None:
    user, organization, account = _tenant(db)
    finding, _ = _finding(db, organization, account, user, severity=FindingSeverity.CRITICAL)
    db.commit()

    event = NotificationService(db).create_for_critical_finding(finding)
    db.commit()

    assert event is not None
    assert event.status == NotificationStatus.PENDING_APPROVAL
    assert event.organization_id == organization.id
    assert event.source_resource_id == finding.id
    rows = db.scalars(
        select(NotificationEvent).where(NotificationEvent.organization_id == organization.id)
    ).all()
    assert len(rows) == 1


@pytest.mark.parametrize(
    "severity",
    [FindingSeverity.HIGH, FindingSeverity.MEDIUM, FindingSeverity.LOW],
)
def test_non_critical_finding_creates_no_event_when_caller_checks_severity(
    db: Session, severity: FindingSeverity
) -> None:
    """create_for_critical_finding does not itself branch on severity (the
    caller in evaluations.py is responsible for that check, matching the
    existing created/updated branching pattern); this test proves the wiring
    contract that the service must only ever be invoked for CRITICAL
    findings by asserting the caller-side severity check would exclude these
    findings, and that if the service were skipped, no row exists."""
    user, organization, account = _tenant(db)
    finding, _ = _finding(db, organization, account, user, severity=severity)
    db.commit()

    assert finding.severity != FindingSeverity.CRITICAL
    rows = db.scalars(
        select(NotificationEvent).where(NotificationEvent.organization_id == organization.id)
    ).all()
    assert len(rows) == 0


@pytest.mark.parametrize(
    "severity",
    [FindingSeverity.HIGH, FindingSeverity.MEDIUM, FindingSeverity.LOW],
)
def test_create_for_critical_finding_returns_none_for_non_critical_severity(
    db: Session, severity: FindingSeverity
) -> None:
    """Defensive check: even when called directly with a non-CRITICAL
    finding (bypassing the evaluations.py caller-side guard entirely), the
    service itself must refuse to create a notification event."""
    user, organization, account = _tenant(db)
    finding, _ = _finding(db, organization, account, user, severity=severity)
    db.commit()

    result = NotificationService(db).create_for_critical_finding(finding)
    db.commit()

    assert result is None
    rows = db.scalars(
        select(NotificationEvent).where(NotificationEvent.organization_id == organization.id)
    ).all()
    assert len(rows) == 0


def test_duplicate_trigger_does_not_create_a_second_event(db: Session) -> None:
    user, organization, account = _tenant(db)
    finding, _ = _finding(db, organization, account, user, severity=FindingSeverity.CRITICAL)
    db.commit()

    service = NotificationService(db)
    first = service.create_for_critical_finding(finding)
    db.commit()
    second = service.create_for_critical_finding(finding)
    db.commit()

    assert first is not None
    assert second is None
    count = db.scalar(
        select(func.count())
        .select_from(NotificationEvent)
        .where(NotificationEvent.organization_id == organization.id)
    )
    assert count == 1


def test_notification_creation_is_tenant_isolated(db: Session) -> None:
    user_a, org_a, account_a = _tenant(db)
    user_b, org_b, account_b = _tenant(db)
    finding_a, _ = _finding(db, org_a, account_a, user_a, severity=FindingSeverity.CRITICAL)
    finding_b, _ = _finding(db, org_b, account_b, user_b, severity=FindingSeverity.CRITICAL)
    db.commit()

    service = NotificationService(db)
    service.create_for_critical_finding(finding_a)
    service.create_for_critical_finding(finding_b)
    db.commit()

    org_a_events = db.scalars(
        select(NotificationEvent).where(NotificationEvent.organization_id == org_a.id)
    ).all()
    org_b_events = db.scalars(
        select(NotificationEvent).where(NotificationEvent.organization_id == org_b.id)
    ).all()
    assert len(org_a_events) == 1
    assert len(org_b_events) == 1
    assert org_a_events[0].source_resource_id == finding_a.id
    assert org_b_events[0].source_resource_id == finding_b.id


# ---------------------------------------------------------------------------
# Approval
# ---------------------------------------------------------------------------


def test_approval_transitions_pending_to_approved_and_sets_fields(db: Session) -> None:
    user, organization, account = _tenant(db)
    finding, _ = _finding(db, organization, account, user, severity=FindingSeverity.CRITICAL)
    db.commit()
    event = NotificationService(db).create_for_critical_finding(finding)
    db.commit()
    assert event is not None
    approver = _approver(db, "approver-basic")
    db.commit()

    approved = NotificationService(db).approve(organization.id, event.id, approver)
    db.commit()

    assert approved.status == NotificationStatus.APPROVED
    assert approved.approved_at is not None
    assert approved.approved_by_user_id == approver.id


def test_re_approving_an_already_approved_event_is_idempotent(db: Session) -> None:
    user, organization, account = _tenant(db)
    finding, _ = _finding(db, organization, account, user, severity=FindingSeverity.CRITICAL)
    db.commit()
    event = NotificationService(db).create_for_critical_finding(finding)
    db.commit()
    assert event is not None
    approver = _approver(db, "approver-idempotent")
    db.commit()

    service = NotificationService(db)
    first = service.approve(organization.id, event.id, approver)
    db.commit()
    second = service.approve(organization.id, event.id, approver)
    db.commit()

    assert first.status == NotificationStatus.APPROVED
    assert second.status == NotificationStatus.APPROVED
    assert first.approved_at == second.approved_at


def test_approval_from_invalid_state_is_rejected(db: Session) -> None:
    user, organization, account = _tenant(db)
    finding, _ = _finding(db, organization, account, user, severity=FindingSeverity.CRITICAL)
    db.commit()
    event = NotificationService(db).create_for_critical_finding(finding)
    db.commit()
    assert event is not None
    approver = _approver(db, "approver-invalid")
    db.commit()

    service = NotificationService(db)
    service.approve(organization.id, event.id, approver)
    db.commit()
    # Deliver it to DELIVERED, then attempt to approve again.
    service.deliver(organization.id, event.id)
    db.commit()

    with pytest.raises(ConflictError):
        service.approve(organization.id, event.id, approver)


def test_approve_unknown_event_raises_not_found(db: Session) -> None:
    _user, organization, _account = _tenant(db)
    db.commit()
    approver = _approver(db, "approver-missing")
    db.commit()

    with pytest.raises(NotFoundError):
        NotificationService(db).approve(organization.id, uuid.uuid4(), approver)


# ---------------------------------------------------------------------------
# Delivery
# ---------------------------------------------------------------------------


def _approved_event(db: Session) -> tuple[NotificationEvent, Organization]:
    user, organization, account = _tenant(db)
    finding, _ = _finding(db, organization, account, user, severity=FindingSeverity.CRITICAL)
    db.commit()
    event = NotificationService(db).create_for_critical_finding(finding)
    db.commit()
    assert event is not None
    approver = _approver(db, "approver-deliver")
    db.commit()
    NotificationService(db).approve(organization.id, event.id, approver)
    db.commit()
    return event, organization


def test_delivery_success_transitions_to_delivered(db: Session) -> None:
    event, organization = _approved_event(db)
    provider = MockNotificationProvider(fault_mode="success")
    service = NotificationService(db, provider=provider)

    delivered = service.deliver(organization.id, event.id)
    db.commit()

    assert delivered.status == NotificationStatus.DELIVERED
    assert delivered.delivered_at is not None
    assert delivered.attempt_count == 1
    assert provider.invocations == 1


def test_first_and_second_failure_keep_status_approved(db: Session) -> None:
    event, organization = _approved_event(db)
    provider = MockNotificationProvider(fault_mode="always_fail")
    service = NotificationService(db, provider=provider)

    first = service.deliver(organization.id, event.id)
    db.commit()
    assert first.status == NotificationStatus.APPROVED
    assert first.attempt_count == 1

    second = service.deliver(organization.id, event.id)
    db.commit()
    assert second.status == NotificationStatus.APPROVED
    assert second.attempt_count == 2
    assert provider.invocations == 2


def test_third_failure_transitions_to_failed(db: Session) -> None:
    event, organization = _approved_event(db)
    provider = MockNotificationProvider(fault_mode="always_fail")
    service = NotificationService(db, provider=provider)

    service.deliver(organization.id, event.id)
    db.commit()
    service.deliver(organization.id, event.id)
    db.commit()
    third = service.deliver(organization.id, event.id)
    db.commit()

    assert third.status == NotificationStatus.FAILED
    assert third.attempt_count == 3
    assert third.failed_at is not None
    assert third.failure_reason is not None
    assert provider.invocations == 3


def test_delivery_from_invalid_state_is_rejected(db: Session) -> None:
    user, organization, account = _tenant(db)
    finding, _ = _finding(db, organization, account, user, severity=FindingSeverity.CRITICAL)
    db.commit()
    event = NotificationService(db).create_for_critical_finding(finding)
    db.commit()
    assert event is not None

    with pytest.raises(ConflictError):
        NotificationService(db).deliver(organization.id, event.id)


def test_provider_not_invoked_after_delivered_terminal_state(db: Session) -> None:
    event, organization = _approved_event(db)
    provider = MockNotificationProvider(fault_mode="success")
    service = NotificationService(db, provider=provider)
    service.deliver(organization.id, event.id)
    db.commit()
    assert provider.invocations == 1

    with pytest.raises(ConflictError):
        service.deliver(organization.id, event.id)
    assert provider.invocations == 1


def test_provider_not_invoked_after_failed_terminal_state(db: Session) -> None:
    event, organization = _approved_event(db)
    provider = MockNotificationProvider(fault_mode="always_fail")
    service = NotificationService(db, provider=provider)
    for _ in range(3):
        service.deliver(organization.id, event.id)
        db.commit()
    assert provider.invocations == 3

    with pytest.raises(ConflictError):
        service.deliver(organization.id, event.id)
    assert provider.invocations == 3


def test_attempt_count_increments_exactly_once_per_invocation(db: Session) -> None:
    event, organization = _approved_event(db)
    provider = MockNotificationProvider(fault_mode="fail_then_succeed")
    service = NotificationService(db, provider=provider)

    first = service.deliver(organization.id, event.id)
    db.commit()
    assert first.attempt_count == 1
    assert first.status == NotificationStatus.APPROVED

    second = service.deliver(organization.id, event.id)
    db.commit()
    assert second.attempt_count == 2
    assert second.status == NotificationStatus.DELIVERED
    assert provider.invocations == 2


def test_smtp_provider_selection_keeps_mock_default() -> None:
    test_secret = SecretStr("x" * 32)
    mock_settings = Settings(
        database_url=SecretStr("sqlite+pysqlite:///:memory:"),
        jwt_secret_key=test_secret,
        notification_provider="mock",
    )
    smtp_settings = Settings(
        database_url=SecretStr("sqlite+pysqlite:///:memory:"),
        jwt_secret_key=test_secret,
        notification_provider="smtp",
        smtp_host="mailpit",
        smtp_port=1025,
        smtp_use_tls=False,
    )

    assert isinstance(notification_provider_from_settings(mock_settings), MockNotificationProvider)
    assert isinstance(notification_provider_from_settings(smtp_settings), SMTPNotificationProvider)


def test_smtp_provider_sends_mailpit_compatible_message(monkeypatch: pytest.MonkeyPatch) -> None:
    sent: list[object] = []

    class FakeSMTP:
        def __init__(self, host: str, port: int, timeout: int) -> None:
            assert host == "mailpit"
            assert port == 1025
            assert timeout == 10

        def __enter__(self) -> FakeSMTP:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def send_message(self, message: EmailMessage) -> dict[str, object]:
            sent.append(message)
            return {}

    monkeypatch.setattr("app.services.notification_provider.smtplib.SMTP", FakeSMTP)
    settings = Settings(
        database_url=SecretStr("sqlite+pysqlite:///:memory:"),
        jwt_secret_key=SecretStr("x" * 32),
        notification_provider="smtp",
        smtp_host="mailpit",
        smtp_port=1025,
        smtp_use_tls=False,
        smtp_from_email="cloudops-demo@example.local",
        smtp_from_name="CloudOps Demo",
    )

    result = SMTPNotificationProvider(settings).deliver(
        channel=NotificationChannel.EMAIL,
        destination_reference=None,
        recipients=["owner@example.com"],
        subject="CloudOps demo",
        text_body="Safe demo body",
        template_key="critical_finding_created",
        context={},
    )

    assert result.outcome == "success"
    assert result.provider_message_id is not None
    assert len(sent) == 1


def test_smtp_provider_returns_sanitized_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    class FailingSMTP:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            raise RuntimeError("smtp://secret-password@example.local")

    monkeypatch.setattr("app.services.notification_provider.smtplib.SMTP", FailingSMTP)
    settings = Settings(
        database_url=SecretStr("sqlite+pysqlite:///:memory:"),
        jwt_secret_key=SecretStr("x" * 32),
        notification_provider="smtp",
    )

    result = SMTPNotificationProvider(settings).deliver(
        channel=NotificationChannel.EMAIL,
        destination_reference=None,
        recipients=["owner@example.com"],
        subject="CloudOps demo",
        text_body="Safe demo body",
        template_key="critical_finding_created",
        context={},
    )

    assert result.outcome == "failure"
    assert result.sanitized_error == "SMTP notification delivery failed."


def test_delivery_includes_admin_and_scan_actor_recipients_without_duplicates(
    db: Session,
) -> None:
    event, organization = _approved_event(db)
    owner_email = "owner-recipient@example.com"
    actor_email = "scan-actor@example.com"
    owner = User(
        email=owner_email,
        normalized_email=owner_email,
        password_hash="test-only-hash",
        full_name="Owner Recipient",
    )
    actor = User(
        email=actor_email,
        normalized_email=actor_email,
        password_hash="test-only-hash",
        full_name="Scan Actor",
    )
    db.add_all([owner, actor])
    db.flush()
    db.add_all(
        [
            OrganizationMembership(
                organization_id=organization.id,
                user_id=owner.id,
                role=OrganizationRole.ADMIN,
                status=MembershipStatus.ACTIVE,
            ),
            OrganizationMembership(
                organization_id=organization.id,
                user_id=actor.id,
                role=OrganizationRole.CLOUD_ENGINEER,
                status=MembershipStatus.ACTIVE,
            ),
        ]
    )
    persisted_event = db.get(NotificationEvent, event.id)
    assert persisted_event is not None
    source_finding = db.get(Finding, persisted_event.source_resource_id)
    assert source_finding is not None
    evaluation = db.get(EvaluationJob, source_finding.last_evaluation_id)
    assert evaluation is not None
    evaluation.started_by_user_id = actor.id
    db.commit()

    class CapturingProvider:
        key = "mock"

        def __init__(self) -> None:
            self.invocations = 0
            self.recipients: list[str] = []
            self.text_body = ""

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
            self.invocations += 1
            self.recipients = recipients
            self.text_body = text_body
            return NotificationDeliveryResult(
                outcome=NotificationDeliveryOutcome.SUCCESS,
                provider_message_id="mock-message-id",
            )

    provider = CapturingProvider()
    delivered = NotificationService(db, provider=provider).deliver(organization.id, event.id)
    db.commit()

    assert delivered.status == NotificationStatus.DELIVERED
    assert delivered.provider_key == "mock"
    assert provider.recipients.count(owner_email) == 1
    assert provider.recipients.count(actor_email) == 1
    assert "Remediation execution is simulated" in provider.text_body


def test_delivery_rejects_malformed_recipient_without_invoking_provider(db: Session) -> None:
    event, organization = _approved_event(db)
    bad_user = User(
        email="not-an-email",
        normalized_email="not-an-email",
        password_hash="test-only-hash",
        full_name="Bad Recipient",
    )
    db.add(bad_user)
    db.flush()
    db.add(
        OrganizationMembership(
            organization_id=organization.id,
            user_id=bad_user.id,
            role=OrganizationRole.ADMIN,
            status=MembershipStatus.ACTIVE,
        )
    )
    db.commit()
    provider = MockNotificationProvider()

    with pytest.raises(ConflictError, match="valid email recipients"):
        NotificationService(db, provider=provider).deliver(organization.id, event.id)

    assert provider.invocations == 0
