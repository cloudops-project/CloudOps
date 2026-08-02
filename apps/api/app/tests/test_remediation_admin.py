from __future__ import annotations

import hashlib
import uuid
from pathlib import Path
from typing import cast

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.exceptions.errors import ConflictError
from app.models import (
    Asset,
    AuditEvent,
    AWSAccount,
    Finding,
    OrganizationMembership,
    PlatformJob,
    RemediationRequest,
    User,
)
from app.models.enums import (
    AWSAccountStatus,
    MembershipStatus,
    OrganizationRole,
    RemediationExecutionMode,
)
from app.security.tokens import create_access_token
from app.services.ai_safety import canonical_json
from app.services.remediation import RemediationService
from app.services.remediation_admin import RemediationAdminService
from app.tests.test_risk import _finding, _tenant


def _headers(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user.id, get_settings())}"}


def _account(
    db: Session, role: OrganizationRole = OrganizationRole.OWNER
) -> tuple[User, AWSAccount]:
    user, _organization, account = _tenant(db, role)
    account.connection_status = AWSAccountStatus.CONNECTED
    account.status = AWSAccountStatus.CONNECTED
    db.commit()
    return user, account


def _configure(
    client: TestClient, user: User, account: AWSAccount, *, suffix: str = "RemediationRole"
) -> dict[str, object]:
    response = client.put(
        f"/api/v1/aws/accounts/{account.id}/remediation-trust",
        headers=_headers(user),
        json={
            "remediation_role_arn": f"arn:aws:iam::{account.account_id}:role/{suffix}",
        },
    )
    assert response.status_code == 200, response.text
    return cast(dict[str, object], response.json())


def _approve(
    client: TestClient,
    user: User,
    account: AWSAccount,
    reason: str = "Lab approved",
) -> None:
    response = client.post(
        f"/api/v1/aws/accounts/{account.id}/sandbox-approval",
        headers=_headers(user),
        json={"reason": reason},
    )
    assert response.status_code == 200, response.text


def _approved_request(
    db: Session,
) -> tuple[User, AWSAccount, RemediationRequest]:
    user, organization, account = _tenant(db)
    account.connection_status = AWSAccountStatus.CONNECTED
    account.status = AWSAccountStatus.CONNECTED
    account.remediation_role_arn = (
        f"arn:aws:iam::{account.account_id}:role/CloudOpsSandboxRemediationRole"
    )
    account.remediation_external_id = "cloudops-remediation-synthetic-only"
    account.sandbox_approved = True
    from app.services.common import now_utc

    account.sandbox_approved_at = now_utc()
    account.sandbox_approved_by_user_id = user.id
    finding, asset = _finding(db, organization, account, user)
    asset.arn = (
        f"arn:aws:ec2:{asset.region}:{account.account_id}:security-group/{asset.resource_id}"
    )
    asset.metadata_json = {
        "vpc_id": "vpc-synthetic",
        "security_group_rules": [
            {
                "GroupId": asset.resource_id,
                "SecurityGroupRuleId": "sgr-synthetic",
                "IsEgress": False,
                "IpProtocol": "tcp",
                "FromPort": 22,
                "ToPort": 22,
                "CidrIpv4": "0.0.0.0/0",
            }
        ],
    }
    db.commit()
    service = RemediationService(db)
    request = service.propose_for_finding(organization.id, finding.id, user)
    db.commit()
    service.approve(organization.id, request.id, user)
    db.commit()
    return user, account, request


def test_owner_configures_trust_and_external_id_is_one_time_only(
    client: TestClient, db: Session
) -> None:
    owner, account = _account(db)
    discovery_role = account.role_arn
    discovery_external_id = account.external_id

    configured = _configure(client, owner, account)
    external_id = configured["remediation_external_id"]
    assert isinstance(external_id, str)
    assert external_id.startswith("cloudops-remediation-")
    assert configured["remediation_trust_configured"] is True
    masked_role = configured["remediation_role_arn_masked"]
    assert isinstance(masked_role, str)
    assert masked_role.endswith("role/RemediationRole")
    assert account.account_id not in masked_role

    repeated = _configure(client, owner, account)
    assert repeated["remediation_external_id"] is None
    status = client.get(
        f"/api/v1/aws/accounts/{account.id}/remediation-administration",
        headers=_headers(owner),
    )
    assert status.status_code == 200
    assert "remediation_external_id" not in status.json()

    listed = client.get(
        "/api/v1/aws/accounts",
        params={"organization_id": str(account.organization_id)},
        headers=_headers(owner),
    )
    assert listed.status_code == 200
    assert "remediation_external_id" not in listed.text
    assert external_id not in listed.text

    db.expire_all()
    stored = db.get(AWSAccount, account.id)
    assert stored is not None
    assert stored.role_arn == discovery_role
    assert stored.external_id == discovery_external_id
    assert stored.remediation_external_id == external_id
    assert external_id not in repr(stored)
    audits = db.scalars(
        select(AuditEvent).where(
            AuditEvent.event_type == "aws.account.remediation_trust_configured"
        )
    ).all()
    assert len(audits) == 1
    assert external_id not in canonical_json(audits[0].metadata_json)


@pytest.mark.parametrize(
    ("role_arn", "code"),
    [
        ("not-an-iam-role-arn-value", "remediation_role_invalid"),
        ("arn:aws:iam::123456789012:user/NotARole", "remediation_role_invalid"),
        ("arn:aws:iam::999999999999:role/WrongAccount", "remediation_role_account_mismatch"),
    ],
)
def test_remediation_role_validation_has_stable_errors(
    client: TestClient, db: Session, role_arn: str, code: str
) -> None:
    owner, account = _account(db)
    response = client.put(
        f"/api/v1/aws/accounts/{account.id}/remediation-trust",
        headers=_headers(owner),
        json={"remediation_role_arn": role_arn},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == code


@pytest.mark.parametrize(
    "role",
    [
        OrganizationRole.ADMIN,
        OrganizationRole.SECURITY_ANALYST,
        OrganizationRole.CLOUD_ENGINEER,
        OrganizationRole.VIEWER,
    ],
)
def test_only_owner_can_administer_remediation_trust(
    client: TestClient, db: Session, role: OrganizationRole
) -> None:
    actor, account = _account(db, role)
    response = client.put(
        f"/api/v1/aws/accounts/{account.id}/remediation-trust",
        headers=_headers(actor),
        json={
            "remediation_role_arn": f"arn:aws:iam::{account.account_id}:role/RemediationRole"
        },
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "remediation_admin_forbidden"


def test_unauthenticated_and_cross_tenant_administration_do_not_disclose_account(
    client: TestClient, db: Session
) -> None:
    _owner, account = _account(db)
    other_owner, _other_organization, _other_account = _tenant(db)
    db.commit()
    path = f"/api/v1/aws/accounts/{account.id}/remediation-administration"
    assert client.get(path).status_code == 401
    response = client.get(path, headers=_headers(other_owner))
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "aws_account_not_found"


def test_approval_rotation_revocation_and_clear_are_atomic_and_audited(
    client: TestClient, db: Session
) -> None:
    owner, account = _account(db)
    initial = _configure(client, owner, account)
    first_external_id = initial["remediation_external_id"]
    _approve(client, owner, account, "Synthetic sandbox account only")
    db.expire_all()
    stored = db.get(AWSAccount, account.id)
    assert stored is not None
    assert stored.sandbox_approved is True
    assert stored.sandbox_approved_at is not None
    assert stored.sandbox_approved_by_user_id == owner.id

    duplicate = client.post(
        f"/api/v1/aws/accounts/{account.id}/sandbox-approval",
        headers=_headers(owner),
        json={"reason": "Repeated approval"},
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "sandbox_already_approved"

    changed = _configure(client, owner, account, suffix="ReplacementRemediationRole")
    assert changed["sandbox_approved"] is False
    assert changed["remediation_external_id"] != first_external_id
    _approve(client, owner, account)

    rotated = client.post(
        f"/api/v1/aws/accounts/{account.id}/remediation-trust/rotate",
        headers=_headers(owner),
        json={"reason": "Scheduled trust rotation"},
    )
    assert rotated.status_code == 200
    assert rotated.json()["remediation_external_id"] != first_external_id
    assert rotated.json()["sandbox_approved"] is False

    _approve(client, owner, account)
    revoked = client.request(
        "DELETE",
        f"/api/v1/aws/accounts/{account.id}/sandbox-approval",
        headers=_headers(owner),
        json={"reason": "Exercise completed"},
    )
    assert revoked.status_code == 200
    assert revoked.json()["sandbox_approved"] is False
    assert revoked.json()["sandbox_approved_at"] is None
    assert revoked.json()["sandbox_approved_by_user_id"] is None

    repeated_revoke = client.request(
        "DELETE",
        f"/api/v1/aws/accounts/{account.id}/sandbox-approval",
        headers=_headers(owner),
        json={"reason": "Repeated revocation"},
    )
    assert repeated_revoke.status_code == 409
    assert repeated_revoke.json()["error"]["code"] == "sandbox_not_approved"

    cleared = client.request(
        "DELETE",
        f"/api/v1/aws/accounts/{account.id}/remediation-trust",
        headers=_headers(owner),
        json={"reason": "Remove sandbox trust"},
    )
    assert cleared.status_code == 200
    assert cleared.json()["remediation_trust_configured"] is False
    db.expire_all()
    stored = db.get(AWSAccount, account.id)
    assert stored is not None
    assert stored.remediation_role_arn is None
    assert stored.remediation_external_id is None
    assert stored.sandbox_approved is False
    reasons = [
        event.metadata_json.get("reason")
        for event in db.scalars(
            select(AuditEvent).where(AuditEvent.resource_id == account.id)
        ).all()
    ]
    assert "Synthetic sandbox account only" in reasons
    assert "Scheduled trust rotation" in reasons
    assert "Exercise completed" in reasons
    assert "Remove sandbox trust" in reasons


def test_approval_requires_complete_trust_and_connected_account(
    client: TestClient, db: Session
) -> None:
    owner, account = _account(db)
    missing = client.post(
        f"/api/v1/aws/accounts/{account.id}/sandbox-approval",
        headers=_headers(owner),
        json={"reason": "Premature approval"},
    )
    assert missing.status_code == 409
    assert missing.json()["error"]["code"] == "sandbox_approval_prerequisite_missing"

    _configure(client, owner, account)
    db.expire_all()
    stored = db.get(AWSAccount, account.id)
    assert stored is not None
    stored.connection_status = AWSAccountStatus.DISCONNECTED
    stored.status = AWSAccountStatus.DISCONNECTED
    db.commit()
    disconnected = client.post(
        f"/api/v1/aws/accounts/{account.id}/sandbox-approval",
        headers=_headers(owner),
        json={"reason": "Still premature"},
    )
    assert disconnected.status_code == 409
    assert disconnected.json()["error"]["code"] == "sandbox_approval_prerequisite_missing"


def test_failed_audit_write_rolls_back_trust_change(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner, account = _account(db)
    original_role = account.remediation_role_arn
    original_external_id = account.remediation_external_id

    def fail_audit(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("synthetic audit failure")

    monkeypatch.setattr("app.services.remediation_admin.record_audit", fail_audit)
    service = RemediationAdminService(db)
    with pytest.raises(RuntimeError, match="synthetic audit failure"):
        service.configure_trust(
            account.id,
            owner,
            f"arn:aws:iam::{account.account_id}:role/RemediationRole",
        )
    db.rollback()
    db.expire_all()
    stored = db.get(AWSAccount, account.id)
    assert stored is not None
    assert stored.remediation_role_arn == original_role
    assert stored.remediation_external_id == original_external_id


def test_prepare_live_request_is_server_owned_and_requires_reapproval(
    client: TestClient, db: Session
) -> None:
    owner, account, request = _approved_request(db)
    response = client.post(
        f"/api/v1/remediations/{request.id}/prepare-live",
        params={"organization_id": str(account.organization_id)},
        headers=_headers(owner),
        json={},
    )
    assert response.status_code == 200, response.text
    assert response.json()["execution_mode"] == "live_aws"
    assert response.json()["dry_run"] is False
    assert response.json()["status"] == "pending_approval"
    assert db.scalar(select(func.count()).select_from(PlatformJob)) == 0

    db.expire_all()
    stored = db.get(RemediationRequest, request.id)
    assert stored is not None
    assert stored.executor_key == "aws"
    assert stored.execution_mode == RemediationExecutionMode.LIVE_AWS
    assert stored.dry_run is False
    assert stored.target_resource_arn is not None
    assert stored.target_region is not None
    assert stored.approved_at is None
    assert stored.approved_by_user_id is None
    assert stored.approved_snapshot_hash is None
    assert len(stored.request_snapshot_json["asset_evidence_hash"]) == 64
    assert db.scalar(
        select(func.count()).select_from(AuditEvent).where(
            AuditEvent.event_type == "remediation.request.live_prepared",
            AuditEvent.resource_id == request.id,
        )
    ) == 1

    client_owned = client.post(
        f"/api/v1/remediations/{request.id}/prepare-live",
        params={"organization_id": str(account.organization_id)},
        headers=_headers(owner),
        json={"executor_key": "aws", "dry_run": False, "evidence": {}},
    )
    assert client_owned.status_code == 422


def test_prepare_live_rejects_unapproved_account_stale_snapshot_and_wrong_tenant(
    client: TestClient, db: Session
) -> None:
    owner, account, request = _approved_request(db)
    account.sandbox_approved = False
    account.sandbox_approved_at = None
    account.sandbox_approved_by_user_id = None
    db.commit()
    path = f"/api/v1/remediations/{request.id}/prepare-live"
    unapproved = client.post(
        path,
        params={"organization_id": str(account.organization_id)},
        headers=_headers(owner),
        json={},
    )
    assert unapproved.status_code == 409
    assert unapproved.json()["error"]["code"] == "live_request_not_eligible"

    account.sandbox_approved = True
    from app.services.common import now_utc

    account.sandbox_approved_at = now_utc()
    account.sandbox_approved_by_user_id = owner.id
    request.request_snapshot_json = {**request.request_snapshot_json, "tampered": True}
    db.commit()
    stale = client.post(
        path,
        params={"organization_id": str(account.organization_id)},
        headers=_headers(owner),
        json={},
    )
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "live_request_not_eligible"

    other_owner, other_org, _other_account = _tenant(db)
    db.commit()
    hidden = client.post(
        path,
        params={"organization_id": str(other_org.id)},
        headers=_headers(other_owner),
        json={},
    )
    assert hidden.status_code == 404


def test_prepare_live_is_owner_only_and_unsupported_action_is_rejected(
    client: TestClient, db: Session
) -> None:
    owner, account, request = _approved_request(db)
    _other_admin, _other_org, _other_account = _tenant(db, OrganizationRole.ADMIN)
    admin = _other_admin
    db.add(
        OrganizationMembership(
            organization_id=account.organization_id,
            user_id=admin.id,
            role=OrganizationRole.ADMIN,
            status=MembershipStatus.ACTIVE,
        )
    )
    db.commit()
    denied = client.post(
        f"/api/v1/remediations/{request.id}/prepare-live",
        params={"organization_id": str(account.organization_id)},
        headers=_headers(admin),
        json={},
    )
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "remediation_admin_forbidden"

    request.action_key = ".".join(("s3", "unsupported_test_action"))
    request.request_snapshot_json = {
        **request.request_snapshot_json,
        "action_key": request.action_key,
    }
    request.request_snapshot_hash = hashlib.sha256(
        canonical_json(request.request_snapshot_json).encode()
    ).hexdigest()
    request.approved_snapshot_hash = request.request_snapshot_hash
    db.commit()
    unsupported = client.post(
        f"/api/v1/remediations/{request.id}/prepare-live",
        params={"organization_id": str(account.organization_id)},
        headers=_headers(owner),
        json={},
    )
    assert unsupported.status_code == 409
    assert unsupported.json()["error"]["code"] == "remediation_action_not_supported"


def test_live_execution_rejects_asset_evidence_changed_after_approval(db: Session) -> None:
    owner, account, request = _approved_request(db)
    prepared = RemediationAdminService(db).prepare_live_request(
        account.organization_id, request.id, owner
    )
    RemediationService(db).approve(account.organization_id, prepared.id, owner)
    db.commit()
    asset = db.get(Asset, uuid.UUID(str(prepared.request_snapshot_json["asset_id"])))
    assert asset is not None
    asset.metadata_json = {**asset.metadata_json, "changed_after_approval": True}
    db.commit()
    finding = db.get(Finding, prepared.finding_id)
    assert finding is not None
    settings = get_settings().model_copy(
        update={
            "remediation_live_aws_enabled": True,
            "remediation_emergency_stop": False,
        }
    )
    with pytest.raises(ConflictError) as exc_info:
        RemediationService(db, settings=settings)._live_execution_context(
            account.organization_id,
            prepared,
            finding,
        )
    assert exc_info.value.code == "remediation_target_mismatch"


def test_no_admin_path_enables_live_flags_or_calls_aws() -> None:
    source = RemediationAdminService.__module__
    assert source == "app.services.remediation_admin"
    text = __import__(source, fromlist=["__file__"]).__file__
    assert text is not None
    contents = Path(text).read_text(encoding="utf-8")
    assert "boto3" not in contents
    assert "PlatformJob" not in contents
    assert "remediation_live_aws_enabled =" not in contents
    assert "remediation_execution_enabled =" not in contents
