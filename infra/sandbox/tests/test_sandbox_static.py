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


def _hosting_security_group() -> str:
    """Return only the aws_security_group.hosting block."""
    start = MAIN.index('resource "aws_security_group" "hosting"')
    end = MAIN.index('resource "', start + 1)
    return MAIN[start:end]


def test_cloudflare_tunnel_quic_egress_exists() -> None:
    block = _hosting_security_group()
    assert 'description = "Cloudflare Tunnel QUIC"' in block
    quic = block[block.index('"Cloudflare Tunnel QUIC"') :]
    quic = quic[: quic.index("}")]
    assert 'protocol    = "udp"' in quic
    assert "from_port   = 7844" in quic
    assert "to_port     = 7844" in quic
    assert 'cidr_blocks = ["0.0.0.0/0"]' in quic


def test_cloudflare_tunnel_http2_fallback_egress_exists() -> None:
    block = _hosting_security_group()
    assert 'description = "Cloudflare Tunnel HTTP/2 fallback"' in block
    fallback = block[block.index('"Cloudflare Tunnel HTTP/2 fallback"') :]
    fallback = fallback[: fallback.index("}")]
    assert 'protocol    = "tcp"' in fallback
    assert "from_port   = 7844" in fallback
    assert "to_port     = 7844" in fallback
    assert 'cidr_blocks = ["0.0.0.0/0"]' in fallback


def test_existing_https_and_dns_egress_remain() -> None:
    block = _hosting_security_group()
    assert 'description = "Outbound HTTPS for SSM, packages, and Cloudflare"' in block
    assert 'description = "DNS over UDP through the VPC resolver"' in block
    assert 'description = "DNS over TCP through the VPC resolver"' in block
    assert block.count("from_port   = 53") == 2
    assert block.count('cidr_blocks = ["10.50.0.2/32"]') == 2
    assert "from_port   = 443" in block


def test_hosting_group_has_no_all_port_or_all_protocol_egress() -> None:
    block = _hosting_security_group()
    assert 'protocol    = "-1"' not in block
    assert "from_port   = 0" not in block
    assert "to_port     = 0" not in block
    assert "to_port     = 65535" not in block


def test_no_public_application_ingress_was_added() -> None:
    block = _hosting_security_group()
    ingress = block[block.index("ingress {") :]
    ingress = ingress[: ingress.index("}")]
    assert "cidr_blocks = [var.administrator_cidr]" in ingress
    assert 'cidr_blocks = ["0.0.0.0/0"]' not in ingress
    assert block.count("ingress {") == 1
    for port in ("80", "443", "8000", "8080", "8081", "7844"):
        assert f"from_port   = {port}" not in ingress


def test_intentional_public_ingress_group_is_unchanged() -> None:
    start = MAIN.index('resource "aws_security_group" "intentional_public_ingress"')
    block = MAIN[start:]
    block = block[: block.index("\nresource \"")] if '\nresource "' in block else block
    assert 'description = "INTENTIONAL-TEST: CloudOps SSH public-ingress finding"' in block
    assert "from_port   = 22" in block
    assert 'cidr_blocks = ["0.0.0.0/0"]' in block
    assert "7844" not in block


def test_operator_mutations_fail_closed() -> None:
    assert 'DESTROY_CONFIRMATION = "DESTROY-CLOUDOPS-AWS-SANDBOX"' in OPERATOR
    assert 'root_identity_forbidden' in OPERATOR
    assert 'caller_account_mismatch' in OPERATOR
    assert 'terraform_state_owner_mismatch' in OPERATOR
    assert '"-destroy",' in OPERATOR
    assert '"terraform", "apply", str(plan_path)' in OPERATOR
    assert "--execute-reviewed-plan" in OPERATOR
    assert "access_key" not in OPERATOR.casefold()
