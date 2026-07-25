from __future__ import annotations

import smtplib
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import make_msgid
from enum import StrEnum
from typing import Protocol

from app.core.config import Settings
from app.models.enums import NotificationChannel


class NotificationDeliveryOutcome(StrEnum):
    SUCCESS = "success"
    FAILURE = "failure"


@dataclass(frozen=True)
class NotificationDeliveryResult:
    outcome: NotificationDeliveryOutcome
    sanitized_error: str | None = None
    provider_message_id: str | None = None


class NotificationProvider(Protocol):
    key: str

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
    ) -> NotificationDeliveryResult: ...


class MockNotificationProvider:
    """Deterministic, offline notification provider for tests and normal local development.

    It performs no network I/O, no sleeps, and no background work.
    """

    key = "mock"

    def __init__(self, fault_mode: str = "success") -> None:
        self.fault_mode = fault_mode
        self.invocations = 0

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
        if self.fault_mode == "success":
            return NotificationDeliveryResult(outcome=NotificationDeliveryOutcome.SUCCESS)
        if self.fault_mode == "always_fail":
            return NotificationDeliveryResult(
                outcome=NotificationDeliveryOutcome.FAILURE,
                sanitized_error="Mock provider was configured to fail delivery.",
            )
        if self.fault_mode == "fail_then_succeed" and self.invocations == 1:
            return NotificationDeliveryResult(
                outcome=NotificationDeliveryOutcome.FAILURE,
                sanitized_error="Mock provider transient failure.",
            )
        return NotificationDeliveryResult(outcome=NotificationDeliveryOutcome.SUCCESS)


class SMTPNotificationProvider:
    """Synchronous SMTP provider for the local Mailpit demo path."""

    key = "smtp"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

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
        if channel != NotificationChannel.EMAIL:
            return NotificationDeliveryResult(
                outcome=NotificationDeliveryOutcome.FAILURE,
                sanitized_error="Unsupported notification channel.",
            )
        if not recipients:
            return NotificationDeliveryResult(
                outcome=NotificationDeliveryOutcome.FAILURE,
                sanitized_error="No valid notification recipients.",
            )

        message = EmailMessage()
        from_name = self.settings.smtp_from_name.strip()
        from_email = self.settings.smtp_from_email.strip()
        message["From"] = f"{from_name} <{from_email}>" if from_name else from_email
        message["To"] = ", ".join(recipients)
        message["Subject"] = subject
        message["Message-ID"] = make_msgid(domain="cloudops.local")
        message.set_content(text_body)

        try:
            with smtplib.SMTP(self.settings.smtp_host, self.settings.smtp_port, timeout=10) as smtp:
                if self.settings.smtp_use_tls:
                    smtp.starttls()
                password = self.settings.smtp_password.get_secret_value()
                if self.settings.smtp_username:
                    smtp.login(self.settings.smtp_username, password)
                refused = smtp.send_message(message)
        except Exception:
            return NotificationDeliveryResult(
                outcome=NotificationDeliveryOutcome.FAILURE,
                sanitized_error="SMTP notification delivery failed.",
            )
        if refused:
            return NotificationDeliveryResult(
                outcome=NotificationDeliveryOutcome.FAILURE,
                sanitized_error=(
                    "SMTP notification delivery was refused for one or more recipients."
                ),
            )
        return NotificationDeliveryResult(
            outcome=NotificationDeliveryOutcome.SUCCESS,
            provider_message_id=message["Message-ID"],
        )


def notification_provider_from_settings(settings: Settings) -> NotificationProvider:
    if settings.notification_provider == "smtp":
        return SMTPNotificationProvider(settings)
    if settings.notification_provider == "ses":
        raise RuntimeError("SES notification provider is not implemented for Version 1.")
    return MockNotificationProvider()
