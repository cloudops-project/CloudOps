output "application_security_group_id" {
  value = aws_security_group.application.id
}

output "cluster_name" {
  value = aws_ecs_cluster.this.name
}

output "load_balancer_dns_name" {
  value = aws_lb.this.dns_name
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

output "private_subnet_ids" {
  value = var.private_subnet_ids
}
