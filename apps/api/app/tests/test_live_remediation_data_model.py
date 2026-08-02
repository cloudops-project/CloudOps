from __future__ import annotations

import uuid
from typing import cast

import pytest
from pydantic import ValidationError
from sqlalchemy import Table
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.base import utc_now
from app.exceptions.errors import ConflictError
from app.models.enums import RemediationExecutionMode
from app.schemas.aws_account import (
    AWSAccountResponse,
    AWSRemediationRoleConfiguration,
)
from app.services.remediation import RemediationService
from app.tests.test_risk import _finding, _tenant


def test_remediation_role_configuration_accepts_matching_role_arn() -> None:
    configuration = AWSRemediationRoleConfiguration(
        account_id="111122223333",
        remediation_role_arn=(
            "arn:aws:iam::111122223333:role/CloudOpsSandboxRemediationRole"
        ),
    )

    assert configuration.remediation_role_arn.endswith("CloudOpsSandboxRemediationRole")


@pytest.mark.parametrize(
    "role_arn",
    [
        "arn:aws:iam::111122223333:user/NotARole",
        "not-an-arn",
        "arn:aws:iam::444455556666:role/WrongAccount",
    ],
)
def test_remediation_role_configuration_rejects_unsafe_arns(role_arn: str) -> None:
    with pytest.raises(ValidationError):
        AWSRemediationRoleConfiguration(
            account_id="111122223333",
            remediation_role_arn=role_arn,
        )


def test_discovery_and_remediation_identity_fields_remain_distinct(db: Session) -> None:
    user, _organization, account = _tenant(db)
    account.role_arn = "arn:aws:iam::111122223333:role/CloudOpsReadOnlyRole"
    account.remediation_role_arn = (
        "arn:aws:iam::111122223333:role/CloudOpsSandboxRemediationRole"
    )
    account.remediation_external_id = "synthetic-remediation-trust-material"
    db.commit()
    db.refresh(account)

    assert account.role_arn != account.remediation_role_arn
    assert account.external_id != account.remediation_external_id
    assert account.sandbox_approved is False
    assert account.sandbox_approved_at is None
    assert account.sandbox_approved_by_user_id is None
    assert account.external_id not in repr(account)
    assert account.remediation_external_id not in repr(account)

    response = AWSAccountResponse.model_validate(account).model_dump()
    assert "external_id" not in response
    assert "remediation_external_id" not in response
    assert "remediation_role_arn" not in response
    assert response["created_by_user_id"] == user.id


def test_complete_sandbox_approval_is_valid(db: Session) -> None:
    user, _organization, account = _tenant(db)
    account.sandbox_approved = True
    account.sandbox_approved_at = utc_now()
    account.sandbox_approved_by_user_id = user.id

    db.commit()
    db.refresh(account)

    assert account.sandbox_approved is True
    assert account.sandbox_approved_by_user_id == user.id


@pytest.mark.parametrize(
    ("set_timestamp", "set_actor"),
    [(False, True), (True, False)],
)
def test_incomplete_sandbox_approval_is_rejected(
    db: Session, set_timestamp: bool, set_actor: bool
) -> None:
    user, _organization, account = _tenant(db)
    account.sandbox_approved = True
    account.sandbox_approved_at = utc_now() if set_timestamp else None
    account.sandbox_approved_by_user_id = user.id if set_actor else None

    with pytest.raises(IntegrityError):
        db.commit()


def test_revoked_sandbox_approval_cannot_retain_stale_metadata(db: Session) -> None:
    user, _organization, account = _tenant(db)
    account.sandbox_approved = False
    account.sandbox_approved_at = utc_now()
    account.sandbox_approved_by_user_id = user.id

    with pytest.raises(IntegrityError):
        db.commit()


def test_sandbox_approver_uses_tenant_membership_foreign_key(db: Session) -> None:
    _owner, _organization, account = _tenant(db)
    table = cast(Table, account.__table__)
    constraint = next(
        item
        for item in table.foreign_key_constraints
        if item.name == "fk_aws_account_sandbox_approver_membership"
    )

    assert [element.parent.name for element in constraint.elements] == [
        "organization_id",
        "sandbox_approved_by_user_id",
    ]
    assert [element.target_fullname for element in constraint.elements] == [
        "organization_members.organization_id",
        "organization_members.user_id",
    ]
    assert constraint.ondelete == "RESTRICT"


def test_existing_mock_request_and_new_evidence_round_trip(db: Session) -> None:
    user, organization, account = _tenant(db)
    finding, _asset = _finding(db, organization, account, user)
    db.commit()
    request = RemediationService(db).propose_for_finding(
        organization.id, finding.id, user
    )
    request.executor_key = "mock"
    request.target_region = "us-east-1"
    request.target_resource_arn = "arn:aws:s3:::synthetic-fixture-bucket"
    request.precondition_evidence_json = {"version": 1, "matches": True}
    request.verification_result_json = {"verified": True}
    request.aws_request_ids_json = {"revalidate": "synthetic-request-id"}
    db.commit()
    db.refresh(request)

    assert request.execution_mode == RemediationExecutionMode.MOCK_AUTOMATION
    assert request.precondition_evidence_json == {"version": 1, "matches": True}
    assert request.verification_result_json == {"verified": True}
    assert request.aws_request_ids_json == {"revalidate": "synthetic-request-id"}
    assert request.before_state_json is None


def test_json_defaults_are_independent_between_requests(db: Session) -> None:
    user, organization, account = _tenant(db)
    first_finding, _asset = _finding(db, organization, account, user)
    db.commit()
    first = RemediationService(db).propose_for_finding(
        organization.id, first_finding.id, user
    )
    first.precondition_evidence_json["first"] = True

    second_user, second_organization, second_account = _tenant(db)
    second_finding, _second_asset = _finding(
        db, second_organization, second_account, second_user
    )
    db.commit()
    second = RemediationService(db).propose_for_finding(
        second_organization.id, second_finding.id, second_user
    )

    assert first.precondition_evidence_json is not second.precondition_evidence_json
    assert second.precondition_evidence_json == {}


@pytest.mark.parametrize(
    "field,value",
    [
        ("precondition_evidence_json", {"aws_secret_access_key": "synthetic"}),
        ("verification_result_json", {"nested": {"session_token": "synthetic"}}),
        ("aws_request_ids_json", {"credentials": ["synthetic"]}),
    ],
)
def test_credential_shaped_execution_evidence_is_rejected(
    db: Session, field: str, value: dict[str, object]
) -> None:
    user, organization, account = _tenant(db)
    finding, _asset = _finding(db, organization, account, user)
    db.commit()
    request = RemediationService(db).propose_for_finding(
        organization.id, finding.id, user
    )

    with pytest.raises(ValueError, match="credential-shaped"):
        setattr(request, field, value)


def test_live_aws_storage_value_does_not_bypass_live_feature_gate(db: Session) -> None:
    user, organization, account = _tenant(db)
    finding, _asset = _finding(db, organization, account, user)
    db.commit()
    request = RemediationService(db).propose_for_finding(
        organization.id, finding.id, user
    )
    request.execution_mode = RemediationExecutionMode.LIVE_AWS
    db.commit()
    service = RemediationService(db)
    service.approve(organization.id, request.id, user)
    db.commit()

    assert request.execution_mode == RemediationExecutionMode.LIVE_AWS
    assert request.dry_run is True
    with pytest.raises(ConflictError, match="Live AWS remediation is disabled"):
        service.execute(
            organization.id,
            request.id,
            execution_lease_id=uuid.uuid4(),
        )
