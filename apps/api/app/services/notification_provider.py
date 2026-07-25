from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from app.models.enums import NotificationChannel


class NotificationDeliveryOutcome(StrEnum):
    SUCCESS = "success"
    FAILURE = "failure"


@dataclass(frozen=True)
class NotificationDeliveryResult:
    outcome: NotificationDeliveryOutcome
    sanitized_error: str | None = None


class NotificationProvider(Protocol):
    key: str

    def deliver(
        self,
        *,
        channel: NotificationChannel,
        destination_reference: str | None,
        template_key: str,
        context: dict[str, object],
    ) -> NotificationDeliveryResult: ...


class MockNotificationProvider:
    """Deterministic, offline notification provider. The only provider
    available in Stage 9; performs no network I/O, no sleeps, and no
    background work. Real providers (email, Slack, webhook, SNS) are
    intentionally out of scope and must implement the same Protocol."""

    key = "mock"

    def __init__(self, fault_mode: str = "success") -> None:
        self.fault_mode = fault_mode
        self.invocations = 0

    def deliver(
        self,
        *,
        channel: NotificationChannel,
        destination_reference: str | None,
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
