#!/usr/bin/env python3
"""Fail-closed operator entry point for the CloudOps AWS sandbox.

The tool never accepts arbitrary AWS operations. Mutating Terraform commands
require verified short-lived identity, exact account/region inputs, state-owner
agreement, and a separate reviewed-plan execution step.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

EXPECTED_REGION = "ap-south-1"
DESTROY_CONFIRMATION = "DESTROY-CLOUDOPS-AWS-SANDBOX"
MANDATORY_TAGS = {
    "CloudOpsLab": "true",
    "Environment": "cloudops-test",
    "AllowCloudOpsRemediation": "true",
    "ManagedBy": "Terraform",
}
ALLOWED_RESOURCE_ADDRESSES = {
    "aws_default_security_group.sandbox",
    "aws_iam_instance_profile.platform",
    "aws_iam_role.discovery",
    "aws_iam_role.platform",
    "aws_iam_role.remediation",
    "aws_iam_role_policy.discovery_additional",
    "aws_iam_role_policy.platform_assume_roles",
    "aws_iam_role_policy.remediation",
    "aws_iam_role_policy_attachment.discovery_security_audit",
    "aws_iam_role_policy_attachment.platform_ssm",
    "aws_instance.hosting",
    "aws_instance.optional_test",
    "aws_internet_gateway.sandbox",
    "aws_route.hosting_internet",
    "aws_route_table.hosting",
    "aws_route_table_association.hosting",
    "aws_s3_account_public_access_block.sandbox",
    "aws_s3_bucket.lab",
    "aws_s3_bucket_lifecycle_configuration.lab",
    "aws_s3_bucket_public_access_block.intentional_test",
    "aws_s3_bucket_server_side_encryption_configuration.lab",
    "aws_s3_bucket_versioning.lab",
    "aws_security_group.hosting",
    "aws_security_group.intentional_public_ingress",
    "aws_subnet.hosting",
    "aws_subnet.test_private",
    "aws_vpc.sandbox",
}
ROOT = Path(__file__).resolve().parents[1]
TERRAFORM_ROOT = ROOT / "infra" / "sandbox"


class SafetyRefusal(RuntimeError):
    """A stable, non-sensitive operator safety failure."""


def _run(command: list[str], *, capture: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 - fixed executable/argument lists only
        command,
        cwd=TERRAFORM_ROOT,
        check=True,
        text=True,
        capture_output=capture,
    )


def _identity(profile: str | None) -> dict[str, str]:
    command = ["aws", "sts", "get-caller-identity", "--output", "json"]
    if profile:
        command.extend(["--profile", profile])
    result = _run(command, capture=True)
    raw = json.loads(result.stdout)
    return {key: str(raw.get(key, "")) for key in ("Account", "Arn", "UserId")}


def verify_identity(args: argparse.Namespace) -> dict[str, str]:
    if args.expected_account_id is None or not args.expected_account_id.isdigit():
        raise SafetyRefusal("exact_expected_account_required")
    if len(args.expected_account_id) != 12:
        raise SafetyRefusal("exact_expected_account_required")
    if args.region != EXPECTED_REGION:
        raise SafetyRefusal("approved_region_mismatch")
    identity = _identity(args.profile)
    if identity["Account"] != args.expected_account_id:
        raise SafetyRefusal("caller_account_mismatch")
    if identity["Arn"].endswith(":root"):
        raise SafetyRefusal("root_identity_forbidden")
    print(f"Verified non-root account ending in {identity['Account'][-4:]}; region {args.region}.")
    return identity


def validate(_args: argparse.Namespace) -> None:
    _run(["terraform", "fmt", "-check", "-recursive"])
    _run(["terraform", "init", "-backend=false"])
    _run(["terraform", "validate"])


def plan(args: argparse.Namespace) -> None:
    verify_identity(args)
    plan_path = Path(args.plan_file).resolve()
    if plan_path.suffix != ".tfplan":
        raise SafetyRefusal("reviewed_plan_extension_required")
    _run(["terraform", "init"])
    _run(
        [
            "terraform",
            "plan",
            f"-out={plan_path}",
            f"-var=expected_aws_account_id={args.expected_account_id}",
            f"-var=aws_region={args.region}",
        ]
    )
    print(f"Review-only plan written to {plan_path}; no resources were changed.")


def cost_inventory(args: argparse.Namespace) -> None:
    result = _run(["terraform", "show", "-json", str(Path(args.plan_file).resolve())], capture=True)
    plan_json: dict[str, Any] = json.loads(result.stdout)
    resources = plan_json.get("planned_values", {}).get("root_module", {}).get("resources", [])
    counts: dict[str, int] = {}
    for resource in resources:
        resource_type = str(resource.get("type", "unknown"))
        counts[resource_type] = counts.get(resource_type, 0) + 1
    print(json.dumps({"planned_resource_counts": counts}, indent=2, sort_keys=True))


def prepare(args: argparse.Namespace) -> None:
    verify_identity(args)
    print("Preparation passed. Review Terraform plan, billable resources, IAM, tags, and state ownership.")
    print("This command did not apply Terraform or create AWS resources.")


def verify(args: argparse.Namespace) -> None:
    verify_identity(args)
    result = _run(["terraform", "output", "-json"], capture=True)
    outputs = json.loads(result.stdout)
    expected = {"platform_instance_id", "discovery_role_arn", "remediation_role_arn", "lab_bucket_name", "test_security_group_id"}
    if not expected.issubset(outputs):
        raise SafetyRefusal("sandbox_outputs_incomplete")
    print("Terraform state contains the expected non-secret sandbox outputs.")


def _state_owner() -> str:
    result = _run(["terraform", "output", "-json", "state_owner"], capture=True)
    value = json.loads(result.stdout)
    if not isinstance(value, str):
        raise SafetyRefusal("terraform_state_owner_missing")
    return value


def _assert_destroy_plan(plan_path: Path) -> None:
    result = _run(["terraform", "show", "-json", str(plan_path)], capture=True)
    plan_json: dict[str, Any] = json.loads(result.stdout)
    changes = plan_json.get("resource_changes")
    if not isinstance(changes, list) or not changes:
        raise SafetyRefusal("destroy_plan_has_no_owned_resources")
    for resource in changes:
        address = str(resource.get("address", "")).split("[")[0]
        if address not in ALLOWED_RESOURCE_ADDRESSES:
            raise SafetyRefusal("destroy_plan_contains_unowned_resource")
        change = resource.get("change", {})
        if change.get("actions") not in (["delete"], ["no-op"]):
            raise SafetyRefusal("destroy_plan_contains_non_delete_action")
        before = change.get("before")
        if not isinstance(before, dict):
            continue
        tags = before.get("tags_all") or before.get("tags")
        if isinstance(tags, dict) and any(
            tags.get(key) != value for key, value in MANDATORY_TAGS.items()
        ):
            raise SafetyRefusal("destroy_plan_resource_tags_mismatch")


def destroy(args: argparse.Namespace) -> None:
    verify_identity(args)
    if args.confirmation != DESTROY_CONFIRMATION:
        raise SafetyRefusal("exact_destroy_confirmation_required")
    if args.state_owner != _state_owner():
        raise SafetyRefusal("terraform_state_owner_mismatch")
    plan_path = Path(args.plan_file).resolve()
    if plan_path.suffix != ".tfplan":
        raise SafetyRefusal("reviewed_plan_extension_required")
    if args.execute_reviewed_plan:
        if not plan_path.is_file():
            raise SafetyRefusal("reviewed_destroy_plan_missing")
        _assert_destroy_plan(plan_path)
        _run(["terraform", "apply", str(plan_path)])
        return
    _run(
        [
            "terraform",
            "plan",
            "-destroy",
            f"-out={plan_path}",
            f"-var=expected_aws_account_id={args.expected_account_id}",
            f"-var=aws_region={args.region}",
        ]
    )
    _assert_destroy_plan(plan_path)
    print("Destroy plan created only. Re-review it before the separate execution command.")


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    subcommands = result.add_subparsers(dest="command", required=True)
    subcommands.add_parser("validate").set_defaults(handler=validate)
    for name, handler in (("preflight", verify_identity), ("prepare", prepare), ("verify", verify)):
        command = subcommands.add_parser(name)
        _identity_arguments(command)
        command.set_defaults(handler=handler)
    plan_command = subcommands.add_parser("plan")
    _identity_arguments(plan_command)
    plan_command.add_argument("--plan-file", required=True)
    plan_command.set_defaults(handler=plan)
    cost_command = subcommands.add_parser("cost-inventory")
    cost_command.add_argument("--plan-file", required=True)
    cost_command.set_defaults(handler=cost_inventory)
    destroy_command = subcommands.add_parser("destroy")
    _identity_arguments(destroy_command)
    destroy_command.add_argument("--state-owner", required=True)
    destroy_command.add_argument("--confirmation", required=True)
    destroy_command.add_argument("--plan-file", required=True)
    destroy_command.add_argument("--execute-reviewed-plan", action="store_true")
    destroy_command.set_defaults(handler=destroy)
    return result


def _identity_arguments(command: argparse.ArgumentParser) -> None:
    command.add_argument("--expected-account-id", required=True)
    command.add_argument("--region", default=EXPECTED_REGION)
    command.add_argument("--profile")


def main() -> int:
    args = parser().parse_args()
    try:
        args.handler(args)
    except (SafetyRefusal, subprocess.CalledProcessError, json.JSONDecodeError) as exc:
        code = str(exc) if isinstance(exc, SafetyRefusal) else "operator_command_failed"
        print(f"REFUSED: {code}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
