from __future__ import annotations

import uuid
from typing import Any, cast

import pytest
from botocore.exceptions import ClientError  # type: ignore[import-untyped]
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.exceptions.errors import AppError
from app.models import (
    AuditEvent,
    AWSAccount,
    AWSExternalIDReservation,
    Organization,
    User,
)
from app.models.enums import AWSAccountStatus, OrganizationRole
from app.security.passwords import hash_password
from app.services.aws_credentials import AWSConnectionFailure
from app.services.aws_onboarding import AWSOnboardingService
from app.tests.conftest import register_and_login


def create_organization(client: TestClient, email: str, slug: str) -> tuple[dict[str, str], str]:
    headers = register_and_login(client, email)
    response = client.post(
        "/api/v1/organizations",
        headers=headers,
        json={"name": slug.replace("-", " ").title(), "slug": slug},
    )
    assert response.status_code == 201
    return headers, response.json()["id"]


def create_aws_account(
    client: TestClient,
    headers: dict[str, str],
    organization_id: str,
    account_id: str = "123456789012",
) -> dict[str, Any]:
    response = client.post(
        "/api/v1/aws/accounts",
        headers=headers,
        json={
            "organization_id": organization_id,
            "name": "Production",
            "account_id": account_id,
        },
    )
    assert response.status_code == 201, response.text
    return cast(dict[str, Any], response.json())


def test_external_id_account_id_and_role_arn_validation() -> None:
    generated = {AWSOnboardingService.generate_external_id() for _ in range(100)}
    assert len(generated) == 100
    assert all(value.startswith("cloudops-") for value in generated)
    assert AWSOnboardingService.validate_account_id("123456789012") == "123456789012"
    with pytest.raises(AppError):
        AWSOnboardingService.validate_account_id("123")
    role = "arn:aws:iam::123456789012:role/CloudOpsReadOnlyRole"
    assert AWSOnboardingService.validate_role_arn(role, "123456789012") == role
    with pytest.raises(AppError):
        AWSOnboardingService.validate_role_arn(role, "999999999999")
    with pytest.raises(AppError):
        AWSOnboardingService.validate_role_arn("not-an-arn")


def test_customer_trust_policy_supports_exact_api_and_worker_principals(
    db: Session,
) -> None:
    principals = [
        "arn:aws:iam::111122223333:role/cloudops-production-api-task",
        "arn:aws:iam::111122223333:role/cloudops-production-worker-task",
    ]
    settings = get_settings().model_copy(
        update={
            "aws_trusted_principal_arn": "",
            "aws_trusted_principal_arns": ",".join(principals),
        }
    )

    assert AWSOnboardingService(db, settings)._trusted_principals() == principals


def test_sts_assume_role_uses_temporary_credentials_only(db: Session) -> None:
    calls: list[tuple[str, dict[str, object]]] = []

    class InitialSTS:
        def assume_role(self, **kwargs: object) -> dict[str, object]:
            calls.append(("assume", kwargs))
            return {
                "Credentials": {
                    "AccessKeyId": "temporary-access",
                    "SecretAccessKey": "temporary-secret",
                    "SessionToken": "temporary-session",
                }
            }

    class AssumedSTS:
        def get_caller_identity(self) -> dict[str, str]:
            calls.append(("identity", {}))
            return {"Account": "123456789012"}

    def factory(service: str, **kwargs: object) -> object:
        assert service == "sts"
        config = cast(Any, kwargs.pop("config"))
        assert config.connect_timeout == 5
        assert config.read_timeout == 30
        assert config.retries == {
            "total_max_attempts": 3,
            "mode": "standard",
        }
        if kwargs:
            assert kwargs == {
                "aws_access_key_id": "temporary-access",
                "aws_secret_access_key": "temporary-secret",
                "aws_session_token": "temporary-session",
            }
            return AssumedSTS()
        return InitialSTS()

    account = AWSAccount(
        organization_id=uuid.uuid4(),
        name="Production",
        account_id="123456789012",
        role_arn="arn:aws:iam::123456789012:role/CloudOpsReadOnlyRole",
        external_id="cloudops-test-external-id",
        created_by_user_id=uuid.uuid4(),
    )
    service = AWSOnboardingService(db, get_settings(), sts_client_factory=factory)
    assert service.assume_role(account) == "123456789012"
    assert [name for name, _ in calls] == ["assume", "identity"]


def test_sts_failure_is_safely_classified(db: Session) -> None:
    class DeniedSTS:
        def assume_role(self, **kwargs: object) -> None:
            raise ClientError(
                {"Error": {"Code": "AccessDenied", "Message": "sensitive provider detail"}},
                "AssumeRole",
            )

    account = AWSAccount(
        organization_id=uuid.uuid4(),
        name="Denied",
        account_id="123456789012",
        role_arn="arn:aws:iam::123456789012:role/CloudOpsReadOnlyRole",
        external_id="cloudops-denied-external-id",
        created_by_user_id=uuid.uuid4(),
    )
    service = AWSOnboardingService(
        db, get_settings(), sts_client_factory=lambda *_args, **_kwargs: DeniedSTS()
    )
    with pytest.raises(AWSConnectionFailure, match="sts_accessdenied"):
        service.assume_role(account)


def test_create_duplicate_policies_and_listing(client: TestClient) -> None:
    owner, organization_id = create_organization(client, "aws-owner@example.com", "aws-owner")
    created = create_aws_account(client, owner, organization_id)
    account = created["account"]
    assert isinstance(account, dict)
    assert account["status"] == "pending"
    assert str(created["external_id"]).startswith("cloudops-")
    assert (
        created["trust_policy"]["Statement"][0]["Condition"]["StringEquals"]["sts:ExternalId"]
        == created["external_id"]
    )
    assert created["permission_policy"]["managed_policy_arn"] == (
        "arn:aws:iam::aws:policy/SecurityAudit"
    )
    duplicate = client.post(
        "/api/v1/aws/accounts",
        headers=owner,
        json={
            "organization_id": organization_id,
            "name": "Duplicate",
            "account_id": "123456789012",
        },
    )
    assert duplicate.status_code == 409
    listed = client.get(
        "/api/v1/aws/accounts", headers=owner, params={"organization_id": organization_id}
    )
    assert listed.status_code == 200
    assert len(listed.json()) == 1


def test_missing_trusted_principal_does_not_persist_account(
    client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner, organization_id = create_organization(
        client, "missing-principal@example.com", "missing-principal"
    )
    monkeypatch.setattr(get_settings(), "aws_trusted_principal_arn", "")

    response = client.post(
        "/api/v1/aws/accounts",
        headers=owner,
        json={
            "organization_id": organization_id,
            "name": "Must not persist",
            "account_id": "123456789012",
        },
    )

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "aws_principal_not_configured"
    assert db.scalar(select(func.count()).select_from(AWSAccount)) == 0
    assert db.scalar(select(func.count()).select_from(AWSExternalIDReservation)) == 0


def test_role_update_validation_success_failure_mismatch_and_audit(
    client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner, organization_id = create_organization(
        client, "validation-owner@example.com", "validation-owner"
    )
    created = create_aws_account(client, owner, organization_id)
    account_id = created["account"]["id"]
    role_arn = "arn:aws:iam::123456789012:role/CloudOpsReadOnlyRole"
    updated = client.patch(
        f"/api/v1/aws/accounts/{account_id}",
        headers=owner,
        json={"role_arn": role_arn},
    )
    assert updated.status_code == 200
    assert updated.json()["account"]["connection_status"] == "pending"

    monkeypatch.setattr(
        AWSOnboardingService, "assume_role", lambda _self, account: account.account_id
    )
    connected = client.post(f"/api/v1/aws/accounts/{account_id}/validate", headers=owner)
    assert connected.status_code == 200
    assert connected.json()["account"]["connection_status"] == "connected"

    monkeypatch.setattr(
        AWSOnboardingService,
        "assume_role",
        lambda _self, _account: "999999999999",
    )
    mismatch = client.post(f"/api/v1/aws/accounts/{account_id}/validate", headers=owner)
    assert mismatch.status_code == 200
    assert mismatch.json()["account"]["connection_status"] == "failed"
    assert mismatch.json()["account"]["failure_reason"] == "caller_account_mismatch"

    def fail(_self: AWSOnboardingService, _account: AWSAccount) -> str:
        raise AWSConnectionFailure("sts_access_denied")

    monkeypatch.setattr(AWSOnboardingService, "assume_role", fail)
    failed = client.post(f"/api/v1/aws/accounts/{account_id}/validate", headers=owner)
    assert failed.json()["account"]["failure_reason"] == "sts_access_denied"
    disconnected = client.post(f"/api/v1/aws/accounts/{account_id}/disconnect", headers=owner)
    assert disconnected.json()["account"]["connection_status"] == "disconnected"

    event_types = set(db.scalars(select(AuditEvent.event_type)).all())
    assert {
        "aws.account.created",
        "aws.account.updated",
        "aws.account.validation_started",
        "aws.account.validation_succeeded",
        "aws.account.validation_failed",
        "aws.account.disconnected",
    } <= event_types
    metadata = db.scalars(
        select(AuditEvent.metadata_json).where(AuditEvent.event_type.like("aws.account.%"))
    ).all()
    assert all("aws_account_id" in item for item in metadata)
    assert "temporary-access" not in str(metadata)


def test_tenant_isolation_and_rbac(client: TestClient) -> None:
    first, first_org = create_organization(client, "first-aws@example.com", "first-aws")
    created = create_aws_account(client, first, first_org)
    account_id = created["account"]["id"]
    second, second_org = create_organization(client, "second-aws@example.com", "second-aws")
    assert client.get(f"/api/v1/aws/accounts/{account_id}", headers=second).status_code == 404
    assert (
        client.get(
            "/api/v1/aws/accounts", headers=second, params={"organization_id": first_org}
        ).status_code
        == 404
    )

    invitation = client.post(
        f"/api/v1/organizations/{second_org}/invitations",
        headers=second,
        json={"email": "aws-viewer@example.com", "role": OrganizationRole.VIEWER.value},
    ).json()
    viewer = register_and_login(client, "aws-viewer@example.com")
    client.post(
        "/api/v1/invitations/accept",
        headers=viewer,
        json={"token": invitation["development_token"]},
    )
    denied = client.post(
        "/api/v1/aws/accounts",
        headers=viewer,
        json={
            "organization_id": second_org,
            "name": "Viewer account",
            "account_id": "210987654321",
        },
    )
    assert denied.status_code == 403


def test_duplicate_role_arn_database_invariant(db: Session) -> None:
    creator = User(
        email="constraint-owner@example.com",
        normalized_email="constraint-owner@example.com",
        password_hash=hash_password("Strong-Password-123!"),
        full_name="Constraint Owner",
    )
    db.add(creator)
    db.flush()
    organization = Organization(
        name="Constraint Org",
        slug="constraint-org",
        created_by_user_id=creator.id,
    )
    db.add(organization)
    db.flush()
    organization_id = organization.id
    role_arn = "arn:aws:iam::123456789012:role/CloudOpsReadOnlyRole"
    first = AWSAccount(
        organization_id=organization_id,
        name="One",
        account_id="123456789012",
        role_arn=role_arn,
        external_id=f"cloudops-{uuid.uuid4()}",
        created_by_user_id=creator.id,
        status=AWSAccountStatus.PENDING,
        connection_status=AWSAccountStatus.PENDING,
    )
    second = AWSAccount(
        organization_id=organization_id,
        name="Two",
        account_id="210987654321",
        role_arn=role_arn,
        external_id=f"cloudops-{uuid.uuid4()}",
        created_by_user_id=creator.id,
        status=AWSAccountStatus.PENDING,
        connection_status=AWSAccountStatus.PENDING,
    )
    db.add_all([first, second])
    with pytest.raises(IntegrityError):
        db.flush()


def test_external_id_reservation_survives_deletion_and_prevents_reuse(
    client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner, organization_id = create_organization(
        client, "reservation-owner@example.com", "reservation-owner"
    )
    values = iter(("cloudops-permanent-id", "cloudops-permanent-id", "cloudops-new-id"))
    monkeypatch.setattr(
        AWSOnboardingService,
        "generate_external_id",
        staticmethod(lambda: next(values)),
    )
    first = create_aws_account(client, owner, organization_id)
    first_id = first["account"]["id"]
    assert first["external_id"] == "cloudops-permanent-id"
    assert client.delete(f"/api/v1/aws/accounts/{first_id}", headers=owner).status_code == 204
    reservation = db.scalar(
        select(AWSExternalIDReservation).where(
            AWSExternalIDReservation.external_id == "cloudops-permanent-id"
        )
    )
    assert reservation is not None
    assert reservation.aws_account_id is None
    assert reservation.retired_at is not None

    second = create_aws_account(client, owner, organization_id, account_id="210987654321")
    assert second["external_id"] == "cloudops-new-id"
    assert db.scalar(select(func.count()).select_from(AWSExternalIDReservation)) == 2
