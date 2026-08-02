from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import pytest
from botocore.exceptions import ClientError  # type: ignore[import-untyped]

from app.core.config import get_settings
from app.models import Asset, AWSAccount, Finding, RemediationRequest
from app.models.enums import (
    AssetType,
    FindingSeverity,
    RemediationExecutionMode,
)
from app.services.aws_remediation_executor import (
    S3_PUBLIC_ACCESS_BLOCK_KEYS,
    AWSRemediationExecutor,
)
from app.services.remediation_executor import (
    RemediationExecutionContext,
    RemediationExecutionOutcome,
)

TAGS = [
    {"Key": "CloudOpsLab", "Value": "true"},
    {"Key": "Environment", "Value": "cloudops-test"},
    {"Key": "AllowCloudOpsRemediation", "Value": "true"},
]


def _context(
    asset: Asset,
    rule_key: str,
    action_key: str,
) -> RemediationExecutionContext:
    organization_id = asset.organization_id
    account = AWSAccount(
        id=asset.aws_account_id,
        organization_id=organization_id,
        name="Synthetic sandbox",
        account_id="111122223333",
        external_id="synthetic-discovery-external-id",
        remediation_role_arn="arn:aws:iam::111122223333:role/CloudOpsRemediation",
        remediation_external_id="synthetic-remediation-external-id",
        sandbox_approved=True,
        sandbox_approved_at=datetime.now(UTC),
        sandbox_approved_by_user_id=uuid.uuid4(),
        created_by_user_id=uuid.uuid4(),
    )
    finding = Finding(
        id=uuid.uuid4(),
        organization_id=organization_id,
        aws_account_id=asset.aws_account_id,
        asset_id=asset.id,
        rule_key=rule_key,
        rule_version=1,
        severity=FindingSeverity.CRITICAL,
        category="network",
        evidence_json={},
    )
    request = RemediationRequest(
        organization_id=organization_id,
        aws_account_id=asset.aws_account_id,
        finding_id=finding.id,
        rule_key=rule_key,
        rule_version=1,
        action_key=action_key,
        action_version=1,
        idempotency_key=uuid.uuid4().hex,
        execution_mode=RemediationExecutionMode.LIVE_AWS,
        executor_key="aws",
        target_region=asset.region,
        target_resource_arn=asset.arn,
        title="Synthetic live request",
        summary="Synthetic test only",
        request_snapshot_hash="a" * 64,
        dry_run=False,
    )
    return RemediationExecutionContext(account, asset, finding, request)


class S3Client:
    def __init__(
        self,
        before: dict[str, bool] | None,
        *,
        tags: list[dict[str, str]] = TAGS,
        verify: dict[str, bool] | None = None,
    ) -> None:
        self.before = before
        self.tags = tags
        self.verify = verify
        self.writes: list[dict[str, object]] = []
        self.reads = 0

    def get_bucket_tagging(self, **_kwargs: object) -> dict[str, object]:
        return {"TagSet": self.tags}

    def get_public_access_block(self, **_kwargs: object) -> dict[str, object]:
        self.reads += 1
        value = self.before if self.reads == 1 else (self.verify or self.writes[-1])
        return {
            "PublicAccessBlockConfiguration": value,
            "ResponseMetadata": {"RequestId": f"read-{self.reads}"},
        }

    def put_public_access_block(self, **kwargs: object) -> dict[str, object]:
        value = kwargs["PublicAccessBlockConfiguration"]
        assert isinstance(value, dict)
        self.writes.append(value)
        return {"ResponseMetadata": {"RequestId": "write-1"}}


def _s3_asset(before: dict[str, bool] | None) -> Asset:
    return Asset(
        id=uuid.uuid4(),
        organization_id=uuid.uuid4(),
        aws_account_id=uuid.uuid4(),
        asset_type=AssetType.S3_BUCKET,
        resource_id="cloudops-lab-evidence",
        arn="arn:aws:s3:::cloudops-lab-evidence",
        name="cloudops-lab-evidence",
        region="ap-south-1",
        tags={item["Key"]: item["Value"] for item in TAGS},
        metadata_json={"public_access_block": before},
    )


@pytest.mark.parametrize(
    "before",
    [
        None,
        {
            "BlockPublicAcls": False,
            "IgnorePublicAcls": True,
            "BlockPublicPolicy": False,
            "RestrictPublicBuckets": True,
        },
    ],
)
def test_s3_executor_preserves_exact_rollback_and_verifies(before: dict[str, bool] | None) -> None:
    asset = _s3_asset(before)
    client = S3Client(before)
    result = AWSRemediationExecutor(get_settings(), client_factory=lambda *_args: client).execute(
        action_key="s3.enable_public_access_block",
        finding_id=uuid.uuid4(),
        snapshot_hash="a" * 64,
        dry_run=False,
        context=_context(
            asset,
            "S3_BUCKET_PUBLIC_ACCESS_BLOCK_INCOMPLETE",
            "s3.enable_public_access_block",
        ),
    )

    assert result.outcome == RemediationExecutionOutcome.SUCCESS
    assert result.rollback_state == {
        "public_access_block": before,
        "configuration_was_absent": before is None,
    }
    assert client.writes == [
        {
            "BlockPublicAcls": True,
            "IgnorePublicAcls": True,
            "BlockPublicPolicy": True,
            "RestrictPublicBuckets": True,
        }
    ]
    assert result.aws_request_ids == {
        "read_before": "read-1",
        "mutate": "write-1",
        "verify": "read-2",
    }


@pytest.mark.parametrize(
    ("name", "tags", "error"),
    [
        ("not-approved", TAGS, "s3_bucket_prefix_not_allowed"),
        ("cloudops-lab-evidence", [], "required_remediation_tags_missing"),
    ],
)
def test_s3_executor_refuses_unapproved_targets(
    name: str, tags: list[dict[str, str]], error: str
) -> None:
    before = {
        key: False
        for key in (
            "BlockPublicAcls",
            "IgnorePublicAcls",
            "BlockPublicPolicy",
            "RestrictPublicBuckets",
        )
    }
    asset = _s3_asset(before)
    asset.resource_id = name
    client = S3Client(before, tags=tags)
    result = AWSRemediationExecutor(get_settings(), client_factory=lambda *_args: client).execute(
        action_key="s3.enable_public_access_block",
        finding_id=uuid.uuid4(),
        snapshot_hash="a" * 64,
        dry_run=False,
        context=_context(
            asset, "S3_BUCKET_PUBLIC_ACCESS_BLOCK_INCOMPLETE", "s3.enable_public_access_block"
        ),
    )
    assert result.outcome == RemediationExecutionOutcome.FAILURE
    assert result.sanitized_error == error
    assert client.writes == []


def test_s3_executor_rejects_drift_and_verification_failure() -> None:
    approved = {key: False for key in S3_PUBLIC_ACCESS_BLOCK_KEYS}
    drifted = {**approved, "BlockPublicAcls": True}
    asset = _s3_asset(approved)

    drift_client = S3Client(drifted)
    drift = AWSRemediationExecutor(
        get_settings(), client_factory=lambda *_args: drift_client
    ).execute(
        action_key="s3.enable_public_access_block",
        finding_id=uuid.uuid4(),
        snapshot_hash="a" * 64,
        dry_run=False,
        context=_context(
            asset,
            "S3_BUCKET_PUBLIC_ACCESS_BLOCK_INCOMPLETE",
            "s3.enable_public_access_block",
        ),
    )
    assert drift.sanitized_error == "remediation_precondition_drift"
    assert drift_client.writes == []

    verify_client = S3Client(approved, verify=approved)
    verification = AWSRemediationExecutor(
        get_settings(), client_factory=lambda *_args: verify_client
    ).execute(
        action_key="s3.enable_public_access_block",
        finding_id=uuid.uuid4(),
        snapshot_hash="a" * 64,
        dry_run=False,
        context=_context(
            asset,
            "S3_BUCKET_PUBLIC_ACCESS_BLOCK_INCOMPLETE",
            "s3.enable_public_access_block",
        ),
    )
    assert verification.sanitized_error == "remediation_verification_failed"


def test_aws_provider_errors_are_sanitized() -> None:
    class DeniedS3(S3Client):
        def get_bucket_tagging(self, **_kwargs: object) -> dict[str, object]:
            raise ClientError(
                {
                    "Error": {
                        "Code": "AccessDenied",
                        "Message": "synthetic-sensitive-provider-detail",
                    }
                },
                "GetBucketTagging",
            )

    before = {key: False for key in S3_PUBLIC_ACCESS_BLOCK_KEYS}
    result = AWSRemediationExecutor(
        get_settings(), client_factory=lambda *_args: DeniedS3(before)
    ).execute(
        action_key="s3.enable_public_access_block",
        finding_id=uuid.uuid4(),
        snapshot_hash="a" * 64,
        dry_run=False,
        context=_context(
            _s3_asset(before),
            "S3_BUCKET_PUBLIC_ACCESS_BLOCK_INCOMPLETE",
            "s3.enable_public_access_block",
        ),
    )
    assert result.sanitized_error == "aws_accessdenied"
    assert "synthetic-sensitive-provider-detail" not in repr(result)


class RulePages:
    def __init__(self, client: EC2Client) -> None:
        self.client = client

    def paginate(self, **_kwargs: object) -> list[dict[str, object]]:
        return [{"SecurityGroupRules": list(self.client.rules)}]


class EC2Client:
    def __init__(self, rules: list[dict[str, Any]]) -> None:
        self.rules = rules
        self.revoked: list[str] = []

    def describe_security_groups(self, **_kwargs: object) -> dict[str, object]:
        return {
            "SecurityGroups": [{"GroupId": "sg-lab", "VpcId": "vpc-lab", "Tags": TAGS}],
            "ResponseMetadata": {"RequestId": "describe-group"},
        }

    def get_paginator(self, operation: str) -> RulePages:
        assert operation == "describe_security_group_rules"
        return RulePages(self)

    def revoke_security_group_ingress(self, **kwargs: object) -> dict[str, object]:
        rule_ids = kwargs["SecurityGroupRuleIds"]
        assert isinstance(rule_ids, list) and len(rule_ids) == 1
        self.revoked.append(str(rule_ids[0]))
        self.rules = [rule for rule in self.rules if rule["SecurityGroupRuleId"] != rule_ids[0]]
        return {"ResponseMetadata": {"RequestId": "revoke-rule"}}


def _ec2_asset(rules: list[dict[str, Any]]) -> Asset:
    return Asset(
        id=uuid.uuid4(),
        organization_id=uuid.uuid4(),
        aws_account_id=uuid.uuid4(),
        asset_type=AssetType.EC2_SECURITY_GROUP,
        resource_id="sg-lab",
        arn="arn:aws:ec2:ap-south-1:111122223333:security-group/sg-lab",
        name="sg-lab",
        region="ap-south-1",
        tags={item["Key"]: item["Value"] for item in TAGS},
        metadata_json={"vpc_id": "vpc-lab", "security_group_rules": rules},
    )


@pytest.mark.parametrize(
    ("rule_key", "rule"),
    [
        (
            "EC2_SG_SSH_OPEN_TO_WORLD",
            {
                "SecurityGroupRuleId": "sgr-ssh",
                "GroupId": "sg-lab",
                "IsEgress": False,
                "IpProtocol": "tcp",
                "FromPort": 22,
                "ToPort": 22,
                "CidrIpv4": "0.0.0.0/0",
            },
        ),
        (
            "EC2_SG_RDP_OPEN_TO_WORLD",
            {
                "SecurityGroupRuleId": "sgr-rdp-v6",
                "GroupId": "sg-lab",
                "IsEgress": False,
                "IpProtocol": "tcp",
                "FromPort": 3389,
                "ToPort": 3389,
                "CidrIpv6": "::/0",
            },
        ),
        (
            "EC2_SG_ALL_TRAFFIC_OPEN_TO_WORLD",
            {
                "SecurityGroupRuleId": "sgr-all",
                "GroupId": "sg-lab",
                "IsEgress": False,
                "IpProtocol": "-1",
                "CidrIpv4": "0.0.0.0/0",
            },
        ),
    ],
)
def test_ec2_executor_revokes_only_exact_rule(rule_key: str, rule: dict[str, Any]) -> None:
    unrelated = {
        "SecurityGroupRuleId": "sgr-private",
        "GroupId": "sg-lab",
        "IsEgress": False,
        "IpProtocol": "tcp",
        "FromPort": 443,
        "ToPort": 443,
        "CidrIpv4": "10.0.0.0/8",
    }
    rules = [rule, unrelated]
    asset = _ec2_asset(rules)
    client = EC2Client(list(rules))
    result = AWSRemediationExecutor(get_settings(), client_factory=lambda *_args: client).execute(
        action_key="ec2.revoke_approved_public_ingress",
        finding_id=uuid.uuid4(),
        snapshot_hash="a" * 64,
        dry_run=False,
        context=_context(asset, rule_key, "ec2.revoke_approved_public_ingress"),
    )
    assert result.outcome == RemediationExecutionOutcome.SUCCESS
    assert client.revoked == [rule["SecurityGroupRuleId"]]
    assert client.rules == [unrelated]
    assert result.rollback_state == {"security_group_rule": rule}


def test_ec2_executor_rejects_egress_and_drift() -> None:
    rule = {
        "SecurityGroupRuleId": "sgr-egress",
        "GroupId": "sg-lab",
        "IsEgress": True,
        "IpProtocol": "tcp",
        "FromPort": 22,
        "ToPort": 22,
        "CidrIpv4": "0.0.0.0/0",
    }
    asset = _ec2_asset([rule])
    client = EC2Client(list([rule]))
    result = AWSRemediationExecutor(get_settings(), client_factory=lambda *_args: client).execute(
        action_key="ec2.revoke_approved_public_ingress",
        finding_id=uuid.uuid4(),
        snapshot_hash="a" * 64,
        dry_run=False,
        context=_context(asset, "EC2_SG_SSH_OPEN_TO_WORLD", "ec2.revoke_approved_public_ingress"),
    )
    assert result.outcome == RemediationExecutionOutcome.FAILURE
    assert result.sanitized_error == "security_group_rule_not_unambiguous"
    assert client.revoked == []


def test_ec2_executor_rejects_live_rule_drift() -> None:
    approved = {
        "SecurityGroupRuleId": "sgr-ssh",
        "GroupId": "sg-lab",
        "IsEgress": False,
        "IpProtocol": "tcp",
        "FromPort": 22,
        "ToPort": 22,
        "CidrIpv4": "0.0.0.0/0",
    }
    live = {**approved, "CidrIpv4": "10.0.0.0/8"}
    asset = _ec2_asset([approved])
    client = EC2Client([live])

    result = AWSRemediationExecutor(
        get_settings(), client_factory=lambda *_args: client
    ).execute(
        action_key="ec2.revoke_approved_public_ingress",
        finding_id=uuid.uuid4(),
        snapshot_hash="a" * 64,
        dry_run=False,
        context=_context(
            asset,
            "EC2_SG_SSH_OPEN_TO_WORLD",
            "ec2.revoke_approved_public_ingress",
        ),
    )

    assert result.sanitized_error == "remediation_precondition_drift"
    assert client.revoked == []
