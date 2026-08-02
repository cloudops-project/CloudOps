#!/usr/bin/env python3
"""Default-refusing CloudOps live AWS sandbox test harness.

This tool performs read-only AWS preflight checks and calls only the fixed
CloudOps remediation detail/execute endpoints. It never dispatches a direct
AWS mutation and never accepts an AWS service or operation name.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

OPT_IN = "true"
REGION = "ap-south-1"
SANDBOX_TAG = "AllowCloudOpsRemediation=true"
PLAN_CONFIRMATION = "RUN-CLOUDOPS-LIVE-AWS-SANDBOX"
EXECUTE_CONFIRMATION = "EXECUTE-CLOUDOPS-GOVERNED-REMEDIATION"
REQUIRED_TAGS = {
    "CloudOpsLab": "true",
    "Environment": "cloudops-test",
    "AllowCloudOpsRemediation": "true",
}
ROLE_ARN = re.compile(r"^arn:(aws|aws-us-gov|aws-cn):iam::([0-9]{12}):role/[A-Za-z0-9+=,.@_/-]+$")
ALLOWED_ACTIONS = {
    "s3.enable_public_access_block": "s3",
    "ec2.revoke_approved_public_ingress": "ec2",
}
ROOT = Path(__file__).resolve().parents[1]


class SafetyRefusal(RuntimeError):
    """Stable, sanitized refusal safe to show to an operator."""


class AWSClientFactory(Protocol):
    def __call__(self, service: str, region: str | None = None) -> Any: ...


@dataclass(frozen=True)
class HarnessConfig:
    account_id: str
    region: str
    remediation_role_arn: str
    action_key: str
    resource_id: str
    api_url: str
    organization_id: uuid.UUID
    request_id: uuid.UUID
    token_file: Path
    external_id_file: Path

    @classmethod
    def from_environment(cls) -> HarnessConfig:
        required = {
            "CLOUDOPS_LIVE_AWS_TESTS": OPT_IN,
            "EXPECTED_AWS_REGION": REGION,
            "EXPECTED_SANDBOX_TAG": SANDBOX_TAG,
            "EXPLICIT_CONFIRMATION": PLAN_CONFIRMATION,
        }
        for name, expected in required.items():
            if os.getenv(name) != expected:
                raise SafetyRefusal(f"required_gate_missing:{name}")
        account_id = _required("EXPECTED_AWS_ACCOUNT_ID")
        if not re.fullmatch(r"[0-9]{12}", account_id):
            raise SafetyRefusal("expected_account_invalid")
        role_arn = _required("EXPECTED_REMEDIATION_ROLE_ARN")
        role_match = ROLE_ARN.fullmatch(role_arn)
        if role_match is None or role_match.group(2) != account_id:
            raise SafetyRefusal("expected_remediation_role_invalid")
        action_key = _required("LIVE_REMEDIATION_ACTION")
        target_type = ALLOWED_ACTIONS.get(action_key)
        if target_type is None:
            raise SafetyRefusal("action_not_allowed")
        resource_variable = (
            "EXPECTED_S3_BUCKET" if target_type == "s3" else "EXPECTED_SECURITY_GROUP_ID"
        )
        resource_id = _required(resource_variable)
        if target_type == "s3" and not resource_id.startswith("cloudops-lab-"):
            raise SafetyRefusal("s3_bucket_prefix_not_allowed")
        if target_type == "ec2" and not re.fullmatch(r"sg-[0-9a-f]{8,17}", resource_id):
            raise SafetyRefusal("security_group_id_invalid")
        api_url = _required("CLOUDOPS_API_URL").rstrip("/")
        if not api_url.startswith("https://"):
            raise SafetyRefusal("https_api_required")
        return cls(
            account_id=account_id,
            region=REGION,
            remediation_role_arn=role_arn,
            action_key=action_key,
            resource_id=resource_id,
            api_url=api_url,
            organization_id=uuid.UUID(_required("CLOUDOPS_ORGANIZATION_ID")),
            request_id=uuid.UUID(_required("CLOUDOPS_REMEDIATION_REQUEST_ID")),
            token_file=Path(_required("CLOUDOPS_AUTH_TOKEN_FILE")),
            external_id_file=Path(_required("REMEDIATION_EXTERNAL_ID_FILE")),
        )


def _required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise SafetyRefusal(f"required_value_missing:{name}")
    return value


def _read_private_value(path: Path, label: str) -> str:
    resolved = path.resolve()
    if resolved.is_relative_to(ROOT):
        raise SafetyRefusal(f"{label}_file_must_be_outside_repository")
    if not resolved.is_file():
        raise SafetyRefusal(f"{label}_file_missing")
    value = resolved.read_text(encoding="utf-8").strip()
    if not value:
        raise SafetyRefusal(f"{label}_file_empty")
    return value


def _plan_path(value: str) -> Path:
    path = Path(value).resolve()
    if path.is_relative_to(ROOT):
        raise SafetyRefusal("plan_file_must_be_outside_repository")
    if path.suffix != ".json":
        raise SafetyRefusal("plan_json_extension_required")
    return path


def default_clients(config: HarnessConfig) -> AWSClientFactory:
    import boto3  # type: ignore[import-untyped]
    from botocore.config import Config  # type: ignore[import-untyped]

    bounded = Config(
        connect_timeout=5,
        read_timeout=15,
        retries={"mode": "standard", "max_attempts": 3},
    )
    sts = boto3.client("sts", region_name=config.region, config=bounded)
    identity = sts.get_caller_identity()
    if str(identity.get("Account")) != config.account_id:
        raise SafetyRefusal("caller_account_mismatch")
    if str(identity.get("Arn", "")).endswith(":root"):
        raise SafetyRefusal("root_identity_forbidden")
    external_id = _read_private_value(config.external_id_file, "external_id")
    response = sts.assume_role(
        RoleArn=config.remediation_role_arn,
        RoleSessionName="CloudOpsLiveHarness",
        ExternalId=external_id,
        DurationSeconds=900,
    )
    raw = response.get("Credentials")
    if not isinstance(raw, dict):
        raise SafetyRefusal("assume_role_credentials_missing")

    def factory(service: str, region: str | None = None) -> Any:
        if service not in {"sts", "s3", "ec2"}:
            raise SafetyRefusal("aws_service_not_allowed")
        return boto3.client(
            service,
            region_name=region or config.region,
            config=bounded,
            aws_access_key_id=raw["AccessKeyId"],
            aws_secret_access_key=raw["SecretAccessKey"],
            aws_session_token=raw["SessionToken"],
        )

    assumed = factory("sts").get_caller_identity()
    if str(assumed.get("Account")) != config.account_id:
        raise SafetyRefusal("assumed_account_mismatch")
    return factory


def _verify_resource(config: HarnessConfig, clients: AWSClientFactory) -> None:
    if ALLOWED_ACTIONS[config.action_key] == "s3":
        response = clients("s3", config.region).get_bucket_tagging(Bucket=config.resource_id)
        tag_items = response.get("TagSet", [])
    else:
        response = clients("ec2", config.region).describe_security_groups(
            GroupIds=[config.resource_id]
        )
        groups = response.get("SecurityGroups", [])
        if len(groups) != 1 or groups[0].get("GroupId") != config.resource_id:
            raise SafetyRefusal("security_group_not_found")
        tag_items = groups[0].get("Tags", [])
    tags = {
        str(item.get("Key")): str(item.get("Value"))
        for item in tag_items
        if isinstance(item, dict) and item.get("Key") is not None
    }
    if any(tags.get(key) != value for key, value in REQUIRED_TAGS.items()):
        raise SafetyRefusal("required_remediation_tags_missing")


def _api_request(config: HarnessConfig, method: str, path: str) -> dict[str, Any]:
    token = _read_private_value(config.token_file, "auth_token")
    request = urllib.request.Request(
        f"{config.api_url}{path}",
        method=method,
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:  # noqa: S310
            body = response.read(65_536)
    except urllib.error.HTTPError as exc:
        raise SafetyRefusal(f"cloudops_api_http_{exc.code}") from None
    except urllib.error.URLError:
        raise SafetyRefusal("cloudops_api_unavailable") from None
    value = json.loads(body)
    if not isinstance(value, dict):
        raise SafetyRefusal("cloudops_api_response_invalid")
    return value


def build_plan(
    config: HarnessConfig,
    *,
    clients: AWSClientFactory,
) -> dict[str, str]:
    _verify_resource(config, clients)
    query = urllib.parse.urlencode({"organization_id": str(config.organization_id)})
    request = _api_request(
        config,
        "GET",
        f"/api/v1/remediations/{config.request_id}?{query}",
    )
    expected = {
        "status": "approved",
        "execution_mode": "live_aws",
        "dry_run": False,
        "action_key": config.action_key,
    }
    if any(request.get(key) != value for key, value in expected.items()):
        raise SafetyRefusal("remediation_request_not_live_approved")
    if str(request.get("organization_id")) != str(config.organization_id):
        raise SafetyRefusal("remediation_request_tenant_mismatch")
    return {
        "schema": "cloudops-live-remediation-plan-v1",
        "account_suffix": config.account_id[-4:],
        "region": config.region,
        "action_key": config.action_key,
        "resource_id": config.resource_id,
        "organization_id": str(config.organization_id),
        "request_id": str(config.request_id),
        "snapshot_hash": str(request.get("request_snapshot_hash", "")),
    }


def plan_command(args: argparse.Namespace) -> None:
    config = HarnessConfig.from_environment()
    plan = build_plan(config, clients=default_clients(config))
    plan_path = _plan_path(args.plan_file)
    plan_path.write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(plan, indent=2, sort_keys=True))
    print("Read-only plan complete. No AWS mutation or CloudOps execution was requested.")


def execute_command(args: argparse.Namespace) -> None:
    if os.getenv("EXECUTION_CONFIRMATION") != EXECUTE_CONFIRMATION:
        raise SafetyRefusal("separate_execution_confirmation_missing")
    config = HarnessConfig.from_environment()
    plan_path = _plan_path(args.plan_file)
    if not plan_path.is_file():
        raise SafetyRefusal("reviewed_plan_missing")
    reviewed = json.loads(plan_path.read_text(encoding="utf-8"))
    current = build_plan(config, clients=default_clients(config))
    if reviewed != current:
        raise SafetyRefusal("reviewed_plan_is_stale")
    query = urllib.parse.urlencode({"organization_id": str(config.organization_id)})
    response = _api_request(
        config,
        "POST",
        f"/api/v1/remediations/{config.request_id}/execute?{query}",
    )
    if response.get("job_type") != "remediation_simulation":
        raise SafetyRefusal("unexpected_job_response")
    print(f"Governed remediation job accepted: {response.get('id', '<redacted>')}")


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    commands = result.add_subparsers(dest="command", required=True)
    for name, handler in (("plan", plan_command), ("execute", execute_command)):
        command = commands.add_parser(name)
        command.add_argument("--plan-file", required=True)
        command.set_defaults(handler=handler)
    return result


def main() -> int:
    args = parser().parse_args()
    try:
        args.handler(args)
    except (SafetyRefusal, KeyError, TypeError, ValueError, json.JSONDecodeError):
        print("REFUSED: live_remediation_safety_gate_failed", file=sys.stderr)
        return 2
    except Exception:  # noqa: BLE001 - final redaction boundary for provider/HTTP failures
        print("REFUSED: live_remediation_external_failure", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
