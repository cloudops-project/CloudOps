output "platform_instance_id" {
  description = "Hosting instance identifier."
  value       = aws_instance.hosting.id
}

output "platform_role_arn" {
  description = "Workload identity attached to the hosting instance."
  value       = aws_iam_role.platform.arn
}

output "discovery_role_arn" {
  description = "Read-only discovery role for CloudOps onboarding."
  value       = aws_iam_role.discovery.arn
}

output "remediation_role_arn" {
  description = "Narrowly scoped sandbox remediation role."
  value       = aws_iam_role.remediation.arn
}

output "lab_bucket_name" {
  description = "Empty test bucket owned by this Terraform state."
  value       = aws_s3_bucket.lab.id
}

output "test_security_group_id" {
  description = "Tagged security group containing the intentional test ingress rule."
  value       = aws_security_group.intentional_public_ingress.id
}

output "estimated_billable_resources" {
  description = "Cost-sensitive resources to review before apply."
  value = {
    hosting_instance       = var.hosting_instance_type
    hosting_root_volume_gb = 50
    optional_test_instance = var.enable_optional_test_instance ? "t3a.nano" : "disabled"
    nat_gateways           = 0
    load_balancers         = 0
    managed_databases      = 0
    elastic_ips            = 0
  }
}

output "state_owner" {
  description = "Non-secret state ownership marker checked by operator safety tooling."
  value       = var.state_owner
}
