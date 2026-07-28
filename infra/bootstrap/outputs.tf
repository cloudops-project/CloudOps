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
  value = aws_iam_openid_connect_provider.github.arn
}

output "github_publish_role_arn" {
  value = aws_iam_role.github_publish.arn
}

output "github_deploy_role_arns" {
  value = { for environment, role in aws_iam_role.github_deploy : environment => role.arn }
}
