from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, ClassVar

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import Asset, AuditEvent, AWSAccount, OrganizationMembership, User
from app.models.enums import (
    AssetType,
    AWSAccountStatus,
    MembershipStatus,
    OrganizationRole,
)
from app.services.aws_credentials import TenantRoleCredentialProvider
from app.services.discovery import DiscoveryOrchestrator, IAMDiscoveryService
from app.tests.conftest import TestingSession, register_and_login
from app.tests.test_discovery import FakeService, asset, organization_and_account
from app.worker.job_worker import JobWorker


class Pages:
    def __init__(self, pages: list[dict[str, Any]]) -> None:
        self.pages = pages

    def paginate(self, **_kwargs: object) -> list[dict[str, Any]]:
        return self.pages


def test_discovery_clients_receive_bounded_timeout_and_retry_config(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    account = AWSAccount(
        organization_id=uuid.uuid4(),
        name="Config",
        account_id="123456789012",
        role_arn="arn:aws:iam::123456789012:role/CloudOpsReadOnlyRole",
        external_id="cloudops-test",
        created_by_user_id=uuid.uuid4(),
    )
    calls: list[dict[str, Any]] = []

    def client(
        _self: TenantRoleCredentialProvider, service: str, region: str | None
    ) -> object:
        calls.append(
            {
                "service": service,
                "region": region,
                "config": _self.settings.aws_client_config,
            }
        )
        return object()

    monkeypatch.setattr(TenantRoleCredentialProvider, "client", client)
    factory = DiscoveryOrchestrator(db, get_settings())._assumed_client_factory(account)
    factory("ec2", "us-east-1")
    config = calls[0]["config"]
    assert config.connect_timeout == 5
    assert config.read_timeout == 30
    assert config.retries == {"total_max_attempts": 3, "mode": "standard"}


def test_every_iam_operation_handles_multiple_pages_and_duplicates() -> None:
    class IAM:
        tag_calls: ClassVar[list[str]] = []

        def get_paginator(self, operation: str) -> Pages:
            if operation.endswith("_tags"):
                self.tag_calls.append(operation)
                return Pages([{"Tags": []}, {"Tags": []}])
            values = {
                "list_users": ("Users", "UserId", "UserName", "U"),
                "list_roles": ("Roles", "RoleId", "RoleName", "R"),
                "list_groups": ("Groups", "GroupId", "GroupName", "G"),
                "list_policies": ("Policies", "PolicyId", "PolicyName", "P"),
            }
            key, id_key, name_key, prefix = values[operation]
            first = {id_key: f"{prefix}1", name_key: f"{prefix.lower()}-one", "Arn": "arn:1"}
            second = {id_key: f"{prefix}2", name_key: f"{prefix.lower()}-two", "Arn": "arn:2"}
            return Pages([{key: []}, {key: [first]}, {key: [first, second]}])

        def can_paginate(self, operation: str) -> bool:
            return operation.startswith("list_") and operation.endswith("_tags")

        def __getattr__(self, name: str) -> object:
            if name.startswith("list_") and name.endswith("_tags"):
                return lambda **_kwargs: {"Tags": []}
            raise AttributeError(name)

    assets = IAMDiscoveryService().discover(lambda *_args: IAM(), [], "123456789012")
    assert len(assets) == 8
    assert len({(item.asset_type, item.resource_id) for item in assets}) == 8
    for asset_type in (
        AssetType.IAM_USER,
        AssetType.IAM_ROLE,
        AssetType.IAM_GROUP,
        AssetType.IAM_POLICY,
    ):
        assert len([item for item in assets if item.asset_type == asset_type]) == 2
    # IAM groups do not support the tagging API; a regression that calls
    # list_group_tags for either group asset must fail here.
    assert IAM.tag_calls == ["list_user_tags"] * 2 + ["list_role_tags"] * 2 + [
        "list_policy_tags"
    ] * 2


@pytest.mark.parametrize(
    "account_state",
    [AWSAccountStatus.PENDING, AWSAccountStatus.FAILED, AWSAccountStatus.DISCONNECTED],
)
def test_only_connected_accounts_reach_collectors(
    client: TestClient,
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
    account_state: AWSAccountStatus,
) -> None:
    headers, _organization_id, account = organization_and_account(
        client, db, f"state-{account_state.value}@example.com"
    )
    account.status = account.connection_status = account_state
    db.commit()
    calls = 0

    def must_not_run(*_args: object) -> object:
        nonlocal calls
        calls += 1
        raise AssertionError("collector execution must not start")

    monkeypatch.setattr(DiscoveryOrchestrator, "run", must_not_run)
    response = client.post(f"/api/v1/aws/accounts/{account.id}/discover", headers=headers)
    assert response.status_code == 409
    assert calls == 0


def test_complete_api_discovery_uses_every_collector_and_exposes_safe_details(
    client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    headers, organization_id, account = organization_and_account(
        client, db, "complete-chain@example.com"
    )

    class EC2:
        def get_paginator(self, _operation: str) -> Pages:
            return Pages(
                [
                    {
                        "Reservations": [
                            {
                                "Instances": [
                                    {
                                        "InstanceId": "i-1",
                                        "State": {"Name": "running"},
                                        "Tags": [{"Key": "Name", "Value": "web"}],
                                    }
                                ]
                            }
                        ]
                    }
                ]
            )

    class S3:
        def get_paginator(self, _operation: str) -> Pages:
            return Pages([{"Buckets": [{"Name": "logs"}]}])

        def get_bucket_location(self, **_kwargs: object) -> dict[str, str]:
            return {"LocationConstraint": "eu-west-1"}

        def get_bucket_tagging(self, **_kwargs: object) -> dict[str, list[dict[str, str]]]:
            return {"TagSet": []}

    class IAM:
        def get_paginator(self, operation: str) -> Pages:
            rows = {
                "list_users": ("Users", {"UserId": "U1", "UserName": "alice"}),
                "list_roles": ("Roles", {"RoleId": "R1", "RoleName": "app"}),
                "list_groups": ("Groups", {"GroupId": "G1", "GroupName": "team"}),
                "list_policies": (
                    "Policies",
                    {"PolicyId": "P1", "PolicyName": "managed", "Arn": "arn:policy"},
                ),
            }
            key, value = rows[operation]
            return Pages([{key: [value]}])

        def can_paginate(self, _operation: str) -> bool:
            return False

        def __getattr__(self, name: str) -> object:
            if name.startswith("list_") and name.endswith("_tags"):
                return lambda **_kwargs: {"Tags": []}
            raise AttributeError(name)

    class RDS:
        def get_paginator(self, _operation: str) -> Pages:
            return Pages(
                [
                    {
                        "DBInstances": [
                            {
                                "DBInstanceIdentifier": "orders",
                                "DBInstanceArn": "arn:rds",
                                "DBInstanceStatus": "available",
                            }
                        ]
                    }
                ]
            )

        def list_tags_for_resource(self, **_kwargs: object) -> dict[str, list[object]]:
            return {"TagList": []}

    clients = {"ec2": EC2(), "s3": S3(), "iam": IAM(), "rds": RDS()}
    monkeypatch.setattr(
        DiscoveryOrchestrator,
        "_assumed_client_factory",
        lambda *_args: lambda service, _region: clients[service],
    )
    response = client.post(f"/api/v1/aws/accounts/{account.id}/discover", headers=headers)
    assert response.status_code == 202
    assert response.json()["status"] == "available"
    assert JobWorker(TestingSession, get_settings(), "complete-discovery-test").process_one()
    assert db.scalar(select(func.count()).select_from(Asset)) == 7
    events = set(db.scalars(select(AuditEvent.event_type)).all())
    assert {"aws.discovery.started", "aws.discovery.completed"} <= events

    listing = client.get(
        "/api/v1/assets", headers=headers, params={"organization_id": organization_id}
    )
    assert listing.status_code == 200 and listing.json()["total"] == 7
    detail_id = listing.json()["items"][0]["id"]
    detail = client.get(
        f"/api/v1/assets/{detail_id}",
        headers=headers,
        params={"organization_id": organization_id},
    )
    assert detail.status_code == 200
    summary = client.get(
        "/api/v1/assets/summary", headers=headers, params={"organization_id": organization_id}
    )
    assert summary.json()["total"] == 7
    jobs = client.get(
        "/api/v1/discovery/jobs", headers=headers, params={"organization_id": organization_id}
    )
    assert jobs.json()["total"] == 1
    job_id = jobs.json()["items"][0]["id"]
    job = client.get(
        f"/api/v1/discovery/jobs/{job_id}",
        headers=headers,
        params={"organization_id": organization_id},
    )
    assert job.status_code == 200 and job.json()["status"] == "completed"


def test_asset_filters_stable_pagination_and_safe_details(client: TestClient, db: Session) -> None:
    headers, organization_id, account = organization_and_account(client, db, "filters@example.com")
    start = datetime(2026, 1, 1, tzinfo=UTC)
    rows: list[Asset] = []
    for index in range(31):
        rows.append(
            Asset(
                organization_id=account.organization_id,
                aws_account_id=account.id,
                asset_type=(AssetType.EC2_INSTANCE if index % 2 == 0 else AssetType.S3_BUCKET),
                resource_id=f"resource-{index:02d}",
                name=f"web-{index:02d}",
                region="us-east-1" if index % 2 == 0 else "global",
                status="running" if index % 3 else "stopped",
                is_active=index % 4 != 0,
                first_seen_at=start,
                last_seen_at=start + timedelta(minutes=index),
                tags={"Team": "platform"},
                metadata_json={
                    "safe": True,
                    "SessionToken": "must-not-leak",
                    "html": "<script>alert(1)</script>",
                },
            )
        )
    db.add_all(rows)
    db.commit()

    cases = (
        ({"aws_account_id": str(account.id)}, 31),
        ({"asset_type": "ec2_instance"}, 16),
        ({"region": "global"}, 15),
        ({"status": "stopped"}, 11),
        ({"is_active": "false"}, 8),
        ({"search": "web-01"}, 1),
        ({"asset_type": "ec2_instance", "status": "running", "is_active": "true"}, 5),
    )
    for filters, expected in cases:
        response = client.get(
            "/api/v1/assets",
            headers=headers,
            params={"organization_id": organization_id, **filters},
        )
        assert response.status_code == 200, response.text
        assert response.json()["total"] == expected

    assert (
        client.get(
            "/api/v1/assets",
            headers=headers,
            params={"organization_id": organization_id, "asset_type": "invalid"},
        ).status_code
        == 422
    )
    assert (
        client.get(
            "/api/v1/assets",
            headers=headers,
            params={"organization_id": organization_id, "search": "x" * 201},
        ).status_code
        == 422
    )
    injection = client.get(
        "/api/v1/assets",
        headers=headers,
        params={"organization_id": organization_id, "search": "' OR 1=1 --"},
    )
    assert injection.status_code == 200 and injection.json()["total"] == 0

    pages: list[list[str]] = []
    for page in (1, 2, 3, 4):
        response = client.get(
            "/api/v1/assets",
            headers=headers,
            params={"organization_id": organization_id, "page": page, "page_size": 10},
        )
        assert response.status_code == 200
        pages.append([item["id"] for item in response.json()["items"]])
    assert [len(page) for page in pages] == [10, 10, 10, 1]
    assert len(set().union(*map(set, pages))) == 31
    empty = client.get(
        "/api/v1/assets",
        headers=headers,
        params={"organization_id": organization_id, "page": 5, "page_size": 10},
    )
    assert empty.json()["items"] == []
    assert (
        client.get(
            "/api/v1/assets",
            headers=headers,
            params={"organization_id": organization_id, "page_size": 101},
        ).status_code
        == 422
    )

    detail = client.get(
        f"/api/v1/assets/{rows[0].id}",
        headers=headers,
        params={"organization_id": organization_id},
    )
    assert detail.status_code == 200
    assert "SessionToken" not in detail.text
    assert "<script>alert(1)</script>" in detail.text
    unknown = client.get(
        f"/api/v1/assets/{uuid.uuid4()}",
        headers=headers,
        params={"organization_id": organization_id},
    )
    assert unknown.status_code == 404
    other_headers, other_org, _other_account = organization_and_account(
        client, db, "filters-other@example.com"
    )
    cross_tenant = client.get(
        f"/api/v1/assets/{rows[0].id}",
        headers=other_headers,
        params={"organization_id": other_org},
    )
    assert cross_tenant.status_code == 404


def test_complete_discovery_rbac_and_membership_matrix(
    client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner_headers, organization_id, account = organization_and_account(
        client, db, "matrix-owner@example.com"
    )
    monkeypatch.setattr(DiscoveryOrchestrator, "services", (FakeService([asset("i-rbac")]),))
    monkeypatch.setattr(DiscoveryOrchestrator, "_assumed_client_factory", lambda *_args: object())

    roles = (
        OrganizationRole.ADMIN,
        OrganizationRole.SECURITY_ANALYST,
        OrganizationRole.CLOUD_ENGINEER,
        OrganizationRole.AUDITOR,
        OrganizationRole.VIEWER,
    )
    registered: list[tuple[OrganizationRole, dict[str, str], str]] = []
    for role in roles:
        email = f"matrix-{role.value}@example.com"
        headers = register_and_login(client, email)
        registered.append((role, headers, email))
    identities: list[tuple[OrganizationRole, dict[str, str], OrganizationMembership]] = []
    for role, headers, email in registered:
        user = db.scalar(select(User).where(User.normalized_email == email))
        assert user is not None
        membership = OrganizationMembership(
            organization_id=account.organization_id,
            user_id=user.id,
            role=role,
            status=MembershipStatus.ACTIVE,
            joined_at=datetime.now(UTC),
        )
        db.add(membership)
        identities.append((role, headers, membership))
    db.commit()

    assert (
        client.post(
            f"/api/v1/aws/accounts/{account.id}/discover", headers=owner_headers
        ).status_code
        == 202
    )
    for role, headers, _membership in identities:
        response = client.post(f"/api/v1/aws/accounts/{account.id}/discover", headers=headers)
        expected = (
            202
            if role
            in {
                OrganizationRole.ADMIN,
                OrganizationRole.SECURITY_ANALYST,
                OrganizationRole.CLOUD_ENGINEER,
            }
            else 403
        )
        assert response.status_code == expected, (role, response.text)
        assert (
            client.get(
                "/api/v1/assets",
                headers=headers,
                params={"organization_id": organization_id},
            ).status_code
            == 200
        )
        assert (
            client.get(
                "/api/v1/discovery/jobs",
                headers=headers,
                params={"organization_id": organization_id},
            ).status_code
            == 200
        )

    auditor = next(item for item in identities if item[0] == OrganizationRole.AUDITOR)
    auditor[2].status = MembershipStatus.SUSPENDED
    db.commit()
    assert (
        client.get(
            "/api/v1/assets",
            headers=auditor[1],
            params={"organization_id": organization_id},
        ).status_code
        == 404
    )
    auditor[2].status = MembershipStatus.REMOVED
    db.commit()
    assert (
        client.get(
            "/api/v1/discovery/jobs",
            headers=auditor[1],
            params={"organization_id": organization_id},
        ).status_code
        == 404
    )
