provider "aws" {
  region = var.aws_region

  default_tags {
    tags = merge(var.tags, {
      ManagedBy = "Terraform"
      Project   = "CloudOps"
      Component = "terraform-bootstrap"
    })
  }
}

data "aws_caller_identity" "current" {}
data "aws_partition" "current" {}

locals {
  github_oidc_provider_arn = (
    var.github_oidc_provider_mode == "create"
    ? one(aws_iam_openid_connect_provider.github[*].arn)
    : var.existing_github_oidc_provider_arn
  )
}

data "aws_iam_policy_document" "state_kms" {
  # checkov:skip=CKV_AWS_109:This is a KMS resource policy, not an identity policy; the account-root statement is the required key-administration control plane.
  # checkov:skip=CKV_AWS_111:KMS key policies require Resource "*" because the policy is attached to the key being created.
  # checkov:skip=CKV_AWS_356:KMS key policies require Resource "*" because the policy is attached to the key being created.
  statement {
    sid    = "AccountKeyAdministration"
    effect = "Allow"
    actions = [
      "kms:CancelKeyDeletion",
      "kms:CreateAlias",
      "kms:CreateGrant",
      "kms:Decrypt",
      "kms:DescribeKey",
      "kms:DisableKey",
      "kms:EnableKey",
      "kms:EnableKeyRotation",
      "kms:Encrypt",
      "kms:GenerateDataKey*",
      "kms:GetKeyPolicy",
      "kms:GetKeyRotationStatus",
      "kms:List*",
      "kms:PutKeyPolicy",
      "kms:ReEncrypt*",
      "kms:RevokeGrant",
      "kms:ScheduleKeyDeletion",
      "kms:TagResource",
      "kms:UntagResource",
      "kms:UpdateAlias",
      "kms:UpdateKeyDescription",
    ]
    resources = ["*"]

    principals {
      type = "AWS"
      identifiers = [
        "arn:${data.aws_partition.current.partition}:iam::${data.aws_caller_identity.current.account_id}:root"
      ]
    }
  }
}

resource "aws_kms_key" "state" {
  description             = "CloudOps Terraform state encryption"
  deletion_window_in_days = 30
  enable_key_rotation     = true
  policy                  = data.aws_iam_policy_document.state_kms.json
}

resource "aws_kms_alias" "state" {
  name          = "alias/cloudops-terraform-state"
  target_key_id = aws_kms_key.state.key_id
}

resource "aws_s3_bucket" "state" {
  bucket = var.state_bucket_name

  # checkov:skip=CKV_AWS_144:Cross-region replication requires a separately approved disaster-recovery region and key; versioning, retention, and backup procedures protect the V1 backend meanwhile.

  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_s3_bucket" "state_access_logs" {
  bucket = "${substr(var.state_bucket_name, 0, 43)}-access-logs"

  # checkov:skip=CKV_AWS_18:This is the terminal server-access-log destination; recursively logging it would create an unbounded log loop.
  # checkov:skip=CKV_AWS_144:Cross-region replication is deferred until the separately approved disaster-recovery region exists.
  # checkov:skip=CKV_AWS_145:S3 server access-log destinations support SSE-S3; the bucket is private, versioned, access-logged events are audited through EventBridge, and contains no application secrets.

  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_s3_bucket_ownership_controls" "state_access_logs" {
  bucket = aws_s3_bucket.state_access_logs.id

  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

resource "aws_s3_bucket_versioning" "state_access_logs" {
  bucket = aws_s3_bucket.state_access_logs.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_public_access_block" "state_access_logs" {
  bucket                  = aws_s3_bucket.state_access_logs.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "state_access_logs" {
  bucket = aws_s3_bucket.state_access_logs.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "state_access_logs" {
  bucket = aws_s3_bucket.state_access_logs.id

  rule {
    id     = "expire-access-logs"
    status = "Enabled"

    filter {}

    expiration {
      days = 365
    }

    abort_incomplete_multipart_upload {
      days_after_initiation = 7
    }
  }
}

data "aws_iam_policy_document" "state_access_logs" {
  statement {
    sid     = "S3ServerAccessLogDelivery"
    effect  = "Allow"
    actions = ["s3:PutObject"]
    resources = [
      "${aws_s3_bucket.state_access_logs.arn}/terraform-state/*",
    ]

    principals {
      type        = "Service"
      identifiers = ["logging.s3.amazonaws.com"]
    }

    condition {
      test     = "ArnLike"
      variable = "aws:SourceArn"
      values   = [aws_s3_bucket.state.arn]
    }

    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [data.aws_caller_identity.current.account_id]
    }
  }
}

resource "aws_s3_bucket_policy" "state_access_logs" {
  bucket = aws_s3_bucket.state_access_logs.id
  policy = data.aws_iam_policy_document.state_access_logs.json
}

resource "aws_s3_bucket_notification" "state_access_logs" {
  bucket      = aws_s3_bucket.state_access_logs.id
  eventbridge = true
}

resource "aws_s3_bucket_logging" "state" {
  bucket        = aws_s3_bucket.state.id
  target_bucket = aws_s3_bucket.state_access_logs.id
  target_prefix = "terraform-state/"

  depends_on = [
    aws_s3_bucket_ownership_controls.state_access_logs,
    aws_s3_bucket_policy.state_access_logs,
  ]
}

resource "aws_s3_bucket_notification" "state" {
  bucket      = aws_s3_bucket.state.id
  eventbridge = true
}

resource "aws_s3_bucket_versioning" "state" {
  bucket = aws_s3_bucket.state.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "state" {
  bucket = aws_s3_bucket.state.id

  rule {
    apply_server_side_encryption_by_default {
      kms_master_key_id = aws_kms_key.state.arn
      sse_algorithm     = "aws:kms"
    }
    bucket_key_enabled = true
  }
}

resource "aws_s3_bucket_public_access_block" "state" {
  bucket                  = aws_s3_bucket.state.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_lifecycle_configuration" "state" {
  bucket = aws_s3_bucket.state.id

  rule {
    id     = "retain-noncurrent-state"
    status = "Enabled"

    filter {}

    noncurrent_version_transition {
      noncurrent_days = 30
      storage_class   = "STANDARD_IA"
    }

    noncurrent_version_expiration {
      noncurrent_days = 365
    }

    abort_incomplete_multipart_upload {
      days_after_initiation = 7
    }
  }
}

resource "aws_dynamodb_table" "locks" {
  name         = var.lock_table_name
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "LockID"

  attribute {
    name = "LockID"
    type = "S"
  }

  point_in_time_recovery {
    enabled = true
  }

  server_side_encryption {
    enabled     = true
    kms_key_arn = aws_kms_key.state.arn
  }

  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_iam_openid_connect_provider" "github" {
  count = var.github_oidc_provider_mode == "create" ? 1 : 0

  url = "https://token.actions.githubusercontent.com"

  client_id_list = ["sts.amazonaws.com"]
  thumbprint_list = [
    "6938fd4d98bab03faadb97b34396831e3780aea1",
    "1b511abead59c6ce207077c0bf0e0043b1382612",
  ]

  tags = var.tags
}

data "aws_iam_policy_document" "github_publish_trust" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [local.github_oidc_provider_arn]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:sub"
      values   = ["repo:${var.github_repository}:ref:refs/heads/main"]
    }
  }
}

data "aws_iam_policy_document" "github_environment_trust" {
  for_each = var.deployment_environments

  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [local.github_oidc_provider_arn]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:sub"
      values   = ["repo:${var.github_repository}:environment:${each.key}"]
    }
  }
}

resource "aws_iam_role" "github_publish" {
  name                 = "cloudops-github-publish"
  assume_role_policy   = data.aws_iam_policy_document.github_publish_trust.json
  max_session_duration = 3600
  tags                 = var.tags
}

resource "aws_iam_role" "github_deploy" {
  for_each = var.deployment_environments

  name                 = "cloudops-github-${each.key}-deploy"
  assume_role_policy   = data.aws_iam_policy_document.github_environment_trust[each.key].json
  max_session_duration = 3600
  tags                 = merge(var.tags, { Environment = each.key })
}

data "aws_iam_policy_document" "publish" {
  statement {
    sid       = "EcrAuthentication"
    effect    = "Allow"
    actions   = ["ecr:GetAuthorizationToken"]
    resources = ["*"]
  }

  statement {
    sid    = "PublishCloudOpsImages"
    effect = "Allow"
    actions = [
      "ecr:BatchCheckLayerAvailability",
      "ecr:CompleteLayerUpload",
      "ecr:GetDownloadUrlForLayer",
      "ecr:InitiateLayerUpload",
      "ecr:PutImage",
      "ecr:UploadLayerPart",
    ]
    resources = [
      "arn:${data.aws_partition.current.partition}:ecr:${var.aws_region}:${data.aws_caller_identity.current.account_id}:repository/cloudops-*"
    ]
  }
}

resource "aws_iam_role_policy" "github_publish" {
  name   = "publish-cloudops-images"
  role   = aws_iam_role.github_publish.id
  policy = data.aws_iam_policy_document.publish.json
}

data "aws_iam_policy_document" "deploy" {
  statement {
    sid    = "ReadCloudOpsEcsDeploymentState"
    effect = "Allow"
    actions = [
      "ecs:DescribeClusters",
      "ecs:DescribeServices",
      "ecs:DescribeTaskDefinition",
      "ecs:DescribeTasks",
      "ecs:ListTasks",
    ]
    resources = ["*"]
  }

  # checkov:skip=CKV_AWS_111:RegisterTaskDefinition does not support resource-level permissions; iam:PassRole below limits usable execution and task roles.
  # checkov:skip=CKV_AWS_356:RegisterTaskDefinition requires Resource "*"; all resource-scoped ECS mutations are in separate statements.
  statement {
    sid       = "RegisterCloudOpsTaskDefinitions"
    effect    = "Allow"
    actions   = ["ecs:RegisterTaskDefinition"]
    resources = ["*"]
  }

  statement {
    sid    = "UpdateCloudOpsServices"
    effect = "Allow"
    actions = [
      "ecs:UpdateService",
    ]
    resources = [
      "arn:${data.aws_partition.current.partition}:ecs:${var.aws_region}:${data.aws_caller_identity.current.account_id}:service/cloudops-*/*",
    ]
  }

  statement {
    sid    = "OperateCloudOpsDeploymentTasks"
    effect = "Allow"
    actions = [
      "ecs:RunTask",
      "ecs:StopTask",
    ]
    resources = [
      "arn:${data.aws_partition.current.partition}:ecs:${var.aws_region}:${data.aws_caller_identity.current.account_id}:task-definition/cloudops-*:*",
      "arn:${data.aws_partition.current.partition}:ecs:${var.aws_region}:${data.aws_caller_identity.current.account_id}:task/cloudops-*/*",
    ]
  }

  statement {
    sid     = "PassOnlyCloudOpsTaskRoles"
    effect  = "Allow"
    actions = ["iam:PassRole"]
    resources = [
      "arn:${data.aws_partition.current.partition}:iam::${data.aws_caller_identity.current.account_id}:role/cloudops-*"
    ]

    condition {
      test     = "StringEquals"
      variable = "iam:PassedToService"
      values   = ["ecs-tasks.amazonaws.com"]
    }
  }

  statement {
    sid    = "ReadDeploymentEvidence"
    effect = "Allow"
    actions = [
      "cloudwatch:DescribeAlarms",
      "logs:GetLogEvents",
      "logs:StartQuery",
      "logs:GetQueryResults",
    ]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "github_deploy" {
  for_each = aws_iam_role.github_deploy

  name   = "deploy-cloudops-${each.key}"
  role   = each.value.id
  policy = data.aws_iam_policy_document.deploy.json
}
