from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import pytest
from botocore.exceptions import ClientError  # type: ignore[import-untyped]

from app.models import Asset
from app.models.enums import AssetType, FindingSeverity, RuleResultStatus
from app.security_rules import default_registry
from app.security_rules.base import RuleContext
from app.services.discovery import (
    EC2DiscoveryService,
    S3DiscoveryService,
    safe_aws_error,
)


class Pages:
    def __init__(self, pages: list[dict[str, Any]]) -> None:
        self.pages = pages

    def paginate(self, **_kwargs: object) -> list[dict[str, Any]]:
        return self.pages


class S3Client:
    def __init__(
        self,
        block: dict[str, bool] | None = None,
        error: ClientError | None = None,
    ) -> None:
        self.block = block
        self.error = error

    def get_paginator(self, operation: str) -> Pages:
        assert operation == "list_buckets"
        return Pages([{"Buckets": [{"Name": "evidence-bucket"}]}])

    def get_bucket_location(self, **_kwargs: object) -> dict[str, None]:
        return {"LocationConstraint": None}

    def get_bucket_tagging(self, **_kwargs: object) -> dict[str, list[object]]:
        return {"TagSet": []}

    def get_public_access_block(self, **_kwargs: object) -> dict[str, object]:
        if self.error is not None:
            raise self.error
        assert self.block is not None
        return {"PublicAccessBlockConfiguration": self.block}


def s3_asset(metadata: dict[str, object]) -> Asset:
    now = datetime.now(UTC)
    return Asset(
        id=uuid.uuid4(),
        organization_id=uuid.uuid4(),
        aws_account_id=uuid.uuid4(),
        asset_type=AssetType.S3_BUCKET,
        resource_id="evidence-bucket",
        name="evidence-bucket",
        region="us-east-1",
        metadata_json=metadata,
        tags={},
        first_seen_at=now,
        last_seen_at=now,
    )


@pytest.mark.parametrize(
    ("block", "complete"),
    [
        (
            {
                "RestrictPublicBuckets": True,
                "BlockPublicPolicy": True,
                "IgnorePublicAcls": True,
                "BlockPublicAcls": True,
            },
            True,
        ),
        (
            {
                "BlockPublicAcls": True,
                "IgnorePublicAcls": True,
                "BlockPublicPolicy": False,
                "RestrictPublicBuckets": False,
            },
            False,
        ),
        (
            {
                "BlockPublicAcls": False,
                "IgnorePublicAcls": False,
                "BlockPublicPolicy": False,
                "RestrictPublicBuckets": False,
            },
            False,
        ),
    ],
)
def test_s3_preserves_exact_public_access_block_evidence(
    block: dict[str, bool], complete: bool
) -> None:
    item = S3DiscoveryService().discover(
        lambda *_args: S3Client(block), [], "123456789012"
    )[0]

    assert item.metadata["public_access_block"] == block
    assert list(item.metadata["public_access_block"]) == [
        "BlockPublicAcls",
        "IgnorePublicAcls",
        "BlockPublicPolicy",
        "RestrictPublicBuckets",
    ]
    assert item.metadata["public_access_block_complete"] is complete


def test_s3_missing_public_access_block_is_explicit() -> None:
    error = ClientError(
        {
            "Error": {
                "Code": "NoSuchPublicAccessBlockConfiguration",
                "Message": "provider details must not be persisted",
            }
        },
        "GetPublicAccessBlock",
    )
    item = S3DiscoveryService().discover(
        lambda *_args: S3Client(error=error), [], "123456789012"
    )[0]

    assert item.metadata["public_access_block"] is None
    assert item.metadata["public_access_block_complete"] is False
    assert "provider details" not in str(item.metadata)


def test_s3_exact_evidence_excludes_unrequested_provider_fields() -> None:
    block = {
        "BlockPublicAcls": True,
        "IgnorePublicAcls": True,
        "BlockPublicPolicy": True,
        "RestrictPublicBuckets": True,
        "SessionToken": True,
    }
    item = S3DiscoveryService().discover(
        lambda *_args: S3Client(block), [], "123456789012"
    )[0]

    assert "SessionToken" not in item.metadata["public_access_block"]


def test_s3_public_access_block_rule_result_is_unchanged_by_exact_evidence() -> None:
    rule = default_registry.get("S3_BUCKET_PUBLIC_ACCESS_BLOCK_INCOMPLETE")
    assert rule is not None
    assert rule.key == "S3_BUCKET_PUBLIC_ACCESS_BLOCK_INCOMPLETE"
    assert rule.severity == FindingSeverity.HIGH
    assert rule.category == "exposure"
    previous = s3_asset({"public_access_block_complete": False})
    extended = s3_asset(
        {
            "public_access_block_complete": False,
            "public_access_block": {
                "BlockPublicAcls": True,
                "IgnorePublicAcls": True,
                "BlockPublicPolicy": False,
                "RestrictPublicBuckets": False,
            },
        }
    )

    previous_result = rule.evaluate(previous, RuleContext((previous,)))
    extended_result = rule.evaluate(extended, RuleContext((extended,)))
    assert previous_result == extended_result
    assert extended_result.status == RuleResultStatus.FAILED
    assert extended_result.evidence == {"public_access_block_complete": False}


def test_s3_unexpected_provider_error_uses_existing_sanitizer() -> None:
    error = ClientError(
        {
            "Error": {
                "Code": "AccessDenied",
                "Message": "sensitive provider request internals",
            }
        },
        "GetPublicAccessBlock",
    )
    with pytest.raises(ClientError) as caught:
        S3DiscoveryService().discover(
            lambda *_args: S3Client(error=error), [], "123456789012"
        )

    sanitized = safe_aws_error(caught.value)
    assert sanitized == "accessdenied"
    assert "sensitive" not in sanitized


class RulePages:
    def __init__(self, client: EC2Client) -> None:
        self.client = client

    def paginate(self, **kwargs: object) -> list[dict[str, Any]]:
        filters = kwargs.get("Filters")
        assert isinstance(filters, list)
        assert len(filters) == 1
        group_filter = filters[0]
        assert isinstance(group_filter, dict)
        assert group_filter.get("Name") == "group-id"
        values = group_filter.get("Values")
        assert isinstance(values, list) and len(values) == 1
        group_id = str(values[0])
        self.client.rule_requests.append(group_id)
        if self.client.rule_error is not None:
            raise self.client.rule_error
        return self.client.rule_pages[group_id]


class EC2Client:
    def __init__(
        self,
        groups: list[dict[str, Any]],
        rule_pages: dict[str, list[dict[str, Any]]],
        *,
        rule_error: ClientError | None = None,
    ) -> None:
        self.groups = groups
        self.rule_pages = rule_pages
        self.rule_error = rule_error
        self.rule_requests: list[str] = []

    def get_paginator(self, operation: str) -> Pages | RulePages:
        if operation == "describe_instances":
            return Pages([{"Reservations": []}])
        if operation == "describe_security_groups":
            return Pages([{"SecurityGroups": self.groups}])
        if operation == "describe_security_group_rules":
            return RulePages(self)
        if operation == "describe_volumes":
            return Pages([{"Volumes": []}])
        raise AssertionError(operation)


def ec2_rule_fixture() -> tuple[list[dict[str, Any]], dict[str, list[dict[str, Any]]]]:
    groups: list[dict[str, Any]] = [
        {
            "GroupId": "sg-a",
            "GroupName": "alpha",
            "IpPermissions": [
                {
                    "IpProtocol": "tcp",
                    "FromPort": 22,
                    "ToPort": 22,
                    "IpRanges": [{"CidrIp": "0.0.0.0/0"}],
                },
                {
                    "IpProtocol": "tcp",
                    "FromPort": 3389,
                    "ToPort": 3389,
                    "Ipv6Ranges": [{"CidrIpv6": "::/0"}],
                },
                {
                    "IpProtocol": "-1",
                    "IpRanges": [{"CidrIp": "0.0.0.0/0"}],
                },
            ],
            "IpPermissionsEgress": [],
        },
        {
            "GroupId": "sg-b",
            "GroupName": "beta",
            "IpPermissions": [],
            "IpPermissionsEgress": [],
        },
    ]
    sg_b_rule: dict[str, Any] = {
        "GroupId": "sg-b",
        "SecurityGroupRuleId": "sgr-b-only",
        "IsEgress": False,
        "IpProtocol": "tcp",
        "FromPort": 443,
        "ToPort": 443,
        "CidrIpv4": "10.0.0.0/8",
    }
    pages: dict[str, list[dict[str, Any]]] = {
        "sg-a": [
            {
                "SecurityGroupRules": [
                    {
                        "GroupId": "sg-a",
                        "SecurityGroupRuleId": "sgr-ssh",
                        "IsEgress": False,
                        "IpProtocol": "tcp",
                        "FromPort": 22,
                        "ToPort": 22,
                        "CidrIpv4": "0.0.0.0/0",
                        "Description": "administration",
                        "RequestCredentials": "synthetic-value-that-must-not-persist",
                    },
                    {
                        "GroupId": "sg-a",
                        "SecurityGroupRuleId": "sgr-v6",
                        "IsEgress": False,
                        "IpProtocol": "tcp",
                        "FromPort": 443,
                        "ToPort": 443,
                        "CidrIpv6": "::/0",
                    },
                    sg_b_rule,
                ]
            },
            {
                "SecurityGroupRules": [
                    {
                        "GroupId": "sg-a",
                        "SecurityGroupRuleId": "sgr-rdp",
                        "IsEgress": False,
                        "IpProtocol": "tcp",
                        "FromPort": 3389,
                        "ToPort": 3389,
                        "CidrIpv4": "0.0.0.0/0",
                    },
                    {
                        "GroupId": "sg-a",
                        "SecurityGroupRuleId": "sgr-all",
                        "IsEgress": False,
                        "IpProtocol": "-1",
                        "CidrIpv4": "0.0.0.0/0",
                    },
                    {
                        "GroupId": "sg-a",
                        "SecurityGroupRuleId": "sgr-reference",
                        "IsEgress": False,
                        "IpProtocol": "tcp",
                        "FromPort": 5432,
                        "ToPort": 5432,
                        "ReferencedGroupInfo": {
                            "GroupId": "sg-database",
                            "UserId": "123456789012",
                        },
                    },
                    {
                        "GroupId": "sg-a",
                        "SecurityGroupRuleId": "sgr-prefix",
                        "IsEgress": False,
                        "IpProtocol": "tcp",
                        "FromPort": 443,
                        "ToPort": 443,
                        "PrefixListId": "pl-1234",
                    },
                    {
                        "GroupId": "sg-a",
                        "SecurityGroupRuleId": "sgr-egress",
                        "IsEgress": True,
                        "IpProtocol": "-1",
                        "CidrIpv4": "0.0.0.0/0",
                    },
                ]
            },
        ],
        "sg-b": [{"SecurityGroupRules": [sg_b_rule]}],
    }
    return groups, pages


def test_ec2_preserves_paginated_group_scoped_rule_evidence() -> None:
    groups, pages = ec2_rule_fixture()
    client = EC2Client(groups, pages)
    assets = EC2DiscoveryService().discover(
        lambda *_args: client, ["us-east-1"], "123456789012"
    )
    by_id = {item.resource_id: item for item in assets}

    assert client.rule_requests == ["sg-a", "sg-b"]
    alpha = by_id["sg-a"]
    rules = alpha.metadata["security_group_rules"]
    assert [rule["SecurityGroupRuleId"] for rule in rules] == sorted(
        [
            "sgr-ssh",
            "sgr-v6",
            "sgr-rdp",
            "sgr-all",
            "sgr-reference",
            "sgr-prefix",
            "sgr-egress",
        ]
    )
    assert all(rule["GroupId"] == "sg-a" for rule in rules)
    assert "RequestCredentials" not in str(rules)
    assert next(rule for rule in rules if rule["SecurityGroupRuleId"] == "sgr-ssh") == {
        "GroupId": "sg-a",
        "SecurityGroupRuleId": "sgr-ssh",
        "IsEgress": False,
        "IpProtocol": "tcp",
        "FromPort": 22,
        "ToPort": 22,
        "CidrIpv4": "0.0.0.0/0",
        "Description": "administration",
    }
    assert next(rule for rule in rules if rule["SecurityGroupRuleId"] == "sgr-v6")[
        "CidrIpv6"
    ] == "::/0"
    all_traffic = next(rule for rule in rules if rule["SecurityGroupRuleId"] == "sgr-all")
    assert "FromPort" not in all_traffic and "ToPort" not in all_traffic
    assert next(rule for rule in rules if rule["SecurityGroupRuleId"] == "sgr-reference")[
        "ReferencedGroupInfo"
    ] == {"GroupId": "sg-database", "UserId": "123456789012"}
    assert next(rule for rule in rules if rule["SecurityGroupRuleId"] == "sgr-prefix")[
        "PrefixListId"
    ] == "pl-1234"
    assert next(rule for rule in rules if rule["SecurityGroupRuleId"] == "sgr-egress")[
        "IsEgress"
    ] is True
    assert by_id["sg-b"].metadata["security_group_rules"] == [
        pages["sg-b"][0]["SecurityGroupRules"][0]
    ]
    assert alpha.metadata["ip_permissions"] == groups[0]["IpPermissions"]


@pytest.mark.parametrize(
    "rule_key",
    [
        "EC2_SG_SSH_OPEN_TO_WORLD",
        "EC2_SG_RDP_OPEN_TO_WORLD",
        "EC2_SG_ALL_TRAFFIC_OPEN_TO_WORLD",
    ],
)
def test_ec2_rule_results_are_unchanged_by_rule_id_evidence(rule_key: str) -> None:
    groups, pages = ec2_rule_fixture()
    legacy_metadata = {"ip_permissions": groups[0]["IpPermissions"]}
    extended_metadata = {
        **legacy_metadata,
        "security_group_rules": [
            rule
            for page in pages["sg-a"]
            for rule in page["SecurityGroupRules"]
            if rule["GroupId"] == "sg-a"
        ],
    }
    previous = ec2_asset(legacy_metadata)
    extended = ec2_asset(extended_metadata)
    rule = default_registry.get(rule_key)
    assert rule is not None
    assert rule.key == rule_key
    assert rule.severity == FindingSeverity.CRITICAL
    assert rule.category == "network"

    previous_result = rule.evaluate(previous, RuleContext((previous,)))
    extended_result = rule.evaluate(extended, RuleContext((extended,)))
    assert previous_result == extended_result
    assert extended_result.status == RuleResultStatus.FAILED


def ec2_asset(metadata: dict[str, object]) -> Asset:
    now = datetime.now(UTC)
    return Asset(
        id=uuid.uuid4(),
        organization_id=uuid.uuid4(),
        aws_account_id=uuid.uuid4(),
        asset_type=AssetType.EC2_SECURITY_GROUP,
        resource_id="sg-a",
        name="alpha",
        region="us-east-1",
        metadata_json=metadata,
        tags={},
        first_seen_at=now,
        last_seen_at=now,
    )


def test_ec2_rule_provider_error_uses_existing_sanitizer() -> None:
    groups, pages = ec2_rule_fixture()
    error = ClientError(
        {
            "Error": {
                "Code": "UnauthorizedOperation",
                "Message": "provider request details must not be persisted",
            }
        },
        "DescribeSecurityGroupRules",
    )
    with pytest.raises(ClientError) as caught:
        EC2DiscoveryService().discover(
            lambda *_args: EC2Client(groups, pages, rule_error=error),
            ["us-east-1"],
            "123456789012",
        )

    sanitized = safe_aws_error(caught.value)
    assert sanitized == "unauthorizedoperation"
    assert "provider request" not in sanitized
