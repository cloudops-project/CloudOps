from __future__ import annotations

import json
from typing import cast

import pytest
from pydantic import SecretStr, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.exceptions.errors import ConflictError
from app.models import NotificationDeliveryAttempt, NotificationEvent, PlatformJob
from app.models.enums import NotificationChannel, NotificationStatus
from app.services.notification_provider import (
    NotificationDeliveryOutcome,
    SMTPNotificationProvider,
    WebhookNotificationProvider,
    WebhookTransport,
)
from app.services.notifications import NotificationService
from app.tests.conftest import TestingSession
from app.tests.test_notifications_api import _pending_event
from app.worker.job_worker import JobWorker


def test_webhook_providers_validate_hosts_bound_payload_and_classify_retry() -> None:
    calls: list[tuple[str, bytes, int]] = []

    def throttled(url: str, payload: bytes, timeout: int) -> tuple[int, dict[str, str]]:
        calls.append((url, payload, timeout))
        return 429, {"retry-after": "7"}

    slack = WebhookNotificationProvider(
        key="slack",
        endpoint="https://hooks.slack.com/services/synthetic/path",
        channel=NotificationChannel.SLACK,
        allowed_host_suffixes=("hooks.slack.com",),
        timeout_seconds=3,
        max_message_bytes=4096,
        transport=cast(WebhookTransport, throttled),
    )
    result = slack.deliver(
        channel=NotificationChannel.SLACK,
        destination_reference=None,
        recipients=[],
        subject="CloudOps",
        text_body="Synthetic notification",
        template_key="security",
        context={},
    )
    assert result.outcome == NotificationDeliveryOutcome.FAILURE
    assert result.retryable is True
    assert result.retry_after_seconds == 7
    assert json.loads(calls[0][1])["text"].startswith("CloudOps")
    with pytest.raises(ValueError):
        WebhookNotificationProvider(
            key="slack",
            endpoint="https://example.invalid/ssrf",
            channel=NotificationChannel.SLACK,
            allowed_host_suffixes=("hooks.slack.com",),
            timeout_seconds=3,
            max_message_bytes=4096,
        )



def test_slack_success_contract_uses_synthetic_transport() -> None:
    endpoint = "https://hooks.slack.com/services/synthetic/success"
    calls: list[tuple[str, bytes, int]] = []

    def accepted(
        url: str,
        payload: bytes,
        timeout: int,
    ) -> tuple[int, dict[str, str]]:
        calls.append((url, payload, timeout))
        return 200, {"x-request-id": "synthetic-slack-message-id"}

    slack = WebhookNotificationProvider(
        key="slack",
        endpoint=endpoint,
        channel=NotificationChannel.SLACK,
        allowed_host_suffixes=("hooks.slack.com",),
        timeout_seconds=3,
        max_message_bytes=4096,
        transport=cast(WebhookTransport, accepted),
    )

    result = slack.deliver(
        channel=NotificationChannel.SLACK,
        destination_reference=None,
        recipients=[],
        subject="CloudOps",
        text_body="Synthetic Slack success",
        template_key="security",
        context={},
    )

    assert result.outcome == NotificationDeliveryOutcome.SUCCESS
    assert result.retryable is False
    assert result.provider_message_id == "synthetic-slack-message-id"
    assert len(calls) == 1
    assert calls[0][0] == endpoint
    assert calls[0][2] == 3


def test_webhook_rejects_non_https_endpoint() -> None:
    with pytest.raises(ValueError):
        WebhookNotificationProvider(
            key="slack",
            endpoint="http://hooks.slack.com/services/synthetic/insecure",
            channel=NotificationChannel.SLACK,
            allowed_host_suffixes=("hooks.slack.com",),
            timeout_seconds=3,
            max_message_bytes=4096,
        )


def test_teams_429_is_retryable_with_parsed_retry_after() -> None:
    def throttled(
        _url: str,
        _payload: bytes,
        _timeout: int,
    ) -> tuple[int, dict[str, str]]:
        return 429, {"retry-after": "12"}

    teams = WebhookNotificationProvider(
        key="teams",
        endpoint="https://synthetic.logic.azure.com/workflows/throttled",
        channel=NotificationChannel.TEAMS,
        allowed_host_suffixes=("logic.azure.com",),
        timeout_seconds=3,
        max_message_bytes=4096,
        transport=cast(WebhookTransport, throttled),
    )

    result = teams.deliver(
        channel=NotificationChannel.TEAMS,
        destination_reference=None,
        recipients=[],
        subject="CloudOps",
        text_body="Synthetic Teams throttle",
        template_key="security",
        context={},
    )

    assert result.outcome == NotificationDeliveryOutcome.FAILURE
    assert result.retryable is True
    assert result.retry_after_seconds == 12
    assert result.error_code == "webhook_http_429"


def test_webhook_transient_5xx_is_retryable() -> None:
    def unavailable(
        _url: str,
        _payload: bytes,
        _timeout: int,
    ) -> tuple[int, dict[str, str]]:
        return 503, {}

    teams = WebhookNotificationProvider(
        key="teams",
        endpoint="https://synthetic.logic.azure.com/workflows/unavailable",
        channel=NotificationChannel.TEAMS,
        allowed_host_suffixes=("logic.azure.com",),
        timeout_seconds=3,
        max_message_bytes=4096,
        transport=cast(WebhookTransport, unavailable),
    )

    result = teams.deliver(
        channel=NotificationChannel.TEAMS,
        destination_reference=None,
        recipients=[],
        subject="CloudOps",
        text_body="Synthetic Teams transient failure",
        template_key="security",
        context={},
    )

    assert result.outcome == NotificationDeliveryOutcome.FAILURE
    assert result.retryable is True
    assert result.retry_after_seconds is None
    assert result.error_code == "webhook_http_503"


def test_webhook_permanent_4xx_is_not_retryable() -> None:
    def rejected(
        _url: str,
        _payload: bytes,
        _timeout: int,
    ) -> tuple[int, dict[str, str]]:
        return 400, {}

    slack = WebhookNotificationProvider(
        key="slack",
        endpoint="https://hooks.slack.com/services/synthetic/rejected",
        channel=NotificationChannel.SLACK,
        allowed_host_suffixes=("hooks.slack.com",),
        timeout_seconds=3,
        max_message_bytes=4096,
        transport=cast(WebhookTransport, rejected),
    )

    result = slack.deliver(
        channel=NotificationChannel.SLACK,
        destination_reference=None,
        recipients=[],
        subject="CloudOps",
        text_body="Synthetic permanent rejection",
        template_key="security",
        context={},
    )

    assert result.outcome == NotificationDeliveryOutcome.FAILURE
    assert result.retryable is False
    assert result.retry_after_seconds is None
    assert result.error_code == "webhook_http_400"


def test_webhook_malformed_retry_after_falls_back_safely() -> None:
    def throttled_with_garbage(
        _url: str,
        _payload: bytes,
        _timeout: int,
    ) -> tuple[int, dict[str, str]]:
        return 429, {"retry-after": "not-a-number"}

    slack = WebhookNotificationProvider(
        key="slack",
        endpoint="https://hooks.slack.com/services/synthetic/malformed",
        channel=NotificationChannel.SLACK,
        allowed_host_suffixes=("hooks.slack.com",),
        timeout_seconds=3,
        max_message_bytes=4096,
        transport=cast(WebhookTransport, throttled_with_garbage),
    )

    result = slack.deliver(
        channel=NotificationChannel.SLACK,
        destination_reference=None,
        recipients=[],
        subject="CloudOps",
        text_body="Synthetic malformed Retry-After",
        template_key="security",
        context={},
    )

    assert result.outcome == NotificationDeliveryOutcome.FAILURE
    assert result.retryable is True
    assert result.retry_after_seconds is None
    assert result.error_code == "webhook_http_429"


def test_webhook_transport_timeout_is_retryable_without_network_access() -> None:
    def timed_out(
        _url: str,
        _payload: bytes,
        _timeout: int,
    ) -> tuple[int, dict[str, str]]:
        raise TimeoutError("synthetic transport timeout")

    teams = WebhookNotificationProvider(
        key="teams",
        endpoint="https://synthetic.logic.azure.com/workflows/timeout",
        channel=NotificationChannel.TEAMS,
        allowed_host_suffixes=("logic.azure.com",),
        timeout_seconds=3,
        max_message_bytes=4096,
        transport=cast(WebhookTransport, timed_out),
    )

    result = teams.deliver(
        channel=NotificationChannel.TEAMS,
        destination_reference=None,
        recipients=[],
        subject="CloudOps",
        text_body="Synthetic Teams timeout",
        template_key="security",
        context={},
    )

    assert result.outcome == NotificationDeliveryOutcome.FAILURE
    assert result.retryable is True
    assert result.retry_after_seconds is None
    assert result.error_code == "webhook_transport_error"
    assert result.sanitized_error == "Webhook notification delivery failed."


def test_webhook_endpoint_and_sentinel_never_appear_in_result() -> None:
    sentinel = "synthetic-sentinel-8f2c1e7a"
    endpoint = f"https://hooks.slack.com/services/{sentinel}/do-not-leak"

    def failing(
        _url: str,
        _payload: bytes,
        _timeout: int,
    ) -> tuple[int, dict[str, str]]:
        raise OSError(f"connection reset while calling {endpoint}")

    slack = WebhookNotificationProvider(
        key="slack",
        endpoint=endpoint,
        channel=NotificationChannel.SLACK,
        allowed_host_suffixes=("hooks.slack.com",),
        timeout_seconds=3,
        max_message_bytes=4096,
        transport=cast(WebhookTransport, failing),
    )

    result = slack.deliver(
        channel=NotificationChannel.SLACK,
        destination_reference=None,
        recipients=[],
        subject="CloudOps",
        text_body="Synthetic leakage probe",
        template_key="security",
        context={},
    )

    rendered = (
        f"{result.error_code or ''} "
        f"{result.sanitized_error or ''} "
        f"{result!r}"
    )

    assert result.outcome == NotificationDeliveryOutcome.FAILURE
    assert result.retryable is True
    assert result.error_code == "webhook_transport_error"
    assert sentinel not in rendered
    assert endpoint not in rendered
    assert "hooks.slack.com" not in rendered

def test_teams_provider_contract_uses_bounded_synthetic_transport() -> None:
    def accepted(_url: str, payload: bytes, _timeout: int) -> tuple[int, dict[str, str]]:
        assert len(payload) < 1024
        return 202, {"x-request-id": "synthetic-message-id"}

    teams = WebhookNotificationProvider(
        key="teams",
        endpoint="https://synthetic.logic.azure.com/workflows/test",
        channel=NotificationChannel.TEAMS,
        allowed_host_suffixes=("logic.azure.com",),
        timeout_seconds=3,
        max_message_bytes=1024,
        transport=cast(WebhookTransport, accepted),
    )
    result = teams.deliver(
        channel=NotificationChannel.TEAMS,
        destination_reference=None,
        recipients=[],
        subject="CloudOps",
        text_body="Synthetic Teams contract",
        template_key="security",
        context={},
    )
    assert result.outcome == NotificationDeliveryOutcome.SUCCESS
    assert result.provider_message_id == "synthetic-message-id"


def test_smtp_rejects_header_injection_without_network() -> None:
    settings = Settings(
        database_url=SecretStr("sqlite://"),
        jwt_secret_key=SecretStr("x" * 32),
        notification_provider="smtp",
    )
    result = SMTPNotificationProvider(settings).deliver(
        channel=NotificationChannel.EMAIL,
        destination_reference=None,
        recipients=["owner@example.com"],
        subject="CloudOps\r\nBcc: attacker@example.com",
        text_body="Safe body",
        template_key="security",
        context={},
    )
    assert result.error_code == "smtp_header_injection"


def test_production_provider_configuration_is_fail_closed() -> None:
    with pytest.raises((ValidationError, ValueError), match="STARTTLS"):
        Settings(
            database_url=SecretStr("postgresql://synthetic.invalid/cloudops"),
            jwt_secret_key=SecretStr("x" * 32),
            app_env="production",
            cookie_secure=True,
            cors_allowed_origins="https://cloudops.example.invalid",
            notification_provider="smtp",
            smtp_password=SecretStr("synthetic-smtp-fixture-password"),
        )
    with pytest.raises((ValidationError, ValueError), match="SLACK_WEBHOOK_URL"):
        Settings(
            database_url=SecretStr("postgresql://synthetic.invalid/cloudops"),
            jwt_secret_key=SecretStr("x" * 32),
            app_env="production",
            cookie_secure=True,
            cors_allowed_origins="https://cloudops.example.invalid",
            notification_provider="slack",
        )


def test_worker_rechecks_approval_and_records_sanitized_delivery_evidence(
    db: Session,
) -> None:
    event, organization_id, owner = _pending_event(db)
    service = NotificationService(db)
    service.approve(organization_id, event.id, owner)
    job = service.enqueue_delivery(organization_id, event.id, owner)
    db.commit()

    worker = JobWorker(TestingSession, get_settings(), "phase3-test-worker")
    assert worker.process_one() is True
    db.expire_all()
    delivered = db.get(NotificationEvent, event.id)
    assert delivered is not None and delivered.status == NotificationStatus.DELIVERED
    evidence = db.scalar(
        select(NotificationDeliveryAttempt).where(
            NotificationDeliveryAttempt.notification_event_id == event.id
        )
    )
    assert evidence is not None
    assert evidence.destination_reference.startswith("recipient_count:")
    assert "@" not in evidence.destination_reference
    completed = db.get(PlatformJob, job.id)
    assert completed is not None and completed.status.value == "succeeded"


def test_revoked_or_changed_approval_blocks_worker_delivery(db: Session) -> None:
    event, organization_id, owner = _pending_event(db)
    service = NotificationService(db)
    service.approve(organization_id, event.id, owner)
    service.enqueue_delivery(organization_id, event.id, owner)
    service.revoke_approval(organization_id, event.id, owner)
    db.commit()
    assert JobWorker(TestingSession, get_settings(), "revoked-worker").process_one()
    db.expire_all()
    assert db.get(NotificationEvent, event.id).status == NotificationStatus.PENDING_APPROVAL  # type: ignore[union-attr]
    assert db.scalar(select(NotificationDeliveryAttempt)) is None

    changed, changed_org, changed_owner = _pending_event(db)
    changed_service = NotificationService(db)
    changed_service.approve(changed_org, changed.id, changed_owner)
    changed.destination_reference = "changed-after-approval"
    with pytest.raises(ConflictError, match="changed after approval"):
        changed_service.deliver(changed_org, changed.id)
