output "state_bucket_name" {
  value = aws_s3_bucket.state.id
}

output "state_kms_key_arn" {
  value = aws_kms_key.state.arn
}

output "lock_table_name" {
  value = aws_dynamodb_table.locks.name
}

output "github_oidc_provider_arn" {
  description = "Resolved GitHub Actions OIDC provider ARN, whether created or supplied."
  value       = local.github_oidc_provider_arn
}

output "github_oidc_provider_created" {
  description = "Whether this bootstrap configuration manages a newly created GitHub Actions OIDC provider."
  value       = var.github_oidc_provider_mode == "create"
}

output "github_publish_role_arn" {
  value = aws_iam_role.github_publish.arn
}

output "github_deploy_role_arns" {
  description = "Deployment role ARNs keyed only by explicitly selected environment."
  value       = { for environment, role in aws_iam_role.github_deploy : environment => role.arn }
}
