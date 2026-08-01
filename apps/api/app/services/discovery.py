from __future__ import annotations

import json
import re
import uuid
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, ClassVar, Protocol

import boto3  # type: ignore[import-untyped]
from botocore.exceptions import BotoCoreError, ClientError  # type: ignore[import-untyped]
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.exceptions.errors import ConflictError, NotFoundError
from app.models import Asset, AWSAccount, DiscoveryJob, User
from app.models.enums import AssetType, AuditResult, AWSAccountStatus, DiscoveryJobStatus
from app.repositories.assets import AssetRepository, DiscoveryJobRepository
from app.security.rbac import Capability
from app.services.aws_credentials import (
    AWSConnectionFailure,
    TenantRoleCredentialProvider,
)
from app.services.common import now_utc, record_audit
from app.services.organizations import OrganizationService

ClientFactory = Callable[[str, str | None], Any]
S3_PUBLIC_ACCESS_BLOCK_KEYS = (
    "BlockPublicAcls",
    "IgnorePublicAcls",
    "BlockPublicPolicy",
    "RestrictPublicBuckets",
)
SECURITY_GROUP_RULE_FIELDS = (
    "GroupId",
    "SecurityGroupRuleId",
    "IsEgress",
    "IpProtocol",
    "FromPort",
    "ToPort",
    "CidrIpv4",
    "CidrIpv6",
    "PrefixListId",
    "ReferencedGroupInfo",
    "Description",
)
SENSITIVE_KEYS = re.compile(
    r"(access.?key|secret|session.?token|credential|password|authorization)", re.I
)


def json_safe(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {
            str(key): json_safe(item)
            for key, item in value.items()
            if not SENSITIVE_KEYS.search(str(key))
        }
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def tags_dict(tags: Iterable[dict[str, Any]] | None) -> dict[str, str]:
    return {
        str(tag.get("Key")): str(tag.get("Value", ""))
        for tag in (tags or [])
        if tag.get("Key") and not SENSITIVE_KEYS.search(str(tag.get("Key")))
    }


def iam_tags(client: Any, operation: str, argument: str, value: str) -> dict[str, str]:
    if hasattr(client, "can_paginate") and client.can_paginate(operation):
        pages = client.get_paginator(operation).paginate(**{argument: value})
        return tags_dict(tag for page in pages for tag in page.get("Tags", []))
    return tags_dict(getattr(client, operation)(**{argument: value}).get("Tags"))


def bounded_policy_document(value: Any, *, max_bytes: int = 20_000) -> dict[str, Any] | None:
    if value in (None, ""):
        return None
    if isinstance(value, str):
        if len(value.encode("utf-8")) > max_bytes:
            return {"truncated": True}
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return {"malformed": True}
    if not isinstance(value, dict):
        return {"malformed": True}
    sanitized = json_safe(value)
    encoded = json.dumps(sanitized, separators=(",", ":"), default=str)
    return sanitized if len(encoded.encode("utf-8")) <= max_bytes else {"truncated": True}


def paginated_items(
    client: Any,
    operation: str,
    result_key: str,
    **kwargs: Any,
) -> list[Any]:
    if hasattr(client, "can_paginate") and client.can_paginate(operation):
        return [
            item
            for page in client.get_paginator(operation).paginate(**kwargs)
            for item in page.get(result_key, [])
        ]
    method = getattr(client, operation)
    items: list[Any] = []
    token: str | None = None
    seen_tokens: set[str] = set()
    while True:
        request = dict(kwargs)
        if token:
            request["NextToken"] = token
        response = method(**request)
        items.extend(response.get(result_key, []))
        next_token = response.get("NextToken")
        if not next_token or next_token in seen_tokens:
            break
        seen_tokens.add(next_token)
        token = next_token
    return items


def security_group_rule_evidence(client: Any, group_id: str) -> list[dict[str, Any]]:
    pages = client.get_paginator("describe_security_group_rules").paginate(
        Filters=[{"Name": "group-id", "Values": [group_id]}]
    )
    normalized: list[dict[str, Any]] = []
    for page in pages:
        for rule in page.get("SecurityGroupRules", []):
            if not isinstance(rule, dict) or rule.get("GroupId") != group_id:
                continue
            normalized.append(
                {
                    field: (
                        rule[field] is True
                        if field == "IsEgress"
                        else json_safe(rule[field])
                    )
                    for field in SECURITY_GROUP_RULE_FIELDS
                    if field in rule
                }
            )
    return sorted(
        normalized,
        key=lambda rule: (
            str(rule.get("GroupId", "")),
            str(rule.get("SecurityGroupRuleId", "")),
            json.dumps(rule, sort_keys=True, separators=(",", ":")),
        ),
    )


@dataclass(frozen=True)
class NormalizedAsset:
    asset_type: AssetType
    resource_id: str
    arn: str | None
    name: str
    region: str
    status: str | None
    tags: dict[str, str]
    metadata: dict[str, Any]


class EC2DiscoveryService:
    asset_types: ClassVar[set[AssetType]] = {
        AssetType.EC2_INSTANCE,
        AssetType.EC2_SECURITY_GROUP,
        AssetType.EBS_VOLUME,
    }

    def discover(
        self, client_factory: ClientFactory, regions: list[str], account_id: str
    ) -> list[NormalizedAsset]:
        assets: list[NormalizedAsset] = []
        for region in regions:
            client = client_factory("ec2", region)
            for page in client.get_paginator("describe_instances").paginate():
                for reservation in page.get("Reservations", []):
                    for instance in reservation.get("Instances", []):
                        instance_id = instance["InstanceId"]
                        tags = tags_dict(instance.get("Tags"))
                        assets.append(
                            NormalizedAsset(
                                AssetType.EC2_INSTANCE,
                                instance_id,
                                f"arn:aws:ec2:{region}:{account_id}:instance/{instance_id}",
                                tags.get("Name", instance_id),
                                region,
                                instance.get("State", {}).get("Name"),
                                tags,
                                json_safe(
                                    {
                                        "instance_type": instance.get("InstanceType"),
                                        "vpc_id": instance.get("VpcId"),
                                        "subnet_id": instance.get("SubnetId"),
                                        "security_group_ids": [
                                            group.get("GroupId")
                                            for group in instance.get("SecurityGroups", [])
                                        ],
                                        "launch_time": instance.get("LaunchTime"),
                                        "has_public_ip": bool(instance.get("PublicIpAddress")),
                                        "metadata_options": {
                                            "http_tokens": (
                                                instance.get("MetadataOptions") or {}
                                            ).get("HttpTokens"),
                                            "http_endpoint": (
                                                instance.get("MetadataOptions") or {}
                                            ).get("HttpEndpoint"),
                                        },
                                    }
                                ),
                            )
                        )
            try:
                security_group_pages = client.get_paginator("describe_security_groups").paginate()
            except (AssertionError, AttributeError, KeyError):
                security_group_pages = ()
            for page in security_group_pages:
                for group in page.get("SecurityGroups", []):
                    group_id = group["GroupId"]
                    tags = tags_dict(group.get("Tags"))
                    rule_evidence = security_group_rule_evidence(client, group_id)
                    assets.append(
                        NormalizedAsset(
                            AssetType.EC2_SECURITY_GROUP,
                            group_id,
                            f"arn:aws:ec2:{region}:{account_id}:security-group/{group_id}",
                            group.get("GroupName", group_id),
                            region,
                            "active",
                            tags,
                            json_safe(
                                {
                                    "description": group.get("Description"),
                                    "vpc_id": group.get("VpcId"),
                                    "ip_permissions": group.get("IpPermissions", []),
                                    "ip_permissions_egress": group.get("IpPermissionsEgress", []),
                                    "security_group_rules": rule_evidence,
                                }
                            ),
                        )
                    )
            try:
                volume_pages = client.get_paginator("describe_volumes").paginate()
            except (AssertionError, AttributeError, KeyError):
                volume_pages = ()
            for page in volume_pages:
                for volume in page.get("Volumes", []):
                    volume_id = volume["VolumeId"]
                    tags = tags_dict(volume.get("Tags"))
                    assets.append(
                        NormalizedAsset(
                            AssetType.EBS_VOLUME,
                            volume_id,
                            f"arn:aws:ec2:{region}:{account_id}:volume/{volume_id}",
                            tags.get("Name", volume_id),
                            region,
                            volume.get("State"),
                            tags,
                            json_safe(
                                {
                                    "encrypted": volume.get("Encrypted"),
                                    "volume_type": volume.get("VolumeType"),
                                    "size_gib": volume.get("Size"),
                                    "snapshot_id": volume.get("SnapshotId"),
                                }
                            ),
                        )
                    )
        return assets


class S3DiscoveryService:
    asset_types: ClassVar[set[AssetType]] = {AssetType.S3_BUCKET}

    def discover(
        self, client_factory: ClientFactory, regions: list[str], account_id: str
    ) -> list[NormalizedAsset]:
        del regions, account_id
        client = client_factory("s3", None)
        assets: list[NormalizedAsset] = []
        for page in client.get_paginator("list_buckets").paginate():
            for bucket in page.get("Buckets", []):
                name = bucket["Name"]
                location = (
                    client.get_bucket_location(Bucket=name).get("LocationConstraint") or "us-east-1"
                )
                try:
                    tags = tags_dict(client.get_bucket_tagging(Bucket=name).get("TagSet"))
                except ClientError as exc:
                    if exc.response.get("Error", {}).get("Code") not in {
                        "NoSuchTagSet",
                        "NoSuchTagSetError",
                    }:
                        raise
                    tags = {}
                metadata: dict[str, Any] = {"creation_date": bucket.get("CreationDate")}
                optional_calls = (
                    ("get_public_access_block", "PublicAccessBlockConfiguration"),
                    ("get_bucket_acl", "Grants"),
                    ("get_bucket_policy_status", "PolicyStatus"),
                    ("get_bucket_encryption", "ServerSideEncryptionConfiguration"),
                    ("get_bucket_versioning", "Status"),
                    ("get_bucket_logging", "LoggingEnabled"),
                )
                values: dict[str, Any] = {}
                for operation, key in optional_calls:
                    method = getattr(client, operation, None)
                    if method is None:
                        continue
                    try:
                        values[operation] = method(Bucket=name).get(key)
                    except ClientError as exc:
                        code = exc.response.get("Error", {}).get("Code")
                        if (
                            operation == "get_public_access_block"
                            and code == "NoSuchPublicAccessBlockConfiguration"
                        ):
                            values[operation] = None
                        elif code not in {
                            "ServerSideEncryptionConfigurationNotFoundError",
                            "NoSuchBucketPolicy",
                        }:
                            raise
                if "get_public_access_block" in values:
                    block = values["get_public_access_block"]
                    normalized_block = (
                        {
                            key: block[key] is True
                            for key in S3_PUBLIC_ACCESS_BLOCK_KEYS
                            if key in block
                        }
                        if isinstance(block, dict)
                        else None
                    )
                    metadata["public_access_block"] = normalized_block
                    metadata["public_access_block_complete"] = bool(
                        isinstance(normalized_block, dict)
                        and len(normalized_block) == len(S3_PUBLIC_ACCESS_BLOCK_KEYS)
                        and all(normalized_block[key] for key in S3_PUBLIC_ACCESS_BLOCK_KEYS)
                    )
                grants = values.get("get_bucket_acl")
                if isinstance(grants, list):
                    public_uris = {
                        "http://acs.amazonaws.com/groups/global/AllUsers",
                        "http://acs.amazonaws.com/groups/global/AuthenticatedUsers",
                    }
                    metadata["public_access_signals"] = {
                        "public_acl": any(
                            isinstance(grant, dict)
                            and (grant.get("Grantee") or {}).get("URI") in public_uris
                            for grant in grants
                        ),
                        "public_policy": bool(
                            (values.get("get_bucket_policy_status") or {}).get("IsPublic")
                        ),
                    }
                if "get_bucket_encryption" in values:
                    metadata["default_encryption_enabled"] = bool(values["get_bucket_encryption"])
                if "get_bucket_versioning" in values:
                    metadata["versioning_enabled"] = values["get_bucket_versioning"] == "Enabled"
                if "get_bucket_logging" in values:
                    metadata["logging_enabled"] = bool(values["get_bucket_logging"])
                policy_method = getattr(client, "get_bucket_policy", None)
                if policy_method is not None:
                    try:
                        policy = policy_method(Bucket=name).get("Policy")
                        metadata["policy_document"] = bounded_policy_document(policy)
                    except ClientError as exc:
                        if exc.response.get("Error", {}).get("Code") == "NoSuchBucketPolicy":
                            metadata["policy_document"] = None
                        else:
                            raise
                assets.append(
                    NormalizedAsset(
                        AssetType.S3_BUCKET,
                        name,
                        f"arn:aws:s3:::{name}",
                        name,
                        location,
                        "available",
                        tags,
                        json_safe(metadata),
                    )
                )
        return assets


class IAMDiscoveryService:
    asset_types: ClassVar[set[AssetType]] = {
        AssetType.IAM_USER,
        AssetType.IAM_ROLE,
        AssetType.IAM_GROUP,
        AssetType.IAM_POLICY,
    }

    def discover(
        self, client_factory: ClientFactory, regions: list[str], account_id: str
    ) -> list[NormalizedAsset]:
        del regions, account_id
        client = client_factory("iam", None)
        assets: list[NormalizedAsset] = []
        seen: set[tuple[AssetType, str]] = set()
        specs = (
            ("list_users", "Users", AssetType.IAM_USER, "UserId", "UserName"),
            ("list_roles", "Roles", AssetType.IAM_ROLE, "RoleId", "RoleName"),
            ("list_groups", "Groups", AssetType.IAM_GROUP, "GroupId", "GroupName"),
            ("list_policies", "Policies", AssetType.IAM_POLICY, "PolicyId", "PolicyName"),
        )
        for operation, key, asset_type, id_key, name_key in specs:
            kwargs = {"Scope": "Local"} if operation == "list_policies" else {}
            for page in client.get_paginator(operation).paginate(**kwargs):
                for item in page.get(key, []):
                    identity = (asset_type, str(item[id_key]))
                    if identity in seen:
                        continue
                    seen.add(identity)
                    tag_method = {
                        AssetType.IAM_USER: "list_user_tags",
                        AssetType.IAM_ROLE: "list_role_tags",
                        AssetType.IAM_POLICY: "list_policy_tags",
                    }.get(asset_type)
                    tags: dict[str, str] = {}
                    if tag_method and hasattr(client, tag_method):
                        argument = {
                            AssetType.IAM_USER: "UserName",
                            AssetType.IAM_ROLE: "RoleName",
                            AssetType.IAM_POLICY: "PolicyArn",
                        }[asset_type]
                        value = (
                            item[name_key]
                            if asset_type != AssetType.IAM_POLICY
                            else item["Arn"]
                        )
                        tags = iam_tags(client, tag_method, argument, value)
                    metadata = {"path": item.get("Path"), "creation_date": item.get("CreateDate")}
                    if asset_type in {
                        AssetType.IAM_USER,
                        AssetType.IAM_ROLE,
                        AssetType.IAM_GROUP,
                    }:
                        prefix = {
                            AssetType.IAM_USER: "user",
                            AssetType.IAM_ROLE: "role",
                            AssetType.IAM_GROUP: "group",
                        }[asset_type]
                        argument_name = f"{prefix.title()}Name"
                        principal_name = str(item[name_key])
                        attached_method = getattr(client, f"list_attached_{prefix}_policies", None)
                        if attached_method:
                            attached = paginated_items(
                                client,
                                f"list_attached_{prefix}_policies",
                                "AttachedPolicies",
                                **{argument_name: principal_name},
                            )
                            metadata["attached_policy_arns"] = [
                                policy.get("PolicyArn")
                                for policy in attached
                                if policy.get("PolicyArn")
                            ]
                        inline_method = getattr(client, f"list_{prefix}_policies", None)
                        inline_names = (
                            paginated_items(
                                client,
                                f"list_{prefix}_policies",
                                "PolicyNames",
                                **{argument_name: principal_name},
                            )
                            if inline_method
                            else []
                        )
                        metadata["inline_policy_names"] = inline_names[:100]
                        metadata["inline_policy_documents"] = []
                        get_inline = getattr(client, f"get_{prefix}_policy", None)
                        if get_inline:
                            for policy_name in inline_names[:100]:
                                document = get_inline(
                                    **{
                                        argument_name: principal_name,
                                        "PolicyName": policy_name,
                                    }
                                ).get("PolicyDocument", {})
                                metadata["inline_policy_documents"].append(
                                    bounded_policy_document(document)
                                )
                    if asset_type == AssetType.IAM_USER:
                        username = str(item[name_key])
                        login_profile = getattr(client, "get_login_profile", None)
                        if login_profile:
                            try:
                                login_profile(UserName=username)
                                metadata["console_access"] = True
                            except ClientError as exc:
                                if exc.response.get("Error", {}).get("Code") == "NoSuchEntity":
                                    metadata["console_access"] = False
                                else:
                                    raise
                        mfa_method = getattr(client, "list_mfa_devices", None)
                        if mfa_method:
                            metadata["mfa_enabled"] = bool(
                                paginated_items(
                                    client,
                                    "list_mfa_devices",
                                    "MFADevices",
                                    UserName=username,
                                )
                            )
                        key_method = getattr(client, "list_access_keys", None)
                        if key_method:
                            created_values = []
                            for key in paginated_items(
                                client,
                                "list_access_keys",
                                "AccessKeyMetadata",
                                UserName=username,
                            ):
                                created = key.get("CreateDate")
                                if key.get("Status") == "Active" and isinstance(created, datetime):
                                    created_values.append(created.isoformat())
                            metadata["active_key_created_at"] = created_values
                    if asset_type == AssetType.IAM_ROLE:
                        metadata["max_session_duration"] = item.get("MaxSessionDuration")
                    if asset_type == AssetType.IAM_POLICY:
                        metadata.update(
                            {
                                "attachment_count": item.get("AttachmentCount"),
                                "update_date": item.get("UpdateDate"),
                            }
                        )
                    assets.append(
                        NormalizedAsset(
                            asset_type,
                            str(item[id_key]),
                            item.get("Arn"),
                            str(item[name_key]),
                            "global",
                            "active",
                            tags,
                            json_safe(metadata),
                        )
                    )
        return assets


class RDSDiscoveryService:
    asset_types: ClassVar[set[AssetType]] = {AssetType.RDS_INSTANCE}

    def discover(
        self, client_factory: ClientFactory, regions: list[str], account_id: str
    ) -> list[NormalizedAsset]:
        del account_id
        assets: list[NormalizedAsset] = []
        for region in regions:
            client = client_factory("rds", region)
            for page in client.get_paginator("describe_db_instances").paginate():
                for item in page.get("DBInstances", []):
                    arn = item.get("DBInstanceArn")
                    tags = (
                        tags_dict(client.list_tags_for_resource(ResourceName=arn).get("TagList"))
                        if arn
                        else {}
                    )
                    vpc_id = (item.get("DBSubnetGroup") or {}).get("VpcId")
                    metadata = {
                        "engine": item.get("Engine"),
                        "engine_version": item.get("EngineVersion"),
                        "instance_class": item.get("DBInstanceClass"),
                        "endpoint": json_safe(item.get("Endpoint")),
                        "multi_az": item.get("MultiAZ"),
                        "vpc_id": vpc_id,
                        "publicly_accessible": item.get("PubliclyAccessible"),
                        "storage_encrypted": item.get("StorageEncrypted"),
                        "backup_retention_period": item.get("BackupRetentionPeriod"),
                        "auto_minor_version_upgrade": item.get("AutoMinorVersionUpgrade"),
                        "deletion_protection": item.get("DeletionProtection"),
                    }
                    identifier = item["DBInstanceIdentifier"]
                    assets.append(
                        NormalizedAsset(
                            AssetType.RDS_INSTANCE,
                            identifier,
                            arn,
                            identifier,
                            region,
                            item.get("DBInstanceStatus"),
                            tags,
                            json_safe(metadata),
                        )
                    )
        return assets


class CloudWatchDiscoveryService:
    asset_types: ClassVar[set[AssetType]] = {
        AssetType.CLOUDWATCH_ALARM,
        AssetType.CLOUDWATCH_LOG_GROUP,
    }

    def discover(
        self, client_factory: ClientFactory, regions: list[str], account_id: str
    ) -> list[NormalizedAsset]:
        assets: list[NormalizedAsset] = []
        for region in regions:
            try:
                cloudwatch = client_factory("cloudwatch", region)
                logs = client_factory("logs", region)
            except KeyError:
                return []
            for page in cloudwatch.get_paginator("describe_alarms").paginate():
                for alarm in page.get("MetricAlarms", []):
                    name = alarm["AlarmName"]
                    assets.append(
                        NormalizedAsset(
                            AssetType.CLOUDWATCH_ALARM,
                            f"{region}:{name}",
                            alarm.get("AlarmArn"),
                            name,
                            region,
                            alarm.get("StateValue"),
                            {},
                            json_safe(
                                {
                                    "actions_enabled": alarm.get("ActionsEnabled"),
                                    "alarm_actions": alarm.get("AlarmActions", []),
                                    "ok_actions": alarm.get("OKActions", []),
                                    "insufficient_data_actions": alarm.get(
                                        "InsufficientDataActions", []
                                    ),
                                    "metric_name": alarm.get("MetricName"),
                                    "namespace": alarm.get("Namespace"),
                                    "dimensions": alarm.get("Dimensions", []),
                                    "state": alarm.get("StateValue"),
                                    "comparison_operator": alarm.get("ComparisonOperator"),
                                }
                            ),
                        )
                    )
            for page in logs.get_paginator("describe_log_groups").paginate():
                for group in page.get("logGroups", []):
                    name = group["logGroupName"]
                    metric_filters = paginated_items(
                        logs,
                        "describe_metric_filters",
                        "metricFilters",
                        logGroupName=name,
                        limit=50,
                    )
                    subscriptions = paginated_items(
                        logs,
                        "describe_subscription_filters",
                        "subscriptionFilters",
                        logGroupName=name,
                        limit=50,
                    )
                    assets.append(
                        NormalizedAsset(
                            AssetType.CLOUDWATCH_LOG_GROUP,
                            f"{region}:{name}",
                            group.get("arn"),
                            name,
                            region,
                            "active",
                            {},
                            json_safe(
                                {
                                    "retention_days": group.get("retentionInDays"),
                                    "kms_encrypted": bool(group.get("kmsKeyId")),
                                    "metric_filter_count": len(metric_filters),
                                    "subscription_filter_count": len(subscriptions),
                                }
                            ),
                        )
                    )
        return assets


class CloudTrailDiscoveryService:
    asset_types: ClassVar[set[AssetType]] = {AssetType.CLOUDTRAIL_TRAIL}

    def discover(
        self, client_factory: ClientFactory, regions: list[str], account_id: str
    ) -> list[NormalizedAsset]:
        del account_id
        assets: list[NormalizedAsset] = []
        seen: set[str] = set()
        for region in regions:
            try:
                client = client_factory("cloudtrail", region)
            except KeyError:
                return []
            for trail in client.describe_trails(includeShadowTrails=False).get("trailList", []):
                arn = str(trail.get("TrailARN") or trail.get("Name"))
                if arn in seen:
                    continue
                seen.add(arn)
                status = client.get_trail_status(Name=arn)
                event_selectors = client.get_event_selectors(TrailName=arn)
                insight_method = getattr(client, "get_insight_selectors", None)
                insights = (
                    insight_method(TrailName=arn).get("InsightSelectors", [])
                    if insight_method
                    else []
                )
                tag_method = getattr(client, "list_tags", None)
                trail_tags: dict[str, str] = {}
                if tag_method and trail.get("TrailARN"):
                    resources = paginated_items(
                        client,
                        "list_tags",
                        "ResourceTagList",
                        ResourceIdList=[trail["TrailARN"]],
                    )
                    for resource in resources:
                        if isinstance(resource, dict):
                            trail_tags.update(tags_dict(resource.get("TagsList")))
                assets.append(
                    NormalizedAsset(
                        AssetType.CLOUDTRAIL_TRAIL,
                        arn,
                        trail.get("TrailARN"),
                        trail.get("Name", arn),
                        trail.get("HomeRegion", region),
                        "logging" if status.get("IsLogging") else "stopped",
                        trail_tags,
                        json_safe(
                            {
                                "is_logging": status.get("IsLogging"),
                                "is_multi_region": trail.get("IsMultiRegionTrail"),
                                "include_global_service_events": trail.get(
                                    "IncludeGlobalServiceEvents"
                                ),
                                "log_file_validation_enabled": trail.get(
                                    "LogFileValidationEnabled"
                                ),
                                "kms_encrypted": bool(trail.get("KmsKeyId")),
                                "cloudwatch_integration": bool(
                                    trail.get("CloudWatchLogsLogGroupArn")
                                ),
                                "delivery_failed": bool(status.get("LatestDeliveryError")),
                                "event_selector_count": len(
                                    event_selectors.get("EventSelectors", [])
                                )
                                + len(event_selectors.get("AdvancedEventSelectors", [])),
                                "insight_selector_count": len(insights),
                            }
                        ),
                    )
                )
        return assets


def safe_aws_error(exc: Exception) -> str:
    if isinstance(exc, ClientError):
        code = str(exc.response.get("Error", {}).get("Code", "client_error"))
        value = re.sub(r"[^a-z0-9]+", "_", code.casefold()).strip("_")
        return value[:80] or "client_error"
    if isinstance(exc, AWSConnectionFailure):
        return exc.reason[:80]
    if isinstance(exc, BotoCoreError):
        return "aws_service_error"
    return "discovery_service_failed"


class DiscoveryCollector(Protocol):
    """Shape shared by the real collectors and the demo synthetic collectors."""

    @property
    def asset_types(self) -> set[AssetType]: ...

    def discover(
        self, factory: Any, regions: list[str], account_id: str
    ) -> list[NormalizedAsset]: ...


class DiscoveryOrchestrator:
    services: tuple[DiscoveryCollector, ...] = (
        EC2DiscoveryService(),
        S3DiscoveryService(),
        IAMDiscoveryService(),
        RDSDiscoveryService(),
        CloudWatchDiscoveryService(),
        CloudTrailDiscoveryService(),
    )

    def __init__(
        self, db: Session, settings: Settings, client_factory: ClientFactory | None = None
    ) -> None:
        self.db, self.settings = db, settings
        self.assets, self.jobs = AssetRepository(db), DiscoveryJobRepository(db)
        self.client_factory = client_factory
        if client_factory is None and settings.demo_synthetic_discovery:
            # Local demo only; Settings forbids this flag in production-like
            # environments. Imported lazily to avoid a circular import, since
            # demo_inventory depends on NormalizedAsset from this module.
            from app.services.demo_inventory import (
                synthetic_client_factory,
                synthetic_discovery_services,
            )

            # Instance attributes shadow the real class-level collectors, so the
            # orchestrator keeps its genuine normalize/upsert/audit pipeline but
            # never assumes a customer role or calls AWS.
            self.services = synthetic_discovery_services()
            self.client_factory = synthetic_client_factory

    def start(self, account_id: uuid.UUID, actor: User) -> DiscoveryJob:
        account = self.db.scalar(
            select(AWSAccount).where(AWSAccount.id == account_id).with_for_update()
        )
        if not account:
            raise NotFoundError("aws_account_not_found", "AWS account was not found.")
        OrganizationService(self.db).require_capability(
            account.organization_id, actor.id, Capability.DISCOVERY_START
        )
        if account.connection_status != AWSAccountStatus.CONNECTED:
            raise ConflictError(
                "aws_account_not_connected", "Only connected AWS accounts can run discovery."
            )
        if self.jobs.active_for_account(account.id):
            raise ConflictError(
                "discovery_already_running", "A discovery job is already active for this account."
            )
        job = DiscoveryJob(
            organization_id=account.organization_id,
            aws_account_id=account.id,
            started_by_user_id=actor.id,
        )
        try:
            self.jobs.create(job)
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            raise ConflictError(
                "discovery_already_running", "A discovery job is already active for this account."
            ) from exc
        return self.run(job.id, actor)

    def run(self, job_id: uuid.UUID, actor: User) -> DiscoveryJob:
        job = self.db.scalar(
            select(DiscoveryJob)
            .where(DiscoveryJob.id == job_id)
            .execution_options(populate_existing=True)
            .with_for_update()
        )
        if not job:
            raise NotFoundError("discovery_job_not_found", "Discovery job was not found.")
        if job.status != DiscoveryJobStatus.PENDING:
            raise ConflictError(
                "discovery_job_not_pending",
                "Only a pending discovery job can start execution.",
            )
        account = self.db.get(AWSAccount, job.aws_account_id)
        if not account:
            raise NotFoundError("aws_account_not_found", "AWS account was not found.")
        job.status, job.started_at = DiscoveryJobStatus.RUNNING, now_utc()
        record_audit(
            self.db,
            "aws.discovery.started",
            "discovery_job",
            organization_id=job.organization_id,
            actor_user_id=actor.id,
            resource_id=job.id,
            metadata={"aws_account_id": account.account_id, "job_id": str(job.id)},
        )
        self.db.commit()
        errors: dict[str, str] = {}
        service_results: dict[str, str] = {}
        successes = 0
        try:
            factory = self.client_factory or self._assumed_client_factory(account)
        except Exception as exc:
            failure = {"sts": safe_aws_error(exc)}
            return self._finish(
                job,
                actor,
                DiscoveryJobStatus.FAILED,
                failure,
                service_results=failure,
            )
        for service in self.services:
            name = service.__class__.__name__.replace("DiscoveryService", "").lower()
            try:
                normalized = service.discover(
                    factory, self.settings.discovery_regions, account.account_id
                )
                counts = self._upsert(account, normalized, service.asset_types)
                job.assets_discovered += len(normalized)
                job.assets_created += counts[0]
                job.assets_updated += counts[1]
                job.assets_deactivated += counts[2]
                self.db.commit()
                successes += 1
                service_results[name] = "succeeded"
            except Exception as exc:
                self.db.rollback()
                job = self.db.get(DiscoveryJob, job.id)
                assert job is not None
                errors[name] = safe_aws_error(exc)
                service_results[name] = errors[name]
        status = (
            DiscoveryJobStatus.COMPLETED
            if not errors
            else (
                DiscoveryJobStatus.PARTIALLY_COMPLETED if successes else DiscoveryJobStatus.FAILED
            )
        )
        return self._finish(job, actor, status, errors, service_results=service_results)

    def _assumed_client_factory(self, account: AWSAccount) -> ClientFactory:
        provider = TenantRoleCredentialProvider(
            account,
            self.settings,
            sts_client_factory=boto3.client,
            client_factory=boto3.client,
        )
        return provider.client

    def _upsert(
        self, account: AWSAccount, discovered: list[NormalizedAsset], asset_types: set[AssetType]
    ) -> tuple[int, int, int]:
        # Account-level locking gives asset upsert/reactivation/deactivation one deterministic
        # order and prevents a stale deactivation from racing a rediscovery for this account.
        self.db.execute(
            select(AWSAccount.id).where(AWSAccount.id == account.id).with_for_update()
        ).scalar_one()
        at, created, updated = now_utc(), 0, 0
        seen: set[tuple[AssetType, str]] = set()
        for item in discovered:
            seen.add((item.asset_type, item.resource_id))
            asset = self.assets.by_identity(account.id, item.asset_type, item.resource_id)
            if asset is None:
                asset = Asset(
                    organization_id=account.organization_id,
                    aws_account_id=account.id,
                    asset_type=item.asset_type,
                    resource_id=item.resource_id,
                    first_seen_at=at,
                )
                self.db.add(asset)
                created += 1
            else:
                updated += 1
            asset.arn, asset.name, asset.region, asset.status = (
                item.arn,
                item.name,
                item.region,
                item.status,
            )
            asset.tags, asset.metadata_json, asset.last_seen_at, asset.is_active = (
                item.tags,
                json_safe(item.metadata),
                at,
                True,
            )
        deactivated = self.assets.deactivate_missing(account.id, asset_types, seen, at)
        self.db.flush()
        return created, updated, deactivated

    def _finish(
        self,
        job: DiscoveryJob,
        actor: User,
        status: DiscoveryJobStatus,
        errors: dict[str, str],
        *,
        service_results: dict[str, str] | None = None,
    ) -> DiscoveryJob:
        locked = self.db.scalar(
            select(DiscoveryJob)
            .where(DiscoveryJob.id == job.id)
            .execution_options(populate_existing=True)
            .with_for_update()
        )
        if locked is None:
            raise NotFoundError("discovery_job_not_found", "Discovery job was not found.")
        if locked.status != DiscoveryJobStatus.RUNNING:
            raise ConflictError(
                "discovery_job_not_running",
                "Only a running discovery job can reach a terminal state.",
            )
        job = locked
        job.status, job.finished_at = status, now_utc()
        job.error_summary = (
            "; ".join(f"{key}:{value}" for key, value in sorted(errors.items()))[:2000] or None
        )
        event = {
            DiscoveryJobStatus.COMPLETED: "aws.discovery.completed",
            DiscoveryJobStatus.PARTIALLY_COMPLETED: "aws.discovery.partially_completed",
            DiscoveryJobStatus.FAILED: "aws.discovery.failed",
        }[status]
        record_audit(
            self.db,
            event,
            "discovery_job",
            organization_id=job.organization_id,
            actor_user_id=actor.id,
            resource_id=job.id,
            result=AuditResult.FAILED
            if status == DiscoveryJobStatus.FAILED
            else AuditResult.SUCCEEDED,
            metadata={
                "aws_account_id": str(job.aws_account_id),
                "job_id": str(job.id),
                "assets_discovered": job.assets_discovered,
                "assets_created": job.assets_created,
                "assets_updated": job.assets_updated,
                "assets_deactivated": job.assets_deactivated,
                "service_results": service_results or errors,
            },
        )
        self.db.commit()
        self.db.refresh(job)
        return job
