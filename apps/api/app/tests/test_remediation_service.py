from __future__ import annotations

import hashlib
import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.base import utc_now
from app.exceptions.errors import ConflictError, NotFoundError
from app.models import Asset, AWSAccount, Organization, RemediationRequest, User
from app.models.enums import FindingStatus, RemediationExecutionMode, RemediationStatus
from app.services.ai_safety import canonical_json
from app.services.remediation import RemediationService
from app.services.remediation_executor import (
    MockRemediationExecutor,
    RemediationExecutionContext,
    RemediationExecutionOutcome,
    RemediationExecutionResult,
)
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


def test_unallowlisted_rule_is_manual_and_cannot_execute(db: Session) -> None:
    user, organization, account = _tenant(db)
    finding, _asset = _finding(
        db,
        organization,
        account,
        user,
        rule_key="SYNTHETIC_RULE_WITHOUT_REMEDIATION",
    )
    db.commit()

    request = RemediationService(db).propose_for_finding(
        organization.id,
        finding.id,
        user,
    )
    db.commit()

    assert request.action_key == "manual.review"
    assert request.execution_mode == RemediationExecutionMode.MANUAL
    assert request.automation_eligible is False


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


def test_approval_rejects_changed_preview_snapshot(db: Session) -> None:
    request, organization, _user = _proposed_request(db)
    approver = _approver(db, f"approver-{uuid.uuid4().hex}")
    request.request_snapshot_json = {
        **request.request_snapshot_json,
        "dry_run": False,
    }
    db.commit()

    with pytest.raises(ConflictError, match="preview changed"):
        RemediationService(db).approve(organization.id, request.id, approver)


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


def _execute(
    service: RemediationService,
    organization: Organization,
    request: RemediationRequest,
) -> RemediationRequest:
    return service.execute(
        organization.id,
        request.id,
        execution_lease_id=uuid.uuid4(),
    )


class _SuccessfulLiveExecutor:
    key = "aws"

    def __init__(self) -> None:
        self.context: RemediationExecutionContext | None = None

    def execute(
        self,
        *,
        action_key: str,
        finding_id: uuid.UUID,
        snapshot_hash: str,
        dry_run: bool,
        context: RemediationExecutionContext | None = None,
    ) -> RemediationExecutionResult:
        del action_key, finding_id, snapshot_hash, dry_run
        self.context = context
        return RemediationExecutionResult(
            outcome=RemediationExecutionOutcome.SUCCESS,
            before_state={"legacy": "before"},
            after_state={"verified": True},
            precondition_evidence={"matched": True},
            verification_result={"verified": True},
            rollback_state={"exact": "original"},
            aws_request_ids={"put_public_access_block": "synthetic-request-id"},
        )


def _live_request(
    db: Session,
) -> tuple[RemediationRequest, Organization, _SuccessfulLiveExecutor]:
    request, organization, requester = _proposed_request(db)
    finding = RemediationService(db)._get_finding(organization.id, request.finding_id)
    account = db.scalar(
        select(AWSAccount).where(
            AWSAccount.id == request.aws_account_id,
            AWSAccount.organization_id == organization.id,
        )
    )
    asset = db.scalar(
        select(Asset).where(
            Asset.id == finding.asset_id,
            Asset.organization_id == organization.id,
        )
    )
    assert account is not None
    assert asset is not None
    asset.arn = (
        f"arn:aws:ec2:{asset.region}:{account.account_id}:"
        f"security-group/{asset.resource_id}"
    )
    account.remediation_role_arn = (
        f"arn:aws:iam::{account.account_id}:role/CloudOpsRemediationRole"
    )
    account.remediation_external_id = "synthetic-remediation-external-id"
    account.sandbox_approved = True
    account.sandbox_approved_at = utc_now()
    account.sandbox_approved_by_user_id = requester.id
    request.execution_mode = RemediationExecutionMode.LIVE_AWS
    request.executor_key = "aws"
    request.dry_run = False
    request.target_region = asset.region
    request.target_resource_arn = asset.arn
    request.request_snapshot_json = {
        **request.request_snapshot_json,
        "execution_mode": RemediationExecutionMode.LIVE_AWS.value,
        "executor_key": "aws",
        "dry_run": False,
        "target_region": asset.region,
        "target_resource_arn": asset.arn,
        "asset_evidence_hash": hashlib.sha256(
            canonical_json(asset.metadata_json).encode()
        ).hexdigest(),
    }
    request.request_snapshot_hash = hashlib.sha256(
        canonical_json(request.request_snapshot_json).encode()
    ).hexdigest()
    db.commit()
    approver = _approver(db, f"live-approver-{uuid.uuid4().hex}")
    db.commit()
    RemediationService(db).approve(organization.id, request.id, approver)
    db.commit()
    return request, organization, _SuccessfulLiveExecutor()


def _live_settings(**updates: object) -> Settings:
    return get_settings().model_copy(
        update={
            "remediation_execution_enabled": True,
            "remediation_live_aws_enabled": True,
            "remediation_emergency_stop": False,
            **updates,
        }
    )


def test_execute_without_approval_is_rejected(db: Session) -> None:
    request, organization, _user = _proposed_request(db)
    db.commit()

    with pytest.raises(ConflictError):
        _execute(RemediationService(db), organization, request)


def test_mock_execution_success_transitions_to_succeeded(db: Session) -> None:
    request, organization = _approved_request(db)
    executor = MockRemediationExecutor(fault_mode="success")
    service = RemediationService(db, executor=executor)

    succeeded = _execute(service, organization, request)
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

    first = _execute(service, organization, request)
    db.commit()
    assert first.status == RemediationStatus.APPROVED
    assert first.attempt_count == 1

    second = _execute(service, organization, request)
    db.commit()
    assert second.status == RemediationStatus.APPROVED
    assert second.attempt_count == 2


def test_third_failure_transitions_to_failed(db: Session) -> None:
    request, organization = _approved_request(db)
    executor = MockRemediationExecutor(fault_mode="always_fail")
    service = RemediationService(db, executor=executor)

    _execute(service, organization, request)
    db.commit()
    _execute(service, organization, request)
    db.commit()
    third = _execute(service, organization, request)
    db.commit()

    assert third.status == RemediationStatus.FAILED
    assert third.attempt_count == 3
    assert third.failed_at is not None
    assert third.failure_reason is not None


def test_duplicate_execution_after_success_is_rejected(db: Session) -> None:
    request, organization = _approved_request(db)
    service = RemediationService(db, executor=MockRemediationExecutor(fault_mode="success"))
    _execute(service, organization, request)
    db.commit()

    with pytest.raises(ConflictError):
        _execute(service, organization, request)


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
        _execute(RemediationService(db), organization, request)


def test_approved_snapshot_is_immutable_and_bound_to_execution(db: Session) -> None:
    request, organization = _approved_request(db)
    approved_hash = request.approved_snapshot_hash
    assert approved_hash == request.request_snapshot_hash

    request.request_snapshot_json = {
        **request.request_snapshot_json,
        "action_key": "ec2.unrestricted-user-input",
    }
    db.commit()

    with pytest.raises(ConflictError, match="snapshot"):
        _execute(RemediationService(db), organization, request)


def test_changed_finding_evidence_fails_execution_precondition(db: Session) -> None:
    request, organization = _approved_request(db)
    finding = RemediationService(db)._get_finding(organization.id, request.finding_id)
    finding.evidence_json = {"changed_after_approval": True}
    db.commit()

    with pytest.raises(ConflictError, match="finding changed"):
        _execute(RemediationService(db), organization, request)


def test_execution_kill_switch_and_live_flag_preserve_mock_execution(db: Session) -> None:
    request, organization = _approved_request(db)
    base = get_settings()

    disabled = base.model_copy(update={"remediation_execution_enabled": False})
    with pytest.raises(ConflictError, match="kill switch"):
        _execute(RemediationService(db, settings=disabled), organization, request)

    live = base.model_copy(
        update={
            "remediation_execution_enabled": True,
            "remediation_live_aws_enabled": True,
        }
    )
    result = _execute(RemediationService(db, settings=live), organization, request)
    assert result.status == RemediationStatus.SUCCEEDED


def test_live_execution_is_fail_closed_by_default(db: Session) -> None:
    request, organization, executor = _live_request(db)

    with pytest.raises(ConflictError, match="emergency stop"):
        _execute(
            RemediationService(
                db,
                settings=_live_settings(remediation_emergency_stop=True),
                live_executor_factory=lambda _settings: executor,
            ),
            organization,
            request,
        )
    assert executor.context is None


def test_live_execution_requires_separate_role_trust(db: Session) -> None:
    request, organization, executor = _live_request(db)
    account = db.scalar(
        select(AWSAccount).where(AWSAccount.id == request.aws_account_id)
    )
    assert account is not None
    account.remediation_external_id = None
    db.commit()

    with pytest.raises(ConflictError, match="separate remediation role"):
        _execute(
            RemediationService(
                db,
                settings=_live_settings(),
                live_executor_factory=lambda _settings: executor,
            ),
            organization,
            request,
        )
    assert executor.context is None


def test_live_execution_rejects_stale_worker_lease(db: Session) -> None:
    request, organization, executor = _live_request(db)
    request.execution_lease_id = uuid.uuid4()
    db.commit()

    with pytest.raises(ConflictError, match="another execution lease"):
        _execute(
            RemediationService(
                db,
                settings=_live_settings(),
                live_executor_factory=lambda _settings: executor,
            ),
            organization,
            request,
        )
    assert executor.context is None


def test_live_execution_persists_sanitized_evidence(db: Session) -> None:
    request, organization, executor = _live_request(db)
    result = _execute(
        RemediationService(
            db,
            settings=_live_settings(),
            live_executor_factory=lambda _settings: executor,
        ),
        organization,
        request,
    )
    db.commit()

    assert result.status == RemediationStatus.SUCCEEDED
    assert executor.context is not None
    assert executor.context.account.organization_id == organization.id
    assert result.before_state_json == {"exact": "original"}
    assert result.precondition_evidence_json == {"matched": True}
    assert result.verification_result_json == {"verified": True}
    assert result.aws_request_ids_json == {
        "put_public_access_block": "synthetic-request-id"
    }


def test_execution_records_worker_lease_and_remains_dry_run(db: Session) -> None:
    request, organization = _approved_request(db)
    lease_id = uuid.uuid4()

    result = RemediationService(db).execute(
        organization.id,
        request.id,
        execution_lease_id=lease_id,
    )
    db.commit()

    assert result.execution_lease_id == lease_id
    assert result.dry_run is True
    assert result.before_state_json is not None
    assert result.before_state_json["dry_run"] is True
