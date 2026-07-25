from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.base import utc_now
from app.exceptions.errors import ConflictError, NotFoundError
from app.models import Organization, RemediationRequest, User
from app.models.enums import FindingStatus, RemediationExecutionMode, RemediationStatus
from app.services.remediation import RemediationService
from app.services.remediation_executor import MockRemediationExecutor
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
# Proposal generation
# ---------------------------------------------------------------------------


def test_propose_generates_deterministic_proposal_from_rule(db: Session) -> None:
    user, organization, account = _tenant(db)
    finding, _asset = _finding(db, organization, account, user, rule_key="EC2_SG_SSH_OPEN_TO_WORLD")
    db.commit()

    request = RemediationService(db).propose_for_finding(organization.id, finding.id, user)
    db.commit()

    assert request.status == RemediationStatus.PENDING_APPROVAL
    assert request.finding_id == finding.id
    assert request.rule_key == "EC2_SG_SSH_OPEN_TO_WORLD"
    assert request.execution_mode == RemediationExecutionMode.MOCK_AUTOMATION
    assert request.automation_eligible is True
    assert request.title
    assert request.summary
    assert len(request.remediation_steps_json) >= 1
    assert len(request.verification_steps_json) >= 1
    assert len(request.rollback_steps_json) >= 1


def test_propose_is_idempotent_for_an_active_request(db: Session) -> None:
    user, organization, account = _tenant(db)
    finding, _asset = _finding(db, organization, account, user)
    db.commit()

    service = RemediationService(db)
    first = service.propose_for_finding(organization.id, finding.id, user)
    db.commit()
    second = service.propose_for_finding(organization.id, finding.id, user)
    db.commit()

    assert first.id == second.id
    rows = db.scalars(
        select(RemediationRequest).where(RemediationRequest.finding_id == finding.id)
    ).all()
    assert len(rows) == 1


def test_propose_rejects_non_open_finding(db: Session) -> None:
    user, organization, account = _tenant(db)
    finding, _asset = _finding(db, organization, account, user)
    finding.status = FindingStatus.RESOLVED
    finding.resolved_at = utc_now()
    db.flush()
    db.commit()

    with pytest.raises(ConflictError):
        RemediationService(db).propose_for_finding(organization.id, finding.id, user)


def test_propose_unknown_finding_raises_not_found(db: Session) -> None:
    user, organization, _account = _tenant(db)
    db.commit()

    with pytest.raises(NotFoundError):
        RemediationService(db).propose_for_finding(organization.id, uuid.uuid4(), user)


def test_propose_is_tenant_isolated(db: Session) -> None:
    user_a, org_a, account_a = _tenant(db)
    user_b, org_b, _account_b = _tenant(db)
    finding_a, _asset_a = _finding(db, org_a, account_a, user_a)
    db.commit()

    with pytest.raises(NotFoundError):
        RemediationService(db).propose_for_finding(org_b.id, finding_a.id, user_b)


# ---------------------------------------------------------------------------
# Approval / rejection / cancellation
# ---------------------------------------------------------------------------


def _proposed_request(db: Session) -> tuple[RemediationRequest, Organization, User]:
    user, organization, account = _tenant(db)
    finding, _asset = _finding(db, organization, account, user)
    db.commit()
    request = RemediationService(db).propose_for_finding(organization.id, finding.id, user)
    db.commit()
    return request, organization, user


def test_approval_transitions_pending_to_approved(db: Session) -> None:
    request, organization, _user = _proposed_request(db)
    approver = _approver(db, f"approver-{uuid.uuid4().hex}")
    db.commit()

    approved = RemediationService(db).approve(organization.id, request.id, approver)
    db.commit()

    assert approved.status == RemediationStatus.APPROVED
    assert approved.approved_at is not None
    assert approved.approved_by_user_id == approver.id


def test_re_approving_is_idempotent(db: Session) -> None:
    request, organization, _user = _proposed_request(db)
    approver = _approver(db, f"approver-{uuid.uuid4().hex}")
    db.commit()

    service = RemediationService(db)
    first = service.approve(organization.id, request.id, approver)
    db.commit()
    second = service.approve(organization.id, request.id, approver)
    db.commit()

    assert first.approved_at == second.approved_at


def test_approval_from_invalid_state_is_rejected(db: Session) -> None:
    request, organization, _user = _proposed_request(db)
    approver = _approver(db, f"approver-{uuid.uuid4().hex}")
    db.commit()
    service = RemediationService(db)
    service.reject(organization.id, request.id, approver, "not needed")
    db.commit()

    with pytest.raises(ConflictError):
        service.approve(organization.id, request.id, approver)


def test_reject_records_reason_and_actor(db: Session) -> None:
    request, organization, _user = _proposed_request(db)
    rejector = _approver(db, f"rejector-{uuid.uuid4().hex}")
    db.commit()

    rejected = RemediationService(db).reject(
        organization.id, request.id, rejector, "False positive after manual review"
    )
    db.commit()

    assert rejected.status == RemediationStatus.REJECTED
    assert rejected.rejected_at is not None
    assert rejected.rejected_by_user_id == rejector.id
    assert rejected.rejection_reason == "False positive after manual review"


def test_cancel_from_pending_approval(db: Session) -> None:
    request, organization, user = _proposed_request(db)
    db.commit()

    cancelled = RemediationService(db).cancel(organization.id, request.id, user)
    db.commit()

    assert cancelled.status == RemediationStatus.CANCELLED
    assert cancelled.cancelled_at is not None


def test_cancel_from_approved(db: Session) -> None:
    request, organization, user = _proposed_request(db)
    approver = _approver(db, f"approver-{uuid.uuid4().hex}")
    db.commit()
    service = RemediationService(db)
    service.approve(organization.id, request.id, approver)
    db.commit()

    cancelled = service.cancel(organization.id, request.id, user)
    db.commit()

    assert cancelled.status == RemediationStatus.CANCELLED


def test_cancel_from_terminal_state_is_rejected(db: Session) -> None:
    request, organization, user = _proposed_request(db)
    db.commit()
    service = RemediationService(db)
    service.reject(organization.id, request.id, user, "no longer relevant")
    db.commit()

    with pytest.raises(ConflictError):
        service.cancel(organization.id, request.id, user)


# ---------------------------------------------------------------------------
# Execution
# ---------------------------------------------------------------------------


def _approved_request(db: Session) -> tuple[RemediationRequest, Organization]:
    request, organization, _user = _proposed_request(db)
    approver = _approver(db, f"approver-{uuid.uuid4().hex}")
    db.commit()
    RemediationService(db).approve(organization.id, request.id, approver)
    db.commit()
    return request, organization


def test_execute_without_approval_is_rejected(db: Session) -> None:
    request, organization, _user = _proposed_request(db)
    db.commit()

    with pytest.raises(ConflictError):
        RemediationService(db).execute(organization.id, request.id)


def test_mock_execution_success_transitions_to_succeeded(db: Session) -> None:
    request, organization = _approved_request(db)
    executor = MockRemediationExecutor(fault_mode="success")
    service = RemediationService(db, executor=executor)

    succeeded = service.execute(organization.id, request.id)
    db.commit()

    assert succeeded.status == RemediationStatus.SUCCEEDED
    assert succeeded.executed_at is not None
    assert succeeded.attempt_count == 1
    assert succeeded.before_state_json is not None
    assert succeeded.after_state_json is not None
    assert executor.invocations == 1


def test_first_and_second_failure_keep_status_approved(db: Session) -> None:
    request, organization = _approved_request(db)
    executor = MockRemediationExecutor(fault_mode="always_fail")
    service = RemediationService(db, executor=executor)

    first = service.execute(organization.id, request.id)
    db.commit()
    assert first.status == RemediationStatus.APPROVED
    assert first.attempt_count == 1

    second = service.execute(organization.id, request.id)
    db.commit()
    assert second.status == RemediationStatus.APPROVED
    assert second.attempt_count == 2


def test_third_failure_transitions_to_failed(db: Session) -> None:
    request, organization = _approved_request(db)
    executor = MockRemediationExecutor(fault_mode="always_fail")
    service = RemediationService(db, executor=executor)

    service.execute(organization.id, request.id)
    db.commit()
    service.execute(organization.id, request.id)
    db.commit()
    third = service.execute(organization.id, request.id)
    db.commit()

    assert third.status == RemediationStatus.FAILED
    assert third.attempt_count == 3
    assert third.failed_at is not None
    assert third.failure_reason is not None


def test_duplicate_execution_after_success_is_rejected(db: Session) -> None:
    request, organization = _approved_request(db)
    service = RemediationService(db, executor=MockRemediationExecutor(fault_mode="success"))
    service.execute(organization.id, request.id)
    db.commit()

    with pytest.raises(ConflictError):
        service.execute(organization.id, request.id)


def test_execute_non_mock_execution_mode_is_rejected(db: Session) -> None:
    user, organization, account = _tenant(db)
    finding, _asset = _finding(db, organization, account, user)
    db.commit()
    request = RemediationService(db).propose_for_finding(organization.id, finding.id, user)
    request.execution_mode = RemediationExecutionMode.MANUAL
    db.commit()
    approver = _approver(db, f"approver-{uuid.uuid4().hex}")
    db.commit()
    RemediationService(db).approve(organization.id, request.id, approver)
    db.commit()

    with pytest.raises(ConflictError):
        RemediationService(db).execute(organization.id, request.id)
