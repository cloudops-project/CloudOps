provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      ManagedBy   = "Terraform"
      Project     = "CloudOps"
      Environment = "staging"
    }
  }
}

locals {
  name     = "cloudops-staging"
  vpc_cidr = "10.20.0.0/16"
  tags = {
    ManagedBy   = "Terraform"
    Project     = "CloudOps"
    Environment = "staging"
  }
}

module "network" {
  source = "../../modules/network"

  name               = local.name
  vpc_cidr           = local.vpc_cidr
  availability_zones = var.availability_zones
  single_nat_gateway = true
  tags               = local.tags
}

module "secrets" {
  source = "../../modules/secrets"

  name                    = "staging"
  secret_names            = ["api-runtime"]
  recovery_window_in_days = 7
  tags                    = local.tags
}

module "platform" {
  source = "../../modules/platform"

  name                       = local.name
  environment                = "staging"
  aws_region                 = var.aws_region
  vpc_id                     = module.network.vpc_id
  vpc_cidr                   = local.vpc_cidr
  public_subnet_ids          = module.network.public_subnet_ids
  private_subnet_ids         = module.network.private_subnet_ids
  api_image                  = var.api_image
  web_image                  = var.web_image
  runtime_secret_arn         = module.secrets.secret_arns["api-runtime"]
  secrets_kms_key_arn        = module.secrets.kms_key_arn
  customer_role_arns         = var.customer_role_arns
  bedrock_model_arn          = var.bedrock_model_arn
  ses_identity_arn           = var.ses_identity_arn
  certificate_arn            = var.certificate_arn
  allowed_origins            = var.allowed_origins
  alarm_email_endpoint       = var.alarm_email_endpoint
  enable_deletion_protection = false
  log_retention_days         = 30
  desired_counts             = { api = 1, web = 1, scheduler = 1, worker = 1 }
  tags                       = local.tags
}

module "database" {
  source = "../../modules/database"

  name                          = local.name
  vpc_id                        = module.network.vpc_id
  private_subnet_ids            = module.network.private_subnet_ids
  application_security_group_id = module.platform.application_security_group_id
  instance_class                = "db.t4g.small"
  allocated_storage_gib         = 20
  max_allocated_storage_gib     = 100
  multi_az                      = false
  deletion_protection           = false
  skip_final_snapshot           = true
  backup_retention_days         = 7
  alarm_topic_arn               = module.platform.alarm_topic_arn
  tags                          = local.tags
}
