from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
MAIN = (ROOT / "infra" / "sandbox" / "main.tf").read_text(encoding="utf-8")
VARIABLES = (ROOT / "infra" / "sandbox" / "variables.tf").read_text(encoding="utf-8")
OPERATOR = (ROOT / "scripts" / "aws_sandbox.py").read_text(encoding="utf-8")


def test_host_and_network_are_bounded() -> None:
    assert 'cidr_block           = "10.50.0.0/16"' in MAIN
    assert 'cidr_block              = "10.50.1.0/24"' in MAIN
    assert 'http_tokens                 = "required"' in MAIN
    assert 'volume_size = 50' in MAIN
    assert "aws_nat_gateway" not in MAIN
    assert "aws_lb" not in MAIN
    assert "aws_eip" not in MAIN
    assert "aws_db_instance" not in MAIN
    assert 'cidr_blocks = [var.administrator_cidr]' in MAIN
    assert 'administrator_cidr != "0.0.0.0/0"' in VARIABLES


def test_roles_are_separate_and_remediation_is_exact() -> None:
    assert 'resource "aws_iam_role" "platform"' in MAIN
    assert 'resource "aws_iam_role" "discovery"' in MAIN
    assert 'resource "aws_iam_role" "remediation"' in MAIN
    assert '"s3:PutBucketPublicAccessBlock"' in MAIN
    assert '"ec2:RevokeSecurityGroupIngress"' in MAIN
    assert '"ec2:AuthorizeSecurityGroupIngress"' in MAIN
    assert "AdministratorAccess" not in MAIN
    assert '"iam:*"' not in MAIN
    assert '"s3:*"' not in MAIN
    assert '"ec2:*"' not in MAIN


def test_test_resources_have_mandatory_safety_properties() -> None:
    assert 'CloudOpsLab              = "true"' in MAIN
    assert 'Environment              = "cloudops-test"' in MAIN
    assert 'AllowCloudOpsRemediation = "true"' in MAIN
    assert 'force_destroy = false' in MAIN
    assert 'prevent_destroy = true' in MAIN
    assert 'enable_optional_test_instance"' in VARIABLES
    assert 'default     = false' in VARIABLES
    assert 'associate_public_ip_address = false' in MAIN


def test_operator_mutations_fail_closed() -> None:
    assert 'DESTROY_CONFIRMATION = "DESTROY-CLOUDOPS-AWS-SANDBOX"' in OPERATOR
    assert 'root_identity_forbidden' in OPERATOR
    assert 'caller_account_mismatch' in OPERATOR
    assert 'terraform_state_owner_mismatch' in OPERATOR
    assert '"-destroy",' in OPERATOR
    assert '"terraform", "apply", str(plan_path)' in OPERATOR
    assert "--execute-reviewed-plan" in OPERATOR
    assert "access_key" not in OPERATOR.casefold()
