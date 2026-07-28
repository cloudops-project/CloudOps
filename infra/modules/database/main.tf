resource "aws_kms_key" "database" {
  description             = "${var.name} RDS encryption"
  deletion_window_in_days = 30
  enable_key_rotation     = true
  tags                    = var.tags
}

resource "aws_kms_alias" "database" {
  name          = "alias/${var.name}-database"
  target_key_id = aws_kms_key.database.key_id
}

resource "aws_db_subnet_group" "this" {
  name       = "${var.name}-database"
  subnet_ids = var.private_subnet_ids
  tags       = var.tags
}

resource "aws_security_group" "database" {
  name_prefix = "${var.name}-database-"
  description = "PostgreSQL ingress only from CloudOps application tasks"
  vpc_id      = var.vpc_id
  tags        = var.tags
  egress      = []

  ingress {
    description     = "PostgreSQL from application tasks"
    protocol        = "tcp"
    from_port       = 5432
    to_port         = 5432
    security_groups = [var.application_security_group_id]
  }

  lifecycle {
    create_before_destroy = true
  }
}

data "aws_iam_policy_document" "monitoring_assume" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["monitoring.rds.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "monitoring" {
  name               = "${var.name}-rds-monitoring"
  assume_role_policy = data.aws_iam_policy_document.monitoring_assume.json
  tags               = var.tags
}

resource "aws_iam_role_policy_attachment" "monitoring" {
  role       = aws_iam_role.monitoring.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonRDSEnhancedMonitoringRole"
}

resource "aws_db_instance" "this" {
  identifier = var.name

  engine         = "postgres"
  engine_version = "16"
  instance_class = var.instance_class

  allocated_storage     = var.allocated_storage_gib
  max_allocated_storage = var.max_allocated_storage_gib
  storage_type          = "gp3"
  storage_encrypted     = true
  kms_key_id            = aws_kms_key.database.arn

  db_name  = "cloudops"
  username = "cloudops_runtime"

  manage_master_user_password   = true
  master_user_secret_kms_key_id = aws_kms_key.database.arn

  db_subnet_group_name   = aws_db_subnet_group.this.name
  vpc_security_group_ids = [aws_security_group.database.id]
  publicly_accessible    = false
  multi_az               = var.multi_az

  backup_retention_period = var.backup_retention_days
  backup_window           = "03:00-04:00"
  maintenance_window      = "sun:04:00-sun:05:00"
  copy_tags_to_snapshot   = true
  deletion_protection     = var.deletion_protection
  skip_final_snapshot     = var.skip_final_snapshot
  final_snapshot_identifier = var.skip_final_snapshot ? null : (
    "${var.name}-final"
  )

  auto_minor_version_upgrade      = true
  performance_insights_enabled    = true
  performance_insights_kms_key_id = aws_kms_key.database.arn
  monitoring_interval             = 60
  monitoring_role_arn             = aws_iam_role.monitoring.arn

  enabled_cloudwatch_logs_exports = ["postgresql", "upgrade"]

  tags = var.tags

  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_cloudwatch_metric_alarm" "cpu" {
  alarm_name          = "${var.name}-database-cpu"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 5
  metric_name         = "CPUUtilization"
  namespace           = "AWS/RDS"
  period              = 60
  statistic           = "Average"
  threshold           = 80
  treat_missing_data  = "breaching"
  alarm_actions       = [var.alarm_topic_arn]
  dimensions          = { DBInstanceIdentifier = aws_db_instance.this.id }
  tags                = var.tags
}

resource "aws_cloudwatch_metric_alarm" "storage" {
  alarm_name          = "${var.name}-database-free-storage"
  comparison_operator = "LessThanThreshold"
  evaluation_periods  = 3
  metric_name         = "FreeStorageSpace"
  namespace           = "AWS/RDS"
  period              = 300
  statistic           = "Minimum"
  threshold           = 10737418240
  treat_missing_data  = "breaching"
  alarm_actions       = [var.alarm_topic_arn]
  dimensions          = { DBInstanceIdentifier = aws_db_instance.this.id }
  tags                = var.tags
}

resource "aws_cloudwatch_metric_alarm" "connections" {
  alarm_name          = "${var.name}-database-connections"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 5
  metric_name         = "DatabaseConnections"
  namespace           = "AWS/RDS"
  period              = 60
  statistic           = "Maximum"
  threshold           = 200
  treat_missing_data  = "breaching"
  alarm_actions       = [var.alarm_topic_arn]
  dimensions          = { DBInstanceIdentifier = aws_db_instance.this.id }
  tags                = var.tags
}
