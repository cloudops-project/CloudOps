"""Deterministic synthetic demo inventory.

This module is the single source of truth for the local demo's synthetic AWS
inventory. It exists because the demo seed and the demo "Run now" scan must
agree exactly: previously the seed invented its own simplified metadata key
names, so every deterministic rule that read the real collector key names
returned ``invalid_or_incomplete_metadata`` and the intended demo findings
(open SSH, public S3 bucket) were never created.

Every ``metadata`` mapping below therefore uses the *same keys the real
collectors in ``app.services.discovery`` emit*, which are the keys the rules in
``app.security_rules`` read. If a collector's metadata contract changes, this
module must change with it, and ``test_demo_stack.py`` asserts the resulting
findings so drift fails loudly.

Nothing here contacts AWS. Values are synthetic and use documentation-reserved
identifiers only.
"""

from __future__ import annotations

from typing import ClassVar

from app.models.enums import AssetType
from app.services.discovery import NormalizedAsset

DEMO_ACCOUNT_ID = "123456789012"
DEMO_REGION = "us-east-1"
_TAGS = {"Environment": "demo", "Synthetic": "true"}


def synthetic_inventory(account_id: str = DEMO_ACCOUNT_ID) -> list[NormalizedAsset]:
    """Return the deterministic synthetic inventory for the demo account."""
    return [
        NormalizedAsset(
            AssetType.EC2_INSTANCE,
            "i-0demo0instance0001",
            f"arn:aws:ec2:{DEMO_REGION}:{account_id}:instance/i-0demo0instance0001",
            "demo-web-instance",
            DEMO_REGION,
            "running",
            dict(_TAGS),
            {
                "instance_type": "t3.micro",
                "vpc_id": "vpc-0demo0000",
                "subnet_id": "subnet-0demo0000",
                "security_group_ids": ["sg-0demo0open0ssh"],
                # Rule EC2_INSTANCE_PUBLIC_IP reads has_public_ip -> FAILED (MEDIUM).
                "has_public_ip": True,
                # Rule EC2_INSTANCE_IMDSV1_ALLOWED reads metadata_options.http_tokens;
                # "optional" means IMDSv1 is still permitted -> FAILED (HIGH).
                "metadata_options": {"http_tokens": "optional", "http_endpoint": "enabled"},
                "synthetic": True,
            },
        ),
        NormalizedAsset(
            AssetType.EC2_SECURITY_GROUP,
            "sg-0demo0open0ssh",
            f"arn:aws:ec2:{DEMO_REGION}:{account_id}:security-group/sg-0demo0open0ssh",
            "demo-open-ssh",
            DEMO_REGION,
            "active",
            dict(_TAGS),
            {
                "description": "Demo group intentionally exposing SSH",
                "vpc_id": "vpc-0demo0000",
                # Rules read ip_permissions with AWS-shaped keys. World-open TCP 22
                # -> EC2_SG_SSH_OPEN_TO_WORLD FAILED (CRITICAL). RDP and all-traffic
                # rules PASS, which demonstrates rules that correctly find nothing.
                "ip_permissions": [
                    {
                        "IpProtocol": "tcp",
                        "FromPort": 22,
                        "ToPort": 22,
                        "IpRanges": [{"CidrIp": "0.0.0.0/0"}],
                        "Ipv6Ranges": [],
                    }
                ],
                "ip_permissions_egress": [],
                "synthetic": True,
            },
        ),
        NormalizedAsset(
            AssetType.S3_BUCKET,
            "cloudops-demo-public-bucket",
            "arn:aws:s3:::cloudops-demo-public-bucket",
            "cloudops-demo-public-bucket",
            DEMO_REGION,
            "active",
            dict(_TAGS),
            {
                # S3_BUCKET_PUBLIC_ACCESS_CONFIRMED reads public_access_signals (dict).
                "public_access_signals": {"public_acl": True, "public_policy": True},
                # S3_BUCKET_PUBLIC_ACCESS_BLOCK_INCOMPLETE reads *_complete, not
                # public_access_block.
                "public_access_block_complete": False,
                "default_encryption_enabled": False,
                "versioning_enabled": False,
                "logging_enabled": False,
                # Explicit None means "no bucket policy", which the HTTPS-only rule
                # treats as FAILED(policy_present=False) rather than an error.
                "policy_document": None,
                "synthetic": True,
            },
        ),
        NormalizedAsset(
            AssetType.CLOUDTRAIL_TRAIL,
            "cloudops-demo-trail",
            f"arn:aws:cloudtrail:{DEMO_REGION}:{account_id}:trail/cloudops-demo-trail",
            "cloudops-demo-trail",
            DEMO_REGION,
            "disabled",
            dict(_TAGS),
            {
                # All seven CloudTrail rule keys are present so none of them errors.
                # delivery_failed stays False so that rule PASSES.
                "is_logging": False,
                "is_multi_region": False,
                "include_global_service_events": False,
                "log_file_validation_enabled": False,
                "kms_encrypted": False,
                "cloudwatch_integration": False,
                "delivery_failed": False,
                "synthetic": True,
            },
        ),
        NormalizedAsset(
            AssetType.IAM_USER,
            "AIDADEMOUSER0000001",
            f"arn:aws:iam::{account_id}:user/demo-admin-user",
            "demo-admin-user",
            "global",
            "active",
            dict(_TAGS),
            {
                "console_access": True,
                "mfa_enabled": False,
                # Fixed past date keeps the >90-day access-key rule deterministically
                # FAILED without depending on when the demo runs.
                "active_key_created_at": ["2024-01-01T00:00:00Z"],
                "attached_policy_arns": ["arn:aws:iam::aws:policy/AdministratorAccess"],
                "inline_policy_documents": [
                    {"Statement": {"Effect": "Allow", "Action": "*", "Resource": "*"}}
                ],
                "synthetic": True,
            },
        ),
    ]


def _inventory_for(asset_types: set[AssetType], account_id: str) -> list[NormalizedAsset]:
    return [item for item in synthetic_inventory(account_id) if item.asset_type in asset_types]


class _SyntheticDiscoveryService:
    """Collector-shaped double that replays synthetic inventory.

    Mirrors the real collector interface (``asset_types`` plus ``discover``) so
    ``DiscoveryOrchestrator`` runs its genuine normalize/upsert/stale/counter/
    audit pipeline. The client factory argument is accepted and ignored; no AWS
    call is made.
    """

    asset_types: ClassVar[set[AssetType]] = set()

    def discover(
        self, _factory: object, _regions: list[str], account_id: str
    ) -> list[NormalizedAsset]:
        return _inventory_for(self.asset_types, account_id)


class SyntheticEC2DiscoveryService(_SyntheticDiscoveryService):
    asset_types: ClassVar[set[AssetType]] = {
        AssetType.EC2_INSTANCE,
        AssetType.EC2_SECURITY_GROUP,
        AssetType.EBS_VOLUME,
    }


class SyntheticS3DiscoveryService(_SyntheticDiscoveryService):
    asset_types: ClassVar[set[AssetType]] = {AssetType.S3_BUCKET}


class SyntheticIAMDiscoveryService(_SyntheticDiscoveryService):
    asset_types: ClassVar[set[AssetType]] = {
        AssetType.IAM_USER,
        AssetType.IAM_ROLE,
        AssetType.IAM_GROUP,
        AssetType.IAM_POLICY,
    }


class SyntheticCloudTrailDiscoveryService(_SyntheticDiscoveryService):
    asset_types: ClassVar[set[AssetType]] = {AssetType.CLOUDTRAIL_TRAIL}


def synthetic_discovery_services() -> tuple[_SyntheticDiscoveryService, ...]:
    """Collectors used when DEMO_SYNTHETIC_DISCOVERY is enabled."""
    return (
        SyntheticEC2DiscoveryService(),
        SyntheticS3DiscoveryService(),
        SyntheticIAMDiscoveryService(),
        SyntheticCloudTrailDiscoveryService(),
    )


def synthetic_client_factory(_service: str, _region: str | None = None) -> object:
    """Placeholder factory so the orchestrator never assumes a customer role.

    Synthetic collectors ignore the factory entirely; returning a sentinel keeps
    ``DiscoveryOrchestrator.run`` from falling through to STS.
    """
    return object()
