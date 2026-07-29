data "aws_caller_identity" "current" {}
data "aws_partition" "current" {}

check "bedrock_configuration_is_complete" {
  assert {
    condition = (
      (var.bedrock_model_arn == "" && var.bedrock_model_id == "") ||
      (var.bedrock_model_arn != "" && var.bedrock_model_id != "")
    )
    error_message = "Bedrock model ARN and model ID must be configured together."
  }
}

data "aws_iam_policy_document" "logs_kms" {
  # checkov:skip=CKV_AWS_109:This is a KMS resource policy, not an identity policy; the account-root statement is the required key-administration control plane.
  # checkov:skip=CKV_AWS_111:KMS key policies require Resource "*" because the policy is attached to the key being created.
  # checkov:skip=CKV_AWS_356:KMS key policies require Resource "*" because the policy is attached to the key being created.
  statement {
    sid       = "AccountAdministration"
    effect    = "Allow"
    actions   = ["kms:*"]
    resources = ["*"]

    principals {
      type = "AWS"
      identifiers = [
        "arn:${data.aws_partition.current.partition}:iam::${data.aws_caller_identity.current.account_id}:root"
      ]
    }
  }

  statement {
    sid    = "CloudWatchLogsEncryption"
    effect = "Allow"
    actions = [
      "kms:Decrypt",
      "kms:DescribeKey",
      "kms:Encrypt",
      "kms:GenerateDataKey*",
      "kms:ReEncrypt*",
    ]
    resources = ["*"]

    principals {
      type        = "Service"
      identifiers = ["logs.${var.aws_region}.amazonaws.com"]
    }

    condition {
      test     = "ArnLike"
      variable = "kms:EncryptionContext:aws:logs:arn"
      values = [
        "arn:${data.aws_partition.current.partition}:logs:${var.aws_region}:${data.aws_caller_identity.current.account_id}:log-group:/cloudops/${var.environment}/*"
      ]
    }
  }
}

resource "aws_kms_key" "logs" {
  description             = "${var.name} CloudWatch logs"
  deletion_window_in_days = 30
  enable_key_rotation     = true
  policy                  = data.aws_iam_policy_document.logs_kms.json
  tags                    = var.tags
}

resource "aws_kms_alias" "logs" {
  name          = "alias/${var.name}-logs"
  target_key_id = aws_kms_key.logs.key_id
}

resource "aws_ecr_repository" "images" {
  for_each = toset(["api", "web"])

  name                 = "${var.name}-${each.key}"
  image_tag_mutability = "IMMUTABLE"
  force_delete         = false

  encryption_configuration {
    encryption_type = "KMS"
    kms_key         = aws_kms_key.logs.arn
  }

  image_scanning_configuration {
    scan_on_push = true
  }

  tags = var.tags
}

resource "aws_ecr_lifecycle_policy" "images" {
  for_each = aws_ecr_repository.images

  repository = each.value.name
  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "Retain the most recent 50 immutable images"
      selection = {
        tagStatus   = "any"
        countType   = "imageCountMoreThan"
        countNumber = 50
      }
      action = { type = "expire" }
    }]
  })
}

resource "aws_ecs_cluster" "this" {
  name = var.name

  setting {
    name  = "containerInsights"
    value = "enabled"
  }

  tags = var.tags
}

resource "aws_cloudwatch_log_group" "services" {
  for_each = toset(["api", "web", "scheduler", "worker", "migration"])

  name              = "/cloudops/${var.environment}/${each.key}"
  retention_in_days = var.log_retention_days
  kms_key_id        = aws_kms_key.logs.arn
  tags              = var.tags
}

data "aws_iam_policy_document" "ecs_assume" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "execution" {
  name               = "${var.name}-ecs-execution"
  assume_role_policy = data.aws_iam_policy_document.ecs_assume.json
  tags               = var.tags
}

resource "aws_iam_role_policy_attachment" "execution" {
  role       = aws_iam_role.execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

data "aws_iam_policy_document" "execution_secrets" {
  statement {
    sid       = "ReadNamedRuntimeSecret"
    effect    = "Allow"
    actions   = ["secretsmanager:GetSecretValue"]
    resources = [var.runtime_secret_arn]
  }

  statement {
    sid       = "DecryptRuntimeSecret"
    effect    = "Allow"
    actions   = ["kms:Decrypt"]
    resources = [var.secrets_kms_key_arn]

    condition {
      test     = "StringEquals"
      variable = "kms:ViaService"
      values   = ["secretsmanager.${var.aws_region}.amazonaws.com"]
    }
  }
}

resource "aws_iam_role_policy" "execution_secrets" {
  name   = "named-runtime-secret"
  role   = aws_iam_role.execution.id
  policy = data.aws_iam_policy_document.execution_secrets.json
}

resource "aws_iam_role" "task" {
  for_each = toset(["api", "web", "scheduler", "worker", "migration"])

  name               = "${var.name}-${each.key}-task"
  assume_role_policy = data.aws_iam_policy_document.ecs_assume.json
  tags               = merge(var.tags, { Service = each.key })
}

data "aws_iam_policy_document" "assume_customers" {
  count = length(var.customer_role_arns) > 0 ? 1 : 0

  statement {
    sid       = "AssumeOnboardedCustomerDiscoveryRoles"
    effect    = "Allow"
    actions   = ["sts:AssumeRole"]
    resources = sort(tolist(var.customer_role_arns))
  }
}

resource "aws_iam_role_policy" "api_customer_roles" {
  count = length(var.customer_role_arns) > 0 ? 1 : 0

  name   = "assume-onboarded-customer-roles"
  role   = aws_iam_role.task["api"].id
  policy = data.aws_iam_policy_document.assume_customers[0].json
}

resource "aws_iam_role_policy" "worker_customer_roles" {
  count = length(var.customer_role_arns) > 0 ? 1 : 0

  name   = "assume-onboarded-customer-roles"
  role   = aws_iam_role.task["worker"].id
  policy = data.aws_iam_policy_document.assume_customers[0].json
}

data "aws_iam_policy_document" "bedrock" {
  count = var.bedrock_model_arn != "" ? 1 : 0

  statement {
    sid       = "InvokeApprovedBedrockModel"
    effect    = "Allow"
    actions   = ["bedrock:InvokeModel"]
    resources = [var.bedrock_model_arn]
  }
}

resource "aws_iam_role_policy" "api_bedrock" {
  count = var.bedrock_model_arn != "" ? 1 : 0

  name   = "invoke-approved-bedrock-model"
  role   = aws_iam_role.task["api"].id
  policy = data.aws_iam_policy_document.bedrock[0].json
}

data "aws_iam_policy_document" "ses" {
  count = var.ses_identity_arn != "" ? 1 : 0

  statement {
    sid       = "SendFromApprovedIdentity"
    effect    = "Allow"
    actions   = ["ses:SendEmail"]
    resources = [var.ses_identity_arn]
  }
}

resource "aws_iam_role_policy" "worker_ses" {
  count = var.ses_identity_arn != "" ? 1 : 0

  name   = "send-approved-ses-identity"
  role   = aws_iam_role.task["worker"].id
  policy = data.aws_iam_policy_document.ses[0].json
}

resource "aws_security_group" "load_balancer" {
  name_prefix = "${var.name}-alb-"
  description = "Public staging or production entry point"
  vpc_id      = var.vpc_id
  tags        = var.tags

  ingress {
    description = var.enable_http_only_staging ? "Temporary staging HTTP" : "HTTPS"
    protocol    = "tcp"
    from_port   = var.enable_http_only_staging ? 80 : 443
    to_port     = var.enable_http_only_staging ? 80 : 443
    cidr_blocks = ["0.0.0.0/0"]
  }

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_security_group" "application" {
  name_prefix = "${var.name}-application-"
  description = "Private ECS tasks"
  vpc_id      = var.vpc_id
  tags        = var.tags

  egress {
    description = "TLS to AWS APIs and approved customer endpoints through NAT"
    protocol    = "tcp"
    from_port   = 443
    to_port     = 443
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    description = "PostgreSQL within VPC"
    protocol    = "tcp"
    from_port   = 5432
    to_port     = 5432
    cidr_blocks = [var.vpc_cidr]
  }

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_vpc_security_group_egress_rule" "alb_api" {
  security_group_id            = aws_security_group.load_balancer.id
  description                  = "API target traffic"
  ip_protocol                  = "tcp"
  from_port                    = 8000
  to_port                      = 8000
  referenced_security_group_id = aws_security_group.application.id
}

resource "aws_vpc_security_group_egress_rule" "alb_web" {
  security_group_id            = aws_security_group.load_balancer.id
  description                  = "Web target traffic"
  ip_protocol                  = "tcp"
  from_port                    = 8080
  to_port                      = 8080
  referenced_security_group_id = aws_security_group.application.id
}

resource "aws_vpc_security_group_ingress_rule" "application_api" {
  security_group_id            = aws_security_group.application.id
  description                  = "API traffic from ALB"
  ip_protocol                  = "tcp"
  from_port                    = 8000
  to_port                      = 8000
  referenced_security_group_id = aws_security_group.load_balancer.id
}

resource "aws_vpc_security_group_ingress_rule" "application_web" {
  security_group_id            = aws_security_group.application.id
  description                  = "Web traffic from ALB"
  ip_protocol                  = "tcp"
  from_port                    = 8080
  to_port                      = 8080
  referenced_security_group_id = aws_security_group.load_balancer.id
}

resource "aws_s3_bucket" "alb_access_logs" {
  bucket = "${var.name}-alb-access-logs"

  # checkov:skip=CKV_AWS_18:This is the terminal ALB access-log destination; recursively logging it would create an unbounded log loop.
  # checkov:skip=CKV_AWS_144:Cross-region replication is deferred until a separately approved disaster-recovery region exists.
  # checkov:skip=CKV_AWS_145:ALB access-log delivery requires SSE-S3; the bucket is private, versioned, and contains request metadata rather than application secrets.
}

resource "aws_s3_bucket_ownership_controls" "alb_access_logs" {
  bucket = aws_s3_bucket.alb_access_logs.id

  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

resource "aws_s3_bucket_public_access_block" "alb_access_logs" {
  bucket                  = aws_s3_bucket.alb_access_logs.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "alb_access_logs" {
  bucket = aws_s3_bucket.alb_access_logs.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_versioning" "alb_access_logs" {
  bucket = aws_s3_bucket.alb_access_logs.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "alb_access_logs" {
  bucket = aws_s3_bucket.alb_access_logs.id

  rule {
    id     = "retain-alb-access-logs"
    status = "Enabled"

    filter {}

    expiration {
      days = 365
    }

    abort_incomplete_multipart_upload {
      days_after_initiation = 7
    }
  }
}

data "aws_iam_policy_document" "alb_access_logs" {
  statement {
    sid     = "AllowAlbLogDelivery"
    effect  = "Allow"
    actions = ["s3:PutObject"]
    resources = [
      "${aws_s3_bucket.alb_access_logs.arn}/alb/AWSLogs/${data.aws_caller_identity.current.account_id}/*",
    ]

    principals {
      type        = "Service"
      identifiers = ["logdelivery.elasticloadbalancing.amazonaws.com"]
    }

    condition {
      test     = "ArnLike"
      variable = "aws:SourceArn"
      values = [
        "arn:${data.aws_partition.current.partition}:elasticloadbalancing:${var.aws_region}:${data.aws_caller_identity.current.account_id}:loadbalancer/*",
      ]
    }
  }
}

resource "aws_s3_bucket_policy" "alb_access_logs" {
  bucket = aws_s3_bucket.alb_access_logs.id
  policy = data.aws_iam_policy_document.alb_access_logs.json
}

resource "aws_s3_bucket_notification" "alb_access_logs" {
  bucket      = aws_s3_bucket.alb_access_logs.id
  eventbridge = true
}

resource "aws_lb" "this" {
  # checkov:skip=CKV2_AWS_20:Temporary HTTP is reachable only when the validated staging-only escape hatch is true; production cannot enable it, and HTTPS remains the default.
  name                       = substr(var.name, 0, 32)
  internal                   = false
  load_balancer_type         = "application"
  security_groups            = [aws_security_group.load_balancer.id]
  subnets                    = var.public_subnet_ids
  drop_invalid_header_fields = true
  enable_deletion_protection = var.enable_deletion_protection
  tags                       = var.tags

  access_logs {
    bucket  = aws_s3_bucket.alb_access_logs.id
    prefix  = "alb"
    enabled = true
  }

  depends_on = [aws_s3_bucket_policy.alb_access_logs]
}

resource "aws_lb_target_group" "api" {
  # checkov:skip=CKV_AWS_378:TLS terminates at the ALB; target traffic stays in private subnets and is restricted to the ALB security group.
  name        = substr("${var.name}-api", 0, 32)
  port        = 8000
  protocol    = "HTTP"
  target_type = "ip"
  vpc_id      = var.vpc_id

  health_check {
    enabled             = true
    path                = "/ready"
    matcher             = "200"
    healthy_threshold   = 2
    unhealthy_threshold = 3
  }

  deregistration_delay = 30
  tags                 = var.tags
}

resource "aws_lb_target_group" "web" {
  # checkov:skip=CKV_AWS_378:TLS terminates at the ALB; target traffic stays in private subnets and is restricted to the ALB security group.
  name        = substr("${var.name}-web", 0, 32)
  port        = 8080
  protocol    = "HTTP"
  target_type = "ip"
  vpc_id      = var.vpc_id

  health_check {
    enabled             = true
    path                = "/healthz"
    matcher             = "200"
    healthy_threshold   = 2
    unhealthy_threshold = 3
  }

  deregistration_delay = 30
  tags                 = var.tags
}

resource "aws_lb_listener" "https" {
  count = var.enable_http_only_staging ? 0 : 1

  load_balancer_arn = aws_lb.this.arn
  port              = 443
  protocol          = "HTTPS"
  ssl_policy        = "ELBSecurityPolicy-TLS13-1-2-2021-06"
  certificate_arn   = var.certificate_arn

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.web.arn
  }
}

resource "aws_lb_listener_rule" "api_https" {
  count = var.enable_http_only_staging ? 0 : 1

  listener_arn = aws_lb_listener.https[0].arn
  priority     = 10

  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.api.arn
  }

  condition {
    path_pattern {
      values = ["/api/*", "/health", "/ready"]
    }
  }
}

resource "aws_lb_listener" "temporary_staging_http" {
  # checkov:skip=CKV_AWS_2:Temporary staging-only listener while DNS and ACM validation are pending; production cannot enable this resource.
  # checkov:skip=CKV_AWS_103:Temporary staging-only HTTP listener has no TLS policy by design; production cannot enable this resource.
  count = var.enable_http_only_staging ? 1 : 0

  load_balancer_arn = aws_lb.this.arn
  port              = 80
  protocol          = "HTTP"

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.web.arn
  }
}

resource "aws_lb_listener_rule" "api_temporary_staging_http" {
  count = var.enable_http_only_staging ? 1 : 0

  listener_arn = aws_lb_listener.temporary_staging_http[0].arn
  priority     = 10

  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.api.arn
  }

  condition {
    path_pattern {
      values = ["/api/*", "/health", "/ready"]
    }
  }
}

locals {
  common_environment = [
    { name = "APP_ENV", value = var.environment },
    { name = "CORS_ALLOWED_ORIGINS", value = join(",", var.allowed_origins) },
    { name = "TRUSTED_HOSTS", value = join(",", var.trusted_hosts) },
    { name = "FRONTEND_URL", value = var.frontend_url },
    { name = "ALLOW_INSECURE_STAGING_TRANSPORT", value = tostring(var.enable_http_only_staging) },
    { name = "COOKIE_SECURE", value = tostring(!var.enable_http_only_staging) },
    { name = "HSTS_ENABLED", value = tostring(!var.enable_http_only_staging) },
    {
      name = "AWS_TRUSTED_PRINCIPAL_ARNS"
      value = join(",", [
        aws_iam_role.task["api"].arn,
        aws_iam_role.task["worker"].arn,
      ])
    },
    { name = "AI_PROVIDER", value = var.bedrock_model_arn == "" ? "mock" : "bedrock" },
    { name = "AWS_BEDROCK_ENABLED", value = tostring(var.bedrock_model_arn != "") },
    { name = "AWS_BEDROCK_REGION", value = var.aws_region },
    { name = "AWS_BEDROCK_MODEL_ID", value = var.bedrock_model_id },
    { name = "NOTIFICATION_PROVIDER", value = var.ses_identity_arn == "" ? "mock" : "ses" },
    { name = "AWS_SES_ENABLED", value = tostring(var.ses_identity_arn != "") },
    { name = "AWS_SES_REGION", value = var.aws_region },
    { name = "REMEDIATION_EXECUTION_ENABLED", value = "false" },
    { name = "REMEDIATION_LIVE_AWS_ENABLED", value = "false" },
  ]
  api_secrets = concat(
    [
      {
        name      = "DATABASE_URL"
        valueFrom = "${var.runtime_secret_arn}:DATABASE_URL::"
      },
      {
        name      = "JWT_SECRET_KEY"
        valueFrom = "${var.runtime_secret_arn}:JWT_SECRET_KEY::"
      },
    ],
    var.ses_identity_arn == "" ? [] : [
      {
        name      = "AWS_SES_FROM_EMAIL"
        valueFrom = "${var.runtime_secret_arn}:AWS_SES_FROM_EMAIL::"
      },
    ],
  )
  api_container = {
    name        = "api"
    image       = var.api_image
    essential   = true
    environment = local.common_environment
    secrets     = local.api_secrets
    portMappings = [{
      name          = "api"
      containerPort = 8000
      protocol      = "tcp"
    }]
    readonlyRootFilesystem = true
    user                   = "cloudops"
    linuxParameters = {
      initProcessEnabled = true
    }
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        awslogs-group         = aws_cloudwatch_log_group.services["api"].name
        awslogs-region        = var.aws_region
        awslogs-stream-prefix = "api"
      }
    }
  }
  worker_container = {
    name                   = "worker"
    image                  = var.api_image
    essential              = true
    command                = ["python", "-m", "app.worker.job_worker"]
    environment            = local.common_environment
    secrets                = local.api_secrets
    readonlyRootFilesystem = true
    user                   = "cloudops"
    linuxParameters = {
      initProcessEnabled = true
    }
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        awslogs-group         = aws_cloudwatch_log_group.services["worker"].name
        awslogs-region        = var.aws_region
        awslogs-stream-prefix = "worker"
      }
    }
  }
  scheduler_container = merge(local.worker_container, {
    name    = "scheduler"
    command = ["python", "-m", "app.worker.scheduler_worker"]
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        awslogs-group         = aws_cloudwatch_log_group.services["scheduler"].name
        awslogs-region        = var.aws_region
        awslogs-stream-prefix = "scheduler"
      }
    }
  })
  migration_container = merge(local.api_container, {
    name         = "migration"
    command      = ["python", "-m", "alembic", "upgrade", "head"]
    portMappings = []
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        awslogs-group         = aws_cloudwatch_log_group.services["migration"].name
        awslogs-region        = var.aws_region
        awslogs-stream-prefix = "migration"
      }
    }
  })
}

resource "aws_ecs_task_definition" "api" {
  family                   = "${var.name}-api"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = 512
  memory                   = 1024
  execution_role_arn       = aws_iam_role.execution.arn
  task_role_arn            = aws_iam_role.task["api"].arn
  container_definitions    = jsonencode([local.api_container])
  tags                     = var.tags
}

resource "aws_ecs_task_definition" "web" {
  family                   = "${var.name}-web"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = 256
  memory                   = 512
  execution_role_arn       = aws_iam_role.execution.arn
  task_role_arn            = aws_iam_role.task["web"].arn
  container_definitions = jsonencode([{
    name      = "web"
    image     = var.web_image
    essential = true
    portMappings = [{
      name          = "web"
      containerPort = 8080
      protocol      = "tcp"
    }]
    readonlyRootFilesystem = true
    user                   = "nginx"
    linuxParameters = {
      initProcessEnabled = true
    }
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        awslogs-group         = aws_cloudwatch_log_group.services["web"].name
        awslogs-region        = var.aws_region
        awslogs-stream-prefix = "web"
      }
    }
  }])
  tags = var.tags
}

resource "aws_ecs_task_definition" "worker" {
  family                   = "${var.name}-worker"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = 512
  memory                   = 1024
  execution_role_arn       = aws_iam_role.execution.arn
  task_role_arn            = aws_iam_role.task["worker"].arn
  container_definitions    = jsonencode([local.worker_container])
  tags                     = var.tags
}

resource "aws_ecs_task_definition" "scheduler" {
  family                   = "${var.name}-scheduler"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = 256
  memory                   = 512
  execution_role_arn       = aws_iam_role.execution.arn
  task_role_arn            = aws_iam_role.task["scheduler"].arn
  container_definitions    = jsonencode([local.scheduler_container])
  tags                     = var.tags
}

resource "aws_ecs_task_definition" "migration" {
  family                   = "${var.name}-migration"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = 256
  memory                   = 512
  execution_role_arn       = aws_iam_role.execution.arn
  task_role_arn            = aws_iam_role.task["migration"].arn
  container_definitions    = jsonencode([local.migration_container])
  tags                     = var.tags
}

resource "aws_ecs_service" "api" {
  name            = "${var.name}-api"
  cluster         = aws_ecs_cluster.this.id
  task_definition = aws_ecs_task_definition.api.arn
  desired_count   = 0
  launch_type     = "FARGATE"

  network_configuration {
    assign_public_ip = false
    subnets          = var.private_subnet_ids
    security_groups  = [aws_security_group.application.id]
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.api.arn
    container_name   = "api"
    container_port   = 8000
  }

  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }

  deployment_minimum_healthy_percent = 100
  deployment_maximum_percent         = 200
  health_check_grace_period_seconds  = 60
  enable_execute_command             = false
  tags                               = var.tags

  depends_on = [
    aws_lb_listener.https,
    aws_lb_listener.temporary_staging_http,
  ]

  lifecycle {
    ignore_changes = [task_definition, desired_count]
  }
}

resource "aws_ecs_service" "web" {
  name            = "${var.name}-web"
  cluster         = aws_ecs_cluster.this.id
  task_definition = aws_ecs_task_definition.web.arn
  desired_count   = 0
  launch_type     = "FARGATE"

  network_configuration {
    assign_public_ip = false
    subnets          = var.private_subnet_ids
    security_groups  = [aws_security_group.application.id]
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.web.arn
    container_name   = "web"
    container_port   = 8080
  }

  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }

  deployment_minimum_healthy_percent = 100
  deployment_maximum_percent         = 200
  health_check_grace_period_seconds  = 30
  enable_execute_command             = false
  tags                               = var.tags

  depends_on = [
    aws_lb_listener.https,
    aws_lb_listener.temporary_staging_http,
  ]

  lifecycle {
    ignore_changes = [task_definition, desired_count]
  }
}

resource "aws_ecs_service" "worker" {
  name            = "${var.name}-worker"
  cluster         = aws_ecs_cluster.this.id
  task_definition = aws_ecs_task_definition.worker.arn
  desired_count   = 0
  launch_type     = "FARGATE"

  network_configuration {
    assign_public_ip = false
    subnets          = var.private_subnet_ids
    security_groups  = [aws_security_group.application.id]
  }

  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }

  enable_execute_command = false
  tags                   = var.tags

  lifecycle {
    ignore_changes = [task_definition, desired_count]
  }
}

resource "aws_ecs_service" "scheduler" {
  name            = "${var.name}-scheduler"
  cluster         = aws_ecs_cluster.this.id
  task_definition = aws_ecs_task_definition.scheduler.arn
  desired_count   = 0
  launch_type     = "FARGATE"

  network_configuration {
    assign_public_ip = false
    subnets          = var.private_subnet_ids
    security_groups  = [aws_security_group.application.id]
  }

  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }

  enable_execute_command = false
  tags                   = var.tags

  lifecycle {
    ignore_changes = [task_definition, desired_count]
  }
}

resource "aws_wafv2_web_acl" "this" {
  name  = var.name
  scope = "REGIONAL"

  default_action {
    allow {}
  }

  rule {
    name     = "AWSManagedRulesCommonRuleSet"
    priority = 10

    override_action {
      none {}
    }

    statement {
      managed_rule_group_statement {
        name        = "AWSManagedRulesCommonRuleSet"
        vendor_name = "AWS"
      }
    }

    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "${var.name}-common"
      sampled_requests_enabled   = true
    }
  }

  rule {
    name     = "AWSManagedRulesKnownBadInputsRuleSet"
    priority = 20

    override_action {
      none {}
    }

    statement {
      managed_rule_group_statement {
        name        = "AWSManagedRulesKnownBadInputsRuleSet"
        vendor_name = "AWS"
      }
    }

    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "${var.name}-known-bad"
      sampled_requests_enabled   = true
    }
  }

  rule {
    name     = "AWSManagedRulesAnonymousIpList"
    priority = 30

    override_action {
      none {}
    }

    statement {
      managed_rule_group_statement {
        name        = "AWSManagedRulesAnonymousIpList"
        vendor_name = "AWS"
      }
    }

    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "${var.name}-anonymous-ip"
      sampled_requests_enabled   = true
    }
  }

  visibility_config {
    cloudwatch_metrics_enabled = true
    metric_name                = var.name
    sampled_requests_enabled   = true
  }

  tags = var.tags
}

resource "aws_cloudwatch_log_group" "waf" {
  name              = "aws-waf-logs-${var.name}"
  retention_in_days = var.log_retention_days
  kms_key_id        = aws_kms_key.logs.arn
  tags              = var.tags
}

resource "aws_wafv2_web_acl_logging_configuration" "this" {
  resource_arn            = aws_wafv2_web_acl.this.arn
  log_destination_configs = [aws_cloudwatch_log_group.waf.arn]

  redacted_fields {
    single_header {
      name = "authorization"
    }
  }

  redacted_fields {
    single_header {
      name = "cookie"
    }
  }
}

resource "aws_wafv2_web_acl_association" "this" {
  resource_arn = aws_lb.this.arn
  web_acl_arn  = aws_wafv2_web_acl.this.arn
}

resource "aws_sns_topic" "alarms" {
  name              = "${var.name}-alarms"
  kms_master_key_id = "alias/aws/sns"
  tags              = var.tags
}

resource "aws_sns_topic_subscription" "email" {
  count = var.alarm_email_endpoint == "" ? 0 : 1

  topic_arn = aws_sns_topic.alarms.arn
  protocol  = "email"
  endpoint  = var.alarm_email_endpoint
}

resource "aws_cloudwatch_metric_alarm" "alb_5xx" {
  alarm_name          = "${var.name}-alb-5xx"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "HTTPCode_ELB_5XX_Count"
  namespace           = "AWS/ApplicationELB"
  period              = 60
  statistic           = "Sum"
  threshold           = 5
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.alarms.arn]

  dimensions = {
    LoadBalancer = aws_lb.this.arn_suffix
  }

  tags = var.tags
}

resource "aws_cloudwatch_metric_alarm" "api_unhealthy" {
  alarm_name          = "${var.name}-api-unhealthy"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "UnHealthyHostCount"
  namespace           = "AWS/ApplicationELB"
  period              = 60
  statistic           = "Maximum"
  threshold           = 0
  treat_missing_data  = "breaching"
  alarm_actions       = [aws_sns_topic.alarms.arn]

  dimensions = {
    LoadBalancer = aws_lb.this.arn_suffix
    TargetGroup  = aws_lb_target_group.api.arn_suffix
  }

  tags = var.tags
}

resource "aws_cloudwatch_log_metric_filter" "api_errors" {
  name           = "${var.name}-api-errors"
  log_group_name = aws_cloudwatch_log_group.services["api"].name
  pattern        = "{ $.event_name = \"request.completed\" && $.result = \"failed\" }"

  metric_transformation {
    name      = "ApiErrorCount"
    namespace = "CloudOps/${var.environment}"
    value     = "1"
  }
}

resource "aws_cloudwatch_log_metric_filter" "request_latency" {
  name           = "${var.name}-request-latency"
  log_group_name = aws_cloudwatch_log_group.services["api"].name
  pattern        = "{ $.event_name = \"request.completed\" && $.duration_ms = * }"

  metric_transformation {
    name      = "RequestDurationMs"
    namespace = "CloudOps/${var.environment}"
    value     = "$.duration_ms"
  }
}

resource "aws_cloudwatch_log_metric_filter" "queue_available" {
  name           = "${var.name}-queue-available"
  log_group_name = aws_cloudwatch_log_group.services["worker"].name
  pattern        = "{ $.event_name = \"platform.queue.snapshot\" && $.queue_available = * }"

  metric_transformation {
    name      = "QueueAvailable"
    namespace = "CloudOps/${var.environment}"
    value     = "$.queue_available"
  }
}

resource "aws_cloudwatch_log_metric_filter" "queue_dead_lettered" {
  name           = "${var.name}-queue-dead-lettered"
  log_group_name = aws_cloudwatch_log_group.services["worker"].name
  pattern        = "{ $.event_name = \"platform.queue.snapshot\" && $.queue_dead_lettered = * }"

  metric_transformation {
    name      = "QueueDeadLettered"
    namespace = "CloudOps/${var.environment}"
    value     = "$.queue_dead_lettered"
  }
}

resource "aws_cloudwatch_log_metric_filter" "job_failures" {
  name           = "${var.name}-job-failures"
  log_group_name = aws_cloudwatch_log_group.services["worker"].name
  pattern        = "{ $.event_name = \"platform.job.failed\" }"

  metric_transformation {
    name      = "JobFailureCount"
    namespace = "CloudOps/${var.environment}"
    value     = "1"
  }
}

resource "aws_cloudwatch_log_metric_filter" "ai_provider_failures" {
  name           = "${var.name}-ai-provider-failures"
  log_group_name = aws_cloudwatch_log_group.services["api"].name
  pattern        = "{ $.event_name = \"ai.provider.failed\" }"

  metric_transformation {
    name      = "AIProviderFailureCount"
    namespace = "CloudOps/${var.environment}"
    value     = "1"
  }
}

resource "aws_cloudwatch_log_metric_filter" "ai_provider_latency" {
  name           = "${var.name}-ai-provider-latency"
  log_group_name = aws_cloudwatch_log_group.services["api"].name
  pattern        = "{ $.event_name = \"ai.provider.completed\" && $.duration_ms = * }"

  metric_transformation {
    name      = "AIProviderDurationMs"
    namespace = "CloudOps/${var.environment}"
    value     = "$.duration_ms"
  }
}

resource "aws_cloudwatch_log_metric_filter" "notification_failures" {
  name           = "${var.name}-notification-failures"
  log_group_name = aws_cloudwatch_log_group.services["worker"].name
  pattern        = "{ $.event_name = \"notification.provider.completed\" && $.result = \"failure\" }"

  metric_transformation {
    name      = "NotificationFailureCount"
    namespace = "CloudOps/${var.environment}"
    value     = "1"
  }
}

resource "aws_cloudwatch_log_metric_filter" "remediation_failures" {
  name           = "${var.name}-remediation-failures"
  log_group_name = aws_cloudwatch_log_group.services["worker"].name
  pattern        = "{ $.event_name = \"platform.job.failed\" && $.job_type = \"remediation_simulation\" }"

  metric_transformation {
    name      = "RemediationFailureCount"
    namespace = "CloudOps/${var.environment}"
    value     = "1"
  }
}

resource "aws_cloudwatch_metric_alarm" "api_latency" {
  alarm_name          = "${var.name}-api-p95-latency"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 3
  metric_name         = "TargetResponseTime"
  namespace           = "AWS/ApplicationELB"
  period              = 60
  extended_statistic  = "p95"
  threshold           = 1.5
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.alarms.arn]

  dimensions = {
    LoadBalancer = aws_lb.this.arn_suffix
    TargetGroup  = aws_lb_target_group.api.arn_suffix
  }

  tags = var.tags
}

resource "aws_cloudwatch_metric_alarm" "dead_letters" {
  alarm_name          = "${var.name}-dead-letter-growth"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "QueueDeadLettered"
  namespace           = "CloudOps/${var.environment}"
  period              = 60
  statistic           = "Maximum"
  threshold           = 0
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.alarms.arn]
  tags                = var.tags
}

resource "aws_cloudwatch_metric_alarm" "queue_depth" {
  alarm_name          = "${var.name}-queue-depth"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 5
  metric_name         = "QueueAvailable"
  namespace           = "CloudOps/${var.environment}"
  period              = 60
  statistic           = "Maximum"
  threshold           = 100
  treat_missing_data  = "breaching"
  alarm_actions       = [aws_sns_topic.alarms.arn]
  tags                = var.tags
}

resource "aws_cloudwatch_dashboard" "this" {
  dashboard_name = var.name
  dashboard_body = jsonencode({
    widgets = [
      {
        type   = "metric"
        x      = 0
        y      = 0
        width  = 12
        height = 6
        properties = {
          region = var.aws_region
          title  = "ALB responses"
          metrics = [
            ["AWS/ApplicationELB", "RequestCount", "LoadBalancer", aws_lb.this.arn_suffix],
            [".", "HTTPCode_ELB_5XX_Count", ".", "."],
          ]
          period = 60
          stat   = "Sum"
        }
      },
      {
        type   = "metric"
        x      = 12
        y      = 0
        width  = 12
        height = 6
        properties = {
          region = var.aws_region
          title  = "ECS CPU"
          metrics = [
            ["AWS/ECS", "CPUUtilization", "ClusterName", aws_ecs_cluster.this.name, "ServiceName", aws_ecs_service.api.name],
            [".", ".", ".", ".", "ServiceName", aws_ecs_service.worker.name],
          ]
          period = 60
          stat   = "Average"
        }
      },
    ]
  })
}
