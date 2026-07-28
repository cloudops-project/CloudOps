variable "name" {
  type = string
}

variable "environment" {
  type = string

  validation {
    condition     = contains(["staging", "production"], var.environment)
    error_message = "environment must be staging or production."
  }
}

variable "aws_region" {
  type = string
}

variable "vpc_id" {
  type = string
}

variable "vpc_cidr" {
  type = string
}

variable "public_subnet_ids" {
  type = list(string)
}

variable "private_subnet_ids" {
  type = list(string)
}

variable "api_image" {
  description = "Immutable API/worker ECR image reference."
  type        = string

  validation {
    condition     = can(regex("@sha256:[0-9a-f]{64}$", var.api_image))
    error_message = "api_image must be an immutable sha256 digest reference."
  }
}

variable "web_image" {
  description = "Immutable web ECR image reference."
  type        = string

  validation {
    condition     = can(regex("@sha256:[0-9a-f]{64}$", var.web_image))
    error_message = "web_image must be an immutable sha256 digest reference."
  }
}

variable "runtime_secret_arn" {
  description = "Secrets Manager JSON secret populated out of band for application runtime."
  type        = string
}

variable "secrets_kms_key_arn" {
  type = string
}

variable "customer_role_arns" {
  description = "Exact onboarded customer role ARNs allowed for sts:AssumeRole."
  type        = set(string)
  default     = []
}

variable "bedrock_model_arn" {
  type    = string
  default = ""
}

variable "bedrock_model_id" {
  description = "Approved Bedrock model or inference-profile identifier."
  type        = string
  default     = ""
}

variable "ses_identity_arn" {
  type    = string
  default = ""
}

variable "frontend_url" {
  type = string

  validation {
    condition     = can(regex("^https://", var.frontend_url))
    error_message = "frontend_url must use HTTPS."
  }
}

variable "trusted_hosts" {
  type = list(string)

  validation {
    condition = (
      length(var.trusted_hosts) > 0 &&
      alltrue([for host in var.trusted_hosts : host != "*" && !strcontains(host, "://")])
    )
    error_message = "trusted_hosts must contain host names without schemes or a global wildcard."
  }
}

variable "certificate_arn" {
  description = "ACM certificate ARN required for the HTTPS-only public listener."
  type        = string

  validation {
    condition     = can(regex("^arn:aws[a-z-]*:acm:", var.certificate_arn))
    error_message = "certificate_arn must be an ACM certificate ARN."
  }
}

variable "allowed_origins" {
  type = list(string)

  validation {
    condition     = length(var.allowed_origins) > 0
    error_message = "At least one explicit allowed origin is required."
  }
}

variable "desired_counts" {
  type = object({
    api       = number
    web       = number
    scheduler = number
    worker    = number
  })
}

variable "log_retention_days" {
  type = number
}

variable "alarm_email_endpoint" {
  description = "Optional operator email for alarm subscription; not a secret."
  type        = string
  default     = ""
}

variable "enable_deletion_protection" {
  type = bool
}

variable "tags" {
  type    = map(string)
  default = {}
}
