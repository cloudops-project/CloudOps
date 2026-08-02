from __future__ import annotations

import uuid
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from app.models import Asset, AWSAccount, Finding, RemediationRequest


class RemediationExecutionOutcome(StrEnum):
    SUCCESS = "success"
    FAILURE = "failure"


@dataclass(frozen=True)
class RemediationExecutionResult:
    outcome: RemediationExecutionOutcome
    before_state: dict[str, object]
    after_state: dict[str, object] | None = None
    sanitized_error: str | None = None
    precondition_evidence: dict[str, object] | None = None
    verification_result: dict[str, object] | None = None
    rollback_state: dict[str, object] | None = None
    aws_request_ids: dict[str, object] | None = None


@dataclass(frozen=True)
class RemediationExecutionContext:
    account: AWSAccount
    asset: Asset
    finding: Finding
    request: RemediationRequest


class RemediationExecutor(Protocol):
    key: str

    def execute(
        self,
        *,
        action_key: str,
        finding_id: uuid.UUID,
        snapshot_hash: str,
        dry_run: bool,
        context: RemediationExecutionContext | None = None,
    ) -> RemediationExecutionResult: ...


class MockRemediationExecutor:
    """Deterministic, offline remediation executor. The only executor
    available in Stage 10; performs no AWS calls, no sleeps, and no
    background work, and never mutates a real customer resource. Real
    executors are intentionally out of scope for Version 1 and must
    implement the same Protocol."""

    key = "mock"

    def __init__(self, fault_mode: str = "success") -> None:
        self.fault_mode = fault_mode
        self.invocations = 0

    def execute(
        self,
        *,
        action_key: str,
        finding_id: uuid.UUID,
        snapshot_hash: str,
        dry_run: bool,
        context: RemediationExecutionContext | None = None,
    ) -> RemediationExecutionResult:
        del context
        self.invocations += 1
        before_state = {
            "simulated": True,
            "action_key": action_key,
            "finding_id": str(finding_id),
            "snapshot_hash": snapshot_hash,
            "dry_run": dry_run,
            "attempt": self.invocations,
        }
        if self.fault_mode == "success":
            return RemediationExecutionResult(
                outcome=RemediationExecutionOutcome.SUCCESS,
                before_state=before_state,
                after_state={
                    "simulated_remediated": True,
                    "action_key": action_key,
                    "dry_run": dry_run,
                },
            )
        if self.fault_mode == "always_fail":
            return RemediationExecutionResult(
                outcome=RemediationExecutionOutcome.FAILURE,
                before_state=before_state,
                sanitized_error="Mock executor was configured to fail execution.",
            )
        if self.fault_mode == "fail_then_succeed" and self.invocations == 1:
            return RemediationExecutionResult(
                outcome=RemediationExecutionOutcome.FAILURE,
                before_state=before_state,
                sanitized_error="Mock executor transient failure.",
            )
        return RemediationExecutionResult(
            outcome=RemediationExecutionOutcome.SUCCESS,
            before_state=before_state,
            after_state={
                "simulated_remediated": True,
                "action_key": action_key,
                "dry_run": dry_run,
            },
        )
