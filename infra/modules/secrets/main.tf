resource "aws_kms_key" "secrets" {
  description             = "${var.name} application secrets"
  deletion_window_in_days = 30
  enable_key_rotation     = true
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

  lifecycle {
    prevent_destroy = true
  }
}
