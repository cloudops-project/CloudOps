from __future__ import annotations

from typing import Any

from app.models import Asset
from app.models.enums import AssetType, FindingSeverity
from app.security_rules.base import Evaluator, RuleContext, SecurityRule
from app.security_rules.results import RuleResult, error, failed, passed

WORLD_CIDRS = {"0.0.0.0/0", "::/0"}


def _permissions(asset: Asset) -> list[dict[str, Any]] | None:
    value = asset.metadata_json.get("ip_permissions")
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        return None
    return value


def _world_ranges(permission: dict[str, Any]) -> list[str]:
    values: list[str] = []
    for item in permission.get("IpRanges", []):
        if isinstance(item, dict) and item.get("CidrIp") in WORLD_CIDRS:
            values.append(str(item["CidrIp"]))
    for item in permission.get("Ipv6Ranges", []):
        if isinstance(item, dict) and item.get("CidrIpv6") in WORLD_CIDRS:
            values.append(str(item["CidrIpv6"]))
    return sorted(set(values))


def _port_exposure(port: int) -> Evaluator:
    def evaluate(asset: Asset | None, _context: RuleContext) -> RuleResult:
        assert asset is not None
        permissions = _permissions(asset)
        if permissions is None:
            return error()
        exposed: list[dict[str, Any]] = []
        for permission in permissions:
            ranges = _world_ranges(permission)
            protocol = str(permission.get("IpProtocol", ""))
            start, end = permission.get("FromPort"), permission.get("ToPort")
            applies = protocol == "-1" or (
                isinstance(start, int) and isinstance(end, int) and start <= port <= end
            )
            if ranges and applies:
                exposed.append(
                    {"protocol": protocol, "from_port": start, "to_port": end, "cidrs": ranges}
                )
        return failed(exposures=exposed, port=port) if exposed else passed(port=port)

    return evaluate


def _all_traffic(asset: Asset | None, _context: RuleContext) -> RuleResult:
    assert asset is not None
    permissions = _permissions(asset)
    if permissions is None:
        return error()
    exposed = [
        {"protocol": permission.get("IpProtocol"), "cidrs": _world_ranges(permission)}
        for permission in permissions
        if str(permission.get("IpProtocol")) == "-1" and _world_ranges(permission)
    ]
    return failed(exposures=exposed) if exposed else passed()


def _boolean_failure(field: str, unsafe_value: Any, *, missing_error: bool = True) -> Evaluator:
    def evaluate(asset: Asset | None, _context: RuleContext) -> RuleResult:
        assert asset is not None
        if field not in asset.metadata_json:
            return error() if missing_error else passed()
        value = asset.metadata_json[field]
        return failed(**{field: value}) if value == unsafe_value else passed(**{field: value})

    return evaluate


def _imdsv1(asset: Asset | None, _context: RuleContext) -> RuleResult:
    assert asset is not None
    options = asset.metadata_json.get("metadata_options")
    if not isinstance(options, dict) or "http_tokens" not in options:
        return error()
    value = options["http_tokens"]
    return failed(http_tokens=value) if value != "required" else passed(http_tokens=value)


RULES = (
    SecurityRule(
        "EC2_SG_SSH_OPEN_TO_WORLD",
        1,
        "SSH open to the world",
        "Security-group ingress permits SSH from an IPv4 or IPv6 world CIDR.",
        "ec2",
        AssetType.EC2_SECURITY_GROUP,
        "network",
        FindingSeverity.CRITICAL,
        "Restrict TCP port 22 to explicitly approved private or administrative CIDRs.",
        evaluator=_port_exposure(22),
    ),
    SecurityRule(
        "EC2_SG_RDP_OPEN_TO_WORLD",
        1,
        "RDP open to the world",
        "Security-group ingress permits RDP from an IPv4 or IPv6 world CIDR.",
        "ec2",
        AssetType.EC2_SECURITY_GROUP,
        "network",
        FindingSeverity.CRITICAL,
        "Restrict TCP port 3389 to explicitly approved administrative CIDRs.",
        evaluator=_port_exposure(3389),
    ),
    SecurityRule(
        "EC2_SG_ALL_TRAFFIC_OPEN_TO_WORLD",
        1,
        "All traffic open to the world",
        "Security-group ingress permits every protocol from a world CIDR.",
        "ec2",
        AssetType.EC2_SECURITY_GROUP,
        "network",
        FindingSeverity.CRITICAL,
        "Replace unrestricted ingress with least-privilege protocol and port rules.",
        evaluator=_all_traffic,
    ),
    SecurityRule(
        "EC2_INSTANCE_IMDSV1_ALLOWED",
        1,
        "IMDSv1 is allowed",
        "The instance does not require IMDSv2 session tokens.",
        "ec2",
        AssetType.EC2_INSTANCE,
        "hardening",
        FindingSeverity.HIGH,
        "Require IMDSv2 by setting HttpTokens to required.",
        evaluator=_imdsv1,
    ),
    SecurityRule(
        "EC2_INSTANCE_PUBLIC_IP",
        1,
        "Instance has a public IP",
        "The instance has a directly assigned public IPv4 address.",
        "ec2",
        AssetType.EC2_INSTANCE,
        "exposure",
        FindingSeverity.MEDIUM,
        "Remove the public address unless direct internet reachability is required.",
        evaluator=lambda asset, context: _boolean_failure("has_public_ip", True)(asset, context),
    ),
    SecurityRule(
        "EBS_VOLUME_UNENCRYPTED",
        1,
        "EBS volume is unencrypted",
        "The EBS volume metadata confirms encryption is disabled.",
        "ec2",
        AssetType.EBS_VOLUME,
        "data_protection",
        FindingSeverity.HIGH,
        "Migrate data to an encrypted EBS volume.",
        evaluator=_boolean_failure("encrypted", False),
    ),
)
