from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, cast

import pytest
from botocore.exceptions import ClientError  # type: ignore[import-untyped]
from pydantic import SecretStr

from app.core.config import Settings
from app.models import AWSAccount
from app.services.aws_credentials import (
    AWSConnectionFailure,
    RemediationRoleCredentialProvider,
    TenantRoleCredentialProvider,
)


def settings() -> Settings:
    return Settings(
        app_env="testing",
        database_url=SecretStr("sqlite://"),
        jwt_secret_key=SecretStr(
            "phase2-workload-test-key-with-at-least-32-characters"
        ),
    )


def account(account_id: str = "123456789012") -> AWSAccount:
    return AWSAccount(
        organization_id=uuid.uuid4(),
        name="Synthetic account",
        account_id=account_id,
        role_arn=f"arn:aws:iam::{account_id}:role/CloudOpsReadOnlyRole",
        external_id="cloudops-synthetic-external-id",
        created_by_user_id=uuid.uuid4(),
    )


class FakeInitialSTS:
    def __init__(
        self,
        expiration: datetime,
        calls: list[dict[str, object]],
        *,
        error: ClientError | None = None,
    ) -> None:
        self.expiration = expiration
        self.calls = calls
        self.error = error

    def assume_role(self, **kwargs: object) -> dict[str, object]:
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        generation = len(self.calls)
        return {
            "Credentials": {
                "AccessKeyId": f"synthetic-access-{generation}",
                "SecretAccessKey": f"synthetic-secret-{generation}",
                "SessionToken": f"synthetic-session-{generation}",
                "Expiration": self.expiration,
            }
        }


class FakeAssumedSTS:
    def __init__(self, returned_account: str) -> None:
        self.returned_account = returned_account

    def get_caller_identity(self) -> dict[str, str]:
        return {"Account": self.returned_account}


def test_provider_uses_default_chain_validates_identity_and_refreshes() -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    clock = [now]
    assume_calls: list[dict[str, object]] = []
    credential_kwargs: list[dict[str, object]] = []
    initial = FakeInitialSTS(now + timedelta(minutes=15), assume_calls)

    def sts_factory(service: str, **kwargs: object) -> object:
        assert service == "sts"
        if "aws_access_key_id" not in kwargs:
            # The initial client receives only configuration: Boto3 resolves
            # ECS/EC2/EKS/Lambda/SSO credentials through its default chain.
            assert set(kwargs) == {"config"}
            return initial
        credential_kwargs.append(kwargs)
        return FakeAssumedSTS("123456789012")

    client_calls: list[tuple[str, str | None, dict[str, object]]] = []

    def boto_client(service: str, region_name: str | None = None, **kwargs: object) -> object:
        client_calls.append((service, region_name, kwargs))
        return object()

    provider = TenantRoleCredentialProvider(
        account(),
        settings(),
        sts_client_factory=sts_factory,
        client_factory=boto_client,
        now=lambda: clock[0],
    )
    provider.client("ec2", "us-east-1")
    provider.client("s3", None)
    assert len(assume_calls) == 1
    assert assume_calls[0]["ExternalId"] == "cloudops-synthetic-external-id"
    assert len(credential_kwargs) == 1
    assert len(client_calls) == 2

    clock[0] = now + timedelta(minutes=14, seconds=1)
    initial.expiration = clock[0] + timedelta(minutes=15)
    provider.client("iam", None)
    assert len(assume_calls) == 2
    assert "synthetic-secret" not in repr(provider)


def test_provider_rejects_wrong_account_without_returning_credentials() -> None:
    now = datetime.now(UTC)
    initial = FakeInitialSTS(now + timedelta(minutes=15), [])

    def factory(service: str, **kwargs: object) -> object:
        if "aws_access_key_id" not in kwargs:
            return initial
        return FakeAssumedSTS("999999999999")

    provider = TenantRoleCredentialProvider(
        account(),
        settings(),
        sts_client_factory=factory,
        client_factory=cast(Any, lambda *_args, **_kwargs: object()),
    )
    with pytest.raises(AWSConnectionFailure, match="caller_account_mismatch"):
        provider.client("ec2", "us-east-1")


def test_remediation_provider_uses_separate_role_and_external_id() -> None:
    target = account()
    target.remediation_role_arn = (
        f"arn:aws:iam::{target.account_id}:role/CloudOpsRemediationRole"
    )
    target.remediation_external_id = "synthetic-remediation-external-id"
    calls: list[dict[str, object]] = []
    initial = FakeInitialSTS(datetime.now(UTC) + timedelta(minutes=15), calls)

    def factory(service: str, **kwargs: object) -> object:
        if "aws_access_key_id" not in kwargs:
            return initial
        return FakeAssumedSTS(target.account_id)

    provider = RemediationRoleCredentialProvider(
        target,
        settings(),
        sts_client_factory=factory,
        client_factory=cast(Any, lambda *_args, **_kwargs: object()),
    )
    provider.client("s3", None)

    assert calls[0]["RoleArn"] == target.remediation_role_arn
    assert calls[0]["ExternalId"] == target.remediation_external_id
    assert calls[0]["RoleArn"] != target.role_arn
    assert calls[0]["ExternalId"] != target.external_id


@pytest.mark.parametrize("code", ("AccessDenied", "ExpiredToken", "ThrottlingException"))
def test_provider_safely_classifies_sts_failures(code: str) -> None:
    error = ClientError(
        {"Error": {"Code": code, "Message": "phase2-sensitive-provider-detail"}},
        "AssumeRole",
    )
    initial = FakeInitialSTS(datetime.now(UTC) + timedelta(minutes=15), [], error=error)
    provider = TenantRoleCredentialProvider(
        account(),
        settings(),
        sts_client_factory=lambda *_args, **_kwargs: initial,
        client_factory=cast(Any, lambda *_args, **_kwargs: object()),
    )
    with pytest.raises(AWSConnectionFailure) as caught:
        provider.client("ec2", None)
    assert "phase2-sensitive-provider-detail" not in str(caught.value)


def test_providers_do_not_share_credentials_across_tenants() -> None:
    now = datetime.now(UTC)
    calls: list[dict[str, object]] = []
    initial = FakeInitialSTS(now + timedelta(minutes=15), calls)

    def factory(service: str, **kwargs: object) -> object:
        if "aws_access_key_id" not in kwargs:
            return initial
        access_key = str(kwargs["aws_access_key_id"])
        returned_account = "123456789012" if access_key.endswith("-1") else "210987654321"
        return FakeAssumedSTS(returned_account)

    clients: list[dict[str, object]] = []

    def client_factory(_service: str, **kwargs: object) -> object:
        clients.append(kwargs)
        return object()

    first = TenantRoleCredentialProvider(
        account("123456789012"),
        settings(),
        sts_client_factory=factory,
        client_factory=client_factory,
    )
    second = TenantRoleCredentialProvider(
        account("210987654321"),
        settings(),
        sts_client_factory=factory,
        client_factory=client_factory,
    )
    first.client("s3", None)
    second.client("s3", None)
    assert len(calls) == 2
    assert clients[0]["aws_access_key_id"] != clients[1]["aws_access_key_id"]
