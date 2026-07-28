data "aws_caller_identity" "current" {}
data "aws_partition" "current" {}

data "aws_iam_policy_document" "secrets_kms" {
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

resource "aws_kms_key" "secrets" {
  description             = "${var.name} application secrets"
  deletion_window_in_days = 30
  enable_key_rotation     = true
  policy                  = data.aws_iam_policy_document.secrets_kms.json
  tags                    = var.tags
}

resource "aws_kms_alias" "secrets" {
  name          = "alias/${var.name}-secrets"
  target_key_id = aws_kms_key.secrets.key_id
}

resource "aws_secretsmanager_secret" "this" {
  for_each = var.secret_names

  name                    = "/cloudops/${var.name}/${each.key}"
  description             = "Managed secret container for ${var.name} ${each.key}"
  kms_key_id              = aws_kms_key.secrets.arn
  recovery_window_in_days = var.recovery_window_in_days
  tags                    = var.tags

  # checkov:skip=CKV2_AWS_57:Rotation is operator-controlled for the composite V1 runtime secret; provider-specific rotation and safe application restart are documented prerequisites.

  lifecycle {
    prevent_destroy = true
  }
}
