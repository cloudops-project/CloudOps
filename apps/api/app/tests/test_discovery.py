from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any, ClassVar

import pytest
from botocore.exceptions import ClientError  # type: ignore[import-untyped]
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import (
    Asset,
    AuditEvent,
    AWSAccount,
    DiscoveryJob,
    Organization,
    OrganizationMembership,
    User,
)
from app.models.enums import (
    AssetType,
    AWSAccountStatus,
    DiscoveryJobStatus,
    OrganizationRole,
)
from app.services.discovery import (
    DiscoveryOrchestrator,
    EC2DiscoveryService,
    IAMDiscoveryService,
    NormalizedAsset,
    RDSDiscoveryService,
    S3DiscoveryService,
    iam_tags,
    json_safe,
    safe_aws_error,
)
from app.tests.conftest import TestingSession, register_and_login
from app.worker.job_worker import JobWorker


def _process_discovery(db: Session) -> DiscoveryJob:
    assert JobWorker(TestingSession, get_settings(), "discovery-api-test").process_one()
    db.expire_all()
    job = db.scalar(select(DiscoveryJob).order_by(DiscoveryJob.created_at.desc()))
    assert job is not None
    return job


class Paginator:
    def __init__(self, pages: list[dict[str, Any]]) -> None:
        self.pages = pages

    def paginate(self, **_kwargs: object) -> list[dict[str, Any]]:
        return self.pages


def organization_and_account(
    client: TestClient, db: Session, email: str = "discovery-owner@example.com"
) -> tuple[dict[str, str], str, AWSAccount]:
    headers = register_and_login(client, email)
    organization = client.post(
        "/api/v1/organizations",
        headers=headers,
        json={"name": "Discovery Org", "slug": f"discovery-{uuid.uuid4().hex[:8]}"},
    )
    organization_id = organization.json()["id"]
    response = client.post(
        "/api/v1/aws/accounts",
        headers=headers,
        json={
            "organization_id": organization_id,
            "name": "Production",
            "account_id": "123456789012",
        },
    )
    account = db.get(AWSAccount, uuid.UUID(response.json()["account"]["id"]))
    assert account is not None
    account.role_arn = "arn:aws:iam::123456789012:role/CloudOpsReadOnlyRole"
    account.status = AWSAccountStatus.CONNECTED
    account.connection_status = AWSAccountStatus.CONNECTED
    db.commit()
    return headers, organization_id, account


def asset(
    resource_id: str,
    *,
    asset_type: AssetType = AssetType.EC2_INSTANCE,
    status: str = "running",
) -> NormalizedAsset:
    return NormalizedAsset(
        asset_type=asset_type,
        resource_id=resource_id,
        arn=f"arn:aws:test::{resource_id}",
        name=resource_id,
        region="us-east-1",
        status=status,
        tags={"Environment": "test"},
        metadata={"safe": True},
    )


class FakeService:
    asset_types: ClassVar[set[AssetType]] = {AssetType.EC2_INSTANCE}

    def __init__(self, values: list[NormalizedAsset] | Exception) -> None:
        self.values = values

    def discover(
        self, _factory: object, _regions: list[str], _account_id: str
    ) -> list[NormalizedAsset]:
        if isinstance(self.values, Exception):
            raise self.values
        return self.values


class FakeS3Service(FakeService):
    asset_types: ClassVar[set[AssetType]] = {AssetType.S3_BUCKET}


def test_ec2_s3_iam_rds_normalization_and_pagination() -> None:
    now = datetime.now(UTC)

    class EC2:
        def get_paginator(self, operation: str) -> Paginator:
            assert operation == "describe_instances"
            return Paginator(
                [
                    {"Reservations": []},
                    {
                        "Reservations": [
                            {
                                "Instances": [
                                    {
                                        "InstanceId": "i-123",
                                        "InstanceType": "t3.micro",
                                        "State": {"Name": "running"},
                                        "VpcId": "vpc-1",
                                        "SubnetId": "subnet-1",
                                        "SecurityGroups": [{"GroupId": "sg-1"}],
                                        "LaunchTime": now,
                                        "Tags": [{"Key": "Name", "Value": "web"}],
                                    }
                                ]
                            }
                        ]
                    },
                ]
            )

    ec2 = EC2DiscoveryService().discover(lambda *_args: EC2(), ["us-east-1"], "123456789012")
    assert ec2[0].name == "web"
    assert ec2[0].metadata["security_group_ids"] == ["sg-1"]

    class S3:
        def get_paginator(self, operation: str) -> Paginator:
            assert operation == "list_buckets"
            return Paginator(
                [{"Buckets": []}, {"Buckets": [{"Name": "logs", "CreationDate": now}]}]
            )

        def get_bucket_location(self, **_kwargs: object) -> dict[str, None]:
            return {"LocationConstraint": None}

        def get_bucket_tagging(self, **_kwargs: object) -> dict[str, list[dict[str, str]]]:
            return {"TagSet": [{"Key": "Team", "Value": "platform"}]}

    s3 = S3DiscoveryService().discover(lambda *_args: S3(), [], "123456789012")
    assert s3[0].region == "us-east-1"
    assert s3[0].tags == {"Team": "platform"}

    class IAM:
        pages: ClassVar[dict[str, list[dict[str, Any]]]] = {
            "list_users": [{"Users": [{"UserId": "U1", "UserName": "alice", "Arn": "user-arn"}]}],
            "list_roles": [{"Roles": [{"RoleId": "R1", "RoleName": "app", "Arn": "role-arn"}]}],
            "list_groups": [
                {"Groups": [{"GroupId": "G1", "GroupName": "team", "Arn": "group-arn"}]}
            ],
            "list_policies": [
                {
                    "Policies": [
                        {
                            "PolicyId": "P1",
                            "PolicyName": "managed",
                            "Arn": "policy-arn",
                            "AttachmentCount": 2,
                        }
                    ]
                }
            ],
        }

        tag_calls: ClassVar[list[str]] = []

        def get_paginator(self, operation: str) -> Paginator:
            return Paginator(self.pages[operation])

        def __getattr__(self, name: str) -> object:
            if name.startswith("list_") and name.endswith("_tags"):
                def list_tags(**_kwargs: object) -> dict[str, list[dict[str, str]]]:
                    self.tag_calls.append(name)
                    return {"Tags": []}

                return list_tags
            raise AttributeError(name)

    iam = IAMDiscoveryService().discover(lambda *_args: IAM(), [], "123456789012")
    assert {item.asset_type for item in iam} == {
        AssetType.IAM_USER,
        AssetType.IAM_ROLE,
        AssetType.IAM_GROUP,
        AssetType.IAM_POLICY,
    }
    # IAM groups do not support the tagging API; a regression that calls
    # list_group_tags (or any other tag operation for groups) must fail here.
    assert IAM.tag_calls == ["list_user_tags", "list_role_tags", "list_policy_tags"]
    assert (
        next(item for item in iam if item.asset_type == AssetType.IAM_POLICY).metadata[
            "attachment_count"
        ]
        == 2
    )

    class RDS:
        def get_paginator(self, operation: str) -> Paginator:
            assert operation == "describe_db_instances"
            return Paginator(
                [
                    {"DBInstances": []},
                    {
                        "DBInstances": [
                            {
                                "DBInstanceIdentifier": "orders",
                                "DBInstanceArn": "rds-arn",
                                "DBInstanceStatus": "available",
                                "Engine": "postgres",
                                "Endpoint": {"Address": "example.invalid", "Port": 5432},
                                "DBSubnetGroup": {"VpcId": "vpc-1"},
                            }
                        ]
                    },
                ]
            )

        def list_tags_for_resource(self, **_kwargs: object) -> dict[str, list[object]]:
            return {"TagList": []}

    rds = RDSDiscoveryService().discover(lambda *_args: RDS(), ["eu-west-1"], "123")
    assert rds[0].metadata["engine"] == "postgres"
    assert rds[0].region == "eu-west-1"


def test_complete_repeated_discovery_upserts_and_stales(
    client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    headers, organization_id, account = organization_and_account(client, db)
    monkeypatch.setattr(DiscoveryOrchestrator, "services", (FakeService([asset("i-1")]),))
    monkeypatch.setattr(DiscoveryOrchestrator, "_assumed_client_factory", lambda *_args: object())
    first = client.post(f"/api/v1/aws/accounts/{account.id}/discover", headers=headers)
    assert first.status_code == 202, first.text
    first_job = _process_discovery(db)
    assert first_job.status == DiscoveryJobStatus.COMPLETED
    assert first_job.assets_created == 1
    stored = db.scalar(select(Asset).where(Asset.resource_id == "i-1"))
    assert stored is not None
    first_seen = stored.first_seen_at

    monkeypatch.setattr(
        DiscoveryOrchestrator,
        "services",
        (FakeService([asset("i-1", status="stopped"), asset("i-2")]),),
    )
    repeated = client.post(f"/api/v1/aws/accounts/{account.id}/discover", headers=headers)
    assert repeated.status_code == 202
    repeated_job = _process_discovery(db)
    assert repeated_job.assets_updated == 1
    assert repeated_job.assets_created == 1
    db.expire_all()
    stored = db.scalar(select(Asset).where(Asset.resource_id == "i-1"))
    assert stored is not None and stored.first_seen_at == first_seen and stored.status == "stopped"

    monkeypatch.setattr(DiscoveryOrchestrator, "services", (FakeService([]),))
    stale = client.post(f"/api/v1/aws/accounts/{account.id}/discover", headers=headers)
    assert stale.status_code == 202
    stale_job = _process_discovery(db)
    assert stale_job.assets_deactivated == 2
    listing = client.get(
        "/api/v1/assets",
        headers=headers,
        params={"organization_id": organization_id, "is_active": False, "page_size": 1},
    )
    assert listing.status_code == 200
    assert listing.json()["total"] == 2
    assert len(listing.json()["items"]) == 1
    summary = client.get(
        "/api/v1/assets/summary", headers=headers, params={"organization_id": organization_id}
    )
    assert summary.json()["stale"] == 2


def test_partial_failure_does_not_deactivate_failed_service_assets(
    client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    headers, _organization_id, account = organization_and_account(
        client, db, "partial-owner@example.com"
    )
    existing = Asset(
        organization_id=account.organization_id,
        aws_account_id=account.id,
        asset_type=AssetType.EC2_INSTANCE,
        resource_id="i-existing",
        name="existing",
        region="us-east-1",
        status="running",
    )
    db.add(existing)
    db.commit()
    failure = ClientError(
        {"Error": {"Code": "AccessDenied", "Message": "SECRET provider message"}},
        "DescribeInstances",
    )
    successful = FakeS3Service([asset("bucket", asset_type=AssetType.S3_BUCKET)])
    monkeypatch.setattr(DiscoveryOrchestrator, "services", (FakeService(failure), successful))
    monkeypatch.setattr(DiscoveryOrchestrator, "_assumed_client_factory", lambda *_args: object())
    response = client.post(f"/api/v1/aws/accounts/{account.id}/discover", headers=headers)
    assert response.status_code == 202
    discovered = _process_discovery(db)
    assert discovered.status == DiscoveryJobStatus.PARTIALLY_COMPLETED
    assert discovered.error_summary == "fakeservice:accessdenied"
    db.expire_all()
    assert db.get(Asset, existing.id).is_active is True  # type: ignore[union-attr]
    assert "SECRET" not in response.text


def test_failed_discovery_state_rbac_tenant_audit_and_bounds(
    client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    headers, organization_id, account = organization_and_account(
        client, db, "controls-owner@example.com"
    )
    monkeypatch.setattr(
        DiscoveryOrchestrator, "services", (FakeService(RuntimeError("credential=secret")),)
    )
    monkeypatch.setattr(DiscoveryOrchestrator, "_assumed_client_factory", lambda *_args: object())
    failed = client.post(f"/api/v1/aws/accounts/{account.id}/discover", headers=headers)
    assert failed.status_code == 202
    failed_job = _process_discovery(db)
    assert failed_job.status == DiscoveryJobStatus.FAILED
    assert failed_job.error_summary == "fakeservice:discovery_service_failed"
    events = set(db.scalars(select(AuditEvent.event_type)).all())
    assert {"aws.discovery.started", "aws.discovery.failed"} <= events
    assert "credential=secret" not in str(db.scalars(select(AuditEvent.metadata_json)).all())

    assert client.get("/api/v1/assets").status_code == 401
    assert (
        client.get(
            "/api/v1/assets",
            headers=headers,
            params={"organization_id": organization_id, "page_size": 101},
        ).status_code
        == 422
    )

    viewer_headers = register_and_login(client, "discovery-viewer@example.com")
    viewer = client.get("/api/v1/auth/me", headers=viewer_headers).json()
    member = db.scalar(
        select(OrganizationMembership).where(
            OrganizationMembership.user_id == uuid.UUID(viewer["user"]["id"])
        )
    )
    assert member is None
    owner_membership = db.scalar(
        select(OrganizationMembership).where(
            OrganizationMembership.organization_id == account.organization_id
        )
    )
    assert owner_membership is not None
    viewer_user_id = uuid.UUID(viewer["user"]["id"])
    db.add(
        OrganizationMembership(
            organization_id=account.organization_id,
            user_id=viewer_user_id,
            role=OrganizationRole.VIEWER,
            status=owner_membership.status,
            joined_at=datetime.now(UTC),
        )
    )
    db.commit()
    assert (
        client.post(
            f"/api/v1/aws/accounts/{account.id}/discover", headers=viewer_headers
        ).status_code
        == 403
    )
    assert (
        client.get(
            "/api/v1/assets",
            headers=viewer_headers,
            params={"organization_id": organization_id},
        ).status_code
        == 200
    )

    other_headers, other_org, _other_account = organization_and_account(
        client, db, "other-discovery@example.com"
    )
    assert (
        client.get(
            "/api/v1/assets",
            headers=other_headers,
            params={"organization_id": organization_id},
        ).status_code
        == 404
    )
    assert (
        client.get(
            f"/api/v1/discovery/jobs/{failed.json()['id']}",
            headers=other_headers,
            params={"organization_id": other_org},
        ).status_code
        == 404
    )

    account.connection_status = AWSAccountStatus.DISCONNECTED
    db.commit()
    assert (
        client.post(f"/api/v1/aws/accounts/{account.id}/discover", headers=headers).status_code
        == 409
    )


def test_active_job_constraint_and_secret_redaction(db: Session) -> None:
    assert json_safe({"safe": 1, "SessionToken": "secret", "nested": {"password": "x"}}) == {
        "safe": 1,
        "nested": {},
    }
    error = ClientError(
        {"Error": {"Code": "ThrottlingException", "Message": "provider secret"}},
        "Call",
    )
    assert safe_aws_error(error) == "throttlingexception"

    class Tagged:
        def can_paginate(self, _operation: str) -> bool:
            return True

        def get_paginator(self, _operation: str) -> Paginator:
            return Paginator(
                [
                    {"Tags": [{"Key": "Team", "Value": "platform"}]},
                    {"Tags": [{"Key": "SecretAccessKey", "Value": "not-stored"}]},
                ]
            )

    assert iam_tags(Tagged(), "list_user_tags", "UserName", "alice") == {"Team": "platform"}

    # The partial unique index is exercised against SQLite here and PostgreSQL in the PG suite.
    user_id, organization_id, account_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    from app.security.passwords import hash_password

    db.add(
        User(
            id=user_id,
            email="constraint@example.com",
            normalized_email="constraint@example.com",
            password_hash=hash_password("Strong-Password-123!"),
            full_name="Constraint",
        )
    )
    db.flush()
    db.add(
        Organization(
            id=organization_id,
            name="Constraint",
            slug="constraint",
            created_by_user_id=user_id,
        )
    )
    db.flush()
    db.add(
        AWSAccount(
            id=account_id,
            organization_id=organization_id,
            name="Test",
            account_id="222233334444",
            external_id="cloudops-constraint",
            created_by_user_id=user_id,
        )
    )
    db.flush()
    db.add(
        DiscoveryJob(
            organization_id=organization_id,
            aws_account_id=account_id,
            started_by_user_id=user_id,
            status=DiscoveryJobStatus.RUNNING,
            started_at=datetime.now(UTC),
        )
    )
    db.commit()
    db.add(
        DiscoveryJob(
            organization_id=organization_id,
            aws_account_id=account_id,
            started_by_user_id=user_id,
            status=DiscoveryJobStatus.PENDING,
        )
    )
    with pytest.raises(IntegrityError):
        db.commit()
