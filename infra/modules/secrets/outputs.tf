output "kms_key_arn" {
  value = aws_kms_key.secrets.arn
}

output "secret_arns" {
  value = { for name, secret in aws_secretsmanager_secret.this : name => secret.arn }
}

output "secret_names" {
  value = { for name, secret in aws_secretsmanager_secret.this : name => secret.name }
}
