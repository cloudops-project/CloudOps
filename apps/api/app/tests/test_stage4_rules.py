from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import (
    Asset,
    AWSAccount,
    EvaluationJob,
    Finding,
    Organization,
    OrganizationMembership,
    User,
)
from app.models.enums import (
    AssetType,
    AWSAccountStatus,
    EvaluationJobStatus,
    FindingSeverity,
    FindingStatus,
    MembershipStatus,
    OrganizationRole,
    RuleResultStatus,
)
from app.security.passwords import hash_password
from app.security_rules import default_registry
from app.security_rules.base import RuleContext
from app.security_rules.results import sanitize_evidence
from app.services.common import now_utc
from app.services.discovery import (
    CloudTrailDiscoveryService,
    CloudWatchDiscoveryService,
    EC2DiscoveryService,
    IAMDiscoveryService,
    RDSDiscoveryService,
    S3DiscoveryService,
)
from app.services.evaluations import EvaluationService
from app.tests.conftest import TestingSession, register_and_login
from app.worker.job_worker import JobWorker


def asset(asset_type: AssetType, metadata: dict[str, object]) -> Asset:
    now = datetime.now(UTC)
    return Asset(
        id=uuid.uuid4(),
        organization_id=uuid.uuid4(),
        aws_account_id=uuid.uuid4(),
        asset_type=asset_type,
        resource_id=str(uuid.uuid4()),
        name="test",
        region="us-east-1",
        metadata_json=metadata,
        tags={},
        first_seen_at=now,
        last_seen_at=now,
    )


@pytest.mark.parametrize("cidr", ["0.0.0.0/0", "::/0"])
def test_ssh_world_exposure_is_critical(cidr: str) -> None:
    key = "CidrIpv6" if ":" in cidr else "CidrIp"
    range_key = "Ipv6Ranges" if ":" in cidr else "IpRanges"
    item = asset(
        AssetType.EC2_SECURITY_GROUP,
        {
            "ip_permissions": [
                {
                    "IpProtocol": "tcp",
                    "FromPort": 22,
                    "ToPort": 22,
                    range_key: [{key: cidr}],
                }
            ]
        },
    )
    rule = default_registry.get("EC2_SG_SSH_OPEN_TO_WORLD")
    assert rule is not None
    assert rule.severity == FindingSeverity.CRITICAL
    result = rule.evaluate(item, RuleContext((item,)))
    assert result.status == RuleResultStatus.FAILED
    assert cidr in str(result.evidence)


def test_ssh_private_cidr_passes() -> None:
    item = asset(
        AssetType.EC2_SECURITY_GROUP,
        {
            "ip_permissions": [
                {
                    "IpProtocol": "tcp",
                    "FromPort": 22,
                    "ToPort": 22,
                    "IpRanges": [{"CidrIp": "10.0.0.0/8"}],
                }
            ]
        },
    )
    rule = default_registry.get("EC2_SG_SSH_OPEN_TO_WORLD")
    assert rule is not None
    assert rule.evaluate(item, RuleContext((item,))).status == RuleResultStatus.PASSED


def test_malformed_security_group_metadata_is_error() -> None:
    item = asset(AssetType.EC2_SECURITY_GROUP, {"ip_permissions": "not-a-list"})
    rule = default_registry.get("EC2_SG_SSH_OPEN_TO_WORLD")
    assert rule is not None
    assert rule.evaluate(item, RuleContext((item,))).status == RuleResultStatus.ERROR


def test_cloudtrail_disabled_and_cloudwatch_retention_rules() -> None:
    trail = asset(AssetType.CLOUDTRAIL_TRAIL, {"is_logging": False})
    log_group = asset(AssetType.CLOUDWATCH_LOG_GROUP, {"retention_days": None})
    trail_rule = default_registry.get("CLOUDTRAIL_LOGGING_DISABLED")
    retention_rule = default_registry.get("CLOUDWATCH_LOG_GROUP_RETENTION_NOT_CONFIGURED")
    assert trail_rule is not None and retention_rule is not None
    assert trail_rule.severity == FindingSeverity.CRITICAL
    assert retention_rule.severity == FindingSeverity.MEDIUM
    assert trail_rule.evaluate(trail, RuleContext((trail,))).status == RuleResultStatus.FAILED
    assert (
        retention_rule.evaluate(log_group, RuleContext((log_group,))).status
        == RuleResultStatus.FAILED
    )


def test_evidence_is_bounded_and_redacted() -> None:
    evidence = sanitize_evidence(
        {
            "AccessKeyId": "not-a-real-key",
            "SessionToken": "not-a-real-token",
            "safe": "<script>alert('x')</script>",
            "long": "x" * 2000,
        }
    )
    assert "AccessKeyId" not in evidence
    assert "SessionToken" not in evidence
    assert evidence["safe"] == "<script>alert('x')</script>"
    assert len(str(evidence["long"])) == 1000


def seeded_account(db: Session) -> tuple[User, Organization, AWSAccount, Asset]:
    actor = User(
        email=f"stage4-{uuid.uuid4()}@example.com",
        normalized_email=f"stage4-{uuid.uuid4()}@example.com",
        password_hash=hash_password("Strong-Password-123!"),
        full_name="Stage Four Owner",
    )
    actor.normalized_email = actor.email
    db.add(actor)
    db.flush()
    organization = Organization(
        name="Stage Four",
        slug=f"stage-four-{uuid.uuid4()}",
        created_by_user_id=actor.id,
    )
    db.add(organization)
    db.flush()
    db.add(
        OrganizationMembership(
            organization_id=organization.id,
            user_id=actor.id,
            role=OrganizationRole.OWNER,
            status=MembershipStatus.ACTIVE,
            joined_at=now_utc(),
        )
    )
    account = AWSAccount(
        organization_id=organization.id,
        name="Production",
        account_id="123456789012",
        role_arn="arn:aws:iam::123456789012:role/CloudOpsReadOnlyRole",
        external_id=f"cloudops-{uuid.uuid4()}",
        status=AWSAccountStatus.CONNECTED,
        connection_status=AWSAccountStatus.CONNECTED,
        created_by_user_id=actor.id,
    )
    db.add(account)
    db.flush()
    item = asset(
        AssetType.EC2_SECURITY_GROUP,
        {
            "ip_permissions": [
                {
                    "IpProtocol": "tcp",
                    "FromPort": 22,
                    "ToPort": 22,
                    "IpRanges": [{"CidrIp": "0.0.0.0/0"}],
                }
            ]
        },
    )
    item.organization_id = organization.id
    item.aws_account_id = account.id
    item.resource_id = "sg-stage4"
    db.add(item)
    db.commit()
    return actor, organization, account, item


def test_finding_lifecycle_detect_resolve_reopen_and_error(db: Session) -> None:
    actor, _organization, account, item = seeded_account(db)
    first_job = EvaluationService(db).start(account.id, actor)
    finding = db.scalar(
        select(Finding).where(
            Finding.asset_id == item.id,
            Finding.rule_key == "EC2_SG_SSH_OPEN_TO_WORLD",
        )
    )
    assert finding is not None
    assert finding.status == FindingStatus.OPEN
    first_seen = finding.first_seen_at

    second_job = EvaluationService(db).start(account.id, actor)
    db.refresh(finding)
    assert finding.id
    assert finding.first_seen_at == first_seen
    assert finding.last_evaluation_id == second_job.id

    item.metadata_json = {"ip_permissions": []}
    db.commit()
    EvaluationService(db).start(account.id, actor)
    resolved_finding = db.get(Finding, finding.id)
    assert resolved_finding is not None
    assert resolved_finding.status == FindingStatus.RESOLVED

    item.metadata_json = {
        "ip_permissions": [
            {
                "IpProtocol": "tcp",
                "FromPort": 22,
                "ToPort": 22,
                "Ipv6Ranges": [{"CidrIpv6": "::/0"}],
            }
        ]
    }
    db.commit()
    EvaluationService(db).start(account.id, actor)
    db.refresh(finding)
    assert finding.status == FindingStatus.OPEN
    assert finding.first_seen_at == first_seen

    item.metadata_json = {"ip_permissions": "malformed"}
    db.commit()
    EvaluationService(db).start(account.id, actor)
    db.refresh(finding)
    assert finding.status == FindingStatus.OPEN
    assert finding.first_seen_at == first_seen
    assert first_job.id != finding.last_evaluation_id


def test_older_evaluation_cannot_resolve_newer_finding_state(db: Session) -> None:
    actor, organization, account, item = seeded_account(db)
    now = now_utc()
    older = EvaluationJob(
        organization_id=organization.id,
        aws_account_id=account.id,
        sequence=1,
        status=EvaluationJobStatus.RUNNING,
        started_by_user_id=actor.id,
        started_at=now,
    )
    newer = EvaluationJob(
        organization_id=organization.id,
        aws_account_id=account.id,
        sequence=2,
        status=EvaluationJobStatus.COMPLETED,
        started_by_user_id=actor.id,
        started_at=now,
        finished_at=now,
    )
    db.add_all([older, newer])
    db.flush()
    finding = Finding(
        organization_id=organization.id,
        aws_account_id=account.id,
        asset_id=item.id,
        rule_key="EC2_SG_SSH_OPEN_TO_WORLD",
        rule_version=1,
        severity=FindingSeverity.CRITICAL,
        category="network",
        status=FindingStatus.OPEN,
        evidence_json={"newer": True},
        first_seen_at=now,
        last_seen_at=now,
        last_evaluation_id=newer.id,
    )
    db.add(finding)
    db.commit()

    rule = default_registry.get("EC2_SG_SSH_OPEN_TO_WORLD")
    assert rule is not None
    passing = rule.evaluate(
        asset(AssetType.EC2_SECURITY_GROUP, {"ip_permissions": []}),
        RuleContext(()),
    )
    EvaluationService(db)._apply_result(older, rule, item, passing)
    db.commit()
    db.refresh(finding)
    assert finding.status == FindingStatus.OPEN
    assert finding.last_evaluation_id == newer.id


def test_finding_api_rbac_suppression_and_safe_response(client: TestClient, db: Session) -> None:
    headers = register_and_login(client, "stage4-api-owner@example.com")
    created = client.post(
        "/api/v1/organizations",
        headers=headers,
        json={"name": "Stage 4 API", "slug": f"stage4-api-{uuid.uuid4()}"},
    )
    organization_id = uuid.UUID(created.json()["id"])
    actor = db.scalar(select(User).where(User.normalized_email == "stage4-api-owner@example.com"))
    assert actor is not None
    account = AWSAccount(
        organization_id=organization_id,
        name="Production",
        account_id="210987654321",
        role_arn="arn:aws:iam::210987654321:role/CloudOpsReadOnlyRole",
        external_id=f"cloudops-{uuid.uuid4()}",
        status=AWSAccountStatus.CONNECTED,
        connection_status=AWSAccountStatus.CONNECTED,
        created_by_user_id=actor.id,
    )
    db.add(account)
    db.flush()
    item = asset(
        AssetType.CLOUDTRAIL_TRAIL,
        {
            "is_logging": False,
            "SecretAccessKey": "must-never-appear",
        },
    )
    item.organization_id = organization_id
    item.aws_account_id = account.id
    item.resource_id = "trail-api"
    db.add(item)
    db.commit()

    evaluation = client.post(
        f"/api/v1/aws/accounts/{account.id}/evaluate",
        headers=headers,
        json={},
    )
    assert evaluation.status_code == 202, evaluation.text
    assert JobWorker(TestingSession, get_settings(), "evaluation-api-test").process_one()
    db.expire_all()
    domain_evaluation = db.scalar(
        select(EvaluationJob).order_by(EvaluationJob.created_at.desc())
    )
    assert domain_evaluation is not None
    rules = client.get(f"/api/v1/rules?organization_id={organization_id}", headers=headers)
    assert rules.status_code == 200
    rule_detail = client.get(
        f"/api/v1/rules/CLOUDTRAIL_LOGGING_DISABLED?organization_id={organization_id}",
        headers=headers,
    )
    assert rule_detail.status_code == 200
    assert rule_detail.json()["severity"] == "critical"
    assert (
        client.get(
            f"/api/v1/rules/UNKNOWN_RULE?organization_id={organization_id}",
            headers=headers,
        ).status_code
        == 404
    )
    evaluations = client.get(
        f"/api/v1/evaluations?organization_id={organization_id}", headers=headers
    )
    assert evaluations.status_code == 200
    assert evaluations.json()["total"] == 1
    evaluation_id = domain_evaluation.id
    assert (
        client.get(
            f"/api/v1/evaluations/{evaluation_id}?organization_id={organization_id}",
            headers=headers,
        ).status_code
        == 200
    )
    assert (
        client.get(
            f"/api/v1/evaluations/{uuid.uuid4()}?organization_id={organization_id}",
            headers=headers,
        ).status_code
        == 404
    )
    findings = client.get(f"/api/v1/findings?organization_id={organization_id}", headers=headers)
    assert findings.status_code == 200
    assert "must-never-appear" not in findings.text
    finding_id = findings.json()["items"][0]["id"]
    assert (
        client.get(
            f"/api/v1/findings/{finding_id}?organization_id={organization_id}",
            headers=headers,
        ).status_code
        == 200
    )
    summary = client.get(
        f"/api/v1/findings/summary?organization_id={organization_id}", headers=headers
    )
    assert summary.status_code == 200
    assert summary.json()["total"] >= 1
    filtered = client.get(
        "/api/v1/findings",
        headers=headers,
        params={
            "organization_id": str(organization_id),
            "aws_account_id": str(account.id),
            "asset_id": str(item.id),
            "service": "cloudtrail",
            "asset_type": "cloudtrail_trail",
            "severity": "critical",
            "status": "open",
            "rule_key": "CLOUDTRAIL_LOGGING_DISABLED",
            "region": "us-east-1",
            "search": "cloudtrail",
            "page": 1,
            "page_size": 10,
        },
    )
    assert filtered.status_code == 200
    assert filtered.json()["total"] == 1
    summary_item = summary.json()["items"][0]
    assert {
        "service",
        "aws_account_id",
        "asset_type",
        "region",
    }.issubset(summary_item)
    injection = client.get(
        "/api/v1/findings",
        headers=headers,
        params={
            "organization_id": str(organization_id),
            "search": "' OR 1=1 --",
        },
    )
    assert injection.status_code == 200
    assert injection.json()["total"] == 0
    assert (
        client.post(
            f"/api/v1/findings/{finding_id}/suppress?organization_id={organization_id}",
            headers=headers,
            json={"reason": ""},
        ).status_code
        == 422
    )
    suppressed = client.post(
        f"/api/v1/findings/{finding_id}/suppress?organization_id={organization_id}",
        headers=headers,
        json={"reason": "Accepted for a bounded maintenance window."},
    )
    assert suppressed.status_code == 200
    assert suppressed.json()["status"] == "suppressed"
    unsuppressed = client.post(
        f"/api/v1/findings/{finding_id}/unsuppress?organization_id={organization_id}",
        headers=headers,
    )
    assert unsuppressed.status_code == 200
    assert unsuppressed.json()["status"] == "open"

    role_expectations = {
        OrganizationRole.ADMIN: (202, 200),
        OrganizationRole.SECURITY_ANALYST: (202, 200),
        OrganizationRole.CLOUD_ENGINEER: (202, 403),
        OrganizationRole.AUDITOR: (403, 403),
        OrganizationRole.VIEWER: (403, 403),
    }
    for role, (evaluation_status, suppression_status) in role_expectations.items():
        email = f"stage4-{role.value}-{uuid.uuid4()}@example.com"
        role_headers = register_and_login(client, email)
        role_user = db.scalar(select(User).where(User.normalized_email == email))
        assert role_user is not None
        db.add(
            OrganizationMembership(
                organization_id=organization_id,
                user_id=role_user.id,
                role=role,
                status=MembershipStatus.ACTIVE,
                joined_at=now_utc(),
            )
        )
        db.commit()
        assert (
            client.get(
                f"/api/v1/findings?organization_id={organization_id}",
                headers=role_headers,
            ).status_code
            == 200
        )
        assert (
            client.post(
                f"/api/v1/aws/accounts/{account.id}/evaluate",
                headers=role_headers,
                json={},
            ).status_code
            == evaluation_status
        )
        assert (
            client.post(
                f"/api/v1/findings/{finding_id}/suppress?organization_id={organization_id}",
                headers=role_headers,
                json={"reason": "Role-matrix authorization test."},
            ).status_code
            == suppression_status
        )
        if suppression_status == 200:
            client.post(
                f"/api/v1/findings/{finding_id}/unsuppress?organization_id={organization_id}",
                headers=headers,
            )


class Pages:
    def __init__(self, pages: list[dict[str, Any]]) -> None:
        self.pages = pages

    def paginate(self, **_kwargs: Any) -> list[dict[str, Any]]:
        return self.pages


class Stage4EC2Client:
    def get_paginator(self, operation: str) -> Pages:
        pages: dict[str, list[dict[str, Any]]] = {
            "describe_instances": [
                {
                    "Reservations": [
                        {
                            "Instances": [
                                {
                                    "InstanceId": "i-1",
                                    "PublicIpAddress": "203.0.113.10",
                                    "MetadataOptions": {"HttpTokens": "optional"},
                                    "State": {"Name": "running"},
                                }
                            ]
                        }
                    ]
                }
            ],
            "describe_security_groups": [
                {
                    "SecurityGroups": [
                        {
                            "GroupId": "sg-1",
                            "GroupName": "public",
                            "IpPermissions": [
                                {
                                    "IpProtocol": "tcp",
                                    "FromPort": 22,
                                    "ToPort": 22,
                                    "IpRanges": [{"CidrIp": "0.0.0.0/0"}],
                                }
                            ],
                            "IpPermissionsEgress": [],
                        }
                    ]
                }
            ],
            "describe_security_group_rules": [
                {
                    "SecurityGroupRules": [
                        {
                            "GroupId": "sg-1",
                            "SecurityGroupRuleId": "sgr-1",
                            "IsEgress": False,
                            "IpProtocol": "tcp",
                            "FromPort": 22,
                            "ToPort": 22,
                            "CidrIpv4": "0.0.0.0/0",
                        }
                    ]
                }
            ],
            "describe_volumes": [
                {
                    "Volumes": [
                        {
                            "VolumeId": "vol-1",
                            "Encrypted": False,
                            "State": "in-use",
                            "Size": 20,
                        }
                    ]
                }
            ],
        }
        return Pages(pages[operation])


def test_stage4_ec2_discovery_metadata() -> None:
    assets = EC2DiscoveryService().discover(
        lambda _service, _region: Stage4EC2Client(), ["us-east-1"], "123456789012"
    )
    assert {item.asset_type for item in assets} == {
        AssetType.EC2_INSTANCE,
        AssetType.EC2_SECURITY_GROUP,
        AssetType.EBS_VOLUME,
    }
    instance = next(item for item in assets if item.asset_type == AssetType.EC2_INSTANCE)
    assert instance.metadata["has_public_ip"] is True
    assert instance.metadata["metadata_options"]["http_tokens"] == "optional"
    volume = next(item for item in assets if item.asset_type == AssetType.EBS_VOLUME)
    assert volume.metadata["encrypted"] is False


class Stage4S3Client:
    def get_paginator(self, _operation: str) -> Pages:
        return Pages([{"Buckets": [{"Name": "inventory"}]}])

    def get_bucket_location(self, **_kwargs: Any) -> dict[str, Any]:
        return {"LocationConstraint": None}

    def get_bucket_tagging(self, **_kwargs: Any) -> dict[str, Any]:
        return {"TagSet": [{"Key": "Environment", "Value": "test"}]}

    def get_public_access_block(self, **_kwargs: Any) -> dict[str, Any]:
        return {
            "PublicAccessBlockConfiguration": {
                "BlockPublicAcls": True,
                "IgnorePublicAcls": True,
                "BlockPublicPolicy": True,
                "RestrictPublicBuckets": True,
            }
        }

    def get_bucket_acl(self, **_kwargs: Any) -> dict[str, Any]:
        return {"Grants": []}

    def get_bucket_policy_status(self, **_kwargs: Any) -> dict[str, Any]:
        return {"PolicyStatus": {"IsPublic": False}}

    def get_bucket_encryption(self, **_kwargs: Any) -> dict[str, Any]:
        return {"ServerSideEncryptionConfiguration": [{"Rules": []}]}

    def get_bucket_versioning(self, **_kwargs: Any) -> dict[str, Any]:
        return {"Status": "Enabled"}

    def get_bucket_logging(self, **_kwargs: Any) -> dict[str, Any]:
        return {"LoggingEnabled": {"TargetBucket": "logs"}}

    def get_bucket_policy(self, **_kwargs: Any) -> dict[str, Any]:
        return {
            "Policy": (
                '{"Statement":{"Effect":"Deny","Action":"s3:*","Resource":"*",'
                '"Condition":{"Bool":{"aws:SecureTransport":"false"}}}}'
            )
        }


def test_stage4_s3_discovery_metadata() -> None:
    item = S3DiscoveryService().discover(
        lambda _service, _region: Stage4S3Client(), [], "123456789012"
    )[0]
    assert item.region == "us-east-1"
    assert item.metadata["public_access_block_complete"] is True
    assert item.metadata["default_encryption_enabled"] is True
    assert item.metadata["versioning_enabled"] is True
    assert item.metadata["logging_enabled"] is True
    assert item.metadata["policy_document"]["Statement"]["Effect"] == "Deny"


class Stage4IAMClient:
    def get_paginator(self, operation: str) -> Pages:
        pages: dict[str, list[dict[str, Any]]] = {
            "list_users": [
                {
                    "Users": [
                        {
                            "UserId": "U1",
                            "UserName": "alice",
                            "Arn": "arn:aws:iam::123456789012:user/alice",
                        }
                    ]
                }
            ],
            "list_roles": [
                {
                    "Roles": [
                        {
                            "RoleId": "R1",
                            "RoleName": "reader",
                            "Arn": "arn:aws:iam::123456789012:role/reader",
                            "MaxSessionDuration": 3600,
                        }
                    ]
                }
            ],
            "list_groups": [
                {
                    "Groups": [
                        {
                            "GroupId": "G1",
                            "GroupName": "team",
                            "Arn": "arn:aws:iam::123456789012:group/team",
                        }
                    ]
                }
            ],
            "list_policies": [
                {
                    "Policies": [
                        {
                            "PolicyId": "P1",
                            "PolicyName": "local",
                            "Arn": "arn:aws:iam::123456789012:policy/local",
                            "AttachmentCount": 1,
                        }
                    ]
                }
            ],
        }
        return Pages(pages[operation])

    def can_paginate(self, operation: str) -> bool:
        del operation
        return False

    def list_user_tags(self, **_kwargs: Any) -> dict[str, Any]:
        return {"Tags": []}

    list_role_tags = list_user_tags
    list_group_tags = list_user_tags
    list_policy_tags = list_user_tags

    def list_attached_user_policies(self, **_kwargs: Any) -> dict[str, Any]:
        return {"AttachedPolicies": [{"PolicyArn": "arn:aws:iam::aws:policy/AdministratorAccess"}]}

    list_attached_role_policies = list_attached_user_policies
    list_attached_group_policies = list_attached_user_policies

    def list_user_policies(self, **_kwargs: Any) -> dict[str, Any]:
        return {"PolicyNames": ["inline"]}

    list_role_policies = list_user_policies
    list_group_policies = list_user_policies

    def get_user_policy(self, **_kwargs: Any) -> dict[str, Any]:
        return {
            "PolicyDocument": {"Statement": {"Effect": "Allow", "Action": "*", "Resource": "*"}}
        }

    get_role_policy = get_user_policy
    get_group_policy = get_user_policy

    def get_login_profile(self, **_kwargs: Any) -> dict[str, Any]:
        return {"LoginProfile": {}}

    def list_mfa_devices(self, **_kwargs: Any) -> dict[str, Any]:
        return {"MFADevices": []}

    def list_access_keys(self, **_kwargs: Any) -> dict[str, Any]:
        return {
            "AccessKeyMetadata": [
                {
                    "Status": "Active",
                    "CreateDate": datetime.now(UTC) - timedelta(days=120),
                }
            ]
        }


def test_stage4_iam_discovery_metadata() -> None:
    items = IAMDiscoveryService().discover(
        lambda _service, _region: Stage4IAMClient(), [], "123456789012"
    )
    assert len(items) == 4
    user = next(item for item in items if item.asset_type == AssetType.IAM_USER)
    assert user.metadata["console_access"] is True
    assert user.metadata["mfa_enabled"] is False
    assert user.metadata["active_key_created_at"]
    assert user.metadata["inline_policy_documents"][0]["Statement"]["Resource"] == "*"
    assert user.metadata["attached_policy_arns"][0].endswith("AdministratorAccess")


class Stage4RDSClient:
    def get_paginator(self, _operation: str) -> Pages:
        return Pages(
            [
                {
                    "DBInstances": [
                        {
                            "DBInstanceIdentifier": "db-1",
                            "DBInstanceArn": "arn:aws:rds:us-east-1:123456789012:db:db-1",
                            "DBInstanceStatus": "available",
                            "PubliclyAccessible": True,
                            "StorageEncrypted": False,
                            "BackupRetentionPeriod": 1,
                            "AutoMinorVersionUpgrade": False,
                            "DeletionProtection": False,
                        }
                    ]
                }
            ]
        )

    def list_tags_for_resource(self, **_kwargs: Any) -> dict[str, Any]:
        return {"TagList": []}


class Stage4CloudWatchClient:
    def get_paginator(self, operation: str) -> Pages:
        if operation == "describe_alarms":
            return Pages(
                [
                    {
                        "MetricAlarms": [
                            {
                                "AlarmName": "high-cpu",
                                "ActionsEnabled": False,
                                "StateValue": "OK",
                            }
                        ]
                    }
                ]
            )
        return Pages(
            [
                {
                    "logGroups": [
                        {
                            "logGroupName": "/cloudops/app",
                            "retentionInDays": None,
                        }
                    ]
                }
            ]
        )

    def describe_metric_filters(self, **_kwargs: Any) -> dict[str, Any]:
        return {"metricFilters": [{}]}

    def describe_subscription_filters(self, **_kwargs: Any) -> dict[str, Any]:
        return {"subscriptionFilters": []}


class Stage4CloudTrailClient:
    def describe_trails(self, **_kwargs: Any) -> dict[str, Any]:
        return {
            "trailList": [
                {
                    "Name": "organization",
                    "TrailARN": "arn:aws:cloudtrail:us-east-1:123456789012:trail/organization",
                    "HomeRegion": "us-east-1",
                    "IsMultiRegionTrail": False,
                    "IncludeGlobalServiceEvents": False,
                    "LogFileValidationEnabled": False,
                }
            ]
        }

    def get_trail_status(self, **_kwargs: Any) -> dict[str, Any]:
        return {"IsLogging": False, "LatestDeliveryError": "sanitized upstream state"}

    def get_event_selectors(self, **_kwargs: Any) -> dict[str, Any]:
        return {"EventSelectors": [{}]}

    def get_insight_selectors(self, **_kwargs: Any) -> dict[str, Any]:
        return {"InsightSelectors": []}


def test_stage4_rds_cloudwatch_and_cloudtrail_discovery() -> None:
    rds = RDSDiscoveryService().discover(
        lambda _service, _region: Stage4RDSClient(), ["us-east-1"], "123456789012"
    )[0]
    assert rds.metadata["publicly_accessible"] is True
    assert rds.metadata["storage_encrypted"] is False

    clients = {
        "cloudwatch": Stage4CloudWatchClient(),
        "logs": Stage4CloudWatchClient(),
    }
    cloudwatch = CloudWatchDiscoveryService().discover(
        lambda service, _region: clients[service], ["us-east-1"], "123456789012"
    )
    assert {item.asset_type for item in cloudwatch} == {
        AssetType.CLOUDWATCH_ALARM,
        AssetType.CLOUDWATCH_LOG_GROUP,
    }
    assert cloudwatch[1].metadata["metric_filter_count"] == 1

    trail = CloudTrailDiscoveryService().discover(
        lambda _service, _region: Stage4CloudTrailClient(),
        ["us-east-1"],
        "123456789012",
    )[0]
    assert trail.status == "stopped"
    assert trail.metadata["delivery_failed"] is True


@pytest.mark.parametrize(
    ("asset_type", "metadata", "rule_keys"),
    [
        (
            AssetType.EC2_SECURITY_GROUP,
            {
                "ip_permissions": [
                    {
                        "IpProtocol": "-1",
                        "IpRanges": [{"CidrIp": "0.0.0.0/0"}],
                    }
                ]
            },
            ["EC2_SG_RDP_OPEN_TO_WORLD", "EC2_SG_ALL_TRAFFIC_OPEN_TO_WORLD"],
        ),
        (
            AssetType.EC2_INSTANCE,
            {"metadata_options": {"http_tokens": "optional"}, "has_public_ip": True},
            ["EC2_INSTANCE_IMDSV1_ALLOWED", "EC2_INSTANCE_PUBLIC_IP"],
        ),
        (AssetType.EBS_VOLUME, {"encrypted": False}, ["EBS_VOLUME_UNENCRYPTED"]),
        (
            AssetType.S3_BUCKET,
            {
                "public_access_signals": {"public_acl": True},
                "public_access_block_complete": False,
                "default_encryption_enabled": False,
                "versioning_enabled": False,
                "policy_document": None,
                "logging_enabled": False,
            },
            [
                "S3_BUCKET_PUBLIC_ACCESS_CONFIRMED",
                "S3_BUCKET_PUBLIC_ACCESS_BLOCK_INCOMPLETE",
                "S3_BUCKET_DEFAULT_ENCRYPTION_MISSING",
                "S3_BUCKET_VERSIONING_DISABLED",
                "S3_BUCKET_HTTPS_ONLY_POLICY_MISSING",
                "S3_BUCKET_LOGGING_DISABLED",
            ],
        ),
        (
            AssetType.IAM_USER,
            {
                "console_access": True,
                "mfa_enabled": False,
                "active_key_created_at": [(datetime.now(UTC) - timedelta(days=120)).isoformat()],
                "attached_policy_arns": ["arn:aws:iam::aws:policy/AdministratorAccess"],
                "inline_policy_documents": [
                    {
                        "Statement": {
                            "Effect": "Allow",
                            "Action": "*",
                            "Resource": "*",
                        }
                    }
                ],
            },
            [
                "IAM_USER_CONSOLE_ACCESS_WITHOUT_MFA",
                "IAM_USER_ACCESS_KEY_TOO_OLD",
                "IAM_ADMINISTRATOR_ACCESS_ATTACHED",
                "IAM_INLINE_POLICY_ALLOW_ALL",
            ],
        ),
        (
            AssetType.RDS_INSTANCE,
            {
                "publicly_accessible": True,
                "storage_encrypted": False,
                "backup_retention_period": 1,
                "auto_minor_version_upgrade": False,
                "deletion_protection": False,
            },
            [
                "RDS_INSTANCE_PUBLICLY_ACCESSIBLE",
                "RDS_STORAGE_NOT_ENCRYPTED",
                "RDS_BACKUP_RETENTION_INSUFFICIENT",
                "RDS_AUTO_MINOR_VERSION_UPGRADE_DISABLED",
                "RDS_DELETION_PROTECTION_DISABLED",
            ],
        ),
        (
            AssetType.CLOUDWATCH_LOG_GROUP,
            {"retention_days": None, "kms_encrypted": False},
            [
                "CLOUDWATCH_LOG_GROUP_RETENTION_NOT_CONFIGURED",
                "CLOUDWATCH_LOG_GROUP_NOT_KMS_ENCRYPTED",
            ],
        ),
        (
            AssetType.CLOUDWATCH_ALARM,
            {"actions_enabled": False},
            ["CLOUDWATCH_ALARM_ACTIONS_DISABLED"],
        ),
        (
            AssetType.CLOUDTRAIL_TRAIL,
            {
                "is_logging": False,
                "is_multi_region": False,
                "include_global_service_events": False,
                "log_file_validation_enabled": False,
                "kms_encrypted": False,
                "cloudwatch_integration": False,
                "delivery_failed": True,
            },
            [
                "CLOUDTRAIL_LOGGING_DISABLED",
                "CLOUDTRAIL_NOT_MULTI_REGION",
                "CLOUDTRAIL_GLOBAL_EVENTS_DISABLED",
                "CLOUDTRAIL_LOG_VALIDATION_DISABLED",
                "CLOUDTRAIL_NOT_KMS_ENCRYPTED",
                "CLOUDTRAIL_CLOUDWATCH_INTEGRATION_MISSING",
                "CLOUDTRAIL_DELIVERY_FAILURE",
            ],
        ),
    ],
)
def test_initial_rule_pack_failure_matrix(
    asset_type: AssetType, metadata: dict[str, object], rule_keys: list[str]
) -> None:
    item = asset(asset_type, metadata)
    context = RuleContext((item,))
    for key in rule_keys:
        rule = default_registry.get(key)
        assert rule is not None
        assert rule.evaluate(item, context).status == RuleResultStatus.FAILED
