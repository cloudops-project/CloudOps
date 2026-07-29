output "application_security_group_id" {
  value = aws_security_group.application.id
}

output "cluster_name" {
  value = aws_ecs_cluster.this.name
}

output "load_balancer_dns_name" {
  value = aws_lb.this.dns_name
}

output "public_protocol" {
  description = "Active public listener protocol."
  value       = var.enable_http_only_staging ? "http" : "https"
}

output "public_listener_ports" {
  description = "Active public listener ports."
  value       = var.enable_http_only_staging ? [80] : [443]
}

output "temporary_http_staging_warning" {
  description = "Non-empty only while the temporary unencrypted staging mode is active."
  value = var.enable_http_only_staging ? (
    "WARNING: staging traffic is unencrypted. Avoid credentials and sensitive testing; keep live Bedrock and SES disabled; remove HTTP mode after DNS and ACM are ready."
  ) : ""
}

output "repository_urls" {
  value = { for name, repository in aws_ecr_repository.images : name => repository.repository_url }
}

output "task_role_arns" {
  value = { for name, role in aws_iam_role.task : name => role.arn }
}

output "alarm_topic_arn" {
  value = aws_sns_topic.alarms.arn
}

output "migration_task_definition_arn" {
  value = aws_ecs_task_definition.migration.arn
}

output "service_task_definition_arns" {
  value = {
    api       = aws_ecs_task_definition.api.arn
    web       = aws_ecs_task_definition.web.arn
    worker    = aws_ecs_task_definition.worker.arn
    scheduler = aws_ecs_task_definition.scheduler.arn
  }
}

output "service_desired_counts" {
  description = "Release-managed target task counts activated only after migrations succeed."
  value       = var.desired_counts
}

output "private_subnet_ids" {
  value = var.private_subnet_ids
}
