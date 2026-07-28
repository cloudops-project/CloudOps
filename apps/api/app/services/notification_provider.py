from __future__ import annotations

import json
import re
import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import make_msgid
from enum import StrEnum
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

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
    error_code: str | None = None
    retryable: bool = False
    retry_after_seconds: int | None = None


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
                error_code="mock_transient_failure",
                retryable=True,
            )
        if self.fault_mode == "fail_then_succeed" and self.invocations == 1:
            return NotificationDeliveryResult(
                outcome=NotificationDeliveryOutcome.FAILURE,
                sanitized_error="Mock provider transient failure.",
                error_code="mock_transient_failure",
                retryable=True,
            )
        return NotificationDeliveryResult(outcome=NotificationDeliveryOutcome.SUCCESS)


class SMTPNotificationProvider:
    """Bounded SMTP adapter for Mailpit verification and production SMTP relays."""

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
                error_code="invalid_recipient",
            )
        if any("\r" in value or "\n" in value for value in [subject, *recipients]):
            return NotificationDeliveryResult(
                outcome=NotificationDeliveryOutcome.FAILURE,
                sanitized_error="Notification headers contain prohibited characters.",
                error_code="smtp_header_injection",
            )
        if len(subject) > 998:
            return NotificationDeliveryResult(
                outcome=NotificationDeliveryOutcome.FAILURE,
                sanitized_error="Notification subject exceeds the configured limit.",
                error_code="smtp_subject_too_large",
            )

        message = EmailMessage()
        from_name = self.settings.smtp_from_name.strip()
        from_email = self.settings.smtp_from_email.strip()
        message["From"] = f"{from_name} <{from_email}>" if from_name else from_email
        message["To"] = ", ".join(recipients)
        message["Subject"] = subject
        message["Message-ID"] = make_msgid(domain="cloudops.local")
        message.set_content(text_body)
        if len(message.as_bytes()) > self.settings.notification_max_message_bytes:
            return NotificationDeliveryResult(
                outcome=NotificationDeliveryOutcome.FAILURE,
                sanitized_error="Notification message exceeds the configured size limit.",
                error_code="smtp_message_too_large",
            )

        try:
            tls_context = ssl.create_default_context()
            security = (
                "starttls"
                if self.settings.smtp_use_tls and self.settings.smtp_security == "none"
                else self.settings.smtp_security
            )
            if security == "implicit":
                smtp_connection: smtplib.SMTP = smtplib.SMTP_SSL(
                    self.settings.smtp_host,
                    self.settings.smtp_port,
                    timeout=self.settings.smtp_timeout_seconds,
                    context=tls_context,
                )
            else:
                smtp_connection = smtplib.SMTP(
                    self.settings.smtp_host,
                    self.settings.smtp_port,
                    timeout=self.settings.smtp_timeout_seconds,
                )
            with smtp_connection as smtp:
                if security == "starttls":
                    smtp.starttls(context=tls_context)
                    smtp.ehlo()
                password = self.settings.smtp_password.get_secret_value()
                if self.settings.smtp_username:
                    smtp.login(self.settings.smtp_username, password)
                refused = smtp.send_message(message)
        except smtplib.SMTPResponseException as exc:
            retryable = 400 <= exc.smtp_code < 500
            return NotificationDeliveryResult(
                outcome=NotificationDeliveryOutcome.FAILURE,
                sanitized_error="SMTP notification delivery failed.",
                error_code=f"smtp_{exc.smtp_code}",
                retryable=retryable,
            )
        except (TimeoutError, OSError, smtplib.SMTPException):
            return NotificationDeliveryResult(
                outcome=NotificationDeliveryOutcome.FAILURE,
                sanitized_error="SMTP notification delivery failed.",
                error_code="smtp_transport_error",
                retryable=True,
            )
        except Exception:
            return NotificationDeliveryResult(
                outcome=NotificationDeliveryOutcome.FAILURE,
                sanitized_error="SMTP notification delivery failed.",
                error_code="smtp_internal_error",
            )
        if refused:
            return NotificationDeliveryResult(
                outcome=NotificationDeliveryOutcome.FAILURE,
                sanitized_error=(
                    "SMTP notification delivery was refused for one or more recipients."
                ),
                error_code="smtp_recipient_refused",
            )
        return NotificationDeliveryResult(
            outcome=NotificationDeliveryOutcome.SUCCESS,
            provider_message_id=message["Message-ID"],
        )


class WebhookTransport(Protocol):
    def __call__(
        self, url: str, payload: bytes, timeout_seconds: int
    ) -> tuple[int, dict[str, str]]: ...


class WebhookNotificationProvider:
    """Slack/Teams webhook adapter with strict endpoint and response bounds."""

    def __init__(
        self,
        *,
        key: str,
        endpoint: str,
        channel: NotificationChannel,
        allowed_host_suffixes: tuple[str, ...],
        timeout_seconds: int,
        max_message_bytes: int,
        transport: WebhookTransport | None = None,
    ) -> None:
        self.key = key
        self.endpoint = endpoint
        self.channel = channel
        self.allowed_host_suffixes = allowed_host_suffixes
        self.timeout_seconds = timeout_seconds
        self.max_message_bytes = max_message_bytes
        self.transport = transport or _send_webhook
        self._validate_endpoint()

    def _validate_endpoint(self) -> None:
        parsed = urlsplit(self.endpoint)
        host = (parsed.hostname or "").casefold()
        if (
            parsed.scheme != "https"
            or not host
            or parsed.username is not None
            or parsed.password is not None
            or parsed.fragment
            or not any(
                host == suffix or host.endswith(f".{suffix}")
                for suffix in self.allowed_host_suffixes
            )
        ):
            raise ValueError(f"{self.key} webhook endpoint is not approved")

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
        if channel != self.channel:
            return NotificationDeliveryResult(
                outcome=NotificationDeliveryOutcome.FAILURE,
                sanitized_error="Unsupported notification channel.",
                error_code="unsupported_channel",
            )
        clean_text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", text_body)
        payload = json.dumps(
            {"text": f"{subject}\n\n{clean_text}"},
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode()
        if len(payload) > self.max_message_bytes:
            return NotificationDeliveryResult(
                outcome=NotificationDeliveryOutcome.FAILURE,
                sanitized_error="Webhook message exceeds the configured size limit.",
                error_code="webhook_message_too_large",
            )
        try:
            status, headers = self.transport(
                self.endpoint, payload, self.timeout_seconds
            )
        except (OSError, TimeoutError, URLError):
            return NotificationDeliveryResult(
                outcome=NotificationDeliveryOutcome.FAILURE,
                sanitized_error="Webhook notification delivery failed.",
                error_code="webhook_transport_error",
                retryable=True,
            )
        if 200 <= status < 300:
            return NotificationDeliveryResult(
                outcome=NotificationDeliveryOutcome.SUCCESS,
                provider_message_id=headers.get("x-request-id"),
            )
        retry_after = _retry_after(headers)
        if status == 429 or 500 <= status < 600:
            return NotificationDeliveryResult(
                outcome=NotificationDeliveryOutcome.FAILURE,
                sanitized_error="Webhook provider temporarily rejected delivery.",
                error_code=f"webhook_http_{status}",
                retryable=True,
                retry_after_seconds=retry_after,
            )
        return NotificationDeliveryResult(
            outcome=NotificationDeliveryOutcome.FAILURE,
            sanitized_error="Webhook provider permanently rejected delivery.",
            error_code=f"webhook_http_{status}",
        )


def _send_webhook(
    url: str, payload: bytes, timeout_seconds: int
) -> tuple[int, dict[str, str]]:
    request = Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json", "User-Agent": "CloudOps/1.0"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            # Never return or persist the provider body.
            response.read(1024)
            return int(response.status), {
                key.casefold(): value for key, value in response.headers.items()
            }
    except HTTPError as exc:
        exc.read(1024)
        return int(exc.code), {
            key.casefold(): value for key, value in exc.headers.items()
        }


def _retry_after(headers: dict[str, str]) -> int | None:
    try:
        return min(3600, max(1, int(headers.get("retry-after", ""))))
    except ValueError:
        return None


def notification_provider_from_settings(settings: Settings) -> NotificationProvider:
    if settings.notification_provider == "smtp":
        return SMTPNotificationProvider(settings)
    if settings.notification_provider == "ses":
        raise RuntimeError("SES notification provider is not implemented for Version 1.")
    if settings.notification_provider == "slack":
        return WebhookNotificationProvider(
            key="slack",
            endpoint=settings.slack_webhook_url.get_secret_value(),
            channel=NotificationChannel.SLACK,
            allowed_host_suffixes=("hooks.slack.com",),
            timeout_seconds=settings.webhook_timeout_seconds,
            max_message_bytes=settings.notification_max_message_bytes,
        )
    if settings.notification_provider == "teams":
        return WebhookNotificationProvider(
            key="teams",
            endpoint=settings.teams_webhook_url.get_secret_value(),
            channel=NotificationChannel.TEAMS,
            allowed_host_suffixes=(
                "webhook.office.com",
                "logic.azure.com",
                "powerautomate.com",
            ),
            timeout_seconds=settings.webhook_timeout_seconds,
            max_message_bytes=settings.notification_max_message_bytes,
        )
    return MockNotificationProvider()
