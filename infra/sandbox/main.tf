data "aws_ssm_parameter" "ubuntu_2404_amd64" {
  name = "/aws/service/canonical/ubuntu/server/24.04/stable/current/amd64/hvm/ebs-gp3/ami-id"
}

data "aws_partition" "current" {}

data "aws_caller_identity" "current" {}

locals {
  mandatory_tags = {
    CloudOpsLab              = "true"
    Environment              = "cloudops-test"
    AllowCloudOpsRemediation = "true"
    ManagedBy                = "Terraform"
    StateOwner               = var.state_owner
  }
}

resource "aws_vpc" "sandbox" {
  #checkov:skip=CKV2_AWS_11:This isolated lab omits continuously billable flow-log delivery; no customer data is permitted and host/application logs remain required.
  cidr_block           = "10.50.0.0/16"
  enable_dns_support   = true
  enable_dns_hostnames = true

  tags = { Name = "cloudops-remediation-sandbox" }
}

resource "aws_internet_gateway" "sandbox" {
  vpc_id = aws_vpc.sandbox.id
  tags   = { Name = "cloudops-remediation-sandbox" }
}

resource "aws_subnet" "hosting" {
  #checkov:skip=CKV_AWS_130:The no-NAT design needs an ephemeral public address for outbound SSM/packages/tunnel traffic; the SG exposes only approved-CIDR SSH.
  vpc_id                  = aws_vpc.sandbox.id
  cidr_block              = "10.50.1.0/24"
  map_public_ip_on_launch = true
  tags                    = { Name = "cloudops-hosting" }
}

resource "aws_default_security_group" "sandbox" {
  vpc_id = aws_vpc.sandbox.id

  tags = { Name = "cloudops-sandbox-default-deny" }
}

resource "aws_subnet" "test_private" {
  vpc_id                  = aws_vpc.sandbox.id
  cidr_block              = "10.50.2.0/24"
  map_public_ip_on_launch = false
  tags                    = { Name = "cloudops-test-private" }
}

resource "aws_route_table" "hosting" {
  vpc_id = aws_vpc.sandbox.id
  tags   = { Name = "cloudops-hosting" }
}

resource "aws_route" "hosting_internet" {
  route_table_id         = aws_route_table.hosting.id
  destination_cidr_block = "0.0.0.0/0"
  gateway_id             = aws_internet_gateway.sandbox.id
}

resource "aws_route_table_association" "hosting" {
  subnet_id      = aws_subnet.hosting.id
  route_table_id = aws_route_table.hosting.id
}

resource "aws_security_group" "hosting" {
  name_prefix = "cloudops-hosting-"
  description = "No public application ports; SSH only from approved administrator CIDR"
  vpc_id      = aws_vpc.sandbox.id

  ingress {
    description = "Explicit administrator SSH access"
    protocol    = "tcp"
    from_port   = 22
    to_port     = 22
    cidr_blocks = [var.administrator_cidr]
  }

  egress {
    description = "Outbound HTTPS for SSM, packages, and Cloudflare"
    protocol    = "tcp"
    from_port   = 443
    to_port     = 443
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    description = "Cloudflare Tunnel QUIC"
    protocol    = "udp"
    from_port   = 7844
    to_port     = 7844
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    description = "Cloudflare Tunnel HTTP/2 fallback"
    protocol    = "tcp"
    from_port   = 7844
    to_port     = 7844
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    description = "DNS over UDP through the VPC resolver"
    protocol    = "udp"
    from_port   = 53
    to_port     = 53
    cidr_blocks = ["10.50.0.2/32"]
  }

  egress {
    description = "DNS over TCP through the VPC resolver"
    protocol    = "tcp"
    from_port   = 53
    to_port     = 53
    cidr_blocks = ["10.50.0.2/32"]
  }

  tags = { Name = "cloudops-hosting" }
}

data "aws_iam_policy_document" "ec2_trust" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "platform" {
  name               = "CloudOpsSandboxPlatformRole"
  assume_role_policy = data.aws_iam_policy_document.ec2_trust.json
}

resource "aws_iam_role_policy_attachment" "platform_ssm" {
  role       = aws_iam_role.platform.name
  policy_arn = "arn:${data.aws_partition.current.partition}:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

resource "aws_iam_instance_profile" "platform" {
  name = "CloudOpsSandboxPlatformProfile"
  role = aws_iam_role.platform.name
}

data "aws_iam_policy_document" "sandbox_role_trust" {
  statement {
    sid     = "CloudOpsPlatformAssumeRole"
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "AWS"
      identifiers = [aws_iam_role.platform.arn]
    }

    condition {
      test     = "StringEquals"
      variable = "sts:ExternalId"
      values   = [var.discovery_external_id]
    }
  }
}

data "aws_iam_policy_document" "remediation_role_trust" {
  statement {
    sid     = "CloudOpsPlatformAssumeRole"
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "AWS"
      identifiers = [aws_iam_role.platform.arn]
    }

    condition {
      test     = "StringEquals"
      variable = "sts:ExternalId"
      values   = [var.remediation_external_id]
    }
  }
}

resource "aws_iam_role" "discovery" {
  name               = "CloudOpsSandboxDiscoveryRole"
  assume_role_policy = data.aws_iam_policy_document.sandbox_role_trust.json
}

resource "aws_iam_role_policy_attachment" "discovery_security_audit" {
  role       = aws_iam_role.discovery.name
  policy_arn = "arn:${data.aws_partition.current.partition}:iam::aws:policy/SecurityAudit"
}

data "aws_iam_policy_document" "discovery_additional" {
  statement {
    sid       = "DescribeSecurityGroupRules"
    actions   = ["ec2:DescribeSecurityGroupRules"]
    resources = ["*"]
  }

  statement {
    sid       = "ReadExactLabBucketEvidence"
    actions   = ["s3:GetBucketPublicAccessBlock", "s3:GetBucketTagging"]
    resources = [aws_s3_bucket.lab.arn]
  }

  statement {
    sid       = "VerifyCallerAccount"
    actions   = ["sts:GetCallerIdentity"]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "discovery_additional" {
  name   = "CloudOpsSandboxDiscoveryEvidence"
  role   = aws_iam_role.discovery.id
  policy = data.aws_iam_policy_document.discovery_additional.json
}

data "aws_iam_policy_document" "platform_assume_roles" {
  statement {
    sid       = "AssumeOnlyCloudOpsSandboxRoles"
    actions   = ["sts:AssumeRole"]
    resources = [aws_iam_role.discovery.arn, aws_iam_role.remediation.arn]
  }
}

resource "aws_iam_role_policy" "platform_assume_roles" {
  name   = "AssumeCloudOpsSandboxRoles"
  role   = aws_iam_role.platform.id
  policy = data.aws_iam_policy_document.platform_assume_roles.json
}

# Organization invitation email. Exactly one action against exactly one
# verified SES identity: no ses:*, no ses:SendRawEmail, no Resource "*",
# and no identity administration or verification permission.
data "aws_iam_policy_document" "platform_ses" {
  statement {
    sid     = "SendCloudOpsInvitationEmail"
    effect  = "Allow"
    actions = ["ses:SendEmail"]
    resources = [
      "arn:${data.aws_partition.current.partition}:ses:${var.aws_region}:${data.aws_caller_identity.current.account_id}:identity/mistlab.in"
    ]
  }
}

resource "aws_iam_role_policy" "platform_ses" {
  name   = "SendCloudOpsInvitationEmail"
  role   = aws_iam_role.platform.id
  policy = data.aws_iam_policy_document.platform_ses.json
}

data "aws_iam_policy_document" "remediation" {
  statement {
    sid       = "DescribeExactSecurityGroupState"
    actions   = ["ec2:DescribeSecurityGroups", "ec2:DescribeSecurityGroupRules"]
    resources = ["*"]
  }

  statement {
    sid       = "ReadExactLabBucketState"
    actions   = ["s3:GetBucketPublicAccessBlock", "s3:GetBucketTagging"]
    resources = [aws_s3_bucket.lab.arn]
  }

  statement {
    sid       = "VerifyCallerAccount"
    actions   = ["sts:GetCallerIdentity"]
    resources = ["*"]
  }

  statement {
    sid       = "SetExactLabBucketPublicAccessBlock"
    actions   = ["s3:PutBucketPublicAccessBlock"]
    resources = [aws_s3_bucket.lab.arn]

    condition {
      test     = "StringEquals"
      variable = "aws:ResourceTag/AllowCloudOpsRemediation"
      values   = ["true"]
    }
  }

  statement {
    sid = "RevokeAndRestoreExactSandboxIngress"
    actions = [
      "ec2:AuthorizeSecurityGroupIngress",
      "ec2:RevokeSecurityGroupIngress",
    ]
    resources = [aws_security_group.intentional_public_ingress.arn]

    condition {
      test     = "StringEquals"
      variable = "aws:ResourceTag/AllowCloudOpsRemediation"
      values   = ["true"]
    }
  }
}

resource "aws_iam_role" "remediation" {
  name               = "CloudOpsSandboxRemediationRole"
  assume_role_policy = data.aws_iam_policy_document.remediation_role_trust.json
}

resource "aws_iam_role_policy" "remediation" {
  name   = "CloudOpsSandboxExactRemediation"
  role   = aws_iam_role.remediation.id
  policy = data.aws_iam_policy_document.remediation.json
}

resource "aws_instance" "hosting" {

  lifecycle {
    # A newly published Canonical AMI must not silently replace the persistent
    # CloudOps host during unrelated infrastructure changes. Host replacement
    # requires a separate migration plan and explicit approval.
    ignore_changes = [ami]
  }
  #checkov:skip=CKV_AWS_88:The explicit no-NAT design requires an ephemeral public address; only approved-CIDR SSH is open and application ports remain closed.
  ami                     = data.aws_ssm_parameter.ubuntu_2404_amd64.value
  instance_type           = var.hosting_instance_type
  subnet_id               = aws_subnet.hosting.id
  vpc_security_group_ids  = [aws_security_group.hosting.id]
  iam_instance_profile    = aws_iam_instance_profile.platform.name
  key_name                = var.hosting_key_name
  disable_api_termination = var.enable_termination_protection
  monitoring              = true
  ebs_optimized           = true

  metadata_options {
    http_endpoint               = "enabled"
    http_tokens                 = "required"
    http_put_response_hop_limit = 2
  }

  root_block_device {
    encrypted   = true
    volume_type = "gp3"
    volume_size = 50
  }

  tags = { Name = "cloudops-sandbox-host" }
}

resource "aws_s3_account_public_access_block" "sandbox" {
  block_public_acls       = true
  ignore_public_acls      = true
  block_public_policy     = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket" "lab" {
  #checkov:skip=CKV_AWS_18:The test bucket must remain empty; API request IDs and CloudTrail are the audit evidence, avoiding a second logging bucket.
  #checkov:skip=CKV_AWS_144:This disposable single-region lab does not replicate intentionally empty test data.
  #checkov:skip=CKV_AWS_145:AES256 encryption is intentional for an empty lab bucket; no sensitive data is permitted.
  #checkov:skip=CKV2_AWS_6:The incomplete bucket-level block is the test condition; account-level Public Access Block remains fully enabled.
  #checkov:skip=CKV2_AWS_62:Event notifications are unnecessary because the governed test bucket must remain empty.
  bucket        = var.lab_bucket_name
  force_destroy = false

  lifecycle {
    prevent_destroy = true
  }

  tags = { Name = var.lab_bucket_name }
}

resource "aws_s3_bucket_versioning" "lab" {
  bucket = aws_s3_bucket.lab.id
  versioning_configuration { status = "Enabled" }
}

resource "aws_s3_bucket_lifecycle_configuration" "lab" {
  bucket = aws_s3_bucket.lab.id

  rule {
    id     = "abort-incomplete-multipart-uploads"
    status = "Enabled"
    filter {}

    abort_incomplete_multipart_upload { days_after_initiation = 1 }
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "lab" {
  bucket = aws_s3_bucket.lab.id

  rule {
    apply_server_side_encryption_by_default { sse_algorithm = "AES256" }
  }
}

resource "aws_s3_bucket_public_access_block" "intentional_test" {
  #checkov:skip=CKV_AWS_54:The incomplete bucket-level block is the deterministic test input; account-level blocking remains enabled.
  #checkov:skip=CKV_AWS_55:The incomplete bucket-level block is the deterministic test input; account-level blocking remains enabled.
  #checkov:skip=CKV_AWS_56:The incomplete bucket-level block is the deterministic test input; account-level blocking remains enabled.
  bucket                  = aws_s3_bucket.lab.id
  block_public_acls       = true
  ignore_public_acls      = false
  block_public_policy     = false
  restrict_public_buckets = false
}

resource "aws_security_group" "intentional_public_ingress" {
  #checkov:skip=CKV_AWS_24:TCP/22 world ingress is the explicit tagged finding under test and is never attached to the hosting instance.
  name_prefix = "cloudops-lab-ingress-"
  description = "Intentional CloudOps remediation test; contains no sensitive workload"
  vpc_id      = aws_vpc.sandbox.id

  ingress {
    description = "INTENTIONAL-TEST: CloudOps SSH public-ingress finding"
    protocol    = "tcp"
    from_port   = 22
    to_port     = 22
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = { Name = "cloudops-lab-intentional-public-ingress" }
}

resource "aws_instance" "optional_test" {
  #checkov:skip=CKV2_AWS_41:The disabled-by-default private test instance intentionally has no AWS API identity or sensitive workload.
  count = var.enable_optional_test_instance ? 1 : 0

  ami                         = data.aws_ssm_parameter.ubuntu_2404_amd64.value
  instance_type               = "t3a.nano"
  subnet_id                   = aws_subnet.test_private.id
  associate_public_ip_address = false
  vpc_security_group_ids      = [aws_security_group.intentional_public_ingress.id]
  monitoring                  = true

  metadata_options {
    http_endpoint               = "enabled"
    http_tokens                 = "required"
    http_put_response_hop_limit = 1
  }

  root_block_device {
    encrypted   = true
    volume_type = "gp3"
    volume_size = 8
  }

  tags = { Name = "cloudops-lab-optional-private-test" }
}
