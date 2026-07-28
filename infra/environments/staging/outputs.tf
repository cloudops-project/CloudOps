output "load_balancer_dns_name" {
  value = module.platform.load_balancer_dns_name
}

output "ecr_repository_urls" {
  value = module.platform.repository_urls
}

output "runtime_secret_name" {
  value = module.secrets.secret_names["api-runtime"]
}

output "database_endpoint" {
  value = module.database.endpoint
}

output "migration_task_definition_arn" {
  value = module.platform.migration_task_definition_arn
}

output "private_subnet_ids" {
  value = module.platform.private_subnet_ids
}

output "application_security_group_id" {
  value = module.platform.application_security_group_id
}

output "service_task_definition_arns" {
  value = module.platform.service_task_definition_arns
}

output "service_desired_counts" {
  value = module.platform.service_desired_counts
}
